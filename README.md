# Multi-Comp-Distillation-KKT-hPINN
Code that finds the optimal distillation column parameters to seperate a feed mixture into specified products. Workflow of code is to first simulate the datapoints in "Simulating Data", use the datapoints to train the neural network in "Training NN", then use the neural network to run the formulation in "Solving Formulation", and finally compare the formulation outputs with the simulated data in "Validating".

Requirements to run this code are: Aspen Plus, and the python packages Pyomo, OMLT, ONNX, Pytorch, and Keras.
