import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler, StandardScaler
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils import data
from models import NN, NNOPT,NNRelu

#device = "cuda" if torch.cuda.is_available() else "cpu"
device = "cpu"

def LoadData(args):
    if args.dataset_type == 'cstr':
        dataset_arr, scaler = load_data(args.dataset_path)
        Data_class = Data_cstr
    elif args.dataset_type == 'plant':
        dataset_arr, scaler = load_data(args.dataset_path)
        Data_class = Data_plant
    elif args.dataset_type == 'distillation':
        dataset_arr, scaler = load_data(args.dataset_path,args.model)
        Data_class = Nonsharp_Dist
    else:
        raise ValueError('Dataset not supported!')

    dataset = Data_class(dataset_arr)
    dataset.resplit_data(args.val_ratio)

    A, B, b = get_scaledABb(dataset.A, dataset.B, dataset.b, scaler,args.model)
    print(f'type of A: {A.dtype}, type of B: {B.dtype}, type of b: {b.dtype}')

    params = {'batch_size': args.batch_size,
              'shuffle': True}
    train_loader = data.DataLoader(dataset.train_set, **params)
    val_loader = data.DataLoader(dataset.val_set, **params)
    test_loader = data.DataLoader(dataset.test_set, **params)

    print(f'train set size: {len(dataset.train_set)}, val set size: {len(dataset.val_set)}, test set size: {len(dataset.test_set)}')

    data_dict = {'train_loader': train_loader, 'val_loader': val_loader, 'test_loader': test_loader,
                 'dataset': dataset, 'A': A, 'B': B, 'b': b.unsqueeze(1),
                 'constrained_indexes': dataset.constrained_indexes,
                 'unconstrained_indexes': dataset.unconstrained_indexes,}
    print(data_dict)
    return data_dict


def LoadModel(args, data):

    if args.model == 'NN' or args.model == 'AugLagNN':
        model = NN(args.input_dim, args.hidden_dim, args.hidden_num, args.z0_dim)
    elif args.model == 'PINN':
        model = NN(args.input_dim, args.hidden_dim, args.hidden_num, args.z0_dim)
    elif args.model == 'KKThPINN' or args.model=='KKThPINN_RELU':
        model = NNOPT(args.input_dim, args.hidden_dim, args.hidden_num, args.z0_dim,
                      data['A'], data['B'], data['b'])
    elif args.model == 'NNRelu':
        model = NNRelu(args.input_dim, args.hidden_dim, args.hidden_num, args.z0_dim)
    model = model.double().to(device)
    return model


def get_optimizer(args, model):
    if args.optimizer == 'adam':
        optimizer = optim.Adam(model.parameters(), lr=args.lr)
    elif args.optimizer == 'SGD':
        optimizer = optim.SGD(model.parameters(), lr=args.lr)
    else:
        raise ValueError('Invalid optimizer')
    return optimizer


def get_loss_func(args, data):
    if args.loss_type == 'MSE':
        loss_func = nn.MSELoss()
    elif args.loss_type == 'PINN':
        loss_func = PINNLoss(data['A'], data['B'], data['b'], args.mu)
    elif args.loss_type == 'ALM':
        loss_func = ALMLoss(data['A'], data['B'], data['b'])
        print('ALM loss function is used!')
    else:
        raise ValueError('Loss function not supported!')
    return loss_func


def load_data(dataset_path,model):
    dataset = np.array(pd.read_csv(dataset_path).values)
    if model == 'KKThPINN_RELU':
        scaler = MinMaxScaler()
    else:
        scaler = StandardScaler()
    scaler.fit(dataset)
    dataset = scaler.transform(dataset)
    return dataset, scaler


def get_ScaleAndMean(scaler, x_dim, z_dim, model):
    if model == 'KKThPINN_RELU':
        xscale = []
        zscale = []
        
        for idx in range(x_dim):
            xscale.append(scaler.data_range_[idx])
        for idx in range(z_dim):
            zscale.append((scaler.data_range_[idx+x_dim]))
    else:
        xscale = []
        zscale = []
        print('x_dim is ')
        print(x_dim)
        print(z_dim)
        for idx in range(x_dim):
            xscale.append(scaler.scale_[idx])
        for idx in range(z_dim):
            zscale.append((scaler.scale_[idx+x_dim]))
    return xscale, zscale


def get_scaledABb(A, B, b, scaler,model):
    x_dim = A.shape[1]
    z_dim = B.shape[1]
    xscale, zscale = get_ScaleAndMean(scaler, x_dim, z_dim,model)
    xscale, zscale = torch.tensor(xscale), torch.tensor(zscale)
    A_scale = torch.ones_like(A) * xscale
    B_scale = torch.ones_like(B) * zscale
    A_scaled = A * A_scale
    B_scaled = B * B_scale
    b_scaled = b
    return A_scaled, B_scaled, b_scaled


class Data_cstr(data.Dataset):
    def __init__(self, dataset):
        self.dataset_tensor = torch.from_numpy(dataset).double()
        self.X = self.dataset_tensor[:, :3]
        self.Y = self.dataset_tensor[:, 3:]
        self.train_set, self.val_set, self.test_set = self.split_data(0.2)  # initial val_ratio -> 0.2

        self.A = torch.tensor([[0, 1, -1],
                                [0, 1, 0]]).double()  # (2, 3)
        self.B = torch.tensor([[0, -1, 1],
                                [-1, -1, 0]]).double()  # (2, 3)
        self.b = torch.tensor([0, 0]).double()

        self.constrained_indexes = list(set([index for index in torch.nonzero(self.B)[:, -1].tolist()]))
        self.unconstrained_indexes = [item for item in range(self.B.shape[1]) if item not in self.constrained_indexes]

    def __len__(self):
        return len(self.dataset_tensor)

    def __getitem__(self, idx):
        return self.dataset_tensor[idx, :]

    def split_data(self, val_ratio, test_ratio=0.2):
        XY = data.TensorDataset(self.X, self.Y)
        n_samples = len(XY)
        n_val = int(val_ratio * n_samples)
        n_test = int(test_ratio * n_samples)
        n_train = n_samples - n_val - n_test
        train_set = data.Subset(XY, range(0, n_train))
        val_set = data.Subset(XY, range(n_train, n_train + n_val))
        test_set = data.Subset(XY, range(n_train + n_val, n_samples))
        return train_set, val_set, test_set

    def resplit_data(self, val_ratio, test_ratio=0.2):
        self.train_set, self.val_set, self.test_set = self.split_data(val_ratio, test_ratio)


class Data_plant(data.Dataset):
    def __init__(self, dataset):
        self.dataset_tensor = torch.from_numpy(dataset).double()
        self.X = self.dataset_tensor[:, :4]
        self.Y = self.dataset_tensor[:, 4:]
        self.train_set, self.val_set, self.test_set = self.split_data(0.2)  # initial val_ratio -> 0.2

        self.A = torch.tensor([[1, 1, 1, -1]]).double()  # (1, 4)
        self.B = torch.tensor([[-1, 0, -1, 0, -1]]).double()  # (1, 5)
        self.b = torch.tensor([0]).double()  # (1, )

        self.constrained_indexes = list(set([index for index in torch.nonzero(self.B)[:, -1].tolist()]))
        self.unconstrained_indexes = [item for item in range(self.B.shape[1]) if item not in self.constrained_indexes]

    def __len__(self):
        return len(self.dataset_tensor)

    def __getitem__(self, idx):
        return self.dataset_tensor[idx, :]

    def split_data(self, val_ratio, test_ratio=0.2):
        XY = data.TensorDataset(self.X, self.Y)
        n_samples = len(XY)
        n_val = int(val_ratio * n_samples)
        n_test = int(test_ratio * n_samples)
        n_train = n_samples - n_val - n_test
        train_set = data.Subset(XY, range(0, n_train))
        val_set = data.Subset(XY, range(n_train, n_train + n_val))
        test_set = data.Subset(XY, range(n_train + n_val, n_samples))
        return train_set, val_set, test_set

    def resplit_data(self, val_ratio, test_ratio=0.2):
        self.train_set, self.val_set, self.test_set = self.split_data(val_ratio, test_ratio)


class Data_distillation(data.Dataset):
    def __init__(self, dataset):
        self.dataset_tensor = torch.from_numpy(dataset).double()
        self.X = self.dataset_tensor[:, :5]
        self.Y = self.dataset_tensor[:, 5:]
        self.train_set, self.val_set, self.test_set = self.split_data(0.2)  # initial val_ratio -> 0.2

        self.A = torch.tensor([[0, 0, 1, 0, 0],
                                [0, 0, 0, 0, 1]]).double()  # (2, 5)
        self.B = torch.tensor([[-1, 0, 0, 0, 0, 0, -1, -1, 0, 0],
                                [0, -1, 0, 0, 0, 0, 0, 0, -1, -1]]).double()  # (2, 10)
        self.b = torch.tensor([0, 0]).double()  # (2, )

        self.constrained_indexes = list(set([index for index in torch.nonzero(self.B)[:, -1].tolist()]))
        self.unconstrained_indexes = [item for item in range(self.B.shape[1]) if item not in self.constrained_indexes]

    def __len__(self):
        return len(self.dataset_tensor)

    def __getitem__(self, idx):
        return self.dataset_tensor[idx, :]

    def split_data(self, val_ratio, test_ratio=0.2):
        XY = data.TensorDataset(self.X, self.Y)
        n_samples = len(XY)
        n_val = int(val_ratio * n_samples)
        n_test = int(test_ratio * n_samples)
        n_train = n_samples - n_val - n_test
        train_set = data.Subset(XY, range(0, n_train))
        val_set = data.Subset(XY, range(n_train, n_train + n_val))
        test_set = data.Subset(XY, range(n_train + n_val, n_samples))
        return train_set, val_set, test_set

    def resplit_data(self, val_ratio, test_ratio=0.2):
        self.train_set, self.val_set, self.test_set = self.split_data(val_ratio, test_ratio)
        
class Nonsharp_Dist(data.Dataset):
    def __init__(self, dataset):
        self.dataset_tensor = torch.from_numpy(dataset).double()
        self.X = self.dataset_tensor[:, 0:5]
        self.Y = self.dataset_tensor[:, 5:]
        self.train_set, self.val_set, self.test_set = self.split_data(0.1,test_ratio=0.2)  # initial val_ratio -> 0.1, test_ratio 0.3

        self.A = torch.tensor([[1, 0, 0, 0, 0,],
                                [0, 1, 0, 0, 0],
                              [0 , 0, 1, 0, 0]]).double()  
        self.B = torch.tensor([[-1, 0, 0, -1, 0, 0, 0, 0,],
                                [0, -1, 0, 0, -1, 0, 0, 0],
                              [0, 0, -1, 0, 0, -1, 0, 0]]).double()  
        self.b = torch.tensor([0, 0,0]).double()  

        self.constrained_indexes = list(set([index for index in torch.nonzero(self.B)[:, -1].tolist()]))
        self.unconstrained_indexes = [item for item in range(self.B.shape[1]) if item not in self.constrained_indexes]

    def __len__(self):
        return len(self.dataset_tensor)

    def __getitem__(self, idx):
        return self.dataset_tensor[idx, :]

    def split_data(self, val_ratio, test_ratio=0.2):
        XY = data.TensorDataset(self.X, self.Y)
        n_samples = len(XY)
        n_val = int(val_ratio * n_samples)
        n_test = int(test_ratio * n_samples)
        print('n_test is ')
        print(n_test)
        n_train = n_samples - n_val - n_test
        train_set = data.Subset(XY, range(0, n_train))
        val_set = data.Subset(XY, range(n_train, n_train + n_val))
        test_set = data.Subset(XY, range(n_train + n_val, n_samples))
        print(test_set)
        return train_set, val_set, test_set

    def resplit_data(self, val_ratio, test_ratio=0.2):
        self.train_set, self.val_set, self.test_set = self.split_data(val_ratio, test_ratio)


class PINNLoss(nn.Module):
    def __init__(self, A, B, b, mu, reduction='mean'):
        super(PINNLoss, self).__init__()
        self.A = A
        self.B = B
        self.b = b
        self.mu = mu
        self.reduction = reduction

    def forward(self, X, pred, target):
        mse_loss = F.mse_loss(pred, target, reduction=self.reduction)
        pinn_loss = torch.mean(self.mu * (torch.mm(self.B, pred.T) + torch.mm(self.A, X.T) - self.b.unsqueeze(1))**2)
        return mse_loss, pinn_loss


class ALMLoss(nn.Module):
    def __init__(self, A, B, b, reduction='mean'):
        super(ALMLoss, self).__init__()
        self.A = A
        self.B = B
        self.b = b
        self.reduction = reduction

    def forward(self, X, pred, target, lambda_k, mu_k):
        mse_loss = F.mse_loss(pred, target, reduction=self.reduction)
        c = torch.mm(self.A, X.T) + torch.mm(self.B, pred.T) - self.b.repeat(1, X.T.shape[1])
        lambda_c = torch.mm(lambda_k.unsqueeze(0), c).mean()
        mu_c = mu_k / 2 * c.pow(2).mean()
        return mse_loss, lambda_c + mu_c


def get_violation(args, data, X, pred):
    violation = torch.mm(data['A'], X.T) + torch.mm(data['B'], pred.T) - data['b'].repeat(1, X.T.shape[1])
    return violation
