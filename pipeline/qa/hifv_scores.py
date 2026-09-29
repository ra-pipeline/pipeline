"""VLA-specific interferometric QA score calculators."""

from __future__ import annotations

import collections
import functools
import operator
import os
import shutil
from collections import defaultdict
from xml.etree import ElementTree

import numpy as np

import pipeline.infrastructure.pipelineqa as pqa
from pipeline import infrastructure
from pipeline.infrastructure import casa_tasks, casa_tools, utils
from pipeline.infrastructure.renderer import rendererutils
from pipeline.qa.common_scores import (
    AgentStats,
    calc_flags_per_agent,
    calc_frac_newly_flagged,
    linear_score,
    log_qa,
)

LOG = infrastructure.logging.get_logger(__name__)

__all__ = [
    'calc_vla_science_frac_total_flagged',
    'countbaddelays',
    'score_contdat_applied',
    'score_flagged_ant_spw',
    'score_flagged_vla_baddef',
    'score_fluxboot',
    'score_longsolint',
    'score_solint',
    'score_spw_solint',
    'score_syspowerdata',
    'score_testBPdcals_delay',
    'score_testBPdcals_dts_ants',
    'score_testBPdcals_refant',
    'score_total_data_flagged_vla',
    'score_total_data_flagged_vla_bandpass',
    'score_total_data_vla_delay',
    'score_vla_agents',
    'score_vla_flux_residual_rms',
    'score_vla_science_data_flagged_by_agents',
]


def calc_vla_science_frac_total_flagged(summaries, agents=None, scanids=None):
    """Calculate total fraction of vla science data that is flagged. If agents are provided,
    then restrict to statistics for those agents. If scanids are provided,
    then restrict to statistics for those scans.
    """
    agent_stats = calc_flags_per_agent(summaries, scanids=scanids)

    # remove the non-sciece vis flagged from the science total
    if agent_stats:
        science_total = functools.reduce(
            operator.sub,
            [s.flagged for s in agent_stats if s.name in ('before', 'anos', 'intents', 'shadow')],
            agent_stats[0].total,
        )

    # once we have the new science total, replace it for those agents
    # and create a new list that only includes 'science' agents
    science_agents = []
    for stat in agent_stats:
        if stat.name not in ('before', 'anos', 'intents', 'shadow'):
            science_agents.append(AgentStats(name=stat.name, flagged=stat.flagged, total=science_total))

    # sum the number of flagged rows for the selected agents
    frac_flagged = functools.reduce(
        operator.add, [float(s.flagged) / s.total for s in science_agents if not agents or s.name in agents], 0
    )

    return frac_flagged


def score_vla_science_data_flagged_by_agents(ms, summaries, min_frac, max_frac, agents, intents=None):
    """Calculate a score for the agentflagger summaries based on the fraction of
    VLA science data flagged by certain flagging agents. If intents are provided, then
    restrict scoring to the scans that match one or more of these intents.

    min_frac < flagged < max_frac maps to score of 1-0
    """
    # If intents are provided, identify which scans to calculate flagging
    # fraction for.
    if intents:
        scanids = {str(scan.id) for intent in intents for scan in ms.get_scans(scan_intent=intent)}
        if not scanids:
            LOG.warning(
                'Cannot restrict QA score to intent(s) {}, since no matching scans were found.'
                ' Score will be based on scans for all intents.'.format(utils.commafy(intents, quotes=False))
            )
    else:
        scanids = None

    # Calculate fraction of flagged data.
    frac_flagged = calc_vla_science_frac_total_flagged(summaries, agents=agents, scanids=scanids)

    # Convert fraction of flagged data into a score.
    score = linear_score(frac_flagged, min_frac, max_frac, 1.0, 0.0)

    # Set score messages and origin.
    percent = 100.0 * frac_flagged
    longmsg = '%0.2f%% data in %s flagged by %s flagging agents' % (
        percent,
        ms.basename,
        utils.commafy(agents, quotes=False),
    )
    if intents:
        longmsg += ' for intent(s): {}'.format(utils.commafy(intents, quotes=False))
    shortmsg = '%0.2f%% data flagged' % percent

    origin = pqa.QAOrigin(
        metric_name='score_vla_science_data_flagged_by_agents',
        metric_score=frac_flagged,
        metric_units='Fraction of data newly flagged',
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_vla_agents(ms, summaries):
    """Get a score for the fraction of data flagged by online, shadow, and template agents.

    0 < score < 1 === 60% < frac_flagged < 5%
    """
    qascore_list = []

    # PIPE-2576: Part-1: if flag template is used score < 0.5
    for flag_stat in summaries:
        if flag_stat['name'] == 'template':
            score_val = 0.3
            msg = 'Flag template is used for flagging.'
            origin = pqa.QAOrigin(metric_name='score_flagdata', metric_score=score_val, metric_units='')
            qascore_list.append(pqa.QAScore(score_val, longmsg=msg, shortmsg=msg, origin=origin))

    # PIPE-2576: Part-2: if clipping > 1% with spectral line window
    # identified, score scales from 0.3 to 0 based on clipping fraction
    # PIPE-3216: Scale score based on flag fraction to enable proper sorting
    # Collect spectral line and continuum scores separately to sort within each category
    spectral_line_scores = []
    continuum_scores = []
    is_continuum_only = True
    for flag_stat in summaries:
        if flag_stat['name'] == 'clip':
            for spw_id in flag_stat['spw'].keys():
                spw = ms.get_spectral_window(spw_id)
                total = flag_stat['spw'][spw_id]['total']
                if total == 0:
                    continue
                flag_fraction = flag_stat['spw'][spw_id]['flagged'] / total
                if spw.specline_window and is_continuum_only:
                    is_continuum_only = False
                if spw.specline_window and flag_fraction > 0.01:
                    # Scale score linearly from 0.3 (low clipping) to 0 (full clipping)
                    score_val = max(0.0, 0.3 * (1 - flag_fraction))
                    msg = f'Clipping {flag_fraction:.2%} in spectral line spw {spw_id}.'
                    origin = pqa.QAOrigin(
                        metric_name='score_flagdata',
                        metric_score=score_val,
                        metric_units='Fraction of data that is flagged in clipping',
                    )
                    spectral_line_scores.append(pqa.QAScore(score_val, longmsg=msg, shortmsg=msg, origin=origin))

    # PIPE-2576: Part-3:  if clipping > 5% with continuum window
    # identified, score scales from 0.3 to 0 based on clipping fraction
    # PIPE-3216: Apply per-spw scoring for continuum windows with same scaling
    for flag_stat in summaries:
        if flag_stat['name'] == 'clip' and is_continuum_only:
            for spw_id in flag_stat['spw'].keys():
                spw = ms.get_spectral_window(spw_id)
                total = flag_stat['spw'][spw_id]['total']
                if total == 0:
                    continue
                flag_fraction = flag_stat['spw'][spw_id]['flagged'] / total
                if flag_fraction > 0.05:
                    # Scale score linearly from 0.3 (low clipping) to 0 (full clipping)
                    score_val = max(0.0, 0.3 * (1 - flag_fraction))
                    msg = f'Clipping {flag_fraction:.2%} in continuum spw {spw_id}.'
                    origin = pqa.QAOrigin(
                        metric_name='score_flagdata',
                        metric_score=score_val,
                        metric_units='Fraction of data that is flagged in clipping',
                    )
                    continuum_scores.append(pqa.QAScore(score_val, longmsg=msg, shortmsg=msg, origin=origin))

    # Sort each category internally by score (ascending) so higher clipping (lower scores) appears first
    spectral_line_scores.sort(key=lambda x: x.score)
    continuum_scores.sort(key=lambda x: x.score)
    # Add spectral line scores first, then continuum scores
    qascore_list.extend(spectral_line_scores)
    qascore_list.extend(continuum_scores)

    # PIPE-2576: Part-4: if total flagging >30%, score < 0.5
    if summaries:
        flag_fraction = summaries[-1]['flagged'] / summaries[-1]['total']
        score_val = max([(1 - flag_fraction / 0.60), 0.0])
        msg = f'Total flag fraction is {flag_fraction:.2%}.'
        origin = pqa.QAOrigin(
            metric_name='score_flagdata', metric_score=score_val, metric_units='Total Fraction of data that is flagged'
        )
        qascore_list.append(pqa.QAScore(score_val, longmsg=msg, shortmsg=msg, origin=origin))
    else:
        score_val = 0.0
        msg = 'No flag summaries found'
        origin = pqa.QAOrigin(
            metric_name='score_flagdata', metric_score=score_val, metric_units='Total Fraction of data that is flagged'
        )
        qascore_list.append(pqa.QAScore(score_val, longmsg=msg, shortmsg=msg, origin=origin))

    # PIPE-2576: Part-5: endtime = 0 in flag.xml then score <0.5
    flag_table = os.path.join(ms.name, 'Flag.xml')
    if os.path.exists(flag_table):
        source_element = ElementTree.parse(flag_table)
        if source_element:
            for flagset in source_element.findall('row'):
                endtime = flagset.findtext('endTime')
                if int(endtime):
                    score_val = 0.3
                    msg = 'In flag.xml for online flags, end time is 0'
                    origin = pqa.QAOrigin(
                        metric_name='score_flagdata',
                        metric_score=score_val,
                        metric_units='Total Fraction of data that is flagged',
                    )
                    qascore_list.append(pqa.QAScore(score_val, longmsg=msg, shortmsg=msg, origin=origin))
                    break

    return qascore_list


@log_qa
def score_total_data_flagged_vla(filename, summaries):
    """Calculate a score for the flagging task based on the total fraction of
    data flagged.

    0%-5% flagged   -> 1.0
    5%-75% flagged  -> 1.0 to 0.5
    75%-100% flagged -> 0.5 to 0.0
    """
    # Calculate fraction of flagged data.
    frac_flagged = calc_frac_newly_flagged(summaries)

    # Convert fraction of flagged data into a score.
    if frac_flagged > 0.75:
        score = linear_score(frac_flagged, 0.75, 1.0, 0.5, 0.0)
    else:
        score = linear_score(frac_flagged, 0.05, 0.75, 1.0, 0.5)

    # Set score messages and origin.
    percent = 100.0 * frac_flagged
    longmsg = '%0.2f%% of data in %s was flagged' % (percent, filename)
    shortmsg = '%0.2f%% data flagged' % percent

    origin = pqa.QAOrigin(
        metric_name='score_total_data_flagged_vla',
        metric_score=frac_flagged,
        metric_units='Total fraction of VLA data that is flagged',
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=os.path.basename(filename), origin=origin)


@log_qa
def score_total_data_flagged_vla_bandpass(filename, frac_flagged):
    """Calculate a score for the flagging task based on the data flagged in the bandpass table.

    0%-5% flagged   -> 1
    5%-60% flagged  -> 1 to 0
    60-100% flagged -> 0
    """
    # Convert fraction of flagged data into a score.
    if frac_flagged > 0.6:
        score = 0
    else:
        score = linear_score(frac_flagged, 0.05, 0.6, 1.0, 0.0)

    # Set score messages and origin.
    percent = 100.0 * frac_flagged
    longmsg = '%0.2f%% of data in %s was flagged' % (percent, filename)
    shortmsg = '%0.2f%% data flagged' % percent

    origin = pqa.QAOrigin(
        metric_name='score_total_data_flagged_vla_bandpass',
        metric_score=frac_flagged,
        metric_units='Total fraction of VLA data that is flagged in the caltable',
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=os.path.basename(filename), origin=origin)


@log_qa
def score_flagged_vla_baddef(amp_collection, phase_collection, num_antennas):
    """Calculate a score for the flagging task based on the number of antennas flagged.

    0% flagged   -> 1
    0%-30% flagged  -> 1 to 0
    30%-100% flagged -> 0

    frac_flagged -- fraction of antennas flagged
    """
    amp_antennas = set(amp_collection.keys())
    phase_antennas = set(phase_collection.keys())
    affected_antennas = amp_antennas.union(phase_antennas)
    num_affected_antennas = len(affected_antennas)
    frac_flagged = num_affected_antennas / float(num_antennas)
    origin = pqa.QAOrigin(
        metric_name='score_flagged_vla_baddef',
        metric_score=frac_flagged,
        metric_units='Fraction of VLA antennas flagged by hifv_flagbaddef',
    )
    if 0 == frac_flagged:
        return pqa.QAScore(1, longmsg='No antennas flagged', shortmsg='No antennas flagged', origin=origin)
    else:
        # Convert fraction of flagged data into a score.
        score = linear_score(frac_flagged, 0.0, 0.3, 1.0, 0.0)
        # Set score messages and origin.
        percent = 100.0 * frac_flagged
        longmsg = '{:d} of {:d} ({:0.2f}%) antennas affected and some of their spws are flagged'.format(
            num_affected_antennas, num_antennas, percent
        )
        shortmsg = '{:0.2f}% antennas affected'.format(percent)
        return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


def countbaddelays(m, delaytable, delaymax):
    """Args:
        m: measurement set object
        delaytable: Delay caltable
        delaymax: units of ns.  If delay is over this value, it could be added to the dictionary

    Returns:
        Dictionary with antenna name as key
    """
    delaydict = collections.defaultdict(list)
    with casa_tools.TableReader(delaytable) as tb:
        spws = np.unique(tb.getcol('SPECTRAL_WINDOW_ID'))
        for ispw in spws:
            # byspw table must be written to disk in outer layer to avoid 'Table does not exist' error
            tbspw = tb.query(query='SPECTRAL_WINDOW_ID==' + str(ispw), name='byspw')
            ants = np.unique(tbspw.getcol('ANTENNA1'))
            for iant in ants:
                tbant = tbspw.query(query='ANTENNA1==' + str(iant))
                absdel = np.absolute(tbant.getcol('FPARAM'))
                if np.max(absdel) > delaymax:
                    antname = m.get_antenna(iant)[0].name
                    delaydict[antname].append((absdel > delaymax).sum())
                    LOG.info(
                        'Spw='
                        + str(ispw)
                        + ' Ant='
                        + antname
                        + '  Delays greater than 200 ns ='
                        + str((absdel > delaymax).sum())
                    )
                tbant.close()
            tbspw.close()
            # clean up byspw table after each iteration
            byspw = os.getcwd() + '/byspw'
            if os.path.exists(byspw):
                shutil.rmtree(byspw)

    return delaydict


@log_qa
def score_total_data_vla_delay(filename, vis, bandname=None):
    """Compute a QA score based on maximum delay values in a calibration table.
    If the maximum delay is below 15 ns, the score is 1.0. Otherwise, the score
    decreases linearly with increasing delay, down to a minimum of 0.3.
    """
    with casa_tools.TableReader(filename) as tb:
        fpar = tb.getcol('FPARAM')
        delays = np.abs(fpar)  # Units of nanoseconds
        maxdelay = np.max(delays)
    # PIPE-2582: if delays > 15 ns, QA score < 0.5
    if maxdelay < 15.0:
        score = 1.0
    else:
        score = round(max(0.3, 0.49 - 0.01 * (maxdelay - 15)), 2)
    longmsg = 'Max delay'
    if bandname is not None:
        longmsg = longmsg + f' for band {bandname}'
    # Set score message and origin
    longmsg = longmsg + f' is {maxdelay:.2f} ns'

    shortmsg = longmsg

    origin = pqa.QAOrigin(
        metric_name='score_total_data_vla_delay', metric_score=score, metric_units='Delays that exceed 15 ns'
    )

    applies_to = pqa.TargetDataSelection(vis={vis})
    return pqa.QAScore(
        score, longmsg=longmsg, shortmsg=shortmsg, vis=os.path.basename(filename), origin=origin, applies_to=applies_to
    )


@log_qa
def score_vla_flux_residual_rms(fractional_residuals, num_spws, spixl):
    """score_vla_flux_residual_rms: calculates the score for pipeline task hifv_fluxboot

    output: returns QAscore
    --------- parameter descriptions ---------------------------------------------
    fractional_residuals: Take the RMS values of the residuals.
    nums_spws: number of spws
    spixl: list of a spectral index
    """
    if len(fractional_residuals) == 0:
        score = 0.0
        longmsg = 'No fractional residuals available.'
        shortmsg = longmsg
        origin = pqa.QAOrigin(metric_name='score_vla_flux_residual_rms', metric_score=score, metric_units='')
        return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)

    # PIPE-119, part a
    max_res = max(max(res) for res in fractional_residuals)
    if max_res < 0.01:
        score = 1.0
    else:
        score = 1.0 - max_res

    # PIPE-119 part b
    for res in fractional_residuals:
        if max(np.abs(res)) > 0.3:
            LOG.warning('Fractional residuals are > 0.3')
            break

    # PIPE-119 part c
    bool_spix = [True if eval(spix) < -3 or eval(spix) > 2 else False for spix in spixl]
    if num_spws > 1 and all(bool_spix):
        score = score - 0.5
        LOG.warning('spix for a band/s is <-3 or >2, reducing score by 0.5')

    if score < 0.0:
        score = 0.0

    # Set score message and origin
    try:
        longmsg = 'Max rms of the residuals is {!s}'.format(max_res)
    except Exception:
        longmsg = 'No max rms.'
    shortmsg = longmsg

    origin = pqa.QAOrigin(
        metric_name='score_vla_flux_residual_rms', metric_score=score, metric_units='rms values that exceed 0.01'
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_syspowerdata(data: dict) -> list[pqa.QAScore]:
    """Calculates QA score as the minimum of per-band scores based on data points outside 0.7-1.2 range.

    For each band:
    - Band QA = 1.0 - (fraction of values outside [0.7, 1.2])
    Final QA = minimum of all band QA scores.

    Args:
        data (dict[str, list[float]]): Dictionary with band as key and list of float values.

    Returns:
        pqa.QAScore: QA score object
    """
    band_score = None
    qascores = []
    for band, values in data.items():
        outliers = [v for v in values.data.flatten() if v < 0.7 or v > 1.2]
        fraction_outside = len(outliers) / len(values.data.flatten())
        band_score = 1 - fraction_outside

        longmsg = f'Band {band} has {fraction_outside * 100:.2f}% data outside the range 0.7-1.2'

        shortmsg = f'{band}: {fraction_outside * 100:.2f}% >[0.7-1.2]'

        origin = pqa.QAOrigin(metric_name='score_syspowerdata', metric_score=band_score, metric_units='')

        qascores.append(pqa.QAScore(band_score, longmsg=longmsg, shortmsg=shortmsg, origin=origin))

    return qascores


@log_qa
def score_solint(short_solint: dict, long_solint: dict) -> list[pqa.QAScore]:
    """Compute a QA score by comparing short and long solints for each band.

    If any band has a short solint value greater than the corresponding long solint,
    the function assigns a reduced score and includes the affected bands in the message.

    Parameters:
        short_solint: Dictionary containing bandname and corresponding short solint value.
        long_solint: Dictionary containing bandname and corresponding long solint value.

    Returns:
        pqa.QAScore: QA score object
    """
    bandlist = []
    for band in short_solint:
        if isinstance(short_solint[band], str) or isinstance(long_solint[band], str):
            # PIPE-2686: short-term workaround for the issue from the initial PIPE-2583 implementation.
            LOG.warning(
                f'Skip scoring solint band {band} due to string solint value: short_solint=%r, long_solint=%r',
                short_solint[band],
                long_solint[band],
            )
            bandlist.append(band)
        else:
            if short_solint[band] >= long_solint[band]:
                bandlist.append(band)

    if bandlist:
        score = 0.3
        longmsg = f"band {', '.join(bandlist)} has short solint >= long solint, or short solint is 'inf'."
        shortmsg = "short solint >= long solint or short solint is 'inf'"
    else:
        score = 1
        longmsg = 'short solint < long solint'
        shortmsg = 'short solint < long solint'

    origin = pqa.QAOrigin(metric_name='score_solint', metric_score=score, metric_units='')
    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_longsolint(context, result) -> list[pqa.QAScore]:
    bandlist = []
    calscantime = []
    long_solint = result.longsolint
    ms = context.observing_run.get_ms(result.inputs['vis'])

    for scanid in context.evla['msinfo'][ms.name].calibrator_scan_select_string.split(','):
        calscantime = [calscan.time_on_source for calscan in ms.get_scans(int(scanid))]
    median_calscantime = np.median(calscantime)

    for band in long_solint:
        if long_solint[band] > 1.5 * median_calscantime.total_seconds():
            bandlist.append(band)

    if bandlist:
        score = 0.3
        longmsg = f'band {", ".join(bandlist)} has long solint > 1.5 * median calibration scan time'
        shortmsg = 'long solint > 1.5 * median calibration scan time'
    else:
        score = 1
        longmsg = 'long solint < 1.5 * median calibration scan time'
        shortmsg = 'long solint < 1.5 * median calibration scan time'

    origin = pqa.QAOrigin(metric_name='score_longsolint', metric_score=score, metric_units='')
    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_testBPdcals_dts_ants(vis: str, amp_collection: dict, phase_collection: dict, bandname: str) -> pqa.QAScore:
    """Evaluate QA score based on the number of antennas affected by DTS issues."""
    bad_ants = []
    bad_ants.extend([str(a) for a in amp_collection.keys()])
    bad_ants.extend([str(p) for p in phase_collection.keys()])
    num_bad_ants = len(set(bad_ants))
    applies_to = pqa.TargetDataSelection(vis={vis})

    # PIPE-2580: if > 4 antennas have DTS issue, QA score < 0.5
    if num_bad_ants > 4:
        score = rendererutils.SCORE_THRESHOLD_ERROR
        longmsg = f'{num_bad_ants} antennas have DTS issue in {bandname} band'
        shortmsg = f'{num_bad_ants} antennas have DTS issue in {bandname} band'
    else:
        score = 1.0
        longmsg = f'Fewer than four antennas have DTS issue in {bandname} band'
        shortmsg = f'Fewer than four antennas have DTS issue in {bandname} band'
    origin = pqa.QAOrigin(metric_name='score_testBPdcals_dts_ants', metric_score=score, metric_units='')
    qa_score = pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin, applies_to=applies_to)

    return qa_score


@log_qa
def score_testBPdcals_refant(vis: str, bad_refant: list, bandname: str) -> pqa.QAScore:
    """Evaluate QA score based on reference antenna validity."""
    applies_to = pqa.TargetDataSelection(vis={vis})
    # PIPE-2580: if bad reference antenna found, QA score <0.5
    if len(bad_refant) > 0:
        score = rendererutils.SCORE_THRESHOLD_ERROR
        longmsg = f'Bad reference antenna ({", ".join(bad_refant)}) found in {bandname} band'
        shortmsg = longmsg
    else:
        score = 1.0
        longmsg = f'No bad reference antenna found in {bandname} band'
        shortmsg = f'No bad reference antenna found in {bandname} band'
    origin = pqa.QAOrigin(metric_name='score_testBPdcals_refant', metric_score=score, metric_units='')
    qa_score = pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin, applies_to=applies_to)

    return qa_score


@log_qa
def score_testBPdcals_delay(vis: str, caltable: str, bandname: str) -> pqa.QAScore:
    """Evaluate QA score based on median delay per baseband."""
    applies_to = pqa.TargetDataSelection(vis={vis})
    # PIPE-2580: if median delay per baseband > 15 ms, QA score < 0.5
    with casa_tools.TableReader(caltable) as tb:
        fpar = tb.getcol('FPARAM')
        delays = np.abs(fpar)
        median_delay = np.median(delays)
    qa = casa_tools.quanta
    median_delay_val = qa.convert(qa.quantity(median_delay, 'ns'), 'ms')['value']

    if median_delay_val > 15:
        score = rendererutils.SCORE_THRESHOLD_ERROR
        longmsg = f'Median delay > 15 ms for {bandname} band'
        shortmsg = f'Median delay > 15 ms for {bandname} band'
    else:
        score = 1.0
        longmsg = f'Median delay < 15 ms for {bandname} band'
        shortmsg = f'Median delay < 15 ms for {bandname} band'

    origin = pqa.QAOrigin(metric_name='score_testBPdcals_delay', metric_score=score, metric_units='')
    qa_score = pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin, applies_to=applies_to)

    return qa_score


@log_qa
def score_flagged_ant_spw(vis: str, flaggedSolnApplycaldelay: dict) -> [pqa.QAScore]:
    """Calculates score for testBPdcals
    if > 50% of spws in a baseband on a majority of antennas newly flagged
    then score < 0.5
    The flaggedSolnApplycaldelay dictionary is structured as follows:
    flaggedSolnApplycaldelay = {
        'antspw': {
            antenna: {
                spwid: {
                    polid: {
                        'flagged': <numeric_value>
                        'total': <numeric_value>
                        'fraction': <numeric_value>
                    }
                }
            }
        }
    }
    """
    badbandlist = []
    goodbandlist = []
    applies_to = pqa.TargetDataSelection(vis={vis})
    scorelist = []
    for bandname, flag_results in flaggedSolnApplycaldelay.items():
        flagged_ants = 0
        total_ants = len(flag_results['antspw'])

        for antenna in flag_results['antspw']:
            flagged_spw_count = 0
            for spwid in flag_results['antspw'][antenna]:
                spw_flagged = False
                for polid in flag_results['antspw'][antenna][spwid]:
                    if flag_results['antspw'][antenna][spwid][polid]['flagged'] > 0:
                        spw_flagged = True
                if spw_flagged:
                    flagged_spw_count += 1
            # If >50% of SPWs flagged on this antenna
            if flagged_spw_count > len(flag_results['antspw'][antenna]) // 2:
                flagged_ants += 1

        if flagged_ants > total_ants // 2:
            badbandlist.append(bandname)
        else:
            goodbandlist.append(bandname)
    if len(badbandlist) > 0:
        score = rendererutils.SCORE_THRESHOLD_ERROR
        longmsg = f'More than 50% of SPWs are newly flagged on the majority of antennas in {",".join(badbandlist)} band'
        shortmsg = longmsg
        origin = pqa.QAOrigin(metric_name='score_flagged_ant_spw', metric_score=score, metric_units='')
        score = pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin, applies_to=applies_to)
        scorelist.append(score)

    if len(goodbandlist) > 0:
        score = 1
        longmsg = (
            f'Less than 50% of SPWs are newly flagged on the majority of antennas in {",".join(goodbandlist)} band'
        )
        shortmsg = longmsg
        origin = pqa.QAOrigin(metric_name='score_flagged_ant_spw', metric_score=score, metric_units='')
        score = pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin, applies_to=applies_to)
        scorelist.append(score)

    return scorelist


@log_qa
def score_fluxboot(context, result) -> list[pqa.QAScore]:
    qascores = []
    calms = 'calibrators.ms'
    ms = context.observing_run.get_ms(result.vis)
    sci_spws = ms.get_spectral_windows(science_windows_only=True)
    total_sci_spws = len(sci_spws)
    flagdata_task = casa_tasks.flagdata(vis=calms, mode='summary')
    flagdata_result = flagdata_task.execute()
    flag_spw = flagdata_result['spw']
    ignored_spw_count = 0

    for spw in sci_spws:
        str_spwid = str(spw.id)
        if str_spwid in flag_spw.keys():
            flag_percentage = flag_spw[str_spwid]['flagged'] / flag_spw[str_spwid]['total']
            if flag_percentage > 0.5:
                ignored_spw_count += 1
        else:
            ignored_spw_count += 1
    spwlist = [spw.id for spw in sci_spws]
    applies_to = pqa.TargetDataSelection(vis={result.vis}, spw=spwlist)

    # PIPE-2584, part-1: If > 50% of science spws are fully flagged
    # or missing from calibrators.ms: QA score < 0.5
    flag_ratio = ignored_spw_count / total_sci_spws
    score = 1 - flag_ratio
    if score < 0.5:
        msg = f'{flag_ratio * 100:.2f}% of science SPWs flagged or not present in calibrator.ms'
        origin = pqa.QAOrigin(metric_name='score_fluxboot', metric_score=score, metric_units='')
        qascores.append(pqa.QAScore(score, longmsg=msg, shortmsg=msg, origin=origin, applies_to=applies_to))

    # PIPE-2584, part-2: If > 50% of all calibrators.ms data flagged
    total_flag_ratio = flagdata_result['flagged'] / flagdata_result['total']
    score = 1 - total_flag_ratio

    msg = f'{total_flag_ratio * 100:.2f}% of data flagged in calibrator.ms'
    origin = pqa.QAOrigin(metric_name='score_fluxboot', metric_score=score, metric_units='')
    applies_to = pqa.TargetDataSelection(vis={result.vis})
    qascores.append(pqa.QAScore(score, longmsg=msg, shortmsg=msg, origin=origin, applies_to=applies_to))

    # PIPE-2584, part-3: IF spectral index > +/- 5: QA score < 0.5
    for sp_result in result.spindex_results:
        if abs(float(sp_result['spix'])) > 5:
            score = rendererutils.SCORE_THRESHOLD_ERROR
            msg = 'spectral index > +- 5'
            origin = pqa.QAOrigin(metric_name='score_fluxboot', metric_score=score, metric_units='')
            qascores.append(pqa.QAScore(score, longmsg=msg, shortmsg=msg, origin=origin, applies_to=applies_to))
            break

    setup_scans = defaultdict(list)
    valid_intents = {'TARGET', 'AMPLITUDE', 'BANDPASS', 'PHASE', 'POLANGLE'}
    for scan in context.evla['msinfo'][result.vis].calibrator_scan_select_string.split(','):
        sc = ms.get_scans(int(scan))[0]
        spw_ids = sorted(spw.id for spw in sc.spws if spw.intents & valid_intents)
        setup_key = frozenset(spw_ids)

        setup_scans[setup_key].append(sc.id)

    missing_spws = 0
    missing_spws_scans = {}
    for spws, scans in setup_scans.items():
        for spw in spws:
            flagged_all = True
            for sc in scans:
                taql = f'SCAN_NUMBER={sc} and DATA_DESC_ID =={spw} and FLAG_ROW==False'
                numrows = utils.get_row_count(calms, taql)
                if numrows > 0:
                    flagged_all = False
                    break
            if flagged_all:
                missing_spws += 1
                missing_spws_scans[spw] = ', '.join(str(int(s)) for s in scans)

    if missing_spws / total_sci_spws > 0.5:
        score = rendererutils.SCORE_THRESHOLD_ERROR
        for spw, scans in missing_spws_scans.items():
            longmsg = f'SPW {spw} flagged in scans {scans}'
            shortmsg = f'SPW {spw} flagged in all scans'
            origin = pqa.QAOrigin(metric_name='score_fluxboot', metric_score=score, metric_units='')
            applies_to = pqa.TargetDataSelection(vis={result.vis}, spw=spw)
            qascores.append(
                pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin, applies_to=applies_to)
            )

    # PIPE-2584, part-4: Ensure flux density is measured.
    # If not measured, model_data column will be filled up with 1.

    # checkif the MODEL column is not present.
    with casa_tools.TableReader(calms) as table:
        if 'MODEL_DATA' in table.colnames():
            is_model_present = True
        else:
            is_model_present = False

    if not is_model_present:
        msg = 'Model column is not present'
        origin = pqa.QAOrigin(metric_name='score_fluxboot', metric_score=score, metric_units='')
        applies_to = pqa.TargetDataSelection(vis={result.vis})
        qascores.append(pqa.QAScore(score, longmsg=msg, shortmsg=msg, origin=origin, applies_to=applies_to))

        return qascores

    for spws, scans in setup_scans.items():
        for sc in scans:
            spwlist = []
            for spw in spws:
                taql = f'SCAN_NUMBER={sc} and DATA_DESC_ID =={spw} and FLAG_ROW==False'
                numrows = utils.get_row_count(calms, taql)
                if numrows == 0:
                    continue
                job = casa_tasks.visstat(
                    vis=calms,
                    scan=str(sc),
                    useflags=True,
                    spw=str(spw),
                    datacolumn='model',
                    correlation='LL,RR',
                    doquantiles=False,
                )
                vis_stats = job.execute()
                for desc_id, stats in vis_stats.items():
                    if all(stats.get(key) == 1 for key in ['min', 'max', 'mean']):
                        spwlist.append(str(spw))
            if spwlist:
                score = rendererutils.SCORE_THRESHOLD_ERROR
                msg = f'Model column is set to 1.0 for scan {sc} and spw {", ".join(spwlist)}'
                origin = pqa.QAOrigin(metric_name='score_fluxboot', metric_score=score, metric_units='')
                applies_to = pqa.TargetDataSelection(vis={result.vis}, scan=sc)
                qascores.append(pqa.QAScore(score, longmsg=msg, shortmsg=msg, origin=origin, applies_to=applies_to))

    return qascores


# PIPE-2512: adding QA score for solint of spws
@log_qa
def score_spw_solint(vis: str, band: str, spw_solint: dict) -> pqa.QAScore | None:
    """Evaluate QA score based on the solint of each spectral window"""
    qascore = None

    pairs = [f'[spw={spw}, solint={solint}ch]' for spw, solint in spw_solint.items() if solint > 1]

    if pairs:
        score = rendererutils.SCORE_THRESHOLD_ERROR
        msg = f'Using per-SPW solints: {", ".join(pairs)} for {band} band'
        shortmsg = f'Per-SPW solints > 1ch for {band} band'
        origin = pqa.QAOrigin(metric_name='score_spw_solint', metric_score=score, metric_units='')

        applies_to = pqa.TargetDataSelection(vis={vis}, spw=set(spw_solint.keys()))

        qascore = pqa.QAScore(score, longmsg=msg, shortmsg=shortmsg, origin=origin, applies_to=applies_to)

    return qascore


# PIPE-3046: adding QA score 1 if cont.dat is applied
@log_qa
def score_contdat_applied(vis: str) -> pqa.QAScore:
    """Evaluate QA score based on whether cont.dat is applied"""
    score = 1.0
    longmsg = "'cont.dat' file is present. Using VLA Spectral Line Heuristics for checkflagmode=target-vla."
    shortmsg = 'cont.dat is applied'
    origin = pqa.QAOrigin(metric_name='score_contdat_applied', metric_score=score, metric_units='')

    applies_to = pqa.TargetDataSelection(vis={vis})

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin, applies_to=applies_to)
