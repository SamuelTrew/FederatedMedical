import copy
import torch
import torch.nn as nn
import numpy as np

from scipy.stats import beta

from sklearn.metrics import confusion_matrix


class Aggregator():
    def __init__(self, clients, model, rounds, device):
        self.model = model
        self.rounds = rounds
        self.clients = clients

        self.device = device

    # FUNCTION FOR COMPUTING PREDICTIONS
    def predict(self, net, xtst):
        with torch.no_grad():
            outputs = net(xtst.to(self.device))
            _, predicted = torch.max(outputs.to(self.device), 1)
        return predicted.to(self.device)

    # FUNCTION TO MANIPULATE THE MODEL FOR BYZANTINE ADVERSARIES
    def manipulateModel(self, model, alpha=20):
        params = model.named_parameters()
        for name1, param1 in params:
            noise = alpha * torch.randn(param1.data.size()).to(self.device)
            param1.data.copy_(param1.data + noise)

    # FUNCTION TO MERGE THE MODELS
    @staticmethod
    def mergeModels(mOrig, mDest, alphaOrig, alphaDest):
        paramsDest = mDest.named_parameters()
        dictParamsDest = dict(paramsDest)
        paramsOrig = mOrig.named_parameters()
        for name1, param1 in paramsOrig:
            if name1 in dictParamsDest:
                weightedSum = alphaOrig * param1.data \
                              + alphaDest * dictParamsDest[name1].data
                dictParamsDest[name1].data.copy_(weightedSum)

    def trainAndTest(self, xTest, yTest):
        raise Exception("Train method should be override by child class, "
                        "specific to the aggregation strategy.")

    def shareModelAndTrainOnClients(self):
        # Share model with the users
        for client in self.clients:
            broadcastModel = copy.deepcopy(self.model).to(self.device)
            client.updateModel(broadcastModel)
            error, pred = client.trainModel()

            if client.byz:
                # Malicious model update
                # print("Malicous update for user ",u.id)
                self.manipulateModel(client.model)

    def test(self, xTest, yTest):
        # Compute test accuracy
        Ypred = self.predict(self.model, xTest)
        # Confusion matrix and normalized confusion matrix
        mconf = confusion_matrix(yTest.to("cpu"), Ypred.to("cpu"))
        errors = 1 - 1.0 * mconf.diagonal().sum() / xTest.size(0)
        print("Error Rate: ", round(100.0 * errors, 3), "%")
        return errors


# FEDERATED AVERAGING AGGREGATOR
class FAAggregator(Aggregator):

    def trainAndTest(self, xTest, yTest):

        roundsError = torch.zeros(self.rounds)
        for r in range(self.rounds):
            print("Round... ", r)
            self.shareModelAndTrainOnClients()

            # Merge models
            comb = 0.0
            for client in self.clients:
                self.mergeModels(client.model, self.model, client.p, comb)
                comb = 1.0

            roundsError[r] = self.test(xTest, yTest)

        return roundsError


# ROBUST AGGREGATION ALGORITHM
# computes the median of the updates provided by the clients
class COMEDAggregator(Aggregator):

    def trainAndTest(self, xTest, yTest):
        roundsError = torch.zeros(self.rounds)

        for r in range(self.rounds):
            print("Round... ", r)

            self.shareModelAndTrainOnClients()

            # Merge models
            self.model = self.medianModels()

            roundsError[r] = self.test(xTest, yTest)

        return roundsError

    def medianModels(self):
        client1 = self.clients[0]
        model = client1.model
        modelCopy = copy.deepcopy(model)
        params = model.named_parameters()
        for name1, param1 in params:
            m = []
            for client2 in self.clients:
                params2 = client2.model.named_parameters()
                dictParams2 = dict(params2)
                m.append(dictParams2[name1].data.view(-1).to("cpu").numpy())
                # print("Size: ", dictParams2[name1].data.size())
            m = torch.tensor(m)
            med = torch.median(m, dim=0)[0]
            dictParamsm = dict(modelCopy.named_parameters())
            dictParamsm[name1].data.copy_(med.view(dictParamsm[name1].data.size()))
            # print("Median computed, size: ", med.size())
        return modelCopy.to(self.device)


# MULTI-KRUM
class MKRUMAggregator(Aggregator):

    def trainAndTest(self, xTest, yTest):

        userNo = len(self.clients)
        # Number of Byzantine workers to be tolerated
        f = int((userNo - 3) / 2)
        th = userNo - f - 2
        mk = userNo - f

        roundsError = torch.zeros(self.rounds)

        for r in range(self.rounds):
            print("Round... ", r)

            self.shareModelAndTrainOnClients()

            # Compute distances for all users
            scores = torch.zeros(userNo)
            for client in self.clients:
                distances = torch.zeros((userNo, userNo))
                for client2 in self.clients:
                    if client.id != client2.id:
                        distance = self.computeModelDistance(client.model.to(self.device),
                                                             client2.model.to(self.device))
                        distances[client.id - 1][client2.id - 1] = distance
                dd = distances[client.id - 1][:].sort()[0]
                dd = dd.cumsum(0)
                scores[client.id - 1] = dd[th]

            _, idx = scores.sort()
            selected_users = idx[:mk - 1] + 1
            # print("Selected users: ", selected_users)

            comb = 0.0
            for client in self.clients:
                if client.id in selected_users:
                    self.mergeModels(client.model, self.model, 1 / mk, comb)
                    comb = 1.0

            roundsError[r] = self.test(xTest, yTest)

        return roundsError

    def computeModelDistance(self, mOrig, mDest):
        paramsDest = mDest.named_parameters()
        dictParamsDest = dict(paramsDest)
        paramsOrig = mOrig.named_parameters()
        d1 = torch.tensor([]).to(self.device)
        d2 = torch.tensor([]).to(self.device)
        for name1, param1 in paramsOrig:
            if name1 in dictParamsDest:
                d1 = torch.cat((d1, dictParamsDest[name1].data.view(-1)))
                d2 = torch.cat((d2, param1.data.view(-1)))
                # d2 = param1.data
                # sim = cos(d1.view(-1),d2.view(-1))
                # print(name1,param1.size())
                # print("Similarity: ",sim)
        sim = torch.norm(d1 - d2, p=2)
        return sim


class AFAAggregator(Aggregator):

    def trainAndTest(self, xTest, yTest):
        # List of malicious users blocked
        maliciousBlocked = []
        # List with the iteration where a malicious user was bloecked
        maliciousBlockedIt = []
        # List of benign users blocked
        benignBlocked = []
        # List with the iteration where a benign user was bloecked
        benignBlockedIt = []

        roundsError = torch.zeros(self.rounds)

        for r in range(self.rounds):
            print("Round... ", r)

            for client in self.clients:
                broadcastModel = copy.deepcopy(self.model).to(self.device)
                client.updateModel(broadcastModel)
                if not client.blocked:
                    error, pred = client.trainModel()
                    if client.byz:
                        # Malicious model
                        self.manipulateModel(client.model)

            badCount = 2
            slack = 2
            while badCount != 0:
                pT_epoch = 0.0
                for client in self.clients:
                    if self.blockedOrBadUpdate(client):
                        client.pEpoch = client.n * client.score
                        pT_epoch = pT_epoch + client.pEpoch

                for client in self.clients:
                    if self.blockedOrBadUpdate(client):
                        client.pEpoch = client.pEpoch / pT_epoch

                comb = 0.0
                for client in self.clients:
                    if self.blockedOrBadUpdate(client):
                        self.mergeModels(client.model, self.model, client.pEpoch, comb)
                        comb = 1.0

                sim = []
                for client in self.clients:
                    if self.blockedOrBadUpdate(client):
                        client.sim = self.modelSimilarity(self.model, client.model)
                        sim.append(np.asarray(client.sim.to("cpu")))
                        # print("Similarity user ", u.id, ": ", u.sim)

                sim = np.asarray(sim)

                meanS = np.mean(sim)
                medianS = np.median(sim)
                desvS = np.std(sim)

                if meanS < medianS:
                    th = medianS - slack * desvS
                else:
                    th = medianS + slack * desvS

                slack += 0.5

                badCount = 0
                for client in self.clients:
                    if not client.badUpdate:
                        # Malicious self.clients are below the threshold
                        if meanS < medianS:
                            if client.sim < th:
                                # print("Type1")
                                # print("Bad update from user ", u.id)
                                client.badUpdate = True
                                badCount += 1
                                # Malicious self.clients are above the threshold
                        else:
                            if client.sim > th:
                                # print("Type 2")
                                # print("Bad update from user ", u.id)
                                client.badUpdate = True
                                badCount += 1

            pT = 0.0
            for client in self.clients:
                if not client.blocked:
                    self.updateUserScore(client)
                    client.blocked = self.checkBlockedUser(client.alpha, client.beta)
                    if client.blocked:
                        print("USER ", client.id, " BLOCKED!!!")
                        client.p = 0
                        if client.byz:
                            maliciousBlocked.append(client.id)
                            maliciousBlockedIt.append(r)
                        else:
                            benignBlocked.append(client.id)
                            benignBlockedIt.append(r)
                    else:
                        client.p = client.n * client.score
                        pT = pT + client.p

            for client in self.clients:
                client.p = client.p / pT
                # print("Weight user", u.id, ": ", round(u.p,3))

            # Update model with the updated scores
            pT_epoch = 0.0
            for client in self.clients:
                if self.blockedOrBadUpdate(client):
                    client.pEpoch = client.n * client.score
                    pT_epoch = pT_epoch + client.pEpoch

            for client in self.clients:
                if self.blockedOrBadUpdate(client):
                    client.pEpoch = client.pEpoch / pT_epoch

            comb = 0.0
            for client in self.clients:
                if self.blockedOrBadUpdate(client):
                    self.mergeModels(client.model, self.model, client.pEpoch, comb)
                    comb = 1.0

            # Reset badUpdate variable
            for client in self.clients:
                if not client.blocked:
                    client.badUpdate = False

            roundsError[r] = self.test(xTest, yTest)

        return roundsError

    def modelSimilarity(self, mOrig, mDest):
        cos = nn.CosineSimilarity(0)

        d2 = torch.tensor([]).to(self.device)
        d1 = torch.tensor([]).to(self.device)

        paramsOrig = mOrig.named_parameters()
        paramsDest = mDest.named_parameters()
        dictParamsDest = dict(paramsDest)

        for name1, param1 in paramsOrig:
            if name1 in dictParamsDest:
                d1 = torch.cat((d1, dictParamsDest[name1].data.view(-1)))
                d2 = torch.cat((d2, param1.data.view(-1)))
                # d2 = param1.data
                # sim = cos(d1.view(-1),d2.view(-1))
                # print(name1,param1.size())
                # print("Similarity: ",sim)
        sim = cos(d1, d2)
        return sim

    @staticmethod
    def checkBlockedUser(a, b, th=0.95):
        # return beta.cdf(0.5, a, b) > th
        s = beta.cdf(0.5, a, b)
        blocked = False
        if s > th:
            blocked = True
        return blocked


    @staticmethod
    def updateUserScore(client):
        if client.badUpdate:
            client.beta += 1
        else:
            client.alpha += 1
        client.score = client.alpha / client.beta

    @staticmethod
    def blockedOrBadUpdate(client):
        return client.blocked == False | client.badUpdate == False


aggregators = Aggregator.__subclasses__()
