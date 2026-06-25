import os, sys
from typing import List, Tuple, Union
import numpy as np
import copy
import pickle
from itertools import product
import matplotlib.dates as mdates
import casatools
from scipy.stats import mstats

import pipeline.infrastructure.pipelineqa as pqa
from . import mswrapper_sd
from . import sd_qa_utils
from . import sd_qa_reports


### Dictionary of default Threshold values ###
# X-Y_freq_dev: Threshold for devation in ON-source XX-YY polarization data difference
# Trec_freq_dev: Threshold for Trec table variation from scan to scan (work both Xx and YY polarizations)
# sci_threshold: Threshold for science line FFT peak detection algorithm
# XYcorr_threshold: Threshold for science line X-Y cross-correlation detection algorithm
# min_freq_dev_percent: Threshold for minimum X-Y deviation amplitude (relative to Requested Sensitivity Goal, in percentage)
# nsigma_bottom: Number of sigmas for which a blue QA scores turn bottom value. Used int he linear mapping for QA scores
#                function qascorefunc(). Must be greater than nsigma_threshold.
# plot_threshold: Value of QA scores below which triggers plotting routines.
#
default_thresholds = {'X-Y_freq_dev': 15.0, 'Trec_freq_dev': 5.0,
                      'sci_threshold': 15.0, 'XYcorr_threshold': 15.0,
                      'min_freq_dev_percent': 50.0, 'nsigma_bottom': 100.0,
                      'plot_threshold': 0.95}

def data_stats_perchan(msw: mswrapper_sd.MSWrapperSD, filter_order: int = 5,
                       filter_cutoff: float = 0.01, loworder_to_zero: int = 3):
    '''Function that calculates summary statistics per channel for a MSWrapperSD object. This comprises the FFT peak (along
    the time dimension) and Pearson correlation coefficient between the XX and YY polarization, also in the time dimension.
    These vector are stored in the "data_stats" attribute from the MSWrapper_SD object and are later used by the function
    sci_line_det() to determine channels likely to correspond to science line emission.
    param:
        msw: MSWrapper_SD object for which to calculate the  data statistics used for the QA scores calculation.
        filter_order, filter_cutoff: (float) parameters to be used with signal.butter highpass filter applied at the beggining.
        loworder_to_zero: (int) Number of modes to zero-out at the beggining of the FFT. This is aimed at removing any low order
                          variation in the time dimension of the data.
        peak_modes (list(int)), peak_minsnr (float): Parameters passed to the function scipy.signal.find_peaks_cwt() to search for
                          peaks in the spectrum (abs(FFT)).
    returns:
        Dictionary "data_stats" as an attribute of the input MSWrapperSD object, containing two 1D vectors of size equal
        to the number of channels of the SPW:
        "peak_fft_pwr":  The peak of the absolute value of the FFT.
        "XYcorr": The Person correlation coefficient between XX and YY.
    '''

    #In case of empty object, return dummy arrays
    if msw.nrows == 0:
        nchan = msw.spw_setup[msw.spw]['nchan']
        msw.data_stats = {'peak_fft_pwr': np.ma.MaskedArray(np.zeros(nchan), mask=np.ones(nchan, dtype=bool)),
                          'XYcorr': np.ma.MaskedArray(np.zeros(nchan), mask=np.ones(nchan, dtype=bool))}
        return

    #Handle cases with 2 or 1 polarizations. Full stokes pol is not considered for now, so return dummy array for that.
    (npol, nchan, nrows) = np.shape(msw.data)
    maskfreq = np.min(msw.data.mask, axis=2)
    if npol == 2:
        maskfreq1D = maskfreq[0] | maskfreq[1]
    elif npol == 1:
        maskfreq1D = maskfreq[0]
    else:
        print('Error: Could not handle npol = '+str(npol))
        msw.data_stats = {'peak_fft_pwr': np.ma.MaskedArray(np.zeros(nchan), mask=np.ones(nchan, dtype=bool)),
                          'XYcorr': np.ma.MaskedArray(np.zeros(nchan), mask=np.ones(nchan, dtype=bool))}
        return

    #Selection of skylines
    skylinesel = sd_qa_utils.get_skysel_from_msw(msw)
    idxskylines = np.arange(nchan)[skylinesel]

    #Make a copy of the data and apply the per-chan filter
    print('Copying and filtering per channel...')
    Fmsw = copy.deepcopy(msw)
    #Apply filters per channel
    Fmsw.filter(type='chanhighpass', filter_order = filter_order, filter_cutoff = filter_cutoff)

    #Get peak of FFT time-spectrum per freq-channel
    peak_fft_pwr = []
    XYcorr = []
    nstep = int(np.floor(nchan/10.0))
    full_freqs = np.fft.rfftfreq(nrows)
    mask_sections = None
    last_chdata_mask = np.zeros(nrows, dtype=bool)
    for ch in range(nchan):
        if maskfreq1D[ch] or (ch in idxskylines):
            peak_fft_pwr.append(0.0)
            XYcorr.append(0.0)
            maskfreq1D[ch] = True
            continue
        if (ch%nstep == 0):
            print('Processing channel '+str(ch)+'/'+str(nchan))
        chdata = Fmsw.data[:,ch,:]
        #Calculate X-Y pols Pearson correlation
        if npol == 2:
            XYcorr.append(mstats.pearsonr(chdata[0], chdata[1])[0])
        else:
            XYcorr.append(0.0)
        #Calculate fft_results
        if npol == 2:
            chdataSum = np.ma.mean(chdata, axis=0)
        else:
            chdataSum = chdata[0]
        #Check is we have a valid masked sections array from lst iteration, if not, set it to None and force recalculate
        if (mask_sections is not None) and (not np.all(chdataSum.mask == last_chdata_mask)):
            mask_sections = None
        absfft_data, mask_sections = sd_qa_utils.abs_rfft_wmask(chdataSum, full_freqfft=full_freqs, mask_sections=mask_sections)
        last_chdata_mask = chdataSum.mask
        #Zero out constant and neighboring modes
        absfft_data[0:loworder_to_zero] = 0.0
        #Get peak
        peak_fft_pwr.append(np.max(absfft_data))
    peak_fft_pwr = np.ma.MaskedArray(peak_fft_pwr, mask=maskfreq1D)
    XYcorr = np.ma.MaskedArray(XYcorr, mask=maskfreq1D)
    if npol == 1:
        XYcorr.mask = np.ones(nchan, dtype=bool)

    #Release memory taken up by the copy of the dataset
    del(Fmsw)

    #Save results in the original MSWrapper object
    msw.data_stats = {'peak_fft_pwr': peak_fft_pwr, 'XYcorr': XYcorr}

    return

def combine_msw_stats(mswCollection: dict) -> dict:
    '''Function that return the combination of "data_stats" attributes in a collection of MSWrapperSD objects.
    Currently combination occurs just as a channel-to-channel stack, i.e. assuming the LSRK frequency of the
    channels of different EBs is the same.
    param:
        mswCollection: Dictionary with a collection of MSWrapperSD generated by the load_and_stats() function.
    returns:
        Dictionary "data_stats_comb", which correspond to the combination of "peak_fft_pwr" and "XYcorr" vectors
        from the collection of MSWrapperSD, named as "comb_peak_data" and "comb_XYcorr", grouped by science field name and SPW:
        data_stats_comb[fieldname][spw]
    '''

    #Get arrays to index msw Collection
    mswCollectionKeys = list(mswCollection.keys())
    mskeys = (np.array(mswCollectionKeys).T)[0]
    mslist = np.unique(mskeys)
    idxfirst = {ms: np.where(mskeys == ms)[0][0] for ms in mslist}
    fieldnames = np.unique(np.array(sd_qa_utils.flattenlist([mswCollection[mswCollectionKeys[idxfirst[ms]]].spw_setup['fieldname']['*OBSERVE_TARGET#ON_SOURCE*'] for ms in mslist])))
    names_for = {ms: mswCollection[mswCollectionKeys[idxfirst[ms]]].spw_setup['namesfor'] for ms in mslist}
    fieldid_for = {ms: {fieldname[0]: fieldid for (fieldid, fieldname) in names_for[ms].items()} for ms in mslist}
    antnames_for = {ms: mswCollection[mswCollectionKeys[idxfirst[ms]]].spw_setup['antnames'] for ms in mslist}
    #assuming all EBs have the same SPW names, no matter what numbering, and we can take the first one. If not one would need to
    #make this more general. SPW list taken is the one form the first SPW
    spwlist = mswCollection[mswCollectionKeys[idxfirst[mslist[0]]]].spw_setup['spwlist']
    spwnamelist = mswCollection[mswCollectionKeys[idxfirst[mslist[0]]]].spw_setup['spwnames']
    #Some MSs could have less fields, lets create a list of the MS that do for each field
    mslist_for_fieldname = {fieldname: [ms for ms in mslist if fieldname in fieldid_for[ms].keys()] for fieldname in fieldnames}

    #Initialize output dictionary with metadata from the combination
    data_stats_comb = {'comb_metadata': {'mslist': mslist, 'mskeys': mskeys, 'idxfirst': idxfirst, 'fieldnames': fieldnames, 'names_for': names_for, 'fieldid_for': fieldid_for, 'antnames_for': antnames_for, 'spwlist': spwlist, 'spwnamelist': spwnamelist}}

    #Iterate over field and SPW and combine
    #Combination done assuming LSRK velocity is being tracked by the online software, so science lines should
    #align in channel number. If not, a regrid to a LSRK frame would be necessary.
    for fieldname in fieldnames:
        data_stats_comb[fieldname] = {}
        for spwname in spwnamelist:
            comb_peak_data = np.ma.sum([np.ma.sum([mswCollection[(ms, spwname, ant, str(fieldid_for[ms][fieldname]))].data_stats['peak_fft_pwr'] for ant in antnames_for[ms]], axis=0) for ms in mslist_for_fieldname[fieldname]], axis=0)
            comb_XYcorr = np.ma.mean([np.ma.mean([mswCollection[(ms, spwname, ant, str(fieldid_for[ms][fieldname]))].data_stats['XYcorr'] for ant in antnames_for[ms]], axis=0) for ms in mslist_for_fieldname[fieldname]], axis=0)
            data_stats_comb[fieldname][spwname] = {'comb_peak_data': comb_peak_data, 'comb_XYcorr': comb_XYcorr}

    return data_stats_comb

def sci_line_det(data_stats_comb:dict, sci_threshold:float = 15.0, XYcorr_threshold:float = 15.0, enlarge_box:float = 0.02):
    '''Function to create selection vector for science emission line channels, based on the "comb_peak_data" and "comb_XYcorr"
    produced by the combine_msw_stats() function.
    param:
        data_stats_comb: (dict) Data stats combination dictionary, as returned by combine_msw_stats()
        sci_threshold: (float) Threshold for the FFT Peak data.
        XYcorr_threshold: (float) Threshold for X-Y correlation data.
        enlarge_box: (float) Size of the box smoothing applied to resulting selection vector, given as fraction
                     of the SPW.
    returns:
        Function modifies the input data_stats_comb variable, adding to this dictionary the selection vectors and summary of the
        thresholding algorithm (obtained from the sd_qa_utils.smoothed_sigma_clip function).
    '''

    for fieldname in data_stats_comb['comb_metadata']['fieldnames']:
        for spwname in data_stats_comb['comb_metadata']['spwnamelist']:

            #Select science line channels
            fft_results = sd_qa_utils.smoothed_sigma_clip(data_stats_comb[fieldname][spwname]['comb_peak_data'], sci_threshold, mode = 'one-sided')
            XYcorr_results = sd_qa_utils.smoothed_sigma_clip(data_stats_comb[fieldname][spwname]['comb_XYcorr'], XYcorr_threshold, mode = 'one-sided', fixedwidth=fft_results['widthmax'])
            sci_line_sel = fft_results['outliers'] & XYcorr_results['outliers']
            #Enlarge selection according to enlarge_box parameter
            nchan = len(data_stats_comb[fieldname][spwname]['comb_peak_data'])
            enlarge_box_pix = int(nchan*enlarge_box)
            sci_line_sel = sd_qa_utils.enlargesel(sci_line_sel, enlarge_box_pix)
            #Continuum selection
            contsel = (~fft_results['outliers']) & (~XYcorr_results['outliers'])
            #Store resulting selection vectors back in the data_stats_comb dictionary
            data_stats_comb[fieldname][spwname]['sci_line_sel'] = sci_line_sel
            data_stats_comb[fieldname][spwname]['cont_sel'] = contsel
            data_stats_comb[fieldname][spwname]['fft_results'] = fft_results
            data_stats_comb[fieldname][spwname]['XYcorr_results'] = XYcorr_results

    return

def attach_sci_line_res(mswCollection: dict, data_stats_comb: dict):
    '''Function used to attach science line selection vector to the individual "data_stats" attribute of each of
    the MSWrapperSD objects inside the mswCollection dictionary.
    param:
        mswCollection: (dict) Dictionary with a collection of MSWrapperSD generated by the load_and_stats() function.
        data_stats_comb: (dict) Dictionary obtained from the sci_line_det() function, which should include
                         the vectors 'sci_line_sel', 'cont_sel', 'fft_results' and 'XYcorr_results'
    returns:
        Function modified in place all the MSWrapperSD objects, associating each msw to the corresponding
        science line selection vectors depending on the Fieldname and SPW.
    '''

    for key, msw in mswCollection.items():
        (ms, spwname, ant, fieldid) = key
        fieldname = data_stats_comb['comb_metadata']['names_for'][ms][str(fieldid)][0]
        if msw.data_stats is None:
            msw.data_stats = {}
        msw.data_stats['sci_line_sel'] = data_stats_comb[fieldname][spwname]['sci_line_sel']
        msw.data_stats['cont_sel'] = data_stats_comb[fieldname][spwname]['cont_sel']
        msw.data_stats['fft_results'] = data_stats_comb[fieldname][spwname]['fft_results']
        msw.data_stats['XYcorr_results'] = data_stats_comb[fieldname][spwname]['XYcorr_results']

    return

def qascorefunc(nsigma: float, score_top: float = 0.67, score_bottom: float = 0.34, nsigma_threshold: float = 3.5,
                nsigma_bottom: float = 10.0):
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

def outlier_detection(msw: mswrapper_sd.MSWrapperSD, thresholds: dict = default_thresholds, plot_output_path: str = '.',
                    plot_sciline: str = 'on-detection', weblog_output_path: str = '.') -> Tuple[mswrapper_sd.MSWrapperSD, pqa.QAScore, list, list]:
    '''Function that calculates the applycal QA score for a given dataset msw.
    param:
        msw: MSWrapper_SD object containing the data statistics used for the QA scores calculation. This method will use the
             data_stats dictionary inside the msw object. If some outlier is detected, data will be reloaded to make a heatmap plot.
             If tsysdata attribute is present in dataset, Trec tables will be used in the detection of deviations.
        thresholds: Dictionary containing threshold parameters for ON-source XX-YY deviations, Trec deviations, minimum deviation level,
                    and QA score scaling.
        plot_output_path: (str) Path to save output plots.
        plot_sciline: (str) String stating whether a diagnostic plot about science line detection should be done. options:
                      "always"/"on-detection"/"never"
        weblog_output_path: (str) Path to save output plots that are intended to be
                            a part of the pipeline weblog.
    returns:
        Tuple of MSWrapperSD object with added analysis attribute, worst QA score, list of all per-scan QA scores, list of summary plot made
    '''

    #Path for output files
    if not os.path.exists(plot_output_path):
        os.mkdir(plot_output_path)

    #output variable for QA scores
    qascores_scans = []

    #Get dataset array size
    (npol, nchan, nrows) = (msw.npol, msw.nchan, msw.nrows)
    msname = msw.fname.split('/')[-1]
    #Channel frequencies in GHz and separation in MHz, and min and max frequency
    freqs = msw.spw_setup[msw.spw]['chanfreqs']*1.e-09
    chansep = msw.spw_setup[msw.spw]['chansep']*(1.e-06)
    minfreq = np.min(freqs)
    maxfreq = np.max(freqs)
    #Scan numbers
    scanlist = msw.spw_setup['scansforfield'][str(msw.fieldid)]
    fieldname = msw.spw_setup['namesfor'][str(msw.fieldid)][0]
    tsys_scanlist = msw.spw_setup['scan']['*CALIBRATE_ATMOSPHERE#OFF_SOURCE*']
    nscans = len(scanlist)
    extscanlist = copy.deepcopy(scanlist)
    if nscans > 1:
        extscanlist.append('all')

    #If this is an empty piece of the dataset, return QA score of 1.0
    if nrows == 0:
        #Create objects to create QAscore
        reason = 'XX-YY.deviation'
        applies_to = pqa.TargetDataSelection(vis={msname}, field={fieldname}, scan={'all'}, intent={'*OBSERVE_TARGET#ON_SOURCE*'}, spw={msw.spw}, ant={msw.antenna}, pol={'N/A'})
        comes_from = pqa.QAOrigin(metric_name=reason, metric_score=0.0, metric_units='n-sigma deviation')
        qascore = pqa.QAScore(1.0, longmsg=f'{msname}: All data flagged for spw {msw.spw}, antenna {msw.antenna} in scan all (field {fieldname}).', shortmsg='XX-YY v/s Frequency deviation', origin=comes_from, applies_to=applies_to, hierarchy=reason)
        return (msw, qascore, [qascore], 'N/A')

    #If this is Pol XX only dataset, return default QA score of 1.0
    if npol == 1:
        reason = 'XX-YY.deviation'
        applies_to = pqa.TargetDataSelection(vis={msname}, field={fieldname}, scan={'all'}, intent={'*OBSERVE_TARGET#ON_SOURCE*'}, spw={msw.spw}, ant={msw.antenna}, pol={0})
        comes_from = pqa.QAOrigin(metric_name=reason, metric_score=0.0, metric_units='n-sigma deviation')
        thisqascore = pqa.QAScore(1.0, longmsg=f'{msname}: Only XX polarization available, no XX-YY QA possible for spw {msw.spw}, antenna {msw.antenna} in scan all.', shortmsg='XX-YY v/s Frequency deviation', origin=comes_from, applies_to=applies_to, hierarchy=reason)
        return (msw, thisqascore, [thisqascore], 'N/A')

    #Create 2D outlier map initialized
    msw.outliers = np.zeros((nchan, nrows), dtype=bool)

    #Selection of skylines
    skylinesel = sd_qa_utils.get_skysel_from_msw(msw)

    #Was there any science line detected?
    if (msw.data_stats is not None) and ('sci_line_sel' in msw.data_stats.keys()):
        is_sci_line_det = (np.sum(msw.data_stats['sci_line_sel']) > 0)
        sci_line_channels = msw.data_stats['sci_line_sel']
    else:
        is_sci_line_det = False
        sci_line_channels = np.zeros(nchan, dtype=bool)

    #Per-scan analysis
    analysis = {}
    #Get Trec data outliers
    atmdata = {}
    #Calculate Trec X and Y differences for scan(n+1) - scan(n)
    for scan in scanlist:
        if (msw.tsysdata is not None):
            tsyshighscan = msw.tsysdata['idx_tsys_scan_high'][scan]
            tsyslowscan = msw.tsysdata['idx_tsys_scan_low'][scan]
        else:
            tsyshighscan = -1
            tsyslowscan = -1
        #Get Trec differences, if both before and after scans exist
        if (tsyshighscan > 0) and (tsyslowscan > 0) and (npol == 2):
            trecdiffX = np.ma.MaskedArray(msw.tsysdata['trec'][0,:,tsyshighscan]-msw.tsysdata['trec'][0,:,tsyslowscan], mask=msw.time_mean_scan[scan].mask[0])
            trecdiffY = np.ma.MaskedArray(msw.tsysdata['trec'][1,:,tsyshighscan]-msw.tsysdata['trec'][1,:,tsyslowscan], mask=msw.time_mean_scan[scan].mask[1])
        #If we don't have tsys scans before and after fill in dictionary with flagged arrays
        else:
            trecdiffX = np.ma.MaskedArray(np.zeros(nchan), mask=np.ones(nchan, dtype=bool))
            trecdiffY = np.ma.MaskedArray(np.zeros(nchan), mask=np.ones(nchan, dtype=bool))
        atmdata[scan] = {'trecdiffX': trecdiffX, 'trecdiffY': trecdiffY}
    #Now calculate added difference to compare with data combination of all scans
    combtrecdiffX = np.ma.sum([atmdata[scan]['trecdiffX'] for scan in atmdata.keys()], axis=0)
    combtrecdiffY = np.ma.sum([atmdata[scan]['trecdiffY'] for scan in atmdata.keys()], axis=0)
    atmdata['all'] = {'trecdiffX': combtrecdiffX, 'trecdiffY': combtrecdiffY}

    #Get data per scan
    idx_lowest = -1
    qascore_lowest = 1.0
    for k, scan in enumerate(extscanlist):
        #Prepare data difference sample
        dataX = msw.time_mean_scan[scan][0]
        dataY = msw.time_mean_scan[scan][1]
        dataX.mask[skylinesel] = True
        dataY.mask[skylinesel] = True
        datadiff = dataX - dataY
        #Check if one or both polarization is fully flagged
        dataX_fully_flagged = (np.sum(dataX.mask) == len(dataX))
        dataY_fully_flagged = (np.sum(dataY.mask) == len(dataY))
        #Case where everything is flagged, return QA score of 1.0, not a major problem at this stage
        if dataX_fully_flagged and dataY_fully_flagged:
            #Create objects to create QAscore
            reason = 'XX-YY.deviation'
            applies_to = pqa.TargetDataSelection(vis={msname}, field={fieldname}, scan={scan}, intent={'*OBSERVE_TARGET#ON_SOURCE*'}, spw={msw.spw}, ant={msw.antenna}, pol={'N/A'})
            comes_from = pqa.QAOrigin(metric_name=reason, metric_score=0.0, metric_units='n-sigma deviation')
            thisqascore = pqa.QAScore(1.0, longmsg=f'{msname}: All data flagged for spw {msw.spw}, antenna {msw.antenna} in scan {scan} (field {fieldname}).', shortmsg='XX-YY v/s Frequency deviation', origin=comes_from, applies_to=applies_to, hierarchy=reason)
            qascores_scans.append(thisqascore)
            analysis[scan] = None
            if qascore_lowest == 1.0:
                idx_lowest = k
            continue
        #Case of on polarization being fully flagged and the other not, return low QA scores, since this should never happen and is problematic
        elif dataX_fully_flagged or dataY_fully_flagged:
            flaggedpol = 'XX 'if dataX_fully_flagged else 'YY'
            #Create objects to create QAscore
            reason = 'XX-YY.deviation'
            applies_to = pqa.TargetDataSelection(vis={msname}, field={fieldname}, scan={scan}, intent={'*OBSERVE_TARGET#ON_SOURCE*'}, spw={msw.spw}, ant={msw.antenna}, pol={flaggedpol})
            comes_from = pqa.QAOrigin(metric_name=reason, metric_score=0.0, metric_units='n-sigma deviation')
            thisqascore = pqa.QAScore(0.34, longmsg=f'{msname}: Data flagged for one polarization only for spw {msw.spw}, antenna {msw.antenna} in scan {scan} (field {fieldname}), pol {flaggedpol}.', shortmsg='XX-YY v/s Frequency deviation', origin=comes_from, applies_to=applies_to, hierarchy=reason)
            qascores_scans.append(thisqascore)
            analysis[scan] = None
            if qascore_lowest < 0.34:
                qascore_lowest = 0.34
                idx_lowest = k
            continue

        #Detect outliers in ON-data
        ondata_results = sd_qa_utils.smoothed_sigma_clip(datadiff, thresholds['X-Y_freq_dev'], mode = 'two-sided')
        normdatadiff = ondata_results['normdata']
        outlier_data = ondata_results['outliers'] & (~sci_line_channels)
        nsigma_ondata = ondata_results['snrmax']

        #Define type of outliers selection arrays
        #Outliers that appear in the Trec difference tables and coincide with on-data outliers
        trecX_results = sd_qa_utils.smoothed_sigma_clip(atmdata[scan]['trecdiffX'], thresholds['Trec_freq_dev'], mode = 'two-sided', fixedwidth=ondata_results['widthmax'])
        trecdiffX = trecX_results['normdata']
        outlier_trecX = trecX_results['outliers']
        nsigma_trecX = trecX_results['snrmax']
        trecY_results = sd_qa_utils.smoothed_sigma_clip(atmdata[scan]['trecdiffY'], thresholds['Trec_freq_dev'], mode = 'two-sided', fixedwidth=ondata_results['widthmax'])
        trecdiffY = trecY_results['normdata']
        outlier_trecY = trecY_results['outliers']
        nsigma_trecY = trecY_results['snrmax']

        #Pick up Trec outliers that match data outliers
        outlier_data_trecX = trecX_results['outliers'] & outlier_data
        outlier_data_trecY = trecY_results['outliers'] & outlier_data

        #Booleans with outlier cases
        has_data_outliers = (nsigma_ondata > thresholds['X-Y_freq_dev'])
        has_trecX_outliers = (np.ma.sum(outlier_data_trecX) > 0)
        has_trecY_outliers = (np.ma.sum(outlier_data_trecY) > 0)
        any_detection = any([has_data_outliers, has_trecX_outliers, has_trecY_outliers])

        #Figure out if data outliers are due to XX or YY polarization, if applicable
        pr_x = mstats.pearsonr(dataX, datadiff)
        pr_y = mstats.pearsonr(-dataY, datadiff)
        #Texts for message
        if any_detection and ((pr_x[0] > pr_y[0]) or (has_trecX_outliers and not has_trecY_outliers)):
            badpol = 'XX'
            badtrec = '. Also detected in the Trec[XX] table.'
        elif any_detection and ((pr_x[0] < pr_y[0]) or (not has_trecX_outliers and has_trecY_outliers)):
            badpol = 'YY'
            badtrec = '. Also detected in the Trec[YY] table.'
        elif any_detection and has_trecX_outliers and has_trecY_outliers:
            badpol = 'not identified'
            badtrec = '. Also detected in the Trec[XX] and Trec[YY] tables.'
        else:
            pr_x, pr_y = [0.0, 0.0], [0.0, 0.0]
            badpol = 'N/A'

        #Calculate max of outlier strength relative to range of data for report, use on-data and calcualte
        #percentage of deviation relative to RMS
        if msw.spw_setup['sensitivityGoalinJy']:
            peak_outlier_percent = np.round(100.0*np.abs(ondata_results['datamax'])/msw.spw_setup['sensitivityGoalinJy'], decimals=1)
        else:
            # unrealistic value to disable second condition in the if statement below
            peak_outlier_percent = 120.0
        #width detection as percentage of BW
        width_bw_percent = 100.0*ondata_results['widthmax']/nchan

        #Create objects to create QAscore
        reason = 'XX-YY.deviation'
        applies_to = pqa.TargetDataSelection(vis={msname}, field={fieldname}, scan={scan}, intent={'*OBSERVE_TARGET#ON_SOURCE*'}, spw={msw.spw}, ant={msw.antenna}, pol={badpol})
        comes_from = pqa.QAOrigin(metric_name=reason, metric_score=nsigma_ondata, metric_units='n-sigma deviation')

        #QA score value evaluation
        if has_data_outliers and (has_trecX_outliers or has_trecY_outliers) and (peak_outlier_percent >= thresholds['min_freq_dev_percent']):
            #Case where actual outliers were found, put a yellow QA score
            qascore_value = qascorefunc(nsigma_ondata, score_top = 0.67, score_bottom = 0.34, nsigma_threshold = thresholds['X-Y_freq_dev'], nsigma_bottom = thresholds['nsigma_bottom'])
            longmsg = 'XX-YY large deviation outlier in data and Trec table for spw {0:d}, antenna {1:s}, polarization {2:s} in scan {3:s} (field {4:s})'.format(msw.spw, msw.antenna, badpol, str(scan), fieldname)
            #longmsg = 'XX-YY deviation outlier ({0:.1f}% of RMS) at {1:.3f}-sigma for spw {2:d}, antenna {3:s}, polarization {4:s} in scan {5:s} (field {6:s}) {7:s}; nsigma Trec: {8:.3f},{9:.3f}; width: {10:.2f}%'.format(peak_outlier_percent, nsigma_ondata, msw.spw, msw.antenna, badpol, str(scan), fieldname, badtrec, nsigma_trecX, nsigma_trecY, width_bw_percent)
            #Mark outliers in outlier array for plotting
            if scan != 'all':
                for row in np.where(msw.scantimesel[scan])[0]:
                    msw.outliers[:,row] = outlier_data
            else:
                for row in range(nrows):
                    msw.outliers[:,row] = outlier_data
        elif has_data_outliers and not(has_trecX_outliers or has_trecY_outliers):
            #Non outliers case only, put a blue QA score
            qascore_value = qascorefunc(nsigma_ondata, score_top = 0.9, score_bottom = 0.68, nsigma_threshold = thresholds['X-Y_freq_dev'], nsigma_bottom = thresholds['nsigma_bottom'])
            longmsg = 'XX-YY deviation for spw {0:d}, antenna {1:s}, polarization {2:s} in scan {3:s} (field {4:s})'.format(msw.spw, msw.antenna, badpol, str(scan), fieldname)
            #longmsg = 'XX-YY polarization difference ({0:.1f}% of RMS) at {1:.3f}-sigma for spw {2:d}, antenna {3:s}, polarization {4:s} in scan {5:s} (field {6:s}), likely due to atmosphere instability, check deviation mask at baseline subtraction; nsigma Trec: {7:.3f},{8:.3f}; width: {9:.2f}%'.format(peak_outlier_percent, nsigma_ondata, msw.spw, msw.antenna, badpol, str(scan), fieldname, nsigma_trecX, nsigma_trecY, width_bw_percent)
            #Mark outliers in outlier array for plotting
            if scan != 'all':
                for row in np.where(msw.scantimesel[scan])[0]:
                    msw.outliers[:,row] = outlier_data
            else:
                for row in range(nrows):
                    msw.outliers[:,row] = outlier_data
        else:
            #Case of no outliers and no information
            qascore_value = 1.0
            longmsg = 'No significant XX-YY polarization difference detected for spw {0:d}, antenna {1:s} in scan {2:s} (field {3:s})'.format(msw.spw, msw.antenna, str(scan), fieldname)

        if qascore_value <= qascore_lowest:
            qascore_lowest = qascore_value
            idx_lowest = k

        thisqascore = pqa.QAScore(qascore_value, longmsg=f"{msname}: {longmsg}", shortmsg='XX-YY v/s Frequency deviation', origin=comes_from, applies_to=applies_to, hierarchy=reason)
        qascores_scans.append(thisqascore)

        analysis[scan] = {'ondata': ondata_results, 'trecX': trecX_results, 'trecY': trecY_results,
                          'qascore': thisqascore}

    #Mark marginalized outlier selections
    msw.outlierfreq = (np.max(msw.outliers, axis = 1) > 0)
    msw.outliertime = (np.max(msw.outliers, axis = 0) > 0)

    #Create summary qascore for this antenna's data
    qascoresvalues = np.array([q.score for q in qascores_scans])
    outlierscans = np.array(extscanlist)[(qascoresvalues < 0.67)]
    outlierscans_str = ','.join(map(str,outlierscans))
    if idx_lowest >= 0 and idx_lowest < nscans:
        qascore = copy.deepcopy(qascores_scans[idx_lowest])
        if len(outlierscans) > 1:
            qascore.longmsg = qascore.longmsg.replace('scan '+str(scanlist[idx_lowest]), 'scans '+outlierscans_str)
            qascore.applies_to.scan = set(outlierscans)
    else:
        qascore = copy.deepcopy(qascores_scans[-1])

    detmsg = 'N/A'
    if not all([(analysis[scan] is not None) for scan in scanlist]):
        snrlist = np.ma.array([analysis[scan]['ondata']['snrmax'] if ((analysis[scan] is not None) and (np.ma.sum(analysis[scan]['ondata']['outliers']) > 0)) else np.nan for scan in scanlist])
        snrlist.mask = ~np.isfinite(snrlist)
        idxmaxsnr = np.ma.argmax(snrlist)
        scanmax = scanlist[idxmaxsnr]
        if not np.ma.is_masked(snrlist[idxmaxsnr]):
            detmsg = 'ON-data: SNR={0:.3f},f={1:.3f}GHz,W={2:.3f}MHz({3:.3f}%)'.format(snrlist[idxmaxsnr], freqs[analysis[scanmax]['ondata']['chanmax']], analysis[scanmax]['ondata']['widthmax']*chansep, 100.0*analysis[scanmax]['ondata']['widthmax']/nchan)

    #Save analysis data
    msw.analysis = analysis

    #Plot science line detections
    if (plot_sciline == 'always') or ((plot_sciline == 'on-detection') and is_sci_line_det):
        sciplotfname = sd_qa_reports.plot_science_det(msw = msw, thresholds = thresholds, plot_output_path = plot_output_path)

    #Plot heatmap if QA score < plot_threshold
    colorlist = sd_qa_utils.genColorList(len(extscanlist))
    if (idx_lowest >= 0) and (qascore.score <= thresholds['plot_threshold']):
        print('Creating plot outputs in '+str(plot_output_path))
        #Make heat map
        if msw.data is None:
            if msw.tsysdata is not None:
                thistsysdata = True
            else:
                thistsysdata = False
            #We might need to reload the data, since we dropped the data array to save memory
            tmpmsw = mswrapper_sd.MSWrapperSD.create_from_ms(fname=msw.fname, spw=msw.spw, antenna=msw.antenna, fieldid=msw.fieldid, column='CORRECTED_DATA', onoffsel='ON', spw_setup=msw.spw_setup, attach_tsys_data=thistsysdata)
            tmpmsw.filter(type = 'rowmedian')
            msw.data = tmpmsw.data
        _ = sd_qa_reports.show_heat_XYdiff(msw=msw, plot_output_path=plot_output_path, colorlist=colorlist)
        #Make diagnostic plots
        _ = sd_qa_reports.plot_data_trec(msw=msw, thresholds = thresholds, colorlist=colorlist, plot_output_path=plot_output_path, detmsg = detmsg)

    plotfname = sd_qa_reports.plot_data(msw=msw, thresholds = thresholds, colorlist=colorlist, plot_output_path=weblog_output_path, detmsg = detmsg)


    return (msw, qascore, qascores_scans, plotfname)

def load_and_stats(msNames: List[str], use_tsys_data: bool = True, sciline_det: bool = True,
                   buffer_data: bool = False) -> dict:
    '''Load a collection of MSWrapper_SD objects, and run a basic filter and statistics on each of them.
    Return a dictionary of MSWrapper_SD objects, indexed by tuples in the form (ms, spw, ant, fieldid).
    param:
        msNames: List of MS names to load.
        ondata_filters: List of filters to pass on the ON-source data
        use_tsys_data: True/False whether to load CalAtmosphere data from dataset
        sciline_det: True/False whether to attempt strong science line detection. The detected channels are passed to outlier_detection()
                     to exclude them for triggering a false XX-YY deviation.
        buffer_data: True/False whether to save/load the MSW collection to disk. This is aimed at easing the
                    use for repeated execution of the code, mostly testing.
    '''

    #Load buffered data from disk, if exists
    buf = os.path.join(os.path.dirname(msNames[0]), 'mswCollection.buffer.pkl')
    if os.path.exists(buf):
        f = open(buf, 'rb')
        mswCollection = pickle.load(f)
        f.close()
        return mswCollection

    #Load data and gather statistics
    mswCollection = {}
    for ms in msNames:
        msonly = ms.split('/')[-1]
        #Load metadata
        spw_setup = sd_qa_utils.getSpecSetup(myms=ms)
        #Iterate over SPW, antenna, FieldID
        datapieces = product(spw_setup['spwlist'], spw_setup['antnames'], spw_setup['fieldid']['*OBSERVE_TARGET#ON_SOURCE*'])
        for datapiece in datapieces:
            (spw, ant, fieldid) = datapiece
            spwname = spw_setup['spwnames'][spw_setup['spwlist'].index(spw)]
            print('Processing MS {0:s}, SPW {1:d}, antenna {2:s}, FieldID {3:d}'.format(ms,spw,ant,fieldid))
            #Load ON-SOURCE data and create MSWrapperSD object
            mswCollection[(msonly, spwname, ant, str(fieldid))] = mswrapper_sd.MSWrapperSD.create_from_ms(fname=ms, spw=spw, antenna=ant, fieldid=fieldid, column='CORRECTED_DATA', onoffsel='ON', spw_setup=spw_setup, attach_tsys_data=use_tsys_data)
            #Apply preliminary filters to ON-data
            print('Applying filter rowmedian...')
            mswCollection[(msonly, spwname, ant, str(fieldid))].filter(type = 'rowmedian')
            #Gather statistics per channel, if requested
            if sciline_det:
                data_stats_perchan(mswCollection[(msonly, spwname, ant, str(fieldid))])
            #Clear raw data from MSWrapper object to release memory
            mswCollection[(msonly, spwname, ant, str(fieldid))].data = None

    if buffer_data:
        print('Buffering mswCollection...')
        f = open(buf, 'wb')
        pickle.dump(mswCollection, f, protocol=2)
        f.close()

    return mswCollection

def get_ms_applycal_qascores(msNames: List[str], thresholds: dict = default_thresholds, plot_output_path: str = '.',
                             use_tsys_data: bool = True, sciline_det: bool = True,
                             plot_sciline: str = 'on-detection', weblog_output_path: str = '.',
                             buffer_data: bool = False) -> Tuple[list, list, list]:
    '''Function used to obtain applycal X-Y QA score on a list of calibrated MSs, at the
    applycal stage of SD pipeline.
    param:
        msNames: List of MS to process
        thresholds: Dictionary containing threshold parameters for ON-source XX-YY deviations,
                    Trec deviations, minimum deviation level, and QA score scaling.
        plot_output_path: (str) Path to save output plots.
        use_tsys_data: True/False whether to load CalAtmosphere data from dataset
        sciline_det: True/False whether to attempt strong science line detection. The detected channels are passed to outlier_detection()
                     to exclude them for triggering a false XX-YY deviation.
        plot_sciline: (str) String stating whether a diagnostic plot about science line detection should be done. options:
                      "always"/"on-detection"/"never"
        weblog_output_path: (str) Path to save output plots if the plots are intended to
                            be a part of the pipeline weblog.
        buffer_data: True/False whether to buffer the data loaded from the MS into a pickle file.
    '''

    #Load data and gather statistics
    mswCollection = load_and_stats(msNames, use_tsys_data=use_tsys_data, sciline_det=sciline_det,
                                   buffer_data=buffer_data)

    #Combine stats for science line detection, if requested
    if sciline_det:
        data_stats_comb = combine_msw_stats(mswCollection)
        #Run simple science line detection
        sci_line_det(data_stats_comb, sci_threshold = default_thresholds['sci_threshold'], XYcorr_threshold = default_thresholds['XYcorr_threshold'])
        #put results inside MSWrapper_SD objects data
        attach_sci_line_res(mswCollection, data_stats_comb)

    #initialize output lists
    qascore_list = []
    plots_fnames = []
    qascore_per_scan_list = []

    #Iterate over collection of MSWrapperSD objects
    for key, msw in mswCollection.items():
        (ms, spw, ant, fieldid) = key
        #Calculate QAscores
        (msw_on, qascore, qascores_scans, plotfname) = outlier_detection(msw = msw, thresholds = thresholds, plot_output_path = plot_output_path, plot_sciline = plot_sciline, weblog_output_path = weblog_output_path)
        #Collect QA scores
        qascore_list.append(qascore)
        plots_fnames.append(plotfname)
        qascore_per_scan_list.extend(qascores_scans)

    if sciline_det:
        #Print channel selection to a text output file
        scilinestr = sd_qa_utils.sci_line_sel_2str(data_stats_comb)
        f = open(plot_output_path + '/scilines_det.txt', 'w')
        f.write(scilinestr)
        f.close()

    return (qascore_list, plots_fnames, qascore_per_scan_list)

