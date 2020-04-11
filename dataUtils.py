import torch
import torchvision.datasets as dset
import torchvision.transforms as transforms

__defaultClientDataSplitPercentage = torch.tensor([0.2, 0.10, 0.15, 0.15, 0.15, 0.15, 0.1])
__defaultLabelsOfInterest = torch.tensor([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])


def loadMNISTdata(percUsers=__defaultClientDataSplitPercentage,
                  labels=__defaultLabelsOfInterest):
    percUsers = percUsers / percUsers.sum()
    userNo = percUsers.size(0)

    xTrn, yTrn, xTst, yTst = __loadMNISTdata()

    xTest, xTrain, yTest, yTrain = __filterByLabelAndShuffle(labels, xTrn, xTst, yTrn, yTst)

    # Splitting data to users corresponding to user percentage param
    ntr_users = (percUsers * xTrain.size(0)).floor().numpy()

    training_data = []
    training_labels = []

    it = 0
    for i in range(userNo):
        x = xTrain[it:it + int(ntr_users[i]), :].clone().detach()
        y = yTrain[it:it + int(ntr_users[i])].clone().detach()
        training_data.append(x)
        training_labels.append(y)
        it = it + int(ntr_users[i])

    return training_data, training_labels, xTest, yTest


def getSyftMNIST(percUsers=__defaultClientDataSplitPercentage,
                 labels=__defaultLabelsOfInterest):
    percUsers = percUsers / percUsers.sum()
    userNo = percUsers.size(0)

    xTrn, yTrn, xTst, yTst = __loadMNISTdata()

    xTest, xTrain, yTest, yTrain = __filterByLabelAndShuffle(labels, xTrn, xTst, yTrn, yTst)

    # Splitting data to users corresponding to user percentage param
    ntr_users = (percUsers * xTrain.size(0)).floor().numpy()

    training_data = []
    training_labels = []

    it = 0
    for i in range(userNo):
        x = xTrain[it:it + int(ntr_users[i]), :].clone().detach()
        y = yTrain[it:it + int(ntr_users[i])].clone().detach()
        it = it + int(ntr_users[i])

        # create syft client sending them x, y

    return training_data, training_labels, xTest, yTest


def __loadMNISTdata():
    trans = transforms.Compose([transforms.ToTensor(),
                                transforms.Normalize((0.5,), (1.0,))])

    # if not exist, download mnist dataset
    trainSet = dset.MNIST('data', train=True, transform=trans, download=True)
    testSet = dset.MNIST('data', train=False, transform=trans, download=True)

    # Scale pixel intensities to [-1, 1]
    x = trainSet.data
    x = 2 * (x.float() / 255.0) - 1
    # list of 2D images to 1D pixel intensities
    x = x.flatten(1, 2)
    y = trainSet.targets

    # Shuffle
    r = torch.randperm(x.size(0))
    xTrain = x
    yTrain = y

    # Scale pixel intensities to [-1, 1]
    xTest = testSet.data.clone().detach()
    xTest = 2 * (xTest.float() / 255.0) - 1
    # list of 2D images to 1D pixel intensities
    xTest = xTest.flatten(1, 2)
    yTest = testSet.targets.clone().detach()

    return xTrain, yTrain, xTest, yTest


def __filterByLabelAndShuffle(labels, xTrn, xTst, yTrn, yTst):
    xTrain = torch.tensor([])
    xTest = torch.tensor([])
    yTrain = torch.tensor([], dtype=torch.long)
    yTest = torch.tensor([], dtype=torch.long)
    # Extract the entries corresponding to the labels passed as param
    for e in labels:
        idx = (yTrn == e)
        xTrain = torch.cat((xTrain, xTrn[idx, :]), dim=0)
        yTrain = torch.cat((yTrain, yTrn[idx]), dim=0)

        idx = (yTst == e)
        xTest = torch.cat((xTest, xTst[idx, :]), dim=0)
        yTest = torch.cat((yTest, yTst[idx]), dim=0)
    # Shuffle
    r = torch.randperm(xTrain.size(0))
    xTrain = xTrain[r, :]
    yTrain = yTrain[r]
    return xTest, xTrain, yTest, yTrain


# Obsolete - from Luiz original codebase
def getMNISTdata(perc_users, labels):
    perc_users = perc_users / perc_users.sum()

    userNo = perc_users.size(0)

    trans = transforms.Compose([transforms.ToTensor(),
                                transforms.Normalize((0.5,), (1.0,))])

    # if not exist, download mnist dataset
    train_set = dset.MNIST('data', train=True, transform=trans, download=True)
    test_set = dset.MNIST('data', train=False, transform=trans, download=True)

    # Scale pixel intensities to [-1, 1]
    x = train_set.data
    x = 2 * (x.float() / 255.0) - 1
    # list of 2D images to 1D pixel intensities
    x = x.flatten(1, 2)
    y = train_set.targets

    ytr = torch.tensor([], dtype=torch.long)
    xtr = torch.tensor([])

    # Extract the entries corresponding to the labels passed as param
    for e in labels:
        idx = (y == e)
        xtr = torch.cat((xtr, x[idx, :]), dim=0)
        ytr = torch.cat((ytr, y[idx]), dim=0)

    ntr = xtr.size(0)

    # Shuffle
    r = torch.randperm(xtr.size(0))
    xtr = xtr[r, :]
    ytr = ytr[r]

    # Splitting data to users corresponding to user percentage param
    ntr_users = (perc_users * ntr).floor()
    ntr_users = ntr_users.numpy()

    training_data = []
    training_labels = []

    it = 0
    for i in range(userNo):
        x = xtr[it:it + int(ntr_users[i]), :].clone().detach()
        y = ytr[it:it + int(ntr_users[i])].clone().detach()
        training_data.append(x)
        training_labels.append(y)
        it = it + int(ntr_users[i])

    x2 = test_set.data.clone().detach()
    x2 = 2 * (x2.float() / 255.0) - 1
    x2 = x2.flatten(1, 2)
    y2 = test_set.targets.clone().detach()

    ytst = torch.tensor([], dtype=torch.long)
    xtst = torch.tensor([])

    for e in labels:
        idx = (y2 == e)
        xtst = torch.cat((xtst, x2[idx, :]), dim=0)
        ytst = torch.cat((ytst, y2[idx]), dim=0)

    return training_data, training_labels, xtst, ytst
