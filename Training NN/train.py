import csv
import numpy as np
import torch
import torch.optim as optim
import torch.nn as nn
import torch.onnx
from utils import LoadModel, get_optimizer, get_loss_func, get_violation, PINNLoss, ALMLoss
import copy
from omlt.io.onnx import write_onnx_model_with_bounds

#device = "cuda" if torch.cuda.is_available() else "cpu"
device = "cpu"

def run_training(args, data):
    model = LoadModel(args, data)
    optimizer = get_optimizer(args, model)
    loss_func = get_loss_func(args, data)

    print('Start Training...')
    min_loss = np.inf
    train_losses = []
    val_losses = []
    train_violations = []
    val_violations = []

    lambda_k = torch.zeros(data['A'].shape[0], requires_grad=False).double().to(device)
    c_best = torch.tensor(np.inf)

    for epoch in range(args.epochs):
        #print('-------- Epoch ' + str(epoch + 1) + ' --------')
        train_loss = 0
        train_violation = 0

        if args.model == 'AugLagNN':
            loss_func = ALMLoss(data['A'], data['B'], data['b'])
            for batch_idx, (X, Y) in enumerate(data['train_loader']):
                mu_k = (batch_idx + 1) * args.mu
                X, Y = X.to(device), Y.to(device)
                mse_loss = optimizer_step(model, optimizer, loss_func, X, Y, args, data, lambda_k, mu_k)
                pred_diff = conservation_step(model, X, data, args)
                # update
                with torch.no_grad():
                    if torch.norm(pred_diff) <= args.eta * torch.norm(c_best):
                        lambda_k = (lambda_k + mu_k * pred_diff.mean(dim=-1))
                        c_best = pred_diff
                        mu_k = mu_k
                    else:
                        lambda_k = lambda_k
                        mu_k = min(args.sigma * mu_k, args.mu_safe)
                train_loss += mse_loss
                train_violation += torch.abs(pred_diff.view(-1)).mean()

        else:
            for batch_idx, (X, Y) in enumerate(data['train_loader']):
                X, Y = X.to(device), Y.to(device)
                mse_loss = optimizer_step(model, optimizer, loss_func, X, Y, args, data)
                pred_diff = conservation_step(model, X, data, args)
                train_loss += mse_loss
                train_violation += torch.abs(pred_diff.view(-1)).mean()

        train_loss /= len(data['train_loader'].dataset)
        train_violation /= len(data['train_loader'].dataset)

        val_loss, val_violation = test(model, data, args)
        train_losses.append(train_loss), train_violations.append(train_violation.detach().item())
        val_losses.append(val_loss), val_violations.append(val_violation.detach().item())

        checkpoint(model, val_loss, min_loss, args, epoch)
        best = np.minimum(min_loss, np.mean(val_loss))

        if (epoch + 1) % 50 == 0:
            print('epoch: {:05d}'.format(epoch + 1),
                  'loss_train: {:.5f}'.format(train_loss),
                  'loss_val: {:.5f}'.format(val_loss),
                  'violation_train: {:.5f}'.format(train_violation),
                  'violation_val: {:.5f}'.format(val_violation))
    print("Finished!")
    scores = evaluate_model(data, args)
    #save_history(args, train_losses, val_losses, train_violations, val_violations)
    file_path = '{}_dist {}-{}.onnx'.format(args.model,args.hidden_dim,args.epochs)
    checkpoint(model, val_loss, min_loss, args, epoch)
    _create_onnx_model(data,args,model,file_path)
    if args.job == 'experiment':
        scores = evaluate_model(data, args)


def optimizer_step(model, optimizer, loss_func, X, Y, args, data, lambda_k=None, mu_k=None):
    if isinstance(loss_func, PINNLoss):
        model.train()
        optimizer.zero_grad()
        pred = model(X)
        mse_loss, pinn_loss = loss_func(X, pred, Y)
        loss = mse_loss + pinn_loss
        loss.backward()
        optimizer.step()
        return mse_loss.item()
    elif isinstance(loss_func, nn.MSELoss):
        model.train()
        optimizer.zero_grad()
        pred = model(X)
        loss = loss_func(pred, Y)
        loss.backward()
        optimizer.step()
        return loss.item()
    elif isinstance(loss_func, ALMLoss):
        for sub_iteration in range(args.max_subiter + 1):
            model.train()
            optimizer.zero_grad()
            pred = model(X)
            mse_loss, penalty_loss = loss_func(X, pred, Y, lambda_k, mu_k)
            loss = mse_loss + penalty_loss
            loss.backward()
            optimizer.step()
        return mse_loss.item()


def conservation_step(model, X, data, args):
    model.eval()
    pred = model(X)
    pred_diff = get_violation(args, data, X, pred)
    return pred_diff


def test(model, data, args):
    loss_func = get_loss_func(args, data)
    model.eval()
    test_loss = 0
    test_violation = 0

    with torch.no_grad():
        for batch_idx, (X, Y) in enumerate(data['val_loader']):
            X, Y = X.to(device), Y.to(device)
            pred = model(X)
            pred_diff = get_violation(args, data, X, pred)
            if args.loss_type == 'PINN':
                mse_loss, pinn_loss = loss_func(X, pred, Y)
                loss = mse_loss + pinn_loss
                test_loss += mse_loss.item()
            elif args.loss_type == 'MSE':
                loss = loss_func(pred, Y)
                test_loss += loss.item()
            test_violation += torch.abs(pred_diff.view(-1)).mean()
    test_loss /= len(data['val_loader'].dataset)  # Test set Average loss
    test_violation /= len(data['val_loader'].dataset)  # Test set Average violation
    return test_loss, test_violation


def checkpoint(model, val_loss, min_loss, args, epoch):
    if np.mean(val_loss) < min_loss:
        checkpoint = {'model': model, 'state_dict': model.state_dict()}
        torch.save(checkpoint, f'C:\\Users\\Razzy\\Multi-Comp-Distillation-KKT-hPINN-main\\Training NN\\{args.model}_{args.dataset_type}_{args.val_ratio}_{args.run}.pth')


def create_report(scores, args):
    args_dict = args_to_dict(args)
    # combine scores and args dict
    args_scores_dict = args_dict | scores
    # save dict
    save_dict(args_scores_dict, args)


def evaluate_model(data, args):
    rmse_total = 0
    rmse_unconstrained = 0
    rmse_constrained = 0
    violation = 0
    loss_func = nn.MSELoss()

    model = LoadModel(args, data)
    load_weights(model, args.model_id, args)
    model.eval()

    with torch.no_grad():
        for batch_idx, (X, Y) in enumerate(data['test_loader']):
            X, Y = X.to(device), Y.to(device)
            pred = model(X)
            pred_diff = get_violation(args, data, X, pred)
            loss = loss_func(pred, Y)

            constrained_loss = torch.tensor(0)
            unconstrained_loss = torch.tensor(0)
            constrained_index = data['constrained_indexes']
            unconstrained_index = data['unconstrained_indexes']
            
            #assuming data is set up as constrained data in first columns, the unconstrained data in last columns.
            constrained_loss = loss_func(pred[:,:3], Y[:,:3]) #replace 3 with unconstrained_index[0] for general case
            unconstrained_loss = loss_func(pred[:, unconstrained_index[0]:], Y[:, unconstrained_index[0]:])

            rmse_total += loss.item()
            rmse_unconstrained += unconstrained_loss.item()
            rmse_constrained += constrained_loss.item()
            violation += torch.abs(pred_diff.view(-1)).mean()

        rmse_total /= batch_idx
        rmse_total = np.sqrt(rmse_total)

        rmse_unconstrained /= batch_idx
        rmse_unconstrained = np.sqrt(rmse_unconstrained)

        rmse_constrained /= batch_idx
        rmse_constrained = np.sqrt(rmse_constrained)

        violation /= len(data['test_loader'].dataset)
        violation = violation.item()

    scores = {'rmse_total': rmse_total, 'rmse_unconstrained': rmse_unconstrained, 'rmse_constrained': rmse_constrained,
                'violation': violation}

    if args.model == 'NN':
        post_rmse_total = 0
        post_rmse_unconstrained = 0
        post_rmse_constrained = 0

        chunk = torch.mm(data['B'].t(),
                         torch.inverse(
                             torch.mm(data['B'], data['B'].t())
                         )
                         )
        Astar = - torch.mm(chunk, data['A'])
        Bstar = torch.eye(args.z0_dim).to(device) - torch.mm(chunk, data['B'])
        bstar = torch.matmul(chunk, data['b']).squeeze(-1)

        with torch.no_grad():
            for batch_idx, (X, Y) in enumerate(data['test_loader']):
                X, Y = X.to(device), Y.to(device)
                pred = model(X)
                e = torch.ones((X.shape[0], 1)).double().to(device)
                pred = torch.mm(X, Astar.T) + torch.mm(pred, Bstar.T) + torch.mm(e, bstar.unsqueeze(1).T)
                loss = loss_func(pred, Y)
                for constrained_index in data['constrained_indexes']:
                    constrained_loss = loss_func(pred[:, constrained_index], Y[:, constrained_index])
                for unconstrained_index in data['unconstrained_indexes']:
                    unconstrained_loss = loss_func(pred[:, unconstrained_index], Y[:, unconstrained_index])
                post_rmse_total += loss.item()
                post_rmse_unconstrained += unconstrained_loss.item()
                post_rmse_constrained += constrained_loss.item()

            post_rmse_total /= len(data['test_loader'].dataset)
            post_rmse_total = np.sqrt(post_rmse_total)
            scores.update({'post_rmse_total': post_rmse_total})

            post_rmse_unconstrained /= len(data['test_loader'].dataset)
            post_rmse_unconstrained = np.sqrt(post_rmse_unconstrained)
            scores.update({'post_rmse_unconstrained': post_rmse_unconstrained})

            post_rmse_constrained /= len(data['test_loader'].dataset)
            post_rmse_constrained = np.sqrt(post_rmse_constrained)
            scores.update({'post_rmse_constrained': post_rmse_constrained})

    print(scores)
    #create_report(scores, args)


def args_to_dict(args):
    return vars(args)


def save_dict(dictionary, args):
    w = csv.writer(open(f'C:\\Users\\RazzyZac\\Optimization 2024 Purdue REU\\KKT_hPINN/data/tables/{args.model_id}_{args.val_ratio}_{args.run}.csv', 'w'))
    # loop over dictionary keys and values
    for key, val in dictionary.items():
        # write every key and value to file
        w.writerow([key, val])


def load_weights(model, model_id, args):
    PATH = f'C:\\Users\\Razzy\\Multi-Comp-Distillation-KKT-hPINN-main\\Training NN\\{args.model}_{args.dataset_type}_{args.val_ratio}_{args.run}.pth'
    checkpoint = torch.load(PATH)
    model.load_state_dict(checkpoint['state_dict'])
    model.to(device)
    return model


def save_history(args, train_losses, val_losses, train_violations, val_violations):
    np.save(f'C:\\Users\\RazzyZac\\Optimization 2024 Purdue REU\\KKT_hPINN/data/learning_curves/{args.dataset_type}_{args.model}_{args.model_id}_train_losses_run{args.run}.npy', train_losses)
    np.save(f'C:\\Users\\RazzyZac\\Optimization 2024 Purdue REU\\KKT_hPINN/data/learning_curves/{args.dataset_type}_{args.model}_{args.model_id}_val_losses_run{args.run}.npy', val_losses)
    np.save(f'C:\\Users\\RazzyZac\\Optimization 2024 Purdue REU\\KKT_hPINN/data/learning_curves/{args.dataset_type}_{args.model}_{args.model_id}_train_violations_run{args.run}.npy', train_violations)
    np.save(f'C:\\Users\\RazzyZac\\Optimization 2024 Purdue REU\\KKT_hPINN\\data\\learning_curves/{args.dataset_type}_{args.model}_{args.model_id}_val_violations_run{args.run}.npy', val_violations)

def transfer_weights(original_model, modified_model):
    with torch.no_grad():
        for original_layer, modified_layer in zip(original_model.layers, modified_model.layers):
            if isinstance(original_layer, nn.Linear) and isinstance(modified_layer, nn.Linear):
                modified_layer.weight.copy_(original_layer.weight)
                modified_layer.bias.copy_(original_layer.bias)
                
                
def create_onnx_model(data,model,file_path,batch_size,z0_dim,input_dim):
    #(X,Y) = data['train_loader']
    min_data = torch.empty((0,input_dim)).to(device)
    max_data = torch.empty((0,input_dim)).to(device)
    for batch_idx, (X, Y) in enumerate(data['train_loader']):
        X, Y = X.to(device), Y.to(device)

        min_val, i = torch.min(X,0)
        min_val = min_val.unsqueeze(0)
        min_data = torch.cat((min_data,min_val),0)
        
        max_val, i = torch.max(X,0)
        max_val = max_val.unsqueeze(0)
        max_data = torch.cat((max_data,max_val),0)
    
    lb, i  = torch.min(min_data,0)
    lb = lb.numpy()
    ub, i  = torch.max(max_data,0)
    ub = ub.numpy()
    input_bounds = [(l, u) for l, u in zip(lb, ub)]
    
    # model input used for exporting
    x = torch.randn(batch_size, input_dim, requires_grad=True,dtype=torch.float64)
    torch.onnx.export(
        model,
        x,
        file_path,
        input_names=['input'],
        output_names=['output'],
        dynamic_axes={
            'input': {0: 'batch_size'},
            'output': {0: 'batch_size'}
        }
    )
    write_onnx_model_with_bounds(file_path, None, input_bounds)
    print(f"Wrote PyTorch Onnx model to {file_path}")
    
def _create_onnx_model(data,args,model,file_path):
    if model == 'KKThPINN_RELU':
        args.model = 'NNRelu'
        print('Saving RELU model')
    else:
        args.model='NN'
        print('Saving standard model')
    modified_model = LoadModel(args,data)
    transfer_weights(model,modified_model)
    create_onnx_model(data,modified_model,file_path,args.batch_size,args.z0_dim,args.input_dim)