#
# [SCRIPT INFORMATION]
# GIT REPO: https://bitbucket.alma.cl/scm/~harold.francke/sd-atm-line-correction-prototype.git
# COMMIT: c600e544134
#
#SDcalatmcorr: Casapipescript with wrapper for TS script "atmcorr.py" for the removal
#of atmospheric line residuals.
#2020 - T.Sawada, H. Francke

# 27/mar/2025: - Added missing docstrings, eliminated bootstrap() and getSBData(), which have no use in production.
#                The code is based on the commit mentioned above, but will be updated by SDPL team
#                for bug fix/refactoring/enhancement.
# 19/mar/2025: - SDPL team took over maintenance responsibility of this code from original author.
# 13/mar/2025: - (v2.7) Update to optimize, simplify and reduce this code in order to pass resposability to PLWG
#              - Removed 'maxabs' and 'intabs' metrics, and the associated baseline fitting routines, and science line
#                channels detection functions, which never worked very well.
# 08/apr/2022: - (v2.6) Change logic of best model evaluation to be done inside the atmcor() method.
#              - Created a function makePlot() to clean up the plot generation par of the code.
#                This function added a label with Applied/Discarded to point out the used model.
#                Additionally, the atmospheric transmission was added to the plot, and the channels
#                selected for metric measurement.
# 31/mar/2022: - (v2.5) Added feature to automatically select representative science target for metric
#                measurements.
#              - Fixed issue with range of atmospheric line range selection.
# 25/feb/2022: - (v2.4) Added feature to automatically select least flagged antenna for doing the metric measurement.
#              - Changed default parameters to consider atmtype 1,2,3,4 only for models testing.
#              - Remove remaining dependencies on analysisUtils
#              - Cleaned up procedure to handle default model fallback case, including the return of
#                a 'fitstatus' variable decribing whether a best fit or a fallback to default model happened.
# 27/jan/2022: - (v2.3) Fixed bug that made script crash with multiples EBs getting different
#                SPW selection with multiple ATM selected for model testing
# 25/jan/2022: - (v2.2) Added catch for case when skyline get fully confused with science line and script
#                ends with no data for model fit
#              - Changed Science target channel detection to previous version (selsource() task)
#              - Added EB uid to plots
# 24/jan/2021: - (v2.1) Fixed issue with spwstoprocess variable with smoothing
# 21/jan/2022: - (v2.0) Fixed several bugs, including handling crashes with fully flagged data pieces
#              - Handles cases where no result is possible when no significant skyline is present, to return default model
#              - Support for using multiple skylines for metric calculation
#              - Added plots for absolute value of derivative, to better assess "*diff" metrics
#              - Added ability to smooth derivative data to reduce noise
#              - Improved skyline range detection from model tau
# 15/dec/2021: - Converted to Python 3/CASA 6 (NOT COMPATIBLE WITH CASA<6 ANYMORE!)
#              - Removed atmospheric correction calculation routine inherited from Sawada san's script and replaced
#                it by one mstransform and several sdatmcor call, in order to calculate the corrected data
#              - Added metrics 'intabsdiff' (integral of absolute value of derivative) and
#                'intsqdiff' (integral of square value of derivative).
#              - Improved statistical estimation of data errors
#              - Changed data normalization routine and science emission detection.
#              - Uploaded to ALMA Bitbucket
# 03/mar/2021: - Fixed bug handling datasets having TDM SPWs
#              - Fixed metric calculation and plotting problem that got model data stuck in non-corrected data
#              - Rearranged code to move atmcorr core routine to separate function and moved auxiliary spectral setup data
#                into the "spwsetup" dictionary.
# 08/jan/2021: - Added functionality to run atmcorr routine in "try" mode and extract three different
#                metrics for a family of model parameters.
# 24/jul/2020: - Aligned with script atmcorr_20200722.py

import os
from typing import Generator

import glob
import numpy as np
from itertools import pairwise, product
import matplotlib
import time as systime
from scipy.interpolate import CubicSpline

import pipeline.infrastructure.callibrary as callibrary
import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.casa_tools as casa_tools
import pipeline.infrastructure.casa_tasks as casa_tasks

LOG = logging.get_logger(__name__)

pipelineloaded = True

#Useful function for fully flattening array
flattenlist = lambda l: [item for sublist in l for item in sublist]

version = '2.7'


def robuststats(A):
    '''Return median and estimate standard deviation
    of numpy array A using median statistics.
    '''
    #correction factor for obtaining sigma from MAD
    madfactor = 1.482602218505602
    n = len(A)
    #Fitting parameters for sample size correction factor b(n)
    if (n%2 == 0):
        alpha = 1.32
        beta = -1.5
    else:
        alpha = 1.32
        beta = -0.9
    bn = 1.0 - 1.0/(alpha*n + beta)
    mu = np.ma.median(A)
    sigma = (1.0/bn)*madfactor*np.ma.median(np.ma.abs(A - mu))
    return (mu, sigma)

def segmentEdges(seq, gap, label, sortdata = True):
    '''Return edges of sequence of values with gaps
    Assumes 1D array "seq" is ordered. Otherwise one should sort it first.
    seq: Sequence of values to search gaps in.
    gap: Gap size to consider.
    label: Label to put in the numpy array returned.
    sortdata: Whether to sort data in the seq vector.
    '''

    if sortdata:
        seq = np.sort(seq)
    n = len(seq)
    diff = seq[1:] - seq[0:n-1]
    if np.any(diff < 0):
        LOG.info('Array is not sorted, use sortdata = True')
        return None
    isgap = (diff > gap)
    if np.sum(isgap) > 0:
        startseg = seq[np.append([True],isgap)]
        endseg = seq[np.append(isgap,[True])]
        output = np.array([(startseg[i], endseg[i], label) for i in range(len(startseg))], np.dtype([('tstart',np.float64),('tend',np.float64),('intent',np.str_,40)]))
    else:
        output = np.array([(seq[0], seq[-1], label)], np.dtype([('tstart',np.float64),('tend',np.float64),('intent',np.str_,40)]))

    return output

def selectRanges(timeseq, rangetable):
    '''Return selection boolean array for a time sequence, given a table of time ranges.
    '''
    nranges = len(rangetable)
    ndata = len(timeseq)
    sel = np.zeros(ndata, dtype=bool)
    for i in range(nranges):
        sel += np.all([timeseq >= rangetable['tstart'][i], timeseq <= rangetable['tend'][i]], axis=0)
    return sel

def sigclipfit(x, A, Asig, fitdeg, nclips, nsigma, bordertokeep = 0.05, progdegree = False, smoothselbox = 0.05):
    '''Return polynomial model parameters done to vector A and residuals from the fit.
    x: x coordinate
    A: Data set vector.
    Asig: Data sigma vector. Should include variance due to skylines and science target emission.
    fitdeg: Fitting polynomial degree.
    nclips: Number of sigma clipping iterations.
    nsigma: Number of sigmas in sigma clipping iterations. Positive float or two-value tuple.
    bordertokeep: Fraction of channels to keep in the borders
    progdegree: Whether to increase polynomial fit progressively in each iteration.
    smoothselbox: Enlarge each outlier detection with a box of this size (as fraction of SPW).
    '''
    if type(nsigma) == float:
        nsigmahigh = nsigma
        nsigmalow = nsigma
    elif ((type(nsigma) == tuple) or (type(nsigma) == list)) and (len(nsigma) == 2):
        nsigmahigh = nsigma[1]
        nsigmalow = nsigma[0]
    output = {}
    gooddata = np.ma.MaskedArray(np.ones(len(A)), mask=A.mask)
    #Start data selection with all good data
    sel = gooddata
    minx = np.ma.min(x)
    maxx = np.ma.max(x)
    bordermin = minx + bordertokeep*(maxx - minx)
    bordermax = maxx - bordertokeep*(maxx - minx)
    #Set border selection, avoiding any bad data
    border = np.ma.MaskedArray(np.ma.all([np.ma.any([x < bordermin, x > bordermax], axis=0), gooddata], axis=0), mask=A.mask)
    if progdegree:
        degree = 0
    else:
        degree = fitdeg
    if smoothselbox > 0.0:
        box = max(2, int(smoothselbox*len(A)))
    else:
        box = 1
    while (degree <= fitdeg):
        for i in range(nclips):
            #Include constant border, if demanded
            thissel = np.ma.any([sel, border], axis=0)
            #If everything is flagged, continue with a default selection of everything
            if np.sum(~A.mask[thissel]) <= fitdeg:
                thissel = np.ma.any([gooddata, border], axis=0)
            try:
                coefs = np.polyfit(x[thissel], A[thissel], fitdeg, w=1/Asig[thissel])
            except:
                coefs = [0.0 for i in range(degree+1)]
                LOG.info('No data!!!\nx='+str(x[thissel])+'\nA='+str(A[thissel])+'\nAsig='+str(Asig[thissel]))
            model = np.ma.sum([coefs[i]*(x**(degree-i)) for i in range(degree+1)], axis=0)
            diff = A - model
            (mu, sigma) = robuststats(diff)
            #Select pixels to use in the next iteration from pixels within nsigma of mean
            #including only non-masked data, but not in the border.
            sel = np.ma.all([((diff - mu)/sigma >= -nsigmalow), ((diff - mu)/sigma <= nsigmahigh), gooddata], axis=0)
            #If boxcar smoothing of selection is chosen (smoothselbox > 0), broadening non-selected pixels
            if box > 1:
                sel = np.ma.logical_not(enlargesel(np.ma.logical_not(sel), box))
        degree += 1
    output['coefs'] = coefs
    output['residuals'] = diff
    output['sel'] = sel
    output['border'] = border
    return output

def enlargesel(sel, box):
    '''Enlarge selection by "box" pixels around each selected pixel
    in "sel" vector.
    '''
    n = len(sel)
    newsel = 0.0*sel
    for i in range(n):
        startrange = max(0, i - box)
        endrange = min(n - 1, i + box + 1)
        newsel[i] = np.ma.max(sel[startrange:endrange])
    return newsel

def smooth(y: np.ndarray, box_pts: int):
    '''Smooth using boxcar convolution.

    To mitigate boundary effect, this function extrapolates
    the data by box_pts // 2 in both edges with "nearest"
    method. This will be harmless in the context of this
    heuristics since we are interested in the gradient
    (diff) between adjuscent channels.

    Args:
        y: 1D array to be smoothed.
        box_pts: Width of the boxcar kernel. Must be a positive integer.

    Returns:
        Smoothed 1D array of the same length as y.
    '''
    if box_pts < 2:
        # no smoothing is applied
        return y

    box = np.ma.ones(box_pts)/box_pts
    extra_chans = (box_pts + 1) // 2
    y_expand = np.pad(y, extra_chans, mode='edge')
    print(f"box_pts {box_pts} extra_chans {extra_chans}")
    y_smooth = np.ma.convolve(y_expand, box, mode='same')
    return y_smooth[extra_chans:-extra_chans]

def getskylines(tauspec, spw, spwsetup, fraclevel = 0.5, minpeaklevel = 0.0, spwbordertoavoid = 0.025, taudeg = 2):
    '''Get position of sky lines and line widths from the optical depth.
    fraclevel: fraction of the maximum of the optical depth to look for.
    If fraclevel=0.5 (default), the width results will be the HWHM.
    minpeaklevel: Minimum relative opacity at a given peak (relative to median opacity)
    to consider a line. Lines smaller than this level are ignored. (default 0.05)
    spwbordertoavoid: Fractional border of the SPW to avoid for peak detection.
    Default is 0.025 (2.5% of SPW BW)
    '''
    nch = len(tauspec)
    borderpix = int(max(1.0,np.round(nch*spwbordertoavoid)))
    noborder = np.ones(nch, dtype=bool)
    noborder[0:borderpix] = False
    noborder[nch-borderpix:nch] = False
    mintau = np.min(tauspec)
    mediantau = np.median(tauspec)
    tauzeroD = np.array(np.ediff1d(1.0*(np.ediff1d(tauspec) > 0.0), to_begin=0, to_end=0), dtype=bool)
    taunegDD = np.array(np.ediff1d(np.ediff1d(tauspec), to_begin=0, to_end=0) < 0.0, dtype=bool)
    taugtminlevel = (tauspec/mediantau >= (1.0 + minpeaklevel))
    taupeak = np.all([tauzeroD, taunegDD, taugtminlevel, noborder], axis=0)
    tauvalley = np.all([tauzeroD, ~taunegDD], axis=0)
    idxpeak = np.arange(nch, dtype=int)[taupeak]
    idxvalley = np.arange(nch, dtype=int)[tauvalley]
    npeak = len(idxpeak)
    peaktau = tauspec[idxpeak]
    output = {'nch': nch, 'npeak': npeak, 'taumin': mintau, 'fraclevel': fraclevel, 'valley': idxvalley, 'peaksinfo': {}}
    hwhmleft = np.zeros(npeak)
    hwhmright = np.zeros(npeak)
    widthratio = np.zeros(npeak)
    #Fit "baseline" to tau
    nu = spwsetup[spw]['chanfreqs']/1.e09
    taufit = sigclipfit(nu, np.ma.MaskedArray(tauspec, mask=np.zeros(nch)),
                        np.ma.MaskedArray(np.sqrt(tauspec), mask=np.zeros(nch)), 2, 3, 5.0)
    taubline = np.ma.sum([taufit['coefs'][deg]*(nu**(taudeg-deg)) for deg in range(taudeg + 1)], axis = 0)
    subtau = tauspec - taubline
    output['taufit'] = taufit
    for k, idx in enumerate(idxpeak):
        #calculate the decrease from the tau depth relative to the minimum tau in the SPW
        #peakratioleft = np.array([(tauspec[idx - i]-mintau)/(peaktau[k]-mintau) for i in range(idx)])
        #peakratioright = np.array([(tauspec[idx + i]-mintau)/(peaktau[k]-mintau) for i in range(nch-idx)])
        peakratioleft = np.array([subtau[idx - i]/subtau[idx] for i in range(idx)])
        peakratioright = np.array([subtau[idx + i]/subtau[idx] for i in range(nch-idx)])
        posrightneg = peakratioright < fraclevel
        if np.sum(posrightneg) > 0:
            hwhmright[k] = np.where(posrightneg)[0][0]
        else:
            #search of peak to the right of this peak, select the border if none
            if k < npeak-1:
                hwhmright[k] = 0.5*(idxpeak[k+1] - idx)
            else:
                hwhmright[k] = nch - idx - 1
        posleftneg = peakratioleft < fraclevel
        if np.sum(posleftneg) > 0:
            hwhmleft[k] = np.where(posleftneg)[0][0]
        else:
            #search of peak to the left of this peak, select the border if none
            if k > 0:
                hwhmleft[k] = 0.5*(idx - idxpeak[k-1])
            else:
                hwhmleft[k] = idx

    #If the range of the skylines goes beyond a valley, shrink range around line using those valleys
    for k in range(npeak):
        valleypointsleft = np.sort([point for point in idxvalley if (point < idxpeak[k])])
        if (len(valleypointsleft) > 0) and (idxpeak[k]-hwhmleft[k] < valleypointsleft[-1]):
            hwhmleft[k] = idxpeak[k] - valleypointsleft[-1]
        valleypointsright = np.sort([point for point in idxvalley if (point > idxpeak[k])])
        if (len(valleypointsright) > 0) and (idxpeak[k]+hwhmright[k] > valleypointsright[0]):
            hwhmright[k] = valleypointsright[0] - idxpeak[k]

    #Check if there is more than one peak and if so check if ranges overlap and correct in that case
    if npeak > 1:
        for k in range(npeak - 1):
            if (idxpeak[k]+hwhmright[k] > idxpeak[k+1]-hwhmleft[k+1]):
                #If there is an valley point detected between the peaks, choose that one.
                #If not, just pick the middle point between peaks
                valleypoints = [point for point in idxvalley if (point > idxpeak[k]) and (point < idxpeak[k+1])]
                if len(valleypoints) > 0:
                    hwhmright[k] = valleypoints[0]-idxpeak[k]
                    hwhmleft[k+1] = idxpeak[k+1]-valleypoints[0]
                else:
                    hwhmright[k] = 0.5*(idxpeak[k+1]-idxpeak[k])
                    hwhmleft[k+1] = 0.5*(idxpeak[k+1]-idxpeak[k])

    #Create output dictionary
    for k, idx in enumerate(idxpeak):
        output['peaksinfo'][k] = {}
        output['peaksinfo'][k]['peakpos'] = int(idx)
        output['peaksinfo'][k]['taupeak'] = tauspec[idx]
        output['peaksinfo'][k]['hwhmleft'] = int(hwhmleft[k])
        output['peaksinfo'][k]['hwhmright'] = int(hwhmright[k])
        output['peaksinfo'][k]['minrange'] = int(idx - hwhmleft[k])
        output['peaksinfo'][k]['maxrange'] = int(idx + hwhmright[k])
    return output

def gradeskylines(skylines: dict, cntrweight: float = 1.0):
    '''Function to calculate a "grade" for each skyline detected by the getskylines() function.
    These "grades" are based on a normalized value of the opacity at the skyline peak and the position of
    the line in the SPW, and is aimed at providing a decision on which skyline to used for model evaluation.
    param:
        skylines: (dict) Dictionary of detected skylines indexed by SPW, where each sub-dictionary is as obtained
                  from getskylines().
        cntrweight: (float) Relative weight given to the position of the skyline relative to the center of the SPW.
                    Must be a positive float number between 0 and 1, a value of 0.0 means no weight to position,
                    a value >0 gives the line a linearly decreasing grade the further it is away from the center of the SPW.
    returns:
        A tuple of (spw, peak) that identifies the SPW and id number of the skyline in that SPW that has the best grade.
        The skyline id number is the same as in the dictionary output from getskylines().
        Additionally, the grades calculated are saved in the input skylines dictionary, modifying the original variable.
    '''

    spwlist = np.sort(list(skylines.keys()))
    idxspw = []
    idxpeak = []
    taupeak = []
    centerdist = []
    #Read values and calculate distance to SPW centers
    for spw in spwlist:
        for i in range(skylines[spw]['npeak']):
            taupeak.append(skylines[spw]['peaksinfo'][i]['taupeak'])
            centerdist.append(2.0*(skylines[spw]['peaksinfo'][i]['peakpos'] - 0.5*skylines[spw]['nch'])/skylines[spw]['nch'])
            idxspw.append(spw)
            idxpeak.append(i)
    taupeak = np.array(taupeak)
    centerdist = np.array(centerdist)
    #Calculate grade
    normtau = (taupeak - np.min(taupeak))/(np.max(taupeak) - np.min(taupeak))
    grade = normtau*(1.0 - cntrweight*np.abs(centerdist))
    bestgrade = np.argsort(grade)[-1]
    #Put grade back into skylines dictionary
    idx = 0
    for spw in spwlist:
        for i in range(skylines[spw]['npeak']):
            skylines[spw]['peaksinfo'][i]['grade'] = grade[idx]
            idx += 1
    #Return SPW and index of higher grade peak
    return (idxspw[bestgrade], idxpeak[bestgrade])

def skysel(skylines, linestouse = 'all', avoidpeak = 0.0):
    '''Create selection array from dictionary of skylines list.
    avoidpeak: Parameter to avoid a range around the line peak as fraction of FWHM
    '''
    skysel = np.zeros(skylines['nch'], dtype=bool)
    if linestouse == 'all':
        linestouse = range(skylines['npeak'])
    for i in linestouse:
        skysel[skylines['peaksinfo'][i]['minrange']:skylines['peaksinfo'][i]['maxrange']+1] = np.ones(skylines['peaksinfo'][i]['maxrange']-skylines['peaksinfo'][i]['minrange']+1, dtype=bool)
        if avoidpeak > 0.0:
            startrange = max(0, skylines['peaksinfo'][i]['peakpos']-int(avoidpeak*skylines['peaksinfo'][i]['hwhmleft']))
            endrange = min(skylines['peaksinfo'][i]['peakpos']+int(avoidpeak*skylines['peaksinfo'][i]['hwhmright']), skylines['nch'])
            skysel[startrange:endrange] = np.zeros(endrange-startrange, dtype=bool)

    return skysel

def calcmetric(rawsample: np.ndarray, rawsigmasample: np.ndarray, metrictype_list: str | list[str] = 'intsqdiff', smoothbox: int = 1) -> dict[str, tuple[float, float]]:
    '''Function that calculates a metric value for a given piece of spectrum (time-averaged data), typically
    a section around the skyline selected by its "grade".
    param:
        rawsample: (numpy array) Array with the data to be used to compute the metric.
        rawsigmasample: (numpy array) Noise array related to the data to be used to compute the metric. Noise
                        estimation typically used is the standard deviation along the time dimension.
        smoothbox: (int) Run a boxcar smoothing on the data piece before calculating the metric. Value in number of channels.
        metrictype: (str) String that determines which algorithm to use to calculate the metric value. Options are:
                    - "intabs": Integral of the absolute value of spectrum piece. (deprecated)
                    - "maxabs": Maximum of the absolute value of spectrum piece. (deprecated)
                    - "maxabsdiff": Maximum of the absolute value of the derivative of the spectrum piece.
                    - "intabsdiff": Integral of the absolute value of the derivative of the spectrum piece.
                    - "intsqdiff": Integral of the square value of the derivative of the spectrum piece.
    '''

    (npols, nch) = np.shape(rawsample)
    # limit smoothing box size to 20% of nch
    smoothbox = max(1, min(nch // 5, smoothbox))
    #Smooth if requested
    if (smoothbox > 1) and (type(smoothbox) == int):
        sample = 0.0*rawsample
        for i in range(npols):
            sample[i,:] = smooth(rawsample[i,:], smoothbox)
        sigmasample = rawsigmasample/np.sqrt(smoothbox)
    else:
        sample = rawsample
        sigmasample = rawsigmasample
    #Transform arrays to ma if not like that already
    if not type(sample) == np.ma.core.MaskedArray:
        sample = np.ma.MaskedArray(sample)
        sigmasample = np.ma.MaskedArray(sigmasample)

    resultdict = {}

    if isinstance(metrictype_list, str):
        metrictype_list = [metrictype_list]

    for metrictype in metrictype_list:
        if metrictype == 'intabs':
            auxval = []
            auxerr = []
            for i in range(npols):
                goodsample = (sample.data[i])[~sample.mask[i]]
                sigmagoodsample = (sigmasample[i])[~sample.mask[i]]
                if len(goodsample) > 0:
                    auxval.append(np.ma.sum(np.ma.abs(sample[i,:])))
                    auxerr.append(np.ma.sqrt(np.ma.sum(sigmasample[i,:]*sigmasample[i,:])))
            if len(auxval) > 0:
                value = np.sum(auxval)
                error = np.sqrt(np.sum(np.array(auxerr)*np.array(auxerr)))
            else:
                value = np.nan
                error = np.nan
            resultdict[metrictype] = (value, error)
        elif metrictype == 'maxabs':
            auxval = []
            auxerr = []
            for i in range(npols):
                goodsample = (sample.data[i])[~sample.mask[i]]
                sigmagoodsample = (sigmasample[i])[~sample.mask[i]]
                if len(goodsample) > 0:
                    idx = np.argsort(np.abs(goodsample))[-1]
                    auxval.append(np.abs(goodsample[idx]))
                    auxerr.append(sigmagoodsample[idx])
            if len(auxval) > 0:
                idx = np.argsort(np.abs(auxval))[-1]
                value = auxval[idx]
                error = auxerr[idx]
            else:
                value = np.nan
                error = np.nan
            resultdict[metrictype] = (value, error)
        elif metrictype == 'maxabsdiff':
            auxval = []
            auxerr = []
            for i in range(npols):
                goodsample = (sample.data[i])[~sample.mask[i]]
                sigmagoodsample = (sigmasample[i])[~sample.mask[i]]
                if len(goodsample) > 0:
                    absdiff = np.abs(np.diff(goodsample))
                    idx = np.argsort(absdiff)[-1]
                    auxval.append(absdiff[idx])
                    auxerr.append(np.sqrt(sigmagoodsample[idx]**2+sigmagoodsample[idx+1]**2))
            if len(auxval) > 0:
                idx = np.argsort(np.abs(auxval))[-1]
                value = auxval[idx]
                error = auxerr[idx]
            else:
                value = np.nan
                error = np.nan
            resultdict[metrictype] = (value, error)
        elif metrictype == 'intabsdiff':
            auxval = []
            auxerr = []
            for i in range(npols):
                goodsample = (sample.data[i])[~sample.mask[i]]
                sigmasqgoodsample = np.square((sigmasample[i])[~sample.mask[i]])
                if len(goodsample) > 0:
                    absdiff = np.abs(np.diff(goodsample))
                    absdiffsqerr = sigmasqgoodsample + np.roll(sigmasqgoodsample, 1)
                    auxval.append(np.sum(absdiff))
                    auxerr.append(np.sqrt(np.sum(absdiffsqerr)))
            if len(auxval) > 0:
                value = np.sum(auxval)
                error = np.sqrt(np.sum(np.array(auxerr)*np.array(auxerr)))
            else:
                value = np.nan
                error = np.nan
            resultdict[metrictype] = (value, error)
        elif metrictype == 'intsqdiff':
            auxval = []
            auxerr = []
            for i in range(npols):
                goodsample = (sample.data[i])[~sample.mask[i]]
                sigmasqgoodsample = np.square((sigmasample[i])[~sample.mask[i]])
                if len(goodsample) > 0:
                    absdiff = np.abs(np.diff(goodsample))
                    sqdiff = np.square(absdiff)
                    absdiffsqerr = sigmasqgoodsample + np.roll(sigmasqgoodsample, 1)
                    sqdifferr = 4*absdiff*absdiff*(absdiffsqerr[0:-1])
                    auxval.append(np.sum(sqdiff))
                    auxerr.append(np.sqrt(np.sum(sqdifferr)))
            if len(auxval) > 0:
                value = np.sum(auxval)
                error = np.sqrt(np.sum(np.array(auxerr)*np.array(auxerr)))
            else:
                value = np.nan
                error = np.nan
            resultdict[metrictype] = (value, error)
        else:
            resultdict[metrictype] = (-1.0, -1.0)

    return resultdict

#Copied over from analysisUtils
def getSpwList(msmd,intent='OBSERVE_TARGET#ON_SOURCE',tdm=True,fdm=True, sqld=False):
    '''Function to extract and return the list of Science SPWs. Copied from analysisUtils.
    params:
        msmd: CASA msmd object used to obtain metadata of the MS.
        intent: (str) Intent of the dataset queried to obtain SPW list.
        tdm, fdm, sqld: (bool) Parameters passed to CASA's task msmd.almaspws. First two say whether
                        to consider TDM and FDM SPWs, third whether to consider SQLD SPWs.
    returns: List of SPWs
    '''
    spws = msmd.spwsforintent(intent)
    almaspws = msmd.almaspws(tdm=tdm,fdm=fdm,sqld=sqld)
    scienceSpws = np.intersect1d(spws,almaspws)
    return(list(scienceSpws))

#Copied over from analysisUtils
def onlineChannelAveraging(msmd, spws=None):
    """
    For Cycle 3-onward data, determines the channel averaging factor from
    the ratio of the effective channel bandwidth to the channel width.
    spw: a single value, or a list; if None, then uses science spws
    Returns: single value for a single spw, or a list for a list of spws
    -Todd Hunter
    """
    hanning_effBw = {1: 2.667, 2: 3.200, 4: 4.923, 8: 8.828, 16: 16.787}
    if spws is None:
        spws = getSpwList(msmd)
    if type(spws) != list:
        spws = [spws]
    Ns = list(hanning_effBw.keys())
    ratios = [hanning_effBw[i]/i for i in Ns]
    Nvalues = []
    for spw in spws:
        chanwidths = msmd.chanwidths(spw)
        nchan = len(chanwidths)
        if (nchan < 5):
            return 1
        chanwidth = abs(chanwidths[0])
        chaneffwidth = msmd.chaneffbws(spw)[0]
        ratio = chaneffwidth/chanwidth
        Nvalues.append(Ns[np.argmin(abs(ratios - ratio))])
    if (len(spws) == 1):
        return Nvalues[0]
    else:
        return Nvalues

#Obtain spectral setup
def getSpecSetup(myms, spwlist = []):
    '''Task to gather spectral setup information.
    myms: MS to be processed.
    spwlist: List of SPW to be included in queries, if left empty, all science SPWs
    will be considered.
    intentlist: List of intents to be included in the queries. By default is *OBSERVE_TARGET*.
    '''

    #Else read in the information from the MS
    #if spwlist is empty, get all science SPWs
    intentlist = ['*OBSERVE_TARGET#ON_SOURCE*', '*OBSERVE_TARGET#OFF_SOURCE*']
    msmd = casa_tools.msmd
    msmd.open(myms)
    if len(spwlist) == 0:
        spwlist = getSpwList(msmd)
    spwsetup = {}
    spwsetup['spwlist'] = spwlist
    spwsetup['intentlist'] = intentlist
    spwsetup['namesfor'] = msmd.fieldsforsources(asnames=True)
    spwsetup['scan'] = {}
    spwsetup['fieldname'] = {}
    spwsetup['fieldid'] = {}
    for intent in intentlist:
        spwsetup['scan'][intent] = list(msmd.scansforintent(intent))
        spwsetup['fieldname'][intent] = list(msmd.fieldsforintent(intent,asnames=True))
        spwsetup['fieldid'][intent] = list(msmd.fieldsforintent(intent,asnames=False))
    spwsetup['scifieldidoff'] = {}
    for fieldid in spwsetup['fieldid']['*OBSERVE_TARGET#ON_SOURCE*']:
        fieldname = spwsetup['namesfor'][str(fieldid)][0]
        listfieldnameoff = [item[0] for item in spwsetup['namesfor'].values() if (fieldname in item[0]) and ('OFF' in item[0])]
        if len(listfieldnameoff) == 1:
            fieldidoff = [i for i in spwsetup['namesfor'].keys() if listfieldnameoff[0] == spwsetup['namesfor'][i]][0]
            spwsetup['scifieldidoff'][str(fieldid)] = fieldidoff
        else:
            spwsetup['scifieldidoff'][str(fieldid)] = ''
    allscans = list(set(flattenlist([spwsetup['scan'][intent] for intent in intentlist])))
    spwsetup['allscans'] = allscans
    spwsetup['intent'] = {}
    for scan in allscans:
        spwsetup['intent'][scan] = [intent for intent in spwsetup['intentlist'] if scan in spwsetup['scan'][intent]]
    spwsetup['antids'] = msmd.antennasforscan(scan = spwsetup['scan'][intentlist[0]][0])
    spwsetup['antnames'] = np.array(msmd.antennanames(spwsetup['antids']))
    spwsetup['spwnames'] = np.array(msmd.namesforspws(spwlist))
    spwsetup['fdmspws'] = msmd.fdmspws()
    spwsetup['tdmspws'] = msmd.tdmspws()

    nchanperbb = [0, 0, 0, 0]

    for spwid in spwlist:
        spwsetup[spwid] = {}
        #Get SPW information: frequencies of each channel, etc.
        chanfreqs = msmd.chanfreqs(spw=spwid)
        nchan = len(chanfreqs)
        fcenter = (chanfreqs[int(nchan/2-1)]+chanfreqs[int(nchan/2)])/2.
        chansep = (chanfreqs[-1]-chanfreqs[0])/(nchan-1)
        spwsetup[spwid]['chanfreqs'] = chanfreqs
        spwsetup[spwid]['nchan'] = nchan
        spwsetup[spwid]['fcenter'] = fcenter
        spwsetup[spwid]['chansep'] = chansep
        spwsetup[spwid]['Nave'] = onlineChannelAveraging(msmd, spwid)
        #Get data descriptor for each SPW
        spwsetup[spwid]['ddi'] = msmd.datadescids(spw=spwid)[0]
        spwsetup[spwid]['npol'] = msmd.ncorrforpol(msmd.polidfordatadesc(spwsetup[spwid]['ddi']))
        #Get baseband for each SPW
        spwsetup[spwid]['BB'] = int(msmd.baseband(spwid))
        spwsetup[spwid]['BBname'] = 'BB_'+str(spwsetup[spwid]['BB'])
        spwsetup[spwid]['istdm'] = (spwid in spwsetup['tdmspws'])
        spwsetup[spwid]['nchan_high'] = nchan*5
        spwsetup[spwid]['chansep_high'] = chansep/5.
        spwsetup[spwid]['chanfreqs_high']  = chanfreqs[0] + (chansep/5.)*np.arange(nchan*5)
        spwsetup[spwid]['fcenter_high'] = (spwsetup[spwid]['chanfreqs_high'][int(nchan/2-1)]+spwsetup[spwid]['chanfreqs_high'][int(nchan/2)])/2.
        nchanperbb[spwsetup[spwid]['BB'] - 1] += spwsetup[spwid]['nchan']

    spwsetup['nchanperbb'] = nchanperbb
    for spwid in spwlist:
        spwsetup[spwid]['istdm2'] = (nchanperbb[spwsetup[spwid]['BB'] - 1] in [128, 256])
        spwsetup[spwid]['dosmooth'] = (nchanperbb[spwsetup[spwid]['BB'] - 1]*spwsetup[spwid]['npol'] in [256, 8192])
        if spwsetup[spwid]['dosmooth']:
            LOG.info('Spw %d in BB_%d (total Nchan within BB is %d, sp avg likely not applied).  dosmooth=True' % (spwid, spwsetup[spwid]['BB'], nchanperbb[spwsetup[spwid]['BB'] - 1]*spwsetup[spwid]['npol']))
        else:
            LOG.info('Spw %d in BB_%d (total Nchan within BB is %d, sp avg likely applied).  dosmooth=False' % (spwid, spwsetup[spwid]['BB'], nchanperbb[spwsetup[spwid]['BB'] - 1]*spwsetup[spwid]['npol']))

    msmd.close()

    return spwsetup

def getAntennaFlagFrac(ms, fieldid, spwid, spwsetup):
    '''Get flagging fraction for each antenna, in a vector listed ordered by order given in spwsetup dictionary.
    ms: Input MS
    fieldid: Field ID used to select data
    spwid: SPW used to select data
    spwsetup: Spectral setup dictionary, as obtained from getSpecSetup()
    '''
    af = casa_tools.agentflagger
    af.open(ms)
    af.selectdata(field = str(fieldid), spw = str(spwid))
    af.parsesummaryparameters()
    af.init()
    flag_stats_dict = af.run()
    af.done()
    antflag = flag_stats_dict['report0']['antenna']
    antflag_frac = [antflag[spwsetup['antnames'][antid]]['flagged']/antflag[spwsetup['antnames'][antid]]['total'] for antid in spwsetup['antids']]
    return antflag_frac

def getCalAtmData(ms: str, spws: list, spwsetup: dict):
    '''Funtion to extract Tsys, Trec, Tatm and tau data from the ASDM's CALATMOSPHERE table.
    param:
        ms: MS filename
        spws: List of SPWs to load
        spwsetup: Dictionary of metadata obtained from getSpecSetup()
    '''

    tb = casa_tools.table
    #Open CALATMOSPHERE table
    tb.open(os.path.join(ms, 'ASDM_CALATMOSPHERE'))
    #Get weather parameters
    LOG.debug("Start reading weather parameters from ASDM_CALATMOSPHERE table")
    tground_all = tb.getcol('groundTemperature')
    pground_all = tb.getcol('groundPressure')
    hground_all = tb.getcol('groundRelHumidity')
    LOG.debug("Done reading weather parameters from ASDM_CALATMOSPHERE table")
    #Get the spectra of the ATM measurements
    tmatm_all = {}
    tsys = {}
    trec = {}
    tau = {}
    antatm = {}
    for spwid in spws:
        minfreq = np.min(spwsetup[spwid]['chanfreqs'])
        maxfreq = np.max(spwsetup[spwid]['chanfreqs'])
        midfreq = 0.5*(minfreq+maxfreq)
        samebbspw = [s for s in spwsetup['spwlist'] if spwsetup[s]['BBname'] == spwsetup[spwid]['BBname']]
        subtb = tb.query('basebandName=="{0:s}" && syscalType=="TEMPERATURE_SCALE"'.format(str(spwsetup[spwid]['BBname'])))
        tmatm_all[spwid] = tb.getcol('startValidTime')
        #Get frequency vector and find section belonging to this SPW
        fullfreq = subtb.getcell('frequencySpectrum', 0)
        sectionmid = []
        freqsection = []
        chansec = []
        chanidx = 0
        for s in samebbspw:
            chansec.append([chanidx,chanidx+spwsetup[s]['nchan']])
            section = fullfreq[chanidx:chanidx+spwsetup[s]['nchan']]
            chanidx += spwsetup[s]['nchan']
            sectionmid.append(np.mean(section))
            freqsection.append(section)
        thissection = np.argsort(np.abs(np.array(sectionmid) - midfreq))[0]
        freq = freqsection[thissection]
        order = np.argsort(freq)
        startchan = chansec[thissection][0]
        endchan = chansec[thissection][1]
        #Load Tsys and Trx tables
        auxtsys = [subtb.getcell('tSysSpectrum', i) for i in range(subtb.nrows())]
        auxtrec = [subtb.getcell('tRecSpectrum', i) for i in range(subtb.nrows())]
        # (npols, nchantsys, nrowstsys) = np.shape(auxtsys)
        npols = auxtsys[0].shape[0]
        nrowstsys = len(auxtsys)
        tsys[spwid] = np.zeros((npols, spwsetup[spwid]['nchan'], nrowstsys))
        trec[spwid] = np.zeros((npols, spwsetup[spwid]['nchan'], nrowstsys))
        #Resample the curves to match the frequency of the data SPWs
        for pol in range(npols):
            for row in range(nrowstsys):
                tsysfit = CubicSpline(freq[order], auxtsys[row][pol][startchan:endchan][order], bc_type='not-a-knot')
                trecfit = CubicSpline(freq[order], auxtrec[row][pol][startchan:endchan][order], bc_type='not-a-knot')
                tsys[spwid][pol,:,row] = tsysfit(spwsetup[spwid]['chanfreqs'])
                trec[spwid][pol,:,row] = trecfit(spwsetup[spwid]['chanfreqs'])
        antatm[spwid] = subtb.getcol('antennaName')
        #To get the skyline list, pick index of first antenna, first entry of tau, for the first polarization
        #Resample according to the same procedure used for Tsys and Trx
        auxtau = subtb.getcell('tauSpectrum', 0)[0]
        taufit = CubicSpline(freq[order], auxtau[startchan:endchan][order], bc_type='not-a-knot')
        tau[spwid] = taufit(spwsetup[spwid]['chanfreqs'])
    tb.close()

    return (tground_all, pground_all, hground_all, tmatm_all, tsys, trec, tau, antatm)

def makeNANmetrics(fieldid, spwid, nmodels):
    ''' Returns a dummy metric resuls table used when the metrics cannot be really calculated, in order
    to be used a place holder and having the same structure as the output from the calcmetric() function.
    All the metric and metric error entries are np.nan value.
    params:
        fieldid: Field ID of field used in atmcorr() for best model identification.
        spwid: SPW used.
        nmodels: Number of models attempted.
    returns: Table given as dictionary with metric tables.
    '''

    metricdtypes = np.dtype([('maxabsdiff', float), ('maxabsdifferr', float), ('intabsdiff', float), ('intabsdifferr', float), ('intsqdiff', float), ('intsqdifferr', float)])
    metrics = {fieldid: {spwid: np.zeros(nmodels, dtype = metricdtypes)}}
    for k in range(nmodels):
        metrics[fieldid][spwid]['maxabsdiff'][k] = np.nan
        metrics[fieldid][spwid]['maxabsdifferr'][k] = np.nan
        metrics[fieldid][spwid]['intabsdiff'][k] = np.nan
        metrics[fieldid][spwid]['intabsdifferr'][k] = np.nan
        metrics[fieldid][spwid]['intsqdiff'][k] = np.nan
        metrics[fieldid][spwid]['intsqdifferr'][k] = np.nan
    return metrics

def makePlot(nu = None, tmavedata = None, skychansel = None, scisrcsel = None, bline = None,
             tau = None, title = None, output = None, isize = 300, psize = 2,
             highbuf = 0.5, lowbuf = 0.3, atmhighbuf = 0.05,
             diffsmoothbox = 1, ischosen = None, takediff = False, xlabel = None, ylabel = None):
    '''Function to produce time-averaged Real v/s Frequency scatter plot, optionally including several markers for
    sky line channel selection, science line channel selection, fitted baseline curve, atmospheric opacity
    curve. Additionally, data can be plotted in diff mode: plot Value(channel n+1) - Value(channel n)
    i.e. the derivative of the data to be plotted.
    params:
        nu: (numpy array) Array of channel frequencies (x-axis).
        tmavedata: (numpy array) Array of y-axis (Real value, or Amplitude) data.
        skychansel: (numpy boolean array) Data selection vector used to mark sky line selection channels.
        scisrcsel: (numpy boolean array) Data selection vector used to mark science line channels.
        bline: (numpy boolean array) Fitted baseline to be plotted on top of tmavedata.
        tau: (numpy boolean array) Opacity data.
        title: (str) Title for the plot.
        output: (str) Path and filename for output PNG image file.
        isize: (int) Number of DPI to be used when saving PNG file.
        psize: (int) Marker size for data points.
        lowbuf, highbuf: (float) Image y-axis margins at the lower and upper part, respectively, given as
                         a fraction of the data range in the y-axis.
        atmhighbuf: (float) Border to add to atmospheric transmission in the upper part of the plot, given as
                    a fraction of the transmission range of the opacity data.
        diffsmoothbox: (int) Size of boxcar smoothing applied to data, if required. Default of 1 means no smoothing.
        ischosen: (bool) True/False Whether this plot is for the selected model. If equal to True, will print string
                  "Applied" in upper right corner of the plot, otherwise will print "Discarded".
        takediff: (bool) True/False Whether to take a np.diff() of the data before plotting.
        xlabel: (str) x-axis label. If none given, defaults to "Freq [GHz]"
        ylabel: (str) y-axis label. If none given, defaults to "Corr Amp [Jy]"
                (or "Abs(Amp[i+1]-Amp[i])", if takediff=True)
    '''

    (npol, nchan) = np.shape(tmavedata)
    #Choose whether to plot data as-is or its derivative
    if takediff:
        ydata = np.ma.MaskedArray(np.zeros((npol, nchan-1)), mask=np.zeros((npol, nchan-1)))
        for ipol in range(npol):
            ydata[ipol] = np.ma.abs(np.ma.diff(tmavedata[ipol]))
            ydata.mask[ipol] = tmavedata.mask[ipol][1:]
        xdata = nu[1:]
        if scisrcsel is not None:
            seldata = scisrcsel[1:]
        else:
            seldata = None
        if ylabel is None:
            ylabel = 'Abs(Amp[i+1]-Amp[i])'
    else:
        ydata = tmavedata
        xdata = nu
        if scisrcsel is not None:
            seldata = scisrcsel
        else:
            seldata = None
        if ylabel is None:
            ylabel = 'Corr Amp [Jy]'
    #Also apply smoothing if requested
    if diffsmoothbox > 1:
        newnpol, newnchan = np.shape(ydata)
        newydata = np.ma.MaskedArray(np.zeros((newnpol, newnchan)), mask=np.zeros((newnpol, newnchan)))
        for ipol in range(npol):
            newydata[ipol] = smooth(ydata[ipol], diffsmoothbox)
            newydata.mask[ipol] = enlargesel(ydata.mask[ipol], diffsmoothbox)
        ydata = newydata
        if xlabel is None:
            xlabel = 'Freq [Ghz] (smooth:'+str(diffsmoothbox)+' ch)'
    elif xlabel is None:
        xlabel = 'Freq [Ghz]'

    #Calculate data limit for plot
    try:
        mindata = np.ma.min(ydata)
        maxdata = np.ma.max(ydata)
        datarange = np.abs(maxdata - mindata)
        ymin = mindata - lowbuf*datarange
        ymax = maxdata + highbuf*datarange
    except:
        LOG.warning('Could not determine normalization of data! Are all of them flagged??')
        datarange = 2.0
        ymin = -1.0
        ymax = 1.0
    xmin = np.min(xdata) - 0.02*(np.max(xdata)-np.min(xdata))
    xmax = np.max(xdata) + 0.02*(np.max(xdata)-np.min(xdata))

    #Plot data before correction
    fig = matplotlib.figure.Figure(figsize=(8, 6), dpi=isize)
    ax1 = fig.add_subplot(111)
    ax1.set_title(title)
    for ipol in range(npol):
        thisstyle = ('blue' if (ipol == 0) else 'red')
        pol_label = ('Pol XX' if (ipol == 0) else 'Pol YY')
        ax1.plot(xdata, ydata[ipol], '.', color=thisstyle, markersize=psize, label=pol_label)
        if seldata is not None:
            ax1.plot(xdata[seldata], ydata[ipol][seldata], '.', color='green', markersize=psize)
        if bline is not None:
            ax1.plot(nu, bline[ipol], '--', color=thisstyle)
    ax1.legend(loc = 'upper left')
    ax1.set_xlabel(xlabel)
    ax1.set_ylabel(ylabel)
    ax1.set_xlim((xmin,xmax))
    ax1.set_ylim((ymin,ymax))
    #Add Accepted/Discarded text
    if ischosen is not None:
        if ischosen:
            ax1.text(0.15*xmin+0.85*xmax, 0.1*ymin+0.9*ymax, 'Applied', fontsize = 14, color = 'black', fontweight = 'bold')
        else:
            ax1.text(0.15*xmin+0.85*xmax, 0.1*ymin+0.9*ymax, 'Discarded', fontsize = 12, color = 'gray', fontweight = 'normal')

    #Plot atmospheric transmission and skyline windows, if provided
    if tau is not None:
        transm = 100.0*np.exp(-1.0*tau)
        mintr = np.min(transm)
        maxtr = np.max(transm)
        trrange = maxtr - mintr
        lowbuf2 = (1 + atmhighbuf)*(1+lowbuf)/highbuf
        ymin2 = mintr - lowbuf2*trrange
        ymax2 = maxtr + atmhighbuf*trrange
        ywin = ymin2 + 0.1*lowbuf2*trrange
        ywintxt = ymin2 + 0.05*lowbuf2*trrange
        ax2 = ax1.twinx()
        if np.sum(skychansel) > 0:
            skyline_channels = np.where(skychansel)[0]
            # detect non-contiguous boundaries
            skyline_boundaries = np.where(np.diff(skyline_channels) > 1)[0]
            left_edge = [0] + (skyline_boundaries + 1).tolist()
            right_edge = skyline_boundaries.tolist() + [len(skyline_channels) - 1]
            # draw channel range for each skyline
            for imin, imax in zip(left_edge, right_edge):
                minskychan = skyline_channels[imin]
                maxskychan = skyline_channels[imax]
                if nu[0] < nu[-1]:
                    # USB
                    chan_label = f'{minskychan}~{maxskychan}'
                else:
                    # LSB
                    chan_label = f'{maxskychan}~{minskychan}'
                sel = skychansel[minskychan:maxskychan + 1]
                ax2.plot(nu[minskychan:maxskychan + 1], ywin*np.ones(len(sel)), 's', color='black', markersize=psize)
                ax2.text(np.min(nu[minskychan:maxskychan + 1]), ywintxt, chan_label, fontsize = 9, color = 'black', fontweight = 'normal')
        ax2.plot(nu, transm, linestyle='solid', linewidth=1.0, color='magenta')
        ax2.set_ylim((ymin2, ymax2))
        ax2.set_yticks([mintr, 0.5*(maxtr+mintr), maxtr])
        ax2.set_ylabel('% ATM Transmission', color = 'magenta')

    fig.savefig(output, dpi=isize)
    fig.clear()

    return


def select_and_yield(
        msname: str,
        datacolumn: str,
        data_desc_id: int,
        field_id: int,
        state_id_list: np.ndarray
) -> Generator[tuple[np.ndarray, np.ndarray], None, None]:
    """Select data from MS and yield data array with mask.

    Args:
        msname: Name of the MS
        datacolumn: Name of the data column to read (e.g., 'DATA',
            'CORRECTED_DATA')
        data_desc_id: Data description id for data selection
        field_id: Field id for data selection
        state_id_list: List of state ids for data selection

    Yields:
        Maked data array. Data is read from data column while
        masks are taken from FLAG column.
    """
    tb = casa_tools.table
    tb.open(msname)
    querystr = f'DATA_DESC_ID in {data_desc_id} && FIELD_ID in {field_id}'
    querystr += f' && NOT FLAG_ROW && STATE_ID IN {state_id_list.tolist()}'
    LOG.info('Reading data for TaQL query: '+querystr)
    subtb = tb.query(querystr)
    try:
        for i in range(subtb.nrows()):
            data = subtb.getcell(datacolumn, i).real
            flag = subtb.getcell('FLAG', i)

            mdata = np.ma.masked_array(data, mask=flag, fill_value=0.0)
            data_shape = mdata.shape
            if len(data_shape) == 2:
                # If data is 2D, add a third dimension of size 1
                mdata = mdata.reshape((data_shape[0], data_shape[1], 1))

            yield mdata
    finally:
        subtb.close()
        tb.close()


def get_stats_and_shape(
        msname: str,
        datacolumn: str,
        data_desc_id: int,
        field_id: int,
        state_id_list: np.ndarray
) -> tuple[np.ndarray, float, np.ndarray]:
    """Compute metrics from selected data in the given MS.

    Core part of this function computes the mean and standard deviation
    for three-dimensional data (npol, nchan, nrow) by iterating over
    the data in the Measurement Set (MS) row-by-row to save memory usage.
    The implementation emulates the behavior of np.ma.mean and np.ma.std.

    Args:
        msname: Name of the MS
        datacolumn: Name of the data column to read (e.g., 'DATA',
            'CORRECTED_DATA')
        data_desc_id: Data description id for data selection
        field_id: Field id for data selection
        state_id_list: List of state ids for data selection

    Returns:
        A tuple containing:
        - time averaged data (masked array)
        - Normalization value for metrics
        - Updated boolean mask array indicating sky lines that are not masked
    """
    LOG.debug("get_stats_and_shape: Reading data row-by-row to save memory usage")
    it = select_and_yield(msname, datacolumn, data_desc_id, field_id, state_id_list)
    data = next(it)
    npol, nchan, nrow = data.shape
    # The following code emulates the behavior of np.ma.mean and np.ma.std
    data_data = np.ma.filled(data, 0.0)
    data_sum = np.sum(data_data, axis=2)
    data_sqsum = np.sum(data_data * data_data, axis=2)
    num_data = np.sum(np.logical_not(data.mask), axis=2)
    for data in it:
        nrow += data.shape[2]
        data_data = np.ma.filled(data, 0.0)
        data_sum += np.sum(data_data, axis=2)
        data_sqsum += np.sum(data_data * data_data, axis=2)
        num_data += np.sum(np.logical_not(data.mask), axis=2)

    data_mean = np.ma.masked_array(data_sum, num_data == 0, fill_value=0.0) / num_data
    data_sqmean = np.ma.masked_array(data_sqsum, num_data == 0, fill_value=0.0) / num_data
    data_std = np.sqrt(data_sqmean - (data_mean * data_mean)) / np.sqrt(nrow)

    data_shape = (npol, nchan, nrow)

    return data_mean, data_std, data_shape


def get_metric(
        msname: str,
        datacolumn: str,
        data_desc_id: int,
        field_id: int,
        state_id_list: np.ndarray,
        skychansel: np.ndarray
) -> tuple[np.ndarray, float, np.ndarray]:
    """Compute metrics from selected data in the given MS.

    Core part of this function computes the mean and maximum
    for three-dimensional data (npol, nchan, nrow) by iterating over
    the data in the Measurement Set (MS) row-by-row to save memory usage.
    The implementation emulates the behavior of np.ma.mean and np.ma.max.

    Args:
        msname: Name of the MS
        datacolumn: Name of the data column to read (e.g., 'DATA',
            'CORRECTED_DATA')
        data_desc_id: Data description id for data selection
        field_id: Field id for data selection
        state_id_list: List of state ids for data selection
        skychansel: Boolean mask array indicating sky lines

    Returns:
        A tuple containing:
        - time averaged data (masked array)
        - Normalization value for metrics
        - Updated boolean mask array indicating sky lines that are not masked
    """
    LOG.debug("get_metric: Reading data row-by-row to save memory usage")
    it = select_and_yield(msname, datacolumn, data_desc_id, field_id, state_id_list)
    data = next(it)
    npol, nchan, nrow = data.shape
    # The following code emulates the behavior of np.ma.mean and np.ma.max
    data_data = np.ma.filled(data, 0.0)
    data_sum = np.sum(data_data, axis=2)
    data_absmax = np.max(np.abs(data_data), axis=2)
    num_data = np.sum(np.logical_not(data.mask), axis=2)
    for data in it:
        nrow += data.shape[2]
        data_data = np.ma.filled(data, 0.0)
        data_sum += np.sum(data_data, axis=2)
        num_data += np.sum(np.logical_not(data.mask), axis=2)
        _absmax = np.max(np.abs(data_data), axis=2)
        data_absmax = np.maximum(data_absmax, _absmax)

    # Pre-correction average
    precorravedataon = np.ma.masked_array(data_sum, num_data == 0, fill_value=0.0) / num_data
    maskedchans = np.any(precorravedataon.mask, axis=0)

    skychansel[maskedchans] = False

    # Try to calculate the normalizing value for the metrics
    # If it cannot calculate it, fill default value of 1
    # similar thing for plot ranges
    try:
        # metricnorm = np.ma.max(np.ma.abs(normsample))
        metricnorm = np.ma.max(data_absmax[:, skychansel])
    except Exception:
        LOG.warning('Could not determine normalization of data! Are all of them flagged??')
        metricnorm = 1.0

    if metricnorm is np.ma.masked:
        metricnorm = 1.0

    return precorravedataon, metricnorm, skychansel


def atmcorr(ms, datacolumn = 'CORRECTED_DATA', iant = 'auto', atmtype = 1,
            maxalt = 120.0, lapserate = -5.6, scaleht = 2.0,
            jyperkfactor = None, dobackup = False, forcespws = None, forcefield = None, forcemetricline = None,
            maxonlyspw = False, minpeaklevel = 0.05, timestamp = None, plotsfolder = None, diffsmooth = 0.002,
            psize = 2, isize = 300, defatmtype = 1, defmaxalt = 120, deflapserate = -5.6, defscaleht = 2.0,
            decisionmetric = 'intsqdiff'):
    ''' Task to apply CSV-3320 correction for atmospheric lines.
    Parameter list:
    ms: (first argument) MS file to be processed
    output: Compute the metrics over the skyline residuals and return them
    for best parameter evaluation. Output in this case is a tuple (models, metrics) where models is an array
    of the models used, and metrics is a dictionary containing arrays of metric results for each one
    of the models for each field and SPW, structured like: metrics[FIELDID][SPW]
    Keyword arguments:
    datacolumn: Column to apply correction to, options: 'DATA', 'CORRECTED_DATA'(default)
    iant: Antenna number to get pointing direction (antenna having mount issues should
    be avoided). Also used to test atmospheric residuals. Default is 0.
    jyperkfactor: Dictionary of Jy/K factors for each EB, antenna and SPW. Default will
    assume a factor of 1.0. To be obtained from getJyperKfromCSV() function
    dobackup: Whether to do a backup of the MS before applying the correction.
    (True/False) Default is True.
    forcespws: Force the list of SPWs to process. If not specified, task will do all SPWs.
    forcefield: Force the FIELD ID to process. If not specified task will pick the first one.
    maxonlyspw: Whether to select the SPW with largest skyline only. (Default: True)
    timestamp: Timestamp string to use for the model plots folder
    plotsfolder: Explicit folder name for model plots folder. If given, timestamp will be ignored.
    Following parameters define the atmospheric model. For runmode = 'try', the parameters below
    can be vectors, in that case the task will try all combinations and return a tuple of the list
    of models and the results of the metrics for each model on the residual of skylines.
    amttype: Atmosphere type paremeter for model in at module (1: tropical, 2: mid lat summer,
    3: mid lat winter, etc). Default is 2
    maxalt: maxAltitude parameter for model, in km. default is 120 (km)
    lapserate: Lapse Rate dTem_dh parameter for at (lapse rate; K/km). Default is -5.6
    scaleht: h0 parameter for at (water scale height; km). Default is 2.0
    '''
    qa = casa_tools.quanta
    ms = str(ms)
    #Do a backup of the MS if requested
    backupms = ms.replace('.ms','.ms.backup')
    if dobackup and not os.path.exists(backupms):
        os.system('cp -r '+ms+' '+backupms)
    #If there is no timestamp, generate new one
    if timestamp is None:
        timestamp = getTimeStamp()
    #If there is no name for the results file, create one
    if plotsfolder is None:
        plotsfolder = 'modelplots_'+timestamp
    #Make plot models folder, if needed
    if not os.path.exists(plotsfolder):
        os.system('mkdir '+plotsfolder)

    ################################################################
    ### Get metadata
    ################################################################
    LOG.info('Obtaining metadata for MS: '+ms)
    spwsetup = getSpecSetup(ms)
    #chanfreqs = {}
    msmd = casa_tools.msmd
    msmd.open(ms)
    #Get data times for OBSERVE_TARGET
    tmonsource = msmd.timesforintent('OBSERVE_TARGET#ON_SOURCE')
    tmoffsource = msmd.timesforintent('OBSERVE_TARGET#OFF_SOURCE')
    #Make table of subscans while on source
    onsourcetab = segmentEdges(tmonsource, 5.0, 'onsource')
    #Initialize list of all SPWs to work on
    spws = spwsetup['spwlist']
    metricskylineids = 'all'
    LOG.info('>>> forcespws='+str(forcespws)+' >>> metricskylineids='+str(forcemetricline))
    LOG.info('>>> spws='+str(spws)+' >>> metricskylineids='+str(metricskylineids))
    msmd.close()
    #Set fields to correct
    if (forcefield is not None) and (type(forcefield) == int):
        fieldid = forcefield
    if (forcefield is not None) and (type(forcefield) == str) and forcefield.isdigit():
        fieldid = int(forcefield)
    else:
        #We could not receive the fieldid from calling method, default to first field
        fieldid = spwsetup['fieldid']['*OBSERVE_TARGET#ON_SOURCE*'][0]
    bnd = (np.diff(tmoffsource)>1)
    w1 = np.append([True], bnd)
    w2 = np.append(bnd, [True])
    tmoffsource = (tmoffsource[w1]+tmoffsource[w2])/2.  ### midpoint of OFF subscan

    ################################################################
    ### Get atmospheric parameters for ATM
    ################################################################
    LOG.info('Obtaining atmospheric parameters for MS: '+ms)
    tb = casa_tools.table
    tb.open(os.path.join(ms, 'ASDM_CALWVR'))
    LOG.debug("Start reading water data from ASDM_CALWVR table")
    tmpwv_all = tb.getcol('startValidTime')
    pwv_all = tb.getcol('water')
    LOG.debug("Done reading water data from ASDM_CALWVR table")
    tb.close()

    #Open CALATMOSPHERE table
    (tground_all, pground_all, hground_all, tmatm_all, tsys, trec, tau, antatm) = getCalAtmData(ms, spws, spwsetup)
    tmatm = np.unique(tmatm_all[spws[0]])

    #Search for sky lines
    skylines = {}
    for spwid in spws:
        skylines[spwid] = getskylines(tau[spwid], spwid, spwsetup, fraclevel = 0.3, minpeaklevel = minpeaklevel)

    #Select SPWs to process
    spwstoprocess = []
    if forcespws is None:
        for spwid in spws:
            #If there is at least one skyline in this SPW, add this spw to the ones to be processed
            if (skylines[spwid]['npeak'] > 0):
                spwstoprocess.append(spwid)
    elif (forcespws is not None) and (type(forcespws) == list):
        spwstoprocess = forcespws
    elif (forcespws is not None) and (type(forcespws) == int):
        spwstoprocess = [forcespws]
    else:
        spwstoprocess = []
    LOG.info('initial spwstoprocess='+str(spwstoprocess))

    #If only one SPW is to be processed, pick the best one
    if (len(spwstoprocess) > 0) and (forcemetricline is None) and maxonlyspw:
        (bestspw, bestpeak) = gradeskylines(skylines)
        spwstoprocess = [bestspw]
        metricskylineids = [bestpeak]
    elif (len(spwstoprocess) > 0) and (forcemetricline is None) and not maxonlyspw:
        (bestspw, bestpeak) = gradeskylines(skylines)
        spwstoprocess = [bestspw]
        metricskylineids = 'all'
    if (len(spwstoprocess) > 0) and (forcemetricline is not None) and (type(forcemetricline) == list):
        metricskylineids = forcemetricline
    if (len(spwstoprocess) > 0) and (forcemetricline is not None) and (type(forcespws) == int):
        metricskylineids = [forcemetricline]
    LOG.info('selecting spwstoprocess='+str(spwstoprocess)+' metricskylineids='+str(metricskylineids))
    #Smoothing box for diff metrics
    if (len(spwstoprocess) > 0):
        diffsmoothbox = max(1,int(np.round(diffsmooth*np.max([spwsetup[s]['nchan'] for s in spwstoprocess]))))
    else:
        diffsmoothbox = 1

    ################################################################
    ### Define list of models to try
    ################################################################
    defmodel = (defatmtype, defmaxalt, deflapserate, defscaleht)
    if 'int' in str(type(atmtype)):
        atmtype = [atmtype]
    if ('int' in str(type(maxalt))) or ('float' in str(type(maxalt))):
        maxalt = [maxalt]
    if ('int' in str(type(lapserate))) or ('float' in str(type(lapserate))):
        lapserate = [lapserate]
    if ('int' in str(type(scaleht))) or ('float' in str(type(scaleht))):
        scaleht = [scaleht]
    modtypes = np.dtype([('atmtype', int), ('maxalt', float), ('lapserate', float), ('scaleht', float)])
    models = np.array([model for model in product(atmtype, maxalt, lapserate, scaleht)], dtype = modtypes)
    nmodels = len(models)
    metricdtypes = np.dtype([('maxabsdiff', float), ('maxabsdifferr', float), ('intabsdiff', float), ('intabsdifferr', float), ('intsqdiff', float), ('intsqdifferr', float)])
    LOG.info('fieldid: '+str(fieldid)+' spwstoprocess: '+str(spwstoprocess))
    #Create metric output dictionary
    if (len(spwstoprocess) > 0) and (jyperkfactor is not None):
        #Case where we have at least one skyline available
        LOG.info('metricskylineids: '+str(metricskylineids))
        metrics = {fieldid: {spwid: np.zeros(nmodels, dtype = metricdtypes) for spwid in spwstoprocess}}
    #If no peak, abort process!!
    else:
        #We either have no skylines or no jy/K factor. Return the correct message
        if len(spwstoprocess) == 0:
            LOG.info('No skylines! Reverting to default model...')
        if jyperkfactor is None:
            LOG.info('No Jy/K factor!! Cannot perform calculation, reverting to default model...')
        spwid = spws[0]
        metrics = makeNANmetrics(fieldid, spwid, nmodels)
        bestmodels = defmodel
        fitstatus = 'defaultmodel'
        return (bestmodels, models, metrics, fitstatus, spwstoprocess, metricskylineids)

    pwv, tground, pground, hground = [], [], [], []
    for tt in tmatm:
        deltat = abs(tmpwv_all-tt)
        pwv.append(np.median(pwv_all[deltat==deltat.min()]))
        tground.append(np.median(tground_all[tmatm_all==tt]))
        pground.append(np.median(pground_all[tmatm_all==tt]))
        hground.append(np.median(hground_all[tmatm_all==tt]))
        LOG.info('PWV = %fm, T = %fK, P = %fPa, H = %f%% at %s' % (pwv[-1], tground[-1], pground[-1], hground[-1], qa.time('%fs' % tt, form='fits')[0]))

    ################################################################
    ### Looping over spws
    ################################################################
    LOG.info('start processing '+ms+' ...')
    LOG.info('will go over SPWs: '+str(spwstoprocess))

    ################################################################
    ## Apply correction using all the different models
    ################################################################

    tmpfolder = 'tmpapply_'+timestamp
    os.system('mkdir '+tmpfolder)
    tmpspwstr = ','.join([str(s) for s in spwstoprocess])
    #If for the test field we have a separate OFF position, create list with both
    if len(spwsetup['scifieldidoff'][str(fieldid)]) > 0:
        testfields = ','.join([str(s) for s in sorted([str(fieldid)]+[spwsetup['scifieldidoff'][str(fieldid)]])])
    else:
        testfields = str(fieldid)
    testspws = ','.join([str(s) for s in spwstoprocess])
    #Split out the relevant fields and SPWs to a smaller MS for testing models
    testms = ms + '.modeltest'

    #Select antenna to be used, if not selected
    if (type(iant) == int) or ((type(iant) == str) and iant.isnumeric()):
        iantsel = int(iant)
        LOG.info('Test data selected forced to use antenna {0:d} ({1:s})'.format(iantsel,spwsetup['antnames'][iantsel]))
    else:
        antflagfrac = getAntennaFlagFrac(ms, testfields, spwid, spwsetup)
        iantsel = np.argsort(antflagfrac)[0]
        LOG.info('Test data selected automatically with antenna {0:d} ({1:s})'.format(iantsel,spwsetup['antnames'][iantsel]))

    #String with data column to be used in sdatmcor command
    if datacolumn == 'CORRECTED_DATA':
        sddatacolumn = 'corrected'
    else:
        sddatacolumn = 'float_data'

    #cycle over all models, calling sdatmcor
    for k in range(nmodels):
        for spwid in spwstoprocess:
            strmodel = '{0:d}/{1:d}: (atmType,maxAlt,scaleht,lapserate)=({2:d},{3:.2f}km,{4:.2f}km,{5:.2f}K/km)'.format(k+1, nmodels, models['atmtype'][k], models['maxalt'][k], models['scaleht'][k], models['lapserate'][k])
            LOG.info('Correcting data with model '+strmodel)
            outfname = tmpfolder+'/'+ms.replace('.ms','.spw'+str(spwid)+'.model'+str(k)+'.ms')
            task_args = dict(
                infile=ms, datacolumn=sddatacolumn, outfile=outfname,
                overwrite=False, spw=str(spwid), outputspw=str(spwid),
                antenna = str(iantsel)+'&&'+str(iantsel), field = testfields,
                gainfactor=jyperkfactor[ms][str(spwid)],
                dtem_dh=str(models['lapserate'][k])+'K/km', h0=str(models['scaleht'][k])+'km',
                atmtype=int(models['atmtype'][k]), atmdetail=False
            )
            sdatmcor_task = casa_tasks.sdatmcor(**task_args)
            sdatmcor_task.execute()

    #Open uncorrected data to measure skylines and presence of science target
    tb.open(ms + '/STATE')
    tb_on = tb.query('OBS_MODE ~ m/^OBSERVE_TARGET#ON_SOURCE/')
    state_ids_on = tb_on.rownumbers()
    tb_on.close()
    tb.close()

    metricnorm_per_spw = {}
    revised_skychansel_per_spw = {}

    for spwid in spwstoprocess:
        LOG.info('Processing spw '+str(spwid))
        nu = spwsetup[spwid]['chanfreqs']/(1.e+09)

        ################################################################
        ### Calculate and apply correction values
        ################################################################
        # Narrow sky channels selection for measuring the metrics
        skychansel = skysel(skylines[spwid], linestouse = metricskylineids)

        LOG.debug("Start reading_data_spw%d", spwid)
        precorravedataon, metricnorm, skychansel = get_metric(
            ms, datacolumn, spwsetup[spwid]['ddi'], fieldid, state_ids_on,
            skychansel
        )
        metricnorm_per_spw[spwid] = metricnorm
        revised_skychansel_per_spw[spwid] = skychansel
        LOG.debug("Done reading_data_spw%d", spwid)

        npol = precorravedataon.shape[0]

        #If we are left with no channels with skylines, we are in trouble
        if np.sum(skychansel) == 0:
            LOG.info('Could not select skyline channels! Aborting...')
            metrics = makeNANmetrics(fieldid, spwid, nmodels)
            bestmodels = defmodel
            fitstatus = 'defaultmodel'
            return (bestmodels, models, metrics, fitstatus, spwstoprocess, metricskylineids)

        #Plot data before correction
        makePlot(nu=nu, tmavedata=precorravedataon, skychansel=skychansel, tau=tau[spwid],
                 title=strmodel, diffsmoothbox=1, takediff=False, ischosen=None, isize = isize, psize = psize,
                 output=plotsfolder+'/'+ms+'.field'+str(fieldid)+'.spw'+str(spwid)+'.nocorr.png')

    #Lists of plots to do after looping over all models
    plotlist = []

    #Open uncorrected data to measure skylines and presence of science target
    for spwid in spwstoprocess:
        #cycle over all models
        for k in range(nmodels):
            strmodel = '{0:d}/{1:d}: ({2:d},{3:.2f}km,{4:.2f}km,{5:.2f}K/km)\nEB:{6:s}\nSPW:{7:s}, Field:{8:s}'.format(k+1, nmodels, models['atmtype'][k], models['maxalt'][k], models['scaleht'][k], models['lapserate'][k], ms, str(spwid), spwsetup['namesfor'][str(fieldid)][0])
            LOG.info('Going over model '+strmodel)
            msk = tmpfolder+'/'+ms.replace('.ms','.spw'+str(spwid)+'.model'+str(k)+'.ms')

            LOG.info('Processing spw '+str(spwid))
            nu = spwsetup[spwid]['chanfreqs']/(1.e+09)

            ################################################################
            ### Read corrected data for model k
            ################################################################
            LOG.debug("Start reading_data_spw%d_model%d", spwid, k)
            tmavedataonk, tmstddataonk, shapek = get_stats_and_shape(
                msk, "DATA", spwsetup[spwid]['ddi'], fieldid, state_ids_on
            )
            npolk, nchank, nrowk = shapek
            LOG.debug("Done reading_data_spw%d_model%d", spwid, k)

            #Plot corrected data with baseline fit, etc.
            skychansel = revised_skychansel_per_spw[spwid]
            plotlist.append({'nu': nu, 'tmavedata': tmavedataonk, 'skychansel': skychansel,
                             'tau': tau[spwid], 'title': 'Model '+strmodel, 'diffsmoothbox': 1,
                             'takediff': False, 'ischosen': False,
                             'isize': isize, 'psize': psize,
                             'output': plotsfolder+'/'+ms+'.field'+str(fieldid)+'.spw'+str(spwid)+'.model.'+str(k)+'.png'})

            #Select sample data for metrics
            metricnorm = metricnorm_per_spw[spwid]
            selected_channels = np.where(skychansel)[0]
            boundary = np.append([0], np.where(np.diff(selected_channels) > 1)[0] + 1)
            if boundary[-1] < len(selected_channels):
                boundary = np.append(boundary, [len(selected_channels)])
            for b_i, b_j in pairwise(boundary):
                _chansel = selected_channels[b_i:b_j]
                skysample = tmavedataonk[:,_chansel]/metricnorm
                skysamplesigma = tmstddataonk[:,_chansel]/(metricnorm*np.sqrt(nrowk))
                #Calculate metrics
                metricdtype_list = ["maxabsdiff", "intabsdiff", "intsqdiff"]
                resultdict = calcmetric(skysample, skysamplesigma, metrictype_list=metricdtype_list, smoothbox = diffsmoothbox)
                for metric_key, metric_result in resultdict.items():
                    metric_value, metric_error = metric_result
                    metrics[fieldid][spwid][metric_key][k] += metric_value
                    metrics[fieldid][spwid][f"{metric_key}err"][k] += metric_error

    #Pick best model
    chosenspw = spwstoprocess[0]
    chosenmetric = metrics[fieldid][chosenspw][decisionmetric]
    LOG.info('for ms: {0:s}, chosenmetric = {1:s}'.format(ms, str(chosenmetric)))
    if not np.any(np.isnan(chosenmetric)):
        idxbestmodel = np.argsort(chosenmetric)[0]
        bestmodels = models[idxbestmodel]
        fitstatus = 'bestfitmodel'
    else:
        idxbestmodel = None
        bestmodels = defmodel
        fitstatus = 'defaultmodel'
    #Set best model plot parameter as "Accepted"
    if idxbestmodel is not None:
        plotlist[idxbestmodel]['ischosen'] = True

    #Create all model plots
    for idx in range(len(plotlist)):
        makePlot(**plotlist[idx])

    return (bestmodels, models, metrics, fitstatus, spwstoprocess, metricskylineids)

def getJyperKfromCSV(jyperkfile = 'jyperk.csv', mssuffix = ''):
    ''' Get Jy/K factor from the indicated CSV file.
    Assumes columns in the file are MS,Antenna,Spwid,Polarization,Factor
    and that the first line is the header.
    '''
    if not os.path.exists(jyperkfile):
        return None
    mslist = []
    spwlist = []
    jyperklist = []
    f = open(jyperkfile, 'r')
    for i, line in enumerate(f):
        if i > 0:
            (ms, ant, spw, pol, jyperk) = line.split(',')
            mslist.append(ms + mssuffix)
            spwlist.append(spw)
            jyperklist.append(float(jyperk.replace('\n','')))
    mslist = np.array(mslist)
    spwlist = np.array(spwlist)
    jyperklist = np.array(jyperklist)
    uniquems = np.unique(mslist)
    uniquespw = np.unique(spwlist)
    output = {ms:{spw:np.mean(jyperklist[np.all([mslist == ms, spwlist == spw], axis = 0)])
               for spw in uniquespw} for ms in uniquems}

    return output

def getJyperKfromCaltable(mslist, context):
    '''Get Jy/K factors from pipeline caltables. Will determine the MS list and tables from pipeline context.

    This method could raise RuntimeError when Jy/K caltable associated with any of given MS does not exist.
    '''
    tb = casa_tools.table
    callib = context.callibrary

    def _extract_jyperk_table(vis: str) -> str:
        """Extract name of Jy/K caltable from callibrary.

        Args:
            vis: name of MS

        Raises:
            RuntimeError: No Jy/K caltable is available.
            RuntimeError: Found more than one Jy/K caltable.

        Returns:
            Name of Jy/K caltable
        """
        caltables = callib.get_calstate(callibrary.CalTo(vis)).get_caltable(caltypes='amp')
        # there should be only one Jy/K caltable in callibrary
        if len(caltables) == 0:
            raise RuntimeError(f'No Jy/K caltable for {os.path.basename(vis)}.')
        elif len(caltables) > 1:
            raise RuntimeError(f'Detected more than one Jy/K caltables for {os.path.basename(vis)}. Something went wrong.')
        return caltables.pop()

    jyperktables = [_extract_jyperk_table(vis) for vis in mslist]

    output = {}
    for i, ms in enumerate(mslist):
        #Get SPW info for this MS
        spwsetup = getSpecSetup(ms)
        #Open Jy/K Amp table
        tb.open(jyperktables[i])
        LOG.debug("Start reading k2jy caltable")
        ant1 = tb.getcol('ANTENNA1')
        spw = tb.getcol('SPECTRAL_WINDOW_ID')
        cparam = tb.getcol('CPARAM')
        LOG.debug("Done reading k2jy caltable")
        jyperk = 1./np.square(np.real(cparam[0][0]))
        tb.close()
        output[ms] = {str(thisspw): np.mean(jyperk[(spw == thisspw)]) for thisspw in spw if thisspw in spwsetup['spwlist']}
    return output

def selectModelParams(mslist, context = None, jyperkfactor = None, decisionmetric = 'intsqdiff',
                      iant = 'auto', atmtype = [1,2,3,4], maxalt = [120],
                      lapserate = [-5.6], scaleht = [2.0], resultsfile = None, plotsfolder = None,
                      forcespws = None, forcefield = None, forcemetricline = None, maxonlyspw = False, minpeaklevel = 0.05,
                      timestamp = None, diffsmooth = 0.002, psize = 2, isize = 300,
                      defatmtype = 1, defmaxalt = 120, deflapserate = -5.6, defscaleht = 2.0):
    '''
    Positional parameters: mslist, context
    mslist: List of MS filenames to be processed.
    context: Pipeline context associated to this reduction.
    decisionmetric: Metric to use to take the decision on best model selection,
    options:'maxabs' (Maximum of absolute residual value, calculated after baseline subtraction),
            'intabs' (integral of absolute residual value, calculated after baseline subtraction),
            'maxabsdiff' (Maximum absolute value of residual derivative)
            'intabsdiff' (integral of absolute value of residual derivative)
            'intsqdiff' (integral of square value of residual derivative)
    Quantities are calculate over a selection of channels around the skylines.
    iant, atmtype, maxalt, lapserate, scaleht: see parameters description in atmcorr()
    defatmtype, defmaxalt, deflapserate, defscaleht: Parameters for default model in case no best fit is possible.
    minpeaklevel: Comparative minimum depth of an atmospheric line (as measured in the optical depth tau)
                  to be considered while searching for sky lines. Will only consider lines above this threshold.
                  This parameters is given in units relative to the median value of tau over the SPW.
    diffsmooth: Size of smoothing box applied during the calculation of the metrics that use derivatives.
                Size if given as a fraction of SPW.
    psize, isize: Point size and image size used for making diagnostic plots.
    resultsfile: Text output file containing models, metrics calculated and chosen best model.
    '''

    #Obtain Jy/K factor
    if (jyperkfactor is None) and (context is not None):
        #from context
        jyperkfactor = getJyperKfromCaltable(mslist, context)
    elif (jyperkfactor is None) and (context is None):
        LOG.warning('Neither jy/K factor dictionary nor pipeline context given as input!!')
        LOG.warning('Could not measure atmospheric line residuals, exiting to default...')

    #Output dictionaries
    models = {}
    metrics = {}
    bestmodels = {}
    fitstatus = {}
    #Default model
    #Set default atmospheric model in case determination is not possible
    defmodel = (defatmtype, defmaxalt, deflapserate, defscaleht)

    #If there is no timestamp, generate new one
    if timestamp is None:
        timestamp = getTimeStamp()
    #If there is no name for the results file, create one
    if resultsfile is None:
        resultsfile = 'modelparam_'+timestamp+'.txt'
    #Get info from first MS
    LOG.info('Obtaining metadata for First MS: '+mslist[0])
    spwsetup1 = getSpecSetup(mslist[0])
    #Set fields to correct
    if (forcefield is None) and (context is not None):
        #Try to obtain representative Field ID, if not possible,
        #the task will just pick first Field ID
        msobj = context.observing_run.get_ms(mslist[0])
        repfield, repspw = msobj.get_representative_source_spw()
        forcefield = [f for f in spwsetup1['namesfor'].keys() if spwsetup1['namesfor'][f] == repfield][0]
    elif (forcefield is None) and (context is None):
        #We could not get the fieldid from the context, default to first field
        LOG.info('No context to obtain the representative field from! using first field...')
        forcefield = None
    elif (forcefield is not None) and (type(forcefield) == int):
        fieldid = forcefield
    else:
        LOG.info('Could not understand FIELDID='+str(forcefield)+'! Taking first instead...')
        forcefield = None

    #If the SPW and/or the metric line is force to a value, will keep using it for all MSs
    spwstoprocess = forcespws
    metricskylineids = forcemetricline
    #Execute correction for all MSes
    for ms in mslist:
        (bestmodels[ms], models[ms], metrics[ms], fitstatus[ms], spwstoprocess, metricskylineids) = \
            atmcorr(ms, datacolumn = 'CORRECTED_DATA', iant = iant, atmtype = atmtype, maxalt = maxalt, lapserate = lapserate,
                    scaleht = scaleht, jyperkfactor = jyperkfactor, dobackup = False,
                    forcespws = spwstoprocess, plotsfolder = plotsfolder,
                    forcefield = forcefield, forcemetricline = metricskylineids,
                    maxonlyspw = maxonlyspw, minpeaklevel = minpeaklevel, timestamp = timestamp,
                    diffsmooth = diffsmooth, psize = psize, isize = isize,
                    defatmtype=defatmtype, defmaxalt=defmaxalt, deflapserate=deflapserate, defscaleht=defscaleht,
                    decisionmetric = decisionmetric)

    LOG.info('metrics: '+str(metrics))
    LOG.info('bestmodels: '+str(bestmodels))
    LOG.info('fitstatus: '+str(fitstatus))

    ms1 = mslist[0]
    f1 = list(metrics[ms1].keys())[0]
    s1 = list(metrics[ms1][f1].keys())[0]
    paramnames = models[ms1].dtype.names
    metricnames = [item for item in metrics[ms1][f1][s1].dtype.names if 'err' not in item]
    nmodels = len(models[ms1])

    f = open(resultsfile, 'w')
    #Write summary of results
    f.write('#Summary of resulting best models\n')
    f.write('#MS,FieldID,SPW,'+','.join(paramnames)+',fitstatus'+'\n')
    for ms in mslist:
        f.write('{0:s},{1:d},{2:d},{3:d},{4:.6f},{5:.6f},{6:.6f},{7:s}\n'.format(ms,f1,s1,bestmodels[ms][0],bestmodels[ms][1],bestmodels[ms][2],bestmodels[ms][3],fitstatus[ms]))

    #All models should be the same for all MSs, so let's just print the first one (?)
    f.write('#List of models attempted\n')
    f.write('#Nmodel,'+','.join(paramnames)+'\n')
    for m in range(nmodels):
        f.write('{0:d},{1:d},{2:.6f},{3:.6f},{4:.6f}\n'.format(m,models[ms1][m][0],models[ms1][m][1],models[ms1][m][2],models[ms1][m][3]))

    #Write results for the metrics
    f.write('#Metrics results\n')
    f.write('#MS,Nmodel,'+(','.join(['{0:s},{1:s}'.format(met, met+'err') for met in metricnames]))+'\n')
    for ms in mslist:
        for m in range(nmodels):
            mdata = ','.join(['{0:.6f},{1:.8f}'.format(metrics[ms][f1][s1][m][met],metrics[ms][f1][s1][m][met+'err']) for met in metricnames])
            LOG.info('ms,m,mdata={0:s} {1:d} {2:s}\n'.format(ms,m,mdata))
            f.write('{0:s},{1:d},{2:s}\n'.format(ms,m,mdata))

    f.close()

    return (bestmodels, models, metrics, fitstatus)

def getTimeStamp(timefmt = '{0:04d}{1:02d}{2:02d}{3:02d}{4:02d}{5:02d}'):
    '''Function to generate a timestamp for output folders and files.
    param:
        timefmt: (str) Python string format string, to be used with the string.format() function.
    returns: String of timestamp.
    '''
    aux = systime.localtime()
    timestamp = timefmt.format(aux.tm_year, aux.tm_mon, aux.tm_mday, aux.tm_hour, aux.tm_min, aux.tm_sec)
    return timestamp

def redPipeSDatmcorr(iant = 'auto', atmtype = [1, 2, 3, 4],
                     maxalt = 120, lapserate = -5.6, scaleht = 2.0, decisionmetric = 'intsqdiff',
                     dobackup = True, pcode = '0000.1.00000.S', mousstatusuid = 'uid://A000/X000/X000',
                     metricspws = None, metricfield = None, metricline = None, minpeaklevel = 0.05, diffsmooth = 0.002):
    ''' Task to run SD pipeline, applying CSV-3320 correction for atmospheric lines
    between stage hsd_applycal and hsd_baseline.
    Keyword arguments:
    iant: Antenna number to get pointing direction (antenna having mount issues should
    be avoided). Default is 0.
    amttype: Atmosphere type paremeter for model in at module (1: tropical, 2: mid lat summer,
    3: mid lat winter, etc). Default is list [1, 2, 3, 4]
    maxalt: maxAltitude parameter for model, in km. default is 120 (km)
    lapserate: Lapse Rate dTem_dh parameter for at (lapse rate; K/km). Default is -5.6
    scaleht: h0 parameter for at (water scale height; km). Default is 2.0
    decisionmetric: Metric to use to take the decision on best model selection (see selectModelParams())
    metricspws: List of SPWs to use for model selection. Parameter gets passed to task selectModelParams() as forcespws.
    metricfield: List of Field to use for model selection. Currently only supported one.
    Parameter gets passed to task selectModelParams() as forcefield.
    dobackup: Whether to do a backup of the MS before applying the correction.
    (True/False) Default is True
    pcode: Project Code to enter into the pipeline context.
    mousstatusuid: MOUS status uid to enter into the pipeline context.
    '''
    from pipeline.h.cli import h_init
    from pipeline.hsd.cli import hsd_importdata
    from pipeline.hsd.cli import hsd_flagdata
    from pipeline.h.cli import h_tsyscal
    from pipeline.hsd.cli import hsd_tsysflag
    from pipeline.hsd.cli import hsd_skycal
    from pipeline.hsd.cli import hsd_k2jycal
    from pipeline.hsd.cli import hsd_applycal
    from pipeline.hsd.cli import hsd_atmcor
    from pipeline.h.cli import h_resume
    from pipeline.hsd.cli import hsd_baseline
    from pipeline.hsd.cli import hsd_blflag
    from pipeline.hsd.cli import hsd_imaging
    from pipeline.hsd.cli import hsd_exportdata
    from pipeline.h.cli import h_save

    timestamp = getTimeStamp()
    if not pipelineloaded:
        LOG.warning('Pipeline tasks not available!')
        return

    uidfilelist = glob.glob('uid___*')
    asdmlist = [item for item in uidfilelist if not '.' in item]
    LOG.info('Found the following ASDMs: '+str(asdmlist))
    #Create the working folder...
    os.system('mkdir working')
    for asdm in asdmlist:
        os.system('ln -s ../'+asdm+' working/'+asdm)
    #es = aU.stuffForScienceDataReduction()
    #Get Project Code and MOUS uid to enter dat into the context

    os.chdir('working')
    context = h_init()
    context.set_state('ProjectSummary', 'proposal_code', pcode)
    #context.set_state('ProjectSummary', 'piname', 'unknown')
    #context.set_state('ProjectSummary', 'proposal_title', 'unknown')
    #context.set_state('ProjectStructure', 'ous_part_id', 'X0')
    #context.set_state('ProjectStructure', 'ous_title', 'Undefined')
    #context.set_state('ProjectStructure', 'ppr_file', '')
    #context.set_state('ProjectStructure', 'ps_entity_id', '')
    context.set_state('ProjectStructure', 'recipe_name', 'hsd_calimage')
    #context.set_state('ProjectStructure', 'ous_entity_id', '')
    context.set_state('ProjectStructure', 'ousstatus_entity_id', mousstatusuid)

    #Import ASDM and start pipeline
    hsd_importdata(vis=asdmlist)
    #Obtain the Jy/K factors
    #mslist = glob.glob('uid___*.ms')
    mslist = [x.name for x in context.observing_run.measurement_sets]

    #Deactivated Jy/K factor from es.
    #print('Obtaining Jy/K factors for MSs: '+str(mslist))
    #es.getJyPerK(mslist)
    #Continue pipeline
    hsd_flagdata()
    h_tsyscal()
    hsd_tsysflag()
    hsd_skycal()
    hsd_k2jycal()
    hsd_applycal()

    ###Correct atmospheric ozone lines###
    ### following recipe in CSV-3320  ###
    #Read in Jy/K factor from the CSV file (DEACTIVATED)
    #jyperkfactor = getJyperKfromCSV()

    ###Run correction routine in 'try' mode to compute best model to use among the list given###
    (bestmodels, models, metrics, fitstatus) = selectModelParams(mslist, context = context, decisionmetric = decisionmetric,
                                                                 iant = iant, atmtype = atmtype,
                                                                 maxalt = maxalt, lapserate = lapserate, scaleht = scaleht,
                                                                 forcespws = metricspws, forcefield = metricfield,
                                                                 forcemetricline = metricline, diffsmooth = diffsmooth,
                                                                 minpeaklevel = minpeaklevel, timestamp = timestamp)

    #NEW, using hsd_atmcor()
    atmtypelist = [int(bestmodels[ms][0]) for ms in mslist]
    dtem_dhlist = [str(bestmodels[ms][2])+'K/km' for ms in mslist]
    h0list = [str(bestmodels[ms][3])+'km' for ms in mslist]
    hsd_atmcor(infiles=mslist,atmtype=atmtypelist,dtem_dh=dtem_dhlist,h0=h0list)

    ### Finish ATM correction ###

    #Continue pipeline execution from sdbaseline stage
    hsd_baseline()
    hsd_blflag()
    hsd_baseline()
    hsd_blflag()
    hsd_imaging()
    hsd_exportdata()
    h_save()
    os.chdir('..')

    return
