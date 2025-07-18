import pickle
from static_functions import *
import gurobipy as gp
from gurobipy import quicksum, GRB
env = gp.Env()
env.setParam('OutputFlag', 0)

'''Define keys to be global parameters'''
with open(f'Models/Indices.pkl', 'rb') as f:
    X_keys, Y_keys, Y_int_keys = pickle.load(f)
f.close()

with open('Data/OutageScenarios.pkl', 'rb') as handle:
    scens, probs = pickle.load(handle)
handle.close()

Probs = probs



class MasterProb:
    def __init__(self, model, A, b, ubm, lbm):
        self.master, self.A, self.b, self.ub, self.lb = model, A, b, ubm, lbm
        all_vars = self.master.getVars()
        self.X = {key: all_vars[key - 1] for key in X_keys}
        self.eta = self.master.getVarByName('eta')
        self.master.update()
    def Solve(self):
        self.master.optimize()
        if self.master.status == 2:  # Model feasible
            return [{x_key: self.X[x_key].x for x_key in X_keys}, self.master.ObjVal]
        else:
            return 'InfUnb'
    def AddSplit(self, x_key, bound, split_sense):
        # Updating bounds for the corresponding variable
        if split_sense == 'u':
            self.ub[x_key] = int(bound)
            self.X[x_key].UB = int(bound)
        else:
            self.lb[x_key] = int(bound) + 1
            self.X[x_key].LB = int(bound) + 1
        self.master.update()
    def AddBendersCut(self, bt, ut, lt, Tm, rm, ubm, lbm):
        pir = {s: Probs[s] * (sum(bt[s][row] * rm[s][row] for row in rm[s].keys()) -
                              sum(ut[s][y_key] * ubm[s][y_key] for y_key in Y_keys) +
                              sum(lt[s][y_key] * lbm[s][y_key] for y_key in Y_keys))
               for s in Probs.keys()}
        e = sum(pir.values())
        E = {x_key: 0 for x_key in X_keys}
        for s in Probs.keys():
            for key in Tm[s].keys():
                E[key[1]] += Probs[s] * (bt[s][key[0]] * Tm[s][key])
        self.master.addConstr(self.eta + quicksum(self.X[x_key] * E[x_key] for x_key in X_keys) >= e, name='Benders')
        self.master.update()
    def ReturnModel(self):
        return self.master.copy(), copy.copy(self.A), copy.copy(self.b), copy.copy(self.ub), copy.copy(self.lb)
    def ReturnA_b_ub_lb(self):
        return copy.copy(self.A), copy.copy(self.b), copy.copy(self.ub), copy.copy(self.lb)


class SubProb:
    def __init__(self, model, T, W, r, ub, lb):
        # Save the model in the class
        self.sub, self.T, self.W, self.r, self.ub, self.lb = model, T, W, r, ub, lb
        all_vars = self.sub.getVars()
        self.X = {x_key: all_vars[x_key - 1] for x_key in X_keys}
        self.Y = {y_key: all_vars[y_key - 1] for y_key in Y_keys}
        for y_key in Y_keys:
            self.Y[y_key].UB = self.ub[y_key]
    def FixXSolve(self, x):
        y_values, v_value = None, None
        for x_key in self.X.keys():
            self.X[x_key].UB = x[x_key]
            self.X[x_key].LB = x[x_key]
        self.sub.update()
        self.sub.optimize()
        if self.sub.status == 2:
            # Obtain Y values for all and save in a key-format dictionary
            y_values = {y_key: self.Y[y_key].x for y_key in Y_keys}
            # Save ObjVal
            v_value = self.sub.ObjVal
        return y_values, v_value
    def SolveForBenders(self, x):
        y_values, v_value = None, None
        bt, lt, ut = None, None, None
        for x_key in self.X.keys():
            self.X[x_key].UB = x[x_key]
            self.X[x_key].LB = x[x_key]
        for y_key in Y_keys:
            self.sub.addConstr(self.Y[y_key] <= self.ub[y_key], name=f'Upper[{y_key}]')
            self.sub.addConstr(self.Y[y_key] >= self.lb[y_key], name=f'Lower[{y_key}]')
        self.sub.update()
        self.sub.optimize()

        if self.sub.status == 2:
            y_values = {y_key: self.Y[y_key].x for y_key in Y_keys}
            v_value = self.sub.ObjVal

            bt_cons, ut_cons, lt_cons = [], [], []
            for con in self.sub.getConstrs():
                ConName = con.ConstrName
                if 'Upper' in ConName:
                    ut_cons.append(con)
                elif 'Lower' in ConName:
                    lt_cons.append(con)
                else:
                    bt_cons.append(con)

            bt = {row_key + 1: bt_cons[row_key].Pi for row_key in range(len(bt_cons))}
            ut = {y_key: ut_cons[Y_keys.index(y_key)].Pi for y_key in Y_keys}
            lt = {y_key: lt_cons[Y_keys.index(y_key)].Pi for y_key in Y_keys}
        else:
            self.sub.computeIIS()
            viltd_ctrs = []
            for c in self.sub.getConstrs():
                if c.IISConstr:
                    viltd_ctrs.append(c.ConstrName)
            print(viltd_ctrs)

        for y_key in Y_keys:
            self.sub.remove(self.sub.getConstrByName(f'Upper[{y_key}]'))
            self.sub.remove(self.sub.getConstrByName(f'Lower[{y_key}]'))
        self.sub.update()

        return y_values, v_value, bt, ut, lt
    def AddSplit(self, y_key, split_sense):
        # Update the bound as well in the bound dictionary
        if split_sense == 'u':
            self.Y[y_key].UB = 0
            self.ub[y_key] = 0
        else:
            self.Y[y_key].LB = 1
            self.lb[y_key] = 1
        self.sub.update()
    def ReturnModel(self):
        return self.sub.copy(), copy.copy(self.T), copy.copy(self.W), copy.copy(self.r), copy.copy(self.ub), copy.copy(self.lb)
    def ReturnT_W_r(self):
        return copy.copy(self.T), copy.copy(self.W), copy.copy(self.r)
    def AddCut(self, pi0, pi1, pi2):
        pi1x = quicksum(pi1[x_key] * self.X[x_key] for x_key in X_keys)
        pi2y = quicksum(pi2[y_key] * self.Y[y_key] for y_key in Y_keys)
        self.sub.addConstr(pi2y + pi1x >= pi0, name='CGLP')
        print(pi2y + pi1x >= pi0)
        self.sub.update()
        W_new_row = SparseRowCount(self.W) + 1
        T_new_row = SparseRowCount(self.T) + 1
        for t_index in pi1.keys():
            self.T[(T_new_row, t_index)] = pi1[t_index]
        for w_index in pi2.keys():
            self.W[(W_new_row, w_index)] = pi2[w_index]
        self.r[W_new_row] = pi0
