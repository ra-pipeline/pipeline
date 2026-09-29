"""Common / Base QA score calculators and utilities."""

from __future__ import annotations

import collections
import datetime
import functools
import operator
import os
from typing import TYPE_CHECKING, Any

import pipeline.infrastructure.pipelineqa as pqa
from pipeline import infrastructure
from pipeline.domain import measures
from pipeline.infrastructure import basetask, casa_tools, utils
from pipeline.infrastructure.renderer import rendererutils
from pipeline.infrastructure.utils import ous_parallactic_range

if TYPE_CHECKING:
    from pipeline.domain.measurementset import MeasurementSet

LOG = infrastructure.logging.get_logger(__name__)

# struct to hold flagging statistics
AgentStats = collections.namedtuple('AgentStats', 'name flagged total')

__all__ = [
    'AgentStats',
    'calc_flags_per_agent',
    'calc_frac_newly_flagged',
    'calc_frac_total_flagged',
    'linear_score',
    'log_qa',
    'score_applycal_agents',
    'score_applycmds_exist',
    'score_caltables_exist',
    'score_contiguous_session',
    'score_data_flagged_by_agents',
    'score_ephemeris_coordinates',
    'score_file_exists',
    'score_flags_exist',
    'score_fraction_newly_flagged',
    'score_iersstate',
    'score_images_exist',
    'score_missing_intents',
    'score_ms_history_entries_present',
    'score_ms_model_data_column_present',
    'score_mses_exist',
    'score_online_shadow_template_agents',
    'score_parallactic_angle_range',
    'score_parallactic_range',
    'score_path_exists',
    'score_renorm',
    'score_science_spw_names',
    'score_total_data_flagged',
    'score_tsysspwmap',
]


def log_qa(method):
    """Decorator that logs QA evaluations as they return with a log level of
    INFO for scores between perfect and 'slightly suboptimal' scores and
    WARNING for any other level. These messages are meant for pipeline runs
    without a weblog output.
    """

    @functools.wraps(method)
    def f(self, *args, **kw):
        # get the size of the CASA log before task execution
        qascore = method(self, *args, **kw)
        if basetask.DISABLE_WEBLOG:
            if isinstance(qascore, tuple):
                _qascore = qascore[0]
            else:
                _qascore = qascore
            if _qascore.score >= rendererutils.SCORE_THRESHOLD_SUBOPTIMAL:
                LOG.info(_qascore.longmsg)
            else:
                LOG.warning(_qascore.longmsg)
        return qascore

    return f


def calc_flags_per_agent(summaries, scanids=None):
    """Calculate flagging statistics per agents. If scanids are provided,
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
        stat = AgentStats(name=summary['name'], flagged=flagcount, total=totalcount)
        stats.append(stat)

        # Keep count of total number of flags found in summaries, for
        # subsequent summaries.
        flagsum += flagcount

    return stats


def calc_frac_total_flagged(summaries, agents=None, scanids=None):
    """Calculate total fraction of data that is flagged. If agents are provided,
    then restrict to statistics for those agents. If scanids are provided,
    then restrict to statistics for those scans.
    """
    agent_stats = calc_flags_per_agent(summaries, scanids=scanids)

    # sum the number of flagged rows for the selected agents
    frac_flagged = functools.reduce(
        operator.add, [float(s.flagged) / s.total for s in agent_stats if not agents or s.name in agents], 0
    )

    return frac_flagged


def calc_frac_newly_flagged(summaries, agents=None, scanids=None):
    """Calculate fraction of data that is newly flagged, i.e. exclude pre-existing
    flags (assumed to be represented in first summary). If agents are provided,
    then restrict to statistics for those agents. If scanids are provided,
    then restrict to statistics for those scans.
    """
    agent_stats = calc_flags_per_agent(summaries, scanids=scanids)

    # sum the number of flagged rows for the selected agents
    frac_flagged = functools.reduce(
        operator.add, [float(s.flagged) / s.total for s in agent_stats[1:] if not agents or s.name in agents], 0
    )

    return frac_flagged


def linear_score(x: float, x1: float, x2: float, y1: float = 0.0, y2: float = 1.0) -> float:
    """Calculate the score for the given data value using linear scaling.

    Computes a linearly interpolated score between two boundary points (x1, y1) and (x2, y2).
    The input value x is automatically clipped to lie within the range [min(x1, x2), max(x1, x2)].

    Args:
        x: The input data value to score.
        x1: The first boundary x-coordinate.
        x2: The second boundary x-coordinate.
        y1: The score corresponding to x1.
        y2: The score corresponding to x2.

    Returns:
        The linearly interpolated score value.

    Examples:
        >>> linear_score(0.5, 0.0, 1.0)  # Midpoint between 0 and 1
        0.5
        >>> linear_score(1.5, 0.0, 1.0)  # Clipped to upper bound
        1.0
        >>> linear_score(-0.5, 0.0, 1.0)  # Clipped to lower bound
        0.0

    Raises:
        ZeroDivisionError: When x1 equals x2 (no valid interpolation range).
    """
    # Ensure all inputs are float type for consistent arithmetic
    x, x1, x2, y1, y2 = map(float, [x, x1, x2, y1, y2])

    # Handle edge case to prevent division by zero
    if x1 == x2:
        raise ZeroDivisionError('Cannot interpolate when x1 equals x2 (zero-width interval)')

    # Clip x to valid interpolation range
    x_min, x_max = (x1, x2) if x1 <= x2 else (x2, x1)
    x_clipped = max(x_min, min(x_max, x))

    # Linear interpolation formula: y = y1 + (y2 - y1) * (x - x1) / (x2 - x1)
    return y1 + (y2 - y1) * (x_clipped - x1) / (x2 - x1)


def score_data_flagged_by_agents(ms, summaries, min_frac, max_frac, agents=None, intents=None):
    """Calculate a score for the agentflagger summaries based on the fraction of
    data flagged by certain flagging agents. If intents are provided, then
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
    frac_flagged = calc_frac_total_flagged(summaries, agents=agents, scanids=scanids)

    # Convert fraction of flagged data into a score.
    score = linear_score(frac_flagged, min_frac, max_frac, 1.0, 0.0)

    # Set score messages and origin.
    percent = 100.0 * frac_flagged
    longmsg = '{:.2f}% data in {} flagged'.format(percent, ms.basename)
    if agents:
        longmsg += ' by {} flagging agents'.format(utils.commafy(agents, quotes=False))
    if intents:
        longmsg += ' for intent(s): {}.'.format(utils.commafy(intents, quotes=False))
    shortmsg = '%0.2f%% data flagged' % percent

    origin = pqa.QAOrigin(
        metric_name='score_data_flagged_by_agents',
        metric_score=frac_flagged,
        metric_units='Fraction of data newly flagged',
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


def score_ms_model_data_column_present(all_mses, mses_with_column):
    """Give a score for a group of mses based on the number with modeldata
    columns present.
    None with modeldata - 100% with modeldata = 1.0 -> 0.5
    """
    num_with = len(mses_with_column)
    num_all = len(all_mses)

    if num_all == 0:
        return pqa.QAScore(0.0, 'No MSes were imported', 'No MSes imported')

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
        longmsg = 'No model data column found in %s' % s
        shortmsg = 'MODELDATA empty'

    score = linear_score(f, 0.0, 1.0, 1.0, 0.9)

    origin = pqa.QAOrigin(
        metric_name='score_ms_model_data_column_present',
        metric_score=f,
        metric_units='Fraction of MSes with modeldata columns present',
    )

    return pqa.QAScore(score, longmsg, shortmsg, origin=origin)


@log_qa
def score_ms_history_entries_present(all_mses, mses_with_history):
    """Give a score for a group of mses based on the number with history
    entries present.
    None with history - 100% with history = 1.0 -> 0.5
    """
    num_with = len(mses_with_history)
    num_all = len(all_mses)

    if num_all == 0:
        return pqa.QAScore(0.0, 'No MSes were imported', 'No MSes imported')

    if mses_with_history:
        # log a message like 'Entries were found in the HISTORY table for
        # a.ms and b.ms'
        basenames = utils.commafy([ms.basename for ms in mses_with_history], quotes=False)
        if len(mses_with_history) == 1:
            longmsg = (
                'Unexpected entries were found in the HISTORY table of %s. '
                'This measurement set may already be processed.' % basenames
            )
        else:
            longmsg = (
                'Unexpected entries were found in the HISTORY tables of %s. '
                'These measurement sets may already be processed.' % basenames
            )
        shortmsg = '%s/%s have HISTORY' % (num_with, num_all)

    else:
        # log a message like 'No history entries were found in a.ms or b.ms'
        basenames = [ms.basename for ms in all_mses]
        s = utils.commafy(basenames, quotes=False, conjunction='or')
        longmsg = 'No HISTORY entries found in %s' % s
        shortmsg = 'No HISTORY entries'

    f = float(num_with) / num_all
    score = linear_score(f, 0.0, 1.0, 1.0, 0.5)

    origin = pqa.QAOrigin(
        metric_name='score_ms_history_entries_present', metric_score=f, metric_units='Fraction of MSes with HISTORY'
    )

    return pqa.QAScore(score, longmsg, shortmsg, origin=origin)


@log_qa
def score_missing_intents(mses, array_type='ALMA_12m'):
    """Score a MeasurementSet object based on the presence of certain
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
            'AMPLITUDE': -1.0,
        }
    else:
        score_map = {'PHASE': -0.7, 'BANDPASS': -0.7, 'AMPLITUDE': -0.7}

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
                score += score_map[m] / num_mses

            longmsg = '%s is missing %s calibration intents' % (ms.basename, utils.commafy(missing, False))
            complaints.append(longmsg)

            applies_to.add(ms.basename)

    if all_ok:
        longmsg = 'All required calibration intents were found in %s.' % utils.commafy(
            [ms.basename for ms in mses], False
        )
        shortmsg = 'All calibrators found'
        applies_to = {ms.basename for ms in mses}
    else:
        longmsg = '%s.' % utils.commafy(complaints, False)
        shortmsg = 'Calibrators missing'

    origin = pqa.QAOrigin(
        metric_name='score_missing_intents',
        metric_score=score,
        metric_units='Score based on missing calibration intents',
    )

    return pqa.QAScore(
        max(0.0, score),
        longmsg=longmsg,
        shortmsg=shortmsg,
        origin=origin,
        applies_to=pqa.TargetDataSelection(vis=applies_to),
    )


@log_qa
def score_ephemeris_coordinates(mses):
    """Score a MeasurementSet object based on the presence of possible
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
                score += -1.0 / num_mses
                longmsg = (
                    'Suspicious source coordinates for  %s in %s. Check whether position of '
                    '00:00:00.0+00:00:00.0 is valid.' % (source.name, ms.basename)
                )
                complaints.append(longmsg)
                applies_to.add(ms.basename)

    if all_ok:
        longmsg = 'All source coordinates OK in %s.' % utils.commafy([ms.basename for ms in mses], False)
        shortmsg = 'All source coordinates OK'
        applies_to = {ms.basename for ms in mses}
    else:
        longmsg = '%s.' % utils.commafy(complaints, False)
        shortmsg = 'Suspicious source coordinates'

    origin = pqa.QAOrigin(
        metric_name='score_ephemeris_coordinates',
        metric_score=score,
        metric_units='Score based on presence of ephemeris coordinates',
    )

    return pqa.QAScore(
        max(0.0, score),
        longmsg=longmsg,
        shortmsg=shortmsg,
        origin=origin,
        applies_to=pqa.TargetDataSelection(vis=applies_to),
    )


@log_qa
def score_online_shadow_template_agents(ms, summaries):
    """Get a score for the fraction of data flagged by online, shadow, and template agents.

    0 < score < 1 === 60% < frac_flagged < 5%
    """
    score = score_data_flagged_by_agents(
        ms, summaries, 0.24, 0.79, agents=['online', 'shadow', 'qa0', 'qa2', 'before', 'template']
    )

    new_origin = pqa.QAOrigin(
        metric_name='score_online_shadow_template_agents',
        metric_score=score.origin.metric_score,
        metric_units='Fraction of data newly flagged by online, shadow, and template agents',
    )
    score.origin = new_origin

    return score


@log_qa
def score_applycal_agents(ms, summaries):
    """Get a score for the fraction of data flagged by applycal agents.

    0 < score < 1 === 60% < frac_flagged < 5%
    """
    agents = ['applycal']
    intents = ['TARGET']

    # Get score for 'applycal' agent and 'TARGET' intent.
    score = score_data_flagged_by_agents(ms, summaries, 0.24, 0.79, agents=agents, intents=intents)
    perc_flagged = 100.0 * score.origin.metric_score

    # Get score for all agents (total) for 'TARGET' intent.
    dummy_score = score_data_flagged_by_agents(ms, summaries, 0, 1, intents=['TARGET'])
    total_perc_flagged = 100.0 * (1.0 - dummy_score.score)

    # Recreate the long message from the applycal score to also mention the total
    # percentage flagged.
    longmsg = (
        'For {}, intent(s): {}, {:.2f}% of the data was newly flagged by {} flagging agents, for a total of'
        ' {:.2f}% flagged.'.format(
            ms.basename,
            utils.commafy(intents, quotes=False),
            perc_flagged,
            utils.commafy(agents, quotes=False),
            total_perc_flagged,
        )
    )
    score.longmsg = longmsg

    # Update origin.
    new_origin = pqa.QAOrigin(
        metric_name='score_applycal_agents',
        metric_score=score.origin.metric_score,
        metric_units=score.origin.metric_units,
    )
    score.origin = new_origin

    return score


@log_qa
def score_total_data_flagged(filename, summaries):
    """Calculate a score for the flagging task based on the total fraction of
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

    origin = pqa.QAOrigin(
        metric_name='score_total_data_flagged',
        metric_score=frac_flagged,
        metric_units='Total fraction of data that is flagged',
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=os.path.basename(filename), origin=origin)


@log_qa
def score_fraction_newly_flagged(filename, summaries, vis):
    """Calculate a score for the flagging task based on the fraction of
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

    origin = pqa.QAOrigin(
        metric_name='score_fraction_newly_flagged',
        metric_score=frac_flagged,
        metric_units='Fraction of data that is newly flagged',
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=os.path.basename(vis), origin=origin)


@log_qa
def score_contiguous_session(mses, tolerance=datetime.timedelta(hours=1)):
    """Check whether measurement sets are contiguous in time."""
    # only need to check when given multiple measurement sets
    if len(mses) < 2:
        origin = pqa.QAOrigin(
            metric_name='score_contiguous_session',
            metric_score=0,
            metric_units='Non-contiguous measurement sets present',
        )
        return pqa.QAScore(
            1.0,
            longmsg='%s forms one continuous observing session.' % mses[0].basename,
            shortmsg='Unbroken observing session',
            vis=mses[0].basename,
            origin=origin,
        )

    # reorder MSes by start time
    by_start = sorted(mses, key=lambda m: utils.get_epoch_as_datetime(m.start_time))

    # create an interval for each one, including our tolerance
    intervals = []
    for ms in by_start:
        start = utils.get_epoch_as_datetime(ms.start_time)
        end = utils.get_epoch_as_datetime(ms.end_time)
        interval = measures.TimeInterval(start - tolerance, end + tolerance)
        intervals.append(interval)

    # check whether the intervals overlap
    bad_mses = []
    for i, (interval1, interval2) in enumerate(zip(intervals[0:-1], intervals[1:])):
        if not interval1.overlaps(interval2):
            bad_mses.append(utils.commafy([by_start[i].basename, by_start[i + 1].basename]))

    if bad_mses:
        basenames = utils.commafy(bad_mses, False)
        longmsg = 'Measurement sets %s are not contiguous. They may be miscalibrated as a result.' % basenames
        shortmsg = 'Gaps between observations'
        score = 0.5
    else:
        basenames = utils.commafy([ms.basename for ms in mses])
        longmsg = 'Measurement sets %s are contiguous.' % basenames
        shortmsg = 'Unbroken observing session'
        score = 1.0

    origin = pqa.QAOrigin(
        metric_name='score_contiguous_session',
        metric_score=not bool(bad_mses),
        metric_units='Non-contiguous measurement sets present',
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_tsysspwmap(ms, unmappedspws):
    """Score is equal to the fraction of unmapped windows"""
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
        longmsg = 'Tsys spw map is incomplete for %s science window%s ' % (
            ms.basename,
            utils.commafy(unmappedspws, False, 's'),
        )
        shortmsg = 'Tsys spw map is incomplete'

    origin = pqa.QAOrigin(
        metric_name='score_tsysspwmap', metric_score=score, metric_units='Fraction of unmapped Tsys windows'
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_path_exists(mspath, path, pathtype):
    """Score the existence of the path
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

    origin = pqa.QAOrigin(metric_name='score_path_exists', metric_score=bool(score), metric_units='Path exists on disk')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_file_exists(filedir, filename, filetype):
    """Score the existence of a products file
    1.0 if it exists
    0.0 if it does not
    """
    if filename is None:
        score = 1.0
        longmsg = 'The %s file is undefined' % filetype
        shortmsg = 'The %s file is undefined' % filetype

        origin = pqa.QAOrigin(
            metric_name='score_file_exists', metric_score=None, metric_units='No %s file to check' % filetype
        )

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

    origin = pqa.QAOrigin(metric_name='score_file_exists', metric_score=bool(score), metric_units='File exists on disk')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_mses_exist(filedir, visdict):
    """Score the existence of the flagging products files
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

    origin = pqa.QAOrigin(
        metric_name='score_mses_exist', metric_score=len(missing), metric_units='Number of missing ms product files'
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_flags_exist(filedir, visdict):
    """Score the existence of the flagging products files
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

    origin = pqa.QAOrigin(
        metric_name='score_flags_exist',
        metric_score=len(missing),
        metric_units='Number of missing flagging product files',
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_applycmds_exist(filedir, visdict):
    """Score the existence of the apply commands products files
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

    origin = pqa.QAOrigin(
        metric_name='score_applycmds_exist',
        metric_score=len(missing),
        metric_units='Number of missing apply command files',
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_caltables_exist(filedir, sessiondict):
    """Score the existence of the caltables products files
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

    origin = pqa.QAOrigin(
        metric_name='score_caltables_exist', metric_score=len(missing), metric_units='Number of missing caltables'
    )

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

    origin = pqa.QAOrigin(
        metric_name='score_images_exist', metric_score=metric, metric_units='Number of exported images'
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


def score_renorm(result):
    if result.renorm_applied:
        msg = 'Restore successful with renormalization applied'
        score = rendererutils.SCORE_THRESHOLD_SUBOPTIMAL
    else:
        msg = 'Restore successful'
        score = 1.0

    origin = pqa.QAOrigin(metric_name='score_renormalize', metric_score=score, metric_units='')
    return pqa.QAScore(score, longmsg=msg, shortmsg=msg, origin=origin)


@log_qa
def score_iersstate(mses: list[MeasurementSet]) -> list[pqa.QAScore]:
    """Check state of IERS tables relative to observation date"""
    iers_info = utils.IERSInfo()
    # reorder MSes by start time
    by_start = sorted(mses, key=lambda m: utils.get_epoch_as_datetime(m.start_time))

    # create an interval for each one, including our tolerance
    scores = []
    for ms in by_start:
        longmsg = f'Dates for {ms.basename} fully covered by IERSeop2000.'
        shortmsg = 'MS dates fully covered by IERSeop2000.'
        time_end = utils.get_epoch_as_datetime(ms.end_time)

        if iers_info.validate_date(time_end):
            score = 1.0
        elif iers_info.date_message_type(time_end) == 'INFO':
            score = 0.9
            longmsg = f'Dates for {ms.basename} not fully covered by IERSeop2000. CASA will use IERSpredict.'
            shortmsg = 'MS dates not fully covered by IERSeop2000. CASA will use IERSpredict.'
        elif iers_info.date_message_type(time_end) == 'WARN':
            score = 0.5
            longmsg = f'Dates for {ms.basename} not fully covered by IERSeop2000. CASA will use IERSpredict.'
            shortmsg = 'MS dates not fully covered by IERSeop2000. CASA will use IERSpredict.'
        else:
            score = 0.3
            longmsg = f'Dates for {ms.basename} not fully covered by IERSeop2000. Please update your data repository.'
            shortmsg = 'MS dates not fully covered by IERSpredict. Please update your data repository.'

        origin = pqa.QAOrigin(
            metric_name='score_iersstate',
            metric_score=score,
            metric_units='state of IERS tables relative to observation date',
        )

        scores.append(pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin))

    return scores


@log_qa
def score_parallactic_range(
    pol_intents_present: bool, session_name: str, field_name: str, coverage: float, threshold: float
) -> list[pqa.QAScore]:
    """Score a session based on parallactic angle coverage.

    Issues a warning if the parallactic coverage < threshold. See PIPE-597
    for full spec.
    """
    # holds the final list of QA scores
    scores: list[pqa.QAScore] = []

    # are polarisation intents expected? true if pol recipe, false if not
    # Polcal detected in session (this function was called!) but this is not a
    # polcal recipe, hence nothing to check
    if not pol_intents_present:
        longmsg = (
            f'No polarisation intents detected. No parallactic angle coverage check required for session '
            f'{session_name}.'
        )
        shortmsg = 'Parallactic angle'
        origin = pqa.QAOrigin(metric_name='ScoreParallacticAngle', metric_score=0.0, metric_units='degrees')
        score = pqa.QAScore(
            1.0,
            longmsg=longmsg,
            shortmsg=shortmsg,
            origin=origin,
            weblog_location=pqa.WebLogLocation.ACCORDION,
            applies_to=pqa.TargetDataSelection(session={session_name}),
        )
        return [score]

    if coverage is None:
        longmsg = (
            f'Cannot determine parallactic angle for polarisation calibrator {field_name} in session {session_name}'
        )
        shortmsg = 'Parallactic angle'
        origin = pqa.QAOrigin(
            metric_name='ScoreParallacticAngle',
            metric_score=0,
        )
        score = pqa.QAScore(
            0.0,
            longmsg=longmsg,
            shortmsg=shortmsg,
            origin=origin,
            weblog_location=pqa.WebLogLocation.ACCORDION,
            applies_to=pqa.TargetDataSelection(session={session_name}),
        )
        scores.append(score)
        return scores

    # accordion message if coverage is adequate
    if coverage >= threshold:
        longmsg = (
            f'Sufficient parallactic angle coverage ({coverage:.2f}\u00b0 > {threshold:.2f}\u00b0) for '
            f'polarisation calibrator {field_name} in session {session_name}'
        )
        shortmsg = 'Parallactic angle'
        origin = pqa.QAOrigin(metric_name='ScoreParallacticAngle', metric_score=coverage, metric_units='degrees')
        score = pqa.QAScore(
            1.0,
            longmsg=longmsg,
            shortmsg=shortmsg,
            origin=origin,
            weblog_location=pqa.WebLogLocation.ACCORDION,
            applies_to=pqa.TargetDataSelection(session={session_name}),
        )
        scores.append(score)

    # complain with a banner message if coverage is insufficient
    else:
        longmsg = (
            f'Insufficient parallactic angle coverage ({coverage:.2f}\u00b0 < {threshold:.2f}\u00b0) for '
            f'polarisation calibrator {field_name} in session {session_name}'
        )
        shortmsg = 'Parallactic angle'
        origin = pqa.QAOrigin(metric_name='ScoreParallacticAngle', metric_score=coverage, metric_units='degrees')
        score = pqa.QAScore(
            0.6,
            longmsg=longmsg,
            shortmsg=shortmsg,
            origin=origin,
            weblog_location=pqa.WebLogLocation.BANNER,
            applies_to=pqa.TargetDataSelection(session={session_name}),
        )
        scores.append(score)

    return scores


def score_parallactic_angle_range(
    mses: list[MeasurementSet], intents: set[str], threshold: float
) -> tuple[list[pqa.QAScore], dict[str, Any]]:
    """Check that the parallactic angle coverage of the intent(s) meets the required threshold.

    Args:
        mses: a list of MeasurementSet objects
        intents: a set containing all data intent(s) to check for
        threshold: the minimum acceptable value of parallactic angle coverage

    Returns:
        a tuple containing a list of QA scores and a dictionary with information related to the
         parallactic angle of the intent(s)
    """
    # holds list of all QA scores for this metric
    all_scores: list[pqa.QAScore] = []
    # holds all parallactic angle ranges for all
    # session names, intents and calibrator names
    all_metrics = {'sessions': {}, 'intents_found': False}

    intents_present = any([intents.intersection(ms.intents) for ms in mses])

    # group MSes per sessions, adding to default 'Shared' session if not
    # defined
    session_to_mses = collections.defaultdict(list)
    for ms in mses:
        session_to_mses[getattr(ms, 'session', 'Shared')].append(ms)

    # Check parallactic angle for each calibrator in each session
    for session_name, session_mses in session_to_mses.items():
        all_metrics['sessions'][session_name] = {
            'min_parang_range': 360.0,
            'vis': [ms_do.name for ms_do in session_mses],
        }
        for intent in intents:
            all_metrics['sessions'][session_name][intent] = {}
            cal_names = {cal.name for ms in session_mses for cal in ms.get_fields(intent=intent)}
            if len(cal_names) > 0:
                all_metrics['intents_found'] = True
            for cal_name in cal_names:
                parallactic_range = ous_parallactic_range(session_mses, cal_name, intent)
                if parallactic_range is not None:
                    all_metrics['sessions'][session_name][intent][cal_name] = parallactic_range
                    all_metrics['sessions'][session_name]['min_parang_range'] = min(
                        all_metrics['sessions'][session_name]['min_parang_range'], parallactic_range
                    )
                LOG.info(
                    f'Parallactic angle range for {cal_name} ({intent}) in session {session_name}: {parallactic_range}'
                )
                session_scores = score_parallactic_range(
                    intents_present, session_name, cal_name, parallactic_range, threshold
                )
                all_scores.extend(session_scores)

    return all_scores, all_metrics


@log_qa
def score_science_spw_names(mses, virtual_science_spw_names):
    """Check that all MSs have the same set of spw names. If this is
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
            msgs.append(
                'Science spw names {0} of EB {1} do not match spw names of first EB.'.format(
                    ','.join(spw_msgs), os.path.basename(ms.name).replace('.ms', '')
                )
            )

    if msgs == []:
        longmsg = 'Science spw names match virtual spw lookup table'
        shortmsg = 'Science spw names match'
    else:
        longmsg = '{0} Virtual spw ID mapping will not work.'.format(' '.join(msgs))
        shortmsg = 'Science spw names do not match'

    origin = pqa.QAOrigin(
        metric_name='score_spwnames', metric_score=score, metric_units='spw names match virtual spw name lookup table'
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)
