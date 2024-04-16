"""This module is an adaptation from the original auto_selfcal prototype.

see: https://github.com/jjtobin/auto_selfcal
"""

import logging
import os
import time
import numpy as np
import shutil

import casatools
from casatasks import casalog

import pipeline.infrastructure as infrastructure
import pipeline.hif.heuristics.findrefant as findrefant
from pipeline.infrastructure.casa_tasks import casa_tasks as cts
from pipeline.infrastructure.casa_tools import image as ia
from pipeline.infrastructure.casa_tools import imager as im
from pipeline.infrastructure.casa_tools import table as tb
from pipeline.infrastructure.casa_tools import msmd
from pipeline.infrastructure import casa_tools


LOG = infrastructure.get_logger(__name__)


def get_selfcal_logger(loggername='auto_selfcal', loglevel='DEBUG', logfile=None):
    """Get a named logger for auto_selfcal.
    
    When auto_selfcal runs outside of Pipeline, this function is a custom Python logger object
    as constructed below.
    When auto_selfcal runs as a Pipeline "extern" module, this function directly wraps around 
    pipeline.infrastructure.get_logger
    """

    casalog.showconsole(onconsole=True)
    if logfile is None:
        logfile = casalog.logfile()

    format = '%(asctime)s %(levelname)s    %(module)s.%(funcName)s     %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S'
    fmt = logging.Formatter(format, datefmt)
    fmt.converter = time.gmtime

    logger = logging.getLogger(loggername)
    logger.handlers = []
    logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(loglevel)
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    logfile_handler = logging.FileHandler(logfile, mode='a')
    logfile_handler.setLevel(loglevel)
    logfile_handler.setFormatter(fmt)
    logger.addHandler(logfile_handler)

    return logger


def fetch_scan_times(vislist, targets):
    scantimesdict = {}
    integrationsdict = {}
    integrationtimesdict = {}
    integrationtimes = np.array([])
    n_spws = np.array([])
    min_spws = np.array([])
    spwslist_dict = {}
    spws_set_dict = {}
    scansdict = {}
    for vis in vislist:
        scantimesdict[vis] = {}
        integrationsdict[vis] = {}
        integrationtimesdict[vis] = {}
        scansdict[vis] = {}
        spws_set_dict[vis] = {}
        spwslist_dict[vis] = np.array([])
        msmd.open(vis)
        for target in targets:
            scansdict[vis][target] = msmd.scansforfield(target)

        for target in targets:
            scantimes = np.array([])
            integrations = np.array([])
            for scan in scansdict[vis][target]:
                spws_set_dict[vis][scan] = np.array([])
                spws = msmd.spwsforscan(scan)
                spws_set_dict[vis][scan] = spws.copy()
                n_spws = np.append(len(spws), n_spws)
                min_spws = np.append(np.min(spws), min_spws)
                spwslist_dict[vis] = np.append(spws, spwslist_dict[vis])
                integrationtime = msmd.exposuretime(scan=scan, spwid=spws[0])['value']
                integrationtimes = np.append(integrationtimes, np.array([integrationtime]))
                times = msmd.timesforscan(scan)
                scantime = np.max(times)+integrationtime-np.min(times)
                ints_per_scan = np.round(scantime/integrationtimes[0])
                scantimes = np.append(scantimes, np.array([scantime]))
                integrations = np.append(integrations, np.array([ints_per_scan]))

            scantimesdict[vis][target] = scantimes.copy()
            #assume each band only has a single integration time
            integrationtimesdict[vis][target] = np.median(integrationtimes)
            integrationsdict[vis][target] = integrations.copy()
        msmd.close()
    if np.mean(n_spws) != np.max(n_spws):
        LOG.warning('Inconsistent number of spws in scans/MSes (possibly expected if multi-band VLA data or ALMA spectral scan)')
    if np.max(min_spws) != np.min(min_spws):
        LOG.warning('Inconsistent minimum spwid in scans/MSes (possibly expected if multi-band VLA data or ALMA spectral scan)')
    for vis in vislist:
        spwslist_dict[vis] = np.unique(spwslist_dict[vis]).astype(int)
    # jump through some hoops to get the dictionary that has spws per scan into a dictionary of unique
    # spw sets per vis file
    for vis in vislist:
        spws_set_list = [i for i in spws_set_dict[vis].values()]
        spws_set_list = [i.tolist() for i in spws_set_list]
        unique_spws_set_list = [list(i) for i in set(tuple(i) for i in spws_set_list)]
        spws_set_list = [np.array(i) for i in unique_spws_set_list]
        spws_set_dict[vis] = np.array(spws_set_list, dtype=object)

    return scantimesdict, integrationsdict, integrationtimesdict, integrationtimes, np.max(n_spws), np.min(min_spws), spwslist_dict, spws_set_dict


def fetch_scan_times_band_aware(vislist, targets, band_properties, band):
    scantimesdict = {}
    scanstartsdict = {}
    scanendsdict = {}
    integrationsdict = {}
    integrationtimesdict = {}
    integrationtimes = np.array([])
    n_spws = np.array([])
    min_spws = np.array([])
    spwslist = np.array([])
    spws_set_dict = {}
    mosaic_field = {}
    scansdict = {}
    for vis in vislist:
        scantimesdict[vis] = {}
        scanstartsdict[vis] = {}
        scanendsdict[vis] = {}
        integrationsdict[vis] = {}
        integrationtimesdict[vis] = {}
        spws_set_dict[vis] = {}
        scansdict[vis] = {}
        msmd.open(vis)
        for target in targets:
            scansforfield = msmd.scansforfield(target)
            # scansforspw = msmd.scansforspw(band_properties[vis][band]['spwarray'][0])
            # scansdict[vis][target] = list(set(scansforfield) & set(scansforspw))
            # scansdict[vis][target].sort()
            # only valid because we are assuming vislist is a single band/field
            scansdict[vis][target] = list(set(scansforfield))
            scansdict[vis][target].sort()
        for target in targets:
            mosaic_field[target] = {}
            mosaic_field[target]['field_ids'] = []
            mosaic_field[target]['mosaic'] = False
            #mosaic_field[target]['field_ids']=msmd.fieldsforname(target)
            mosaic_field[target]['field_ids'] = msmd.fieldsforscans(scansdict[vis][target])
            mosaic_field[target]['field_ids'] = list(set(mosaic_field[target]['field_ids']))
            if len(mosaic_field[target]['field_ids']) > 1:
                mosaic_field[target]['mosaic'] = True
            scantimes = np.array([])
            integrations = np.array([])
            scanstarts = np.array([])
            scanends = np.array([])

            for scan in scansdict[vis][target]:
                spws = msmd.spwsforscan(scan)
                spws_set_dict[vis][scan] = spws.copy()
                n_spws = np.append(len(spws), n_spws)
                min_spws = np.append(np.min(spws), min_spws)
                spwslist = np.append(spws, spwslist)
                integrationtime = msmd.exposuretime(scan=scan, spwid=spws[0])['value']
                integrationtimes = np.append(integrationtimes, np.array([integrationtime]))
                times = msmd.timesforscan(scan)
                scantime = np.max(times)+integrationtime-np.min(times)
                scanstarts = np.append(scanstarts, np.array([np.min(times)/86400.0]))
                scanends = np.append(scanends, np.array([(np.max(times)+integrationtime)/86400.0]))
                ints_per_scan = np.round(scantime/integrationtimes[0])
                scantimes = np.append(scantimes, np.array([scantime]))
                integrations = np.append(integrations, np.array([ints_per_scan]))

            scantimesdict[vis][target] = scantimes.copy()
            scanstartsdict[vis][target] = scanstarts.copy()
            scanendsdict[vis][target] = scanends.copy()
            #assume each band only has a single integration time
            integrationtimesdict[vis][target] = np.median(integrationtimes)
            integrationsdict[vis][target] = integrations.copy()
        msmd.close()
    # jump through some hoops to get the dictionary that has spws per scan into a dictionary of unique
    # spw sets per vis file
    for vis in vislist:
        spws_set_list = [i for i in spws_set_dict[vis].values()]
        spws_set_list = [i.tolist() for i in spws_set_list]
        unique_spws_set_list = [list(i) for i in set(tuple(i) for i in spws_set_list)]
        spws_set_list = [np.array(i) for i in unique_spws_set_list]
        spws_set_dict[vis] = np.array(spws_set_list, dtype=object)

    if len(n_spws) > 0:
        if np.mean(n_spws) != np.max(n_spws):
            LOG.warning('Inconsistent number of spws in scans/MSes (possibly expected if multi-band VLA data or ALMA spectral scan)')
        if np.max(min_spws) != np.min(min_spws):
            LOG.warning('Inconsistent minimum spwid in scans/MSes (possibly expected if multi-band VLA data or ALMA spectral scan)')
        spwslist = np.unique(spwslist).astype(int)
    else:
        return scantimesdict, scanstartsdict, scanendsdict, integrationsdict, integrationtimesdict, integrationtimes, -99, -99, spwslist, spws_set_dict, mosaic_field
    return scantimesdict, scanstartsdict, scanendsdict, integrationsdict, integrationtimesdict, integrationtimes, np.max(n_spws), np.min(
        min_spws), spwslist, spws_set_dict, mosaic_field


# actual routine used for getting solints
def get_solints_simple(
        vislist, scantimesdict, scanstartsdict, scanendsdict, integrationtimes, inf_EB_gaincal_combine, spwcombine=True,
        solint_decrement='fixed', solint_divider=2.0, n_solints=4.0, do_amp_selfcal=False):
    all_integrations = np.array([])
    all_nscans_per_obs = np.array([])
    all_time_between_scans = np.array([])
    all_times_per_obs = np.array([])
    allscantimes = np.array([])  # we put all scan times from all MSes into single array
    # mix of short and long baseline data could have differing integration times and hence solints
    # could do solints per vis file, but too complex for now at least use perhaps keep scan groups different
    # per MOUS
    nscans_per_obs = {}
    time_per_vis = {}
    time_between_scans = {}
    for vis in vislist:
        nscans_per_obs[vis] = {}
        time_between_scans[vis] = {}
        time_per_vis[vis] = 0.0
        targets = integrationtimes[vis].keys()
        earliest_start = 1.0e10
        latest_end = 0.0
        for target in targets:
            nscans_per_obs[vis][target] = len(scantimesdict[vis][target])
            allscantimes = np.append(allscantimes, scantimesdict[vis][target])
            # way to get length of an EB with multiple targets without writing new functions; I could be more clever with np.where()
            for i in range(len(scanstartsdict[vis][target])):
                if scanstartsdict[vis][target][i] < earliest_start:
                    earliest_start = scanstartsdict[vis][target][i]
                if scanendsdict[vis][target][i] > latest_end:
                    latest_end = scanstartsdict[vis][target][i]
            if np.isfinite(integrationtimes[vis][target]):
                all_integrations = np.append(all_integrations, integrationtimes[vis][target])
            all_nscans_per_obs = np.append(all_nscans_per_obs, nscans_per_obs[vis][target])
            # determine time between scans
            # scan list isn't sorted, so sort these so they're in order and we can subtract them from each other
            sortedstarts = np.sort(scanstartsdict[vis][target])
            sortedends = np.sort(scanstartsdict[vis][target])
            # delta_scan=(sortedends[:-1]-sortedstarts[1:])*86400.0*-1.0
            delta_scan = np.zeros(len(sortedends)-1)
            for i in range(len(sortedstarts)-1):
                delta_scan[i] = (sortedends[i]-sortedstarts[i+1])*86400.0*-1.0
            all_time_between_scans = np.append(all_time_between_scans, delta_scan)
        time_per_vis[vis] = (latest_end - earliest_start)*86400.0    # calculate length of EB
        all_times_per_obs = np.append(all_times_per_obs, np.array([time_per_vis[vis]]))
    integration_time = np.max(all_integrations)  # use the longest integration time from all MS files

    max_scantime = np.median(allscantimes)
    median_scantime = np.max(allscantimes)
    median_scans_per_obs = np.median(all_nscans_per_obs)
    median_time_per_obs = np.median(all_times_per_obs)
    median_time_between_scans = np.median(all_time_between_scans)
    LOG.info(f'median scan length: {median_scantime}')
    LOG.info(f'median time between target scans: {median_time_between_scans}')
    LOG.info(f'median scans per observation: {median_scans_per_obs}')
    LOG.info(f'median length of observation: {median_time_per_obs}')

    solints_gt_scan = np.array([])
    gaincal_combine = []

    # commented completely, no solints between inf_EB and inf
    # make solints between inf_EB and inf if more than one scan per source and scans are short
    # if median_scans_per_obs > 1 and median_scantime < 150.0:
    #   # add one solint that is meant to combine 2 short scans, otherwise go to inf_EB
    #   solint=(median_scantime*2.0+median_time_between_scans)*1.1
    #   if solint < 300.0:  # only allow solutions that are less than 5 minutes in duration
    #      solints_gt_scan=np.append(solints_gt_scan,[solint])

    # code below would make solints between inf_EB and inf by combining scans
    # sometimes worked ok, but many times selfcal would quit before solint=inf
    '''
    solint=median_time_per_obs/4.05 # divides slightly unevenly if lengths of observation are exactly equal, but better than leaving a small out of data remaining
    while solint > (median_scantime*2.0+median_time_between_scans)*1.05:      #solint should be greater than the length of time between two scans + time between to be better than inf
        solints_gt_scan=np.append(solints_gt_scan,[solint])                       # add solint to list of solints now that it is an integer number of integrations
        solint = solint/2.0  
        # LOG.info('Next solint: {solint}')                                        #divide solint by 2.0 for next solint
    '''
    LOG.info(f'{max_scantime} {integration_time}')
    if solint_decrement == 'fixed':
        solint_divider = np.round(np.exp(1.0/n_solints*np.log(max_scantime/integration_time)))
    # division never less than 2.0
    if solint_divider < 2.0:
        solint_divider = 2.0
    solints_lt_scan = np.array([])
    n_scans = len(allscantimes)
    solint = max_scantime/solint_divider
    # 1.1*integration_time will ensure that a single int will not be returned such that solint='int' can be appended to the final list.
    while solint > 1.90*integration_time:
        ints_per_solint = solint/integration_time
        if not ints_per_solint.is_integer():
            # calculate delta_T greater than an a fixed multile of integrations
            remainder = ints_per_solint-float(int(ints_per_solint))
            solint = solint-remainder*integration_time  # add remainder to make solint a fixed number of integrations

        ints_per_solint = float(int(ints_per_solint))
        LOG.info(f'Checking solint = {ints_per_solint*integration_time}')
        delta = test_truncated_scans(ints_per_solint, allscantimes, integration_time)
        solint = (ints_per_solint+delta)*integration_time
        if solint > 1.90*integration_time:
            # add solint to list of solints now that it is an integer number of integrations
            solints_lt_scan = np.append(solints_lt_scan, [solint])

        solint = solint/solint_divider
        # LOG.info(f'Next solint: {solint}')                                        #divide solint by 2.0 for next solint

    solints_list = []
    if len(solints_gt_scan) > 0:
        for solint in solints_gt_scan:
            solint_string = '{:0.2f}s'.format(solint)
            solints_list.append(solint_string)
            if spwcombine:
                gaincal_combine.append('spw,scan')
            else:
                gaincal_combine.append('scan')

    # insert inf_EB
    solints_list.insert(0, 'inf_EB')
    gaincal_combine.insert(0, inf_EB_gaincal_combine)

    # insert solint = inf
    if median_scans_per_obs > 1:                    # if only a single scan per target, redundant with inf_EB and do not include
        solints_list.append('inf')
        if spwcombine:
            gaincal_combine.append('spw')
        else:
            gaincal_combine.append('')

    for solint in solints_lt_scan:
        solint_string = '{:0.2f}s'.format(solint)
        solints_list.append(solint_string)
        if spwcombine:
            gaincal_combine.append('spw')
        else:
            gaincal_combine.append('')

    # append solint = int to end
    solints_list.append('int')
    if spwcombine:
        gaincal_combine.append('spw')
    else:
        gaincal_combine.append('')
    solmode_list = ['p']*len(solints_list)
    if do_amp_selfcal:
        if median_time_between_scans > 150.0 or np.isnan(median_time_between_scans):
            amp_solints_list = ['inf_ap']
            if spwcombine:
                amp_gaincal_combine = ['spw']
            else:
                amp_gaincal_combine = ['']
        else:
            amp_solints_list = ['300s_ap', 'inf_ap']
            if spwcombine:
                amp_gaincal_combine = ['scan,spw', 'spw']
            else:
                amp_gaincal_combine = ['scan', '']
        solints_list = solints_list+amp_solints_list
        gaincal_combine = gaincal_combine+amp_gaincal_combine
        solmode_list = solmode_list+['ap']*len(amp_solints_list)

    return solints_list, integration_time, gaincal_combine, solmode_list


def test_truncated_scans(ints_per_solint, allscantimes, integration_time):
    delta_ints_per_solint = [0, -1, 1, -2, 2]
    n_truncated_scans = np.zeros(len(delta_ints_per_solint))
    n_remaining_ints = np.zeros(len(delta_ints_per_solint))
    min_index = 0

    for idx, delta_ints in enumerate(delta_ints_per_solint):
        diff_ints_per_scan = (
            (allscantimes-((ints_per_solint+delta_ints)*integration_time))/integration_time)+0.5
        diff_ints_per_scan = diff_ints_per_scan.astype(int)
        trimmed_scans = ((diff_ints_per_scan > 0.0) & (diff_ints_per_scan <
                         ints_per_solint+delta_ints)).nonzero()
        if len(trimmed_scans[0]) > 0:
            n_remaining_ints[idx] = np.max(diff_ints_per_scan[trimmed_scans[0]])
        else:
            n_remaining_ints[idx] = 0.0
        n_truncated_scans[idx] = len(trimmed_scans[0])
        if ((idx > 0) and (n_truncated_scans[idx] <= n_truncated_scans[min_index]) and (n_remaining_ints[idx] < n_remaining_ints[min_index])):
            min_index = idx

    return delta_ints_per_solint[min_index]


def fetch_targets(vis):
    fields = []
    msmd.open(vis)
    fieldnames = msmd.fieldnames()
    for fieldname in fieldnames:
        scans = msmd.scansforfield(fieldname)
        if len(scans) > 0:
            fields.append(fieldname)
    msmd.close()
    fields = list(set(fields))  # convert to set to only get unique items
    return fields


def checkmask(imagename):
    maskImage = imagename.replace('image', 'mask').replace('.tt0', '')
    with casa_tools.ImageReader(maskImage) as image:
        image_stats = image.statistics()
    if image_stats['max'][0] == 0:
        return False
    else:
        return True


def estimate_SNR(imagename, maskname=None, verbose=True):
    MADtoRMS = 1.4826

    with casa_tools.ImageReader(imagename) as image:
        bm = image.restoringbeam(polarization=0)
        image_stats = image.statistics(robust=False)
    beammajor = bm['major']['value']
    beamminor = bm['minor']['value']
    beampa = bm['positionangle']['value']

    if maskname is None:
        maskImage = imagename.replace('image', 'mask').replace('.tt0', '')
    else:
        maskImage = maskname
    residualImage = imagename.replace('image', 'residual')
    os.system('rm -rf temp.mask temp.residual')
    if os.path.exists(maskImage):
        os.system('cp -r '+maskImage + ' temp.mask')
        maskImage = 'temp.mask'
    os.system('cp -r '+residualImage + ' temp.residual')
    residualImage = 'temp.residual'
    if 'dirty' not in imagename:
        goodMask = checkmask(imagename)
    else:
        goodMask = False
    if os.path.exists(maskImage) and goodMask:
        with casa_tools.ImageReader(residualImage) as image:
            image.calcmask("'"+maskImage+"'"+" <0.5"+"&& mask("+residualImage+")", name='madpbmask0')
            mask0Stats = image.statistics(robust=True, axes=[0, 1])
            image.maskhandler(op='set', name='madpbmask0')
        rms = mask0Stats['medabsdevmed'][0] * MADtoRMS
    else:
        with casa_tools.ImageReader(imagename.replace('image', 'residual')) as image:
            rms = image.statistics(algorithm='chauvenet')['rms'][0]

    peak_intensity = image_stats['max'][0]
    SNR = peak_intensity/rms
    if verbose:
        LOG.info("#%s" % imagename)
        LOG.info("#Beam %.3f arcsec x %.3f arcsec (%.2f deg)" % (beammajor, beamminor, beampa))
        LOG.info("#Peak intensity of source: %.2f mJy/beam" % (peak_intensity*1000,))
        LOG.info("#rms: %.2e mJy/beam" % (rms*1000,))
        LOG.info("#Peak SNR: %.2f" % (SNR,))
    shutil.rmtree('temp.mask', ignore_errors=True)
    shutil.rmtree('temp.residual', ignore_errors=True)
    return SNR, rms


def estimate_near_field_SNR(imagename, las=None, maskname=None, verbose=True):
    MADtoRMS = 1.4826

    temp_list = ['temp.mask', 'temp.residual', 'temp.border.mask', 'temp.smooth.ceiling.mask',
                 'temp.smooth.mask', 'temp.nearfield.mask', 'temp.big.smooth.ceiling.mask',
                 'temp.nearfield.prepb.mask', 'temp.big.smooth.mask', 'temp.beam.extent.image']

    with casa_tools.ImageReader(imagename) as image:
        bm = image.restoringbeam(polarization=0)
        image_stats = image.statistics(robust=False)
    beammajor = bm['major']['value']
    beamminor = bm['minor']['value']
    beampa = bm['positionangle']['value']

    if maskname is None:
        maskImage = imagename.replace('image', 'mask').replace('.tt0', '')
    else:
        maskImage = maskname
    if not os.path.exists(maskImage):
        LOG.info('Does not exist')
        return np.float64(-99.0), np.float64(-99.0)
    goodMask = checkmask(maskImage)
    if not goodMask:
        LOG.info('The mask file %s is empty.', maskImage)
        return np.float64(-99.0), np.float64(-99.0)
    residualImage = imagename.replace('image', 'residual')

    for temp in temp_list:
        shutil.rmtree(temp, ignore_errors=True)

    os.system('cp -r '+maskImage + ' temp.mask')
    os.system('cp -r '+residualImage + ' temp.residual')
    residualImage = 'temp.residual'

    cts.imsmooth(imagename='temp.mask', kernel='gauss', major=str(beammajor*1.0)+'arcsec',
                 minor=str(beammajor*1.0)+'arcsec', pa='0deg', outfile='temp.smooth.mask')
    cts.immath(imagename=['temp.smooth.mask'], expr='iif(IM0 > 0.1*max(IM0),1.0,0.0)', outfile='temp.smooth.ceiling.mask')

    # Check the extent of the beam as well.
    psfImage = maskImage.replace('mask', 'psf')+'.tt0'
    pbImage = imagename.replace('image', 'pb')

    cts.immath(imagename=[psfImage, pbImage], mode="evalexpr", expr="iif(IM0 > 0.1,1/IM1,0.0)",
               outfile="temp.beam.extent.image")

    centerpos = cts.imhead(psfImage, mode="get", hdkey="maxpixpos")
    maxpos = cts.imhead("temp.beam.extent.image", mode="get", hdkey="maxpixpos")
    center_coords = cts.imval(psfImage, box=str(centerpos[0])+","+str(centerpos[1]))["coords"]
    max_coords = cts.imval(psfImage, box=str(maxpos[0])+","+str(maxpos[1]))["coords"]

    beam_extent_size = ((center_coords - max_coords)**2)[0:2].sum()**0.5 * 360*60*60/(2*np.pi)

    # use the maximum of the three possibilities as the outer extent of the mask.
    LOG.info("beammajor*5 = %f, LAS = %f, beam_extent = %f", beammajor*5, 5*las, beam_extent_size)
    outer_major = max(beammajor*5, beam_extent_size, 5*las if las is not None else 0.)

    cts.imsmooth(imagename='temp.smooth.ceiling.mask', kernel='gauss', major=str(outer_major)+'arcsec',
                 minor=str(outer_major)+'arcsec', pa='0deg', outfile='temp.big.smooth.mask')

    cts.immath(imagename=['temp.big.smooth.mask'], expr='iif(IM0 > 0.01*max(IM0),1.0,0.0)',
               outfile='temp.big.smooth.ceiling.mask')
    cts.immath(imagename=['temp.big.smooth.ceiling.mask', 'temp.smooth.ceiling.mask'],
               expr='((IM0-IM1)-1.0)*-1.0', outfile='temp.nearfield.prepb.mask')
    cts.immath(imagename=['temp.nearfield.prepb.mask', imagename.replace("image", "pb")],
               expr='iif(VALUE(IM1) > 0.1,IM0,1.0)', outfile='temp.nearfield.mask')
    maskImage = 'temp.nearfield.mask'
    mask_stats = cts.imstat(maskImage)
    if mask_stats['min'][0] == 1:
        LOG.info('checkmask')
        SNR, rms = np.float64(-99.0), np.float64(-99.0)
    else:
        with casa_tools.ImageReader(residualImage) as image:
            image.calcmask("'"+maskImage+"'"+" <0.5"+"&& mask("+residualImage+")", name='madpbmask0')
            mask0Stats = image.statistics(robust=True, axes=[0, 1])
            image.maskhandler(op='set', name='madpbmask0')
        rms = mask0Stats['medabsdevmed'][0] * MADtoRMS
        peak_intensity = image_stats['max'][0]
        SNR = peak_intensity/rms
        if verbose:
            LOG.info("#%s" % imagename)
            LOG.info("#Beam %.3f arcsec x %.3f arcsec (%.2f deg)" % (beammajor, beamminor, beampa))
            LOG.info("#Peak intensity of source: %.2f mJy/beam" % (peak_intensity*1000,))
            LOG.info("#Near Field rms: %.2e mJy/beam" % (rms*1000,))
            LOG.info("#Peak Near Field SNR: %.2f" % (SNR,))
    os.system('cp -r '+maskImage+' '+imagename.replace('image', 'nearfield.mask').replace('.tt0', ''))
    for temp in temp_list:
        shutil.rmtree(temp, ignore_errors=True)

    return SNR, rms


def get_intflux(imagename, rms, maskname=None):

    cqa = casa_tools.quanta
    with casa_tools.ImageReader(imagename) as image:
        bm = image.restoringbeam(polarization=0)
        bmaj_arcsec = cqa.convert(bm['major'], 'arcsec')['value']
        bmin_arcsec = cqa.convert(bm['minor'], 'arcsec')['value']
        cdelt12_arcsec = np.degrees(np.abs(image.coordsys().increment()['numeric'][0:2]))*3600.0
        beamarea = np.pi*bmaj_arcsec*bmin_arcsec/(4.0*np.log(2.0))
        cellarea = cdelt12_arcsec[0]*cdelt12_arcsec[1]
        pix_per_beam = beamarea/cellarea

        if maskname is None:
            maskname = imagename.replace('image.tt0', 'mask')
        imagestats = image.statistics(mask=maskname)

    if len(imagestats['flux']) > 0:
        flux = imagestats['flux'][0]
        n_beams = imagestats['npts'][0]/pix_per_beam
        e_flux = (n_beams)**0.5*rms
    else:
        flux = 0.
        e_flux = rms

    return flux, e_flux


def get_n_ants(vislist):
    # Examines number of antennas in each ms file and returns the minimum number of antennas
    msmd = casatools.msmetadata()

    n_ants = 50.0
    for vis in vislist:
        msmd.open(vis)
        names = msmd.antennanames()
        msmd.close()
        n_ant_vis = len(names)
        if n_ant_vis < n_ants:
            n_ants = n_ant_vis
    return n_ants


def get_ant_list(vis):
    # Examines number of antennas in each ms file and returns the minimum number of antennas
    msmd = casatools.msmetadata()
    msmd.open(vis)
    names = msmd.antennanames()
    msmd.close()
    return names


def rank_refants(vis, refantignore=None):
    """Rank the reference antenna for a measurement set."""

    refantobj = findrefant.RefAntHeuristics(vis=vis, field='',
                                            geometry=True, flagging=True, intent='', spw='',
                                            refantignore=refantignore)
    refant_list = refantobj.calculate()
    LOG.info(f"refant list for {vis} = {refant_list!r}")

    return ','.join(refant_list)


def get_SNR_self(
        all_targets, bands, vislist, selfcal_library, n_ant, solints, integration_time, inf_EB_gaincal_combine,
        inf_EB_gaintype):
    solint_snr = {}
    solint_snr_per_spw = {}
    if inf_EB_gaintype == 'G':
        polscale = 2.0
    else:
        polscale = 1.0
    for target in all_targets:
        solint_snr[target] = {}
        solint_snr_per_spw[target] = {}
        for band in selfcal_library[target].keys():
            solint_snr[target][band] = {}
            solint_snr_per_spw[target][band] = {}
            for solint in solints[band]:
                #code to work around some VLA data not having the same number of spws due to missing BlBPs
                #selects spwlist from the visibilities with the greates number of spws
                maxspws = 0
                maxspwvis = ''
                for vis in vislist:
                    if selfcal_library[target][band][vis]['n_spws'] >= maxspws:
                        maxspws = selfcal_library[target][band][vis]['n_spws']
                        maxspwvis = vis+''
                solint_snr[target][band][solint] = 0.0
                solint_snr_per_spw[target][band][solint] = {}
                if solint == 'inf_EB':
                    SNR_self_EB = np.zeros(len(vislist))
                    SNR_self_EB_spw = {}
                    for i in range(len(vislist)):
                        SNR_self_EB[i] = selfcal_library[target][band]['SNR_orig']/((n_ant)**0.5*(
                            selfcal_library[target][band]['Total_TOS']/selfcal_library[target][band][vislist[i]]['TOS'])**0.5)
                        SNR_self_EB_spw[vislist[i]] = {}
                        for spw in selfcal_library[target][band][vislist[i]]['spwsarray']:
                            if spw in SNR_self_EB_spw[vislist[i]].keys():
                                SNR_self_EB_spw[
                                    vislist[i]][
                                    str(spw)] = (polscale) ** -0.5 * selfcal_library[target][band]['SNR_orig'] / (
                                    (n_ant - 3) ** 0.5 *
                                    (selfcal_library[target][band]['Total_TOS'] /
                                     selfcal_library[target][band][vislist[i]]['TOS']) ** 0.5) * (
                                    selfcal_library[target][band][vislist[i]]['per_spw_stats'][spw]['effective_bandwidth'] /
                                    selfcal_library[target][band][vislist[i]]['total_effective_bandwidth']) ** 0.5
                    for spw in selfcal_library[target][band][maxspwvis]['spwsarray']:
                        mean_SNR = 0.0
                        for j in range(len(vislist)):
                            if spw in SNR_self_EB_spw[vislist[j]].keys():
                                mean_SNR += SNR_self_EB_spw[vislist[j]][str(spw)]
                        mean_SNR = mean_SNR/len(vislist)
                        solint_snr_per_spw[target][band][solint][str(spw)] = mean_SNR
                    solint_snr[target][band][solint] = np.mean(SNR_self_EB)
                    selfcal_library[target][band]['per_EB_SNR'] = np.mean(SNR_self_EB)
                elif solint == 'inf' or solint == 'inf_ap':
                    selfcal_library[target][band]['per_scan_SNR'] = selfcal_library[target][band]['SNR_orig']/((n_ant-3)**0.5*(
                        selfcal_library[target][band]['Total_TOS']/selfcal_library[target][band]['Median_scan_time'])**0.5)
                    solint_snr[target][band][solint] = selfcal_library[target][band]['per_scan_SNR']
                    for spw in selfcal_library[target][band][maxspwvis]['spwsarray']:
                        solint_snr_per_spw[target][band][solint][
                            str(spw)] = selfcal_library[target][band]['SNR_orig'] / (
                            (n_ant - 3) ** 0.5 *
                            (selfcal_library[target][band]['Total_TOS'] / selfcal_library[target][band]['Median_scan_time']) ** 0.5) * (
                            selfcal_library[target][band][maxspwvis]['per_spw_stats'][spw]['effective_bandwidth'] /
                            selfcal_library[target][band][maxspwvis]['total_effective_bandwidth']) ** 0.5
                elif solint == 'int':
                    solint_snr[target][band][solint] = selfcal_library[target][band]['SNR_orig'] / \
                        ((n_ant-3)**0.5*(selfcal_library[target][band]['Total_TOS']/integration_time)**0.5)
                    for spw in selfcal_library[target][band][maxspwvis]['spwsarray']:
                        solint_snr_per_spw[target][band][solint][
                            str(spw)] = selfcal_library[target][band]['SNR_orig'] / (
                            (n_ant - 3) ** 0.5 * (selfcal_library[target][band]['Total_TOS'] / integration_time) ** 0.5) * (
                            selfcal_library[target][band][maxspwvis]['per_spw_stats'][spw]['effective_bandwidth'] /
                            selfcal_library[target][band][maxspwvis]['total_effective_bandwidth']) ** 0.5
                else:
                    solint_float = float(solint.replace('s', '').replace('_ap', ''))
                    solint_snr[target][band][solint] = selfcal_library[target][band]['SNR_orig'] / \
                        ((n_ant-3)**0.5*(selfcal_library[target][band]['Total_TOS']/solint_float)**0.5)
                    for spw in selfcal_library[target][band][maxspwvis]['spwsarray']:
                        solint_snr_per_spw[target][band][solint][
                            str(spw)] = selfcal_library[target][band]['SNR_orig'] / (
                            (n_ant - 3) ** 0.5 * (selfcal_library[target][band]['Total_TOS'] / solint_float) ** 0.5) * (
                            selfcal_library[target][band][maxspwvis]['per_spw_stats'][spw]['effective_bandwidth'] /
                            selfcal_library[target][band][maxspwvis]['total_effective_bandwidth']) ** 0.5
    return solint_snr, solint_snr_per_spw


def get_SNR_self_update(
        all_targets, band, vislist, selfcal_library, n_ant, solint_curr, solint_next, integration_time, solint_snr):
    for target in all_targets:
        if solint_next == 'inf' or solint_next == 'inf_ap':
            selfcal_library[target][band]['per_scan_SNR'] = selfcal_library[target][band][vislist[0]][solint_curr]['SNR_post']/(
                (n_ant-3)**0.5*(selfcal_library[target][band]['Total_TOS']/selfcal_library[target][band]['Median_scan_time'])**0.5)
            solint_snr[target][band][solint_next] = selfcal_library[target][band]['per_scan_SNR']
        elif solint_next == 'int':
            solint_snr[target][band][solint_next] = selfcal_library[target][band][vislist[0]][solint_curr][
                'SNR_post'] / ((n_ant - 3) ** 0.5 * (selfcal_library[target][band]['Total_TOS'] / integration_time) ** 0.5)
        else:
            solint_float = float(solint_next.replace('s', '').replace('_ap', ''))
            solint_snr[target][band][solint_next] = selfcal_library[target][band][vislist[0]][solint_curr][
                'SNR_post'] / ((n_ant - 3) ** 0.5 * (selfcal_library[target][band]['Total_TOS'] / solint_float) ** 0.5)


def get_sensitivity(vislist, selfcal_library, field='', specmode='mfs', virtual_spw='all',
                    chan=0, cellsize='0.025arcsec', imsize=1600, robust=0.5, uvtaper=''):

    for vis in vislist:
        if virtual_spw == 'all':
            im.selectvis(vis=vis, field=field, spw=selfcal_library[vis]['spws'])
        else:
            im.selectvis(vis=vis, field=field, spw=selfcal_library['spw_map'][virtual_spw][vis])

    casa_tools.imager.defineimage(mode=specmode, stokes='I', cellx=cellsize, celly=cellsize, nx=imsize, ny=imsize)
    casa_tools.imager.weight(type='briggs', robust=robust)
    if uvtaper != '':
        if 'klambda' in uvtaper:
            uvtaper = uvtaper.replace('klambda', '')
            uvtaperflt = float(uvtaper)
            bmaj = str(206.0/uvtaperflt)+'arcsec'
            bmin = bmaj
            bpa = '0.0deg'
        if 'arcsec' in uvtaper:
            bmaj = uvtaper
            bmin = uvtaper
            bpa = '0.0deg'
        LOG.info('uvtaper: '+bmaj+' '+bmin+' '+bpa)
        casa_tools.imager.filter(type='gaussian', bmaj=bmaj, bmin=bmin, bpa=bpa)
    try:
        estsens = np.float64(casa_tools.imager.apparentsens()[1])
    except:
        LOG.info('#')
        LOG.info('# Sensisitivity Calculation failed for %r', vislist)
        LOG.info('# Data in MS may be flagged')
        LOG.info('#')
    casa_tools.imager.done()

    LOG.info(f'Estimated Sensitivity: {estsens}')
    return estsens


def parse_contdotdat(contdotdat_file, target):
    """
    Parses the cont.dat file that includes line emission automatically identified by the ALMA pipeline.

    Parameters
    ==========
    msfile: Name of the cont.dat file (string)

    Returns
    =======
    Dictionary with the boundaries of the frequency range including line emission. The dictionary keys correspond to the spectral windows identified 
    in the cont.dat file, and the entries include numpy arrays with shape (nline, 2), with the 2 corresponding to min and max frequencies identified.
    """
    f = open(contdotdat_file, 'r')
    lines = f.readlines()
    f.close()

    while '\n' in lines:
        lines.remove('\n')

    contdotdat = {}
    desiredTarget = False
    for i, line in enumerate(lines):
        if 'ALL' in line:
            continue
        if 'Field' in line:
            field = line.split()[-1]
            if field == target:
                desiredTarget = True
                continue
            else:
                desiredTarget = False
                continue
        if desiredTarget == True:
            if 'SpectralWindow' in line:
                spw = int(line.split()[-1])
                contdotdat[spw] = []
            else:
                contdotdat[spw] += [line.split()[0].split("G")[0].split("~")]

    for spw in contdotdat:
        contdotdat[spw] = np.array(contdotdat[spw], dtype=float)

    return contdotdat


def get_spw_chanwidths(vis, spwarray):
    widtharray = np.zeros(len(spwarray))
    bwarray = np.zeros(len(spwarray))
    nchanarray = np.zeros(len(spwarray))
    for i in range(len(spwarray)):
        tb.open(vis+'/SPECTRAL_WINDOW')
        widtharray[i] = np.abs(np.unique(tb.getcol('CHAN_WIDTH', startrow=spwarray[i], nrow=1)))
        bwarray[i] = np.abs(np.unique(tb.getcol('TOTAL_BANDWIDTH', startrow=spwarray[i], nrow=1)))
        nchanarray[i] = np.abs(np.unique(tb.getcol('NUM_CHAN', startrow=spwarray[i], nrow=1)))
        tb.close()

    return widtharray, bwarray, nchanarray


def get_spw_bandwidth(vis, spwsarray_dict, target, vislist):
    spwbws = {}
    for spw in spwsarray_dict[vis]:
        tb.open(vis+'/SPECTRAL_WINDOW')
        spwbws[spw] = np.abs(np.unique(tb.getcol('TOTAL_BANDWIDTH', startrow=spw, nrow=1)))[
            0]/1.0e9  # put bandwidths into GHz
        tb.close()
    spweffbws = spwbws.copy()
    if os.path.exists("cont.dat"):
        spweffbws = get_spw_eff_bandwidth(vis, target, vislist, spwsarray_dict)

    return spwbws, spweffbws


def get_spw_eff_bandwidth(vis, target, vislist, spwsarray_dict):
    spweffbws = {}
    contdotdat = parse_contdotdat('cont.dat', target)

    spwvisref = vislist[0]
    for key in contdotdat.keys():
        msmd.open(spwvisref)
        spwname = msmd.namesforspws(key)[0]
        msmd.close()
        msmd.open(vis)
        spws = msmd.spwsfornames(spwname)
        msmd.close()
        trans_spw = -1
        # must directly cast to int, otherwise the CASA tool call does not like numpy.uint64
        #loop through returned spws to see which is in the spw array rather than assuming, because assumptions be damned
        for check_spw in spws[spwname]:
            matching_index = np.where(check_spw == spwsarray_dict[vis])
            if len(matching_index[0]) == 0:
                continue
            else:
                trans_spw = check_spw
                break
        #trans_spw=int(np.max(spws[spwname])) # assume higher number spw is the correct one, generally true with ALMA data structure
        cumulat_bw = 0.0
        for i in range(len(contdotdat[key])):
            cumulat_bw += np.abs(contdotdat[key][i][1]-contdotdat[key][i][0])
        spweffbws[trans_spw] = cumulat_bw+0.0
    return spweffbws


def get_spw_chanavg(vis, widtharray, bwarray, chanarray, desiredWidth=15.625e6):
    avgarray = np.zeros(len(widtharray))
    for i in range(len(widtharray)):
        if desiredWidth > bwarray[i]:
            avgarray[i] = chanarray[i]
        else:
            nchan = bwarray[i]/desiredWidth
            nchan = np.round(nchan)
            avgarray[i] = chanarray[i]/nchan
        if avgarray[i] < 1.0:
            avgarray[i] = 1.0
    return avgarray


def get_spw_map(selfcal_library, target, band, telescope):
    # Get the list of EBs from the selfcal_library
    vislist = selfcal_library[target][band]['vislist'].copy()

    # If we are looking at VLA data, find the EB with the maximum number of SPWs so that we have the fewest "odd man out" SPWs hanging out at the end as possible.
    if "VLA" in telescope:
        maxspws = 0
        maxspwvis = ''
        for vis in vislist:
            if selfcal_library[target][band][vis]['n_spws'] >= maxspws:
                maxspws = selfcal_library[target][band][vis]['n_spws']
                maxspwvis = vis+''

        vislist.remove(maxspwvis)
        vislist = [maxspwvis] + vislist

    spw_map = {}
    virtual_index = 0
    # This code is meant to be generic in order to prepare for cases where multiple EBs might have unique SPWs in them (e.g. inhomogeneous data),
    # but the criterea for which SPWs match will need to be updated for this to truly generalize.
    for vis in vislist:
        for spw in selfcal_library[target][band][vis]['spwsarray']:
            found_match = False
            for s in spw_map:
                for v in spw_map[s].keys():
                    if vis == v:
                        continue

                    if telescope == "ALMA" or telescope == "ACA":
                        # NOTE: This assumes that matching based on SPW name is ok. Fine for now... but will need to update this for inhomogeneous data.
                        msmd.open(vis)
                        spwname = msmd.namesforspws(spw)[0]
                        msmd.close()

                        msmd.open(v)
                        sname = msmd.namesforspws(spw_map[s][v])[0]
                        msmd.close()

                        if spwname == sname:
                            found_match = True
                    elif 'VLA' in telescope:
                        msmd.open(vis)
                        bandwidth1 = msmd.bandwidths(spw)
                        chanwidth1 = msmd.chanwidths(spw)[0]
                        chanfreq1 = msmd.chanfreqs(spw)[0]
                        msmd.close()

                        msmd.open(v)
                        bandwidth2 = msmd.bandwidths(spw_map[s][v])
                        chanwidth2 = msmd.chanwidths(spw_map[s][v])[0]
                        chanfreq2 = msmd.chanfreqs(spw_map[s][v])[0]
                        msmd.close()

                        if bandwidth1 == bandwidth2 and chanwidth1 == chanwidth2 and chanfreq1 == chanfreq2:
                            found_match = True

                    if found_match:
                        spw_map[s][vis] = spw
                        break

                if found_match:
                    break

            if not found_match:
                spw_map[virtual_index] = {}
                spw_map[virtual_index][vis] = spw
                virtual_index += 1

    LOG.info('spw_map: %s', spw_map)

    return spw_map


def get_image_parameters(vislist, telescope, band, band_properties):
    cells = np.zeros(len(vislist))
    for i in range(len(vislist)):
        # im.open(vislist[i])
        im.selectvis(vis=vislist[i], spw=band_properties[vislist[i]][band]['spwarray'])
        adviseparams = im.advise()
        cells[i] = adviseparams[2]['value']/2.0
        im.close()
    cell = np.min(cells)
    cellsize = '{:0.3f}arcsec'.format(cell)
    nterms = 1
    if band_properties[vislist[0]][band]['fracbw'] > 0.1:
        nterms = 2
    if 'VLA' in telescope:
        fov = 45.0e9/band_properties[vislist[0]][band]['meanfreq']*60.0*1.5
        if band_properties[vislist[0]][band]['meanfreq'] < 12.0e9:
            fov = fov*2.0
    if telescope == 'ALMA':
        fov = 63.0*100.0e9/band_properties[vislist[0]][band]['meanfreq']*1.5
    if telescope == 'ACA':
        fov = 108.0*100.0e9/band_properties[vislist[0]][band]['meanfreq']*1.5
    npixels = int(np.ceil(fov/cell / 100.0)) * 100
    if npixels > 16384:
        npixels = 16384
    return cellsize, npixels, nterms


def get_nterms(fracbw, nt1snr=3.0):
    """Get nterm based on fracbw and nt1snr.

    see PIPE-1772.
    """
    def func_cubic(X, A, B, C, D, E, F, G, H):
        return A*X[0]**3+B*X[1]**3+C*X[0]**2*X[1]+D*X[1]**2*X[0] + E*X[0]*X[1] + F*X[0] + G*X[1] + H

    nterms = 1
    if fracbw >= 0.1:
        nterms = 2
    else:
        if nt1snr > 10.0:
            # Estimate the gain of going to nterms=2 based on nterms=1 S/N and fracbw
            # The coefficients come from a empirical fit using simulated data with a spectral index of 3
            A1 = 2336.415
            B1 = 0.051
            C1 = -306.590
            D1 = 5.654
            E1 = 28.220
            F1 = -23.598
            G1 = -0.594
            H1 = -3.413
            # Note that we fit the log10 of S/N_nt1 and [S/N_nt2 - S/N_nt1]/(S/N_nt1)
            Z = 10**func_cubic([fracbw, np.log10(nt1snr)], A1, B1, C1, D1, E1, F1, G1, H1)
            if Z > 0.01:
                nterms = 2
    LOG.debug('fracbw = {:0.3f}, nt1snr = {:0.3f}: nterms = {:d} will be used'.format(fracbw, nt1snr, nterms))
    return nterms


def get_mean_freq(vislist, spwsarray):
    tb.open(vislist[0]+'/SPECTRAL_WINDOW')
    freqarray = tb.getcol('REF_FREQUENCY')
    tb.close()
    meanfreq = np.mean(freqarray[spwsarray[vislist[0]]])
    minfreq = np.min(freqarray[spwsarray[vislist[0]]])
    maxfreq = np.max(freqarray[spwsarray[vislist[0]]])
    fracbw = np.abs(maxfreq-minfreq)/meanfreq
    return meanfreq, maxfreq, minfreq, fracbw


def get_spw_chanbin(bwarray, chanarray, desiredWidth=15.625e6):
    """Calculate the number of channels to average over for each spw.
    
    note: mstransform only accept chanbin as integer.
    """
    avgarray = [1]*len(bwarray)
    for i in range(len(bwarray)):
        nchan = bwarray[i]/desiredWidth
        nchan = np.round(nchan)
        avgarray[i] = int(chanarray[i]/nchan)
        if avgarray[i] < 1.0:
            avgarray[i] = 1
    return avgarray


def get_desired_width(meanfreq):
    if meanfreq >= 50.0e9:
        desiredWidth = 15.625e6
    elif (meanfreq < 50.0e9) and (meanfreq >= 40.0e9):
        desiredWidth = 16.0e6
    elif (meanfreq < 40.0e9) and (meanfreq >= 26.0e9):
        desiredWidth = 8.0e6
    elif (meanfreq < 26.0e9) and (meanfreq >= 18.0e9):
        desiredWidth = 16.0e6
    elif (meanfreq < 18.0e9) and (meanfreq >= 8.0e9):
        desiredWidth = 8.0e6
    elif (meanfreq < 8.0e9) and (meanfreq >= 4.0e9):
        desiredWidth = 4.0e6
    elif (meanfreq < 4.0e9) and (meanfreq >= 2.0e9):
        desiredWidth = 4.0e6
    elif (meanfreq < 2.0e9):
        desiredWidth = 2.0e6
    return desiredWidth


def get_ALMA_bands(vislist, spwstring, spwarray):
    meanfreq, maxfreq, minfreq, fracbw = get_mean_freq(vislist, spwarray)
    observed_bands = {}
    if (meanfreq < 950.0e9) and (meanfreq >= 787.0e9):
        band = 'Band_10'
    elif (meanfreq < 720.0e9) and (meanfreq >= 602.0e9):
        band = 'Band_9'
    elif (meanfreq < 500.0e9) and (meanfreq >= 385.0e9):
        band = 'Band_8'
    elif (meanfreq < 373.0e9) and (meanfreq >= 275.0e9):
        band = 'Band_7'
    elif (meanfreq < 275.0e9) and (meanfreq >= 211.0e9):
        band = 'Band_6'
    elif (meanfreq < 211.0e9) and (meanfreq >= 163.0e9):
        band = 'Band_5'
    elif (meanfreq < 163.0e9) and (meanfreq >= 125.0e9):
        band = 'Band_4'
    elif (meanfreq < 116.0e9) and (meanfreq >= 84.0e9):
        band = 'Band_3'
    elif (meanfreq < 84.0e9) and (meanfreq >= 67.0e9):
        band = 'Band_2'
    elif (meanfreq < 50.0e9) and (meanfreq >= 30.0e9):
        band = 'Band_1'
    else:
        raise RuntimeError('meanfreq is ouside the allowed range in get_ALMA_bands()')
    bands = [band]
    for vis in vislist:
        with casa_tools.MSMDReader(vis) as msmd:
            observed_bands[vis] = {}
            observed_bands[vis]['bands'] = [band]
            for band in bands:
                # reject spws that do not exist in the MS.
                observed_bands[vis][band] = {}
                observed_bands[vis][band]['spwarray'] = spwarray[vis]
                observed_bands[vis][band]['spwstring'] = spwstring[vis]+''
                observed_bands[vis][band]['meanfreq'] = meanfreq
                observed_bands[vis][band]['maxfreq'] = maxfreq
                observed_bands[vis][band]['minfreq'] = minfreq
                observed_bands[vis][band]['fracbw'] = fracbw
    get_max_uvdist(vislist, observed_bands[vislist[0]]['bands'].copy(), observed_bands)
    return bands, observed_bands


def get_VLA_bands(vislist, fields):
    observed_bands = {}
    for vis in vislist:
        observed_bands[vis] = {}
        msmd.open(vis)
        spws_for_field = np.array([])
        for field in fields:
            spws_temp = msmd.spwsforfield(field)
            spws_for_field = np.concatenate((spws_for_field, np.array(spws_temp)))
        msmd.close()
        spws_for_field = np.unique(spws_for_field)
        spws_for_field.sort()
        spws_for_field = spws_for_field.astype('int')
        #visheader=vishead(vis,mode='list',listitems=[])
        tb.open(vis+'/SPECTRAL_WINDOW')
        spw_names = tb.getcol('NAME')
        tb.close()
        #spw_names=visheader['spw_name'][0]
        spw_names_band = ['']*len(spws_for_field)
        spw_names_band = ['']*len(spws_for_field)
        spw_names_bb = ['']*len(spws_for_field)
        spw_names_spw = np.zeros(len(spw_names_band)).astype('int')

        for i in range(len(spws_for_field)):
            spw_names_band[i] = spw_names[spws_for_field[i]].split('#')[0]
            spw_names_bb[i] = spw_names[spws_for_field[i]].split('#')[1]
            spw_names_spw[i] = spws_for_field[i]
        all_bands = np.unique(spw_names_band)
        observed_bands[vis]['n_bands'] = len(all_bands)
        observed_bands[vis]['bands'] = all_bands.tolist()
        for band in all_bands:
            index = np.where(np.array(spw_names_band) == band)
            observed_bands[vis][band] = {}
            # logic below removes the VLA standard pointing setups at X and C-bands
            # the code is mostly immune to this issue since we get the spws for only
            # the science targets above; however, should not ignore the possibility
            # that someone might also do pointing on what is the science target
            if (band == 'EVLA_X') and (len(index[0]) >= 2):  # ignore pointing band
                observed_bands[vis][band]['spwarray'] = spw_names_spw[index[0]]
                indices_to_remove = np.array([])
                for i in range(len(observed_bands[vis][band]['spwarray'])):
                    meanfreq, maxfreq, minfreq, fracbw = get_mean_freq([vis], {vis: np.array([observed_bands[vis][band]['spwarray'][i]])})
                    if (meanfreq == 8.332e9) or (meanfreq == 8.460e9):
                        indices_to_remove = np.append(indices_to_remove, [i])
                observed_bands[vis][band]['spwarray'] = np.delete(observed_bands[vis][band]['spwarray'], indices_to_remove.astype(int))
            elif (band == 'EVLA_C') and (len(index[0]) >= 2):  # ignore pointing band
                observed_bands[vis][band]['spwarray'] = spw_names_spw[index[0]]
                indices_to_remove = np.array([])
                for i in range(len(observed_bands[vis][band]['spwarray'])):
                    meanfreq, maxfreq, minfreq, fracbw = get_mean_freq([vis], {vis: np.array([observed_bands[vis][band]['spwarray'][i]])})
                    if (meanfreq == 4.832e9) or (meanfreq == 4.960e9):
                        indices_to_remove = np.append(indices_to_remove, [i])
                observed_bands[vis][band]['spwarray'] = np.delete(observed_bands[vis][band]['spwarray'], indices_to_remove.astype(int))
            else:
                observed_bands[vis][band]['spwarray'] = spw_names_spw[index[0]]
            spwslist = observed_bands[vis][band]['spwarray'].tolist()
            spwstring = ','.join(str(spw) for spw in spwslist)
            observed_bands[vis][band]['spwstring'] = spwstring+''
            observed_bands[vis][band]['meanfreq'], observed_bands[vis][band]['maxfreq'], \
                observed_bands[vis][band]['minfreq'], observed_bands[vis][band]['fracbw'] \
                = get_mean_freq([vis], {vis: [observed_bands[vis][band]['spwarray']]})
    bands_match = True
    for i in range(len(vislist)):
        for j in range(i+1, len(vislist)):
            bandlist_match = (observed_bands[vislist[i]]['bands'] == observed_bands[vislist[i+1]]['bands'])
            if not bandlist_match:
                bands_match = False
    if not bands_match:
        LOG.warning('Inconsistent VLA bands are detected in the input MSs.')
    get_max_uvdist(vislist, observed_bands[vislist[0]]['bands'].copy(), observed_bands)
    return observed_bands[vislist[0]]['bands'].copy(), observed_bands


def get_dr_correction(telescope, dirty_peak, theoretical_sens, vislist):
    dirty_dynamic_range = dirty_peak/theoretical_sens
    n_dr_max = 2.5
    n_dr = 1.0
    tlimit = 2.0
    if telescope == 'ALMA':
        if dirty_dynamic_range > 150.:
            maxSciEDR = 150.0
            new_threshold = np.max([n_dr_max * theoretical_sens, dirty_peak / maxSciEDR * tlimit])
            n_dr = new_threshold/theoretical_sens
        else:
            if dirty_dynamic_range > 100.:
                n_dr = 2.5
            elif 50. < dirty_dynamic_range <= 100.:
                n_dr = 2.0
            elif 20. < dirty_dynamic_range <= 50.:
                n_dr = 1.5
            elif dirty_dynamic_range <= 20.:
                n_dr = 1.0
    if telescope == 'ACA':
        numberEBs = len(vislist)
        if numberEBs == 1:
            # single-EB 7m array datasets have limited dynamic range
            maxSciEDR = 30
            dirtyDRthreshold = 30
            n_dr_max = 2.5
        else:
            # multi-EB 7m array datasets will have better dynamic range and can be cleaned somewhat deeper
            maxSciEDR = 55
            dirtyDRthreshold = 75
            n_dr_max = 3.5

        if dirty_dynamic_range > dirtyDRthreshold:
            new_threshold = np.max([n_dr_max * theoretical_sens, dirty_peak / maxSciEDR * tlimit])
            n_dr = new_threshold/theoretical_sens
        else:
            if dirty_dynamic_range > 40.:
                n_dr = 3.0
            elif dirty_dynamic_range > 20.:
                n_dr = 2.5
            elif 10. < dirty_dynamic_range <= 20.:
                n_dr = 2.0
            elif 4. < dirty_dynamic_range <= 10.:
                n_dr = 1.5
            elif dirty_dynamic_range <= 4.:
                n_dr = 1.0
    return n_dr


def get_baseline_dist(vis):
    # Get the antenna names and offsets.

    msmd = casatools.msmetadata()

    msmd.open(vis)
    names = msmd.antennanames()
    offset = [msmd.antennaoffset(name) for name in names]
    msmd.close()
    baselines = np.array([])
    for i in range(len(offset)):
        for j in range(i+1, len(offset)):
            baseline = np.sqrt(
                (offset[i]["longitude offset"]['value'] - offset[j]["longitude offset"]['value']) ** 2 +
                (offset[i]["latitude offset"]['value'] - offset[j]["latitude offset"]['value']) ** 2)

            baselines = np.append(baselines, np.array([baseline]))
    return baselines


def get_max_uvdist(vislist, bands, band_properties):
    for band in bands:
        all_baselines = np.array([])
        for vis in vislist:
            baselines = get_baseline_dist(vis)
            all_baselines = np.append(all_baselines, baselines)
        max_baseline = np.max(all_baselines)
        min_baseline = np.min(all_baselines)
        baseline_5 = np.percentile(all_baselines, 5.0)
        baseline_75 = np.percentile(all_baselines, 75.0)
        baseline_median = np.percentile(all_baselines, 50.0)
        for vis in vislist:
            max_uv_dist = max_baseline  # leave maxuv in meters like the other uv entries /meanlam/1000.0
            min_uv_dist = min_baseline
            band_properties[vis][band]['maxuv'] = max_uv_dist
            band_properties[vis][band]['minuv'] = min_uv_dist
            band_properties[vis][band]['75thpct_uv'] = baseline_75
            band_properties[vis][band]['median_uv'] = baseline_median
            band_properties[vis][band]['LAS'] = 0.6 / (1000*baseline_5) * 180./np.pi * 3600.


def get_uv_range(band, band_properties, vislist):
    if (band == 'EVLA_C') or (band == 'EVLA_X') or (band == 'EVLA_S') or (band == 'EVLA_L'):
        n_vis = len(vislist)
        mean_max_uv = 0.0
        for vis in vislist:
            mean_max_uv += band_properties[vis][band]['maxuv']
        mean_max_uv = mean_max_uv/float(n_vis)
        min_uv = 0.05*mean_max_uv
        uvrange = '>{:0.2f}m'.format(min_uv)
    else:
        uvrange = ''
    return uvrange


def compare_beams(image1, image2):

    with casa_tools.ImageReader(image1) as image:
        bm1 = image.restoringbeam(polarization=0)
    with casa_tools.ImageReader(image2) as image:
        bm2 = image.restoringbeam(polarization=0)

    beammajor_1 = bm1['major']['value']
    beamminor_1 = bm1['minor']['value']

    beammajor_2 = bm2['major']['value']
    beamminor_2 = bm2['minor']['value']

    beamarea_1 = beammajor_1*beamminor_1
    beamarea_2 = beammajor_2*beamminor_2
    delta_beamarea = (beamarea_2-beamarea_1)/beamarea_1
    return delta_beamarea


def get_sols_flagged_solns(gaintable):
    tb.open(gaintable)
    flags = tb.getcol('FLAG').squeeze()
    nsols = flags.size
    flagged_sols = np.where(flags == True)
    nflagged_sols = flagged_sols[0].size
    tb.close()
    return nflagged_sols, nsols


def gaussian_norm(x, mean, sigma):
    gauss_dist = np.exp(-(x-mean)**2/(2*sigma**2))
    norm_gauss_dist = gauss_dist/np.max(gauss_dist)
    return norm_gauss_dist


def importdata(vislist, all_targets, telescope):
    spectral_scan = False
    scantimesdict, integrationsdict, integrationtimesdict, integrationtimes, n_spws, minspw, spwsarray_dict, spws_set = fetch_scan_times(
        vislist, all_targets)

    spwslist_dict = {}
    spwstring_dict = {}
    for vis in vislist:
        spwslist_dict[vis] = spwsarray_dict[vis].tolist()
        spwstring_dict[vis] = ','.join(str(spw) for spw in spwslist_dict[vis])
    if spws_set[vislist[0]].ndim > 1:
        nspws_sets = spws_set[vislist[0]].shape[0]
    else:
        nspws_sets = 1

    if 'VLA' in telescope:
        bands, band_properties = get_VLA_bands(vislist, all_targets)

    if telescope == 'ALMA' or telescope == 'ACA':
        bands, band_properties = get_ALMA_bands(vislist, spwstring_dict, spwsarray_dict)
        if nspws_sets > 1 and spws_set[vislist[0]].ndim > 1:
            spectral_scan = True

    scantimesdict = {}
    scanstartsdict = {}
    scanendsdict = {}
    integrationsdict = {}
    integrationtimesdict = {}
    mosaic_field_dict = {}
    bands_to_remove = []
    spws_set_dict = {}
    nspws_sets_dict = {}

    for band in bands:
        LOG.info(band)
        scantimesdict_temp, scanstartsdict_temp, scanendsdict_temp, integrationsdict_temp, integrationtimesdict_temp,\
            integrationtimes_temp, n_spws_temp, minspw_temp, spwsarray_temp, spws_set_dict_temp, mosaic_field_temp = fetch_scan_times_band_aware(vislist, all_targets, band_properties, band)

        scantimesdict[band] = scantimesdict_temp.copy()
        scanstartsdict[band] = scanstartsdict_temp.copy()
        scanendsdict[band] = scanendsdict_temp.copy()
        integrationsdict[band] = integrationsdict_temp.copy()
        mosaic_field_dict[band] = mosaic_field_temp.copy()
        integrationtimesdict[band] = integrationtimesdict_temp.copy()
        spws_set_dict[band] = spws_set_dict_temp.copy()
        if spws_set_dict[band][vislist[0]].ndim > 1:
            nspws_sets_dict[band] = spws_set_dict[band][vislist[0]].shape[0]
        else:
            nspws_sets_dict[band] = 1
        if n_spws_temp == -99:
            for vis in vislist:
                band_properties[vis].pop(band)
                band_properties[vis]['bands'].remove(band)
                LOG.info('Removing '+band+' bands from list due to no observations')
            bands_to_remove.append(band)

        loopcount = 0
        for vis in vislist:
            for target in all_targets:
                check_target = len(integrationsdict[band][vis][target])
                if check_target == 0:
                    integrationsdict[band][vis].pop(target)
                    integrationtimesdict[band][vis].pop(target)
                    scantimesdict[band][vis].pop(target)
                    scanstartsdict[band][vis].pop(target)
                    scanendsdict[band][vis].pop(target)
                    if loopcount == 0:
                        mosaic_field_dict[band].pop(target)
            loopcount += 1
    if len(bands_to_remove) > 0:
        for delband in bands_to_remove:
            bands.remove(delband)

    return bands, band_properties, scantimesdict, scanstartsdict, scanendsdict, integrationtimesdict, \
        spwslist_dict, spwstring_dict, spwsarray_dict, mosaic_field_dict, spectral_scan, spws_set_dict


def get_flagged_solns_per_spw(spwlist, gaintable):
    # Get the antenna names and offsets.

    tb = casa_tools.table

    # Calculate the number of flags for each spw.
    # gaintable='"'+gaintable+'"'
    os.system('cp -r '+gaintable.replace(' ', '\ ')+' tempgaintable.g')
    gaintable = 'tempgaintable.g'
    nflags = [tb.calc('[select from '+gaintable+' where SPECTRAL_WINDOW_ID==' +
                      spwlist[i]+' giving  [ntrue(FLAG)]]')['0'].sum() for i in
              range(len(spwlist))]
    nunflagged = [tb.calc('[select from '+gaintable+' where SPECTRAL_WINDOW_ID==' +
                          spwlist[i]+' giving  [nfalse(FLAG)]]')['0'].sum() for i in
                  range(len(spwlist))]
    os.system('rm -rf tempgaintable.g')
    fracflagged = np.array(nflags)/(np.array(nflags)+np.array(nunflagged))
    # Calculate a score based on those two.
    return nflags, nunflagged, fracflagged


def analyze_inf_EB_flagging(selfcal_library, band, spwlist, gaintable, vis, target, spw_combine_test_gaintable, spectral_scan):
    # if more than two antennas are fully flagged relative to the combinespw results, fallback to combinespw
    max_flagged_ants_combspw = 2.0
    # if only a single (or few) spw(s) has flagging, allow at most this number of antennas to be flagged before mapping
    max_flagged_ants_spwmap = 1.0
    fallback = ''
    map_index = -1
    min_spwmap_bw = 0.0
    spwmap = [False]*len(spwlist)
    nflags, nunflagged, fracflagged = get_flagged_solns_per_spw(spwlist, gaintable)
    nflags_spwcomb, nunflagged_spwcomb, fracflagged_spwcomb = get_flagged_solns_per_spw(
        [spwlist[0]], spw_combine_test_gaintable)
    eff_bws = np.zeros(len(spwlist))
    total_bws = np.zeros(len(spwlist))
    keylist = list(selfcal_library[target][band][vis]['per_spw_stats'].keys())
    for i in range(len(spwlist)):
        eff_bws[i] = selfcal_library[target][band][vis]['per_spw_stats'][keylist[i]]['effective_bandwidth']
        total_bws[i] = selfcal_library[target][band][vis]['per_spw_stats'][keylist[i]]['bandwidth']
    minimum_flagged_ants_per_spw = np.min(nflags)/2.0
    # account for the fact that some antennas might be completely flagged and give
    minimum_flagged_ants_spwcomb = np.min(nflags_spwcomb)/2.0
    # the impression of a lot of flagging
    maximum_flagged_ants_per_spw = np.max(nflags)/2.0
    delta_nflags = np.array(nflags)/2.0-minimum_flagged_ants_spwcomb  # minimum_flagged_ants_per_spw

    # if there are more than 3 flagged antennas for all spws (minimum_flagged_ants_spwcomb, fallback to doing spw combine for inf_EB fitting
    # use the spw combine number of flagged ants to set the minimum otherwise could misinterpret fully flagged antennas for flagged solutions
    # captures case where no one spws has sufficient S/N, only together do they have enough
    if (minimum_flagged_ants_per_spw-minimum_flagged_ants_spwcomb) > max_flagged_ants_combspw:
        fallback = 'combinespw'

    # if certain spws have more than max_flagged_ants_spwmap flagged solutions that the least flagged spws, set those to spwmap
    for i in range(len(spwlist)):
        if np.min(delta_nflags[i]) > max_flagged_ants_spwmap:
            fallback = 'spwmap'
            spwmap[i] = True
            if total_bws[i] > min_spwmap_bw:
                min_spwmap_bw = total_bws[i]
    # also spwmap spws with similar bandwidths to the others that are getting mapped, avoid low S/N solutions
    if fallback == 'spwmap':
        for i in range(len(spwlist)):
            if total_bws[i] <= min_spwmap_bw:
                spwmap[i] = True
        if all(spwmap):
            fallback = 'combinespw'
    # want the widest bandwidth window that also has the minimum flags to use for spw mapping
    applycal_spwmap = []
    if fallback == 'spwmap':
        minflagged_index = (np.array(nflags)/2.0 == minimum_flagged_ants_per_spw).nonzero()
        max_bw_index = (eff_bws == np.max(eff_bws[minflagged_index[0]])).nonzero()
        max_bw_min_flags_index = np.intersect1d(minflagged_index[0], max_bw_index[0])
        # if len(max_bw_min_flags_index) > 1:
        # don't need the conditional since this works with array lengths of 1
        map_index = max_bw_min_flags_index[np.argmax(eff_bws[max_bw_min_flags_index])]
        # else:
        #   map_index=max_bw_min_flags_index[0]

        # make spwmap list that first maps everything to itself, need max spw to make that list
        maxspw = np.max(selfcal_library[target][band][vis]['spwsarray']+1)
        applycal_spwmap_int_list = list(np.arange(maxspw))
        for i in range(len(applycal_spwmap_int_list)):
            applycal_spwmap.append(applycal_spwmap_int_list[i])

        # replace the elements that require spwmapping (spwmap[i] == True
        for i in range(len(spwmap)):
            LOG.info(f'{i} {spwlist[i]} {spwmap[i]}')
            if spwmap[i]:
                applycal_spwmap[int(spwlist[i])] = int(spwlist[map_index])
        # always fallback to combinespw for spectral scans
        if fallback != '' and spectral_scan:
            fallback = 'combinespw'
    return fallback, map_index, spwmap, applycal_spwmap
