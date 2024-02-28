#!/usr/bin/env python
# coding: utf-8

In_pipeline : bool = False    # Set this boolean parameter to True 'In_pipeline'. 


# Find indices of lines from spectrum data.
# 
# <br>
#     lf_g_gmngs.py (v.4.3)<br>
#     This module provides a line finder based on Gaussian filter along with baseline estimator using Geman-McClure function.<br>
#     <br>
#     line_finder() is a main function of this module, which serves as a line finder for a given spectrum data.<br>
#     <br>
#     Abstract of line_finder() is as folows:<br>
#     0)Rough estimation of mean and std of Baseline by Iterative 2-sigma exclusions: (iterative_2s_exclusions())<br>
#     1)Baseline estimation by Geman-McClure function: (lf_gmn.py)<br>
#     2)Integrated line detection by zero-crossings of first derivative of Gaussian average of SIGNAL_BL: (integrated_line_detection())<br>
#       2.1)Narrow line detection by zero-crossings of the first derivative of Gaussian average on SIGNAL_BL: (narrow_line_detection())<br>
#       2.2)Indices of the detected lines are made: (in line_finder())
# 

sigma_sp :float          #STD, most important parameter estimated in this module
local_std :float         #local_std
ga5_std:float            #ga5_std
gs_param:float = 1.2     #2.0
optimum_sigma:float = 10.0   #10.0

e_std_max = 12          #Maximum iterations of iterative 2-sigma exclusions for estimation of STD and BL
e_std :int
thr_rmg = 2.25          #Main requirement for the estimation termination is relative_mean_gap < thr_rmg.
forced_level_down = 0.1 #When cut_level[est] is not effective in the iterative exclusions, cut_level is reduced forced_level_down

Baseline_estimation :bool = True    # If True, baseline estimation is effective.
Baseline_inclination :bool = True   # If False, horizontal baseline is assumed.
thr_ss = 128                        # Inclination is effective for dmax > thr_ss
thr_rpg = 0.5                       # Inclination is effective when abs(relative_pos_gap) > thr_rpg
Gaussian_enable:bool = True        # Gaussian_subtraction is used when linear baseline is inappropiate. 
Gaussian_subtraction:bool           # Boolen parameter for baseline type selection

# Baseline estimation by Geman-McClure function
gm_param = 4                         # In Geman-McClure function, parameter c is defined by STD/gm_param.

# Line/WideLine detection
sgzxmax=3             # 3: See details in line_finder()
wl_mask_index = 1     # 1: 0 through 3 are effective, wl_mask_index indicates a number of effective sigma's
thr_c = 0.01          # 0.01, fixed empirically, used in narrow_line_detection()
thr_h = 40            # 40, fixed empirically, used in integrated_line_detection()
thr_fgh = 100         # 100, fixed empirically, used in integrated_line_detection()

# Line Width estimation
Gaussian_sp_bl :bool   # When True, zero-crosings of Median of Gaussian (with sigma=1) of signal_bl is used for edge estimation
                       # Otherwise, zero-crossings of signal_bl is used.
median_iw :int         # global parameter controled by Gaussian_sp_bl
thr_Gsb = 20.0         # Threshold for determining Gaussian_sp_bl:      Gaussian_sp_bl = (max_height/sigma_sp < thr_Gsb)

# Other global parameters
dmax : int           # length of input spectrum
min_X : int          # effective range of spectrum is [min_x:max_x]
max_X : int          # effective range of spectrum is [min_x:max_x]
max_height : int     # maximum height of signal_bl
min_height : int     # minimum height of signal_bl
sign_dist : int      # automatically set to max_height/abs(min_height) in line_finder()

thr_d : float         # automatically tuned by Gaussian_sp_bl in narrow_line_detection()
thr_f1 : float        # automatically tuned by sign_dist in integrated_line_detection()
thr_f2 : float        # automatically tuned by sign_dist in integrated_line_detection()
thr_g1 : float         # automatically tuned to thr_d in integrated_line_detection()

# Parameters for Graphic Option
Draw_graph = True
Savefig_only_detected_lines = False    # True: Save figures if lines are detected   # False: Save all figures
Show_details = False             # False: only Fig-0,  # True: All Figs   # True : only Fig-i
Show_each = 0 # 0 1 2 3 4 5      # 0                   # 0                # i(1..5)
Show_label = True                #effective only when Show_details = False
Zoom_in = 0 # if Zoom_in=1,narrow band arround the highest peak is shown in the graph, if Zoom_in==2, given band.

import numpy as np
from math import pi, sqrt, exp, log, isnan
import copy
from typing import List, Optional
if In_pipeline:
    from . import lf_gmn_open as lfr   # bitbucket (pipeline)   lf_gmn_open
    Draw_graph = False
else:
    import lf_gmn as lfr          # jupyternote (version-4.3 uses lf_gmn module)

np_signal = 'np.ndarray[float]'
line_list = List[List[int]]
ranges = List[int]
kernel = List[float]
odd = int

def gaussian(n: odd, sigma: float) -> kernel:
    """
    Make a Gaussian kernel.
    Args:
        n: Filter size (odd number)
        sigma: Gaussian parameter (real number)
    Returns:
        kernel: A list of real numbers used for Gaussian averaging: 
                    Real numbers are in the order of [value(-m) value(-m+1) ... value(m)] when n = 2m + 1.
    """
    r = range(-int(n/2),int(n/2)+1)
    return [1 / (sigma * sqrt(2*pi)) *exp(-float(x)**2/(2*sigma**2)) for x in r]

def derivative_of_gaussian(n: odd, sigma: float) -> kernel:
    """
    Make a Gaussian derivative kernal for the first floor derivative of Gaussian.
    Args:
        n: Filter size (odd number)
        sigma: Gaussian parameter (real number)
    Returns:
        kernel: A list of real numbers for making the first floor derivative of Gaussian: 
                    Real numbers are in the order of [value(-m) value(-m+1) ... value(m)] when n = 2m + 1.
    """
    r = range(-int(n/2),int(n/2)+1)
    return [-x / (sigma**3 * sqrt(2*pi)) *exp(-float(x)**2/(2*sigma**2)) for x in r]

def second_floor_derivative_of_gaussian(n: odd, sigma: float) -> kernel:
    """
    Make a Gaussian derivative kernal for the second floor derivative of Gaussian.
    Args:
        n: Filter size (odd number)
        sigma: Gaussian parameter (real number)
    Returns:
        kernel: A list of real numbers for making the second floor derivative of Gaussian: 
                    Real numbers are in the order of [value(-m) value(-m+1) ... value(m)] when n = 2m + 1.
    """ 
    r = range(-int(n/2),int(n/2)+1)
    return [1 / (sigma**5 * sqrt(2*pi)) *(x**2 - sigma**2) * exp(-float(x)**2/(2*sigma**2)) for x in r]

def gaussian_average(_spectrum :np_signal, sigma: float) -> np_signal:
    """
    Make a Gaussian averaged signal from an input signal.
    Args:
        _spectrum: np.ndarray
        sigma: Gaussian parameter used for Gaussian averaging
    Returns:
        spectrum: np.ndarray made by covolusion of _spectrum and Gaussian kernel.
    """ 
    k_edge = int(sigma * 3)
    ksize= 2 * k_edge + 1
    _g = np.array(gaussian(ksize,sigma))      # normalization
    _g_total = np.sum(_g)
    _g /= _g_total
    return(np.ma.convolve(_spectrum, _g, propagate_mask=False)[k_edge:-k_edge])

def med_bl_a(sig :np_signal, ib:int, ibmin:int, ibmax:int) -> float:    # median of sig[ib0:ib1] is calculated 
    """
    Make a median signal at a channel from an input signal.
    Args:
        sig: np.ndarray
        ib: channel number(integer)
        ibmin: minimum limit
        ibmax: maximum limit
    Returns:
        real number: median of sig[ib+ib0:ib+ib1]
    """
    global median_iw
    median_iw = 0      # SOS
    ib0 = max(ibmin,ib-median_iw)
    ib1 = min(ibmax,ib+median_iw+1)
    return np.ma.median(sig[ib0:ib1])

def narrow_line_detection(sp_bl:np_signal, sigma:float, signal:np_signal, coeff:np_signal, wl_flag:'np.ndarray[int]', wl_analysis:bool) ->line_list:
    """
    Detect narrow lines from a baseline-subtracted signal using zero-crossings of the first derivative of Gaussian average.
    Qualification check is made by using the second derivative and baseline-subtracted signal.
    Args:
        sp_bl: np.ndarray representing a baseline-subtracted signal
        sigma: Gaussian parameter used for Gaussian averaging
        signal: np.ndarray representing the first floor derivative of Gaussian average of sp_bl
        coeff: np.ndarray representing the second floor derivative of Gaussian average of sp_bl
        wl_flag: np.ndarray[int] reprisenting whether each channel is included in wide-lines
        wl_analysis: bool representing effectiveness of the narrow-line detection in the wide-line ranges
    Requirements for narrow lines (effective when (not wl_flag[i] or wl_analysis) == True)
        1) -coeff[i] > thr_c (emission line)       coeff[i] > thr_c (absorption line)
        2) sp_bl[i] > thr_d1 * sigma_sp            sp_bl[i] < -sigma_sp *thrt_d2
    Returns:
        line_list: A list of list representing peak, start and end indices of spectral lines. The indices of 
                    lines are in the order of, e.g., [[peak1, start1, end1], ..., [peakN, startN, endN]].
    """
    global sigma_sp, Gaussian_sp_bl, thr_c, thr_d
    global min_X,max_X,max_height,min_height
    global median_iw
    detected_lines = []
    k_edge = int(sigma * 3)
    ksize= 2 * k_edge + 1

    # Prepare kernels of Gaussian and Gaussian derivatives
    _dg1 = np.array(derivative_of_gaussian(ksize,sigma))
    _cf1 = np.array(second_floor_derivative_of_gaussian(ksize,sigma))

    # Make Gaussian average and its derivatives
    signal[min_X:max_X] = np.ma.convolve(sp_bl[min_X:max_X], _dg1)[k_edge:-k_edge]    #length is adjusted after the convolution
    coeff[min_X:max_X] = np.ma.convolve(sp_bl[min_X:max_X], _cf1)[k_edge:-k_edge]
    std_coeff = np.std(coeff[min_X:max_X])
    coeff[min_X:max_X] /= std_coeff

    # Preparation for edge-detection.
    if Gaussian_sp_bl:        # When sp_bl is noisy, Gaussian average is used for adjusting edges.
        k_edge2 = 1
        g_ave2 = np.ma.arange(sp_bl.shape[0], dtype=np.float64)
        g_ave2[min_X:max_X] = gaussian_average(sp_bl[min_X:max_X],k_edge2)
        sp_bl_a = g_ave2
        median_iw = 1
        thr_d = 4.5
    else:                     # When sp_bl is not noisy, original signal is used for djusting edges.
        sp_bl_a = sp_bl
        median_iw = 0
        thr_d = 4.0
    thrt_d1 = thr_d
    thrt_d2 = thr_d * 1.5

    # Make a List of zero-crossings.
    zero_crossings = np.where(np.diff(np.sign(signal[min_X:max_X])))[0]     # Simple implementation of crossing-range detection.
    zero_crossings += min_X
    for j in range(len(zero_crossings)):
        i = zero_crossings[j]
        if abs(signal[i+1]) < abs(signal[i]):    # The nearer point is selected from two terminals of each range.
            i += 1
    for j in range(len(zero_crossings)):
        i = zero_crossings[j]
        ib_lim = min_X if j == 0 else zero_crossings[j-1]          # lower/upper limits of the line
        ie_lim = max_X if j == (len(zero_crossings)-1) else zero_crossings[j+1]
        dl_on = not wl_flag[i] or wl_analysis    # dl_on is controled by combination of wl_flag and wl_analysis
        emissional = (signal[i] > signal[i+1])
        if dl_on and emissional:
            if (-coeff[i] > thr_c and (sp_bl[i] > sigma_sp*thrt_d1)):          # Qualification by coeff and sp_bl
                if max_height > -min_height:
                    ib, ie = find_edges_e(i, sp_bl_a, ib_lim, ie_lim)
                    detected_lines.append([i,ib,ie])
        elif dl_on:  # absorption
            if coeff[i] > thr_c and sp_bl[i] < -sigma_sp *thrt_d2 :                   # Qualification by coeff and sp_bl
                if min_height < -max_height:
                    ib, ie = find_edges_a(i, sp_bl_a, ib_lim, ie_lim)
                    detected_lines.append([i,ib,ie])
    return(detected_lines)

def find_edges_e(i:int, sp_bl_a:np_signal, ib_lim:int, ie_lim:int) -> 'int,int':
    """
    Detect edges of emissional line in the both sides of location i.
    Args:
        i: channel number in the line
        sp_bl_a: np.ndarray representing a baseline-subtracted signal or its Gaussian average
        ib_lim: limit of left side 
        ie_lim: limit of right side
    Returns:
        ib: location of left edge
        ie: location of right edge
    """
    global min_X,max_X
    ib = i
    ie = i + 1        # SOS                    # lower/upper bounds of the line
    while med_bl_a(sp_bl_a, ib, min_X, max_X) > 0 and ib > ib_lim:  # Detect left zero-crossing of sp_bl_a
        ib -= 1
    while med_bl_a(sp_bl_a, ie, min_X, max_X) > 0 and ie < ie_lim:  # Detect right zero-crossing of sp_bl_a
        ie += 1
    return ib,ie

def find_edges_a(i:int, sp_bl_a:np_signal, ib_lim:int, ie_lim:int) -> 'int,int':
    """
    Detect edges of absorption line in the both sides of location i.
    Args:
        i: channel number in the line
        sp_bl_a: np.ndarray representing a baseline-subtracted signal or its Gaussian average
        ib_lim: limit of left side 
        ie_lim: limit of right side
    Returns:
        ib: location of left edge
        ie: location of right edge
    """
    global min_X,max_X
    ib = i
    ie = i + 1        # SOS                    # lower/upper bounds of the line
    while med_bl_a(sp_bl_a, ib, min_X, max_X) < 0 and ib > ib_lim:  # Detect left zero-crossing of sp_bl_a
        ib -= 1
    while med_bl_a(sp_bl_a, ie, min_X, max_X) < 0 and ie < ie_lim:  # Detect right zero-crossing of sp_bl_a
        ie += 1
    return ib,ie

def parameter_set2(sign_dist :float) -> 'float, float':
    """
    Set thresholds, thr_f1 and thr_f2, for integrated_line_detection().
    Args:
        sign_dist: indicating max_height/abs(min_height) 
    Returns:
        thr_f1: threshold for emissional lines
        thr_f2: threshold for absortion lines
    """
    if sign_dist > 10.0: 
        thr_f1 = 1.5   # very sensitive for mean_height in positive side
        thr_f2 = 3
    elif sign_dist > 2.0:
        thr_f1 = 2.5   # a little sensitive in positive side
        thr_f2 = 3
    elif sign_dist > 0.5:
        thr_f1 = 2.5   # a little sensitive in both sides
        thr_f2 = 2.5
    elif sign_dist > 0.1:
        thr_f1 = 3
        thr_f2 = 2.5   # a little sensitive in negative side
    else:
        thr_f1 = 3
        thr_f2 = 1.5   # very sensitive for mean_height in negative side
    return(thr_f1,thr_f2)

def integrated_line_detection(sp_bl:np_signal,sigma:float,signal:np_signal,coeff:np_signal) ->line_list:
    """
    Detect wide lines from a baseline-subtracted signal using zero-crossings of the first derivative of Gaussian average.
    Qualification check is made by using the second derivative and baseline-subtracted signal.
    Args:
        sp_bl: np.ndarray representing a baseline-subtracted signal
        sigma: Gaussian parameter used for Gaussian averaging
        signal: np.ndarray representing the first floor derivative of Gaussian average of sp_bl
        coeff: np.ndarray representing the second floor derivative of Gaussian average of sp_bl
    Requirements for wide lines:
      (mean_g > thr_f*sigma_sp) or (max_g > thr_g*sigma_sp) or (area_g > thr_h*sigma_sp) or (prod_coeff > thr_fgh)   #emissional
      (mean_g < -thr_f*sigma_sp) or (min_g < -thr_g*sigma_sp) or (area_g > thr_h*sigma_sp) or (prod_coeff > thr_fgh) #absorption
    where mean_g = np.mean(sp_bl[ib:ie]) if ie > ib+2 else 0
          max_g = np.max(sp_bl[ib:ie])
          area_g = mean_g *min(ie-ib,100) #if mean_g > 1.0 else 0
          prod_coeff = (mean_g * max_g * area_g)/sigma_sp**3
    Returns:
        line_list: A list of list representing peak, start and end indices of spectral lines. The indices of 
                    lines are in the order of, e.g., [[peak1, start1, end1], ..., [peakN, startN, endN]].
    """
    global sigma_sp, Gaussian_sp_bl,thr_c,thr_f1,thr_f2,thr_g1,thr_h,thr_fgh,sign_dist
    global min_X,max_X
    global median_iw
    k_edge = int(sigma * 3)
    ksize= 2 * k_edge + 1
    _dg1 = np.array(derivative_of_gaussian(ksize,sigma))
    _cf1 = np.array(second_floor_derivative_of_gaussian(ksize,sigma))

    #print(sp_bl[min_X:max_X].shape, _cf2.shape, np.ma.convolve(sp_bl[min_X:max_X], _cf2).shape)
    signal[min_X:max_X] = np.ma.convolve(sp_bl[min_X:max_X], _dg1)[k_edge:-k_edge]
    coeff[min_X:max_X] = np.ma.convolve(sp_bl[min_X:max_X], _cf1)[k_edge:-k_edge]
    std_coeff = np.std(coeff[min_X:max_X])
    coeff[min_X:max_X] /= std_coeff
    zero_crossings = np.where(np.diff(np.sign(signal[min_X:max_X])))[0]     # Simple implementation of zero-crossings
    zero_crossings += min_X
    for j in range(len(zero_crossings)):
        i = zero_crossings[j]
        if abs(signal[i+1]) < abs(signal[i]):       # The nearer point should be selected for the following processings
            i += 1
    if Gaussian_sp_bl:                         # when sp_bl is noisy. Gaussian average is used for adjusting edges
        k_edge2 = 1
        g_ave2 = np.ma.arange(sp_bl.shape[0], dtype=np.float64)
        g_ave2[min_X:max_X] = gaussian_average(sp_bl[min_X:max_X],k_edge2)
        sp_bl_a = g_ave2                       # Gausian average is used
        median_iw = 1
        thr_g1 = 4.5
    else:
        sp_bl_a = sp_bl                        # original signal is used
        median_iw = 0
        thr_g1 = 4.0
    thr_f1,thr_f2 = parameter_set2(sign_dist)
    print('sign_dist,thr_f1,thr_f2',sign_dist,thr_f1,thr_f2)
    print('thr_c,f1,f2,g1,h,fgh',thr_c,thr_f1,thr_f2,thr_g1,thr_h,thr_fgh)
    first_spbl = sp_bl[min_X]
    detected_lines = []
    ib_lim = min_X
    ie_lim = max_X
    last_registered = [-1, -1, 0]
    for j in range(len(zero_crossings)):
        i = zero_crossings[j]
        if (i > last_registered[1] and i < last_registered[2]):
            #print ('last_registered',i)
            continue
        emissional = (signal[i] > signal[i+1])
        if emissional and (-coeff[i] > thr_c):
            ib, ie = find_edges_e(i, sp_bl_a, ib_lim, ie_lim)
            if ib != ie:                            # Select a wide line by mean, max and area of sp_bl[ib:ie]
                mean_g = np.mean(sp_bl[ib:ie]) if ie > ib+2 else 0    # mean_g is effective when ie > 1b + 2
                thr_f = thr_f1
                thr_g = thr_g1
                if sign_dist > 2:        # thr_f and thr_g are tuned by sign_dist and ie-ib
                    if ie > ib + 10:
                        thr_f -= 0.2
                        thr_g -= 1.0
                    elif ie > ib + 5:
                        thr_f -= 0.1
                max_g = np.max(sp_bl[ib:ie])
                area_g = mean_g *min(ie-ib,100) #if mean_g > 1.0 else 0
                prod_coeff = (mean_g * max_g * area_g)/sigma_sp**3
                if (mean_g > thr_f*sigma_sp) or (max_g > thr_g*sigma_sp) or (area_g > thr_h*sigma_sp) or (prod_coeff > thr_fgh):
                    ic = ib + np.argmax(sp_bl[ib:ie])  #(ib+ie)//2
                    detected_lines.append([ic,ib,ie])
                    last_registered = [ic,ib,ie]
        elif (not emissional) and (coeff[i] > thr_c):
            ib, ie = find_edges_a(i, sp_bl_a, ib_lim, ie_lim)
            if ib != ie:                          # Select a wide line by mean, max and area of sp_bl[ib:ie]
                mean_g = np.mean(sp_bl[ib:ie]) if ie > ib+2 else 0
                thr_f = thr_f2
                thr_g = thr_g1
                if sign_dist < 0.5:        # thr_f and thr_g are tuned by sign_dist and ie-ib
                    if ie > ib + 10:
                        thr_f -= 0.2
                        thr_g -= 1.0
                    elif ie > ib + 5:
                        thr_f -= 0.1
                min_g = np.min(sp_bl[ib:ie])
                area_g = -mean_g * min(ie-ib,100) if -mean_g > 1.0 else 0
                prod_coeff = (mean_g * min_g * area_g)/sigma_sp**3
                if (mean_g < -thr_f*sigma_sp) or (min_g < -thr_g*sigma_sp) or (area_g > thr_h*sigma_sp) or (prod_coeff > thr_fgh):
                    ic = ib + np.argmin(sp_bl[ib:ie])  #(ib+ie)//2
                    detected_lines.append([ic,ib,ie])
                    last_registered = [ic,ib,ie]
    return(detected_lines)

def make_g_ave(sp_bl:np_signal, sigma:float, g_ave:np_signal):
    """
    Make Gaussian average of a given signal.
    Args:
        sp_bl: baseline-subtracted spectrum
        sigma: parameter for Gaussian averaging
        g_ave: Gaussian average of sp_bl is made in this np.ndarray
    """
    k_edge = int(sigma * 3)
    ksize= 2 * k_edge + 1
    # Prepare kernels of Gaussian and Gaussian derivatives
    _g1 = np.array(gaussian(ksize,sigma))
    # Make Gaussian average and its derivatives
    g_ave[min_X:max_X] = np.ma.convolve(sp_bl[min_X:max_X], _g1)[k_edge:-k_edge]
    return

def merge_detected_lines(lines_lists :List[line_list]) ->line_list:
    """
    Merge sorted lists generated by narrow_line_detection() and integrated_line_detection().
    Args:
        lines_list: list of line lists generated by narrow_line_detection() and integrated_line_detection()
    Return:
        'line list': merged list of lines
    """
    num_lists = len(lines_lists)
    merged_lines_list = [] if num_lists == 0 else copy.copy(lines_lists[num_lists-2])
    if num_lists > 1:
        for i in range(1,num_lists-1):              # merge line lists generated by narrow_line_detection()
            ii = num_lists - i-2
            jmax = len(lines_lists[ii])             # index of the new line list
            mmax = len(merged_lines_list)           # index of the merged line list
            j = 0
            m = 0
            #print(i,ii,m,mmax,j,jmax)
            while j < jmax:                        # while loop is used for easy implementation
                #print(i,ii,m,mmax,j)
                if m == mmax:
                    for jt in range(j,jmax):                           # append the rest of the line lists
                        merged_lines_list.append(lines_lists[ii][jt])
                    break
                k = lines_lists[ii][j][0]
                km = merged_lines_list[m][0]
                #print(k,km)
                if k < km-1:                                           # new line appears before the m-th line
                    merged_lines_list.insert(m,lines_lists[ii][j])
                    m += 1
                    mmax += 1
                    j += 1
                elif k >= km-1 and k <= km+1:                        # same line appears
                    if 1:                                          #_#_# if 1: the m-th line is replaced by the new line
                        merged_lines_list[m]=lines_lists[ii][j]
                    m += 1
                    j += 1
                else: # elif k > km+1:
                    while k > merged_lines_list[m][0]+1 and m <= mmax-1:  # skip merged lines to the appropreate position
                        m += 1
                        if m == mmax:
                            break
            #print('mdl',i,ii,merged_lines_list)
        ii = num_lists - 1                            # Finally, lines detected by integrated_line_detection() are merged.
        jmax = len(lines_lists[ii])
        mmax = len(merged_lines_list)
        j = 0
        m = 0
        while j < jmax:
            if m == mmax:
                for jt in range(j,jmax):
                    merged_lines_list.append(lines_lists[ii][jt])
                break
            k = lines_lists[ii][j][0]
            km = merged_lines_list[m][0]
            if k < km:
                merged_lines_list.insert(m,lines_lists[ii][j])
                m += 1
                mmax += 1
                j += 1
            elif k == km:                                          # if peak positions are same
                if lines_lists[ii][j] != merged_lines_list[m]:       # the m-th line is replaced by the new (wide) line.
                    merged_lines_list.insert(m,lines_lists[ii][j])
                    m += 1
                    mmax += 1
                j += 1
            else: # elif k > km:
                while k > merged_lines_list[m][0] and m <= mmax-1:  # skip merged lines to the appropreate position
                    m += 1
                    if m == mmax:
                        break
        #print('mdl',i,ii,merged_lines_list)
    return(merged_lines_list)

def pipeline_format_lines(lines_merged :line_list) ->ranges:
    """
    Convert a line list to a list in pipeline format.
    
    Args:
        lines_merged: line_list
    Return:
        ranges: A list of start and end indices of spectral lines. The indices of 
                    lines are in the order of, e.g., [start1, end1, ..., startN, endN].        
    """
    num_list = len(lines_merged)
    formatted_list = [] if num_list == 0 else copy.copy(lines_merged[0][1:])
    if num_list > 1:
        for i in range(1,num_list):
            new_member = lines_merged[i][1:3]
            last_member = formatted_list[-2:]
            #print(new_member,last_member)
            if last_member[0] > new_member[0]:
                formatted_list.insert(-2,new_member[0])
                formatted_list.insert(-2,new_member[1])
            elif last_member == new_member:
                continue
            else:
                formatted_list.extend(new_member)
            #formatted_list.append(new_member[1])
    return(formatted_list)

def draw_graph_gmr(_spectrum:np_signal,baseline,_spectrum_bl:np_signal,signal:np_signal,
                   coeff:np_signal,g_ave:np_signal,lines_detected:List[line_list],
                   lines_merged:line_list,sgzx_list:List[int],mean_level:np_signal,cut_level:np_signal):
    """
    Draw graphs when Draw_graph == True.
    This is not used in the pipeline.
    """
    import matplotlib.pyplot as plt
    global thr_c,thr_d,thr_f1,thr_f2,thr_rmg,gm_param,sigma_sp
    global dmax,min_X,max_X
    global Zoom_in, Show_details, Show_each, Show_label,Savefig_only_detected_lines
    X = np.ma.arange(dmax)
    sgzxmax = len(sgzx_list)
    if 1:
        sgzxmax += 1
    str1 = format(Baseline_estimation,'01d')
    str1a = format(Baseline_inclination,'01d')
    str2c = format(thr_c,'3.2f')
    str2d = format(thr_d,'3.2f')
    str2f1 = format(thr_f1,'3.2f')
    str2f2 = format(thr_f2,'3.2f')
    str3a = format(thr_rmg,'3.2f')
    str3b = format(gm_param,'3.1f')
    str4 = format(Show_each,'01d')
    opt_sigma = '('
    for sgzx in range(sgzxmax-1):
        if sgzx > 0 :
            opt_sigma += ','
        opt_sigma += format(sgzx_list[sgzx],'3.2f')
    opt_sigma += ')'
    resultfile='gm_result_'+data_file+'_('+str1+str1a+'_'+str2c+','+str2d+','+str2f1+','+str2f2+','+str3a+','+str3b+')-'+opt_sigma+'-'+str4+'.png'
    plt.style.use("seaborn-darkgrid")
    if Show_details and Show_each == 0:
        plt.rcParams["figure.figsize"] = [20, 20]#[20,20]#ax.set_box_aspect(0.5)  # 0.2     1
    else:
        plt.rcParams["figure.figsize"] = [20, 6]#[20, 6] [20,200]#ax.set_box_aspect(0.5)  # 0.2     1
    parameters = {'axes.labelsize': 25,'axes.titlesize': 35,'xtick.labelsize':20,'ytick.labelsize':20}
    if Show_details and Show_each == 0:
        fig, ax = plt.subplots(sgzxmax+2, 1)
    else:
        fig, ax = plt.subplots(1, 1)

    #print(str(fig), str(ax[0]))
    if Zoom_in == 1:
        peak_i = int((min_X+max_X)/2)
        max_line_height = 0
        for sgzx in range(sgzxmax):
            for j in range(len(lines_detected[sgzx])):
                i = lines_detected[sgzx][j][0]
                if _spectrum_bl[i] > max_line_height:
                    max_line_height = _spectrum_bl[i]
                    peak_i = i
        min_Xd=max(min_X,peak_i-250)
        max_Xd=min(max_X,peak_i+250)
    elif Zoom_in == 0:
        min_Xd=min_X
        max_Xd=max_X  # max_X - 30
    else:
        rate1=0.15   #0.40
        rate2=0.4    #0.85
        min_Xd=int(min_X*(1-rate1)+max_X*rate1)
        max_Xd=int(min_X*(1-rate2)+max_X*rate2)
    if Show_details and Show_each == 0:
        ax[0].plot(X[min_Xd:max_Xd], _spectrum[min_Xd:max_Xd],c="darkgray")
        ax[0].plot(X[min_Xd:max_Xd], baseline[min_Xd:max_Xd], c="black")
        ax[0].plot(X[min_Xd:max_Xd], baseline[min_Xd:max_Xd]+sigma_sp, c="lightgreen")    # t_param/gm_param
        ax[0].plot(X[min_Xd:max_Xd], baseline[min_Xd:max_Xd]-sigma_sp, c="lightgreen")
    elif not Show_details :
        if Show_label:
            plt.xlabel(resultfile)
        plt.plot(X[min_Xd:max_Xd], baseline[min_Xd:max_Xd], c="black")  #"black"  "red"
        plt.plot(X[min_Xd:max_Xd], baseline[min_Xd:max_Xd]+sigma_sp, c="lightgreen")    # t_param/gm_param
        plt.plot(X[min_Xd:max_Xd], baseline[min_Xd:max_Xd]-sigma_sp, c="lightgreen")
        plt.plot(X[min_Xd:max_Xd], _spectrum[min_Xd:max_Xd],c="darkgray")
    if Show_details:
        print('Show_each',Show_each)
        if Show_each == 0:
            ax[sgzxmax+1].plot(X[min_Xd:max_Xd], _spectrum[min_Xd:max_Xd],c="gray")
            for sgzx in range(sgzxmax):
                if 1:
                    std_sig = np.std(signal[sgzx,min_X:max_X])
                    signal[sgzx,min_X:max_X] /= std_sig
                ax[sgzx+1].plot(X[min_Xd:max_Xd], coeff[sgzx,min_Xd:max_Xd]*10,c="green")
                ax[sgzx+1].plot(X[min_Xd:max_Xd], signal[sgzx,min_Xd:max_Xd]*10,c="orange")
                ax[sgzx+1].plot(X[min_Xd:max_Xd], g_ave[sgzx,min_Xd:max_Xd],c="brown")
                ax[sgzx+1].plot(X[min_Xd:max_Xd], _spectrum_bl[min_Xd:max_Xd],c="black")
                #print('gzx,len(lines_detected)',sgzx,len(lines_detected[sgzx]))
                jmax = len(lines_detected[sgzx])
                for j in range(jmax):
                    #print('sgzx,j,len(lines_detected)',sgzx,j,len(lines_detected[sgzx]))
                    i=lines_detected[sgzx][j][0]
                    ib=lines_detected[sgzx][j][1]
                    ie=lines_detected[sgzx][j][2]
                    #print('i,ib,ie',i,ib,ie,min_Xd,max_Xd)
                    if i>=min_Xd and i<max_Xd:
                        #print('green line1')
                        #ax[0].plot([i, i],[baseline[i],_spectrum[i]] , c="black")
                        ax[sgzx+1].plot([i, i],[0,_spectrum_bl[i]] , c="blue")
                        if sgzx < sgzxmax-1:
                            #print('graph',sgzx,sgzxmax-1)
                            ax[sgzx+1].plot([i, i],[0,signal[sgzx,i]] , c="blue")
                        if ib>=min_Xd:
                            ax[sgzx+1].plot([ib, ib],[0,_spectrum_bl[ib]] , c="green")
                        #print('green line3')
                        if ie<max_Xd:
                            ax[sgzx+1].plot([ie, ie],[0,_spectrum_bl[ie]] , c="green")
                        #print('green line3')
                        ax[sgzx+1].plot([max(ib,min_Xd), min(ie,max_Xd-1)],[0,0] , c="red", linewidth=4)
                        #ax[0].plot([max(ib,min_Xd), min(ie,max_Xd-1)],[baseline[max(ib,min_Xd)],baseline[min(ie,max_Xd-1)]] , c="yellow")
            print ('mean_level',mean_level,len(mean_level))
            print ('cut_level',cut_level,len(cut_level))
            for icut in range(len(cut_level)):
                ax[sgzxmax+1].plot(X[min_Xd:max_Xd], X[min_Xd:max_Xd]*0+cut_level[icut],c="blue", linewidth=0.5)
            for imean in range(len(mean_level)):
                ax[sgzxmax+1].plot(X[min_Xd:max_Xd], X[min_Xd:max_Xd]*0+mean_level[imean],c="red", linewidth=0.5)
        elif Show_each < 5:
            sgzx = Show_each -1
            if 1:
                std_sig = np.std(signal[sgzx,min_X:max_X])
                signal[sgzx,min_X:max_X] /= std_sig
            plt.plot(X[min_Xd:max_Xd], coeff[sgzx,min_Xd:max_Xd]*10,c="green")
            plt.plot(X[min_Xd:max_Xd], signal[sgzx,min_Xd:max_Xd]*10,c="orange")
            plt.plot(X[min_Xd:max_Xd], g_ave[sgzx,min_Xd:max_Xd],c="brown")
            plt.plot(X[min_Xd:max_Xd], _spectrum_bl[min_Xd:max_Xd],c="black")

            #print('gzx,len(lines_detected)',sgzx,len(lines_detected[sgzx]))
            jmax = len(lines_detected[sgzx])
            for j in range(jmax):
                #print('sgzx,j,len(lines_detected)',sgzx,j,len(lines_detected[sgzx]))
                i=lines_detected[sgzx][j][0]
                ib=lines_detected[sgzx][j][1]
                ie=lines_detected[sgzx][j][2]
                #print('i,ib,ie',i,ib,ie,min_Xd,max_Xd)
                if i>=min_Xd and i<max_Xd:
                    #print('green line1')
                    #ax[0].plot([i, i],[baseline[i],_spectrum[i]] , c="black")
                    plt.plot([i, i],[0,_spectrum_bl[i]] , c="blue")
                    if sgzx < sgzxmax-1:
                        #print('graph',sgzx,sgzxmax-1)
                        plt.plot([i, i],[0,signal[sgzx,i]] , c="blue")
                    if ib>=min_Xd:
                        plt.plot([ib, ib],[0,_spectrum_bl[ib]] , c="green")
                    #print('green line3')
                    if ie<max_Xd:
                        plt.plot([ie, ie],[0,_spectrum_bl[ie]] , c="green")
                    #print('green line3')
                    plt.plot([max(ib,min_Xd), min(ie,max_Xd-1)],[0,0] , c="red", linewidth=4)
                    #ax[0].plot([max(ib,min_Xd), min(ie,max_Xd-1)],[baseline[max(ib,min_Xd)],baseline[min(ie,max_Xd-1)]] , c="yellow")
        else:
            print ('Show_each5:mean_level',mean_level,len(mean_level))
            print ('Show_each5:cut_level',cut_level,len(cut_level))
            plt.plot(X[min_Xd:max_Xd], _spectrum[min_Xd:max_Xd],c="gray")
            for imean in range(len(mean_level)):
                plt.plot(X[min_Xd:max_Xd], X[min_Xd:max_Xd]*0+mean_level[imean],c="red", linewidth=0.5)
            for icut in range(len(cut_level)):
                plt.plot(X[min_Xd:max_Xd], X[min_Xd:max_Xd]*0+cut_level[icut],c="blue", linewidth=0.5)
    for j in range(len(lines_merged)):
        #print('sgzx,j,len(lines_merged)',sgzx,j,len(lines_merged))
        i=lines_merged[j][0]
        ib=lines_merged[j][1]
        ie=lines_merged[j][2]
        #print('i,ib,ie',i,ib,ie)
        if i>=min_Xd and i<max_Xd:
            if Show_details and Show_each == 0:
                ax[0].plot([i, i],[baseline[i],_spectrum[i]] , c="blue")
                ax[0].plot([max(ib,min_Xd), min(ie,max_Xd-1)],[baseline[max(ib,min_Xd)],baseline[min(ie,max_Xd-1)]] , c="red", linewidth=4)  ##temp
            elif not Show_details:
                plt.plot([i, i],[baseline[i],_spectrum[i]] , c="blue")
                plt.plot([max(ib,min_Xd), min(ie,max_Xd-1)],[baseline[max(ib,min_Xd)],baseline[min(ie,max_Xd-1)]] , c="red", linewidth=4)  ##temp
    print(resultfile)
    if not Savefig_only_detected_lines or len(lines_merged) > 0:
        plt.savefig(resultfile)
    else:
        plt.close()
    #plt.close()
    return

def local_sigma(_spectrum:np_signal,gaussian_sgm:float) -> 'float,float':
    """
    local_std is calculated for Gaussian-subtracted spectrum data.
    
    Args:
        _spectrum: a given spectrum data
        gaussian_sgm: sigma parameter of Gaussian filter
    Return:
        std is calculated after Gaussian subtraction
        std of Gausian average is also provided
    """
    global min_X,max_X
    delta=gaussian_sgm*3
    local_std=np.ma.std(_spectrum[min_X+delta:max_X-delta]-gaussian_average(_spectrum,gaussian_sgm)[min_X+delta:max_X-delta])
    ga_std=np.ma.std(gaussian_average(_spectrum,gaussian_sgm)[min_X+delta:max_X-delta])
    return(local_std,ga_std)

def iterative_2s_exclusions(_spectrum:np_signal,mean_level:np_signal,cut_level:np_signal):
    """
    Provide rough estimations of mean and std of Baseline by Iterative 2-sigma exclusions.
    
    Args:
        _spectrum: a given spectrum data
        mean_level: mean_level table
        cut_level: cut_level table
    Algorithm:
      *0 Regard the original set as SET
      *1 Calculate mean and std of SET
      *2 Devide SET into Upperset(more than mean+2std) and Lowerset(the rest)
      *3 Calculate means and stds in the two sets
      *4 Calculate relative_mean_gap = (mean_upper - mean_lower)/ std_lower
      *5 If relative_mean_gap < thr(2.25), mean_lower and std_lower indicate rough estimation of MEAN and STD.
         Otherwise, regard the Lowerset as SET, and goto *2
    Note:
        The std_lower is used as STD (No correction is made in the current version.)
    """
    global e_std_max, e_std, local_std
    # Preparations
    #mean_sp = np.ma.mean(_spectrum)                # both-sides-exclusions
    #height_sp = np.ma.max(_spectrum)-mean_sp       # both-sides-exclusions
    #depth_sp = mean_sp - np.ma.min(_spectrum)      # both-sides-exclusions
    sigma_sp = np.ma.std(_spectrum)

    # Main cycle of Iterative 2-sigma exclusions
    _spectrum1 = _spectrum
    for e_std in range(e_std_max-1):
        mean_sp = np.ma.mean(_spectrum1)                # both-sides-exclusions
        height_sp = np.ma.max(_spectrum1)-mean_sp       # both-sides-exclusions
        depth_sp = mean_sp - np.ma.min(_spectrum1)      # both-sides-exclusions
        # update mean_level[e_std] and cut_level[e_std]
        mean_level[e_std]=mean_sp
        if height_sp > depth_sp:                  # Exclude from upper_part
            cut_level[e_std]=mean_sp+sigma_sp*2
            upper_part = np.where(_spectrum1>cut_level[e_std])  # upper_part is selected
            thr_level = 2.0
            while upper_part[0].shape[0] == 0:     # thr_level is tuned, if neccessary
                thr_level -= forced_level_down
                print ('*forced thr_level down1',thr_level)
                cut_level[e_std]=mean_sp+sigma_sp*thr_level
                upper_part = np.where(_spectrum1>cut_level[e_std])
            lower_part = np.where(_spectrum1<=cut_level[e_std])   # lower_part is selected
  
        else:                                      # Exclude from lower part
            cut_level[e_std]=mean_sp-sigma_sp*2
            lower_part = np.where(_spectrum1<cut_level[e_std])    # lower_part is selected
            thr_level = 2.0
            while lower_part[0].shape[0] == 0:      # thr_level is tuned, if neccessary
                thr_level -= forced_level_down
                print ('*forced thr_level down2',thr_level)
                cut_level[e_std]=mean_sp-sigma_sp*thr_level
                lower_part = np.where(_spectrum1<cut_level[e_std])
            upper_part = np.where(_spectrum1>=cut_level[e_std])    # upper_part is selected

        # Calculate upper_mean and lower_mean
        upper_mean = np.ma.mean(_spectrum1[upper_part])
        lower_mean = np.ma.mean(_spectrum1[lower_part])

        # Calculate relative_mean_gap
        mean_gap = upper_mean - lower_mean
        relative_mean_gap = mean_gap/sigma_sp
        print('statistics0:',e_std,mean_gap,sigma_sp,relative_mean_gap,mean_level[e_std],cut_level[e_std])
        
        # Update mean_sp and sigma_sp
        if height_sp > depth_sp:
            sigma_sp = np.ma.std(_spectrum1[lower_part])
            mean_sp = lower_mean
        else:
            sigma_sp = np.ma.std(_spectrum1[upper_part])
            mean_sp = upper_mean

        # validation by local_std_check
        local_std_check_invalid = (sigma_sp > 2 * local_std)
        if relative_mean_gap <= thr_rmg and not local_std_check_invalid:      # thr_tmg = 2.25  # relative_mean_gap converges to 2.25
            mean_level[e_std+1]=mean_sp
            break
        if local_std_check_invalid and (e_std == e_std_max-2):                   # at final iteration
            print ('**final_local_std_check_invalid')

        # _spectrum1 is updated for the next iteration (important)
        if height_sp > depth_sp:
            _spectrum1 = _spectrum1[lower_part]             # This substitution is important for convergence
        else:
            _spectrum1 = _spectrum1[upper_part]             # This substitution is important for convergence
        #print('statistics1:',e_std,mean_gap,sigma_sp,relative_mean_gap)
    return(sigma_sp,mean_sp,e_std,_spectrum1)

def optimize_sigma(sp:np_signal) -> float:
    global dmax, min_X, max_X
    sigma_gap = 2 ** 0.1 # 2**0.2   2**0.5
    sigma_num = 80  # 60
    sigma_first = 2.0  # 
    sigma_list = []
    for i in range(sigma_num):
        sigma_list.append(sigma_first*sigma_gap**i)
    kmax=len(sigma_list)

    dmax0 = max_X - min_X
    _gaussian = np.ma.arange(kmax*dmax0,dtype=float).reshape(kmax,dmax0)
    mse = np.ma.arange(kmax,dtype=float)
    for kk in range(kmax):
        sigma = sigma_list[kk]
        k_edge = int(sigma * 3)
        ksize= 2 * k_edge + 1
        _g = np.array(gaussian(ksize,sigma))      # normalization
        _g_total = np.sum(_g)
        _g /= _g_total
        #print(np.sum(_g))

        #_gaussian[kk,:] = np.ma.convolve(sp, _g, propagate_mask=False)[k_edge:-k_edge]  # propagate_mask = False version
        _gaussian[kk,:] = np.ma.convolve(sp, _g)[k_edge:-k_edge]

        k_edge_left = k_edge
        k_edge_right = - k_edge - 1
        #print(k_edge_left,k_edge_right,sigma)
        for j in range(k_edge_left):
            _gaussian[kk,j]=_gaussian[kk,k_edge_left]
        for j in range(-k_edge_right):
            _gaussian[kk,-1-j]=_gaussian[kk,k_edge_right]
        mse[kk] = np.average((_gaussian[kk,:] - sp)**2)/np.log(sigma)
    best_k = 0
    best_est = 10**20
    for kk in range(10,kmax-10):    # 20 ???
        if best_est > mse[kk]:
            best_est = mse[kk]
            best_k = kk
            sigma = sigma_list[kk]
        #print (sigma,mse[kk]*np.log(sigma),mse[kk],best_est,best_k)
        #print(len(_spectrum),len(_gaussian))
        #print (signal)
    print ('best_k,sigma,best_est',best_k,sigma,best_est)
    return(sigma)

def line_finder(sp:np_signal, sp_mask:'np.ndarray[bool]' = False) -> ranges:
    """Line finder based on Gaussian filter along with baseline estimator using Geman-McClure function.
    This function consists of five subtasks as follows:
        0)Rough estimation of mean and std of Baseline by Iterative 2-sigma exclusions (iterative_2s_exclusions())
        1)Baseline estimation by Geman-McClure function: (lf_gmb.py)
        2)Integrated line detection by zero-crossings of first derivative of Gaussian average of SIGNAL_BL: (integrated_line_detection())
        3)Narrow line detection by zero-crossings of the first derivative of Gaussian average on SIGNAL_BL: (narrow_line_detection())
    
    Returns:
        ranges: A list of start and end indices of spectral lines. The indices of 
                    lines are in the order of, e.g., [start1, end1, ..., startN, endN].
    """
    global sigma_sp, local_std, ga5_std, gs_param, optimum_sigma, Gaussian_sp_bl, thr_rmg, sign_dist
    global dmax, min_X, max_X, max_height, min_height
    global Draw_graph, Baseline_estimation, Baseline_inclination, Gaussian_subtraction, Gaussian_enable
    dmax = len(sp)
    _spectrum = np.ma.array(sp,mask=sp_mask)

    # effective signal range is set to [min_X max_X]
    min_X = 0
    max_X = dmax - 1          # SOS
    if _spectrum.mask.shape != ():        ### even when == (), this code works
        while _spectrum.mask[min_X] :     ### otherwise, min_X and max_X are adjusted to mask data
            if min_X == dmax - 1:
                break
            min_X += 1
        while _spectrum.mask[max_X] :     # SOS
            if max_X == 0:
                break
            max_X -= 1
    print('min_X,max_X',min_X,max_X)
    if (min_X > max_X):
        print ('No effective data')
        return [],0,0

    # Calculate local_std
    gaussian_sgm=5
    local_std,ga5_std = local_sigma(_spectrum,gaussian_sgm)
    print ('**local_std,ga5_std',local_std,ga5_std)

    ## Iterative 2-sigma exclusions
    mean_level = np.arange(e_std_max,dtype=float)
    cut_level = np.arange(e_std_max,dtype=float)
    sigma_sp,mean_sp,k_std,_spectrum1 = iterative_2s_exclusions(_spectrum,mean_level,cut_level)
    print('sigma_sp,mean_sp',sigma_sp,mean_sp)
    
    # Baseline estimation by Geman-McClure function
    baseline = np.ma.arange(dmax,dtype=float)
    X_ = np.ma.arange(dmax).reshape(-1,1)
    
    # Selection of Baseline_estimation or Gaussian_subtraction
    Baseline_estimation = True
    #if (ga5_std < 2.5 * local_std and sigma_sp > gs_param *local_std):
    if Gaussian_enable:
        if (dmax > 256 and sigma_sp > gs_param *local_std):  # gs_param = 1.25
            if ((k_std < 4 and ga5_std > 1.8 * local_std) or (k_std < 10 and ga5_std > 2.0 * local_std)):   # Baseline_estimation works in these cases
                print ('**k_std check')
            else:
                Baseline_estimation = False
        print ('Baseline_estimation', local_std, k_std, sigma_sp/local_std, ga5_std/local_std, Baseline_estimation)
    Gaussian_subtraction = not Baseline_estimation
        
    # Preparation for lfr.GM()
    if Baseline_estimation:               # Baseline_estimation is used for the future alternative, e.g. Gaussian-subtraction
        if Baseline_inclination and (dmax > thr_ss):         # Baseline_inclination is not effective for short spectrum  

            # SLOPE is estimated from mean_left and mean_right
            half_pos = len(_spectrum)//2
            mean_left= np.ma.mean(_spectrum1[:half_pos])
            mean_right=np.ma.mean(_spectrum1[half_pos:])
            relative_pos_gap = 2*(mean_right-mean_left)/sigma_sp
            print ('relative_pos_gap',half_pos,mean_sp,mean_left,mean_right,relative_pos_gap)

            # SLOPE is effective when abs(relative_pos_gap) is not too small
            displacement_effective = (abs(relative_pos_gap) > thr_rpg)
            if displacement_effective:   # in case of inclined baseline
                # Make displacement for inclination compensation  
                displacement = np.ma.arange(dmax,dtype=float)
                #print ('displacement',displacement)
                slope = 2*(mean_right-mean_left)/len(_spectrum)
                mean_displacement =slope*(displacement[min_X]+displacement[max_X-1])/2
                displacement = displacement * slope - mean_displacement
                print ('slope,mean_displacement',slope,mean_displacement)
                # Inclination is compensated by subtracting displacement
                _spectrum2 = _spectrum - displacement
                _spectrum_ = _spectrum2.reshape(-1,1)
            else:                        # in case of non-inclined baseline
                _spectrum_ = _spectrum.reshape(-1,1)
        else:
            displacement_effective = False
            _spectrum_ = _spectrum.reshape(-1,1)
            print ('**horizontal baseline assumed')

        # Set parameters for lfr.GM()
        t_param = 3.0 * sigma_sp
        #d_param = len(_spectrum)//1.5         # when d_param is not effective for lfr.GM, d_param is gradually reduced in lfr.GM
        ycmax = 1
        yc_list = np.ma.arange(ycmax,dtype=float).reshape(-1,1)
        yc_list[0] = mean_sp        # mean_sp is used  for initial value.

        # Instanciation of lfr.GM() along with instanciation of lfr.LinearModel()
        regressor = lfr.GM(t=t_param,g=gm_param, y_list=yc_list, model=lfr.LinearModel(), 
                           metric=lfr.mean_gm_error, fdt=lfr.gm_fd_total, sdt=lfr.gm_sd_total)
        #regressor =lfr.GM(t=t_param, g=gm_param, y_list=yc_list,model=lfr.LinearModel(), loss=lfr.gm_error_loss, metric=lfr.mean_gm_error)
        print ('t,g:',t_param,gm_param)
        #print (X_.shape,_spectrum_.shape)
        
        # Horizintal baseline estimation
        ones = np.ones((len(X_), 1))
        aaa=regressor.fit(X_,_spectrum_,ones)
        #print ('aaa',vars(aaa.model))
        baseline = regressor.predict(X_)[:,0]

        # Inclination is recovered, if neccessary
        if displacement_effective:
            baseline += displacement
        #print ('baseline=',baseline)
    if Gaussian_subtraction:                # SOSGS
        print('Gaussian_subtraction', optimum_sigma)
        sigma_sp = local_std
        optimum_sigma = optimize_sigma(_spectrum[min_X:max_X])
        gs_edge_width = int(optimum_sigma*3.0)
        baseline[min_X:max_X] = gaussian_average(_spectrum[min_X:max_X], optimum_sigma)
        baseline[min_X:min_X+gs_edge_width] = _spectrum[min_X:min_X+gs_edge_width]
        baseline[max_X-gs_edge_width:max_X] = _spectrum[max_X-gs_edge_width:max_X]
    # Baseline-subtracted spectrum is generated
    _spectrum_bl = np.ma.arange(_spectrum.shape[0], dtype=np.float64)
    if Gaussian_subtraction or Baseline_estimation:
        _spectrum_bl[min_X:max_X] = _spectrum[min_X:max_X] -baseline[min_X:max_X]
    else:
        _spectrum_bl[min_X:max_X] = _spectrum[min_X:max_X]
        baseline[min_X:max_X] = 0

    # Line detection scheme 
    ## Preparation for parallel processings
    # sgzx_list is generated
    sgzx_list = []
    if sgzxmax >= 1:
        for ii in range(sgzxmax):
            sgzx_list += [2 ** (ii+1)]
    #print ('sgzx_list',sgzx_list)

    # arangement of g_ave, signal and coeff 
    sgzxmaxp1= sgzxmax + 1
    g_ave = np.ma.arange(sgzxmaxp1*dmax,dtype=float).reshape(sgzxmaxp1,dmax)   # for Graphic use
    signal = np.ma.arange(sgzxmaxp1*dmax,dtype=float).reshape(sgzxmaxp1,dmax)
    coeff = np.ma.arange(sgzxmaxp1*dmax,dtype=float).reshape(sgzxmaxp1,dmax)

    ## Wide line detection
    # setting parameters
    max_height = np.ma.max(_spectrum_bl[min_X:max_X])
    min_height = np.ma.min(_spectrum_bl[min_X:max_X])
    sign_dist = max_height/abs(min_height)
    #print ('sign_dist', np.ma.max(_spectrum_bl[min_X:max_X]),np.ma.min(_spectrum_bl[min_X:max_X]), sign_dist)
    Gaussian_sp_bl = (max_height/sigma_sp < thr_Gsb)
    print ('Gaussian_sp_bl',Gaussian_sp_bl,max_height/sigma_sp)

    ## select sigma_p
    sigma_p = sgzx_list[0]

    ## call integrated_line_detection)
    wide_line_list = integrated_line_detection(_spectrum_bl,sigma_p,signal[sgzxmax,:],coeff[sgzxmax,:])

    ## Make wl_flag from wide_line_list
    wl_flag= np.arange(dmax,dtype='int')
    wl_flag[min_X:max_X] = 0
    for il in range(len(wide_line_list)):
        ib = wide_line_list[il][1]
        ie = wide_line_list[il][2]
        wl_flag[ib:ie] = 1

    ## Narrow line detection by narrow_line_detection()
    lines_detected = []

    # Parallel narrow line detection with changing sigma
    for sgzx in range(sgzxmax):
        #setting parameters
        sigma = sgzx_list[sgzx]
        wl_analysis = (sgzx >= sgzxmax - wl_mask_index)       # wl_analysis is controled by wl_mask_index.
        
        # call narrow_line_detection()
        new_lines = narrow_line_detection(_spectrum_bl,sigma,signal[sgzx,:],coeff[sgzx,:],wl_flag,wl_analysis)

        # detected line_list is appended to lines_detected 
        lines_detected.append(new_lines)
        print ('lines_detected',sgzx,len(lines_detected[sgzx]),lines_detected[sgzx])

    # wide_line_list is appended to lines_detected
    lines_detected.append(wide_line_list)
    print ('lines_detected2',sgzxmax,len(lines_detected[sgzxmax]),lines_detected[sgzxmax])

    # lines_detected(list of line_lists) is merged to a list of lines named lines_merged
    lines_merged = merge_detected_lines(lines_detected)
    print ('lines_merged',len(lines_merged),lines_merged)

    # lines_final is generated from lines_merged due to pipeline_format
    lines_final = pipeline_format_lines(lines_merged)
    #print ('lines_final',len(lines_final)/2,lines_final)
    if Draw_graph:
        for sgzx in range(sgzxmax):
            sigma = sgzx_list[sgzx]
            make_g_ave(_spectrum_bl,sigma,g_ave[sgzx,:])
        make_g_ave(_spectrum_bl,sigma_p,g_ave[sgzxmax,:])
        draw_graph_gmr(_spectrum,baseline,_spectrum_bl,signal,coeff,g_ave,lines_detected,lines_merged,
                       sgzx_list, mean_level[0:e_std+2], cut_level[0:e_std+1])
    return(lines_final,baseline[0],baseline[0]/sigma_sp)

if __name__ == "__main__":
    Database_selector = 6
    _bl_selector = False
    all_files =True            # if False, hand-made list is used for debugging
    loc_all = 1
    if Database_selector == 0 or Database_selector == 1:
        get_ipython().run_line_magic('cd', 'C:\\Users\\TakeshiShakunaga\\line-forest')
    elif Database_selector == 2:
        get_ipython().run_line_magic('cd', 'C:\\Users\\TakeshiShakunaga\\multi-wide-line')
    elif Database_selector == 3:
        get_ipython().run_line_magic('cd', 'C:\\Users\\TakeshiShakunaga\\weak-wide-line')
    elif Database_selector == 4:
        get_ipython().run_line_magic('cd', 'C:\\Users\\TakeshiShakunaga\\wide-line-at-spw-edge')
    elif Database_selector == 5:
        get_ipython().run_line_magic('cd', 'C:\\Users\\TakeshiShakunaga\\multi_source')
    elif Database_selector == 6:
        get_ipython().run_line_magic('cd', 'C:\\Users\\TakeshiShakunaga\\multi_source2')
    elif Database_selector == 7:
        get_ipython().run_line_magic('cd', 'C:\\Users\\TakeshiShakunaga\\singlepolLW')
    elif Database_selector == 8:
        get_ipython().run_line_magic('cd', 'C:\\Users\\TakeshiShakunaga\\VenusLW')
    if Database_selector == 0:
        if _bl_selector:
            file_name_list_original = ['simplegrid_stage11_spw17_field1','simplegrid_stage11_spw19_field1',
                                       'simplegrid_stage11_spw21_field1','simplegrid_stage11_spw23_field1']
        else:
            file_name_list_original = ['simplegrid_stage9_spw17_field1','simplegrid_stage9_spw19_field1',
                                       'simplegrid_stage9_spw21_field1','simplegrid_stage9_spw23_field1']
    elif Database_selector == 1:
        if _bl_selector:
            file_name_list_original = ['simplegrid_stage11_spw25_field1','simplegrid_stage11_spw27_field1',
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
    elif Database_selector == 3 or Database_selector == 4:
        if _bl_selector:
            file_name_list_original = ['simplegrid_stage11_spw17_field1','simplegrid_stage11_spw19_field1',
                                       'simplegrid_stage11_spw21_field1','simplegrid_stage11_spw23_field1']
        else:
            file_name_list_original = ['simplegrid_stage9_spw17_field1','simplegrid_stage9_spw19_field1',
                                       'simplegrid_stage9_spw21_field1','simplegrid_stage9_spw23_field1']
    elif Database_selector == 5:
        if _bl_selector:
            file_name_list_original = ['simplegrid_stage11_spw23_field3']
        else:
            file_name_list_original = ['simplegrid_stage9_spw23_field3']
    elif Database_selector == 6:
        if _bl_selector:
            file_name_list_original = ['simplegrid_stage11_spw17_field6','simplegrid_stage11_spw19_field6']
        else:
            file_name_list_original = ['simplegrid_stage9_spw17_field6','simplegrid_stage9_spw19_field6']
    elif Database_selector == 7:
        if _bl_selector:
            file_name_list_original = ['simplegrid_stage11_spw19_field7']
        else:
            file_name_list_original = ['simplegrid_stage9_spw19_field7']
    elif Database_selector == 8:
        if _bl_selector:
            file_name_list_original = ['simplegrid_stage11_spw17_field1','simplegrid_stage11_spw23_field1']
        else:
            file_name_list_original = ['simplegrid_stage9_spw17_field1','simplegrid_stage9_spw23_field1']
    file_name_list = file_name_list_original
    if not all_files:                              # if 1, select one spw field
        file_name_list = []
        file_name_list.append(file_name_list_original[0])
    for file_name in file_name_list:
        data_file =file_name+'.npz'
        data = np.load(data_file)                         # np.load('data1_17_1.npz')
        #data = np.load(directory_name+data_file)         # np.load('data1_17_1.npz')
        full_spectrum = data['data'][:,:]
        fs_mask = data['mask'][:,:]
        fs = np.ma.array(full_spectrum,mask=fs_mask)
        _spectrum = np.ma.arange(fs.shape[1], dtype=np.float64)
        loc_max = fs.shape[0]
        if loc_all:
            loc_b = 0 #loc_max // 4 #loc_max//4 #//4
            loc_e = loc_max #loc_b + 3 #loc_max // 2 #loc_max // 2 #int(loc_max//2) #loc_max//2 #loc_b + 1
        else:
            loc_b =  120 #51 #139 #72
            loc_e = loc_b + 1 #30  #15
        print('loc_b,loc_e',loc_b,loc_e,loc_max,fs.shape[1])
        base_l = np.arange(loc_e-loc_b, dtype=np.float64)
        base_lr = np.arange(loc_e-loc_b, dtype=np.float64)
        for loc in range(loc_b,loc_e):
            str1 = format(loc,'03d')
            data_file = file_name + '.npz#' + str1
            #_spectrum = fs[loc,:]
            for j in range(_spectrum.shape[0]):
                #_spectrum[j] = np.ma.average(fs[loc,j])
                _spectrum[j] = fs[loc,j]

            ## setting for line_finder()
            if _bl_selector:             # spectrum data before baseline subtraction
                Baseline_estimation = False 
            else:
                Baseline_estimation = True         # lf_gm is called for baseline estimation
            if 1:   # line_finder works for spetrum with mask
                #print (_spectrum.shape,_spectrum.mask.shape)
                lines_final,base_l[loc-loc_b],base_lr[loc-loc_b] = line_finder(_spectrum,_spectrum.mask)
            else:   # line_finder also works for spectrum without mask
                lines_final,base_l[loc-loc_b],base_lr[loc-loc_b] =line_finder(_spectrum)
            print('lines_final',data_file,len(lines_final)/2,lines_final)