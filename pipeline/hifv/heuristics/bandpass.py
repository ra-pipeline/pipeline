import os
import math
import time

import numpy as np

import pipeline.infrastructure.utils as utils
import pipeline.infrastructure as infrastructure
from pipeline.infrastructure import casa_tasks
from pipeline.infrastructure import casa_tools
from pipeline.hifv.heuristics.lib_EVLApipeutils import vla_minbaselineforcal
from . import uvrange

LOG = infrastructure.get_logger(__name__)


def removeRows(caltable, spwids):
    """Remove rows from specified spwid from a CASA caltable."""

    with casa_tools.TableReader(caltable, nomodify=False) as tb:
        for spwid in spwids:
            subtb = tb.query('SPECTRAL_WINDOW_ID == '+str(spwid))
            flaggedrows = subtb.rownumbers()
            if len(flaggedrows) > 0:
                LOG.debug('removing rows from table '+caltable+' for spw='+str(spwid))
                tb.removerows(flaggedrows)
            subtb.close()

    with casa_tools.TableReader(caltable+'/SPECTRAL_WINDOW', nomodify=False) as tb:
        for spwid in spwids:
            temparray = tb.getcol('FLAG_ROW')
            temparray[spwid] = True
            tb.putcol('FLAG_ROW', temparray)


def computeChanFlag(vis, caltable, context):

    m = context.observing_run.get_ms(vis)
    channels = m.get_vla_numchan()

    with casa_tools.TableReader(caltable) as table:
        spwVarCol = table.getvarcol('SPECTRAL_WINDOW_ID')
        dataVarCol = table.getvarcol('CPARAM')
        flagVarCol = table.getvarcol('FLAG')
        rowlist = sorted(dataVarCol.keys())

        spwids = []

        largechunk = False

        for rrow in rowlist:
            dataArr = dataVarCol[rrow]
            flagArr = flagVarCol[rrow]
            spwArr = spwVarCol[rrow]

            ispw = spwArr[0]
            fivepctch = int(0.05*channels[ispw])
            startch1 = 0
            startch2 = fivepctch - 1
            endch1 = channels[ispw] - fivepctch
            endch2 = channels[ispw] - 1
            if (fivepctch < 3):
                startch2=2
                endch1=channels[ispw]-3

            # Find flagged ranges in both polarizations
            rangeA = utils.flagged_intervals(flagArr[0,:].flatten())
            rangeB = utils.flagged_intervals(flagArr[1,:].flatten())

            # print rangeA, rangeB

            # If no solutions are found, only one tuple is returned and make note
            '''
            try:
                if ((rangeA[0][0] == 0 and rangeA[0][1] == len(flagArr[0])-1) or (rangeB[0][0] == 0 and rangeB[0][1] == len(flagArr[1])-1)):
                    LOG.warning("channel pre-averaging bandpass calibration heuristic could not recover solutions for spw="+str(spwArr[0]))
                    print rangeA, rangeB
                    spwids.append(spwArr[0])
                    largechunk = True
            except:
                LOG.warning("Problem with using channel pre-averaging bandpass calibration heuristic - check CASA log")
            '''

            # Determine contiguous lengths of failed solutions for both polarizations, but ignoring edge flagging
            for row in rangeA[1:-1]:
                length = row[-1]-row[0]
                spwids.append(spwArr[0])
                LOG.info('WEAKBP FAILED SOLUTION: SPW '+str(spwArr[0])+': '+str(row[0])+'~'+str(row[-1]))
                if length > len(flagArr[0])/32.0:
                    largechunk = True

            for row in rangeB[1:-1]:
                length = row[-1]-row[0]
                spwids.append(spwArr[0])
                LOG.info('WEAKBP FAILED SOLUTION: SPW '+str(spwArr[0])+': '+str(row[0])+'~'+str(row[-1]))
                if length > len(flagArr[1])/32.0:
                    largechunk = True

    spwids = np.unique(spwids)
    spwids = list(spwids)

    return (largechunk, spwids)


def _compute_median_snr(caltable: str) -> dict[int, float]:
    """Compute the median S/N for each SPW in the given caltable.

    Flagged and NaN values are ignored when computing the median. If an SPW has
    no valid SNR values or no rows in the caltable, its median S/N is set to 0.

    Args:
        caltable: Path to the CASA bandpass calibration table.

    Returns:
        Dictionary mapping spectral window ID to median S/N.
    """
    median_snr = {}
    with casa_tools.TableReader(caltable) as table:
        for spw in np.unique(table.getcol('SPECTRAL_WINDOW_ID')):
            subtable = table.query(query=f'SPECTRAL_WINDOW_ID=={spw}')
            snr = subtable.getcol('SNR')
            flag = subtable.getcol('FLAG')
            subtable.close()

            valid_snr = snr[(~flag) & (~np.isnan(snr))]
            median_snr[int(spw)] = float(np.median(valid_snr)) if valid_snr.size else 0.0

    return median_snr


HIGH_BANDS = {'U', 'K', 'A', 'Q', 'KU', 'KA'}
LOW_BANDS = {'4', 'P', 'L', 'S', 'C', 'X'}


def is_high_frequency_band(band: str | None, m=None, spw_list: list | None = None) -> bool:
    """Determine whether the specified band or SPWs correspond to Ku-band or higher (>= 12 GHz)."""
    if band is not None:
        band_name = str(band).strip().upper()
        if band_name in HIGH_BANDS:
            return True
        if band_name in LOW_BANDS:
            return False

    # Fallback to SPW reference frequency if band name is unclassified or ambiguous
    if m is not None and spw_list:
        for spwid in spw_list:
            try:
                if float(m.get_spectral_window(int(spwid)).ref_frequency.value) >= 12.0e9:
                    return True
            except Exception as e:
                LOG.warning("Could not determine reference frequency for SPW %s: %s", spwid, e)
                LOG.debug("Exception traceback during reference frequency evaluation for SPW %s:", spwid, exc_info=True)
    return False


def do_bandpass(vis, caltable, context=None, RefAntOutput=None, spw=None, ktypecaltable=None,
                bpdgain_touse=None, solint=None, append=None, executor=None, solnorm=None,
                bpsolint_mode='auto', band=None):
    """Run CASA task bandpass."""
    m = context.observing_run.get_ms(vis)
    bandpass_field_select_string = context.evla['msinfo'][m.name].bandpass_field_select_string
    bandpass_scan_select_string = context.evla['msinfo'][m.name].bandpass_scan_select_string
    minBL_for_cal = vla_minbaselineforcal()

    try:
        setjy_results = context.results[0].read()[0].setjy_results
    except Exception as e:
        setjy_results = context.results[0].read().setjy_results

    BPGainTables = sorted(context.callibrary.active.get_caltable())
    if os.path.exists(ktypecaltable):
        BPGainTables.append(ktypecaltable)
    BPGainTables.append(bpdgain_touse)

    bandpass_task_args = {'vis': vis,
                          'caltable': caltable,
                          'field': '',
                          'spw': spw,
                          'intent': '',
                          'selectdata': True,
                          'uvrange': '',
                          'scan': bandpass_scan_select_string,
                          'solint': solint,
                          'combine': 'scan',
                          'refant': ','.join(RefAntOutput),
                          'minblperant': minBL_for_cal,
                          'minsnr': 5.0,
                          'solnorm': solnorm,
                          'bandtype': 'B',
                          'fillgaps': 0,
                          'smodel': [],
                          'append': append,
                          'docallib': False,
                          'gaintable': BPGainTables,
                          'gainfield': [''],
                          'interp': [''],
                          'spwmap': [],
                          'parang': True}

    bpscanslist = list(map(int, bandpass_scan_select_string.split(',')))
    scanobjlist = m.get_scans(scan_id=bpscanslist)
    allfieldidlist = []
    for scanobj in scanobjlist:
        fieldobj, = scanobj.fields
        if str(fieldobj.id) not in allfieldidlist:
            allfieldidlist.append(str(fieldobj.id))

    # See vlascanheuristics - only use the first bandpass calibrator
    fieldidlist = [fieldid for fieldid in allfieldidlist if fieldid in bandpass_field_select_string]

    for fieldidstring in fieldidlist:
        fieldid = int(fieldidstring)
        uvrangestring = uvrange(setjy_results, fieldid)
        bandpass_task_args['field'] = fieldidstring
        bandpass_task_args['uvrange'] = uvrangestring
        if os.path.exists(caltable):
            bandpass_task_args['append'] = True

        job = casa_tasks.bandpass(**bandpass_task_args)

        executor.execute(job)

    # PIPE-3064: Check if caltable exists (may not if band is fully flagged)
    if not os.path.exists(caltable):
        LOG.warning(
            'Bandpass calibration table %s does not exist (band may be fully flagged). '
            'Skipping bandpass spectral solint optimization.',
            caltable,
        )
        return {}

    # PIPE-2512 / PIPE-3239: Re-run bandpass for low-S/N SPWs with smoothing if enabled
    mode = str(bpsolint_mode).lower().strip() if bpsolint_mode is not None else 'auto'
    if mode not in ('on', 'auto', 'off'):
        LOG.warning("Unrecognized bpsolint_mode='%s', defaulting to 'auto'.", bpsolint_mode)
        mode = 'auto'

    if mode == 'off':
        LOG.info("Bandpass spectral solint optimization is turned off (bpsolint_mode='off').")
        return {}
    elif mode == 'auto':
        spw_list = [s.strip() for s in spw.split(',')] if spw else []
        if not is_high_frequency_band(band, m=m, spw_list=spw_list):
            LOG.info(
                'Bandpass spectral solint optimization is disabled for band %s '
                "(active only for Ku-band and higher frequencies in 'auto' mode).",
                band,
            )
            return {}
    else:  # mode == 'on'
        LOG.info("Bandpass spectral solint optimization is active for band %s (bpsolint_mode='on').", band)

    median_snrs = _compute_median_snr(caltable)
    low_snr_spws = [spw for spw, snr in median_snrs.items() if snr < 50.0]
    good_snr_spws = [spw for spw, snr in median_snrs.items() if snr >= 50.0]
    if not low_snr_spws:
        LOG.info("All SPWs have median S/N ≥ 50 — no rerun needed.")
        return {}

    LOG.info(f"Re-running bandpass for SPWs with low S/N: {low_snr_spws}")
    # rename the old caltable
    if os.path.exists(caltable):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        os.rename(caltable, f"{caltable}.allspws.{timestamp}.bak")
    if len(good_snr_spws) != 0:
        # Run bandpass using high-SNR SPWs only
        bandpass_task_args['spw'] = ','.join(map(str, good_snr_spws))
        bandpass_task_args['append'] = False
        job = casa_tasks.bandpass(**bandpass_task_args)
        executor.execute(job)
    else:
        LOG.warning(
            'All SPWs have low median S/N (< 50). Skipping initial high-S/N bandpass solving; '
            'will attempt to solve each SPW individually with smoothing.'
        )
    spw_solint = {}
    # re-run the low-SNR SPWs individually with smoothing
    for bad_spw in low_snr_spws:
        snr = median_snrs[bad_spw]
        # if S/N is very low, skip this SPW
        if math.isclose(snr, 0.0, abs_tol=1e-6):
            LOG.warning("SPW %s: median S/N ≈ 0, skipping bandpass re-run", bad_spw)
            continue
        nchan = m.get_spectral_window(bad_spw).num_channels
        if nchan < 16:
            continue
        Nbin = nchan / 16 if snr <= 0 else min((50.0 / snr) ** 2, nchan / 16)
        start = int(math.ceil(Nbin))

        for i in range(start, nchan+1):
            if nchan % i == 0:
                Nbin = i
                break
        spw_solint[bad_spw] = Nbin
        solint_smooth = f"inf,{int(Nbin)}ch"

        LOG.info(f"SPW {bad_spw}: median S/N={snr:.1f}, rerunning with solint='{solint_smooth}'")
        append = os.path.exists(caltable)
        bandpass_task_args.update({
            'spw': str(bad_spw),
            'solint': solint_smooth,
            'append': append,
        })

        job = casa_tasks.bandpass(**bandpass_task_args)
        executor.execute(job)

    return spw_solint


def do_bandpassweakbp(vis, caltable, context=None, RefAntOutput=None, spw=None, ktypecaltable=None,
                      bpdgain_touse=None, solint=None, append=None, solnorm=None):
    """Run CASA task bandpass."""
    m = context.observing_run.get_ms(vis)
    bandpass_field_select_string = context.evla['msinfo'][m.name].bandpass_field_select_string
    bandpass_scan_select_string = context.evla['msinfo'][m.name].bandpass_scan_select_string
    minBL_for_cal = vla_minbaselineforcal()

    BPGainTables = sorted(context.callibrary.active.get_caltable())
    if os.path.exists(ktypecaltable):
        BPGainTables.append(ktypecaltable)
    BPGainTables.append(bpdgain_touse)

    bandpass_task_args = {'vis': vis,
                          'caltable': caltable,
                          'field': bandpass_field_select_string,
                          'spw': spw,
                          'intent': '',
                          'selectdata': True,
                          'uvrange': '',
                          'scan': bandpass_scan_select_string,
                          'solint': solint,
                          'combine': 'scan',
                          'refant': ','.join(RefAntOutput),
                          'minblperant': minBL_for_cal,
                          'minsnr': 5.0,
                          'solnorm': solnorm,
                          'bandtype': 'B',
                          'fillgaps': 0,
                          'smodel': [],
                          'append': append,
                          'docallib': False,
                          'gaintable': BPGainTables,
                          'gainfield': [''],
                          'interp': [''],
                          'spwmap': [],
                          'parang': True}

    job = casa_tasks.bandpass(**bandpass_task_args)

    return job


def weakbp(vis, caltable, context=None, RefAntOutput=None, ktypecaltable=None,
           bpdgain_touse=None, solint=None, append=None, executor=None, spw='', solnorm=None):

    m = context.observing_run.get_ms(vis)
    channels = m.get_vla_numchan()  # Number of channels before averaging

    bpjob = do_bandpassweakbp(vis, caltable, context=context, spw=spw, RefAntOutput=RefAntOutput,
                              ktypecaltable=ktypecaltable, bpdgain_touse=bpdgain_touse, solint='inf', append=False, solnorm=solnorm)
    executor.execute(bpjob)
    (largechunk, spwids) = computeChanFlag(vis, caltable, context)
    # print largechunk, spwids
    if not largechunk and spwids == []:
        # All solutions found - proceed as normal with the pipeline
        interp = ''
        return interp

    LOG.warning("Solutions for all channels not obtained.  Using weak bandpass calibration heuristic.")
    cpa = 2  # Channel pre-averaging
    while largechunk:

        LOG.info("Removing rows in table " + caltable + " for spws="+','.join([str(i) for i in spwids]))
        removeRows(caltable, spwids)
        solint = 'inf,' + str(cpa) + 'ch'
        LOG.warning("Largest contiguous set of channels with no BP solution is greater than maximum " +
                    "allowable 1/32 fractional bandwidth for spw="+','.join([str(i) for i in spwids])
                    + "." + "  Using solint=" + solint)
        LOG.info('Weak bandpass calibration heuristic.  Using solint='+solint)
        bpjob = do_bandpassweakbp(vis, caltable, context=context, RefAntOutput=RefAntOutput,
                                  spw=','.join([str(i) for i in spwids]),
                                  ktypecaltable=ktypecaltable, bpdgain_touse=bpdgain_touse, solint=solint, append=True)
        executor.execute(bpjob)
        (largechunk, spwids) = computeChanFlag(vis, caltable, context)
        for spw in spwids:
            preavgnchan = channels[spw]/float(cpa)
            LOG.debug("CPA: " + str(cpa) + "   NCHAN: "+str(preavgnchan)+"    NCHAN/32: "+str(preavgnchan/32.0))
            if cpa > preavgnchan/32.0:
                LOG.warning("Limiting pre-averaging to maximum 1/32 fractional bandwidth for spw="+str(spw)
                            + ". Interpolation in applycal will need to extend over greater " +
                            "than 1/32 fractional bandwidth, which may fail to capture significant bandpass structure.")
                largechunk = False  # This will break the while loop and move onto applycal
        cpa = cpa * 2

    LOG.warning("Channel gaps in bandpass solutions will be linearly interpolated over in applycal.")
    LOG.warning("Accuracy of bandpass solutions will be slightly degraded at interpolated channels, " +
                "particularly if these fall at spectral window edges where applycal will " +
                "perform 'nearest' extrapolation.")
    interp = 'nearest'
    return interp
