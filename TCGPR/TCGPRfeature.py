# coding = UTF-8
import time
import warnings
import copy
import math
import random
import numpy as np
import pandas as pd
from scipy.stats import norm
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF
from sklearn.model_selection import LeaveOneOut
from itertools import combinations
from sklearn.model_selection import KFold

# the main function
# treat the columns 
def cal_TCGPR(filePath, initial_set_cap=2, sampling_cap=1, ratio=0.005, up_search = 50, target = 1, exploit_coef=2, CV = 10,
    alpha=1e-10, n_restarts_optimizer=10,normalize_y=True, exploit_model = False):

    """
    Algorithm name: Tree classifier for gaussian process regression
    23 April 2022, version 1, Bin Cao, MGI, SHU, Shanghai, CHINA.

    :param filePath: the input dataset in csv

    :param initial_set_cap: the initial feature set, default = 1, recommend = 1-5
            or a list : i.e.,  
            [3,4,8], means the 4-th, 5-th, 9-th feature will be selected as the initial characterize

    :param sampling_cap: the number of features added to the updating feature set at each iteration, default = 1, recommend = 1-3

    :param ratio: tolerance, lower boundary of R is (1+ratio)R[last], default = 0.1, recommend = 0-0.3

    :param up_search: up boundary of candidates for brute force search, default = 20 , recommend =  10-2e2

    :param exploit_coef: constrains to the magnitude of variance in Cal_EI function,default = 2, recommend = 2

    :param CV: cross validation, default = 10
    e.g. (int) CV = 5,10,... or str CV = 'LOOCV' for leave one out cross validation

    :param defined in Gpr
    alpha : float or array-like of shape (n_samples), default=1e-10
            Value added to the diagonal of the kernel matrix during fitting.
            Larger values correspond to increased noise level in the observations.
            This can also prevent a potential numerical issue during fitting, by
            ensuring that the calculated values form a positive definite matrix.
            If an array is passed, it must have the same number of entries as the
            data used for fitting and is used as datapoint-dependent noise level.
            Note that this is equivalent to adding a WhiteKernel with c=alpha.
            Allowing to specify the noise level directly as a parameter is mainly
            for convenience and for consistency with Ridge.

    optimizer : "fmin_l_bfgs_b" or callable, default="fmin_l_bfgs_b"
            Can either be one of the internally supported optimizers for optimizing
            the kernel's parameters, specified by a string, or an externally
            defined optimizer passed as a callable. If a callable is passed, it
            must have the signature::

            def optimizer(obj_func, initial_theta, bounds):
                # * 'obj_func' is the objective function to be minimized, which
                #   takes the hyperparameters theta as parameter and an
                #   optional flag eval_gradient, which determines if the
                #   gradient is returned additionally to the function value
                # * 'initial_theta': the initial value for theta, which can be
                #   used by local optimizers
                # * 'bounds': the bounds on the values of theta
                ....
                # Returned are the best found hyperparameters theta and
                # the corresponding value of the target function.
                return theta_opt, func_min

            Per default, the 'L-BGFS-B' algorithm from scipy.optimize.minimize
            is used. If None is passed, the kernel's parameters are kept fixed.
            Available internal optimizers are::

                'fmin_l_bfgs_b'

    n_restarts_optimizer : int, default=10
            The number of restarts of the optimizer for finding the kernel's
            parameters which maximize the log-marginal likelihood. The first run
            of the optimizer is performed from the kernel's initial parameters,
            the remaining ones (if any) from thetas sampled log-uniform randomly
            from the space of allowed theta-values. If greater than 0, all bounds
            must be finite. Note that n_restarts_optimizer == 0 implies that one
            run is performed.

    normalize_y : boolean, optional (default: False)
            Whether the target values y are normalized, the mean and variance of
            the target values are set equal to 0 and 1 respectively. This is
            recommended for cases where zero-mean, unit-variance priors are used.
            Note that, in this implementation, the normalisation is reversed
            before the GP predictions are reported.

    :param exploit_model: boolean,(default: False)
            if exploit_model == True, the searching direction will be R only! GGMF will not be used!

    :return: a list of selected features and a new dataset generated by TCGPR
    """


    # import dataset
    dataset = pd.read_csv(filePath)
    data = dataset.iloc[:,:-target]
    response = np.array(dataset.iloc[:,-target:])
    response_name = dataset.columns[-target:]
    # be executed time
    timename = time.localtime(time.time())
    namey, nameM, named, nameh, namem, mames = timename.tm_year, timename.tm_mon, timename.tm_mday, timename.tm_hour, timename.tm_min, timename.tm_sec
    warnings.filterwarnings('ignore')

    fea_name = data.columns
    fea_num = len(fea_name)
    data = np.array(data)
    datanum = len(data)
    # global settings
    fitting_goodness_track = []
    GGMF_GLOBAL_Track = []
    Feature_Track = []

    if type(initial_set_cap) != int:
        if type(initial_set_cap) == list:
            zero_ini_dataset = np.zeros((datanum,len(initial_set_cap)))
            for feature in range(len(initial_set_cap)):  
                # read in the index of datum in raw dataset
                zero_ini_dataset[:,feature] = data[:,initial_set_cap[feature]]
                # save the selected features
                Feature_Track.append(fea_name[initial_set_cap[feature]])

            ini_data = copy.deepcopy(zero_ini_dataset)
            
            # evaluate the quality of initial dataset
            GGMF_ini,Rvalue,_ = dataset_eval(ini_data,response,n_restarts_optimizer,alpha,normalize_y,exploit_model,CV)
          
            fitting_goodness_track.append(1 - Rvalue)
            GGMF_GLOBAL_Track.append(GGMF_ini)

            up_data = np.delete(data, initial_set_cap, axis=1)
            outdata = pd.DataFrame(ini_data)
            outdata.columns = Feature_Track
            print('THE specific Initial feature set is \n', outdata.head())
            print('-'*100)

    elif initial_set_cap < 1:
        print('The initial capacity of dataset must be larger than 1!')
        print('Please input a right integer value')

    elif initial_set_cap >= fea_num:
        print('The initial capacity of dataset must be smaller than the original number of features!')
        print('Please input a right integer value')
    
    else:
        # seraching the initial feature set
        cal_initial_feaset_index = list(combinations(range(fea_num), initial_set_cap))
        # Determine if the searching space is too large
        if len(cal_initial_feaset_index) <= up_search:
            initial_feaset_index = copy.deepcopy(cal_initial_feaset_index)
            print('The algorithm will searching all candidates by brute force searching')
        else:
            print('Candidates at current searching apace are {totalcan} \n'' {samcan} candidates will be randomly chosen '.format(totalcan=len(cal_initial_feaset_index),
                                                                         samcan=up_search))
            initial_feaset_index = list_random_del_function(cal_initial_feaset_index, up_search)

        # local setting
        GGMF_set = []
        uncer_set = []
        Rvalue_set = []
        Feature_set = []
        for set_index in range(len(initial_feaset_index)):  
            # read in the combination situations
            zero_ini_dataset = np.zeros((datanum, initial_set_cap))
            fea_name_set = []
            for fea in range(initial_set_cap):  
                # read in the index of feature in raw dataset
                fea_index = initial_feaset_index[set_index][fea]
                zero_ini_dataset[:,fea] = data[:,fea_index]
                fea_name_set.append(fea_name[fea_index])
            _ini_data = copy.deepcopy(zero_ini_dataset)
            # save the feature names of diff combination    
            Feature_set.append(fea_name_set)

            # testing the quality of initial dataset
            GGMF_ini,Rvalue,y_std_set = dataset_eval(_ini_data,response,n_restarts_optimizer,alpha,normalize_y,exploit_model,CV) 
            Rvalue_set.append(Rvalue)
            uncer_set.append(np.array(y_std_set).mean())
            # loss, the lower the better
            GGMF_set.append(GGMF_ini)

        uncer_array = np.array(uncer_set)
        GGMF_array = np.array(GGMF_set)

        GGMF_empty = np.nanmax(GGMF_array) * 1.5
        _Expected_improvement = Cal_EI(GGMF_array, uncer_array, GGMF_empty, exploit_coef)
        initial_EI = np.nanmax(_Expected_improvement, axis=0)
        EI_ini_dat_index = np.where(_Expected_improvement == initial_EI)[0][0]
        fitting_goodness_track.append(1 - Rvalue_set[EI_ini_dat_index])
        GGMF_initial = GGMF_array[EI_ini_dat_index]
        GGMF_GLOBAL_Track.append(GGMF_initial)
        # consider the saving format
        for j in range(len(Feature_set[EI_ini_dat_index])):
            Feature_Track.append(Feature_set[EI_ini_dat_index][j])

        _zero_ini_dataset = np.zeros((datanum, initial_set_cap))
        for j in range(initial_set_cap):  
            # read in the index of datum in raw dataset
            _datum_index = initial_feaset_index[EI_ini_dat_index][j]
            _zero_ini_dataset[:,j] = data[:,_datum_index]
            # del the choosen data from the original datset
        ini_data = copy.deepcopy(_zero_ini_dataset)
        up_data = np.delete(data, initial_feaset_index[EI_ini_dat_index], axis=1)

        # JUST for output the pandas format
        outdata = pd.DataFrame(ini_data)
        outdata.columns = Feature_Track
        print('After searching by TCGPR, THE most suitable Initial feature set is \n', outdata.head())
        print('-'*100)

      
    # iteration
    # adding features into the initial feature set
    if type(sampling_cap) != int:
        print('The Sampling capacity at each iteration must be a integer ')
    elif sampling_cap < 1:
        print('The Sampling capacity at each iteration must be no samller than 1!')
        print('Please input a right integer value')
    elif sampling_cap == 1:
        print('It a greedy searching strategy, since the sampling_cap is 1')
        # adding data one by one into the initial dataset
        inter = 0
        # main loop
        while True: 
            GGMF_inter_index = inter 
            inter += 1
            
            if len(up_data[0]) < sampling_cap:
                data_in_pd = pd.DataFrame(ini_data)
                data_in_pd.columns = Feature_Track
                data_in_pd_rest = pd.DataFrame(up_data)
                data_in_pd_rest.columns = redundancy_fea(fea_name,Feature_Track)
                print('Only {reddata} features are remained, the sampling_cap = {sampling_cap_} is larger than it'.format(
                        reddata=len(up_data[0]), sampling_cap_=sampling_cap))
                print('*'*100)
                print('The selected features are :', Feature_Track)
                print('The dataset after feature selection is : \n', data_in_pd.head())
                print('The changes of fitting goodness is : \n', fitting_goodness_track[:-1])
                print('The dataset after feature selection has been saved successfully!')
                print('*'*100)
                complate_dataset(data_in_pd,response,response_name).to_csv('Featureset selected by TCGPR {year}.{month}.{day}-{hour}.{minute}.{second}.csv'
                        .format(year=namey, month=nameM, day=named, hour=nameh, minute=namem, second=mames),index=False)
                complate_dataset(data_in_pd_rest,response,response_name).to_csv('Featureset remained by TCGPR.csv',index=False)
                break

            else:
                _uncer_array,GGMF_inter_array,_Rvalue_set,_ = best_supplement(response,up_data,ini_data,n_restarts_optimizer,alpha,normalize_y,exploit_model,sampling_cap,up_search,CV,single_samples=True)

                Expected_improvement = Cal_EI(GGMF_inter_array, _uncer_array, GGMF_GLOBAL_Track[GGMF_inter_index],exploit_coef)
                # select the best datum with highest improvement
                EI_max = np.nanmax(Expected_improvement, axis=0)
                EI_index = np.where(Expected_improvement == EI_max)[0][0]
                fitting_goodness_track.append(1 - _Rvalue_set[EI_index])
                GGMF = GGMF_inter_array[EI_index]
                GGMF_GLOBAL_Track.append(GGMF)
                red_fea = redundancy_fea(fea_name, Feature_Track)
                Feature_Track.append(red_fea[EI_index])


                # save archive
                ulti_data = copy.deepcopy(ini_data)
                ulti_rest_data = copy.deepcopy(up_data)

                if fitting_goodness_track[inter] >= (1 + ratio) * fitting_goodness_track[inter-1]:
                    print('{iteration}-th iteration : The newly added feature is'.format(iteration=inter))
                    print(red_fea[EI_index])
                    # uppdate the datset, one iteation finished
                    ini_data = np.column_stack((ini_data, up_data[:,EI_index]))
                    up_data = np.delete(up_data, [EI_index], axis=1)

                else:
                    data_in_pd = pd.DataFrame(ulti_data)
                    data_in_pd.columns = Feature_Track[:-1]
                    data_in_pd_rest = pd.DataFrame(ulti_rest_data)
                    data_in_pd_rest.columns = redundancy_fea(fea_name,Feature_Track[:-1])
                    print('*'*100)
                    print('The selected features are :', Feature_Track[:-1])
                    print('The dataset after feature selection is : \n', data_in_pd.head())
                    print('The changes of fitting goodness is : \n', fitting_goodness_track[:-1])
                    print('The dataset after feature selection has been saved successfully!')
                    print('*'*100)
                    complate_dataset(data_in_pd,response,response_name).to_csv(
                        'Dataset selected by TCGPR {year}.{month}.{day}-{hour}.{minute}.{second}.csv'
                            .format(year=namey, month=nameM, day=named, hour=nameh, minute=namem, second=mames),index = False)
                    complate_dataset(data_in_pd_rest,response,response_name).to_csv('Dataset remained by TCGPR.csv', index=False)
                    break

    elif sampling_cap > len(up_data[0]):
        # forbided 
        print('The input sampling_cap is too large!' )

    elif sampling_cap > 1:
        print('The input sampling_cap is {num}'.format(num=sampling_cap))
        inter = 0
        # main loop
        while True: 
            GGMF_inter_index = inter
            inter += 1

            if len(up_data[0]) < sampling_cap:
                data_in_pd = pd.DataFrame(ini_data)
                data_in_pd.columns = Feature_Track
                data_in_pd_rest = pd.DataFrame(up_data)
                data_in_pd_rest.columns = redundancy_fea(fea_name,Feature_Track)
                print('Only {reddata} features are remained, the sampling_cap = {sampling_cap_} is larger than it'.format(
                    reddata=len(up_data[0]), sampling_cap_=sampling_cap))
                print('*'*100)
                print('The selected features are :', Feature_Track)
                print('The dataset after feature selection is : \n', data_in_pd.head())
                print('The changes of fitting goodness is : \n', fitting_goodness_track[:-1])
                print('The dataset after feature selection has been saved successfully!')
                print('*'*100)
                complate_dataset(data_in_pd,response,response_name).to_csv('Dataset selected by TCGPR {year}.{month}.{day}-{hour}.{minute}.{second}.csv'
                        .format(year=namey, month=nameM, day=named, hour=nameh, minute=namem, second=mames),index=False)
                complate_dataset(data_in_pd_rest,response,response_name).to_csv('Dataset remained by TCGPR.csv', index=False)
                break

            else:
                _uncer_array,GGMF_inter_array,_Rvalue_set,sampling_index = best_supplement(response,up_data,ini_data,n_restarts_optimizer,alpha,normalize_y,exploit_model,sampling_cap,up_search,CV,single_samples=0)
                Expected_improvement = Cal_EI(GGMF_inter_array, _uncer_array, GGMF_GLOBAL_Track[GGMF_inter_index],exploit_coef)
                EI_max = np.nanmax(Expected_improvement, axis=0)
                EI_index = np.where(Expected_improvement == EI_max)[0][0]
                fitting_goodness_track.append(1 - _Rvalue_set[EI_index])
                GGMF = GGMF_inter_array[EI_index]
                GGMF_GLOBAL_Track.append(GGMF)
                red_fea = redundancy_fea(fea_name, Feature_Track)
                for j in range(len(sampling_index[EI_index])):
                    Feature_Track.append(red_fea[sampling_index[EI_index][j]])

                # save archive
                ulti_data = copy.deepcopy(ini_data)
                ulti_rest_data = copy.deepcopy(up_data)

                if fitting_goodness_track[inter] >= (1 + ratio) * fitting_goodness_track[inter-1]:
                    print('{iteration}-th iteration : The newly added features are'.format(iteration=inter))
                    print(Feature_Track[-sampling_cap:])
                   
                    for i in range(len(sampling_index[EI_index])):
                        # uppdate the datset
                        ini_data = np.column_stack((ini_data, up_data[:,sampling_index[EI_index][i]]))
                    up_data = np.delete(up_data, sampling_index[EI_index], axis=1)

                else:
                    data_in_pd = pd.DataFrame(ulti_data)
                    data_in_pd.columns = Feature_Track[:-sampling_cap]
                    data_in_pd_rest = pd.DataFrame(ulti_rest_data)
                    data_in_pd_rest.columns = redundancy_fea(fea_name,Feature_Track[:-sampling_cap])
                    print('*'*100)
                    print('The selected features are :', Feature_Track[:-sampling_cap])
                    print('The dataset after feature selection is : \n', data_in_pd.head())
                    print('The changes of fitting goodness is : \n', fitting_goodness_track[:-1])
                    print('The dataset after feature selection has been saved successfully!')
                    print('*'*100)
                    complate_dataset(data_in_pd,response,response_name).to_csv(
                        'Dataset selected by TCGPR {year}.{month}.{day}-{hour}.{minute}.{second}.csv'
                            .format(year=namey, month=nameM, day=named, hour=nameh, minute=namem, second=mames),
                        index=False)
                    complate_dataset(data_in_pd_rest,response,response_name).to_csv('Dataset remained by TCGPR.csv', index=False)

                    break
    else:
        print('The initial capacity of feature set must be a integer or a list ')

def redundancy_fea(fea_name, selected_features):
    # fea_name is a index object of pandas attribute
    # selected_features is a list of features
    # returned a list called red_fea
    red_fea = []
    for i in range(len(fea_name)):
        if fea_name[i] not in selected_features:
            red_fea.append(fea_name[i])
        else:
            pass
    return red_fea 

def complate_dataset(dataset,response,response_name):
    for j in range(len(response_name)):
        _column_name = response_name[j]
        dataset[_column_name] = response[:,j]
    return dataset

# define the function for calculating 1-R value
def PearsonR(X, Y,target):
    X_ = copy.deepcopy(np.array(X)).reshape(-1,target)
    Y_ = copy.deepcopy(np.array(Y)).reshape(-1,target)
    R_value = 0
    for j in range(target):
        X = X_[:,j]
        Y = Y_[:,j]
        xBar = np.mean(X)
        yBar = np.mean(Y)
        SSR = 0
        varX = 0
        varY = 0
        for i in range(0, len(X)):
            diffXXBar = X[i] - xBar
            diffYYBar = Y[i] - yBar
            SSR += (diffXXBar * diffYYBar)
            varX += diffXXBar ** 2
            varY += diffYYBar ** 2
        SST = math.sqrt(varX * varY)
    R_value += (1 - SSR / SST)
    return R_value/target



# define the function for calculating the standard normal probability distribution
def norm_des(x):
    return 1 / np.sqrt(2 * np.pi) * np.exp(- x ** 2 / 2)


# def the global gaussian messy factor
def GGMfactor(lik_hood, Rvalue, Length_scale, exploit_model):
    if exploit_model == True:
        return Rvalue
    else:
        return np.log(lik_hood + 1) * Rvalue / np.log(Length_scale + 1)

# def the  expected decrease
def Cal_EI(pre, std, currentmin, exploit_coef ):
    if len(pre) == len(std):
        std = np.log(exploit_coef + std) + 1e-10
        EI = []
        for i in range(len(pre)):
            each_EI = (currentmin - pre[i]) * norm.cdf((currentmin - pre[i]) / std[i]) \
                      + std[i] * norm_des((currentmin - pre[i]) / std[i])
            EI.append(each_EI)
        return np.array(EI)
    else:
        return 'Num Error'

# def the sampling function
def list_random_del_function(list_, up_save_num):
    del_num = int(len(list_) - up_save_num)
    if del_num <= up_save_num:
        del_lis = random.sample(range(0,len(list_)),del_num)
        out_list = [n for i, n in enumerate(list_) if i not in del_lis]
    else:
        out_list = []
        sav_index = random.sample(range(0,len(list_)),up_save_num)
        for i in range(up_save_num):
            out_list.append(list_[sav_index[i]])
    return out_list

def dataset_eval(dataset,response,n_restarts_optimizer,alpha,normalize_y,exploit_model,CV):
    # evaluate the quality of dataset
    KErnel = RBF(length_scale_bounds = (1e-2, 1e2))
    X = dataset
    Y = response
    target = Y.shape[1]
    y_pre_set = []
    y_std_set = []
    ls_set = []
    neg_lik_hood_set = []
    if CV == 'LOOCV':
        loo = LeaveOneOut()
        for train_index, test_index in loo.split(X):
            X_train, X_test = X[train_index], X[test_index]
            y_train, _ = Y[train_index], Y[test_index]
            Gpr_i = GaussianProcessRegressor(kernel=KErnel,
                                            n_restarts_optimizer=n_restarts_optimizer,
                                            alpha=alpha,
                                            normalize_y=normalize_y,
                                            random_state=0).fit(X_train, y_train)

            LS_i = np.exp(Gpr_i.kernel_.theta)
            ls_set.append(LS_i)
            neg_li = - Gpr_i.log_marginal_likelihood(LS_i)
            neg_lik_hood_set.append(neg_li)
            y_pre = Gpr_i.predict(X_test, return_std=True)[0]
            y_std = Gpr_i.predict(X_test, return_std=True)[1]
            y_pre_set.append(y_pre[0])
            y_std_set.append(y_std.mean())
        Rvalue = PearsonR(y_pre_set, Y,target)
        _LS_i = np.array(ls_set).mean()
        Lik_hood_value = np.array(neg_lik_hood_set).mean()
        GGMF_value = GGMfactor(Lik_hood_value, Rvalue, _LS_i, exploit_model)
    else:
        kfold = TCGPR_KFold(X, Y, CV)
        for train_index, test_index in kfold:
            X_train, X_test = X[train_index], X[test_index]
            y_train, _ = Y[train_index], Y[test_index]
            Gpr_i = GaussianProcessRegressor(kernel=KErnel,
                                            n_restarts_optimizer=n_restarts_optimizer,
                                            alpha=alpha,
                                            normalize_y=normalize_y,
                                            random_state=0).fit(X_train, y_train)

            LS_i = np.exp(Gpr_i.kernel_.theta)
            ls_set.append(LS_i)
            neg_li = - Gpr_i.log_marginal_likelihood(LS_i)
            neg_lik_hood_set.append(neg_li)
            y_pre = Gpr_i.predict(X_test, return_std=True)[0]
            y_std = Gpr_i.predict(X_test, return_std=True)[1]
            y_pre_set.append(y_pre[0])
            y_std_set.append(y_std.mean())
        Rvalue = PearsonR(y_pre_set, Y,target)
        _LS_i = np.array(ls_set).mean()
        Lik_hood_value = np.array(neg_lik_hood_set).mean()
        GGMF_value = GGMfactor(Lik_hood_value, Rvalue, _LS_i, exploit_model)
    return GGMF_value,Rvalue,y_std_set

def best_supplement(response,up_data,ini_data,n_restarts_optimizer,alpha,normalize_y,exploit_model,sampling_cap,up_search,CV,single_samples=True):
    # add one datum 
    if single_samples == True:
        GGMF_inter_set = []
        _uncer_set = []
        _Rvalue_set = []
        for i in range(len(up_data[0])):
            dataset_inter = copy.deepcopy(ini_data)
            dataset_inter = np.column_stack((dataset_inter, up_data[:,i]))

            GGMF_inter,_Rvalue, _y_std_set= dataset_eval(dataset_inter,response,n_restarts_optimizer,alpha,normalize_y,exploit_model,CV)

            _Rvalue_set.append(_Rvalue)
            _uncer_set.append(np.array(_y_std_set).mean())
            GGMF_inter_set.append(GGMF_inter)

        _uncer_array = np.array(_uncer_set)
        GGMF_inter_array = np.array(GGMF_inter_set)
        sampling_index = None
    
    # add a set of data  
    else:
        GGMF_inter_set = []
        _uncer_set = []
        _Rvalue_set = []
        cal_sampling_index = list(combinations(range(len(up_data[0])), sampling_cap))
        # Determine if the searching space is too large
        if len(cal_sampling_index) <= up_search:
            sampling_index = copy.deepcopy(cal_sampling_index)
            print('The algorithm will searching all candidates by brute force searching')
        else:
            print('Candidates at current searching space are {totalcan} \n'
                    ' {samcan} candidates will be randomly chosen and compared'.format(totalcan = len(cal_sampling_index), samcan= up_search))
            sampling_index = list_random_del_function(cal_sampling_index,up_search)

       
        for k in range(len(sampling_index)):  # read in the combination situations
            zero_samp_dataset = np.zeros((len(up_data), sampling_cap))
            for fea in range(sampling_cap):  # read in the index of datum in raw dataset
                fea_index = sampling_index[k][fea]
                zero_samp_dataset[:,fea] = up_data[:,fea_index]
            sam_data = copy.deepcopy(zero_samp_dataset)

            dataset_inter = copy.deepcopy(ini_data)
            dataset_inter = np.column_stack((dataset_inter, sam_data))
            
            GGMF_inter,_Rvalue, _y_std_set= dataset_eval(dataset_inter,response,n_restarts_optimizer,alpha,normalize_y,exploit_model,CV)
            _Rvalue_set.append(_Rvalue)
            _uncer_set.append(np.array(_y_std_set).mean())
            GGMF_inter_set.append(GGMF_inter)

        _uncer_array = np.array(_uncer_set)
        GGMF_inter_array = np.array(GGMF_inter_set)
    return _uncer_array,GGMF_inter_array,_Rvalue_set,sampling_index


def TCGPR_KFold(x_train, y_train,cv):
    x_train = np.array(x_train)
    y_train = np.array(y_train)
    kfolder = KFold(n_splits=cv, shuffle=True,random_state=0)
    kfold = kfolder.split(x_train, y_train)
    return kfold