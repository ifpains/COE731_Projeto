import pandas as pd
import numpy as np
import pysindy as ps
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from scipy.optimize import curve_fit
from pysindy.feature_library import CustomLibrary
import scipy.signal
import pysindy as ps

## Quarta tentativa de Modelo (USANDO CUSTOM LIB):
# Estados:
# Fluxo de Vapor - x1
# Nível medido - x2
# Saída y = x2 + E * (x1 - u)
# Entrada de Controle u = fluxo de água de alimentação - Vetor de entrada de medidas

## Equação:
#(x1)' = 4207755272.506 1 + 539.554 x1 + -1079175153.059 x2 + -546.931 u + -0.151 x1^2 + -43.356 x1 x2 + 0.293 x1 u + 90916427.935 x2^2 + 43.997 x2 u + -0.142 u^2 + 
# -2517477.568 f0(x2) + -3.115 f1(x1) + -13198648.474 f1(x2) + 3.594 f1(u) + 0.266 f2(x1) + -7702397.829 f2(x2) + -2.904 f2(u)
#(x2)' = 4.792 x1 + -50426.098 x2 + -4.701 u + -0.391 x1 x2 + 8319.331 x2^2 + 0.384 x2 u + -338.561 f0(x2) + 1667.459 f1(x2) + 0.066 f2(x1) + -8223.899 f2(x2)
# y = x2 + E * (x1 - u)

dt = 0.01

def load_data(path):
    df = pd.read_csv(path)

    return df

def filter(x):
    b, a = scipy.signal.butter(3, 0.1)
    filtered = scipy.signal.filtfilt(b, a, x)

    return filtered

def data_conditioning(df, filtered):    
    df.drop(df[df["LBA10CF901"] <= 0.].index, inplace=True)
    df.drop(df[df["JEA10CL901"] <= 0.].index, inplace=True)
    df.drop(df[df["LAB60CF901"] <= 0.].index, inplace=True)
    df.drop(df[df["LAB60CF001A"] <= 0.].index, inplace=True)

    n = len(df["Data_Hora"])
    t = np.linspace(0, n*dt, num=n)
    df["Data_Hora"] = t

    df.rename({"Data_Hora":"t", "LBA10CF901":"x1", "JEA10CL901":"x2", "LAB60CF001A":"u", "LAB60CF901":"u_corr"}, axis='columns', inplace=True)

    flt = pd.DataFrame(columns=['x1','x2','u'])
    if filtered:        
        flt["t"] = t
        flt["x1"] = filter(df["x1"])
        flt["x2"] = filter(df["x2"])
        flt["u"] = filter(df["u"])
        flt["u_corr"] = filter(df["u_corr"])

        return df, flt
    
    return df, df

def states(tmin, tmax, filtered):
    df = load_data('data_gv10.csv')
    K_temp = -0.0006 # 1/ºC
    K_shift = 1.1381
    x = [0,	2,	4,	6,	8,	10,	13,	16,	22,	30,	41,	55,	70,	80,	90,	100]
    y = [0.129,	0.216,	0.267,	0.321,	0.362,	0.398,	0.447,	0.491,	0.569,	0.661,	0.771,	0.897,	1.0,	1.1,	1.16,	1.257]

    temp_corr01 = df['LAB60CF001A']*np.clip((K_temp*df['LAB60CT002'] + K_shift),0.998, 1.043) 
    temp_corr02 = df['LAB60CF001A']*np.clip((K_temp*df['LAB60CT003'] + K_shift),0.998, 1.043)

    df['LAB60CF901'] = (temp_corr01 + temp_corr02)/2.0
    df.drop(df[df["LAB60CF901"] == 0.].index, inplace=True)

    K_pressure =  np.polyfit(x,y,4)
    press_corr01 = np.polyval(K_pressure,  df['LBA10CP001'])*df['LBA10CF001A']
    press_corr02 = np.polyval(K_pressure,  df['LBA10CP951A'])*df['LBA10CF001B']

    df['LBA10CF901'] = (press_corr01 + press_corr02)/2.0

    X, flt = data_conditioning(df, filtered)

    return  X.loc[tmin:tmax, ["t", "x1", "x2", "u", "u_corr"]], flt.loc[tmin:tmax, ["t", "x1", "x2", "u", "u_corr"]]

def u_fit(df):
    def func(x, a, b, c, d, e, f, g, h, i, j):
        return a*x**9 + b*x**8 + c*x**7 + d*x**6 + e*x**5 + f*x**4 + g*x**3 + h*x**2 + i*x + j

    popt, _ = curve_fit(func, df["t"], df["u"])
    print(popt)
    plt.plot(df["t"], df["u"], 'b-', label='data')   
    plt.plot(df["t"], func(df["t"], *popt), 'g--')
    plt.show()    

def u_fun(t):
    return 7.45409110e-07*t**9 - 1.55942700e-04*t**8 + 1.08221950e-02*t**7 - 1.82047991e-05*t**6 - 4.49095364e+01*t**5 + 3.06799073e+03*t**4 - 1.04204413e+05*t**3 + 2.01072271e+06*t**2 - 2.10917709e+07*t + 9.38253864e+07

def identify_model(df):
    x_train, x_test = train_test_split(df, train_size=0.8, shuffle=False)

    # Entrada: Dados de Teste e Treinamento
    u_train = x_train.loc[:,["u"]].to_numpy()
    u_test = x_test.loc[:,["u"]].to_numpy()

    # Tempo: Treinamento e Teste
    t_train = x_train.loc[:, "t"].to_numpy()
    t_test = x_test.loc[:, "t"].to_numpy()

    # Estados: Dados de Treinamento e Teste
    x_train = x_train.loc[:,["x1", "x2"]].to_numpy()
    x_test = x_test.loc[:,["x1", "x2"]].to_numpy()

    ## CROSS-VLIDATION
    model = ps.SINDy(t_default=0.01, feature_names = ['x1', 'x2', 'u'])

    param_grid = {
        "optimizer":[ps.SR3()],
        "optimizer__threshold":[0.1],
        "optimizer__thresholder":["L1"],
        "feature_library":[ps.PolynomialLibrary()],
        "feature_library__degree":[3]
    }

    search = GridSearchCV(
        model,
        param_grid,
        cv=TimeSeriesSplit(n_splits=5),
    )

    fit_params = {"t":t_train, "u":u_train, "unbias":True}

    search.fit(x_train, **fit_params)
    print("Best parameters:", search.best_params_)
    search.best_estimator_.print()

    x0_test= x_test[0,:]
    x_model = search.best_estimator_.simulate(x0=x0_test, t=t_test, u=u_test)
    x0_train= x_train[0,:]
    x_model_train = search.best_estimator_.simulate(x0=x0_train, t=t_train, u=u_train)

    print("Predict x1: " + str(r2_score(x_test[:-1,0], x_model[:, 0])) + "\n")
    print("Predict x2: " + str(r2_score(x_test[:-1,1], x_model[:, 1])) + "\n")

    print("Trained x1: " + str(r2_score(x_train[:-1,0], x_model_train[:, 0])) + "\n")
    print("Trained x2: " + str(r2_score(x_train[:-1,1], x_model_train[:, 1])) + "\n")

    _, ax = plt.subplots(3, 1, figsize=(10,10))
    ax[0].plot(t_train[:-1], x_model_train[:, 0], label="trained Model", linestyle='dashed',linewidth=2.0)
    ax[0].plot(t_train, x_train[:, 0], label="train signal", linewidth=.5)
    ax[0].plot(t_test[:-1], x_model[:, 0], label="tested Model", color="black", linestyle='dashed',linewidth=2.0)
    ax[0].plot(t_test, x_test[:,0], label="test signal", linewidth=.5)
    ax[0].legend()

    ax[1].plot(t_train[:-1], x_model_train[:, 1], label="trained Model", linestyle='dashed',linewidth=2.0)
    ax[1].plot(t_train, x_train[:, 1], label="train signal", linewidth=.5)
    ax[1].plot(t_test[:-1], x_model[:, 1], label="tested Model", color="black", linestyle='dashed',linewidth=2.0)
    ax[1].plot(t_test, x_test[:,1], label="test signal", linewidth=.5)
    ax[1].legend()

    ax[2].plot(df.loc[:, "t"], df.loc[:, "u"], label="u", linestyle='dashed',linewidth=2.0)
    ax[2].legend()

    plt.show()

def graphics(states):
    _, ax = plt.subplots(4, 1, figsize=(10,10))
    
    ax[0].plot(states['x1'], label='LBA10CF901 - X1')
    ax[0].legend(loc='upper right')
    ax[0].grid(True)
    
    ax[1].plot(states['x2'], label='JEA10CL901 - X2')
    #ax[1].plot(np.arange(2800, 3901) ,12.2*np.ones(len(states['x2'])), label='Setpoint')
    ax[1].legend(loc='upper right')
    ax[1].grid(True)

    ax[2].plot(states['u'], label='LAB60CF001A - U Flux')
    ax[2].grid(True)
    ax[2].legend(loc='upper right')

    ax[3].plot(states['u_corr'], label='LAB60CF901 - U Corrected')
    ax[3].legend(loc='upper right')
    ax[3].grid(True)

    plt.show()   

X = states(2935, 3000)
#graphics(X)
#u_fit(X)
identify_model(X)




