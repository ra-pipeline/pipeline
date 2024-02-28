#!/usr/bin/env python
# coding: utf-8

from copy import copy
import numpy as np

gm_param = 4
loop_best = 20 # 8 8st # 8 3

class GM:
    """
    A class to invoke M-estimation of baseline where self.model and self.metric are provided.

    Methods:
        fit: estimates self.model of baseline by Newton-Raphson method for minimizing self.metric.
        predict: provides a y value of the estimated baseline at a given point. .
    """
    def __init__(self, t=1, g=4, y_list=[], model=None, metric=None, fdt=None, sdt=None):
        """
        Method __init__
        """
        self.t = t
        self.g = g
        self.y_list = y_list
        self.model = model      # `model`: class implementing `fit` and `predict`
        self.metric = metric    # `metric`: Geman-McClure error, function of `y_true` and `y_pred` and returns a float
        self.fdt = fdt          # 'fdt': first derivative of 'metric'
        self.sdt = sdt          # 'sdt': second derivative of 'metric'
        self.best_model = None
        
    def fit(self, X, y, w):
        gm_param = self.g
        par1 = self.t / gm_param
        
        all_ids = np.arange(X.shape[0])
        ones = np.ones((len(all_ids), 1))
        kmax = len(self.y_list)
        print('kmax,y_list',kmax,self.y_list.T)

        initial_model = copy(self.model).fit0(X[0], self.y_list[0], ones[0])
        this_error = self.metric(y[all_ids], initial_model.predict(X[all_ids]), par1) 
        this_fdt = self.fdt(y[all_ids], initial_model.predict(X[all_ids]), par1) 
        this_sdt = self.sdt(y[all_ids], initial_model.predict(X[all_ids]), par1)  
        
        self.best_error = this_error
        self.best_model = initial_model
        next_model = copy(initial_model)
        print('initial_model',0,self.best_model.params,this_error)
        for ii in range(loop_best):  # Improvement by Newton-Raphson
            param0 = self.best_model.params
            next_model.params = param0 - this_fdt/this_sdt       ## Newton-Raphson 
            next_error = self.metric(y[all_ids], next_model.predict(X[all_ids]), par1)    ## Rnaga: GM-version 
            if next_error < this_error:
                this_error = next_error
                this_fdt = self.fdt(y[all_ids], next_model.predict(X[all_ids]), par1)    ## Rnaga: Newton-Raphson  
                this_sdt = self.sdt(y[all_ids], next_model.predict(X[all_ids]), par1)    ## Rnaga: Newton-Raphson
                self.best_model.params = next_model.params
                if (ii % 5 == 4):
                    print('updated_model',ii+1,self.best_model.params,this_error)
            else:
                break
        print('Newton-Raphson',ii,this_error,vars(self.best_model))
        if self.best_model != None:
            print('*:',self.best_model.params,self.best_model.params/self.t)
        return self

    def predict(self, X):
        return self.best_model.predict(X)

def gm_error_loss(y_true, y_pred, c):            ## Rnaga: GM-version
    """
    A function to calculate Geman-McClure error for Newton-Raphson.

    Args:
        y_true: list of true y values
        y_pred: list of predicted y values
        c: Geman-McClure arameter
    Returns:
        list of Geman-McClure errors.

"""
    ey = y_true - y_pred
    sqe = ey ** 2
    sqc = c * c
    sqec = sqe + sqc
    gme = sqe / sqec
    return gme

def gm_fd(y_true, y_pred, c):            ## Rnaga: GM-version
    """
    A function to calculate Geman-McClure error for Newton-Raphson.

    Args:
        y_true: list of true y values
        y_pred: list of predicted y values
        c: Geman-McClure arameter
    Returns:
        list of its first derivatives.
"""
    ey = y_true - y_pred
    sqe = ey ** 2
    sqc = c * c
    sqec = sqe + sqc
    fd_gme = 2 * sqc * ey / (sqec*sqec)
    return fd_gme

def gm_sd(y_true, y_pred, c):            ## Rnaga: GM-version
    """
    A function to calculate Geman-McClure error for Newton-Raphson.

    Args:
        y_true: list of true y values
        y_pred: list of predicted y values
        c: Geman-McClure arameter
    Returns:
        list of its second derivatives.
"""
    ey = y_true - y_pred
    sqe = ey ** 2
    sqc = c * c
    sqec = sqe + sqc
    sd_gme = 2 * sqc * (sqc - 6 * sqe)/(sqec*sqec*sqec)
    return sd_gme

def mean_gm_error(y_true, y_pred, c):          ## Rnaga: GM-version
    return np.sum(gm_error_loss(y_true, y_pred, c)) / y_true.shape[0]

def gm_fd_total(y_true, y_pred, c):          ## Rnaga: GM-version
    return np.sum(gm_fd(y_true, y_pred, c))

def gm_sd_total(y_true, y_pred, c):          ## Rnaga: GM-version
    return np.sum(gm_sd(y_true, y_pred, c))

class LinearModel():
    """
    A class to generate a baseline.

    Methods:
        fit0: fit method in the class.
        predict: predict method in the class.
    """
    def __init__(self):
        self.params = None

    def fit0(self, X: np.ndarray, y: np.ndarray, w: np.ndarray):  # Rnaga
        self.params = np.ma.dot(y.T,w)/np.ma.sum(w)     # Rnaga
        #self.params = np.ma.mean(y)     # ma.dot works with masked array
        return self

    def predict(self, X: np.ndarray):
        r, _ = X.shape
        X = np.ones((r, 1))           # modified for horizinal base line
        ##return X @ self.params                              # @ cannot work with masked array
        return X * self.params 

if __name__ == "__main__":
    Database_selector = 1
    _bl_selector = True
    if Database_selector == 0 or Database_selector == 1:
        get_ipython().run_line_magic('cd', 'C:\\Users\\TakeshiShakunaga\\line-forest')
    elif Database_selector == 2:
        get_ipython().run_line_magic('cd', 'C:\\Users\\TakeshiShakunaga\\multi-wide-line')
    elif Database_selector == 3:
        get_ipython().run_line_magic('cd', 'C:\\Users\\TakeshiShakunaga\\weak-wide-line')
    elif Database_selector == 4:
        get_ipython().run_line_magic('cd', 'C:\\Users\\TakeshiShakunaga\\wide-line-at-spw-edge')
    #%cd C:\Users\TakeshiShakunaga\dset_data
    import matplotlib.pyplot as plt
    import scipy.stats as ss
    from math import pi, sqrt, exp, log   
    Draw_graph = True
    loc_all = 1
    if Database_selector == 0:
        if _bl_selector:
            file_name_list_original = ['simplegrid_stage11_spw17_field1','simplegrid_stage11_spw19_field1',
                              'simplegrid_stage11_spw21_field1','simplegrid_stage11_spw23_field1']
        else:
            file_name_list_original = ['simplegrid_stage9_spw17_field1','simplegrid_stage9_spw19_field1',
                                    'simplegrid_stage9_spw21_field1','simplegrid_stage9_spw23_field1']
    elif Database_selector == 1:
        if _bl_selector:
            file_name_list_original =['simplegrid_stage11_spw25_field1','simplegrid_stage11_spw27_field1',
                          'simplegrid_stage11_spw29_field1','simplegrid_stage11_spw31_field1']
        else:
            file_name_list_original = ['simplegrid_stage9_spw25_field1','simplegrid_stage9_spw27_field1',
                                    'simplegrid_stage9_spw29_field1','simplegrid_stage9_spw31_field1']
    elif Database_selector == 2:
        if _bl_selector:
            file_name_list_original = ['simplegrid_stage11_spw17_field2','simplegrid_stage11_spw19_field2',
                                      'simplegrid_stage11_spw21_field2','simplegrid_stage11_spw23_field2']
        else:
            file_name_list_original = ['simplegrid_stage9_spw17_field2','simplegrid_stage9_spw19_field2',
                                    'simplegrid_stage9_spw21_field2','simplegrid_stage9_spw23_field2']
    elif Database_selector >= 3:
        if _bl_selector:
            file_name_list_original = ['simplegrid_stage11_spw17_field1','simplegrid_stage11_spw19_field1',
                                      'simplegrid_stage11_spw21_field1','simplegrid_stage11_spw23_field1']
        else:
            file_name_list_original = ['simplegrid_stage9_spw17_field1','simplegrid_stage9_spw19_field1',
                                    'simplegrid_stage9_spw21_field1','simplegrid_stage9_spw23_field1']
    file_name_list = file_name_list_original
    if 1:                              # if 1, select one spw field
        file_name_list = []
        file_name_list.append(file_name_list_original[1])
        loc_all = 0                   # if 0, select locations by [loc_b loc_e]
        if loc_all == 0:
            loc_b =  99 #139 #72
            if Database_selector == 3:
                loc_b = 102
            elif Database_selector == 4:
                loc_b = 0
            loc_e = loc_b + 9 #30  #15
    for file_name in file_name_list:
        data_file =file_name+'.npz'
        data = np.load(data_file)                         # np.load('data1_17_1.npz')
        #data = np.load(directory_name+data_file)         # np.load('data1_17_1.npz')
        full_spectrum = data['data'][:,:]
        fs_mask = data['mask'][:,:]
        fs = np.ma.array(full_spectrum,mask=fs_mask)
        #print(fs_mask,np.sum(fs_mask))
        print(fs.shape)

        spectrum = np.ma.arange(fs.shape[1], dtype=np.float64)

        loc_max = fs.shape[0]
        if loc_all:
            loc_b = 0 #loc_max // 4 #loc_max//4 #//4
            loc_e = loc_max #loc_b + 3 #loc_max // 2 #loc_max // 2 #int(loc_max//2) #loc_max//2 #loc_b + 1
        print('loc_b,loc_e',loc_b,loc_e,loc_max,fs.shape[1])
        base_l = np.arange(loc_e-loc_b, dtype=np.float64)
        base_lr = np.arange(loc_e-loc_b, dtype=np.float64)
        color = ["red", "yellow", "green", "blue", "purple"]
        for loc in range(loc_b,loc_e):
            str1 = format(loc,'03d')
            data_file = file_name + '.npz#' + str1
            #spectrum = fs[loc,:]
            for j in range(spectrum.shape[0]):
                spectrum[j] = fs[loc,j]

            X = np.ma.arange(len(spectrum)).reshape(-1,1)   # ma doesn't work with @
            if Draw_graph:
                plt.style.use("seaborn-darkgrid")
                plt.rcParams["figure.figsize"] = [20,6]#ax.set_box_aspect(0.5)  # 0.2     1
                parameters = {'axes.labelsize': 25,'axes.titlesize': 35,'xtick.labelsize':20,'ytick.labelsize':20}
                plt.rcParams.update(parameters)
                fig, ax = plt.subplots(1, 1)
            ii = -1

            thr_rmg = 2.25
            e_std_max = 12
            for m in range(1):      # if 1:
                mean_sp = np.ma.mean(spectrum)
                height_sp = np.ma.max(spectrum)-mean_sp
                depth_sp = mean_sp - np.ma.min(spectrum)
                sigma_sp = np.ma.std(spectrum)
                mean_level = np.arange(e_std_max,dtype=float)
                cut_level = np.arange(e_std_max,dtype=float)
                spectrum1 = spectrum
                for e_std in range(e_std_max):
                    if height_sp > depth_sp:
                        mean_level[e_std]=mean_sp
                        cut_level[e_std]=mean_sp+sigma_sp*2
                        upper_part = np.where(spectrum1>cut_level[e_std])
                        if e_std == 0:                              # For initial division
                            thr_level = 2.0
                            while upper_part[0].shape[0] == 0:      # Very rare cases, thr_level is tuned for the set
                                thr_level -= 0.33
                                cut_level[e_std]=mean_sp+sigma_sp*thr_level
                                upper_part = np.where(spectrum1>cut_level[e_std])
                        lower_part = np.where(spectrum1<=cut_level[e_std])
                    else:
                        mean_level[e_std]=mean_sp
                        cut_level[e_std]=mean_sp-sigma_sp*2
                        lower_part = np.where(spectrum1<cut_level[e_std])
                        if e_std == 0:                              # For initial division
                            thr_level = 2.0
                            while lower_part[0].shape[0] == 0:      # Very rare cases, thr_level is tuned for the set
                                thr_level -= 0.33
                                cut_level[e_std]=mean_sp-sigma_sp*thr_level
                                lower_part = np.where(spectrum1<cut_level[e_std])
                        upper_part = np.where(spectrum1>=cut_level[e_std])
                    upper_mean = np.mean(spectrum1[upper_part])    # np.ma.mean
                    lower_mean = np.mean(spectrum1[lower_part])
                    mean_gap = upper_mean - lower_mean
                    relative_mean_gap = mean_gap/sigma_sp
                    print('statistics0:',e_std,mean_gap,sigma_sp,relative_mean_gap,mean_level[e_std],cut_level[e_std])
                    if height_sp > depth_sp:
                        sigma_sp = np.ma.std(spectrum1[lower_part])
                        mean_sp = lower_mean
                    else:
                        #print('**negative')
                        sigma_sp = np.ma.std(spectrum1[upper_part])
                        mean_sp = upper_mean

                    if relative_mean_gap > thr_rmg:           # thr_tmg = 2.25 is empirically tuned.   # relative_mean_gap converges to 2.25
                        if height_sp > depth_sp:
                            spectrum1 = spectrum1[lower_part]             # This substitution is important for convergence 
                        else:
                            spectrum1 = spectrum1[upper_part]             # This substitution is important for convergence 
                        #print('statistics1:',e_std,mean_gap,sigma_sp,relative_mean_gap)
                    else:
                        mean_level[e_std+1]=mean_sp
                        break
                print('sigma_sp,mean_sp',sigma_sp,mean_sp)

                t_param = 3.0 * sigma_sp

                y = np.ma.array(spectrum).reshape(-1,1) 
                yc_list = np.ma.array(copy(spectrum[0:1])).reshape(-1,1)
                yc_list[0]= mean_sp

                regressor = GM(t=t_param,g=gm_param, y_list=yc_list, model=LinearModel(), #loss=gm_error_loss,# fd=gm_fd, sd=gm_sd,
                               metric=mean_gm_error, fdt=gm_fd_total, sdt=gm_sd_total)
                
                ones = np.ones((len(X), 1))
                a=regressor.fit(X, y, ones)
                #print(vars(a.self.best_model))

                if Draw_graph:
                    line = np.linspace(min(X), max(X), num=100).reshape(-1, 1)
                    #print (line, regressor.predict(line))
                    #plt.plot(line, regressor.predict(line), c="red")
                    if m==0:
                        plt.scatter(X,np.ma.array(spectrum).reshape(-1,1),color="peru")
                        plt.scatter(X, y)
                    else:
                        plt.scatter(X,np.ma.array(spectrum).reshape(-1,1))
                    plt.plot(line, regressor.predict(line), c=color[m % 5])
            #plt.show()
            if Draw_graph:
                str1 = format(gm_param,'01d')
                str3b = format(loop_best,'01d')
                str5 = format(t_param,'3.2f')
                resultfile='result_gm_'+file_name+'_'+str1+'_'+str3b+str5+'.png'
                plt.savefig(resultfile)