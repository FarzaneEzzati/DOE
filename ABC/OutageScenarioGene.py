import pickle
import numpy as np

scens = [3, 4, 6, 8, 9, 15, 18, 19, 22, 26, 27, 34, 41, 42, 56, 60, 64, 68, 70, 80, 87, 94]
probs = [(scens[s] + 1) / (np.sum(scens) + 10) for s in range(len(scens))][::-1]

scens_dic = {i + 1: scens[i] for i in range(len(scens))}
probs_dic = {i + 1: probs[i] for i in range(len(probs))}

with open('Data/OutageScenarios.pkl', 'wb') as handle:
    pickle.dump([scens_dic, probs_dic], handle)
handle.close()
