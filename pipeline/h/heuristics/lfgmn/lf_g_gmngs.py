#!/usr/bin/env python
# coding: utf-8

IN_PIPELINE : bool = True    # Set this boolean parameter to True 'IN_PIPELINE'.
BOTH_SIDES_EXCLUSIONS :bool = False    # If True, main exclusion side is fixed, and weak excusion is invoked in the reverse side.
GAUSSIAN_ENABLE:bool = False        # Gaussian_subtraction is used when linear baseline is inappropiate.
WL_ANALYSIS : bool = True  # Narrow line analysis is activated in wide line ranges


# Find indices of lines from spectrum data.

import numpy as np
from math import pi, sqrt, exp, log, isnan
import copy
from typing import List, Optional
if IN_PIPELINE:
    from . import lf_gmn as lfr   # bitbucket (pipeline) lf_gmn
    Draw_graph = False
else:
    import lf_gmn as lfr          # jupyternote (version-4.3 uses lf_gmn module)


# <br>
# <br><br>
#     lf_g_gmngs.py (v.4.3)<br><br>
#     This module provides a line finder based on Gaussian filter along with baseline estimator using Geman-McClure function.<br><br>
#     <br><br>
#     line_finder() is a main function of this module, which serves as a line finder for a given spectrum data.<br><br>
#     <br><br>
#     Abstract of line_finder() is as follows:<br><br>
#     0)Rough estimation of mean and std of Baseline by Iterative 2-sigma exclusions: (iterative_2s_exclusions())<br><br>
#     1)Baseline estimation by Geman-McClure function: (lf_gmn.py)<br><br>
#     2)Integrated line detection by zero-crossings of first derivative of Gaussian average of SIGNAL_BL: (integrated_line_detection())<br><br>
#       2.1)Narrow line detection by zero-crossings of the first derivative of Gaussian average on SIGNAL_BL: (narrow_line_detection())<br><br>
#       2.2)Indices of the detected lines are made: (in line_finder())<br>
#

np_signal = 'np.ndarray[float]'
line_list = List[List[int]]
ranges = List[int]
kernel = List[float]
odd = int


# Important parameters

sigma_sp :float          #STD, most important parameter estimated in this module
local_std :float         #local_std
ga5_std:float            #ga5_std
GS_PARAM:float = 1.2     #2.0
optimum_sigma:float       #10.0


# Iterative 2-sigma exclusions

E_STD_MAX = 12          #Maximum iterations of iterative 2-sigma exclusions for estimation of STD and BL
e_std :int
THR_RMG = 2.25          #Main requirement for the estimation termination is relative_mean_gap < THR_RMG.
FORCED_LEVEL_DOWN = 0.1 #When cut_level[est] is not effective in the iterative exclusions, cut_level is reduced FORCED_LEVEL_DOWN


# Baseline estimation by Geman-McClure function

BASELINE_ESTIMATION :bool = True    # If True, baseline estimation is effective.
BASELINE_INCLINATION :bool = True   # If False, horizontal baseline is assumed.
THR_SS = 128                        # Inclination is effective for dmax > THR_SS
THR_RPG = 0.5                       # Inclination is effective when abs(relative_pos_gap) > THR_RPG
GM_PARAM = 4                         # In Geman-McClure function, parameter c is defined by STD/GM_PARAM.

#

Gaussian_subtraction:bool           # Boolen parameter for baseline type selection

# WideLine detection

#
# <br>
#     Requirements for lines used in integrated_line_detection():<br>
#       (mean_line > thr_f*sigma_sp) or (max_line > thr_g*sigma_sp) or (area_line > THR_H*sigma_sp) or (prod3_line > THR_FGH)   #emissional<br>
#       (mean_line < -thr_f*sigma_sp) or (min_line < -thr_g*sigma_sp) or (area_line > THR_H*sigma_sp) or (prod3_line > THR_FGH) #absorption<br>
#     where mean_line = np.mean(sp_bl[ib:ie]) if ie > ib+2 else 0<br>
#           max_line = np.max(sp_bl[ib:ie])<br>
#           area_line = mean_line *min(ie-ib,100)<br>
#           prod3_line = (mean_line * max_line * area_line)/sigma_sp**3<br>
#     when [ib:ie] indicates a range of line candidate.<br>
#

# Threshold parameters and how they are tuned in integrated_line_detection()

THR_E = 0.01          # 0.01, fixed empirically, used in integrated_line_detection()
#
#thr_f : float        # used in (mean_line > thr_f*sigma_sp) for emissional line
                      # this parameter is selected from thr_f1 and thr_f2 and tuned by ie-ib between 1.3 and 3.0
thr_f1 : float        # automatically tuned by sign_dist between 1.5 and 3.0
thr_f2 : float        # automatically tuned by sign_dist between 1.5 and 3.0
#
thr_g : float         # used in (max_line > thr_g*sigma_sp) for emissional line
                      # tuned by sign_dist and ie-ib between 3.5 and 4.5
THR_G0 : float = 4.5  # 4.5, base value of thr_g, fixed empirically
#
THR_H = 40            # used in (area_line > THR_H*sigma_sp) for emissional line
                      # 40, fixed empirically
#
THR_FGH = 100         # used in (prod3_line > THR_FGH) for emissional line
                      # 100, fixed empirically
                      # NOTE: THR_FGH < thr_f * thr_g * thr_h

# Line Width estimation

THR_SPBL = 20.0        # Threshold for determining Gaussian_sp_bl:      Gaussian_sp_bl = (max_height/sigma_sp < THR_SPBL)
Gaussian_sp_bl :bool   # When True, zero-crosings of Median of Gaussian (with sigma=1) of signal_bl is used for edge estimation
                       # Otherwise, zero-crossings of signal_bl is used.
median_iw :int         # global parameter controled by Gaussian_sp_bl
sp_bl_a: np_signal     # signal used for edge detection

# Other global parameters

dmax : int           # length of input spectrum
min_X : int          # effective range of spectrum is [min_x:max_x]
max_X : int          # effective range of spectrum is [min_x:max_x]
max_height : int     # maximum height of signal_bl
min_height : int     # minimum height of signal_bl
sign_dist : int      # automatically set to max_height/abs(min_height), used for tune thr_f1 and thr_f2, in line_finder()
SGZXMAX=2            # 2:

# Parameters for Graphic Option

Draw_graph = True
Savefig_only_detected_lines = False    # True: Save figures if lines are detected   # False: Save all figures
Show_details = False             # False: only Fig-0,  # True: All Figs   # True : only Fig-i
Show_each = 0 # 0 1 2           # 0                   # 0                # i(1..5)
Show_label = True                #effective only when Show_details = False
Zoom_in = 0 # if Zoom_in=1,narrow band arround the highest peak is shown in the graph, if Zoom_in==2, given band.

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
    #median_iw = 0      # SOS
    ib0 = max(ibmin,ib-median_iw)
    ib1 = min(ibmax,ib+median_iw+1)
    return np.ma.median(sig[ib0:ib1])

def narrow_line_detection(sp_bl:np_signal, sigma:float, signal:np_signal, coeff:np_signal, wl_flag:'np.ndarray[int]', WL_ANALYSIS:bool) ->line_list:
    """
    Detect narrow lines from a baseline-subtracted signal using zero-crossings of the first derivative of Gaussian average.
    Qualification check is made by using the second derivative and baseline-subtracted signal.
    Args:
        sp_bl: np.ndarray representing a baseline-subtracted signal
        sigma: Gaussian parameter used for Gaussian averaging
        signal: np.ndarray representing the first floor derivative of Gaussian average of sp_bl
        coeff: np.ndarray representing the second floor derivative of Gaussian average of sp_bl
        wl_flag: np.ndarray[int] reprisenting whether each channel is included in wide-lines
        WL_ANALYSIS: bool representing effectiveness of the narrow-line detection in the wide-line ranges
    Requirements for narrow lines (effective when (not wl_flag[i] or WL_ANALYSIS) == True)
        1) -coeff[i] > THR_E (emission line)       coeff[i] > THR_E (absorption line)
        2) sp_bl[i] > thr_g * sigma_sp            sp_bl[i] < -thr_g * sigma_sp
    Returns:
        line_list: A list of list representing peak, start and end indices of spectral lines. The indices of
                    lines are in the order of, e.g., [[peak1, start1, end1], ..., [peakN, startN, endN]].
    """
    global sigma_sp, THR_E, thr_g, sp_bl_a
    global min_X,max_X,max_height,min_height

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
        dl_on = not wl_flag[i] or WL_ANALYSIS    # dl_on is controled by combination of wl_flag and WL_ANALYSIS
        emissional = (signal[i] > signal[i+1])
        if dl_on and emissional:
            if (-coeff[i] > THR_E and (sp_bl[i] > sigma_sp * thr_g)):          # Qualification by coeff and sp_bl
                if max_height > -min_height:
                    #ib, ie = find_edges_e(i, sp_bl_a, ib_lim, ie_lim)
                    ib = i
                    ie = i+1
                    detected_lines.append([i,ib,ie])
        elif dl_on:  # absorption
            if coeff[i] > THR_E and sp_bl[i] < -sigma_sp * thr_g :                   # Qualification by coeff and sp_bl
                if min_height < -max_height:
                    #ib, ie = find_edges_a(i, sp_bl_a, ib_lim, ie_lim)
                    ib = i
                    ie = i+1
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
        thr_f1 = 1.5   # very sensitive for mean_line in positive side
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
        thr_f2 = 1.5   # very sensitive for mean_line in negative side
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
      (mean_line > thr_f*sigma_sp) or (max_line > thr_g*sigma_sp) or (area_line > THR_H*sigma_sp) or (prod3_line > THR_FGH)   #emissional
      (mean_line < -thr_f*sigma_sp) or (min_line < -thr_g*sigma_sp) or (area_line > THR_H*sigma_sp) or (prod3_line > THR_FGH) #absorption
    where mean_line = np.mean(sp_bl[ib:ie]) if ie > ib+2 else 0
          max_line = np.max(sp_bl[ib:ie])
          area_line = mean_line *min(ie-ib,100) #if mean_line > 1.0 else 0
          prod3_line = (mean_line * max_line * area_line)/sigma_sp**3
    Returns:
        line_list: A list of list representing peak, start and end indices of spectral lines. The indices of
                    lines are in the order of, e.g., [[peak1, start1, end1], ..., [peakN, startN, endN]].
    """
    global sigma_sp, Gaussian_sp_bl,THR_E,thr_f1,thr_f2,thr_g,THR_G0,THR_H,THR_FGH,sign_dist
    global min_X,max_X
    global median_iw, sp_bl_a
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
    else:
        sp_bl_a = sp_bl                        # original signal is used
        median_iw = 0
    thr_f1,thr_f2 = parameter_set2(sign_dist)
    print('sign_dist,thr_f1,thr_f2',sign_dist,thr_f1,thr_f2)
    print('THR_E,f1,f2,G0,H,FGH',THR_E,thr_f1,thr_f2,THR_G0,THR_H,THR_FGH)
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
        if emissional and (-coeff[i] > THR_E):
            ib, ie = find_edges_e(i, sp_bl_a, ib_lim, ie_lim)
            if ib != ie:                            # Select a wide line by mean, max and area of sp_bl[ib:ie]
                mean_line = np.ma.mean(sp_bl[ib:ie]) if ie > ib+2 else 0    # mean_line is effective when ie > 1b + 2
                thr_f = thr_f1
                thr_g = THR_G0
                if sign_dist > 2:        # thr_f and thr_g are tuned by sign_dist and ie-ib
                    if ie > ib + 10:
                        thr_f -= 0.2
                        thr_g -= 1.0
                    elif ie > ib + 5:
                        thr_f -= 0.1
                max_line = np.max(sp_bl[ib:ie])
                area_line = mean_line *min(ie-ib,100) #if mean_line > 1.0 else 0
                prod3_line = (mean_line * max_line * area_line)/sigma_sp**3
                if (mean_line > thr_f*sigma_sp) or (max_line > thr_g*sigma_sp) or (area_line > THR_H*sigma_sp) or (prod3_line > THR_FGH):
                    ic = ib + np.argmax(sp_bl[ib:ie])  #(ib+ie)//2
                    detected_lines.append([ic,ib,ie])
                    last_registered = [ic,ib,ie]
        elif (not emissional) and (coeff[i] > THR_E):
            ib, ie = find_edges_a(i, sp_bl_a, ib_lim, ie_lim)
            if ib != ie:                          # Select a wide line by mean, max and area of sp_bl[ib:ie]
                mean_line = np.ma.mean(sp_bl[ib:ie]) if ie > ib+2 else 0
                thr_f = thr_f2
                thr_g = THR_G0
                if sign_dist < 0.5:        # thr_f and thr_g are tuned by sign_dist and ie-ib
                    if ie > ib + 10:
                        thr_f -= 0.2
                        thr_g -= 1.0
                    elif ie > ib + 5:
                        thr_f -= 0.1
                min_line = np.min(sp_bl[ib:ie])
                area_line = -mean_line * min(ie-ib,100) if -mean_line > 1.0 else 0
                prod3_line = (mean_line * min_line * area_line)/sigma_sp**3
                if (mean_line < -thr_f*sigma_sp) or (min_line < -thr_g*sigma_sp) or (area_line > THR_H*sigma_sp) or (prod3_line > THR_FGH):
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
    #global THR_E,thr_d,thr_f1,thr_f2,THR_RMG,GM_PARAM,sigma_sp
    global THR_E,THR_G0,thr_f1,thr_f2,THR_RMG,GM_PARAM,sigma_sp
    global dmax,min_X,max_X
    global Zoom_in, Show_details, Show_each, Show_label,Savefig_only_detected_lines
    X = np.ma.arange(dmax)
    SGZXMAX = len(sgzx_list)
    #if 1:
    #    SGZXMAX += 1
    str1 = format(BASELINE_ESTIMATION,'01d')
    str1a = format(BASELINE_INCLINATION,'01d')
    str2c = format(THR_E,'3.2f')
    #str2d = format(thr_d,'3.2f')
    str2d = format(THR_G0,'3.2f')
    str2f1 = format(thr_f1,'3.2f')
    str2f2 = format(thr_f2,'3.2f')
    str3a = format(THR_RMG,'3.2f')
    str3b = format(GM_PARAM,'3.1f')
    str4 = format(Show_each,'01d')
    opt_sigma = '('
    for sgzx in range(SGZXMAX-1):
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
        fig, ax = plt.subplots(SGZXMAX+2, 1)
    else:
        fig, ax = plt.subplots(1, 1)

    #print(str(fig), str(ax[0]))
    if Zoom_in == 1:
        peak_i = int((min_X+max_X)/2)
        line_height = 0
        for sgzx in range(SGZXMAX):
            for j in range(len(lines_detected[sgzx])):
                i = lines_detected[sgzx][j][0]
                if _spectrum_bl[i] > line_height:
                    line_height = _spectrum_bl[i]
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
        ax[0].plot(X[min_Xd:max_Xd], baseline[min_Xd:max_Xd]+sigma_sp, c="lightgreen")    # t_param/GM_PARAM
        ax[0].plot(X[min_Xd:max_Xd], baseline[min_Xd:max_Xd]-sigma_sp, c="lightgreen")
    elif not Show_details :
        if Show_label:
            plt.xlabel(resultfile)
        plt.plot(X[min_Xd:max_Xd], baseline[min_Xd:max_Xd], c="black")  #"black"  "red"
        plt.plot(X[min_Xd:max_Xd], baseline[min_Xd:max_Xd]+sigma_sp, c="lightgreen")    # t_param/GM_PARAM
        plt.plot(X[min_Xd:max_Xd], baseline[min_Xd:max_Xd]-sigma_sp, c="lightgreen")
        plt.plot(X[min_Xd:max_Xd], _spectrum[min_Xd:max_Xd],c="darkgray")
    if Show_details:
        print('Show_each',Show_each)
        if Show_each == 0:
            ax[SGZXMAX+1].plot(X[min_Xd:max_Xd], _spectrum[min_Xd:max_Xd],c="gray")
            for sgzx in range(SGZXMAX):
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
                        if sgzx < SGZXMAX-1:
                            #print('graph',sgzx,SGZXMAX-1)
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
                ax[SGZXMAX+1].plot(X[min_Xd:max_Xd], X[min_Xd:max_Xd]*0+cut_level[icut],c="blue", linewidth=0.5)
            for imean in range(len(mean_level)):
                ax[SGZXMAX+1].plot(X[min_Xd:max_Xd], X[min_Xd:max_Xd]*0+mean_level[imean],c="red", linewidth=0.5)
        elif Show_each < 3:
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
                    if sgzx < SGZXMAX-1:
                        #print('graph',sgzx,SGZXMAX-1)
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
            print ('Show_each3:mean_level',mean_level,len(mean_level))
            print ('Show_each3:cut_level',cut_level,len(cut_level))
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
    #print(resultfile)
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
    global E_STD_MAX, e_std, local_std, BOTH_SIDES_EXCLUSIONS
    # Preparations
    mean_sp = np.ma.mean(_spectrum)                # both-sides-exclusions
    if len(_spectrum) == 0:
        print('np.ma.mean 0')
    #if not BOTH_SIDES_EXCLUSIONS:
    if 1:
        height_sp = np.ma.max(_spectrum)-mean_sp       # constant for e_std
        depth_sp = mean_sp - np.ma.min(_spectrum)      # constant for e_std
    sigma_sp = np.ma.std(_spectrum)

    # Main cycle of Iterative 2-sigma exclusions
    _spectrum1 = _spectrum
    for e_std in range(E_STD_MAX-1):
        #if BOTH_SIDES_EXCLUSIONS:
        #    height_sp = np.ma.max(_spectrum1)-mean_sp       # variable for e_std
        #    depth_sp = mean_sp - np.ma.min(_spectrum1)      # variable for e_std
        #    print ('Both_sides',height_sp,depth_sp,height_sp/depth_sp)

        # update mean_level[e_std] and cut_level[e_std]
        mean_level[e_std]=mean_sp
        if height_sp > depth_sp:                  # Exclude from upper_part
            cut_level[e_std]=mean_sp+sigma_sp*2
            upper_part = np.where(_spectrum1>cut_level[e_std])  # upper_part is selected
            thr_level = 2.0
            while upper_part[0].shape[0] == 0:     # thr_level is tuned, if neccessary
                thr_level -= FORCED_LEVEL_DOWN
                print ('*forced thr_level down1',thr_level)
                cut_level[e_std]=mean_sp+sigma_sp*thr_level
                upper_part = np.where(_spectrum1>cut_level[e_std])
            if BOTH_SIDES_EXCLUSIONS:
                cut_level2 = mean_sp -sigma_sp*3
                lower_part = np.where((_spectrum1<=cut_level[e_std]) & (_spectrum1>cut_level2))   # lower_part is selected
            else:
                lower_part = np.where(_spectrum1<=cut_level[e_std])   # lower_part is selected

        else:                                      # Exclude from lower part
            cut_level[e_std]=mean_sp-sigma_sp*2
            lower_part = np.where(_spectrum1<cut_level[e_std])    # lower_part is selected
            thr_level = 2.0
            while lower_part[0].shape[0] == 0:      # thr_level is tuned, if neccessary
                thr_level -= FORCED_LEVEL_DOWN
                print ('*forced thr_level down2',thr_level)
                cut_level[e_std]=mean_sp-sigma_sp*thr_level
                lower_part = np.where(_spectrum1<cut_level[e_std])
            if BOTH_SIDES_EXCLUSIONS:
                cut_level2 = mean_sp +sigma_sp*3
                upper_part = np.where((_spectrum1>=cut_level[e_std]) & (_spectrum1<cut_level2))   # lower_part is selected
            else:
                upper_part = np.where(_spectrum1>=cut_level[e_std])   # lower_part is selected

        # Calculate upper_mean and lower_mean
        upper_mean = np.ma.mean(_spectrum1[upper_part])
        lower_mean = np.ma.mean(_spectrum1[lower_part])
        if upper_part[0].shape[0] == 0:
             print('np.ma.mean 1: upper_part[0]')
        if lower_part[0].shape[0] == 0:
             print('np.ma.mean 2: lower_part[0]')

        # Calculate relative_mean_gap
        mean_gap = upper_mean - lower_mean
        relative_mean_gap = mean_gap/sigma_sp
        print('statistics0:',e_std,(height_sp > depth_sp), mean_gap,sigma_sp,relative_mean_gap,mean_level[e_std],cut_level[e_std])

        # Update mean_sp and sigma_sp
        if height_sp > depth_sp:
            sigma_sp = np.ma.std(_spectrum1[lower_part])
            mean_sp = lower_mean
        else:
            sigma_sp = np.ma.std(_spectrum1[upper_part])
            mean_sp = upper_mean

        # validation by local_std_check
        local_std_check_invalid = (sigma_sp > 2 * local_std)
        if relative_mean_gap <= THR_RMG and not local_std_check_invalid:      # thr_tmg = 2.25  # relative_mean_gap converges to 2.25
            mean_level[e_std+1]=mean_sp
            break
        if local_std_check_invalid and (e_std == E_STD_MAX-2):                   # at final iteration
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
    sigma_num = 60  # 60
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
        1)Baseline estimation by Geman-McClure function: (lf_gmn.py)
        2)Integrated line detection by zero-crossings of first derivative of Gaussian average of SIGNAL_BL: (integrated_line_detection())
        3)Narrow line detection by zero-crossings of the first derivative of Gaussian average on SIGNAL_BL: (narrow_line_detection())

    Returns:
        ranges: A list of start and end indices of spectral lines. The indices of
                    lines are in the order of, e.g., [start1, end1, ..., startN, endN].
    """
    global sigma_sp, local_std, ga5_std, GS_PARAM, optimum_sigma, Gaussian_sp_bl, THR_RMG, sign_dist
    global dmax, min_X, max_X, max_height, min_height, SGZXMAX
    global Draw_graph, BASELINE_ESTIMATION, BASELINE_INCLINATION, Gaussian_subtraction, GAUSSIAN_ENABLE, WL_ANALYSIS
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
    mean_level = np.arange(E_STD_MAX,dtype=float)
    cut_level = np.arange(E_STD_MAX,dtype=float)
    sigma_sp,mean_sp,k_std,_spectrum1 = iterative_2s_exclusions(_spectrum,mean_level,cut_level)
    print('sigma_sp,mean_sp',sigma_sp,mean_sp)

    # Baseline estimation by Geman-McClure function
    baseline = np.ma.arange(dmax,dtype=float)
    X_ = np.ma.arange(dmax).reshape(-1,1)

    # Selection of BASELINE_ESTIMATION or Gaussian_subtraction
    BASELINE_ESTIMATION = True
    #if (ga5_std < 2.5 * local_std and sigma_sp > GS_PARAM *local_std):
    print('GAUSSIAN_ENABLE',GAUSSIAN_ENABLE)
    if GAUSSIAN_ENABLE:
        print ('BASELINE_ESTIMATION0', local_std, k_std, sigma_sp/local_std, ga5_std/local_std, BASELINE_ESTIMATION)
        if (dmax > 256 and sigma_sp > GS_PARAM *local_std):  # GS_PARAM = 1.2
            if ((k_std < 4 and ga5_std > 1.8 * local_std) or (k_std < 10 and ga5_std > 2.0 * local_std)):     # BASELINE_ESTIMATION works in these cases
                print ('**k_std check')
            else:
                BASELINE_ESTIMATION = False
        print ('BASELINE_ESTIMATION', local_std, k_std, sigma_sp/local_std, ga5_std/local_std, BASELINE_ESTIMATION)
    Gaussian_subtraction = not BASELINE_ESTIMATION

    # Preparation for lfr.GM()
    if BASELINE_ESTIMATION:               # BASELINE_ESTIMATION is used for the future alternative, e.g. Gaussian-subtraction
        if BASELINE_INCLINATION and (dmax > THR_SS):         # BASELINE_INCLINATION is not effective for short spectrum

            # SLOPE is estimated from mean_left and mean_right
            half_pos = len(_spectrum)//2
            mean_left= np.ma.mean(_spectrum1[:half_pos])
            mean_right=np.ma.mean(_spectrum1[half_pos:])
            relative_pos_gap = 2*(mean_right-mean_left)/sigma_sp
            print ('relative_pos_gap',half_pos,mean_sp,mean_left,mean_right,relative_pos_gap)

            # SLOPE is effective when abs(relative_pos_gap) is not too small
            displacement_effective = (abs(relative_pos_gap) > THR_RPG)
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
        regressor = lfr.GM(t=t_param,g=GM_PARAM, y_list=yc_list, model=lfr.LinearModel(),
                           metric=lfr.mean_gm_error, fdt=lfr.gm_fd_total, sdt=lfr.gm_sd_total)
        #regressor =lfr.GM(t=t_param, g=GM_PARAM, y_list=yc_list,model=lfr.LinearModel(), loss=lfr.gm_error_loss, metric=lfr.mean_gm_error)
        print ('t,g:',t_param,GM_PARAM)
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
        sigma_sp = local_std
        optimum_sigma = optimize_sigma(_spectrum[min_X:max_X])
        print('Gaussian_subtraction', optimum_sigma)
        gs_edge_width = int(optimum_sigma*3.0)
        baseline[min_X:max_X] = gaussian_average(_spectrum[min_X:max_X], optimum_sigma)
        baseline[min_X:min_X+gs_edge_width] = _spectrum[min_X:min_X+gs_edge_width]
        baseline[max_X-gs_edge_width:max_X] = _spectrum[max_X-gs_edge_width:max_X]
    # Baseline-subtracted spectrum is generated
    _spectrum_bl = np.ma.arange(_spectrum.shape[0], dtype=np.float64)
    if Gaussian_subtraction or BASELINE_ESTIMATION:
        _spectrum_bl[min_X:max_X] = _spectrum[min_X:max_X] -baseline[min_X:max_X]
    else:
        _spectrum_bl[min_X:max_X] = _spectrum[min_X:max_X]
        baseline[min_X:max_X] = 0

    # Line detection scheme
    ## Preparation for parallel processings
    # sgzx_list is generated
    sgzx_list = []
    if SGZXMAX >= 1:
        for ii in range(SGZXMAX):
            sgzx_list += [2 ** (ii+ii+1)]       # 2, 8
            #sgzx_list += [2 ** (ii+1)]          # 2, 4
    #print ('sgzx_list',sgzx_list)

    # arangement of g_ave, signal and coeff
    #SGZXMAXp1= SGZXMAX + 1
    #g_ave = np.ma.arange(SGZXMAXp1*dmax,dtype=float).reshape(SGZXMAXp1,dmax)   # for Graphic use
    #signal = np.ma.arange(SGZXMAXp1*dmax,dtype=float).reshape(SGZXMAXp1,dmax)
    #coeff = np.ma.arange(SGZXMAXp1*dmax,dtype=float).reshape(SGZXMAXp1,dmax)
    g_ave = np.ma.arange(SGZXMAX*dmax,dtype=float).reshape(SGZXMAX,dmax)   # for Graphic use
    signal = np.ma.arange(SGZXMAX*dmax,dtype=float).reshape(SGZXMAX,dmax)
    coeff = np.ma.arange(SGZXMAX*dmax,dtype=float).reshape(SGZXMAX,dmax)

    ## Wide line detection
    # setting parameters
    max_height = np.ma.max(_spectrum_bl[min_X:max_X])
    min_height = np.ma.min(_spectrum_bl[min_X:max_X])
    sign_dist = max_height/abs(min_height)
    #print ('sign_dist', np.ma.max(_spectrum_bl[min_X:max_X]),np.ma.min(_spectrum_bl[min_X:max_X]), sign_dist)
    Gaussian_sp_bl = (max_height/sigma_sp < THR_SPBL)
    print ('Gaussian_sp_bl',Gaussian_sp_bl,max_height/sigma_sp)

    ## select sigma_p
    sigma_p = sgzx_list[0]     # 2

    ## call integrated_line_detection)
    #wide_line_list = integrated_line_detection(_spectrum_bl,sigma_p,signal[SGZXMAX,:],coeff[SGZXMAX,:])
    wide_line_list = integrated_line_detection(_spectrum_bl,sigma_p,signal[0,:],coeff[0,:])

    ## Make wl_flag from wide_line_list
    wl_flag= np.arange(dmax,dtype='int')
    wl_flag[min_X:max_X] = 0
    for il in range(len(wide_line_list)):
        ib = wide_line_list[il][1]
        ie = wide_line_list[il][2]
        wl_flag[ib:ie] = 1

    ## Narrow line detection by narrow_line_detection()
    lines_detected = []

    # Narrow line detection for sigma = 8

    #for sgzx in range(SGZXMAX):
    if 1:
        sgzx = 1
        #setting parameters
        sigma = sgzx_list[sgzx]
        #WL_ANALYSIS = (sgzx >= SGZXMAX - WL_MASK_INDEX)

        # call narrow_line_detection()
        new_lines = narrow_line_detection(_spectrum_bl,sigma,signal[sgzx,:],coeff[sgzx,:],wl_flag,WL_ANALYSIS)

        # detected line_list is appended to lines_detected
        lines_detected.append(new_lines)
        print ('lines_detected',sgzx,len(lines_detected[0]),lines_detected[0])
        #print ('lines_detected',sgzx,len(lines_detected[sgzx]),lines_detected[sgzx])

    # wide_line_list is appended to lines_detected
    lines_detected.append(wide_line_list)
    nlist=len(lines_detected)-1
    print ('lines_detected *',1,len(lines_detected[nlist]),lines_detected[nlist])
    #print ('lines_detected2',SGZXMAX,len(lines_detected[SGZXMAX]),lines_detected[SGZXMAX])

    # lines_detected(list of line_lists) is merged to a list of lines named lines_merged
    lines_merged = merge_detected_lines(lines_detected)
    print ('lines_merged',len(lines_merged),lines_merged)

    # lines_final is generated from lines_merged due to pipeline_format
    lines_final = pipeline_format_lines(lines_merged)
    #print ('lines_final',len(lines_final)/2,lines_final)
    if Draw_graph:
        for sgzx in range(SGZXMAX):
            sigma = sgzx_list[sgzx]
            make_g_ave(_spectrum_bl,sigma,g_ave[sgzx,:])
        #make_g_ave(_spectrum_bl,sigma_p,g_ave[SGZXMAX,:])
        make_g_ave(_spectrum_bl,sigma_p,g_ave[1,:])
        draw_graph_gmr(_spectrum,baseline,_spectrum_bl,signal,coeff,g_ave,lines_detected,lines_merged,
                       sgzx_list, mean_level[0:e_std+2], cut_level[0:e_std+1])
    return(lines_final,baseline[0],baseline[0]/sigma_sp)

if __name__ == "__main__":
    Database_selector = 0
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
                BASELINE_ESTIMATION = False
            else:
                BASELINE_ESTIMATION = True         # lf_gm is called for baseline estimation
            if 1:   # line_finder works for spetrum with mask
                #print (_spectrum.shape,_spectrum.mask.shape)
                lines_final,base_l[loc-loc_b],base_lr[loc-loc_b] = line_finder(_spectrum,_spectrum.mask)
            else:   # line_finder also works for spectrum without mask
                lines_final,base_l[loc-loc_b],base_lr[loc-loc_b] =line_finder(_spectrum)
            print('lines_final',data_file,len(lines_final)/2,lines_final)