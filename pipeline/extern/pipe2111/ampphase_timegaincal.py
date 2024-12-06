import os, sys
import numpy as np
import glob
import qa_utils as qau
import TableWrapper
import pipelineqa as pqa
import astropy.units as u
from scipy.interpolate import interp1d
from scipy import stats
import csv
from matplotlib import pyplot as plt

#Dictionary of threshholds, could be different for different array, currently all fixed
thres_delta_amp_dict = {'12m': 16.5, 'ACA': 16.5, 'Mixed': 16.5}
thres_delta_phase_dict = {'12m': 9.0, 'ACA': 9.0, 'Mixed': 9.0}
#Dictionary of absolute threshholds, could be different for different array, currently all fixed
thres_abs_amp_dict = {'12m': 0.1, 'ACA': 0.1, 'Mixed': 0.1}  # Given as fraction of median flux i.e. 0.1=10% of flux
thres_abs_phase_dict = {'12m': 35.0, 'ACA': 35.0, 'Mixed': 35.0}  #Given in degrees

#Minimum array radius to force constant radial fit, in meters (mostly for ACA datasets)
minrad_const_fit = 40.0

def get_array(spwsetup):
    '''Function to discern the type of array used in the observation.
    '''
    
    hasCMantenna  = any([('CM' in ant) for ant in spwsetup['antnames']])
    hasDVantenna  = any([('DV' in ant) for ant in spwsetup['antnames']])
    hasDAantenna  = any([('DA' in ant) for ant in spwsetup['antnames']])
    if hasCMantenna and (not (hasDVantenna or hasDAantenna)):
        array_type = 'ACA'
    elif (not hasCMantenna) and (hasDVantenna or hasDAantenna):
        array_type = '12m'
    elif hasCMantenna and (hasDVantenna or hasDAantenna):
        array_type = 'Mixed'
    return array_type

def qascorefunc(nsigmaratio):
    '''Function used to calculate the QA score numerical evaluation as a linear mapping between the number of sigma excess
    of the outlier and the QA score value.
    '''
    
    return max(0.67 + (0.67 - 0.34)*(nsigmaratio - 1.0)/(1.0 - 5.0), 0.34)

def anglediff(phi1, phi2, angleunit = 'deg'):
    '''Calculate la minimum absolute angle difference between two angles.
    angleunit: Can be 'rad' for angles in radians (default) or 'deg' for angles in degrees.
    '''
    if angleunit == 'rad':
        C = 2*np.pi
    elif angleunit == 'deg':
        C = 360.0
    return min(np.abs(phi1 - phi2), np.abs(C - np.abs(phi1 - phi2)))

def calc_metric_delta(tab, var = 'phase'):
    '''Calculate amp/phase scan-to-scan absolute value differences. Currently the task propagates errors obtained from
    the dispersion of data within the scan, which only exists for 'int' tables. This is for diagnostic purposes and can be removed
    from the metric without altering nothing but the report plots done at the end of the get_timegaincal_qascores() method.
    
    Parameters:
    tab: TableWrapper object containing the data from the timegaincal table.
    var: Either 'amp' or 'phase', depending on the type of solutions of the table used.
    '''

    #Calculate stats over the whole table
    timestats = qau.table_stats(tab, var = var)

    #Get array shapes
    nspws = len(tab.spws)
    nscans = len(tab.scanlist)
    nants = len(tab.antids)
    (npols, nints) = np.shape(tab.amp_time[tab.spws[0]][tab.scanlist[0]][0])
    #Mean scan time
    meanscantime = np.array([tab.spwsetup['scan_mean_time'][scan] for scan in tab.scanlist])
    medianscandelta = np.nanmedian(np.ma.diff(meanscantime))

    #Initialize output variables
    delta = np.ma.MaskedArray(np.zeros((nspws, nants, nscans, npols)), mask = np.zeros((nspws, nants, nscans, npols)))
    delta_sigma = np.ma.MaskedArray(np.zeros((nspws, nants, nscans, npols)), mask = np.zeros((nspws, nants, nscans, npols)))

    #Median per SPW, relevant for amplitude
    medianvalue = {}

    #Examine scan-to-scan amp/phase differences
    for idxspw, spwtopick in enumerate(tab.spws):
        medianvalue[spwtopick] = np.ma.median(timestats['avg'][idxspw,:,:,:])
        for ant in tab.antids:
            for i, scan in enumerate(tab.scanlist):
                for pol in range(npols):
                    refant = tab.refant_time[spwtopick][scan][ant]
                    if timestats['avg'].mask[idxspw,i,ant,pol] or (not np.isfinite(timestats['avg'][idxspw,i,ant,pol])) or np.isnan(refant):
                        delta[idxspw,ant,i,pol] = np.nan
                        delta_sigma[idxspw,ant,i,pol] = np.nan
                        delta.mask[idxspw,ant,i,pol] = True
                        delta_sigma.mask[idxspw,ant,i,pol] = True
                        continue
                    #Get nearest unmasked scan
                    (left, right) = qau.nearestFinite(timestats['avg'][idxspw,:,ant,pol], i)
                    #Mask the space for the last slot
                    if (i == nscans-1):
                        delta[idxspw,ant,i,pol] = np.nan
                        delta_sigma[idxspw,ant,i,pol] = np.nan
                        delta.mask[idxspw,ant,i,pol] = True
                        delta_sigma.mask[idxspw,ant,i,pol] = True
                        continue
                    # For phase deltas
                    if (var == 'phase') and (i < nscans-1):
                        delta[idxspw,ant,i,pol] = np.ma.abs(anglediff(anglediff(timestats['avg'][idxspw,right,ant,pol], timestats['avg'][idxspw,i,ant,pol]), timestats['avg'][idxspw,i,refant,pol]))
                        delta_sigma[idxspw,ant,i,pol] = 1.4826*np.ma.sqrt(timestats['mad'][idxspw,right,ant,pol]**2 + timestats['mad'][idxspw,i,ant,pol]**2)
                    #For Amp deltas
                    elif (var == 'amp') and (i < nscans-1):
                        delta[idxspw,ant,i,pol] = np.ma.abs((timestats['avg'][idxspw,right,ant,pol] - timestats['avg'][idxspw,i,ant,pol]))
                        delta_sigma[idxspw,ant,i,pol] = 1.4826*np.ma.sqrt(timestats['mad'][idxspw,right,ant,pol]**2 + timestats['mad'][idxspw,i,ant,pol]**2)
                    #Copy mask
                    delta.mask[idxspw,ant,i,pol] = (timestats['avg'].mask[idxspw,right,ant,pol] | timestats['avg'].mask[idxspw,i,ant,pol])
                    delta_sigma.mask[idxspw,ant,i,pol] = (timestats['mad'].mask[idxspw,right,ant,pol] | timestats['mad'].mask[idxspw,i,ant,pol])

    #Subtract the median, if nscans>2
    for idxspw, spwtopick in enumerate(tab.spws):
        for ant in tab.antids:
            for pol in range(npols):
                antdata = delta[idxspw,ant,:,pol]
                if np.ma.count(antdata) > 1:
                    delta[idxspw,ant,:,pol] -= np.ma.median(antdata)

    #Return mean scan times, delta values and their errors (errors currently used just for diagnostic purposes)
    return (meanscantime, delta, delta_sigma, medianvalue)

def amp_threshold(metric = None, spwsetup = None, scanindices = None, spws = None, threshold = 16.0, abs_threshold = 0.1, median_amp = None):
    '''Function to collect amplitude values, measure their dispersion with outlier rejection,
    and apply the threshold for detecting amplitude outlier deviations.
    
    Parameters:
    metric: Array containing the delta amplitude metric values for all spws, scans and antennas.
    spwsetup: Dictionary obtained from qau.getSpecSetup()
    scanindices: list of indices for scan dimension in the metric array. Should be 0..(nscans-2) for the delta metric.
    spws: list of spws considered in the metric array. Could be as many as 0..(nspws-1) bt can be less if SPW combination
          was used in the creation of the timegaincal table.
    threshold: Amplitude threshold value used in detecting outliers.
    '''

    #Initialize main variables
    (nspws, nants, ntimes, npols) = np.shape(metric)
    ampfit = {}
    maxval = -1
    maxvalidx = ''
    maxvalstd = -1
    outliers = np.ma.MaskedArray(np.zeros((nspws, nants, ntimes, npols)), mask = np.zeros((nspws, nants, ntimes, npols)))
    #List of log output entries
    log = []
    #List of resulting QAscores
    qascores = []

    for idxspw, spwtopick in enumerate(spws):
        values = np.ma.concatenate([np.ma.concatenate([metric[idxspw,:,i,pol] for i in range(ntimes)]) for pol in range(npols)])
        (miny, maxy) = (np.ma.min(values), np.ma.max(values))
        nonzerovalues = (np.abs(values) > 1.e-06)

        #Threshold the amplitude deltas
        # correction factor for obtaining sigma from MAD
        madfactor = 1.482602218505602
        ampstats = qau.robust_amp_stats(values[nonzerovalues])
        (amp_mu, amp_sigma) = (ampstats['median'], madfactor*ampstats['mad'])
        ampfit[spwtopick] = {'mean': amp_mu, 'std': amp_sigma, 'threshold': threshold*amp_sigma}

        #Find outliers to amplitude deltas excesses
        for ant in spwsetup['antids']:
            for i, scan in enumerate(scanindices):
                for pol in range(npols):
                    value = np.ma.abs(metric[idxspw,ant,i,pol])
                    sigma = ampfit[spwtopick]['std']
                    notmasked = ~metric.mask[idxspw,ant,i,pol]
                    outliers[idxspw,ant,i,pol] = (value > ampfit[spwtopick]['threshold']) and notmasked and np.isfinite(value) and ((value/median_amp[spwtopick]) > abs_threshold)
                    nsigma = value/sigma
                    #Calculate nsigma/threshold ratio for QA score evaluation
                    nsigmaratio = nsigma/threshold
                    if outliers[idxspw,ant,i,pol]:
                        #Create objects to create QAscore
                        reason = 'amp_vs_time.deviation'
                        applies_to = pqa.TargetDataSelection(vis={spwsetup['msname']}, scan={scan}, intent={'*PHASE*'}, spw={spwtopick}, ant={ant}, pol={pol})
                        comes_from = pqa.QAOrigin(metric_name=reason, metric_score=nsigma, metric_units='sigma deviation from reference fit')
                        #QA score value evaluation
                        qascore_value = qascorefunc(nsigmaratio)
                        longmsg = 'Amplitude gain solution deviation outlier for spw {0:d}, antenna {1:s}'.format(spwtopick, spwsetup['antnames'][ant])
                        qascore = pqa.QAScore(qascore_value, longmsg=longmsg, shortmsg='Amplitude v/s Time deviation', origin=comes_from, applies_to=applies_to, hierarchy=reason)
                        qascores.append(qascore)
                        #Log outlier entry in log output
                        log.append('scan={0:d} spw={1:d} ant={2:d} pol={3:d} reason={4:s} sigma_deviation={5:.4f} delta_physical={6:.4f} qascore={7:.2f}\n'.format(scan,spwtopick,ant,pol,reason,nsigma,value,qascore_value))
                    #For threshold determination and diagnostic, save the maximum value (not relevant for pipeline use)
                    if outliers[idxspw,ant,i,pol] and (value/sigma > maxval):
                        maxval = value/sigma
                        maxvalidx = str((spwtopick, spwsetup['antnames'][ant], scan, pol)).replace("""'""","")
                        maxvalstd = sigma

    #If there are no outliers, put a 1.0 QA score
    if len(qascores) == 0:
        reason = 'amp_vs_time.deviation'
        short_msg = 'No gain amplitude outliers'
        long_msg = 'No amplitude gain solution deviations detected for '+spwsetup['msname']
        qascore = pqa.QAScore(1.0, longmsg=long_msg, shortmsg=short_msg, hierarchy=reason,  applies_to=pqa.TargetDataSelection(vis={spwsetup['msname']}))
        qascore.origin = pqa.QAOrigin(metric_name=reason, metric_score=0, metric_units='number of outliers')
        qascores.append(qascore)

    return (ampfit, outliers, {'maxval': maxval, 'maxvalidx': maxvalidx, 'maxvalstd': maxvalstd}, log, qascores)

def sigma_segments(x, y, nmin = 30, pval = 0.05, sigmalimit = None, forceshape = 'none'):
    '''Function to partition and make estimates of 1-sigma dispersions in each partition of a
    dependent variable as a function of variable x. The criteria for deciding whether to split or not
    a given set of data is that there is at least nmin element in each piece of the subdivision, and that the
    two sets have a statistically significant difference in their variances, according to the criteria from
    Levene's test of equality of variances (Levene 1960), as implemented in scipy.stats.levene().
    
    Parameters:
    x: Array with value of independent variable, which will be partitioned in segments
    y: Array with value of dependent variable, on which 1-sigma will be calculated
    nmin: Minimum number of datapoints to attempt dispersion calculation, for smaller samples, stop dividing the data.
    pval: p-value for Levene's test.
    sigmalimit: Impose a limit to the obtained sigma values, after the calculation.
    forceshape: Impose strictly increasing/decreasing behavior to the resulting sigma datapoints.
    return: Dictionary containing:
                'partitions': List of partitions.
                'pcenter': List of partitions centers datapoints.
                'sigmas': List of sigma values obtained in each partition.
    '''
    #Keep unmasked an finite value for calculation
    goodvalues = np.isfinite(y)
    if type(y) == np.ma.core.MaskedArray:
        z = 1.0*y
        z.mask = (y.mask | ~goodvalues)
    else:
        z = np.ma.MaskedArray(y, mask=~goodvalues)
    y = z[~z.mask]
    x = x[~z.mask]
    #Obtain range of independent variable x
    xmin = np.min(x)
    xmax = np.max(x)
    #Define initial partition as the whole range
    partitions = [[xmin, xmax]]
    #Calculate initial sigma
    (mufull, sigmafull) = qau.robust_stats(y)
    sigmas = [sigmafull]
    #Iterate a long as partitions change
    doiter = True
    while (doiter):
        newpartitions = []
        newsigmas = []
        #Let's examine the statistics in each partition
        for i, partition in enumerate(partitions):
            #Let's divide the partition in two, and
            midp = 0.5*(partition[0] + partition[1])
            sel = (x >= partition[0]) & (x < partition[1])
            lowsel = (x >= partition[0]) & (x <= midp)
            highsel = (x > midp) & (x < partition[1])
            nlow = np.ma.sum(lowsel)
            nhigh = np.ma.sum(highsel)
            (_, sigmasel) = qau.robust_stats(y[sel], forcezeromu = True)
            lowhightest = stats.levene(y[lowsel], y[highsel])
            (_, sigmalow) = qau.robust_stats(y[lowsel], forcezeromu = True)
            (_, sigmahigh) = qau.robust_stats(y[highsel], forcezeromu = True)
            #If sigmas in first half of the partition is statistically different than the second half, divide partition
            #Otherwise, leave is as it is
            if (nlow >= nmin) and (nhigh >= nmin) and (lowhightest.pvalue < pval):
                newpartitions.append([partition[0], midp])
                newpartitions.append([midp, partition[1]])
                newsigmas.append(sigmalow)
                newsigmas.append(sigmahigh)
            else:
                newpartitions.append(partition)
                newsigmas.append(sigmasel)
        #If in this iteration, the list of partitions has not changed, stop iterating
        if (len(newpartitions) == len(partitions)):
            doiter = False
        else:
            doiter = True
            partitions = newpartitions
            sigmas = newsigmas
    #Make sigmas non-decreasing, if desired
    if forceshape == 'increasing':
        for i in range(1, len(sigmas)):
            if sigmas[i] < sigmas[i-1]:
                sigmas[i] = sigmas[i-1]
    #Make sigmas decreasing, if desired
    elif forceshape == 'decreasing':
        for i in range(1, len(sigmas)):
            if sigmas[i] > sigmas[i-1]:
                sigmas[i] = sigmas[i-1]
    #Enforce cap if requested
    if sigmalimit is not None:
        for i in range(len(sigmas)):
            if sigmas[i] > sigmalimit:
                sigmas[i] = sigmalimit

    #Calculate center of partitions
    pcenter = [np.mean(p) for p in partitions]
    #Extend to minimum and maximum x
    pcenter.insert(0, xmin)
    sigmas.insert(0, sigmas[0])
    pcenter.insert(len(pcenter), xmax)
    sigmas.insert(len(sigmas), sigmas[-1])

    return {'partitions': partitions, 'pcenter': pcenter, 'sigmas': sigmas}

def stdfit(x, fitparam = None):
    '''Function used to evaluate a linear interpolation between datapoints using output from sigma_segments() function.
    
    Parameters:
    x: value(s) to evaluate the linearly interpolated function.
    fitparam: Dictionary containing datapoints to interpolate. Should be output from sigma_segments().
    '''
    stdf = interp1d(fitparam['pcenter'], fitparam['sigmas'], fill_value = 'extrapolate', bounds_error = False, assume_sorted = True)
    return stdf(x)

def radial_metric_threshold(metric = None, spwsetup = None, scanindices = None, spws = None, refant = None,
                               threshold = 9.0, abs_threshold = 20.0, minrad_const_fit = 40.0, maxphasethreshold = 160.0):
    '''Function to collect phase values, measure their dispersion with outlier rejection,
    and apply the threshold for detecting phase outlier deviations.
    
    Parameters:
    metric: Array containing the delta phase metric values for all spws, scans and antennas.
    spwsetup: Dictionary obtained from qau.getSpecSetup()
    scanindices: list of indices for scan dimension in the metric array. Should be 0..(nscans-2) for the delta metric.
    spws: list of spws considered in the metric array. Could be as many as 0..(nspws-1) bt can be less if SPW combination
          was used in the creation of the timegaincal table.
    refant: Array with reference antennas used for each datapoint in metric. Should be the "refant_time" attribute from the
            corresponding TableWrapper object used to create the metric array.
    threshold: Phase threshold value used in detecting outliers.
    minrad_const_fit: Minimum array radius to force constant radial fit, in meters (mostly for ACA datasets, but could be also
                      applicable to arrays with very few remaining unflagged antennas. ).
    '''

    #Initialize main variables
    (nspws, nants, ntimes, npols) = np.shape(metric)
    #Output dictionary and array
    radialfit = {}
    maxval = -1
    maxvalidx = ''
    maxvalstd = -1
    outliers = np.ma.MaskedArray(np.zeros((nspws, nants, ntimes, npols), dtype=bool), mask = np.zeros((nspws, nants, ntimes, npols), dtype=bool))
    #List of log output entries
    log = []
    #List of resulting QAscores
    qascores = []

    #Distance to center variable
    centerdistdic = {}

    for idxspw, spwtopick in enumerate(spws):
      
        #If SPWs were mapped, then skip them. The metric should be masked
        if np.sum(metric.mask[idxspw]) == nants*ntimes*npols:
            continue

        #Count number of flagged antennas. I too many antennas are flagged, statistics might star to behave as in the ACA array case.
        flaggedants = np.array([(np.sum(metric.mask[idxspw,ant]) == ntimes*npols) for ant in spwsetup['antids']])
        nonflaggedants = nants - np.sum(flaggedants)

        #Calculate vector of projected distances to reference antenna.
        centerdistdic[spwtopick] = {}
        for scan in scanindices:
            thisrefant = np.nanmedian([refant[spwtopick][scan][ant] for ant in spwsetup['antids']])
            if not np.isnan(thisrefant):
                (antposXY, scancenterdist) = qau.calcProjDist(spwsetup, ['*PHASE*'], refant = int(thisrefant), scantouse = scan)
                centerdistdic[spwtopick][scan] = scancenterdist[scan]
            else:
                centerdistdic[spwtopick][scan] = spwsetup['antcenterdistproj'][scan]   #np.array([np.nan for ant in spwsetup['antids']])
        centerdists = np.concatenate([np.concatenate([centerdistdic[spwtopick][scan] for scan in scanindices]) for pol in range(npols)])
        (minr, maxr) = (np.ma.min(centerdists), np.ma.max(centerdists))
        startcenter = minr
        #Determine radial distribution ranges
        midr = 0.5*(minr + maxr)
        #Boolean to contain determination if this is considered ACA-like array (fallback to constant sigma(r))
        isACAsize = (maxr <= minrad_const_fit) or (nonflaggedants <= 25)

        #Collect metric values into a vector
        values = np.ma.concatenate([np.ma.concatenate([metric[idxspw,:,i,pol] for i in range(ntimes)]) for pol in range(npols)])

        #For ACA dataset
        if isACAsize:
            endcenter = maxr
        #Regular 12m array case
        else:
            endcenter = np.percentile(centerdists[~values.mask], 30.0)
            
        #RMS value ranges
        (miny, maxy) = (np.ma.min(values), np.ma.max(values))
        nonzerovalues = (np.abs(values) > 1.e-06)
        sel = ~values.mask & nonzerovalues

        r = centerdists[sel]
        y = values[sel]

        #12m case
        if not isACAsize:
            fit = sigma_segments(r, y, sigmalimit = maxphasethreshold/threshold)
        #ACA case
        else:
            centralsel = (centerdists >= startcenter) & (centerdists <= endcenter) & sel
            (_, centralrms) = qau.robust_stats(values[centralsel], forcezeromu = True)
            if centralrms > maxphasethreshold/threshold:
                centralrms = maxphasethreshold/threshold
            fit = {'partitions': [[minr, maxr]], 'pcenter': [minr, maxr], 'sigmas': [centralrms, centralrms]}
            
        radialfit[spwtopick] = {'meanfit': 0.0, 'stdfit': fit, 'threshold': threshold}

        #Find outliers to phase delta excesses
        for ant in spwsetup['antids']:
            for i, scan in enumerate(scanindices):
                for pol in range(npols):
                    #Calculate the threshold at this distance
                    thisr = centerdistdic[spwtopick][scan][ant]
                    sigma = stdfit(thisr, fitparam = radialfit[spwtopick]['stdfit'])
                    threshold_sigma = threshold*sigma
                    #Extract value to be evaluated and mark it as outlier if it is
                    value = np.ma.abs(metric[idxspw,ant,i,pol])
                    notmasked = ~metric.mask[idxspw,ant,i,pol]
                    outliers[idxspw,ant,i,pol] = (value > threshold_sigma) and notmasked and np.isfinite(value) and (value > abs_threshold)
                    nsigma = value/sigma
                    #Calculate nsigma/threshold ratio for QA score evaluation
                    nsigmaratio = nsigma/threshold
                    if outliers[idxspw,ant,i,pol]:
                        #Create objects to create QAscore
                        reason = 'phase_vs_time.deviation'
                        applies_to = pqa.TargetDataSelection(vis={spwsetup['msname']}, scan={scan}, intent={'*PHASE*'}, spw={spwtopick}, ant={ant}, pol={pol})
                        comes_from = pqa.QAOrigin(metric_name=reason, metric_score=nsigma, metric_units='sigma deviation from reference fit')
                        #QA score value evaluation
                        qascore_value = qascorefunc(nsigmaratio)
                        longmsg = 'Phase gain solution deviation outlier for spw {0:d}, antenna {1:s}'.format(spwtopick, spwsetup['antnames'][ant])
                        qascore = pqa.QAScore(qascore_value, longmsg=longmsg, shortmsg='Phase v/s Time deviation', origin=comes_from, applies_to=applies_to, hierarchy=reason)
                        qascores.append(qascore)
                        #Log outlier entry in log output
                        log.append('scan={0:d} spw={1:d} ant={2:d} pol={3:d} reason={4:s} sigma_deviation={5:.4f} delta_physical={6:.4f} qascore={7:.2f}\n'.format(scan,spwtopick,ant,pol,reason,nsigma,value,qascore_value))
                    #For threshold determination and diagnostic, save the maximum value (not relevant for pipeline use)
                    if outliers[idxspw,ant,i,pol] and (value/sigma > maxval):
                        maxval = value/sigma
                        maxvalidx = str((spwtopick, spwsetup['antnames'][ant], scan, pol)).replace("""'""","")
                        maxvalstd = sigma

    #If there are no outliers, put a 1.0 QA score
    if len(qascores) == 0:
        reason = 'phase_vs_time.deviation'
        short_msg = 'No gain phase outliers'
        long_msg = 'No phase gain solution deviations detected for '+spwsetup['msname']
        qascore = pqa.QAScore(1.0, longmsg=long_msg, shortmsg=short_msg, hierarchy=reason,  applies_to=pqa.TargetDataSelection(vis={spwsetup['msname']}))
        qascore.origin = pqa.QAOrigin(metric_name=reason, metric_score=0, metric_units='number of outliers')
        qascores.append(qascore)

    return (radialfit, outliers, centerdistdic, {'maxval': maxval, 'maxvalidx': maxvalidx, 'maxvalstd': maxvalstd}, log, qascores)

def metric_center_dist_plot(metric = None, metric_sigma = None, metric_outlier = None, centerdistdic = None, spwsetup = None, scanindices = None, spwindices = None, radialfit_dict = None, refant = None, minrad_const_fit = None, abs_threshold = None, metric_label = 'Metric Label', plot_title = 'Plot Title', plot_filename = 'metric_center_dist_plot.png', dpi = 100, colors = 'auto'):

    #Initialize variables
    (nspws, nants, ntimes, npols) = np.shape(metric)
    if str(colors) == 'auto':
        colors = genColorList(nants)
    polmarker = ['x', '1']
    pollinestyle = [':k', '--k']
    #Go over each SPW checking if it is to be plotted
    spwlist = [spw for idxspw, spw in enumerate(spwindices) if np.sum(metric.mask[idxspw]) < nants*ntimes*npols]

    maxr = np.max([[[centerdistdic[s][scan][ant] for s in spwlist] for scan in scanindices] for ant in spwsetup['antids']])
    if not np.isfinite(maxr):
        maxr = 1.1*np.max(spwsetup['antcenterdist'])
    r = np.arange(0.0,1.05*maxr, 1.0)
    sigmafunction = {}
    threshold_sigma = {}

    #Avoid opening window for interactive use
    plt.ioff()
    #Go over each SPW plotting and saving the plot in a png file
    for idxspw, spwtopick in enumerate(spwlist):
        #Evaluate sigma envelope function for plotting
        sigmafunction[spwtopick] = np.array([stdfit(x, fitparam = radialfit_dict[spwtopick]['stdfit']) for x in r])
        threshold_sigma[spwtopick] = radialfit_dict[spwtopick]['threshold']*sigmafunction[spwtopick]

        #Plot metric v/s distance to projected center
        plt.clf()
        fig = plt.figure(frameon = False)
        fig.set_size_inches(8, 5)
        for ant in spwsetup['antids']:
            for i, scan in enumerate(scanindices):
                for pol in range(npols):
                    if np.isfinite(metric[idxspw,ant,i,pol]):
                        plt.errorbar(centerdistdic[spwtopick][scan][ant], np.abs(metric[idxspw,ant,i,pol]), yerr=metric_sigma[idxspw,ant,i,pol], fmt=polmarker[pol], color=colors[ant])
                    #For datapoints that show an excess, plot a label
                    if metric_outlier[idxspw,ant,i,pol]:
                        plt.text(centerdistdic[spwtopick][scan][ant]*1.01, np.abs(metric[idxspw,ant,i,pol]), 'ant: '+spwsetup['antnames'][ant])
        plt.plot(r, threshold_sigma[spwtopick], pollinestyle[0])
        plt.plot(r, sigmafunction[spwtopick], linestyle='--', color='gray')
        if abs_threshold is not None:
            plt.plot(r, abs_threshold*np.ones(len(r)), linestyle='-.', color='blue')
        plt.xlabel('Projected distance to array center [m]')
        plt.ylabel(metric_label)
        plt.xlim(-0.1*maxr, 1.1*maxr)
        plt.title(plot_title.replace('#SPW#', str(spwtopick)))
        plt.savefig(plot_filename.replace('#SPW#', str(spwtopick)), dpi=dpi)
    plt.close()

    return

def metric_plot(metric = None, metric_sigma = None, metric_outlier = None, spwsetup = None, scanindices = None, spwindices = None, fit_dict = None, abs_threshold = None, median_value = None, metric_label = 'Metric Label', plot_title = 'Plot Title', plot_filename = 'metric_center_dist_plot.png', dpi = 100, colors = 'auto'):

    #Initialize variables
    (nspws, nants, ntimes, npols) = np.shape(metric)
    if str(colors) == 'auto':
        colors = genColorList(nants)
    polmarker = ['x', '1']
    pollinestyle = [':k', '--k']

    #Avoid opening window for interactive use
    plt.ioff()
    #Go over each SPW plotting and saving the plot in a png file
    for idxspw, spwtopick in enumerate(spwindices):
        #If SPWs were mapped, then skip them. The metric should be masked
        if np.sum(metric.mask[idxspw]) == nants*ntimes*npols:
            continue
        #Plot metric histogram
        plt.clf()
        fig = plt.figure(frameon = False)
        fig.set_size_inches(8, 5)
        for ant in spwsetup['antids']:
            for i, scan in enumerate(scanindices):
                for pol in range(npols):
                    if np.isfinite(metric[idxspw,ant,i,pol]):
                        plt.errorbar(ant, np.abs(metric[idxspw,ant,i,pol])/fit_dict[spwtopick]['std'], yerr=metric_sigma[idxspw,ant,i,pol]/fit_dict[spwtopick]['std'], fmt=polmarker[pol], color=colors[ant])
                    #For datapoints that show an excess, plot a label
                    if metric_outlier[idxspw,ant,i,pol]:
                        plt.text(ant*1.01, (np.abs(metric[idxspw,ant,i,pol])/fit_dict[spwtopick]['std']), 'ant: '+spwsetup['antnames'][ant], fontsize=6)
        plt.plot([0.0, nants], [fit_dict[spwtopick]['threshold']/fit_dict[spwtopick]['std'], fit_dict[spwtopick]['threshold']/fit_dict[spwtopick]['std']], pollinestyle[0])
        if abs_threshold is not None:
            absthvalue = abs_threshold*median_value[spwtopick]/fit_dict[spwtopick]['std']
            plt.plot([0.0, nants], [absthvalue, absthvalue], linestyle='-.', color='blue')
        plt.xlabel('Antenna')
        plt.xticks(spwsetup['antids'], spwsetup['antnames'], rotation=90)
        plt.ylabel(metric_label)
        plt.xlim(-1.0, nants+1.0)
        plt.title(plot_title.replace('#SPW#', str(spwtopick))+'\n(Sigma={0:.4f})'.format(fit_dict[spwtopick]['std']))
        plt.savefig(plot_filename.replace('#SPW#', str(spwtopick)), dpi=dpi)
    plt.close()

    return

def metric_time_plot(meanscantime = None, metric = None, metric_sigma = None, metric_outlier = None, spwsetup = None, scanindices = None, spwindices = None, fit_dict = None, abs_threshold = None, median_value = None, metric_label = 'Metric Label', plot_title = 'Plot Title', plot_filename = 'metric_time_plot.png', dpi = 100, tstart = 'auto', tend = 'auto', colors = 'auto'):

    #Initialize variables
    (nspws, nants, ntimes, npols) = np.shape(metric)
    (nspws_sig, nants_sig, ntimes_sig, npols_sig) = np.shape(metric_sigma)
    if str(colors) == 'auto':
        colors = genColorList(nants)
    polmarker = ['x', '1']
    pollinestyle = [':k', '--k']
    if tstart == 'auto':
        tstart = np.min(meanscantime)
    if tend == 'auto':
        tend = np.max(meanscantime)
    dtime = tend - tstart

    #Avoid opening window for interactive use
    plt.ioff()
    #Go over each SPW plotting and saving the plot in a png file
    for idxspw, spwtopick in enumerate(spwindices):
        #If SPWs were mapped, then skip them. The metric should be masked
        if np.sum(metric.mask[idxspw]) == nants*ntimes*npols:
            continue
        #Plot delta_BA
        plt.clf()
        fig = plt.figure(frameon = False)
        fig.set_size_inches(8, 5)
        for ant in spwsetup['antids']:
            for i in range(ntimes):
                scan = scanindices[i]
                for pol in range(npols):
                    #Plot values with their errors
                    if np.isfinite(metric[idxspw,ant,i,pol]):
                        plt.errorbar(meanscantime[i]-tstart, np.abs(metric[idxspw,ant,i,pol])/fit_dict[spwtopick]['std'], yerr=metric_sigma[idxspw,ant,i,pol]/fit_dict[spwtopick]['std'], fmt=polmarker[pol], color=colors[ant])
                    #For datapoints that show an excess, plot a label
                    if metric_outlier[idxspw,ant,i,pol]:
                        plt.text((meanscantime[i]-tstart)*1.01, (np.abs(metric[idxspw,ant,i,pol])/fit_dict[spwtopick]['std']), 'ant: '+spwsetup['antnames'][ant], fontsize=6)
        plt.plot([0.0, dtime], [fit_dict[spwtopick]['threshold']/fit_dict[spwtopick]['std'], fit_dict[spwtopick]['threshold']/fit_dict[spwtopick]['std']], pollinestyle[0])
        if abs_threshold is not None:
            absthvalue = abs_threshold*median_value[spwtopick]/fit_dict[spwtopick]['std']
            plt.plot([0.0, dtime], [absthvalue, absthvalue], linestyle='-.', color='blue')
        plt.xlim(0.0-0.05*dtime, 1.05*dtime)
        plt.xlabel('Time since first Phase cal scan [s]')
        plt.ylabel(metric_label)
        plt.title(plot_title.replace('#SPW#', str(spwtopick))+'\n(Sigma={0:.4f})'.format(fit_dict[spwtopick]['std']))
        plt.savefig(plot_filename.replace('#SPW#', str(spwtopick)))
    plt.close()

    return

def outlier2str(metric_outlier, antnames, spwindices, scanindices):
    outlierlist = []
    for idxspw, spw in enumerate(spwindices):
        #Collapse outliers
        outlier = (np.ma.sum(metric_outlier[idxspw], axis = 2) > 0)
        outlierstr = ''
        if np.ma.sum(outlier) > 0:
            outlierstr += str(spw)+':'
            spwstr = []
            for ant in range(len(antnames)):
                if np.ma.sum(outlier[ant,:]) > 0:
                    spwstr.append(antnames[ant]+'_scan('+';'.join([str(scan) for i,scan in enumerate(scanindices) if outlier[ant,i]])+')')
            outlierstr += '-'.join(spwstr)
            outlierlist.append(outlierstr)
    
    return ';'.join(outlierlist)


def get_timegaincal_qascores(ms, output_path = '.', label='', applycalQAversion = ''):
    '''Run amplitude and phase diagnostic metrics and report QA scores based on them.
    '''

    msname = ms.split('/')[-1]
    plfolder = output_path.split('/')[-1]
    fullplfolder = ms.replace(msname, '')
    print('Calculating timegaincal qa scores for MS: '+msname)
    #if there is any saved data, it is in buffer_folder
    buffer_folder = output_path + "/databuffer"
    print('buffer_folder: '+str(buffer_folder))
    #Load ms metadata
    spwsetup = qau.getSpecSetup(ms, bfolder=buffer_folder, applycalQAversion=applycalQAversion)
    nants = len(spwsetup['antids'])
    array_type = get_array(spwsetup)
    #Threshold for this EB
    thres_delta_amp = thres_delta_amp_dict[array_type]
    thres_delta_phase = thres_delta_phase_dict[array_type]
    thres_abs_amp = thres_abs_amp_dict[array_type]
    thres_abs_phase = thres_abs_phase_dict[array_type]
    
    #Create plots folder
    qaplotsfolder = output_path+'/timeqaplots_'+plfolder+msname+'_'+label
    if not os.path.exists(qaplotsfolder):
        os.system('mkdir '+qaplotsfolder)

    #Get filenames of timegaincal diagnostic tables
    #Scan average tables
    diag_data = qau.getDiagTimegaincalTables(fullplfolder, msname, spwsetup, tbltype = 'inf')
    amp_table_fname = diag_data['amp_table']
    phase_table_fname = diag_data['phase_table']
    #Int diagnostic tables
    diag_data_int = qau.getDiagTimegaincalTables(fullplfolder, msname, spwsetup, tbltype = 'int')
    amp_table_fname_int = diag_data_int['amp_table']
    phase_table_fname_int = diag_data_int['phase_table']

    #Load timegaincal inf tables for phase
    tab_phase = TableWrapper.TableWrapper.create_from_tables(intent='*PHASE*', gpcaltbl=phase_table_fname, spwsetup=spwsetup)
    #Calculate metric for the phase case
    (meanscantime_phase, delta_phase, delta_phase_sigma, median_phase) = calc_metric_delta(tab_phase, var = 'phase')
    #Load timegaincal int tables for phase, for plotting only at this point
    tab_phase_int = TableWrapper.TableWrapper.create_from_tables(intent='*PHASE*', gpcaltbl=phase_table_fname_int, spwsetup=spwsetup)
    #Calculate metric for the phase case
    (meanscantime_phase_int, delta_phase_int, delta_phase_sigma_int, median_phase_int) = calc_metric_delta(tab_phase_int, var = 'phase')
    #Calculate the radial thresholds functions and find outliers
    (radialfit_phase_delta_dict, phase_delta_outlier, phase_centerdist, phase_maxval, phase_log, phase_qascores) = radial_metric_threshold(metric = delta_phase, spwsetup = spwsetup, scanindices = tab_phase.scanlist, spws = tab_phase.spws, refant = tab_phase.refant_time, threshold = thres_delta_phase, abs_threshold = thres_abs_phase, minrad_const_fit = minrad_const_fit)

    #Write phase outlier log
    f = open(qaplotsfolder+'/'+msname+'_outliers_'+label+'.txt', 'a')
    for line in phase_log:
        f.write(msname+' *PHASE* '+line)
    f.close()

    #Load timegaincal inf tables for amplitude
    tab_amp = TableWrapper.TableWrapper.create_from_tables(intent='*PHASE*', gpcaltbl=amp_table_fname, spwsetup=spwsetup)
    #Calculate metric for the amplitude case
    (meanscantime_amp, delta_amp, delta_amp_sigma, median_amp) = calc_metric_delta(tab_amp, var = 'amp')
    #Load timegaincal int tables for amplitude, for plotting only at this point
    tab_amp_int = TableWrapper.TableWrapper.create_from_tables(intent='*PHASE*', gpcaltbl=amp_table_fname_int, spwsetup=spwsetup)
    #Calculate metric for the amplitude case
    (meanscantime_amp_int, delta_amp_int, delta_amp_sigma_int, median_amp_int) = calc_metric_delta(tab_amp_int, var = 'amp')
    # Find sigma envelope function and outliers to amp deltas
    (amp_fit, amp_delta_outlier, amp_maxval, amp_log, amp_qascores) = amp_threshold(metric = delta_amp, spwsetup = spwsetup, scanindices = tab_amp.scanlist, spws = tab_amp.spws, threshold = thres_delta_amp, abs_threshold = thres_abs_amp, median_amp = median_amp)
    
    #Final list of QA scores
    ms_qascores = amp_qascores
    ms_qascores.extend(phase_qascores)
    
    #Write amplitude outlier log (analog to PIPE356 file in applycal)
    f = open(qaplotsfolder+'/'+msname+'_outliers_'+label+'.txt', 'a')
    for line in amp_log:
        f.write(msname+' *PHASE* '+line)
    f.close()

    #Write summary line for the internal report (this shall not be interesting for pipeline)
    f = open(output_path+'/timegaincal_reportline_'+label+'.csv', 'a')
    f.write(plfolder+','+msname+',')
    f.write(outlier2str(amp_delta_outlier, spwsetup['antnames'], tab_amp.spws, tab_amp.scanlist)+',')
    if (amp_maxval['maxval'] > 0):
        f.write(str(amp_maxval['maxval']*amp_maxval['maxvalstd'])+','+str(amp_maxval['maxval'])+','+str(amp_maxval['maxvalidx']).replace(' ','').replace(',',';')+',')
    else:
        f.write(',,,')
    f.write(outlier2str(phase_delta_outlier, spwsetup['antnames'], tab_phase.spws, tab_phase.scanlist)+',')
    if (phase_maxval['maxval'] > 0):
        f.write(str(phase_maxval['maxval']*phase_maxval['maxvalstd'])+','+str(phase_maxval['maxval'])+','+str(phase_maxval['maxvalidx']).replace(' ','').replace(',',';')+'\n')
    else:
        f.write(',,\n')
    f.close()

    #Color for the plots
    colors = qau.genColorList(nants, rndseed = 0)

    #Plot amp deltas v/s antennaid for the internal report (this shall not be interesting for pipeline)
    deltas_radialplotfile = qaplotsfolder+'/'+msname+'.delta_amp_vs_antid.spw#SPW#.png'
    metric_plot(metric = delta_amp, metric_sigma = delta_amp_sigma_int, metric_outlier = amp_delta_outlier, spwsetup = spwsetup, scanindices = tab_amp.scanlist, spwindices = tab_amp.spws, fit_dict = amp_fit, abs_threshold = thres_abs_amp, median_value = median_amp, metric_label = 'Amp Delta/Sigma', plot_title = 'Timegaincal Amplitude deltas for '+msname+'\nSPW: #SPW# Res.Amp.thres: '+str(thres_delta_amp), plot_filename = deltas_radialplotfile, dpi = 100, colors = colors)

    #Plot amp deltas v/s time for the internal report (this shall not be interesting for pipeline)
    deltas_radialplotfile = qaplotsfolder+'/'+msname+'.delta_amp_vs_time.spw#SPW#.png'
    metric_time_plot(meanscantime = meanscantime_amp, metric = delta_amp, metric_sigma = delta_amp_sigma_int, metric_outlier = amp_delta_outlier, spwsetup = spwsetup, scanindices = tab_amp.scanlist, spwindices = tab_amp.spws, fit_dict = amp_fit, abs_threshold = thres_abs_amp, median_value = median_amp, metric_label = 'Amp Delta/Sigma', plot_title = 'Timegaincal Amplitude deltas v/s Time for '+msname+'\nSPW: #SPW# Res.Amp.thres: '+str(thres_delta_amp), plot_filename = deltas_radialplotfile, dpi = 100, colors = colors)

    #Plot phase deltas v/s distance to projected center for the internal report (this shall not be interesting for pipeline)
    deltas_radialplotfile = qaplotsfolder+'/'+msname+'.delta_phase_vs_Proj_distance.spw#SPW#.png'
    metric_center_dist_plot(metric = delta_phase, metric_sigma = delta_phase_sigma_int, metric_outlier = phase_delta_outlier, centerdistdic = phase_centerdist, spwsetup = spwsetup, scanindices = tab_phase.scanlist, spwindices = tab_phase.spws, radialfit_dict = radialfit_phase_delta_dict, refant = tab_phase.refant_time, minrad_const_fit = minrad_const_fit, abs_threshold = thres_abs_phase, metric_label = 'Phase Delta [deg]', plot_title = 'Timegaincal phase delta v/s Proj. Distance\nfor '+msname+' SPW: #SPW#\nRes.Ph.thres: '+str(thres_delta_phase), plot_filename = deltas_radialplotfile, dpi = 100, colors = colors)
    
    return ms_qascores
