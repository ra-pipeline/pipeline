import os
import numpy as np
import copy
import pickle
import pathlib

from scipy import stats
from typing import List, Tuple
from itertools import product

import pipeline.extern.sd_baseline_qa.sd_qa_utils as sd_qa_utils
import pipeline.extern.sd_baseline_qa.sd_qa_reports as sd_qa_reports
import pipeline.extern.sd_baseline_qa.mswrapper_sd as mswrapper_sd

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.pipelineqa as pipelineqa

LOG = infrastructure.get_logger(__name__)

default_thresholds = {
    "min_pXY_corr": 2.0,
    "max_pXY_cont": 12.0,
    "max_diff0_sigma": 5.0,
    "max_diffXY_sigma": 5.0,
    "sinusoid_sigma": 6.0,
    "maxant_rangeratio": 5.5,
    "blue_qa_128ch": True
}
#Dictionary with thresholds and switches for the different metrics of the QA

def qascorefunc(nsigma: float, score_top: float = 0.67, score_bottom: float = 0.34,
                nsigma_threshold: float = 3.5, nsigma_bottom: float = 10.0):
    '''Function used to calculate the QA score numerical evaluation as a linear mapping between the number of sigma excess
    of the outlier and the QA score value.
    param:
        nsigma: Number of sigma of detected outlier
        score_top: upper range of QA score value to consider
        score_bottom: lower  range of QA score value to consider
        nsigma_threshold: Number of sigmas set as threshold, value for which a QA score turns the color in this range.
        nsigma_bottom: Number of sigmas for which a blue QA scores turn bottom value. Must be greater than nsigma_threshold.
    '''

    return max(score_top - (score_top - score_bottom)*(nsigma - nsigma_threshold)/(nsigma_bottom - nsigma_threshold), score_bottom)


def rangefun(x: np.ma.MaskedArray, tail = 2.0):
    ''' Function to return the range of unmasked values of an array excluding a percentage
    tail/2 on each side of the distribution.
    param: tail (float): Percentage of data to be considered "outside" of the range,
                         percentiles of the limits are tail/2.0 on each side. Default = 2.0.
    '''
    unmasked_x = x.data[~x.mask]
    hi = np.percentile(unmasked_x, 100.0-tail/2.0)
    low = np.percentile(unmasked_x, tail/2.0)
    return hi - low

def top90(x: np.ma.MaskedArray):
    ''' Function to return a top 90% percentile of a masked array.
    '''
    unmaskedx = x.data[~x.mask]
    return np.percentile(unmaskedx, 90.0)

def data_stats_bl(msw: mswrapper_sd.MSWrapperSD, scisel: np.ndarray, min_nwave: int = 2, max_nwave_frac: float = 0.15, n_sigma_nwave: float = 5.0):
    ''' Function used to calculate basic statistics used by the QA score
    generating functions calc_baseline_qascore_single() and calc_qascores_collection().
    params:
      msw: MSWrapperSD object containing the piece of dataset to compute statistic on.
      scisel: Boolean numpy array containing a selection vector of the science line channels
      min_nwave: (int) Minimum wavenumber considered in Fourier analysis. Default: 2
      max_nwave_frac: (float) Maximum wavenumber considered in Fourier analysis, given as a fraction of the maximum wavenumber possible. Default: 0.15
      n_sigma_nwave: (float) Number of sigmas for the power of a wavenumber over the median to be considered an excess.
    outputs:
      Function will leave results inside the msw object, in the "analysis" dictionary.
    '''
    
    #Selection of skylines
    skylinesel = sd_qa_utils.get_skysel_from_msw(msw)
    #Continuum only selection
    contsel = (~skylinesel) & (~scisel['all'])
    #List of scans
    scanlist = msw.spw_setup['scansforfield'][str(msw.fieldid)]
    nscans = len(scanlist)
    extscanlist = copy.deepcopy(scanlist)
    extscanlist.append('all')

    #Check fully flagged pieces of data
    is_fully_flagged = {scan: {pol: ((msw.time_mean_scan is None) or (np.sum(msw.time_mean_scan[scan].mask[pol]) == msw.nchan)) for pol in range(msw.npol)} for scan in extscanlist}
    if msw.analysis is None:
        msw.analysis = {}

    msw.analysis['is_fully_flagged'] = is_fully_flagged

    #If no data, fill in with dummy values
    if msw.nrows == 0:
        msw.analysis['scisel'] = scisel
        msw.analysis['skylinesel'] = skylinesel
        msw.analysis['prXY'] = None
        msw.analysis['sigma_cont'] = np.nan
        msw.analysis['data_range'] = np.nan
        msw.analysis['flatness'] = np.nan
        msw.analysis['powerstats'] = None
        msw.analysis['powerspec'] = None
        return
        
    if msw.data is not None:
        (npol, nchan, ntstamps) = np.shape(msw.data) 

    #Calculate per-channel stats
    prXY = np.ma.MaskedArray(np.zeros(msw.nchan), mask=np.zeros(msw.nchan, dtype=np.bool_))
    if (msw.data is not None) and (npol == 2):
        for ch in range(msw.nchan):
            prXY[ch] = stats.mstats.pearsonr(msw.data[0,ch,:], msw.data[1,ch,:])[0]
    std_prXY = np.abs(1.0 - prXY**2)/np.sqrt(ntstamps - 3)

    #Calculate the median data noise, data range and power spectrum quantities
    sigma_cont = {}
    data_range = {}
    powerspec = {}
    powerstats = {}
    flatness = {}

    maxnwave = min(int(max_nwave_frac*msw.nchan), int(msw.nchan/2.0))
    freqs = msw.spw_setup[msw.spw]['chanfreqs']*1.e-09
    xfft = np.fft.rfftfreq(len(freqs), d=np.abs(freqs[1]-freqs[0]))

    for scan in extscanlist:
        sigma_cont[scan] = {}
        data_range[scan] = {}
        powerspec[scan] = {}
        powerstats[scan] = {}
        flatness[scan] = {}
        for pol in range(msw.npol):
            if is_fully_flagged[scan][pol]:
                powerstats[scan][pol] = None
                powerspec[scan][pol] = None
                flatness[scan][pol] = np.nan
                sigma_cont[scan][pol] = np.nan
                data_range[scan][pol] = np.nan
                continue
            #For flatness calculation, do copy, mask science and sky lines, and linear detrend
            data = copy.deepcopy(msw.time_mean_scan[scan][pol])
            #Estimate median standard deviations in each data piece
            sigma_res = sd_qa_utils.sigma_segments(np.arange(msw.nchan)[contsel], msw.time_mean_scan[scan][pol][contsel])
            sigma_cont[scan][pol] = np.median(sigma_res['sigmas'])
            #Calculate 95% range of data
            data_range[scan][pol] = rangefun(msw.time_mean_scan[scan][pol][contsel], tail=2.5)

            #Power spectrum quantities
            max_stable_nwave = sd_qa_utils.get_max_stable_wavenumber(scisel['all'], sigma_cont[scan][pol])
            data.mask[scisel['all']] = True
            data.mask[skylinesel] = True
            datafit = np.ma.polyfit(freqs, data, 1)
            datalinsub = data - (freqs*datafit[0] + datafit[1])
            #Calculate power spectrum and convert to dB
            pwrspec, _ = sd_qa_utils.abs_rfft_wmask(datalinsub)
            mupwrspec, sigmapwrspec = sd_qa_utils.robuststats(pwrspec[1:maxnwave])
            excesspwr = (pwrspec - mupwrspec)/sigmapwrspec
            excesspwr[0:min_nwave] = 0.0
            excesspwr[maxnwave:] = 0.0
            idxpeak = np.argsort(excesspwr)[-1]
            powerspec[scan][pol] = pwrspec
            flatness[scan][pol] = 20.0*np.log10(np.exp(np.mean(np.log(pwrspec[1:maxnwave])))/np.mean(pwrspec[1:maxnwave]))
            #Get waves numbers for sinusoid baseline subtraction or plotting
            nwaves = np.where(((pwrspec-mupwrspec)/sigmapwrspec > n_sigma_nwave))[0]
            powerstats[scan][pol] = {'nwavemax': idxpeak, 'powermax': pwrspec[idxpeak], 'peakfreq': np.abs(1.0/xfft[idxpeak]), 'mupwrspec': mupwrspec, 'sigmapwrspec': sigmapwrspec, 'peakpwrexcess': excesspwr[idxpeak], 'nwaves': nwaves, 'max_stable_nwave': max_stable_nwave}
 
    msw.analysis['scisel'] = scisel
    msw.analysis['skylinesel'] = skylinesel
    msw.analysis['prXY'] = prXY
    msw.analysis['std_prXY'] = std_prXY
    msw.analysis['sigma_cont'] = sigma_cont
    msw.analysis['data_range'] = data_range
    msw.analysis['flatness'] = flatness
    msw.analysis['powerstats'] = powerstats
    msw.analysis['powerspec'] = powerspec

    return


def calc_baseline_qascore_single(
        msw: mswrapper_sd.MSWrapperSD,
        thresholds: dict = None
):
    '''Function that calculates the hsd_baseline QA score for a given dataset msw object.
    param:
        msw: MSWrapper_SD object containing the data statistics used for the QA scores calculation. This method will use the
             analysis dictionary inside the msw object.
        thresholds: Dictionary containing threshold parameters.
    returns:
        Function modifies the 'analysis' attribute inside the MSWrapperSD object to add a list of all per-scan QA scores.
    '''

    GHz = 1e-9
    MHz = 1e-6

    if thresholds is None:
        thresholds = default_thresholds

    #Set QA scores value range
    if (msw.nchan <= 128) and thresholds['blue_qa_128ch']:
        this_score_top = 0.80
        this_score_bottom = 0.67
    else:
        this_score_top = 0.67
        this_score_bottom = 0.34

    #output variable for QA scores
    qascores_list = []

    #Get dataset array size
    (npol, nchan, nrows) = (msw.npol, msw.nchan, msw.nrows)

    msname = pathlib.Path(msw.fname).name

    #Channel frequencies in GHz and separation in MHz, and min and max frequency
    freqs = msw.spw_setup[msw.spw]['chanfreqs']*GHz

    chansep = np.abs(msw.spw_setup[msw.spw]['chansep']*MHz)
    minfreq = np.min(freqs)
    maxfreq = np.max(freqs)

    repBW = msw.spw_setup['representativeBandwidthinHz']*0.1

    #Representative BW in MHz, sensitivity Goal in Jy
    msw.analysis['sensgoal'] = msw.spw_setup['sensitivityGoalinJy'] if repBW is None else msw.spw_setup['sensitivityGoalinJy'] * np.sqrt(repBW / chansep)
    sensgoal = msw.analysis['sensgoal']

    #Scan numbers
    scanlist = msw.spw_setup['scansforfield'][str(msw.fieldid)]
    fieldname = msw.spw_setup['namesfor'][str(msw.fieldid)][0]
    tsys_scanlist = msw.spw_setup['scan']['*CALIBRATE_ATMOSPHERE#OFF_SOURCE*']

    nscans = len(scanlist)
    extscanlist = copy.deepcopy(scanlist)
    extscanlist.append('all')

    #Science line channels
    scisel = msw.analysis.get('scisel')

    #Selection of skylines
    skylinesel = msw.analysis.get('skylinesel')#  sd_qa_utils.get_skysel_from_msw(msw)

    #Check fully flagged pieces of data
    is_fully_flagged = msw.analysis.get("is_fully_flagged")

    lineidx = sorted([l for l in scisel.keys() if l!='all'])
    sci_line_detected = (np.sum(scisel['all']) > 0)
    notflaggedscans = [scan for scan in extscanlist if (not is_fully_flagged[scan].get(0)) and (not is_fully_flagged[scan].get(1))]

    #If this is an empty piece of the dataset, return QA score of 1.0, there is nothing to do here
    if (nrows == 0) or (len(notflaggedscans) == 0):
        #Create objects to create QAscore
        reason = 'BLine.deviation'
        applies_to = pipelineqa.TargetDataSelection(
            vis={msname},
            scan={"All"},
            intent={'*OBSERVE_TARGET#ON_SOURCE*'},
            spw={msw.spw},
            ant={msw.antenna},
            pol={'NA'},
            field={fieldname},
        )

        comes_from = pipelineqa.QAOrigin(metric_name=reason, metric_score=0.0, metric_units='n-sigma deviation')

        qascore = pipelineqa.QAScore(
            1.0,
            longmsg=f'{msname}: All data flagged for spw {msw.spw}, antenna {msw.antenna} in scan all (field {fieldname}).',
            shortmsg='Baseline deviation',
            origin=comes_from,
            applies_to=applies_to,
            hierarchy=reason
        )

        return msw, qascore, [qascore], 'N/A'

    #Calculate XX/YY deviations from 0 and Fourier analysis
    diff0 = {}
    sinusoid_sigma = {}
    for scan in extscanlist:
        diff0[scan] = {}
        sinusoid_sigma[scan] = {}
        for pol in range(msw.npol):
            #If scan/polarization fully flagged, continue
            if is_fully_flagged[scan][pol]:
                diff0[scan][pol] = np.nan
                sinusoid_sigma[scan][pol] = np.nan
                continue

            #Check if there is any deviation from zero in the continuum (line-free channels)
            diff0[scan][pol] = np.ma.abs(msw.time_mean_scan[scan][pol])
            contsel = (~scisel['all']) & (~msw.time_mean_scan[scan].mask[pol]) & (~skylinesel)
            max_diff0 = np.ma.max(diff0[scan][pol][contsel])
            max_diff0_sigma = max_diff0/msw.analysis['sigma_cont'][scan][pol]

            #Check If there are any significant Fourier modes
            if len(msw.analysis['powerstats'][scan][pol]['nwaves']) > 0:
                sinusoid_sigma[scan][pol] = {'n_sigma': msw.analysis['powerstats'][scan][pol]['peakpwrexcess'], 'n_amp': (2.0/msw.nchan)*msw.analysis['powerstats'][scan][pol]['powermax'], 'freqMHz': (1000.0*msw.analysis['powerstats'][scan][pol]['peakfreq']), 'nwave': int(msw.analysis['powerstats'][scan][pol]['nwavemax'])}
            else:
                sinusoid_sigma[scan][pol] = {'n_sigma': 0.0, 'n_amp': 0.0, 'freqMHz': 0.0, 'nwave': 0}

            #Put yellow QA score if there is deviation from zero
            if (len(notflaggedscans) > 0) and (max_diff0_sigma > thresholds['max_diff0_sigma']):
                polstr = 'XX' if (pol == 0) else 'YY'
                qascore_value = qascorefunc(max_diff0_sigma, score_top = this_score_top, score_bottom = this_score_bottom, nsigma_threshold = thresholds['max_diff0_sigma'], nsigma_bottom = 2.0*thresholds['max_diff0_sigma'])
                reason = 'BLine.continuum.dev'
                applies_to = pipelineqa.TargetDataSelection(
                    vis={msname},
                    scan={scan},
                    intent={'*OBSERVE_TARGET#ON_SOURCE*'},
                    spw={msw.spw},
                    ant={msw.antenna},
                    pol={'NA'},
                    field={fieldname},
                )

                comes_from = pipelineqa.QAOrigin(metric_name=reason, metric_score=float(np.round(max_diff0_sigma, 3)), metric_units='Deviation from 0')
                message = f'{msname}: Significant baseline deviation for spw {msw.spw}, antenna {msw.antenna}, field {fieldname}, scan {scan}, polarization {polstr}.'

                qascore = pipelineqa.QAScore(
                    score=float(np.round(qascore_value, 3)),
                    longmsg=f'{msname}: All data flagged for spw {msw.spw}, antenna {msw.antenna} in scan all (field {fieldname}).',
                    shortmsg='Baseline deviation',
                    origin=comes_from,
                    applies_to=applies_to,
                    hierarchy=reason
                )

                qascores_list.append(qascore)

            #Put a yellow QA scores if there is a sinusoidal residual in line free channels
            if (len(notflaggedscans) > 0) and (sinusoid_sigma[scan][pol]['n_sigma'] > thresholds['sinusoid_sigma']):
                polstr = 'XX' if (pol == 0) else 'YY'
                qascore_value = qascorefunc(sinusoid_sigma[scan][pol]['n_sigma'], score_top = this_score_top, score_bottom = this_score_bottom, nsigma_threshold = thresholds['sinusoid_sigma'], nsigma_bottom = 2.0*thresholds['sinusoid_sigma'])
                reason = 'BLine.continuum.sinusoid'

                applies_to = pipelineqa.TargetDataSelection(
                    vis={msname},
                    scan={scan},
                    intent={'*OBSERVE_TARGET#ON_SOURCE*'},
                    spw={msw.spw},
                    ant={msw.antenna},
                    pol={polstr},
                    field={fieldname},
                )

                comes_from = pipelineqa.QAOrigin(
                    metric_name=reason,
                    metric_score=float(np.round(sinusoid_sigma[scan][pol]['n_sigma'], 3)),
                    metric_units='Deviation from 0'
                )

                # This is similar to the original code but slightly modified to accommodate the new
                # NoneSafeDict class. The conditional is needed because the NoneSafeDict is a fudge
                # fix to avoid a long list of if else statements.
                _calculation = 100.0*sinusoid_sigma[scan][pol]['n_amp']/sensgoal if sensgoal is not None else None
                _calculation = 1.0 if _calculation == None else _calculation

                message = ('{0:s}: Sinusoidal baseline deviation for spw {1:s}, antenna {2:s}, '
                           'field {3:s}, scan {4:s}, polarization {5:s}. Amplitude {6:.1f}% of '
                           'requested RMS, wavelength {7:.3f}MHz (nwave={8:s})').format(
                            msname,
                            str(msw.spw),
                            msw.antenna,
                            fieldname,
                            str(scan),
                            polstr,
                            _calculation,
                            sinusoid_sigma[scan][pol]['freqMHz'],
                            str(sinusoid_sigma[scan][pol]['nwave'])
                        )

                qascore = pipelineqa.QAScore(
                    score=float(np.round(qascore_value, 3)),
                    longmsg=message,
                    shortmsg='Baseline deviation',
                    origin=comes_from,
                    applies_to=applies_to,
                    hierarchy=reason
                )

                qascores_list.append(qascore)

    if (len(notflaggedscans) > 0) and (npol == 2):
        #Calculate XX/YY deviation, XX-YY difference, XX/YY polarizations range ratio
        XYdiff = {}
        XYdiffsigma = {}
        XYrangeratio = {}
        for scan in extscanlist:
            XYdiffsigma[scan] = np.sqrt(msw.analysis['sigma_cont'][scan][0]**2 + msw.analysis['sigma_cont'][scan][1]**2)
            XYdiff[scan] = np.ma.abs(msw.time_mean_scan[scan][0] - msw.time_mean_scan[scan][1])/XYdiffsigma[scan]
            Xrange = msw.analysis['data_range'][scan][0]
            Yrange = msw.analysis['data_range'][scan][1]
            maxrange = max(Xrange, Yrange)
            minrange = min(Xrange, Yrange)
            XYrangeratio[scan] = maxrange/minrange

    #Test for "science lines" detections that don't correlate between XX and YY
    #and XX-YY difference
    if sci_line_detected and (len(notflaggedscans) > 0) and (npol == 2):
        #Test line differences from zero
        max_diff0XX_lines = np.array([np.nanmax([np.ma.max(diff0[scan][0][scisel[l]])/msw.analysis['sigma_cont'][scan][0] for scan in notflaggedscans]) for l in lineidx])
        max_diff0YY_lines = np.array([np.nanmax([np.ma.max(diff0[scan][1][scisel[l]])/msw.analysis['sigma_cont'][scan][1] for scan in notflaggedscans]) for l in lineidx])
        high_diff0XX = (max_diff0XX_lines > thresholds['max_diff0_sigma'])
        high_diff0YY = (max_diff0YY_lines > thresholds['max_diff0_sigma'])
        #Test Difference between XX and YY
        max_diffXY_lines = np.array([np.nanmax([np.ma.max(XYdiff[scan][scisel[l]])/XYdiffsigma[scan] for scan in extscanlist if (not is_fully_flagged[scan][0]) and (not is_fully_flagged[scan][1])]) for l in lineidx])
        high_diffXY = (max_diffXY_lines > thresholds['max_diffXY_sigma'])
        #Test Pearson's r between XX and YY on science lines
        max_pXY_lines = np.array([np.nanmax((msw.analysis['prXY']/msw.analysis['std_prXY'])[scisel[l]]) for l in lineidx])
        low_pXY = (max_pXY_lines < thresholds['min_pXY_corr'])
        low_pXY_high_diff = (low_pXY & (high_diff0XX | high_diff0YY | high_diffXY))
        if (np.sum(low_pXY_high_diff) > 0) or (np.sum(low_pXY) > 0):
            idxmin_pXY = np.argsort(max_pXY_lines)[0]
            min_pXY = max_pXY_lines[idxmin_pXY]
            chan_str = sd_qa_utils.range2str(scisel[idxmin_pXY])
            msw.analysis['idxmin_pXY'] = idxmin_pXY

        #Case of X/Y non-correlation and XX-YY difference
        if np.sum(low_pXY_high_diff) > 0:
            qascore_value = qascorefunc(min_pXY, score_top = this_score_top, score_bottom = this_score_bottom, nsigma_threshold = thresholds['min_pXY_corr'], nsigma_bottom = 0.0)
            reason = 'BLine.scienceline.lowpXYsci'
            polstr = 'XX' if (pol == 0) else 'YY'

            applies_to = pipelineqa.TargetDataSelection(
                vis={msname},
                scan={scan},
                intent={'*OBSERVE_TARGET#ON_SOURCE*'},
                spw={msw.spw},
                ant={msw.antenna},
                pol={polstr},
                field={fieldname},
            )
            comes_from = pipelineqa.QAOrigin(metric_name=reason, metric_score=float(np.round(min_pXY, 3)), metric_units='XX-YY Pearsons cross-correlation')
            qascore = pipelineqa.QAScore(float(np.round(qascore_value, 3)), longmsg=f'{msname}: Significant lack of XX-YY correlation and XX-YY difference in science line detection for spw {msw.spw}, antenna {msw.antenna}, field {fieldname} in channels {chan_str}.', shortmsg='Science line detection problem', origin=comes_from, applies_to=applies_to, hierarchy=reason)

            qascores_list.append(qascore)

        elif np.sum(low_pXY) > 0:
            qascore_value = qascorefunc(min_pXY, score_top = 0.80, score_bottom = this_score_top, nsigma_threshold = thresholds['min_pXY_corr'], nsigma_bottom = 0.0)
            reason = 'BLine.scienceline.lowpXYsci'
            polstr = 'XX' if (pol == 0) else 'YY'

            applies_to = pipelineqa.TargetDataSelection(
                vis={msname},
                scan={scan},
                intent={'*OBSERVE_TARGET#ON_SOURCE*'},
                spw={msw.spw},
                ant={msw.antenna},
                pol={polstr},
                field={fieldname},
            )
            comes_from = pipelineqa.QAOrigin(metric_name=reason, metric_score=float(np.round(min_pXY, 3)), metric_units='XX-YY Pearsons cross-correlation')
            qascore = pipelineqa.QAScore(float(np.round(qascore_value, 3)), longmsg=f'{msname}: Significant lack of XX-YY correlation in science line detection for spw {msw.spw}, antenna {msw.antenna}, field {fieldname} in channels {chan_str}.', shortmsg='Science line detection problem', origin=comes_from, applies_to=applies_to, hierarchy=reason)
            qascores_list.append(qascore)

    #Test for any weird correlation in continuum channels, which should not be
    if (len(notflaggedscans) > 0) and (npol == 2):

        contsel = (~scisel['all']) & (~skylinesel) & (~msw.time_mean_scan['all'].mask[0]) & (~msw.time_mean_scan['all'].mask[1])

        #Test Pearson's r between XX and YY on continuum channels
        idxmax_pXY_cont = np.ma.argmax(msw.analysis['prXY'][contsel])
        max_pXY_cont = ((msw.analysis['prXY']/msw.analysis['std_prXY'])[contsel])[idxmax_pXY_cont]
        freq_max_pXY_cont = (freqs[contsel])[idxmax_pXY_cont]

        #Test XX/YY data ranges
        maxXYrange = 0.0
        idxmax_XYranges = np.ma.argmax([XYrangeratio[scan] for scan in notflaggedscans])
        scanmax_XYranges = np.array(notflaggedscans)[idxmax_XYranges]
        if ((type(scanmax_XYranges) == str) or (type(scanmax_XYranges) == np.str_)) and scanmax_XYranges.isdigit():
            scanmax_XYranges = int(scanmax_XYranges)
        maxXYrange = XYrangeratio[scanmax_XYranges]

        if (max_pXY_cont > thresholds['max_pXY_cont']):
            qascore_value = qascorefunc(max_pXY_cont, score_top = this_score_top, score_bottom = this_score_bottom, nsigma_threshold = thresholds['max_pXY_cont'], nsigma_bottom = 2.0*thresholds['max_pXY_cont'])
            print('max_pXY_cont: '+str(max_pXY_cont)+' -> qascore_value: '+str(qascore_value))
            reason = 'BLine.scienceline.highpXYcont'

            applies_to = pipelineqa.TargetDataSelection(
                vis={msname},
                scan={scan},
                intent={'*OBSERVE_TARGET#ON_SOURCE*'},
                spw={msw.spw},
                ant={msw.antenna},
                pol={pol},
                field={fieldname},
            )
            comes_from = pipelineqa.QAOrigin(metric_name=reason, metric_score=float(np.round(max_pXY_cont, 3)), metric_units='XX-YY Pearsons cross-correlation')
            qascore = pipelineqa.QAScore(float(np.round(qascore_value, 3)), longmsg=f'{msname}: Possible miss of science line detection for spw {msw.spw}, antenna {msw.antenna}, field {fieldname} at {freq_max_pXY_cont:.4f}MHz.', shortmsg='Science line detection problem', origin=comes_from, applies_to=applies_to, hierarchy=reason)
            qascores_list.append(qascore)

        if maxXYrange > thresholds['maxant_rangeratio']:
            polstr = 'XX' if msw.analysis['data_range'][scanmax_XYranges][0] > msw.analysis['data_range'][scanmax_XYranges][1] else 'YY'
            qascore_value = qascorefunc(maxXYrange, score_top = this_score_top, score_bottom = this_score_bottom, nsigma_threshold = thresholds['maxant_rangeratio'], nsigma_bottom = 2.0*thresholds['maxant_rangeratio'])
            reason = 'BLine.continuum.XYrangeratio'

            applies_to = pipelineqa.TargetDataSelection(
                vis={msname},
                scan={scan},
                intent={'*OBSERVE_TARGET#ON_SOURCE*'},
                spw={msw.spw},
                ant={msw.antenna},
                pol={polstr},
                field={fieldname},
            )
            comes_from = pipelineqa.QAOrigin(metric_name=reason, metric_score=float(np.round(maxXYrange, 3)), metric_units='Deviation from 0')
            message = f'{msname}: Baseline data range significantly greater compared to other polarization for spw {msw.spw}, antenna {msw.antenna}, field {fieldname}, scan {scan}, polarization {polstr}.'
            qascore = pipelineqa.QAScore(float(np.round(qascore_value, 3)), longmsg=message, shortmsg='Continuum data range', origin=comes_from, applies_to=applies_to, hierarchy=reason)
            qascores_list.append(qascore)

    #Save QA scores generated into the msw data structure
    if 'qascores_list' not in msw.analysis.keys():
        msw.analysis['qascores_list'] = []

    msw.analysis['qascores_list'].extend(qascores_list)

    return

def calc_qascores_collection(
        mswCollection: dict,
        thresholds=None
):
    '''Function that calculates the hsd_baseline QA score for a collection of msw objects. The task will compare the statistics between the different antennas for each spectral window and field.
    param:
        mswCollection: Dictionary containing MSWrapper_SD objects to be analyzed together.
        thresholds: Dictionary containing threshold parameters.
    returns:
        Function modifies the 'analysis' attribute inside the MSWrapperSD object to add a list of QA scores.
    '''

    #Get variables of the collection
    if thresholds is None:
        thresholds = default_thresholds

    (mswCollectionKeys, mslist, idxfirst, fieldnames, names_for, fieldid_for, antnames_for, spwlist, spwnamelist, mslist_for_fieldname) = sd_qa_utils.get_mswCollection_params(mswCollection)
    
    #initialize output list
    qascore_list = []

    #Iterate over MS, SPW and Field, and then generate comparison matrix
    for ms in mslist:
        #Get a spw_setup dictionary
        spw_setup = mswCollection[mswCollectionKeys[idxfirst[ms]]].spw_setup
        #Get the DDI to SPW conversion
        spw_from_ddi = {int(spw_setup[spw]['ddi']): int(spw) for spw in spw_setup['spwlist']}
        #Get SPW names
        spwname_for_spw = {int(s): str(spw_setup['spwnames'][k]) for k,s in enumerate(spw_setup['spwlist'])}
        #Antenna names
        antnames = antnames_for[ms]
        for spw in spw_setup['spwlist']:
            for field in fieldnames:
                fieldid = fieldid_for[ms][field]
                print(f'Doing spw {spw}, field {field}')
                ants = []
                scans = []
                pols = []
                data_ranges = []
                for antid in range(len(antnames)):
                    msw = mswCollection[(ms, spw, antnames[antid], str(fieldid))]

                    #Set QA scores value range
                    if (msw.nchan <= 128) and thresholds['blue_qa_128ch']:
                        this_score_top = 0.80
                        this_score_bottom = 0.67
                    else:
                        this_score_top = 0.67
                        this_score_bottom = 0.34

                    if msw.nrows > 0:
                        scanlist = msw.spw_setup['scansforfield'][str(msw.fieldid)]
                        nscans = len(scanlist)
                        extscanlist = copy.deepcopy(scanlist)
                        extscanlist.append('all')
                        for scan in extscanlist:
                            for pol in range(msw.npol):
                                ants.append(antnames[antid])
                                scans.append(scan)
                                pols.append(pol)
                                data_ranges.append(msw.analysis['data_range'][scan][pol])
                data_ranges = np.array(data_ranges)
                min_data_ranges = np.nanmin(data_ranges)
                idxmax_data_ranges = np.nanargmax(data_ranges)
                max_data_ranges = data_ranges[idxmax_data_ranges]
                if (max_data_ranges/min_data_ranges > thresholds['maxant_rangeratio']):
                    metricvalue = max_data_ranges/min_data_ranges
                    qascore_value = qascorefunc(metricvalue, score_top = this_score_top, score_bottom = this_score_bottom, nsigma_threshold = thresholds['maxant_rangeratio'], nsigma_bottom = 2.0*thresholds['maxant_rangeratio'])
                    reason = 'BLine.continuum.XYrangeratio'
                    triggerscan = np.array(scans)[idxmax_data_ranges]
                    triggerant = np.array(ants)[idxmax_data_ranges]
                    triggerscan = np.array(scans)[idxmax_data_ranges]
                    triggerpol = np.array(pols)[idxmax_data_ranges]
                    triggerpolstr = 'XX' if (triggerpol == 0) else 'YY'

                    applies_to = pipelineqa.TargetDataSelection(
                        vis={ms},
                        scan={triggerscan},
                        intent={'*OBSERVE_TARGET#ON_SOURCE*'},
                        spw={msw.spw},
                        ant={triggerant},
                        pol={triggerpolstr},
                        field={field},
                    )
                    comes_from = pipelineqa.QAOrigin(metric_name=reason, metric_score=float(np.round(metricvalue, 3)), metric_units='Data range Max to Min ratio')
                    message = f'{ms}: Data range excess for spw {spw}, antenna {triggerant}, field {field}, scan {triggerscan}, polarization {triggerpolstr}.'
                    qascore = pipelineqa.QAScore(float(np.round(qascore_value, 3)), longmsg=message, shortmsg='Baseline data range excess', origin=comes_from, applies_to=applies_to, hierarchy=reason)
                    #Append qasocres to msw analysis dict
                    msw = mswCollection[(ms, spw, triggerant, str(fieldid))]
                    if 'qascores_list' not in msw.analysis.keys():
                        msw.analysis['qascores_list'] = []
                    msw.analysis['qascores_list'].append(qascore)

    return

def load_mswCollection(mswCfile: str):
    print('Loading mswCollection dat from buffer '+mswCfile+' ...')
    f = open(mswCfile, 'rb')
    mswCollection = pickle.load(f)
    f.close()
    return mswCollection

def save_mswCollection(mswCollection: dict, mswCfile: str):
    print('Buffering mswCollection...')
    f = open(mswCfile, 'wb')
    pickle.dump(mswCollection, f)
    f.close()
    return

def load_and_stats_bl(
        measurementset: str,
        basename,
        sci_line_data: List = None,
        buffer_data: bool = True,
        buffer_fname: str = 'mswCollection.bl.buffer.pkl'
) -> dict:
    """
    Load a collection of MSWrapper_SD objects, and run a basic filter and statistics on each of them.
    Return a dictionary of MSWrapper_SD objects (an mswCollection), indexed by tuples in the form (ms, spw, ant, field id).
    param:
        ms_name: List of MS names to load.
                     to exclude them for triggering a false XX-YY deviation.
        buffer_data: True/False whether to save/load the MSW collection to disk. This is aimed at easing the
                    use for repeated execution of the code, mostly testing.
    """



    #Load data and gather statistics
    mswCollection = {}
    #for ms in ms_name:
    #msonly = ms.split('/')[-1]

    #Load metadata
    spw_setup = sd_qa_utils.getSpecSetup(myms=measurementset)
    #Get science line selection vectors from context and spw_setup
    science_line_sel = sd_qa_utils.line_list_to_datasel(lines=sci_line_data, spw_setup=spw_setup)
    #Load original MS metadata

    spw_setup_orig = sd_qa_utils.getSpecSetup(myms=basename)
    #In case any SPW reindex, need to map SPWs
    sortidx = np.argsort(spw_setup['spwnames'])
    sortidx_orig = np.argsort(spw_setup_orig['spwnames'])
    sorted_spw = np.array(spw_setup['spwlist'])[sortidx]
    sorted_spw_orig = np.array(spw_setup_orig['spwlist'])[sortidx_orig]
    spwmap = {sorted_spw[i]: sorted_spw_orig[i] for i in range(len(sorted_spw))}
    #Iterate over SPW, antenna, FieldID
    datapieces = product(spw_setup['spwlist'], spw_setup['antnames'], spw_setup['fieldid']['*OBSERVE_TARGET#ON_SOURCE*'])

    for datapiece in datapieces:
        (spw, ant, fieldid) = datapiece
        print(spw_setup_orig[spw]["npol"])
        # We want to stop the analysis if there is only a single polarization.
        if spw_setup_orig[spw]["npol"] == 1:
            LOG.debug(f"Skipping spw: {spw} because it is single polarization.")
            continue

        fieldname = str(spw_setup['namesfor'][str(fieldid)][0])
        print('Processing MS {0:s}, SPW {1:d}, antenna {2:s}, FieldID {3:d}'.format(measurementset,spw,ant,fieldid))
        #Load ON-SOURCE data and create MSWrapperSD object
        mswCollection[(measurementset, spw, ant, str(fieldid))] = mswrapper_sd.MSWrapperSD.create_from_ms(
            fname=measurementset,
            spw=spw,
            antenna=ant,
            fieldid=fieldid,
            column='DATA',
            onoffsel='ON',
            spw_setup=spw_setup,
            attach_tsys_data=False
        )

        #Get Tsys data from original MS
        mswCollection[(measurementset, spw, ant, str(fieldid))].tsysdata = sd_qa_utils.getAtmDataForSPW(basename, spw_setup_orig, spwmap[spw], ant)
        #Gather necessary stats
        LOG.info('>> Data stats for '+str((measurementset, spw, ant, str(fieldid))))
        data_stats_bl(mswCollection[(measurementset, spw, ant, str(fieldid))], science_line_sel[fieldname][spw])
        #Clear raw data from MSWrapper object to release memory
        mswCollection[(measurementset, spw, ant, str(fieldid))].data = None

    if not mswCollection:
        raise sd_qa_utils.FailedAnalysisException(
            "Measurementset doesn't contain analysis relevant data. Like contains only a single polarization.")
    #if buffer_data and (not os.path.exists(buffer_fname)):
    #    save_mswCollection(mswCollection, buffer_fname)

    return mswCollection

def add_non_outlier_qascores(mswCollection: dict):
    '''Function to fill in a 1.0 QA scores for MSWrapperSD object with no outliers and hence
    no lower QA scores.
    param: mswCollection dictionary with all MSWrapperSD objects previously analyzed
    output: Add 1.0 QA scores to 'qascores_list' attribute inside each MSWwrapperSD 'analysis' dictionary that doesn't have any QA score.
    '''
    #Case of no outliers and no information
    #Iterate over collection of individual MSWrapperSD objects
    for key, msw in mswCollection.items():
        (ms, spw, ant, fieldid) = key
        if 'qascores_list' not in msw.analysis.keys():
            msw.analysis['qascores_list'] = []
        if len(msw.analysis['qascores_list']) == 0:
            #Create objects to create QAscore
            reason = 'BLine.continuum'
            fieldname = msw.spw_setup['namesfor'][str(msw.fieldid)][0]
            scanlist = msw.spw_setup['scansforfield'][str(msw.fieldid)]

            for scan in scanlist:
                applies_to = pipelineqa.TargetDataSelection(
                    vis={ms},
                    scan={scan},
                    intent={'*OBSERVE_TARGET#ON_SOURCE*'},
                    spw={msw.spw},
                    ant={msw.antenna},
                    pol={"NA"},
                    field={fieldname},
                )
                comes_from = pipelineqa.QAOrigin(metric_name=reason, metric_score=0.0, metric_units='Deviation from 0')

                qascore_value = 1.0
                longmsg = '{0:s}: No significant baseline deviation detected for spw {1:s}, antenna {2:s} in all scans (field {3:s})'.format(ms, str(spw), ant, fieldname)
                qascore = pipelineqa.QAScore(
                    qascore_value,
                    longmsg=f"{ms}: {longmsg}",
                    shortmsg='Baseline deviation',
                    origin=comes_from,
                    applies_to=applies_to,
                    hierarchy=reason
                )

                msw.analysis['qascores_list'].append(qascore)

    return

def find_min_qascores(mswCollection: dict):
    '''Find the lowest QAscore of each data piece.
    param: mswCollection dictionary with all MSWrapperSD objects previously analyzed
    output: 'min_qascore' attribute inside each MSWwrapperSD 'analysis' dictionary with the link to the lowest QA score.
    '''
    
    #Iterate over collection of individual MSWrapperSD objects
    for key, msw in mswCollection.items():
        qascores_list = msw.analysis['qascores_list']
        scores = [qascore.score for qascore in qascores_list]
        idxmin = np.argmin(scores)
        msw.analysis['min_qascore'] = qascores_list[idxmin]

    return

def get_ms_baseline_qascores(
        ms_name: str,
        basename: str,
        sci_line_data: List = None,
        thresholds=None,
        plot_output_path: str = '.',
        weblog_output_path: str = '.',
        buffer_data: bool = True
) -> Tuple[list, list, list]:

    '''Function used to obtain baseline X-Y QA score on a list of calibrated MSs, at the
    baseline stage of SD` pipeline.
    param:
        ms_name: List of MS to process
        thresholds: Dictionary containing threshold parameters for ON-source XX-YY deviations,
                    Trec deviations, minimum deviation level, and QA score scaling.
        plot_output_path: (str) Path to save output plots.
        weblog_output_path: (str) Path to save output plots if the plots are intended to
                            be a part of the pipeline weblog.
        buffer_data: True/False whether to buffer the data loaded from the MS into a pickle file.
        buffer_fname: (Str) Filename for the buffer data file.
    returns: Tuple of:
             1) the list of resulting QA scores
             2) dictionary of antenna names per MS
             3) a list of generated plots
    '''

    #Load data and gather statistics
    if thresholds is None:
        thresholds = default_thresholds

    mswCollection = load_and_stats_bl(
        ms_name,
        basename,
        sci_line_data=sci_line_data,
        buffer_data=buffer_data
    )

    #Get QA scores by analyzing individual data pieces
    #Iterate over collection of individual MSWrapperSD objects
    for key, msw in mswCollection.items():
        print('QA baseline analysis for single MSW object: '+str(key))
        (ms, spw, ant, fieldid) = key
        #Calculate QAscores
        calc_baseline_qascore_single(msw = msw, thresholds = thresholds)

    #Get QA scores by analyzing data pieces in antenna groups
    calc_qascores_collection(mswCollection, thresholds = thresholds)

    #Add 1.0 QA scores for data piece without outliers
    add_non_outlier_qascores(mswCollection)

    #Find minimum QAscores per data piece
    find_min_qascores(mswCollection)

    # Gather list of minimum QA scores and make plots for each minimum QA score
    # These variable names should be changed to support PEP8 standards but that is for another ticket.
    (
        mswCollectionKeys,
        mslist,
        idxfirst,
        fieldnames,
        names_for,
        fieldid_for,
        antnames_for,
        spwlist,
        spwnamelist,
        mslist_for_fieldname
    ) = sd_qa_utils.get_mswCollection_params(mswCollection)

    qascore_list = []
    plots_fnames = []
    for key, msw in mswCollection.items():
        qascore_list.append(msw.analysis['min_qascore'])
        fname = sd_qa_reports.plot_data_single_bl(msw, plot_output_path = plot_output_path)
        plots_fnames.append(fname)

    #if buffer_data:
    #    save_mswCollection(mswCollection, buffer_fname)

    return (qascore_list, antnames_for, plots_fnames)

