import numpy as np
import torch
import torch.nn as nn
# import torch.nn.functional as F
from torch import optim

# from matplotlib import pyplot as plt


class TrainingModel(nn.Module):
    def __init__(self):
        super().__init__()

        self.a = nn.Parameter(torch.randn(1, requires_grad=True))
        self.b = nn.Parameter(torch.randn(1, requires_grad=True))

    def forward(self, x):
        y = self.a + self.b * x
        return y


if __name__ == "__main__":
    lr = .1
    epochs = 500
    max_data_amount = 1000
    training_amount_ratio = 0.8

    training_amount = int(max_data_amount * training_amount_ratio)
    np.random.seed(7)
    torch.manual_seed(7)
    x = np.random.rand(max_data_amount, 1)

    y = 2 + 5 * x + .2 * np.random.randn(max_data_amount, 1)

    idx = np.arange(max_data_amount)
    np.random.shuffle(idx)

    train_idx = idx[:training_amount]
    val_idx = idx[training_amount:]
    x_train, y_train = x[train_idx], y[train_idx]
    x_val, y_val = x[val_idx], y[val_idx]

    x_train_tensor = torch.from_numpy(x_train)
    y_train_tensor = torch.from_numpy(y_train)
    print(type(x_train_tensor), type(y_train_tensor))

    model = TrainingModel()

    print(model.state_dict())

    optimizer = optim.SGD(model.parameters(), lr=lr)
    MSELoss = nn.MSELoss(reduction="mean")
    for epoch in range(epochs):
        model.train()
        yhat = model(x_train_tensor)
        loss = MSELoss(y_train_tensor, yhat)
        loss.backward()
        optimizer.step()
        optimizer.zero_grad()

    print(model.state_dict())
