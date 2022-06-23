"""
Created on 9 Jan 2014

@author: sjw
"""
import collections
import datetime
import functools
import math
import operator
import os
import re
from typing import List

import numpy as np
from scipy import interpolate
from scipy.special import erf

import pipeline.domain as domain
import pipeline.domain.measures as measures
import pipeline.infrastructure.basetask
import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.pipelineqa as pqa
import pipeline.infrastructure.renderer.rendererutils as rutils
import pipeline.infrastructure.utils as utils
import pipeline.qa.checksource as checksource
from pipeline.domain.datatable import OnlineFlagIndex
from pipeline.infrastructure import casa_tools

__all__ = ['score_polintents',                                # ALMA specific
           'score_bands',                                     # ALMA specific
           'score_bwswitching',                               # ALMA specific
           'score_spwnames',                                  # ALMA specific
           'score_tsysspwmap',                                # ALMA specific
           'score_number_antenna_offsets',                    # ALMA specific
           'score_missing_derived_fluxes',                    # ALMA specific
           'score_derived_fluxes_snr',                        # ALMA specific
           'score_combine_spwmapping',                        # ALMA specific
           'score_phaseup_mapping_fraction',                  # ALMA specific
           'score_phaseup_spw_median_snr_for_phase',          # ALMA specific
           'score_phaseup_spw_median_snr_for_check',          # ALMA specific
           'score_refspw_mapping_fraction',                   # ALMA specific
           'score_missing_phaseup_snrs',                      # ALMA specific
           'score_missing_bandpass_snrs',                     # ALMA specific
           'score_poor_phaseup_solutions',                    # ALMA specific
           'score_poor_bandpass_solutions',                   # ALMA specific
           'score_missing_phase_snrs',                        # ALMA specific
           'score_poor_phase_snrs',                           # ALMA specific
           'score_flagging_view_exists',                      # ALMA specific
           'score_checksources',                              # ALMA specific
           'score_gfluxscale_k_spw',                          # ALMA specific
           'score_fluxservice',                               # ALMA specific
           'score_renorm',                                    # ALMA IF specific
           'score_file_exists',
           'score_path_exists',
           'score_flags_exist',
           'score_mses_exist',
           'score_applycmds_exist',
           'score_caltables_exist',
           'score_setjy_measurements',
           'score_missing_intents',
           'score_ephemeris_coordinates',
           'score_online_shadow_template_agents',
           'score_lowtrans_flagcmds',                         # ALMA IF specific
           'score_applycal_agents',
           'score_vla_agents',
           'score_total_data_flagged',
           'score_total_data_flagged_vla',
           'score_total_data_flagged_vla_bandpass',
           'score_flagged_vla_baddef',
           'score_total_data_vla_delay',
           'score_vla_flux_residual_rms',
           'score_ms_model_data_column_present',
           'score_ms_history_entries_present',
           'score_contiguous_session',
           'score_multiply',
           'score_mom8_fc_image']

LOG = logging.get_logger(__name__)


# - utility functions --------------------------------------------------------------------------------------------------

def log_qa(method):
    """
    Decorator that logs QA evaluations as they return with a log level of
    INFO for scores between perfect and 'slightly suboptimal' scores and
    WARNING for any other level. These messages are meant for pipeline runs
    without a weblog output.
    """
    def f(self, *args, **kw):
        # get the size of the CASA log before task execution
        qascore = method(self, *args, **kw)
        if pipeline.infrastructure.basetask.DISABLE_WEBLOG:
            if isinstance(qascore, tuple):
                _qascore = qascore[0]
            else:
                _qascore = qascore
            if _qascore.score >= rutils.SCORE_THRESHOLD_SUBOPTIMAL:
                LOG.info(_qascore.longmsg)
            else:
                LOG.warning(_qascore.longmsg)
        return qascore

    return f


# struct to hold flagging statistics
AgentStats = collections.namedtuple("AgentStats", "name flagged total")


def calc_flags_per_agent(summaries, scanids=None):
    """
    Calculate flagging statistics per agents. If scanids are provided,
    restrict statistics to just those scans.
    """
    stats = []
    flagsum = 0

    # Go through summary for each agent.
    for idx, summary in enumerate(summaries):
        if scanids:
            # Add up flagged and total for specified scans.
            flagcount = 0
            totalcount = 0
            for scanid in scanids:
                if scanid in summary['scan']:
                    flagcount += int(summary['scan'][scanid]['flagged'])
                    totalcount += int(summary['scan'][scanid]['total'])
        else:
            # Add up flagged and total for all data.
            flagcount = int(summary['flagged'])
            totalcount = int(summary['total'])

        # From the second summary onwards, subtract counts from the previous
        # one.
        if idx > 0:
            flagcount -= flagsum

        # Create agent stats object, append to output.
        stat = AgentStats(name=summary['name'],
                          flagged=flagcount,
                          total=totalcount)
        stats.append(stat)

        # Keep count of total number of flags found in summaries, for
        # subsequent summaries.
        flagsum += flagcount

    return stats


def calc_frac_total_flagged(summaries, agents=None, scanids=None):
    """
    Calculate total fraction of data that is flagged. If agents are provided,
    then restrict to statistics for those agents. If scanids are provided,
    then restrict to statistics for those scans.
    """

    agent_stats = calc_flags_per_agent(summaries, scanids=scanids)

    # sum the number of flagged rows for the selected agents
    frac_flagged = functools.reduce(
        operator.add, [float(s.flagged)/s.total for s in agent_stats if not agents or s.name in agents], 0)

    return frac_flagged


def calc_vla_science_frac_total_flagged(summaries, agents=None, scanids=None):
    """
    Calculate total fraction of vla science data that is flagged. If agents are provided,
    then restrict to statistics for those agents. If scanids are provided,
    then restrict to statistics for those scans.
    """

    agent_stats = calc_flags_per_agent(summaries, scanids=scanids)

    # remove the non-sciece vis flagged from the science total
    if agent_stats:
        science_total = functools.reduce(operator.sub, [s.flagged for s in agent_stats
                                                        if s.name in ('before', 'anos', 'intents',
                                                                      'shadow')], agent_stats[0].total)

    # once we have the new science total, replace it for those agents
    # and create a new list that only includes 'science' agents
    science_agents = []
    for stat in agent_stats:
        if stat.name not in ('before', 'anos', 'intents', 'shadow'):
            science_agents.append(AgentStats(name=stat.name,
                                             flagged=stat.flagged,
                                             total=science_total))

    # sum the number of flagged rows for the selected agents
    frac_flagged = functools.reduce(operator.add, [float(s.flagged)/s.total for s in science_agents
                                                   if not agents or s.name in agents], 0)

    return frac_flagged


def calc_frac_newly_flagged(summaries, agents=None, scanids=None):
    """
    Calculate fraction of data that is newly flagged, i.e. exclude pre-existing
    flags (assumed to be represented in first summary). If agents are provided,
    then restrict to statistics for those agents. If scanids are provided,
    then restrict to statistics for those scans.
    """
    agent_stats = calc_flags_per_agent(summaries, scanids=scanids)

    # sum the number of flagged rows for the selected agents
    frac_flagged = functools.reduce(
        operator.add, [float(s.flagged)/s.total for s in agent_stats[1:] if not agents or s.name in agents], 0)

    return frac_flagged


def linear_score(x, x1, x2, y1=0.0, y2=1.0):
    """
    Calculate the score for the given data value, assuming the
    score follows a linear gradient between the low and high values.

    x values will be clipped to lie within the range x1->x2
    """
    x1 = float(x1)
    x2 = float(x2)
    y1 = float(y1)
    y2 = float(y2)

    clipped_x = sorted([x1, x, x2])[1]
    m = (y2-y1) / (x2-x1)
    c = y1 - m*x1
    return m*clipped_x + c


def score_data_flagged_by_agents(ms, summaries, min_frac, max_frac, agents=None, intents=None):
    """
    Calculate a score for the agentflagger summaries based on the fraction of
    data flagged by certain flagging agents. If intents are provided, then
    restrict scoring to the scans that match one or more of these intents.

    min_frac < flagged < max_frac maps to score of 1-0
    """
    # If intents are provided, identify which scans to calculate flagging
    # fraction for.
    if intents:
        scanids = {str(scan.id) for intent in intents for scan in ms.get_scans(scan_intent=intent)}
        if not scanids:
            LOG.warning("Cannot restrict QA score to intent(s) {}, since no matching scans were found."
                        " Score will be based on scans for all intents.".format(utils.commafy(intents, quotes=False)))
    else:
        scanids = None

    # Calculate fraction of flagged data.
    frac_flagged = calc_frac_total_flagged(summaries, agents=agents, scanids=scanids)

    # Convert fraction of flagged data into a score.
    score = linear_score(frac_flagged, min_frac, max_frac, 1.0, 0.0)

    # Set score messages and origin.
    percent = 100.0 * frac_flagged
    longmsg = ("{:.2f}% data in {} flagged".format(percent, ms.basename))
    if agents:
        longmsg += " by {} flagging agents".format(utils.commafy(agents, quotes=False))
    if intents:
        longmsg += ' for intent(s): {}.'.format(utils.commafy(intents, quotes=False))
    shortmsg = '%0.2f%% data flagged' % percent

    origin = pqa.QAOrigin(metric_name='score_data_flagged_by_agents',
                          metric_score=frac_flagged,
                          metric_units='Fraction of data newly flagged')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


def score_vla_science_data_flagged_by_agents(ms, summaries, min_frac, max_frac, agents, intents=None):
    """
    Calculate a score for the agentflagger summaries based on the fraction of
    VLA science data flagged by certain flagging agents. If intents are provided, then
    restrict scoring to the scans that match one or more of these intents.

    min_frac < flagged < max_frac maps to score of 1-0
    """
    # If intents are provided, identify which scans to calculate flagging
    # fraction for.
    if intents:
        scanids = {str(scan.id) for intent in intents for scan in ms.get_scans(scan_intent=intent)}
        if not scanids:
            LOG.warning("Cannot restrict QA score to intent(s) {}, since no matching scans were found."
                        " Score will be based on scans for all intents.".format(utils.commafy(intents, quotes=False)))
    else:
        scanids = None

    # Calculate fraction of flagged data.
    frac_flagged = calc_vla_science_frac_total_flagged(summaries, agents=agents, scanids=scanids)

    # Convert fraction of flagged data into a score.
    score = linear_score(frac_flagged, min_frac, max_frac, 1.0, 0.0)

    # Set score messages and origin.
    percent = 100.0 * frac_flagged
    longmsg = ('%0.2f%% data in %s flagged by %s flagging agents'
               '' % (percent, ms.basename, utils.commafy(agents, quotes=False)))
    if intents:
        longmsg += ' for intent(s): {}'.format(utils.commafy(intents, quotes=False))
    shortmsg = '%0.2f%% data flagged' % percent

    origin = pqa.QAOrigin(metric_name='score_vla_science_data_flagged_by_agents',
                          metric_score=frac_flagged,
                          metric_units='Fraction of data newly flagged')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)

# - exported scoring functions -----------------------------------------------------------------------------------------


def score_ms_model_data_column_present(all_mses, mses_with_column):
    """
    Give a score for a group of mses based on the number with modeldata
    columns present.
    None with modeldata - 100% with modeldata = 1.0 -> 0.5
    """
    num_with = len(mses_with_column)
    num_all = len(all_mses)
    f = float(num_with) / num_all

    if mses_with_column:
        # log a message like 'No model columns found in a.ms, b.ms or c.ms'
        basenames = [ms.basename for ms in mses_with_column]
        s = utils.commafy(basenames, quotes=False)
        longmsg = 'Model data column found in %s' % s
        shortmsg = '%s/%s have MODELDATA' % (num_with, num_all)
    else:
        # log a message like 'Model data column was found in a.ms and b.ms'
        basenames = [ms.basename for ms in all_mses]
        s = utils.commafy(basenames, quotes=False, conjunction='or')
        longmsg = ('No model data column found in %s' % s)
        shortmsg = 'MODELDATA empty'

    score = linear_score(f, 0.0, 1.0, 1.0, 0.9)

    origin = pqa.QAOrigin(metric_name='score_ms_model_data_column_present',
                          metric_score=f,
                          metric_units='Fraction of MSes with modeldata columns present')

    return pqa.QAScore(score, longmsg, shortmsg, origin=origin)


@log_qa
def score_ms_history_entries_present(all_mses, mses_with_history):
    """
    Give a score for a group of mses based on the number with history
    entries present.
    None with history - 100% with history = 1.0 -> 0.5
    """
    num_with = len(mses_with_history)
    num_all = len(all_mses)

    if mses_with_history:
        # log a message like 'Entries were found in the HISTORY table for
        # a.ms and b.ms'
        basenames = utils.commafy([ms.basename for ms in mses_with_history], quotes=False)
        if len(mses_with_history) is 1:
            longmsg = ('Unexpected entries were found in the HISTORY table of %s. '
                       'This measurement set may already be processed.' % basenames)
        else:
            longmsg = ('Unexpected entries were found in the HISTORY tables of %s. '
                       'These measurement sets may already be processed.' % basenames)
        shortmsg = '%s/%s have HISTORY' % (num_with, num_all)

    else:
        # log a message like 'No history entries were found in a.ms or b.ms'
        basenames = [ms.basename for ms in all_mses]
        s = utils.commafy(basenames, quotes=False, conjunction='or')
        longmsg = 'No HISTORY entries found in %s' % s
        shortmsg = 'No HISTORY entries'

    f = float(num_with) / num_all
    score = linear_score(f, 0.0, 1.0, 1.0, 0.5)

    origin = pqa.QAOrigin(metric_name='score_ms_history_entries_present',
                          metric_score=f,
                          metric_units='Fraction of MSes with HISTORY')

    return pqa.QAScore(score, longmsg, shortmsg, origin=origin)


@log_qa
def score_bwswitching(mses):
    """
    Score a MeasurementSet object based on the presence of
    bandwidth switching observings. For bandwidth switched
    observations the TARGET and PHASE spws are different.
    """
    score = 1.0
    num_mses = len(mses)
    all_ok = True
    complaints = []
    nophasecals = []

    # analyse each MS
    for ms in mses:
        # Get the science spws
        scispws = {spw.id for spw in ms.get_spectral_windows(science_windows_only=True)}

        # Get phase calibrator science spw ids
        phasespws = []
        for scan in ms.get_scans(scan_intent='PHASE'):
            phasespws.extend([spw.id for spw in scan.spws])
        phasespws = set(phasespws).intersection(scispws)

        # Get science target science spw ids
        targetspws = []
        for scan in ms.get_scans(scan_intent='TARGET'):
            targetspws.extend([spw.id for spw in scan.spws])
        targetspws = set(targetspws).intersection(scispws)

        # Determine the difference between the two
        nophasecals = targetspws.difference(phasespws)
        if len(nophasecals) == 0:
            continue

        # Score the difference
        all_ok = False
        for _ in nophasecals:
            score += (-1.0 / num_mses / len(nophasecals))
        longmsg = ('%s contains no phase calibrations for target spws %s'
                   '' % (ms.basename, utils.commafy(nophasecals, False)))
        complaints.append(longmsg)

    if all_ok:
        longmsg = ('Phase calibrations found for all target spws in %s.' % (
                   utils.commafy([ms.basename for ms in mses], False)))
        shortmsg = 'Phase calibrations found for all target spws'
    else:
        longmsg = '%s.' % utils.commafy(complaints, False)
        shortmsg = 'No phase calibrations found for target spws %s' % list(nophasecals)

    origin = pqa.QAOrigin(metric_name='score_bwswitching',
                          metric_score=len(nophasecals),
                          metric_units='Number of MSes without phase calibrators')

    return pqa.QAScore(max(0.0, score), longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_bands(mses):
    """
    Score a MeasurementSet object based on the presence of
    ALMA bands with calibration issues.
    """

    # ALMA receiver bands. Warnings will be raised for any
    # measurement sets containing the following bands.
    score = 1.0
    score_map = {'9': -1.0,
                 '10': -1.0}

    unsupported = set(score_map.keys())

    num_mses = len(mses)
    all_ok = True
    complaints = []

    # analyse each MS
    for ms in mses:
        msbands = []
        for spw in ms.get_spectral_windows(science_windows_only=True):
            bandnum = spw.band.split(' ')[2]
            msbands.append(bandnum)
        msbands = set(msbands)
        overlap = unsupported.intersection(msbands)
        if not overlap:
            continue
        all_ok = False
        for m in overlap:
            score += (score_map[m] / num_mses)
        longmsg = ('%s contains band %s data'
                   '' % (ms.basename, utils.commafy(overlap, False)))
        complaints.append(longmsg)

    if all_ok:
        longmsg = ('No high frequency %s band data were found in %s.' % (list(unsupported),
                   utils.commafy([ms.basename for ms in mses], False)))
        shortmsg = 'No high frequency band data found'
    else:
        longmsg = '%s.' % utils.commafy(complaints, False)
        shortmsg = 'High frequency band data found'

    origin = pqa.QAOrigin(metric_name='score_bands',
                          metric_score=score,
                          metric_units='MS score based on presence of high-frequency data')

    # Make score linear
    return pqa.QAScore(max(rutils.SCORE_THRESHOLD_SUBOPTIMAL, score), longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_parallactic_range(
        pol_intents_present: bool, session_name: str, field_name: str, coverage: float, threshold: float
        ) -> List[pqa.QAScore]:
    """
    Score a session based on parallactic angle coverage.

    Issues a warning if the parallactic coverage < threshold. See PIPE-597
    for full spec.
    """
    # holds the final list of QA scores
    scores: List[pqa.QAScore] = []

    # are polarisation intents expected? true if pol recipe, false if not
    # Polcal detected in session (this function was called!) but this is not a
    # polcal recipe, hence nothing to check
    if not pol_intents_present:
        longmsg = (f'No polarisation intents detected. No parallactic angle coverage check required for session '
                   f'{session_name}.')
        shortmsg = 'Parallactic angle'
        origin = pqa.QAOrigin(
            metric_name='ScoreParallacticAngle',
            metric_score=0.0,
            metric_units='degrees'
        )
        score = pqa.QAScore(1.0, longmsg=longmsg, shortmsg=shortmsg, origin=origin,
                            weblog_location=pqa.WebLogLocation.ACCORDION,
                            applies_to=pqa.TargetDataSelection(session={session_name}))
        return [score]

    # accordion message if coverage is adequate
    if coverage >= threshold:
        longmsg = (f'Sufficient parallactic angle coverage ({coverage:.2f}\u00B0 > {threshold:.2f}\u00B0) for '
                   f'polarisation calibrator {field_name} in session {session_name}')
        shortmsg = 'Parallactic angle'
        origin = pqa.QAOrigin(
            metric_name='ScoreParallacticAngle',
            metric_score=coverage,
            metric_units='degrees'
        )
        score = pqa.QAScore(1.0, longmsg=longmsg, shortmsg=shortmsg, origin=origin,
                            weblog_location=pqa.WebLogLocation.ACCORDION,
                            applies_to=pqa.TargetDataSelection(session={session_name}))
        scores.append(score)

    # complain with a banner message if coverage is insufficient
    else:
        longmsg = (f'Insufficient parallactic angle coverage ({coverage:.2f}\u00B0 < {threshold:.2f}\u00B0) for '
                   f'polarisation calibrator {field_name} in session {session_name}')
        shortmsg = 'Parallactic angle'
        origin = pqa.QAOrigin(
            metric_name='ScoreParallacticAngle',
            metric_score=coverage,
            metric_units='degrees'
        )
        score = pqa.QAScore(0.0, longmsg=longmsg, shortmsg=shortmsg, origin=origin,
                            weblog_location=pqa.WebLogLocation.BANNER,
                            applies_to=pqa.TargetDataSelection(session={session_name}))
        scores.append(score)

    return scores


@log_qa
def score_polintents(recipe_name: str, mses: List[domain.MeasurementSet]) -> List[pqa.QAScore]:
    """
    Score a MeasurementSet object based on the presence of
    polarization intents.
    """
    pol_intents = {'POLARIZATION', 'POLANGLE', 'POLLEAKAGE'}
    # these recipes are allowed to process polarisation data
    pol_recipes = {'hifa_polcal', 'hifa_polcalimage', 'hifa_polcal_renorm', 'hifa_polcalimage_renorm'}

    # Sort to ensure presentation consistency
    mses = sorted(mses, key=lambda ms: ms.basename)

    # are polarisation intents expected? true if pol recipe, false if not
    pol_intents_expected = recipe_name in pol_recipes

    # holds the final list of QA scores
    scores: List[pqa.QAScore] = []

    # Spec from PIPE-606:
    #
    # Currently, hifa_importdata sets the score of that stage to 0 if a
    # polarization calibrator is found (in qa/scorecalculator.py). This score
    # should now become 1 if one of these recipes is being run, or 0.5 if any
    # other recipe is being run.

    # analyse each MS, recording an accordion warning if there's an unexpected
    # pol calibrator

    if pol_intents_expected:
        pol_intents_present = any([pol_intents.intersection(ms.intents) for ms in mses])

        ms_names = {ms.basename for ms in mses}
        mses_for_msg = utils.commafy(sorted(ms_names), False)

        # and an 'all OK' accordion message if pol scans were expected and found
        if pol_intents_present:
            longmsg = f'Polarization calibrations expected and found: {mses_for_msg}'
            shortmsg = 'Polarization calibrators'
            origin = pqa.QAOrigin(metric_name='score_polintents',
                                  metric_score=1.0,
                                  metric_units='MS score based on presence of polarisation data')
            score = pqa.QAScore(1.0, longmsg=longmsg, shortmsg=shortmsg, origin=origin,
                                weblog_location=pqa.WebLogLocation.ACCORDION,
                                applies_to=pqa.TargetDataSelection(vis=ms_names))
            scores.append(score)

        # and complain with a banner message if they weren't. Perhaps this
        # should be part of score_missing_intents?
        else:
            longmsg = f'Expected polarization calibrations not found in {mses_for_msg}'
            shortmsg = 'Polarization calibrators'
            origin = pqa.QAOrigin(metric_name='score_polintents',
                                  metric_score=0.5,
                                  metric_units='MS score based on presence of polarisation data')
            score = pqa.QAScore(0.5, longmsg=longmsg, shortmsg=shortmsg, origin=origin,
                                weblog_location=pqa.WebLogLocation.BANNER,
                                applies_to=pqa.TargetDataSelection(vis=ms_names))
            scores.append(score)

        return scores

    # so, pol data not expected. Find any problem scans and record an accordion warning
    for ms in mses:
        pol_intents_in_ms = sorted(pol_intents.intersection(ms.intents))

        if pol_intents_in_ms:
            longmsg = f'{ms.basename} contains polarization calibrations: {utils.commafy(pol_intents_in_ms, False)}'
            shortmsg = 'Polarization intents'
            origin = pqa.QAOrigin(metric_name='score_polintents',
                                  metric_score=0.5,
                                  metric_units='MS score based on presence of polarisation data')
            score = pqa.QAScore(0.5, longmsg=longmsg, shortmsg=shortmsg, origin=origin,
                                weblog_location=pqa.WebLogLocation.ACCORDION,
                                applies_to=pqa.TargetDataSelection(vis=ms.basename))
            scores.append(score)

    # if there are accordion warnings, summarise them in a banner warning too
    if scores:
        affected_mses = {score.applies_to.vis for score in scores}
        longmsg = f'Unexpected polarization calibrations in {utils.commafy(affected_mses, False)}'
        shortmsg = 'Polarization intents'
        origin = pqa.QAOrigin(metric_name='score_polintents',
                              metric_score=0.5,
                              metric_units='MS score based on presence of polarisation data')
        score = pqa.QAScore(0.5, longmsg=longmsg, shortmsg=shortmsg, origin=origin,
                            weblog_location=pqa.WebLogLocation.BANNER,
                            applies_to=pqa.TargetDataSelection(vis=affected_mses))
        scores.append(score)

    # Add an 'all OK' accordion message if no unexpected intents detected
    if not scores and not pol_intents_expected:
        ms_names = {ms.basename for ms in mses}
        longmsg = f'No polarization calibrations found: {utils.commafy(sorted(ms_names), False)}'
        shortmsg = 'No polarization calibrators'
        origin = pqa.QAOrigin(metric_name='score_polintents',
                              metric_score=1.0,
                              metric_units='MS score based on presence of polarisation data')
        score = pqa.QAScore(1.0, longmsg=longmsg, shortmsg=shortmsg, origin=origin,
                            weblog_location=pqa.WebLogLocation.ACCORDION,
                            applies_to=pqa.TargetDataSelection(vis=ms_names))
        scores.append(score)

    return scores


@log_qa
def score_samecalobjects(recipe_name: str, mses: List[domain.MeasurementSet]) -> List[pqa.QAScore]:
    """
        Check if BP/Phcal/Ampcal are all the same object and score appropriately
    """
    alma_recipes = {'hifa_cal', 'hifa_calimage', 'hifa_calsurvey', 'hifa"image', 'hifa_polcal', 'hifa_polcalimage'}

    # Sort to ensure presentation consistency
    mses = sorted(mses, key=lambda ms: ms.basename)

    # We are just considering ALMA recipes.   True if an ALMA recipe, false if not
    alma_recipes_expected = recipe_name in alma_recipes

    # holds the final list of QA scores
    scores: List[pqa.QAScore] = []

    if alma_recipes_expected:
        for ms in mses:
            # Get list of calibrator names
            calfields = ms.get_fields(intent='AMPLITUDE,PHASE,BANDPASS')
            calfieldnames = [field.name for field in calfields]

            # Check for any duplicate names in the list of calibrator field names
            # samefieldnames = all(element == calfieldnames[0] for element in calfieldnames)
            samefieldnames = any(calfieldnames.count(x) > 1 for x in calfieldnames)
            if samefieldnames:
                scorevalue = 0.3
                msg = "Some calibrators are the same object."
            else:
                scorevalue = 1.0
                msg = "Calibrators are different objects."

            origin = pqa.QAOrigin(metric_name='score_samecalobjects',
                                  metric_score=scorevalue,
                                  metric_units='samecalobjects')

            score = pqa.QAScore(scorevalue, longmsg=msg, shortmsg=msg, origin=origin)

            scores.append(score)

    return scores


@log_qa
def score_missing_intents(mses, array_type='ALMA_12m'):
    """
    Score a MeasurementSet object based on the presence of certain
    observing intents.
    """
    # Required calibration intents. Warnings will be raised for any
    # measurement sets missing these intents
    score = 1.0
    if array_type == 'ALMA_TP':
        score_map = {'ATMOSPHERE': -1.0}
    elif array_type == 'VLA':
        score_map = {
            'PHASE': -1.0,
            # 'FLUX': -1.0,
            # CALIBRATE_FLUX and CALIBRATE_AMPLITUDE are both associated to 'AMPLITUDE'
            'AMPLITUDE': -1.0
        }
    else:
        score_map = {
            'PHASE': -0.7,
            'BANDPASS': -0.7,
            'AMPLITUDE': -0.7
        }

    required = set(score_map.keys())

    num_mses = len(mses)
    all_ok = True
    complaints = []

    # hold names of MSes this QA will be applicable to
    applies_to = set()

    # analyse each MS
    for ms in mses:
        # do we have the necessary calibrators?
        if not required.issubset(ms.intents):
            all_ok = False
            missing = required.difference(ms.intents)
            for m in missing:
                score += (score_map[m] / num_mses)

            longmsg = ('%s is missing %s calibration intents'
                       '' % (ms.basename, utils.commafy(missing, False)))
            complaints.append(longmsg)

            applies_to.add(ms.basename)

    if all_ok:
        longmsg = ('All required calibration intents were found in '
                   '%s.' % utils.commafy([ms.basename for ms in mses], False))
        shortmsg = 'All calibrators found'
        applies_to = {ms.basename for ms in mses}
    else:
        longmsg = '%s.' % utils.commafy(complaints, False)
        shortmsg = 'Calibrators missing'

    origin = pqa.QAOrigin(metric_name='score_missing_intents',
                          metric_score=score,
                          metric_units='Score based on missing calibration intents')

    return pqa.QAScore(
        max(0.0, score), longmsg=longmsg, shortmsg=shortmsg, origin=origin,
        applies_to=pqa.TargetDataSelection(vis=applies_to)
    )


@log_qa
def score_ephemeris_coordinates(mses):

    """
    Score a MeasurementSet object based on the presence of possible
    ephemeris coordinates.
    """

    score = 1.0

    num_mses = len(mses)
    all_ok = True
    complaints = []
    zero_direction = casa_tools.measures.direction('j2000', '0.0deg', '0.0deg')
    zero_ra = casa_tools.quanta.formxxx(zero_direction['m0'], format='hms', prec=3)
    zero_dec = casa_tools.quanta.formxxx(zero_direction['m1'], format='dms', prec=2)

    applies_to = set()

    # analyse each MS
    for ms in mses:
        # Examine each source
        for source in ms.sources:
            if source.ra == zero_ra and source.dec == zero_dec:
                all_ok = False
                score += (-1.0 / num_mses)
                longmsg = ('Suspicious source coordinates for  %s in %s. Check whether position of '
                           '00:00:00.0+00:00:00.0 is valid.' % (source.name, ms.basename))
                complaints.append(longmsg)
                applies_to.add(ms.basename)

    if all_ok:
        longmsg = ('All source coordinates OK in '
                   '%s.' % utils.commafy([ms.basename for ms in mses], False))
        shortmsg = 'All source coordinates OK'
        applies_to = {ms.basename for ms in mses}
    else:
        longmsg = '%s.' % utils.commafy(complaints, False)
        shortmsg = 'Suspicious source coordinates'

    origin = pqa.QAOrigin(metric_name='score_ephemeris_coordinates',
                          metric_score=score,
                          metric_units='Score based on presence of ephemeris coordinates')

    return pqa.QAScore(
        max(0.0, score), longmsg=longmsg, shortmsg=shortmsg, origin=origin,
        applies_to=pqa.TargetDataSelection(vis=applies_to)
    )


@log_qa
def score_online_shadow_template_agents(ms, summaries):
    """
    Get a score for the fraction of data flagged by online, shadow, and template agents.

    0 < score < 1 === 60% < frac_flagged < 5%
    """
    score = score_data_flagged_by_agents(ms, summaries, 0.05, 0.6,
                                         agents=['online', 'shadow', 'qa0', 'qa2', 'before', 'template'])

    new_origin = pqa.QAOrigin(metric_name='score_online_shadow_template_agents',
                              metric_score=score.origin.metric_score,
                              metric_units='Fraction of data newly flagged by online, shadow, and template agents')
    score.origin = new_origin

    return score


@log_qa
def score_lowtrans_flagcmds(ms, result):
    """
    Get a score for data flagged by the low transmission agent.

    Heuristic from PIPE-624: search for SpW(s) flagged for low transmission,
    and set score to:
    * 1 if no SpWs are flagged.
    * red warning threshold if the representative SpW is flagged, or otherwise,
    * blue suboptimal threshold if any non-representative SpW is flagged.
    """
    # Search in flag commands for SpW(s) flagged for low transmission.
    spws = []
    flagcmds = [f for f in result.flagcmds() if "low_transmission" in f]
    for flagcmd in flagcmds:
        match = re.search(r"spw='(\d*)'", flagcmd)
        if match:
            spws.append(int(match.group(1)))

    # If successful in finding SpWs that were flagged for low transmission,
    # then create a score that depends on whether the representative SpW was
    # among those flagged.
    if spws:
        # Get representative SpW for MS.
        _, rspw = ms.get_representative_source_spw()
        if rspw in spws:
            score = rutils.SCORE_THRESHOLD_ERROR
            longmsg = f"Representative SpW {rspw} flagged for low transmission"
            shortmsg = f"Representative SpW flagged for low transmission"
        else:
            score = rutils.SCORE_THRESHOLD_SUBOPTIMAL
            longmsg = f"Non-representative SpW(s) {', '.join(str(s) for s in spws)} flagged for low transmission"
            shortmsg = f"Non-representative SpW(s) flagged for low transmission"
    else:
        score = 1.0
        longmsg = "No SpW(s) flagged for low transmission"
        shortmsg = "No SpW(s) flagged for low transmission"

    origin = pqa.QAOrigin(metric_name='score_lowtrans',
                          metric_score=score,
                          metric_units='SpW(s) flagged by low transmission agent.')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_vla_agents(ms, summaries):
    """
    Get a score for the fraction of data flagged by online, shadow, and template agents.

    0 < score < 1 === 60% < frac_flagged < 5%
    """
    score = score_vla_science_data_flagged_by_agents(ms, summaries, 0.05, 0.6,
                                                     ['online', 'template', 'autocorr', 'edgespw',
                                                      'clip', 'quack', 'baseband'])

    new_origin = pqa.QAOrigin(metric_name='score_vla_agents',
                              metric_score=score.origin.metric_score,
                              metric_units='Fraction of data newly flagged by online, shadow, and template agents')
    score.origin = new_origin

    return score


@log_qa
def score_applycal_agents(ms, summaries):
    """
    Get a score for the fraction of data flagged by applycal agents.

    0 < score < 1 === 60% < frac_flagged < 5%
    """
    agents = ['applycal']
    intents = ['TARGET']

    # Get score for 'applycal' agent and 'TARGET' intent.
    score = score_data_flagged_by_agents(ms, summaries, 0.05, 0.6, agents=agents, intents=intents)
    perc_flagged = 100. * score.origin.metric_score

    # Get score for all agents (total) for 'TARGET' intent.
    dummy_score = score_data_flagged_by_agents(ms, summaries, 0, 1, intents=['TARGET'])
    total_perc_flagged = 100. * (1. - dummy_score.score)

    # Recreate the long message from the applycal score to also mention the total
    # percentage flagged.
    longmsg = ("For {}, intent(s): {}, {:.2f}% of the data was newly flagged by {} flagging agents, for a total of"
               " {:.2f}% flagged.".format(ms.basename, utils.commafy(intents, quotes=False), perc_flagged,
                                          utils.commafy(agents, quotes=False), total_perc_flagged))
    score.longmsg = longmsg

    # Update origin.
    new_origin = pqa.QAOrigin(metric_name='score_applycal_agents',
                              metric_score=score.origin.metric_score,
                              metric_units=score.origin.metric_units)
    score.origin = new_origin

    return score


@log_qa
def score_total_data_flagged(filename, summaries):
    """
    Calculate a score for the flagging task based on the total fraction of
    data flagged.

    0%-5% flagged   -> 1
    5%-50% flagged  -> 0.5
    50-100% flagged -> 0
    """
    # Calculate fraction of flagged data.
    frac_flagged = calc_frac_total_flagged(summaries)

    # Convert fraction of flagged data into a score.
    if frac_flagged > 0.5:
        score = 0
    else:
        score = linear_score(frac_flagged, 0.05, 0.5, 1.0, 0.5)

    # Set score messages and origin.
    percent = 100.0 * frac_flagged
    longmsg = '%0.2f%% of data in %s was flagged' % (percent, filename)
    shortmsg = '%0.2f%% data flagged' % percent

    origin = pqa.QAOrigin(metric_name='score_total_data_flagged',
                          metric_score=frac_flagged,
                          metric_units='Total fraction of data that is flagged')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=os.path.basename(filename), origin=origin)


@log_qa
def score_total_data_flagged_vla(filename, summaries):
    """
    Calculate a score for the flagging task based on the total fraction of
    data flagged.

    0%-5% flagged   -> 1
    5%-60% flagged  -> 1 to 0
    60-100% flagged -> 0
    """
    # Calculate fraction of flagged data.
    frac_flagged = calc_frac_newly_flagged(summaries)

    # Convert fraction of flagged data into a score.
    if frac_flagged > 0.6:
        score = 0
    else:
        score = linear_score(frac_flagged, 0.05, 0.6, 1.0, 0.0)

    # Set score messages and origin.
    percent = 100.0 * frac_flagged
    longmsg = '%0.2f%% of data in %s was flagged' % (percent, filename)
    shortmsg = '%0.2f%% data flagged' % percent

    origin = pqa.QAOrigin(metric_name='score_total_data_flagged_vla',
                          metric_score=frac_flagged,
                          metric_units='Total fraction of VLA data that is flagged')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=os.path.basename(filename), origin=origin)


@log_qa
def score_total_data_flagged_vla_bandpass(filename, frac_flagged):
    """
    Calculate a score for the flagging task based on the data flagged in the bandpass table.

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

    origin = pqa.QAOrigin(metric_name='score_total_data_flagged_vla_bandpass',
                          metric_score=frac_flagged,
                          metric_units='Total fraction of VLA data that is flagged in the caltable')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=os.path.basename(filename), origin=origin)


@log_qa
def score_flagged_vla_baddef(amp_collection, phase_collection, num_antennas):
    """
    Calculate a score for the flagging task based on the number of antennas flagged.

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
    origin = pqa.QAOrigin(metric_name='score_flagged_vla_baddef',
                          metric_score=frac_flagged,
                          metric_units='Fraction of VLA antennas flagged by hifv_flagbaddef')
    if 0 == frac_flagged:
        return pqa.QAScore(1, longmsg='No antennas flagged', shortmsg='No antennas flagged', origin=origin)
    else:
        # Convert fraction of flagged data into a score.
        score = linear_score(frac_flagged, 0.0, 0.3, 1.0, 0.0)
        # Set score messages and origin.
        percent = 100.0 * frac_flagged
        longmsg = "{:d} of {:d} ({:0.2f}%) antennas affected and some of their spws are flagged" \
                  "".format(num_affected_antennas, num_antennas, percent)
        shortmsg = "{:0.2f}% antennas affected".format(percent)
        return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


def countbaddelays(m, delaytable, delaymax):
    """
    Args:
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
            tbspw = tb.query(query='SPECTRAL_WINDOW_ID==' + str(ispw), name='byspw')
            ants = np.unique(tbspw.getcol('ANTENNA1'))
            for iant in ants:
                tbant = tbspw.query(query='ANTENNA1==' + str(iant), name='byant')
                absdel = np.absolute(tbant.getcol('FPARAM'))
                if np.max(absdel) > delaymax:
                    antname = m.get_antenna(iant)[0].name
                    delaydict[antname].append((absdel > delaymax).sum())
                    LOG.info('Spw=' + str(ispw) + ' Ant=' + antname
                             + '  Delays greater than 200 ns ='
                             + str((absdel > delaymax).sum()))
                tbant.close()
            tbspw.close()

    return delaydict


@log_qa
def score_total_data_vla_delay(filename, m):
    """
    Use a filename of a delay (K-type) calibration table
    Calculate a score for antennas with a delay > 200 ns
    For each antenna with delays > 200 ns, reduce score by 0.1
    """

    with casa_tools.TableReader(filename) as tb:
        fpar = tb.getcol('FPARAM')
        delays = np.abs(fpar)  # Units of nanoseconds
        maxdelay = np.max(delays)

    if maxdelay < 200.0:
        score = 1.0
    else:
        # For each antenna with a delay > 200.0 ns, deduct 0.1 from the score
        delaydict = countbaddelays(m, filename, 200.0)
        count = len(delaydict)
        score = 1.0 - (0.1 * count)
    if score < 0.0:
        score = 0.0

    # Set score message and origin
    longmsg = 'Max delay is {!s} ns'.format(str(maxdelay))
    shortmsg = longmsg

    origin = pqa.QAOrigin(metric_name='score_total_data_vla_delay',
                          metric_score=score,
                          metric_units='Delays that exceed 200 ns')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=os.path.basename(filename), origin=origin)


@log_qa
def score_vla_flux_residual_rms(rmsmeanvalues):
    """
    Take the RMS values of the residuals.
    Input is a list of tuples with (rms, mean, count) per sources
    """

    scores = []
    rmsvalues = []
    counts = []
    for rms, mean, count in rmsmeanvalues:
        sourcescore = 1.0 - (0.01 * count)
        rmsvalues.append(rms)
        counts.append(float(count))

        if sourcescore < 0.0:
            sourcescore = 0.0

        scores.append(sourcescore)

    countfractions = np.array(counts) / np.sum(counts)

    # Weighted average per sources
    try:
        score = np.average(scores, weights=countfractions)
    except Exception as e:
        score = 0.0

    if score < 0.0:
        score = 0.0

    # Set score message and origin
    try:
        longmsg = 'Max rms of the residuals is {!s}'.format(np.max(rmsvalues))
    except Exception as e:
        longmsg = 'No max rms.'
    shortmsg = longmsg

    origin = pqa.QAOrigin(metric_name='score_vla_flux_residual_rms',
                          metric_score=score,
                          metric_units='rms values that exceed 0.01')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_fraction_newly_flagged(filename, summaries, vis):
    """
    Calculate a score for the flagging task based on the fraction of
    data newly flagged.

    0%-5% flagged   -> 1
    5%-50% flagged  -> 0.5
    50-100% flagged -> 0
    """
    # Calculate fraction of flagged data.
    frac_flagged = calc_frac_newly_flagged(summaries)

    # Convert fraction of flagged data into a score.
    if frac_flagged > 0.5:
        score = 0
    else:
        score = linear_score(frac_flagged, 0.05, 0.5, 1.0, 0.5)

    # Set score messages and origin.
    percent = 100.0 * frac_flagged
    longmsg = '%0.2f%% of data in %s was newly flagged' % (percent, filename)
    shortmsg = '%0.2f%% data flagged' % percent

    origin = pqa.QAOrigin(metric_name='score_fraction_newly_flagged',
                          metric_score=frac_flagged,
                          metric_units='Fraction of data that is newly flagged')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=os.path.basename(vis), origin=origin)


@log_qa
def linear_score_fraction_newly_flagged(filename, summaries, vis):
    """
    Calculate a score for the flagging task based on the fraction of
    data newly flagged.

    fraction flagged   -> score
    """
    # Calculate fraction of flagged data.
    frac_flagged = calc_frac_newly_flagged(summaries)

    # Convert fraction of flagged data into a score.
    score = 1.0 - frac_flagged

    # Set score messages and origin.
    percent = 100.0 * frac_flagged
    longmsg = '%0.2f%% of data in %s was newly flagged' % (percent, filename)
    shortmsg = '%0.2f%% data flagged' % percent

    origin = pqa.QAOrigin(metric_name='linear_score_fraction_newly_flagged',
                          metric_score=frac_flagged,
                          metric_units='Fraction of data that is newly flagged')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=os.path.basename(vis), origin=origin)


@log_qa
def linear_score_fraction_unflagged_newly_flagged_for_intent(ms, summaries, intent):
    """
    Calculate a score for the flagging task based on the fraction of unflagged
    data for scans belonging to specified intent that got newly flagged.

    If no unflagged data was found in the before summary, then return a score
    of 0.0.
    """

    # Identify scan IDs belonging to intent.
    scanids = [str(scan.id) for scan in ms.get_scans(scan_intent=intent)]

    # Calculate flags for scans belonging to intent.
    agent_stats = calc_flags_per_agent(summaries, scanids=scanids)

    # Calculate counts of unflagged data.
    unflaggedcount = agent_stats[0].total - agent_stats[0].flagged

    # If the "before" summary had unflagged data, then proceed to compute
    # the fraction fo unflagged data that got newly flagged.
    if unflaggedcount > 0:
        frac_flagged = functools.reduce(operator.add,
                                        [float(s.flagged)/unflaggedcount for s in agent_stats[1:]], 0)

        score = 1.0 - frac_flagged
        percent = 100.0 * frac_flagged
        longmsg = '{:0.2f}% of unflagged data with intent {} in {} was newly ' \
                  'flagged.'.format(percent, intent, ms.basename)
        shortmsg = '{:0.2f}% unflagged data flagged.'.format(percent)

        origin = pqa.QAOrigin(metric_name='linear_score_fraction_unflagged_newly_flagged_for_intent',
                              metric_score=frac_flagged,
                              metric_units='Fraction of unflagged data for intent '
                                           '{} that is newly flagged'.format(intent))
    # If no unflagged data was found at the start, return score of 0.
    else:
        score = 0.0
        longmsg = 'No unflagged data with intent {} found in {}.'.format(intent, ms.basename)
        shortmsg = 'No unflagged data.'
        origin = pqa.QAOrigin(metric_name='linear_score_fraction_unflagged_newly_flagged_for_intent',
                              metric_score=False,
                              metric_units='Presence of unflagged data.')

    # Append extra warning to QA message if score falls at-or-below the "warning" threshold.
    if score <= rutils.SCORE_THRESHOLD_WARNING:
        longmsg += ' Please investigate!'
        shortmsg += ' Please investigate!'

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_contiguous_session(mses, tolerance=datetime.timedelta(hours=1)):
    """
    Check whether measurement sets are contiguous in time.
    """
    # only need to check when given multiple measurement sets
    if len(mses) < 2:
        origin = pqa.QAOrigin(metric_name='score_contiguous_session',
                              metric_score=0,
                              metric_units='Non-contiguous measurement sets present')
        return pqa.QAScore(1.0,
                           longmsg='%s forms one continuous observing session.' % mses[0].basename,
                           shortmsg='Unbroken observing session',
                           vis=mses[0].basename,
                           origin=origin)

    # reorder MSes by start time
    by_start = sorted(mses,
                      key=lambda m: utils.get_epoch_as_datetime(m.start_time))

    # create an interval for each one, including our tolerance
    intervals = []
    for ms in by_start:
        start = utils.get_epoch_as_datetime(ms.start_time)
        end = utils.get_epoch_as_datetime(ms.end_time)
        interval = measures.TimeInterval(start - tolerance, end + tolerance)
        intervals.append(interval)

    # check whether the intervals overlap
    bad_mses = []
    for i, (interval1, interval2) in enumerate(zip(intervals[0:-1],
                                                   intervals[1:])):
        if not interval1.overlaps(interval2):
            bad_mses.append(utils.commafy([by_start[i].basename,
                                           by_start[i+1].basename]))

    if bad_mses:
        basenames = utils.commafy(bad_mses, False)
        longmsg = ('Measurement sets %s are not contiguous. They may be '
                   'miscalibrated as a result.' % basenames)
        shortmsg = 'Gaps between observations'
        score = 0.5
    else:
        basenames = utils.commafy([ms.basename for ms in mses])
        longmsg = ('Measurement sets %s are contiguous.' % basenames)
        shortmsg = 'Unbroken observing session'
        score = 1.0

    origin = pqa.QAOrigin(metric_name='score_contiguous_session',
                          metric_score=not bool(bad_mses),
                          metric_units='Non-contiguous measurement sets present')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_wvrgcal(ms_name, wvr_score):
    if wvr_score < 1.0:
        score = 0
    else:
        score = linear_score(wvr_score, 1.0, 2.0, 0.5, 1.0)

    longmsg = 'RMS improvement was %0.2f for %s' % (wvr_score, ms_name)
    shortmsg = '%0.2fx improvement' % wvr_score

    origin = pqa.QAOrigin(metric_name='score_wvrgcal',
                          metric_score=wvr_score,
                          metric_units='Phase RMS improvement after applying WVR correction')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=os.path.basename(ms_name), origin=origin)


@log_qa
def score_sdtotal_data_flagged(label, frac_flagged):
    """
    Calculate a score for the flagging task based on the total fraction of
    data flagged.

    0%-5% flagged   -> 1
    5%-50% flagged  -> 0.5
    50-100% flagged -> 0
    """
    if frac_flagged > 0.5:
        score = 0
    else:
        score = linear_score(frac_flagged, 0.05, 0.5, 1.0, 0.5)

    percent = 100.0 * frac_flagged
    longmsg = '%0.2f%% of data in %s was newly flagged' % (percent, label)
    shortmsg = '%0.2f%% data flagged' % percent

    origin = pqa.QAOrigin(metric_name='score_sdtotal_data_flagged',
                          metric_score=frac_flagged,
                          metric_units='Fraction of data newly flagged')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=None, origin=origin)


@log_qa
def score_sdtotal_data_flagged_old(name, ant, spw, pol, frac_flagged, field=None):
    """
    Calculate a score for the flagging task based on the total fraction of
    data flagged.

    0%-5% flagged   -> 1
    5%-50% flagged  -> 0.5
    50-100% flagged -> 0
    """
    if frac_flagged > 0.5:
        score = 0
    else:
        score = linear_score(frac_flagged, 0.05, 0.5, 1.0, 0.5)

    percent = 100.0 * frac_flagged
    if field is None:
        longmsg = '%0.2f%% of data in %s (Ant=%s, SPW=%d, Pol=%d) was flagged' % (percent, name, ant, spw, pol)
    else:
        longmsg = ('%0.2f%% of data in %s (Ant=%s, Field=%s, SPW=%d, Pol=%s) was '
                   'flagged' % (percent, name, ant, field, spw, pol))
    shortmsg = '%0.2f%% data flagged' % percent

    origin = pqa.QAOrigin(metric_name='score_sdtotal_data_flagged_old',
                          metric_score=frac_flagged,
                          metric_units='Fraction of data newly flagged')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=os.path.basename(name), origin=origin)


@log_qa
def score_tsysspwmap(ms, unmappedspws):
    """
    Score is equal to the fraction of unmapped windows
    """

    if len(unmappedspws) <= 0:
        score = 1.0
        longmsg = 'Tsys spw map is complete for %s ' % ms.basename
        shortmsg = 'Tsys spw map is complete'
    else:
        nscispws = len([spw.id for spw in ms.get_spectral_windows(science_windows_only=True)])
        if nscispws <= 0:
            score = 0.0
        else:
            score = float(nscispws - len(unmappedspws)) / float(nscispws)
        longmsg = 'Tsys spw map is incomplete for %s science window%s ' % (ms.basename,
                                                                           utils.commafy(unmappedspws, False, 's'))
        shortmsg = 'Tsys spw map is incomplete'

    origin = pqa.QAOrigin(metric_name='score_tsysspwmap',
                          metric_score=score,
                          metric_units='Fraction of unmapped Tsys windows')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_setjy_measurements(ms, reqfields, reqintents, reqspws, measurements):
    """
    Score is equal to the ratio of the number of actual flux
    measurements to expected number of flux measurements
    """

    # Expected fields
    scifields = {field for field in ms.get_fields(reqfields, intent=reqintents)}

    # Expected science windows
    scispws = {spw.id for spw in ms.get_spectral_windows(reqspws, science_windows_only=True)}

    # Loop over the expected fields
    nexpected = 0
    for scifield in scifields:
        validspws = {spw.id for spw in scifield.valid_spws}
        nexpected += len(validspws.intersection(scispws))

    # Loop over the measurements
    nmeasured = 0
    for value in measurements.values():
        # Loop over the flux measurements
        nmeasured += len(value)

    # Compute score
    if nexpected == 0:
        score = 0.0
        longmsg = 'No flux calibrators for %s ' % ms.basename
        shortmsg = 'No flux calibrators'
    elif nmeasured == 0:
        score = 0.0
        longmsg = 'No flux measurements for %s ' % ms.basename
        shortmsg = 'No flux measurements'
    elif nexpected == nmeasured:
        score = 1.0
        longmsg = 'All expected flux calibrator measurements present for %s ' % ms.basename
        shortmsg = 'All expected flux calibrator measurements present'
    elif nmeasured < nexpected:
        score = float(nmeasured) / float(nexpected)
        longmsg = 'Missing flux calibrator measurements for %s %d/%d ' % (ms.basename, nmeasured, nexpected)
        shortmsg = 'Missing flux calibrator measurements'
    else:
        score = 0.0
        longmsg = 'Too many flux calibrator measurements for %s %d/%d' % (ms.basename, nmeasured, nexpected)
        shortmsg = 'Too many flux measurements'

    origin = pqa.QAOrigin(metric_name='score_setjy_measurements',
                          metric_score=score,
                          metric_units='Ratio of number of flux measurements to number expected')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_number_antenna_offsets(ms, offsets):
    """
    Score is 1.0 if no antenna needed a position offset correction, and
    set to the "suboptimal" threshold if at least one antenna needed a
    correction.
    """
    nant_with_offsets = len(offsets) // 3

    if nant_with_offsets == 0:
        score = 1.0
        longmsg = 'No antenna position offsets for %s ' % ms.basename
        shortmsg = 'No antenna position offsets'
    else:
        # CAS-8877: if at least 1 antenna needed correction, then set the score
        # to the "suboptimal" threshold.
        score = rutils.SCORE_THRESHOLD_SUBOPTIMAL
        longmsg = '%d nonzero antenna position offsets for %s ' % (nant_with_offsets, ms.basename)
        shortmsg = 'Nonzero antenna position offsets'

    origin = pqa.QAOrigin(metric_name='score_number_antenna_offsets',
                          metric_score=nant_with_offsets,
                          metric_units='Number of antennas requiring position offset correction')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_missing_derived_fluxes(ms, reqfields, reqintents, measurements):
    """
    Score is equal to the ratio of actual flux
    measurement to expected flux measurements
    """
    # Expected fields
    scifields = {field for field in ms.get_fields(reqfields, intent=reqintents)}

    # Expected science windows
    scispws = {spw.id for spw in ms.get_spectral_windows(science_windows_only=True)}

    # Loop over the expected fields
    nexpected = 0
    for scifield in scifields:
        validspws = {spw.id for spw in scifield.valid_spws}
        nexpected += len(validspws.intersection(scispws))

    # Loop over measurements
    nmeasured = 0
    for key, value in measurements.items():
        # Loop over the flux measurements
        for flux in value:
            fluxjy = getattr(flux, 'I').to_units(measures.FluxDensityUnits.JANSKY)
            uncjy = getattr(flux.uncertainty, 'I').to_units(measures.FluxDensityUnits.JANSKY)
            if fluxjy <= 0.0 or uncjy <= 0.0:
                continue
            nmeasured += 1

    # Compute score
    if nexpected == 0:
        score = 0.0
        longmsg = 'No secondary calibrators for %s ' % ms.basename
        shortmsg = 'No secondary calibrators'
    elif nmeasured == 0:
        score = 0.0
        longmsg = 'No derived fluxes for %s ' % ms.basename
        shortmsg = 'No derived fluxes'
    elif nexpected == nmeasured:
        score = 1.0
        longmsg = 'All expected derived fluxes present for %s ' % ms.basename
        shortmsg = 'All expected derived fluxes present'
    elif nmeasured < nexpected:
        score = float(nmeasured) / float(nexpected)
        longmsg = 'Missing derived fluxes for %s %d/%d' % (ms.basename, nmeasured, nexpected)
        shortmsg = 'Missing derived fluxes'
    else:
        score = 0.0
        longmsg = 'Extra derived fluxes for %s %d/%d' % (ms.basename, nmeasured, nexpected)
        shortmsg = 'Extra derived fluxes'

    origin = pqa.QAOrigin(metric_name='score_missing_derived_fluxes',
                          metric_score=score,
                          metric_units='Ratio of number of flux measurements to number expected')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_refspw_mapping_fraction(ms, ref_spwmap):
    """
    Compute the fraction of science spws that have not been
    mapped to other windows.
    """
    if ref_spwmap == [-1]:
        score = 1.0
        longmsg = 'No mapped science spws for %s ' % ms.basename
        shortmsg = 'No mapped science spws'

        origin = pqa.QAOrigin(metric_name='score_refspw_mapping_fraction',
                              metric_score=0,
                              metric_units='Number of unmapped science spws')
    else:
        # Expected science windows
        scispws = {spw.id for spw in ms.get_spectral_windows(science_windows_only=True)}
        nexpected = len(scispws)

        nunmapped = 0
        for spwid in scispws:
            if spwid == ref_spwmap[spwid]:
                nunmapped += 1

        if nunmapped >= nexpected:
            score = 1.0
            longmsg = 'No mapped science spws for %s ' % ms.basename
            shortmsg = 'No mapped science spws'
        else:
            # Replace the previous score with a warning
            score = rutils.SCORE_THRESHOLD_WARNING
            longmsg = 'There are %d mapped science spws for %s ' % (nexpected - nunmapped, ms.basename)
            shortmsg = 'There are mapped science spws'

        origin = pqa.QAOrigin(metric_name='score_refspw_mapping_fraction',
                              metric_score=nunmapped,
                              metric_units='Number of unmapped science spws')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_combine_spwmapping(ms, intent, field, spwmapping):
    """
    Evaluate whether or not a spw mapping is using combine.
    If not, then set score to 1. If so, then set score to the sub-optimal
    threshold (for blue info message).
    """
    if spwmapping.combine:
        score = rutils.SCORE_THRESHOLD_SUBOPTIMAL
        longmsg = f'Using combined spw mapping for {ms.basename}, intent={intent}, field={field}'
        shortmsg = 'Using combined spw mapping'
    else:
        score = 1.0
        longmsg = f'No combined spw mapping for {ms.basename}, intent={intent}, field={field}'
        shortmsg = 'No combined spw mapping'

    origin = pqa.QAOrigin(metric_name='score_check_phaseup_combine_mapping',
                          metric_score=spwmapping.combine,
                          metric_units='Using combined spw mapping')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_phaseup_mapping_fraction(ms, intent, field, spwmapping):
    """
    Compute the fraction of science spws that have not been
    mapped to other probably wider windows.
    """
    if not spwmapping.spwmap:
        nunmapped = len([spw for spw in ms.get_spectral_windows(science_windows_only=True)])
        score = 1.0
        longmsg = f'No spw mapping for {ms.basename}, intent={intent}, field={field}'
        shortmsg = 'No spw mapping'
    elif spwmapping.combine:
        nunmapped = 0
        score = rutils.SCORE_THRESHOLD_WARNING
        longmsg = f'Combined spw mapping for {ms.basename}, intent={intent}, field={field}'
        shortmsg = 'Combined spw mapping'
    else:
        # Expected science windows
        scispws = [spw for spw in ms.get_spectral_windows(science_windows_only=True)]
        scispwids = [spw.id for spw in ms.get_spectral_windows(science_windows_only=True)]
        nexpected = len(scispwids)

        nunmapped = 0
        samesideband = True
        for spwid, scispw in zip(scispwids, scispws):
            if spwid == spwmapping.spwmap[spwid]:
                nunmapped += 1
            else:
                if scispw.sideband != ms.get_spectral_window(spwmapping.spwmap[spwid]).sideband:
                    samesideband = False

        if nunmapped >= nexpected:
            score = 1.0
            longmsg = f'No spw mapping for {ms.basename}, intent={intent}, field={field}'
            shortmsg = 'No spw mapping'
        else:
            # Replace the previous score with a warning
            if samesideband is True:
                score = rutils.SCORE_THRESHOLD_SUBOPTIMAL
                longmsg = f'Spw mapping within sidebands for {ms.basename}, intent={intent}, field={field}'
                shortmsg = 'Spw mapping within sidebands'
            else:
                score = rutils.SCORE_THRESHOLD_WARNING
                longmsg = f'Spw mapping across sidebands required for {ms.basename}, intent={intent}, field={field}'
                shortmsg = 'Spw mapping across sidebands'

    origin = pqa.QAOrigin(metric_name='score_phaseup_mapping_fraction',
                          metric_score=nunmapped,
                          metric_units='Number of unmapped science spws')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_phaseup_spw_median_snr_for_phase(ms, field, spw, median_snr, snr_threshold):
    """
    Score the median achieved SNR for a given phase calibrator field and SpW.
    Introduced for hifa_spwphaseup (PIPE-665).
    """
    if median_snr <= 0.3 * snr_threshold:
        score = rutils.SCORE_THRESHOLD_ERROR
        shortmsg = 'Low median SNR'
        longmsg = f'For {ms.basename}, field={field} (intent=PHASE), SpW={spw}, the median achieved SNR ({median_snr:.1f}) is <= 30% of the' \
                  f' phase SNR threshold ({snr_threshold:.1f}).'
    elif median_snr <= 0.5 * snr_threshold:
        score = rutils.SCORE_THRESHOLD_WARNING
        shortmsg = 'Low median SNR'
        longmsg = f'For {ms.basename}, field={field} (intent=PHASE), SpW={spw}, the median achieved SNR ({median_snr:.1f}) is <= 50% of the' \
                  f' phase SNR threshold ({snr_threshold:.1f}).'
    elif median_snr <= 0.75 * snr_threshold:
        score = rutils.SCORE_THRESHOLD_SUBOPTIMAL
        shortmsg = 'Low median SNR'
        longmsg = f'For {ms.basename}, field={field} (intent=PHASE), SpW={spw}, the median achieved SNR ({median_snr:.1f}) is <= 75% of the' \
                  f' phase SNR threshold ({snr_threshold:.1f}).'
    else:
        score = 1.0
        shortmsg = 'Median SNR is ok'
        longmsg = f'For {ms.basename}, field={field} (intent=PHASE), SpW={spw}, the median achieved SNR ({median_snr:.1f}) is > 75% of the' \
                  f' phase SNR threshold ({snr_threshold:.1f}).'

    origin = pqa.QAOrigin(metric_name='score_phaseup_spw_median_snr',
                          metric_score=median_snr,
                          metric_units='Median SNR')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_phaseup_spw_median_snr_for_check(ms, field, spw, median_snr, snr_threshold):
    """
    Score the median achieved SNR for a given check source field and SpW.
    Introduced for hifa_spwphaseup (PIPE-665).
    """
    if median_snr <= 0.3 * snr_threshold:
        score = 0.7
        shortmsg = 'Low median SNR'
        longmsg = f'For {ms.basename}, field={field} (intent=CHECK), SpW={spw}, the median achieved SNR ({median_snr:.1f}) is <= 30% of the' \
                  f' phase SNR threshold ({snr_threshold:.1f}).'
    elif median_snr <= 0.5 * snr_threshold:
        score = 0.8
        shortmsg = 'Low median SNR'
        longmsg = f'For {ms.basename}, field={field} (intent=CHECK), SpW={spw}, the median achieved SNR ({median_snr:.1f}) is <= 50% of the' \
                  f' phase SNR threshold ({snr_threshold:.1f}).'
    elif median_snr <= 0.75 * snr_threshold:
        score = 0.9
        shortmsg = 'Low median SNR'
        longmsg = f'For {ms.basename}, field={field} (intent=CHECK), SpW={spw}, the median achieved SNR ({median_snr:.1f}) is <= 75% of the' \
                  f' phase SNR threshold ({snr_threshold:.1f}).'
    else:
        score = 1.0
        shortmsg = 'Median SNR is ok'
        longmsg = f'For {ms.basename}, field={field} (intent=CHECK), SpW={spw}, the median achieved SNR ({median_snr:.1f}) is > 75% of the' \
                  f' phase SNR threshold ({snr_threshold:.1f}).'

    origin = pqa.QAOrigin(metric_name='score_phaseup_spw_median_snr',
                          metric_score=median_snr,
                          metric_units='Median SNR')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)

@log_qa
def score_missing_phaseup_snrs(ms, spwids, phsolints):
    """
    Score is the fraction of spws with phaseup SNR estimates
    """
    # Compute the number of expected and missing SNR measurements
    nexpected = len(spwids)
    missing_spws = []
    for i in range(len(spwids)):
        if not phsolints[i]:
            missing_spws.append(spwids[i])
    nmissing = len(missing_spws)

    if nexpected <= 0:
        score = 0.0
        longmsg = 'No phaseup SNR estimates for %s ' % ms.basename
        shortmsg = 'No phaseup SNR estimates'
    elif nmissing <= 0:
        score = 1.0
        longmsg = 'No missing phaseup SNR estimates for %s ' % ms.basename
        shortmsg = 'No missing phaseup SNR estimates'
    else:
        score = float(nexpected - nmissing) / nexpected
        longmsg = 'Missing phaseup SNR estimates for spws %s in %s ' % \
            (missing_spws, ms.basename)
        shortmsg = 'Missing phaseup SNR estimates'

    origin = pqa.QAOrigin(metric_name='score_missing_phaseup_snrs',
                          metric_score=nmissing,
                          metric_units='Number of spws with missing SNR measurements')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_poor_phaseup_solutions(ms, spwids, nphsolutions, min_nsolutions):
    """
    Score is the fraction of spws with poor phaseup solutions
    """
    # Compute the number of expected and poor SNR measurements
    nexpected = len(spwids)
    poor_spws = []
    for i in range(len(spwids)):
        if not nphsolutions[i]:
            poor_spws.append(spwids[i])
        elif nphsolutions[i] < min_nsolutions:
            poor_spws.append(spwids[i])
    npoor = len(poor_spws)

    if nexpected <= 0:
        score = 0.0
        longmsg = 'No phaseup solutions for %s ' % ms.basename
        shortmsg = 'No phaseup solutions'
    elif npoor <= 0:
        score = 1.0
        longmsg = 'No poorly determined phaseup solutions for %s ' % ms.basename
        shortmsg = 'No poorly determined phaseup solutions'
    else:
        score = float(nexpected - npoor) / nexpected
        longmsg = 'Poorly determined phaseup solutions for spws %s in %s ' % \
            (poor_spws, ms.basename)
        shortmsg = 'Poorly determined phaseup solutions'

    origin = pqa.QAOrigin(metric_name='score_poor_phaseup_solutions',
                          metric_score=npoor,
                          metric_units='Number of poor phaseup solutions')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_missing_bandpass_snrs(ms, spwids, bpsolints):
    """
    Score is the fraction of spws with bandpass SNR estimates
    """

    # Compute the number of expected and missing SNR measurements
    nexpected = len(spwids)
    missing_spws = []
    for i in range(len(spwids)):
        if not bpsolints[i]:
            missing_spws.append(spwids[i])
    nmissing = len(missing_spws)

    if nexpected <= 0:
        score = 0.0
        longmsg = 'No bandpass SNR estimates for %s ' % ms.basename
        shortmsg = 'No bandpass SNR estimates'
    elif nmissing <= 0:
        score = 1.0
        longmsg = 'No missing bandpass SNR estimates for %s ' % ms.basename
        shortmsg = 'No missing bandpass SNR estimates'
    else:
        score = float(nexpected - nmissing) / nexpected
        longmsg = 'Missing bandpass SNR estimates for spws %s in%s ' % \
            (missing_spws, ms.basename)
        shortmsg = 'Missing bandpass SNR estimates'

    origin = pqa.QAOrigin(metric_name='score_missing_bandpass_snrs',
                          metric_score=nmissing,
                          metric_units='Number of missing bandpass SNR estimates')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_poor_bandpass_solutions(ms, spwids, nbpsolutions, min_nsolutions):
    """
    Score is the fraction of spws with poor bandpass solutions
    """
    # Compute the number of expected and poor solutions
    nexpected = len(spwids)
    poor_spws = []
    for i in range(len(spwids)):
        if not nbpsolutions[i]:
            poor_spws.append(spwids[i])
        elif nbpsolutions[i] < min_nsolutions:
            poor_spws.append(spwids[i])
    npoor = len(poor_spws)

    if nexpected <= 0:
        score = 0.0
        longmsg = 'No bandpass solutions for %s ' % ms.basename
        shortmsg = 'No bandpass solutions'
    elif npoor <= 0:
        score = 1.0
        longmsg = 'No poorly determined bandpass solutions for %s ' % ms.basename
        shortmsg = 'No poorly determined bandpass solutions'
    else:
        score = float(nexpected - npoor) / nexpected
        longmsg = 'Poorly determined bandpass solutions for spws %s in %s ' % (poor_spws, ms.basename)
        shortmsg = 'Poorly determined bandpass solutions'

    origin = pqa.QAOrigin(metric_name='score_missing_bandpass_snrs',
                          metric_score=npoor,
                          metric_units='Number of poor bandpass solutions')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_missing_phase_snrs(ms, spwids, snrs):
    """
    Score is the fraction of spws with SNR estimates
    """
    # Compute the number of expected and missing SNR measurements
    nexpected = len(spwids)
    missing_spws = []
    for i in range(len(spwids)):
        if not snrs[i]:
            missing_spws.append(spwids[i])
    nmissing = len(missing_spws)

    if nexpected <= 0:
        score = 0.0
        longmsg = 'No gaincal SNR estimates for %s ' % ms.basename
        shortmsg = 'No gaincal SNR estimates'
    elif nmissing <= 0:
        score = 1.0
        longmsg = 'No missing gaincal SNR estimates for %s ' % ms.basename
        shortmsg = 'No missing gaincal SNR estimates'
    else:
        score = float(nexpected - nmissing) / nexpected
        longmsg = 'Missing gaincal SNR estimates for spws %s in %s ' % (missing_spws, ms.basename)
        shortmsg = 'Missing gaincal SNR estimates'

    origin = pqa.QAOrigin(metric_name='score_missing_phase_snrs',
                          metric_score=nmissing,
                          metric_units='Number of missing phase SNR estimates')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_poor_phase_snrs(ms, spwids, minsnr, snrs):
    """
    Score is the fraction of spws with poor snr estimates
    """
    # Compute the number of expected and poor solutions
    nexpected = len(spwids)
    poor_spws = []
    for i in range(len(spwids)):
        if not snrs[i]:
            poor_spws.append(spwids[i])
        elif snrs[i] < minsnr:
            poor_spws.append(spwids[i])
    npoor = len(poor_spws)

    if nexpected <= 0:
        score = 0.0
        longmsg = 'No gaincal SNR estimates for %s ' % \
            ms.basename
        shortmsg = 'No gaincal SNR estimates'
    elif npoor <= 0:
        score = 1.0
        longmsg = 'No low gaincal SNR estimates for %s ' % \
            ms.basename
        shortmsg = 'No low gaincal SNR estimates'
    else:
        score = float(nexpected - npoor) / nexpected
        longmsg = 'Low gaincal SNR estimates for spws %s in %s ' % \
            (poor_spws, ms.basename)
        shortmsg = 'Low gaincal SNR estimates'

    origin = pqa.QAOrigin(metric_name='score_poor_phase_snrs',
                          metric_score=npoor,
                          metric_units='Number of poor phase SNR estimates')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_derived_fluxes_snr(ms, measurements):
    """
    Score the SNR of the derived flux measurements.

    See PIPE-644 for latest description.

    Linearly scale QA score based on SNR value, where
      QA = 1.0 if SNR >= 26.25
      QA = 0.66 if SNR < 5.0
    and QA linearly scales from 0.66 to 1.0 between SNR 5 to 26.25.

    These QA and SNR threshold were chosen such that SNR values in the range of
    5-20 should map to QA scores in the range that will show as a blue
    "suboptimal" level QA message.
    """
    # Loop over measurements
    nmeasured = 0
    score = 0.0
    minscore = 1.0
    minsnr = None

    for value in measurements.values():
        # Loop over the flux measurements
        for flux in value:
            fluxjy = flux.I.to_units(measures.FluxDensityUnits.JANSKY)
            uncjy = flux.uncertainty.I.to_units(measures.FluxDensityUnits.JANSKY)
            if fluxjy <= 0.0 or uncjy <= 0.0:
                continue
            snr = fluxjy / uncjy
            minsnr = snr if minsnr is None else min(minsnr, snr)
            nmeasured += 1
            score1 = linear_score(float(snr), 5.0, 26.25, 0.66, 1.0)
            minscore = min(minscore, score1)
            score += score1

    if nmeasured > 0:
        score /= nmeasured

    if nmeasured == 0:
        score = 0.0
        longmsg = 'No derived fluxes for %s ' % ms.basename
        shortmsg = 'No derived fluxes'
    elif minscore >= 1.0:
        score = 1.0
        longmsg = 'No low SNR derived fluxes for %s ' % ms.basename
        shortmsg = 'No low SNR derived fluxes'
    else:
        longmsg = 'Low SNR derived fluxes for %s ' % ms.basename
        shortmsg = 'Low SNR derived fluxes'

    origin = pqa.QAOrigin(metric_name='score_derived_fluxes_snr',
                          metric_score=minsnr,
                          metric_units='Minimum SNR of derived flux measurement')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_path_exists(mspath, path, pathtype):
    """
    Score the existence of the path
        1.0 if it exist
        0.0 if it does not
    """
    if os.path.exists(path):
        score = 1.0
        longmsg = 'The %s file %s for %s was created' % (pathtype, os.path.basename(path), os.path.basename(mspath))
        shortmsg = 'The %s file was created' % pathtype
    else:
        score = 0.0
        longmsg = 'The %s file %s for %s was not created' % (pathtype, os.path.basename(path), os.path.basename(mspath))
        shortmsg = 'The %s file was not created' % pathtype

    origin = pqa.QAOrigin(metric_name='score_path_exists',
                          metric_score=bool(score),
                          metric_units='Path exists on disk')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_file_exists(filedir, filename, filetype):
    """
    Score the existence of a products file
        1.0 if it exists
        0.0 if it does not
    """
    if filename is None:
        score = 1.0
        longmsg = 'The %s file is undefined' % filetype
        shortmsg = 'The %s file is undefined' % filetype

        origin = pqa.QAOrigin(metric_name='score_file_exists',
                              metric_score=None,
                              metric_units='No %s file to check' % filetype)

        return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)

    file_path = os.path.join(filedir, os.path.basename(filename))
    if os.path.exists(file_path):
        score = 1.0
        longmsg = 'The %s file has been exported' % filetype
        shortmsg = 'The %s file has been exported' % filetype
    else:
        score = 0.0
        longmsg = 'The %s file %s does not exist' % (filetype, os.path.basename(filename))
        shortmsg = 'The %s file does not exist' % filetype

    origin = pqa.QAOrigin(metric_name='score_file_exists',
                          metric_score=bool(score),
                          metric_units='File exists on disk')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_mses_exist(filedir, visdict):
    """
    Score the existence of the flagging products files
        1.0 if they all exist
        n / nexpected if some of them exist
        0.0 if none exist
    """

    nexpected = len(visdict)
    nfiles = 0
    missing = []

    for visname in visdict:
        file_path = os.path.join(filedir, os.path.basename(visdict[visname]))
        if os.path.exists(file_path):
            nfiles += 1
        else:
            missing.append(os.path.basename(visdict[visname]))

    if nfiles <= 0:
        score = 0.0
        longmsg = 'Final ms files %s are missing' % (','.join(missing))
        shortmsg = 'Missing final ms files'
    elif nfiles < nexpected:
        score = float(nfiles) / float(nexpected)
        longmsg = 'Final ms files %s are missing' % (','.join(missing))
        shortmsg = 'Missing final ms files'
    else:
        score = 1.0
        longmsg = 'No missing final ms  files'
        shortmsg = 'No missing final ms files'

    origin = pqa.QAOrigin(metric_name='score_mses_exist',
                          metric_score=len(missing),
                          metric_units='Number of missing ms product files')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_flags_exist(filedir, visdict):
    """
    Score the existence of the flagging products files
        1.0 if they all exist
        n / nexpected if some of them exist
        0.0 if none exist
    """
    nexpected = len(visdict)
    nfiles = 0
    missing = []

    for visname in visdict:
        file_path = os.path.join(filedir, os.path.basename(visdict[visname][0]))
        if os.path.exists(file_path):
            nfiles += 1
        else:
            missing.append(os.path.basename(visdict[visname][0]))

    if nfiles <= 0:
        score = 0.0
        longmsg = 'Final flag version files %s are missing' % (','.join(missing))
        shortmsg = 'Missing final flags version files'
    elif nfiles < nexpected:
        score = float(nfiles) / float(nexpected)
        longmsg = 'Final flag version files %s are missing' % (','.join(missing))
        shortmsg = 'Missing final flags version files'
    else:
        score = 1.0
        longmsg = 'No missing final flag version files'
        shortmsg = 'No missing final flags version files'

    origin = pqa.QAOrigin(metric_name='score_flags_exist',
                          metric_score=len(missing),
                          metric_units='Number of missing flagging product files')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_flagging_view_exists(filename, result):
    """
    Assign a score of zero if the flagging view cannot be computed
    """

    # By default, assume no flagging views were found.
    score = 0.0
    longmsg = 'No flagging views for %s' % filename
    shortmsg = 'No flagging views'

    # Check if this is a flagging result for a single metric, where
    # the flagging view is stored directly in the result.
    try:
        view = result.view
        if view:
            score = 1.0
            longmsg = 'Flagging views exist for %s' % filename
            shortmsg = 'Flagging views exist'
    except AttributeError:
        pass

    # Check if this flagging results contains multiple metrics,
    # and look for flagging views among components.
    try:
        # Set score to 1 as soon as a single metric contains a
        # valid flagging view.
        for metricresult in result.components.values():
            view = metricresult.view
            if view:
                score = 1.0
                longmsg = 'Flagging views exist for %s' % filename
                shortmsg = 'Flagging views exist'
    except AttributeError:
        pass

    origin = pqa.QAOrigin(metric_name='score_flagging_view_exists',
                          metric_score=bool(score),
                          metric_units='Presence of flagging view')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=filename, origin=origin)


@log_qa
def score_applycmds_exist(filedir, visdict):
    """
    Score the existence of the apply commands products files
        1.0 if they all exist
        n / nexpected if some of them exist
        0.0 if none exist
    """
    nexpected = len(visdict)
    nfiles = 0
    missing = []

    for visname in visdict:
        file_path = os.path.join(filedir, os.path.basename(visdict[visname][1]))
        if os.path.exists(file_path):
            nfiles += 1
        else:
            missing.append(os.path.basename(visdict[visname][1]))

    if nfiles <= 0:
        score = 0.0
        longmsg = 'Final apply commands files %s are missing' % (','.join(missing))
        shortmsg = 'Missing final apply commands files'
    elif nfiles < nexpected:
        score = float(nfiles) / float(nexpected)
        longmsg = 'Final apply commands files %s are missing' % (','.join(missing))
        shortmsg = 'Missing final apply commands files'
    else:
        score = 1.0
        longmsg = 'No missing final apply commands files'
        shortmsg = 'No missing final apply commands files'

    origin = pqa.QAOrigin(metric_name='score_applycmds_exist',
                          metric_score=len(missing),
                          metric_units='Number of missing apply command files')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_caltables_exist(filedir, sessiondict):
    """
    Score the existence of the caltables products files
        1.0 if theu all exist
        n / nexpected if some of them exist
        0.0 if none exist
    """
    nexpected = len(sessiondict)
    nfiles = 0
    missing = []

    for sessionname in sessiondict:
        file_path = os.path.join(filedir, os.path.basename(sessiondict[sessionname][1]))
        if os.path.exists(file_path):
            nfiles += 1
        else:
            missing.append(os.path.basename(sessiondict[sessionname][1]))

    if nfiles <= 0:
        score = 0.0
        longmsg = 'Caltables files %s are missing' % (','.join(missing))
        shortmsg = 'Missing caltables files'
    elif nfiles < nexpected:
        score = float(nfiles) / float(nexpected)
        longmsg = 'Caltables files %s are missing' % (','.join(missing))
        shortmsg = 'Missing caltables files'
    else:
        score = 1.0
        longmsg = 'No missing caltables files'
        shortmsg = 'No missing caltables files'

    origin = pqa.QAOrigin(metric_name='score_caltables_exist',
                          metric_score=len(missing),
                          metric_units='Number of missing caltables')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_images_exist(filesdir, imaging_products_only, calimages, targetimages):
    if imaging_products_only:
        if len(targetimages) <= 0:
            score = 0.0
            metric = 0
            longmsg = 'No target images were exported'
            shortmsg = 'No target images exported'
        else:
            score = 1.0
            metric = len(targetimages)
            longmsg = '%d target images were exported' % (len(targetimages))
            shortmsg = 'Target images exported'
    else:
        if len(targetimages) <= 0 and len(calimages) <= 0:
            score = 0.0
            metric = 0
            longmsg = 'No images were exported'
            shortmsg = 'No images exported'
        else:
            score = 1.0
            metric = len(calimages) + len(targetimages)
            longmsg = '%d images were exported' % (len(calimages) + len(targetimages))
            shortmsg = 'Images exported'

    origin = pqa.QAOrigin(metric_name='score_images_exist',
                          metric_score=metric,
                          metric_units='Number of exported images')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_sd_line_detection(group_id_list, spw_id_list, lines_list):
    detected_spw = []
    detected_group = []

    for group_id, spw_id, lines in zip(group_id_list, spw_id_list, lines_list):
        if any([l[2] for l in lines]):
            LOG.trace('detected lines exist at group_id %s spw_id %s' % (group_id, spw_id))
            unique_spw_id = set(spw_id)
            if len(unique_spw_id) == 1:
                detected_spw.append(unique_spw_id.pop())
            else:
                detected_spw.append(-1)
            detected_group.append(group_id)

    if len(detected_spw) == 0:
        score = 0.0
        longmsg = 'No spectral lines were detected'
        shortmsg = 'No spectral lines were detected'
    else:
        score = 1.0
        if detected_spw.count(-1) == 0:
            longmsg = 'Spectral lines were detected in spws %s' % (', '.join(map(str, detected_spw)))
        else:
            longmsg = 'Spectral lines were detected in ReductionGroups %s' % (','.join(map(str, detected_group)))
        shortmsg = 'Spectral lines were detected'

    origin = pqa.QAOrigin(metric_name='score_sd_line_detection',
                          metric_score=len(detected_spw),
                          metric_units='Number of spectral lines detected')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_sd_line_detection_for_ms(group_id_list, field_id_list, spw_id_list, lines_list):
    detected_spw = []
    detected_field = []
    detected_group = []

    for group_id, field_id, spw_id, lines in zip(group_id_list, field_id_list, spw_id_list, lines_list):
        if any([l[2] for l in lines]):
            LOG.trace('detected lines exist at group_id %s field_id %s spw_id %s' % (group_id, field_id, spw_id))
            unique_spw_id = set(spw_id)
            if len(unique_spw_id) == 1:
                detected_spw.append(unique_spw_id.pop())
            else:
                detected_spw.append(-1)
            unique_field_id = set(field_id)
            if len(unique_field_id) == 1:
                detected_field.append(unique_field_id.pop())
            else:
                detected_field.append(-1)
            detected_group.append(group_id)

    if len(detected_spw) == 0:
        score = 0.0
        longmsg = 'No spectral lines are detected'
        shortmsg = 'No spectral lines are detected'
    else:
        score = 1.0
        if detected_spw.count(-1) == 0 and detected_field.count(-1) == 0:
            longmsg = 'Spectral lines are detected at Spws (%s) Fields (%s)' % (', '.join(map(str, detected_spw)),
                                                                                ', '.join(map(str, detected_field)))
        else:
            longmsg = 'Spectral lines are detected at ReductionGroups %s' % (','.join(map(str, detected_group)))
        shortmsg = 'Spectral lines are detected'

    origin = pqa.QAOrigin(metric_name='score_sd_line_detection_for_ms',
                          metric_score=len(detected_spw),
                          metric_units='Number of spectral lines detected')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)

@log_qa
def score_sd_baseline_quality(vis: str, source: str, ant: str, vspw: str,
                              pol: str, stat: List[tuple]) -> pqa.QAScore:
    """
    Return Pipeline QA score of baseline quality.

    Args:
        vis: MS name
        source: source name
        ant: antenna name
        vspw: virtual spw ID
        pol: polarization
        stat: a list of binned statistics

    Returns:
        Pipeline QA score of baseline quality.
    """
    scores = []
    LOG.info(f'Statistics of {vis}: {source}, {ant}, {vspw}, {pol}')
    # See PIPEREQ-168 for details of QA metrics.
    # The values of bin_diff_ratio at the edges of ramp
    ramp_range = (1.8, 3.6)
    # The scores at the corresponding edges of ramp. These values are also
    # adopted in extrapolation beyond ramp_range.
    score_range = (1.0, 0.33)
    metric_func = interpolate.interp1d(ramp_range, score_range,
                                       kind='linear', bounds_error=False,
                                       fill_value=score_range)
    for s in stat:
        diff_score =  metric_func(s.bin_diff_ratio)
        scores.append(diff_score)
        LOG.info(f'rdiff = {s.bin_diff_ratio} -> score = {diff_score}')
    final_score = np.nanmin(scores)
    quality = 'Good'
    if final_score <= 0.66:
        quality='Poor'
    elif final_score <= 0.9:
        quality='Moderate'
    shortmsg = f'{quality} baseline flatness'
    longmsg = f'{quality} baseline flatness in {vis}, {source}, {ant}, virtual spw {vspw}, {pol}'
    origin = pqa.QAOrigin(metric_name='score_sd_baseline_quality',
                          metric_score=len(stat),
                          metric_units='Statistics of binned spectra')

    return pqa.QAScore(final_score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)

@log_qa
def score_checksources(mses, fieldname, spwid, imagename, rms, gfluxscale, gfluxscale_err):
    """
    Score a single field image of a point source by comparing the source
    reference position to the fitted position and the source reference flux
    to the fitted flux.

    The source is assumed to be near the center of the image.
    The fit is performed using pixels in a circular regions
    around the center of the image
    """
    qa = casa_tools.quanta
    me = casa_tools.measures

    # Get the reference direction of the check source field
    #    There is at least one field with check source intent
    #    Protect against the same source having multiple fields
    #    with different intent.
    #    Assume that the same field as defined by its field name
    #    has the same direction in all the mses that contributed
    #    to the input image. Loop through the ms(s) and find the
    #    first occurrence of the specified field. Convert the
    #    direction to ICRS to match the default image coordinate
    #    system

    refdirection = None
    for ms in mses:
        field = ms.get_fields(name=fieldname)
        # No fields with the check source name. Should be
        # impossible at this point but check just in case
        if not field:
            continue
        # Find check field for that ms
        chkfield = None
        for fielditem in field:
            if 'CHECK' not in fielditem.intents:
                continue
            chkfield = fielditem
            break
        # No matching check field for that ms, next ms
        if chkfield is None:
            continue
        # Found field, get reference direction in ICRS coordinates
        LOG.info('Using field name %s id %s to determine check source reference direction' %
                 (chkfield.name, str(chkfield.id)))
        refdirection = me.measure(chkfield.mdirection, 'ICRS')
        break

    # Get the reference flux of the check source field
    #    Loop over all the ms(s) extracting the derived flux
    #    values for the specified field and spw. Set the reference
    #    flux to the maximum of these values.
    reffluxes = []
    for ms in mses:
        if not ms.derived_fluxes:
            continue
        for field_arg, measurements in ms.derived_fluxes.items():
            mfield = ms.get_fields(field_arg)
            chkfield = None
            for mfielditem in mfield:
                if mfielditem.name != fieldname:
                    continue
                if 'CHECK' not in mfielditem.intents:
                    continue
                chkfield = mfielditem
                break
            # No matching check field for this ms
            if chkfield is None:
                continue
            LOG.info('Using field name %s id %s to identify check source flux densities' %
                     (chkfield.name, str(chkfield.id)))
            for measurement in sorted(measurements, key=lambda m: int(m.spw_id)):
                if int(measurement.spw_id) != spwid:
                    continue
                for stokes in ['I']:
                    try:
                        flux = getattr(measurement, stokes)
                        flux_jy = float(flux.to_units(measures.FluxDensityUnits.JANSKY))
                        reffluxes.append(flux_jy)
                    except:
                        pass

    # Use the maximum reference flux
    if not reffluxes:
        refflux = None
    else:
        median_flux = np.median(np.array(reffluxes))
        refflux = qa.quantity(median_flux, 'Jy')

    # Do the fit and compute positions offsets and flux ratios
    fitdict = checksource.checkimage(imagename, rms, refdirection, refflux)

    msnames = ','.join([os.path.basename(ms.name).strip('.ms') for ms in mses])

    # Compute the scores the default score is the geometric mean of
    # the position and flux scores if both are available.
    if not fitdict:
        offset = None
        offset_err = None
        beams = None
        beams_err = None
        fitflux = None
        fitflux_err = None
        fitpeak = None
        score = 0.0
        longmsg = 'Check source fit failed for %s field %s spwid %d' % (msnames, fieldname, spwid)
        shortmsg = 'Check source fit failed'
        metric_score = 'N/A'
        metric_units = 'Check source fit failed'

    else:
        offset = fitdict['positionoffset']['value'] * 1000.0
        offset_err = fitdict['positionoffset_err']['value'] * 1000.0
        beams = fitdict['beamoffset']['value']
        beams_err = fitdict['beamoffset_err']['value']
        fitflux = fitdict['fitflux']['value']
        fitflux_err = fitdict['fitflux_err']['value']
        fitpeak = fitdict['fitpeak']['value']
        shortmsg = 'Check source fit successful'

        warnings = []

        if refflux is not None:
            coherence = fitdict['fluxloss']['value'] * 100.0
            flux_score = max(0.0, 1.0 - fitdict['fluxloss']['value'])
            flux_metric = fitdict['fluxloss']['value']
            flux_unit = 'flux loss'
        else:
            flux_score = 0.0
            flux_metric = 'N/A'
            flux_unit = 'flux loss'

        offset_score = 0.0
        offset_metric = 'N/A'
        offset_unit = 'beams'
        if beams is None:
            warnings.append('unfitted offset')
        else:
            offset_score = max(0.33, 1.0 - min(1.0, beams))
            offset_metric = beams
            if beams > 0.30:
                warnings.append('large fitted offset of %.2f marcsec and %.2f synth beam' % (offset, beams))

        fitflux_score = 0.0
        fitflux_metric = 'N/A'
        fitflux_unit = 'fitflux/refflux'
        if gfluxscale is None:
            warnings.append('undefined gfluxscale result')
        elif gfluxscale == 0.0:
            warnings.append('gfluxscale value of 0.0 mJy')
        else:
            chk_fitflux_gfluxscale_ratio = fitflux * 1000. / gfluxscale
            fitflux_score = max(0.33, 1.0 - abs(1.0 - chk_fitflux_gfluxscale_ratio))
            fitflux_metric = chk_fitflux_gfluxscale_ratio
            if chk_fitflux_gfluxscale_ratio < 0.8:
                warnings.append('low [Fitted / gfluxscale] Flux Density Ratio of %.2f' % (chk_fitflux_gfluxscale_ratio))

        fitpeak_score = 0.0
        fitpeak_metric = 'N/A'
        fitpeak_unit = 'fitpeak/fitflux'
        if fitflux is None:
            warnings.append('undefined check fit result')
        elif fitflux == 0.0:
            warnings.append('Fitted Flux Density value of 0.0 mJy')
        else:
            chk_fitpeak_fitflux_ratio = fitpeak / fitflux
            fitpeak_score = max(0.33, 1.0 - abs(1.0 - (chk_fitpeak_fitflux_ratio)))
            fitpeak_metric = chk_fitpeak_fitflux_ratio
            if chk_fitpeak_fitflux_ratio < 0.7:
                warnings.append('low Fitted [Peak Intensity / Flux Density] Ratio of %.2f' % (chk_fitpeak_fitflux_ratio))

        snr_msg = ''
        if gfluxscale is not None and gfluxscale_err is not None:
            if gfluxscale_err != 0.0:
                chk_gfluxscale_snr = gfluxscale / gfluxscale_err
                if chk_gfluxscale_snr < 20.:
                    snr_msg = ', however, the S/N of the gfluxscale measurement is low'

        if any(np.array([offset_score, fitflux_score, fitpeak_score]) < 1.0):
            score = math.sqrt(offset_score * fitflux_score * fitpeak_score)
        else:
            score = offset_score * fitflux_score * fitpeak_score
        metric_score = [offset_metric, fitflux_metric, fitpeak_metric]
        metric_units = '%s, %s, %s' % (offset_unit, fitflux_unit, fitpeak_unit)

        if warnings != []:
            longmsg = 'EB %s field %s spwid %d: has a %s%s' % (msnames, fieldname, spwid, ' and a '.join(warnings), snr_msg)
            # Log warnings only if they would not be logged by the QA system (score <= 0.66)
            if score > 0.66:
                LOG.warning(longmsg)
        else:
            if score <= 0.9:
                longmsg = 'EB %s field %s spwid %d: Check source fit not optimal' % (msnames, fieldname, spwid)
            else:
                longmsg = 'EB %s field %s spwid %d: Check source fit successful' % (msnames, fieldname, spwid)

        if score <= 0.9:
            shortmsg = 'Check source fit not optimal'

    origin = pqa.QAOrigin(metric_name='ScoreChecksources',
                          metric_score=metric_score,
                          metric_units=metric_units)

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin), offset, offset_err, beams, beams_err, fitflux, fitflux_err, fitpeak


@log_qa
def score_multiply(scores_list):
    score = functools.reduce(operator.mul, scores_list, 1.0)
    longmsg = 'Multiplication of scores.'
    shortmsg = 'Multiplication of scores.'
    origin = pqa.QAOrigin(metric_name='score_multiply',
                          metric_score=len(scores_list),
                          metric_units='Number of multiplied scores.')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_sd_skycal_elevation_difference(ms, resultdict, threshold=3.0):
    """
    """
    field_ids = list(resultdict.keys())
    metric_score = []
    el_threshold = threshold
    lmsg_list = []
    for field_id in field_ids:
        field = ms.fields[field_id]
        if field_id not in resultdict:
            continue

        eldiffant = resultdict[field_id]
        warned_antennas = set()
        for antenna_id, eldiff in eldiffant.items():
            for spw_id, eld in eldiff.items():
                preceding = eld.eldiff0
                subsequent = eld.eldiff1
                # LOG.info('field {} antenna {} spw {} preceding={}'.format(field_id, antenna_id, spw_id, preceding))
                # LOG.info('field {} antenna {} spw {} subsequent={}'.format(field_id, antenna_id, spw_id, subsequent))
                max_pred = None
                max_subq = None
                if len(preceding) > 0:
                    max_pred = np.abs(preceding).max()
                    metric_score.append(max_pred)
                    if max_pred >= el_threshold:
                        warned_antennas.add(antenna_id)
                if len(subsequent) > 0:
                    max_subq = np.abs(subsequent).max()
                    metric_score.append(max_subq)
                    if max_subq >= el_threshold:
                        warned_antennas.add(antenna_id)
                LOG.debug('field {} antenna {} spw {} metric_score {}'.format(field_id, antenna_id, spw_id, metric_score))

        if len(warned_antennas) > 0:
            antenna_names = ', '.join([ms.antennas[a].name for a in warned_antennas])
            lmsg_list.append(
                'field {} (antennas {})'.format(field.name, antenna_names)
            )

    if len(lmsg_list) > 0:
        longmsg = 'Elevation difference between ON and OFF exceeds threshold ({}deg) for {}: {}'.format(
            el_threshold,
            ms.basename,
            ', '.join(lmsg_list)
        )
    else:
        longmsg = 'Elevation difference between ON and OFF is below threshold ({}deg) for {}'.format(
            el_threshold,
            ms.basename
        )

    # CAS-11054: it is decided that we do not calculate QA score based on elevation difference for Cycle 6
    # PIPE-246: we implement QA score based on elevation difference for Cycle 7.
    #           requirement is that score is 0.8 if elevation difference is larger than 3deg.
    # make sure threshold is 3deg
    assert el_threshold == 3.0
    max_metric_score = np.max(metric_score)
    # lower the score if elevation difference exceeds 3deg
    score = 1.0 if max_metric_score < el_threshold else 0.8
    origin = pqa.QAOrigin(metric_name='OnOffElevationDifference',
                          metric_score=max_metric_score,
                          metric_units='deg')

    if score < 1.0:
        shortmsg = 'Elevation difference between ON and OFF exceeds {}deg'.format(el_threshold)
    else:
        shortmsg = 'Elevation difference between ON and OFF is below {}deg'.format(el_threshold)

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin, vis=ms.basename)


def generate_metric_mask(context, result, cs, mask):
    """
    Generate boolean mask array for metric calculation in
    score_sdimage_masked_pixels. If image pixel contains
    observed points, mask will be True. Otherwise, mask is
    False.

    Arguments:
        context {Context} -- Pipeline context
        result {SDImagingResultItem} -- result item created by
                                        hsd_imaging
        cs {coordsys} -- CASA coordsys tool
        mask {bool array} -- image mask

    Returns:
        bool array -- metric mask (True: valid, False: invalid)
    """
    outcome = result.outcome
    org_direction = outcome['image'].org_direction
    imshape = mask.shape

    file_index = np.asarray(outcome['file_index'])
    antenna_list = np.asarray(outcome['assoc_antennas'])
    field_list = np.asarray(outcome['assoc_fields'])
    vspw_list = np.asarray(outcome['assoc_spws'])

    mses = context.observing_run.measurement_sets
    ms_list = [mses[i] for i in file_index]
    spw_list = np.asarray([context.observing_run.virtual2real_spw_id(i, m) for i, m in zip(vspw_list, ms_list)])

    ra = []
    dec = []
    ofs_ra = []
    ofs_dec = []
    online_flag = []

    for i in range(len(ms_list)):
        origin_basename = os.path.basename(ms_list[i].origin_ms)
        datatable_name = os.path.join(context.observing_run.ms_datatable_name, origin_basename)
        rotable_name = os.path.join(datatable_name, 'RO')
        rwtable_name = os.path.join(datatable_name, 'RW')
        _index = np.where(file_index == file_index[i])
        if len(_index[0]) == 0:
            continue

        _antlist = antenna_list[_index]
        _fieldlist = field_list[_index]
        _spwlist = spw_list[_index]

        with casa_tools.TableReader(rotable_name) as tb:
            unit_ra = tb.getcolkeyword('OFS_RA', 'UNIT')
            unit_dec = tb.getcolkeyword('OFS_DEC', 'UNIT')
            tsel = tb.query('SRCTYPE==0&&ANTENNA IN {}&&FIELD_ID IN {}&&IF IN {}'.format(list(_antlist), list(_fieldlist), list(_spwlist)))
            ofs_ra.extend(tsel.getcol('OFS_RA'))
            ofs_dec.extend(tsel.getcol('OFS_DEC'))
            rows = tsel.rownumbers()
            tsel.close()

        with casa_tools.TableReader(rwtable_name) as tb:
            permanent_flag = tb.getcol('FLAG_PERMANENT').take(rows, axis=2)
            online_flag.extend(permanent_flag[0, OnlineFlagIndex])

    if org_direction is None:
        ra = np.asarray(ofs_ra)
        dec = np.asarray(ofs_dec)
    else:
        for rr, dd in zip(ofs_ra, ofs_dec):
            shift_ra, shift_dec = direction_recover( rr, dd, org_direction )
            ra.append(shift_ra)
            dec.append(shift_dec)
        ra = np.asarray(ra)
        dec = np.asarray(dec)
    online_flag = np.asarray(online_flag)

    del ofs_ra, ofs_dec

    metric_mask = np.empty(imshape, dtype=bool)
    metric_mask[:] = False

    qa = casa_tools.quanta

    # template measure for world-pixel conversion
    # 2019/06/03 TN
    # Workaround for memory consumption issue (PIPE-362)
    # cs.topixel consumes some amount of memory and it accumulates,
    # too many call of cs.topixel results in unexpectedly large amount of
    # memory usage. To avoid cs.topixel, approximate mapping to pixel
    # coordinate is done manually.
    blc = cs.toworld([-0.5, -0.5, 0, 0], format='q')
    brc = cs.toworld([imshape[0] - 0.5, -0.5, 0, 0], format='q')
    tlc = cs.toworld([-0.5, imshape[1] - 0.5, 0, 0], format='q')
    trc = cs.toworld([imshape[0] - 0.5, imshape[1] - 0.5, 0, 0], format='q')
    #print('blc {} {}'.format(blc['quantity']['*1'], blc['quantity']['*2']))
    #print('brc {} {}'.format(brc['quantity']['*1'], brc['quantity']['*2']))
    #print('tlc {} {}'.format(tlc['quantity']['*1'], tlc['quantity']['*2']))
    #print('trc {} {}'.format(trc['quantity']['*1'], trc['quantity']['*2']))
    #print('cen {} {}'.format(cen['quantity']['*1'], cen['quantity']['*2']))
    cpi = qa.convert(qa.quantity(180, 'deg'), unit_ra)['value']
    s0 = (qa.convert(tlc['quantity']['*1'], unit_ra)['value'] - qa.convert(blc['quantity']['*1'], unit_ra)['value']) \
        / (qa.convert(tlc['quantity']['*2'], unit_dec)['value'] - qa.convert(blc['quantity']['*2'], unit_dec)['value'])
    t0 = ((qa.convert(blc['quantity']['*1'], unit_ra)['value']) + cpi) % (cpi * 2) - cpi
    s1 = (qa.convert(trc['quantity']['*1'], unit_ra)['value'] - qa.convert(brc['quantity']['*1'], unit_ra)['value']) \
        / (qa.convert(trc['quantity']['*2'], unit_dec)['value'] - qa.convert(brc['quantity']['*2'], unit_dec)['value'])
    t1 = ((qa.convert(brc['quantity']['*1'], unit_ra)['value']) + cpi) % (cpi * 2) - cpi
    ymax = (qa.convert(tlc['quantity']['*2'], unit_dec)['value'] + qa.convert(trc['quantity']['*2'], unit_dec)['value']) / 2
    ymin = (qa.convert(blc['quantity']['*2'], unit_dec)['value'] + qa.convert(brc['quantity']['*2'], unit_dec)['value']) / 2
    dy = (ymax - ymin) / imshape[1]
    #print('s0 {} t0 {} s1 {} t1 {}'.format(s0, t0, s1, t1))
    #print('ymax {} ymin {} dy {}'.format(ymax, ymin, dy))
    #world = cs.toworld([0, 0, 0, 0], format='m')
    px = np.empty_like(ra)
    py = np.empty_like(dec)
    px[:] = -1
    py[:] = -1
    for i, (x, y, f) in enumerate(zip(ra, dec, online_flag)):
        if f != 1:
            # PIPE-439 flagged pointing data are not taken into account
            continue

        #world['measure']['direction']['m0']['value'] = qa.quantity(x, unit_ra)
        #world['measure']['direction']['m1']['value'] = qa.quantity(y, unit_dec)
        #p = cs.topixel(world)
        #px[i] = p['numeric'][0]
        #py[i] = p['numeric'][1]
        y0 = y
        xmin = s0 * (y - y0) + t0
        xmax = s1 * (y - y0) + t1
        dx = (xmax - xmin) / imshape[0]
        #print('xmin {} xmax {} dx {}'.format(xmin, xmax, dx))
        #print('x {} y {}'.format(x, y))
        py[i] = (y - ymin) / dy - 0.5
        px[i] = (x - xmin) / dx - 0.5
        #print('WORLD {} {} <-> PIXEL {} {}'.format(x, y, px[i], py[i]))

    for x, y in zip(map(int, np.round(px)), map(int, np.round(py))):
        #print(x, y)
        if 0 <= x and x <= imshape[0] - 1 and 0 <= y and y <= imshape[1] - 1:
            metric_mask[x, y, :, :] = True

    # exclude edge channels
    edge_channels = [i for i in range(imshape[3]) if np.all(mask[:, :, :, i] == False)]
    LOG.debug('edge channels: {}'.format(edge_channels))
    metric_mask[:, :, :, edge_channels] = False

    return metric_mask


def direction_recover( ra, dec, org_direction ):
    me = casa_tools.measures
    qa = casa_tools.quanta

    direction = me.direction( org_direction['refer'],
                              str(ra)+'deg', str(dec)+'deg' )
    zero_direction  = me.direction( org_direction['refer'], '0deg', '0deg' )
    offset = me.separation( zero_direction, direction )
    posang = me.posangle( zero_direction, direction )
    new_direction = me.shift( org_direction, offset=offset, pa=posang )
    new_ra  = qa.convert( new_direction['m0'], 'deg' )['value']
    new_dec = qa.convert( new_direction['m1'], 'deg' )['value']

    return new_ra, new_dec


@log_qa
def score_sdimage_masked_pixels(context, result):
    """
    Evaluate QA score based on the fraction of masked pixels in image.


    Requirements (PIPE-249):
        - calculate the number of masked pixels in image
        - search area should be the extent of pointing direction
        - QA score should be
            1.0 (if the nuber of masked pixel == 0)
            0.5 (if any of the pixel in pointing area is masked)
            0.0 (if 10% of the pixels in pointing area are masked)
            *linearly interpolate between 0.5 and 0.0

    Arguments:
        context {Context} -- Pipeline context
        result {SDImagingResultItem} -- Imaging result instance

    Returns:
        QAScore -- QAScore instance holding the score based on number of
                   masked pixels in image
    """
    # metric score is a fraction of masked pixels
    result_item = result.outcome
    image_item = result_item['image']
    imagename = image_item.imagename

    LOG.debug('imagename = {}'.format(imagename))
    with casa_tools.ImageReader(imagename) as ia:
        # get mask
        # Mask Definition: True is valid, False is invalid.
        mask = ia.getchunk(getmask=True)

        imageshape = ia.shape()

        # cs represents coordinate system of the image
        cs = ia.coordsys()

    # image shape: (lon, lat, stokes, freq)
    LOG.debug('image shape: {}'.format(list(imageshape)))

    try:
        # metric_mask is boolean array that defines the region to be excluded
        #    True: included in the metric calculation
        #   False: excluded from the metric calculation
        # TODO: decide if any margin is necessary
        metric_mask = generate_metric_mask(context, result, cs, mask)
    finally:
        # done using coordsys tool
        cs.done()

    # calculate metric_score
    total_pixels = mask[metric_mask]
    LOG.debug('Total number of pixels to be included in: {}'.format(len(total_pixels)))
    masked_pixels = total_pixels[total_pixels == False]
    if len(total_pixels) == 0:
        LOG.warning('No pixels associated with pointing data exist. QA score will be zero.')
        metric_score = -1.0
    else:
        masked_fraction = float(len(masked_pixels)) / float(len(total_pixels))
        LOG.debug('Number of masked pixels: {} fraction {}'.format(len(masked_pixels), masked_fraction))
        metric_score = masked_fraction

    # score should be evaluated from metric score
    lmsg = ''
    smsg = ''
    score = 0.0
    metric_score_threshold = 0.1
    metric_score_max = 1.0
    metric_score_min = 0.0

    # convert score and threhold for logging purpose
    frac2percentage = lambda x: '{:.4g}%'.format(x * 100)
    imbasename = os.path.basename(imagename.rstrip('/'))

    if metric_score > metric_score_max:
        # metric_score should not exceed 1.0. something wrong.
        _x = frac2percentage(metric_score_max)
        lmsg = '{}: fraction of number of masked pixels should not exceed {}. something went wrong.'.format(imbasename, _x)
        smsg = 'metric value out of range.'
        score = 0.0
    elif metric_score < metric_score_min:
        lmsg = '{}: No pixels associated with pointing data exist. something went wrong.'.format(imbasename)
        smsg = 'metric value out of range.'
        score = 0.0
    elif metric_score == metric_score_min:
        lmsg = 'All examined pixels in image {} are valid.'.format(imbasename)
        smsg = 'All examined pixels are valid.'
        score = 1.0
    elif metric_score > metric_score_threshold:
        _x = frac2percentage(metric_score_threshold)
        _y = frac2percentage(metric_score)
        lmsg = 'Fraction of masked pixels in image {} is {}, exceeding threshold value ({}).'.format(imbasename, _y, _x)
        smsg = 'More than {} of image pixels are masked.'.format(_x)
        score = 0.0
    else:
        # interpolate between 0.5 and 0.0
        _x = frac2percentage(metric_score)
        lmsg = 'Fraction of masked pixels in image {} is {}.'.format(imbasename, _x)
        smsg = '{} of image pixels are masked.'.format(_x)
        smax = 0.5
        mmax = 0.0
        smin = 0.0
        mmin = 0.1
        score = (smax - smin) / (mmax - mmin) * (metric_score - mmin) + smin

    origin = pqa.QAOrigin(metric_name='SingleDishImageMaskedPixels',
                          metric_score=metric_score,
                          metric_units='Fraction of masked pixels in image')

    return pqa.QAScore(score,
                       longmsg=lmsg,
                       shortmsg=smsg,
                       origin=origin)


@log_qa
def score_gfluxscale_k_spw(vis, field, spw_id, k_spw, ref_spw):
    """ Convert internal spw_id-spw_id consistency ratio to a QA score.

    See CAS-10792 for full specification.
    See PIPE-644 for update to restrict range of scores.

    k_spw is equal to the ratio:

                       calibrated visibility flux / catalogue flux
    k_spw = --------------------------------------------------------------------
            (calibrated visibility flux / catalogue flux) for highest SNR window

    Q_spw = abs(1 - k_spw)

    If        Q_spw < 0.1 then QA score = 1.0  (green)
    If 0.1 <= Q_spw < 0.2 then QA score = 0.75 (Blue/below standard)
    If 0.2 <= Q_spw       then QA score = 0.5  (Yellow/warning)

    :param k_spw: numeric k_spw ratio, as per spec
    :param vis: name of measurement set to which k_spw applies
    :param field: field domain object to which k_spw applies
    :param spw_id: name of spectral window to which k_spw applies
    :return: QA score
    """
    q_spw = abs(1-k_spw)
    if q_spw < 0.1:
        score = 1.0
    elif q_spw < 0.2:
        score = 0.75
    else:
        score = 0.5

    longmsg = ('Ratio of <i>S</i><sub>calibrated</sub>/<i>S</i><sub>catalogue</sub> for {} ({}) spw {} in {} differs by'
               ' {:.0%} from the ratio for the highest SNR spw ({})'
               ''.format(utils.dequote(field.name), ','.join(field.intents), spw_id, vis, q_spw, ref_spw))
    shortmsg = 'Internal spw-spw consistency'

    origin = pqa.QAOrigin(metric_name='score_gfluxscale_k_spw',
                          metric_score=float(k_spw),
                          metric_units='Number of spws with missing SNR measurements')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=vis, origin=origin)


@log_qa
def score_science_spw_names(mses, virtual_science_spw_names):
    """
    Check that all MSs have the same set of spw names. If this is
    not the case, the virtual spw mapping will not work.
    """

    score = 1.0
    msgs = []
    for ms in mses:
        spw_msgs = []
        for s in ms.get_spectral_windows(science_windows_only=True):
            if s.name not in virtual_science_spw_names:
                score = 0.0
                spw_msgs.append('{0} (ID {1})'.format(s.name, s.id))
        if spw_msgs != []:
            msgs.append('Science spw names {0} of EB {1} do not match spw names of first EB.'
                        ''.format(','.join(spw_msgs), os.path.basename(ms.name).replace('.ms', '')))

    if msgs == []:
        longmsg = 'Science spw names match virtual spw lookup table'
        shortmsg = 'Science spw names match'
    else:
        longmsg = '{0} Virtual spw ID mapping will not work.'.format(' '.join(msgs))
        shortmsg = 'Science spw names do not match'

    origin = pqa.QAOrigin(metric_name='score_spwnames',
                          metric_score=score,
                          metric_units='spw names match virtual spw name lookup table')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)

def score_renorm(result):
    if result.renorm_applied:
        msg = 'Restore successful with renormalization applied'
        score = rutils.SCORE_THRESHOLD_SUBOPTIMAL
    else:
        msg = 'Restore successful'
        score = 1.0

    origin = pqa.QAOrigin(metric_name='score_renormalize',
                            metric_score=score,
                            metric_units='')
    return pqa.QAScore(score, longmsg=msg, shortmsg=msg, origin=origin)

@log_qa
def score_fluxservice(result):
    """
    If the primary FS query fails and the backup is invoked,
    the severity level should be BLUE (below standard; numerically, on its own, 0.9).
    If the backup FS query also fails, the warning should be YELLOW (WARNING; numerically, on its own, 0.6).
    But it should keep running as it currently does.
    """

    if result.inputs['dbservice'] is False:
        score = 1.0
        msg = "Flux catalog service not used."
        for setjy_result in result.setjy_results:
            measurements = setjy_result.measurements
            for measurement in measurements.items():
                try:
                    fluxorigin = measurement[1][0].origin
                    if fluxorigin == 'Source.xml':
                        score = 0.3
                        msg = "Flux catalog service not used.  Source.xml is the origin."
                except Exception as e:
                    LOG.debug("Skip since there is not a flux measurement")

        origin = pqa.QAOrigin(metric_name='score_fluxservice',
                              metric_score=score,
                              metric_units='flux service')
        return pqa.QAScore(score, longmsg=msg, shortmsg=msg, origin=origin)
    elif result.inputs['dbservice'] is True:
        msg = ""
        if result.fluxservice is 'FIRSTURL':
            msg += "Flux catalog service used.  "
            score = 1.0
        elif result.fluxservice is 'BACKUPURL':
            msg += "Backup flux catalog service used.  "
            score = 0.9
        elif result.fluxservice is 'FAIL':
            msg += "Neither primary or backup flux service could be queried.  ASDM values used."
            score = 0.3

        agecounter = 0
        if result.fluxservice in ['FIRSTURL', 'BACKUPURL']:
            for setjy_result in result.setjy_results:
                measurements = setjy_result.measurements
                for measurement in measurements.items():
                    try:
                        fieldid = measurement[0]
                        mm = result.mses[0]
                        fieldobjs = mm.get_fields(field_id=fieldid)
                        intentlist = []
                        for fieldobj in fieldobjs:
                            intentlist.append(fieldobj.intents)

                        # PIPE-1124.  Only determine QA age scoring if 'AMPLITUDE' intent is present for a source.
                        if 'AMPLTIUDE' in intentlist:
                            age = measurement[1][0].age  # second element of a tuple, first element of list of flux objects
                            if int(abs(age)) > 14:
                                agecounter = agecounter + 1
                    except IndexError:
                        LOG.debug("Skip since there is no age present")

            # Any sources with age of nearest monitoring point greater than 14 days?
            if agecounter > 0:
                score = 0.5
                msg += "Age of nearest monitor point is greater than 14 days."

        origin = pqa.QAOrigin(metric_name='score_fluxservice',
                              metric_score=score,
                              metric_units='flux service')
        return pqa.QAScore(score, longmsg=msg, shortmsg=msg, origin=origin)


@log_qa
def score_fluxservicemessages(result):
    """
    Report any flux service messaging and status codes
    """
    if result.inputs['dbservice'] is False:
        score = 1.0
        longmsg = "Flux catalog service not used.  No warning messages reported."
        shortmsg = longmsg
    elif result.inputs['dbservice'] is True:
        score = 1.0
        longmsg = "No warning messages from the flux catalog service."
        shortmsg = longmsg
        if result.qastatus:
            longmsg = ""
            for qacode in result.qastatus:
                if qacode['clarification']:
                    score = 0.5
                    # Queries a per source, so there may be more than one message returned.
                    longmsg += "Source: {!s},  Status code: {!s},     Message: {!s}\n".format(qacode['source'],
                                                                                            qacode['status_code'],
                                                                                            qacode['clarification'])
                    shortmsg = "Flux service returned warning messages."

    origin = pqa.QAOrigin(metric_name='score_fluxservice_messaging',
                          metric_score=score,
                          metric_units='flux service messaging')
    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_fluxservicestatuscodes(result):
    """
    Report any flux service codes for status_code > 1
    """
    if result.inputs['dbservice'] is False:
        score = 1.0
        msg = "Flux catalog service not used.  No status codes to report."
    elif result.inputs['dbservice'] is True:
        score = 1.0
        msg = "Flux catalog service status queries returned code 0 or 1."
        if result.qastatus:
            scores = []
            for qacode in result.qastatus:
                # Status code can be 0,1,2,3
                if int(qacode['status_code']) > 1:
                    score = 0.3
                    msg = "A query of the flux catalog service returned a status code: {!s}".format(str(qacode['status_code']))

    origin = pqa.QAOrigin(metric_name='score_fluxservice_statuscode',
                          metric_score=score,
                          metric_units='flux service status code')
    return pqa.QAScore(score, longmsg=msg, shortmsg=msg, origin=origin)


@log_qa
def score_fluxcsv(result):
    """
    Check for existence of flux.csv file on import
    """

    if os.path.exists('flux.csv'):
        score = 1.0
        msg = 'flux.csv exists on disk'
    else:
        score = 0.3
        msg = "flux.csv does not exist"

    origin = pqa.QAOrigin(metric_name='score_fluxcsv',
                          metric_score=score,
                          metric_units='flux csv')
    return pqa.QAScore(score, longmsg=msg, shortmsg=msg, origin=origin)





@log_qa
def score_mom8_fc_image(mom8_fc_name, peak_snr, cube_chanScaled_MAD, outlier_threshold, n_pixels, n_outlier_pixels, is_eph_obj=False):
    """
    Check the MOM8 FC image for outliers above a given SNR threshold. The score
    can vary between 0.33 and 1.0 depending on the fraction of outlier pixels.
    """

    outlier_fraction = n_outlier_pixels / n_pixels
    with casa_tools.ImageReader(mom8_fc_name) as image:
        info = image.miscinfo()
        field = info.get('field')
        spw = info.get('virtspw')

    if peak_snr <= outlier_threshold:
        score = 1.0
        longmsg = 'MOM8 FC image for field {:s} virtspw {:s} has a peak SNR of {:#.5g} which is below the QA threshold.'.format(field, spw, peak_snr)
        shortmsg = 'MOM8 FC peak SNR below QA threshold'
        weblog_location = pqa.WebLogLocation.ACCORDION
    else:
        LOG.info('Image {:s} has {:d} pixels ({:.2f}%) above a threshold of {:.1f} x channel scaled MAD = {:#.5g}.'.format(os.path.basename(mom8_fc_name),
                                          n_outlier_pixels,
                                          outlier_fraction * 100.0,
                                          outlier_threshold,
                                          outlier_threshold * cube_chanScaled_MAD))

        m8fc_score_min = 0.33
        m8fc_score_max = 0.90
        m8fc_metric_scale = 300.0
        score = m8fc_score_min + 0.5 * (m8fc_score_max - m8fc_score_min) * (1.0 + erf(-np.log10(m8fc_metric_scale * outlier_fraction)))
        if 0.66 <= score <= 0.9 and peak_snr > 1.2 * outlier_threshold and n_outlier_pixels > 8:
            LOG.info('Modifying MOM8 FC score from {:.2f} to 0.65 due to peak SNR > 6.0 x channel scaled MAD and > 8 outlier pixels.'.format(score))
            score = 0.65

        if 0.33 <= score < 0.66:
            longmsg = 'MOM8 FC image for field {:s} spw {:s} with a peak SNR of {:#.5g} indicates that there may be residual line emission in the findcont channels.'.format(field, spw, peak_snr)
            shortmsg = 'MOM8 FC image indicates residual line emission'
            weblog_location = pqa.WebLogLocation.UNSET
        else:
            longmsg = 'MOM8 FC image for field {:s} spw {:s} has a peak SNR of {:#.5g} which is above the QA threshold.'.format(field, spw, peak_snr)
            shortmsg = 'MOM8 FC peak SNR above QA threshold'
            weblog_location = pqa.WebLogLocation.ACCORDION

    origin = pqa.QAOrigin(metric_name='score_mom8_fc_image',
                          metric_score=(peak_snr, outlier_fraction),
                          metric_units='Peak SNR / Outlier fraction')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin, weblog_location=weblog_location)
