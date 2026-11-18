"""Single-dish (ALMA & Nobeyama) QA score calculators."""

from __future__ import annotations

import collections
import itertools
import operator
import os
from typing import TYPE_CHECKING

import numpy as np
from scipy import interpolate

import pipeline.infrastructure.pipelineqa as pqa
from pipeline import infrastructure
from pipeline.infrastructure import basetask, casa_tasks, casa_tools, utils
from pipeline.qa.common_scores import (
    linear_score,
    log_qa,
)

if TYPE_CHECKING:
    from casatools import coordsys
    from numpy.typing import NDArray

    from pipeline.domain.measurementset import MeasurementSet
    from pipeline.domain.singledish import MSReductionGroupMember
    from pipeline.hsd.heuristics.rasterscan import RasterScanHeuristicsResult
    from pipeline.hsd.tasks.applycal.applycal import SDApplycalResults
    from pipeline.hsd.tasks.baseline.baseline import SDBaselineResults
    from pipeline.hsd.tasks.flagging.flagdeteralmasd import PointingOutlierStats
    from pipeline.hsd.tasks.imaging.resultobjects import SDImagingResultItem
    from pipeline.hsd.tasks.importdata.importdata import SDImportDataResults
    from pipeline.infrastructure.launcher import Context

LOG = infrastructure.logging.get_logger(__name__)

__all__ = [
    '_rasterscan_failed_per_eb',
    '_score_rasterscan_correctness',
    'channel_ranges_for_image',
    'direction_recover',
    'examine_sd_edge_lines',
    'examine_sd_wide_lines',
    'generate_metric_mask',
    'get_line_ranges',
    'log_edge_channels',
    'score_amp_vs_time_plots',
    'score_pointing_outlier',
    'score_rasterscan_correctness_direction_domain_rasterscan_fail',
    'score_rasterscan_correctness_imaging_raster_analysis_incomplete',
    'score_rasterscan_correctness_imaging_raster_gap',
    'score_rasterscan_correctness_time_domain_rasterscan_fail',
    'score_sd_baseline_quality',
    'score_sd_line_detection',
    'score_sd_line_emission_off_range_at_peak',
    'score_sd_line_emission_off_range_extended',
    'score_sd_skycal_elevation_difference',
    'score_sdimage_contamination',
    'score_sdimage_masked_pixels',
    'score_sdimage_sensitivity_ratio',
    'score_sdtotal_data_flagged',
    'select_deviation_masks',
]


@log_qa
def score_sdtotal_data_flagged(
    frac_flagged: float, ms_name: str | None = None, field: str | None = None, spw: int | None = None
) -> pqa.QAScore:
    """Calculate a score for the flagging task based on the total fraction of
    data flagged.

    0%-5% flagged   -> 1.0
    5%-50% flagged  -> liearly interpolated between 1.0 and 0.0
    50-100% flagged -> 0.0

    Args:
        frac_flagged : flagged fraction
        ms_name : MS name
        field : field name
        spw : spectral window ID
    Returns:
        QAScore object
    """
    if frac_flagged > 0.5:
        score = 0
    else:
        score = linear_score(frac_flagged, 0.05, 0.5, 1.0, 0.5)

    percent = 100.0 * frac_flagged
    label = f'{ms_name} Field {field} Spw {spw}' if ms_name else f'Field {field} Spw {spw}'
    longmsg = f'{percent:.2f}% of data in {label} was newly flagged'
    shortmsg = f'{percent:.2f}% of data newly flagged'
    origin = pqa.QAOrigin(
        metric_name='score_sdtotal_data_flagged',
        metric_score=frac_flagged,
        metric_units='Fraction of data newly flagged',
    )

    selection = pqa.TargetDataSelection(
        vis={ms_name} if ms_name is not None else None,
        field={field} if field is not None else None,
        spw={spw} if spw is not None else None,
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin, applies_to=selection)


def get_line_ranges(lines: list[list[float | bool]]) -> list[tuple[int, int]]:
    """Get valid line ranges from list of line properties.

    Args:
        lines: List of lines. Each line is expressed as at least three
               values, [center, width, validity_flag], where the line
               is regarded as valid if validity_flag is True.

    Returns:
        List of (start, end) channels for valid lines
    """
    line_ranges = []
    for line in lines:
        center, width, is_valid = line[:3]
        if is_valid:
            chan_left = int(np.floor(center - width / 2 + 0.5))
            chan_right = int(np.floor(center + width / 2 + 0.5))
            line_ranges.append((chan_left, chan_right))

    return line_ranges


def examine_sd_edge_lines(line_ranges: list[tuple[int, int]], nchan: int, edge: tuple[int, int] = (0, 0)) -> float:
    """Examine the existence of lines at edge channels.

    This function checks if there are lines that spans edge channels.
    Excluded channels via edge parameter are taken into account.

    Args:
        line_ranges: List of line ranges
        nchan: Number of channels
        edge: Number of edge channels excluded from both sides

    Returns:
        True if there are lines that satisfy the condition above.
        Otherwise, False.
    """
    chan_leftmost = min(line[0] for line in line_ranges)
    chan_rightmost = max(line[1] for line in line_ranges)
    LOG.debug(
        'leftmost %s, rightmost %s, nchan %s, edge (%s, %s)', chan_leftmost, chan_rightmost, nchan, edge[0], edge[1]
    )
    return chan_leftmost <= edge[0] or nchan - 1 - edge[1] <= chan_rightmost


def examine_sd_wide_lines(line_ranges: list[tuple[int, int]], nchan: int, edge: tuple[int, int] = (0, 0)) -> float:
    """Examine the existence of wide lines.

    This function returns True if there is a line with the width
    exceeding 1/3 of spw bandwidth. If there are multiple lines
    and their coverage exceeds the criterion *in total*, the
    function also returns True. Otherwise, it returns False.
    Excluded channels via edge parameter are taken into account.

    Args:
        line_ranges: List of line ranges
        nchan: Number of channels
        edge: Number of edge channels excluded from both sides

    Returns:
        True if wide line exists. Otherwise, Flase. Please see
        the above description on more detailed explanation of
        return value.
    """
    # see PIPEREQ-304 for the origin of the value
    fraction = 1 / 3

    mask = np.zeros(nchan, dtype=np.uint8)
    for line in line_ranges:
        ch_start = max(line[0], 0)
        ch_end = min(line[1], nchan - 1) + 1
        mask[ch_start:ch_end] = 1

    start = edge[0]
    end = nchan - edge[1]
    effective_nchan = nchan - sum(edge)
    line_coverage = np.sum(mask[start:end])
    LOG.debug(
        'line coverage %s, threshold %.1f, (effective nchan %s, fraction %s), edge (%s, %s)',
        line_coverage,
        effective_nchan * fraction,
        effective_nchan,
        fraction,
        edge[0],
        edge[1],
    )

    return line_coverage > effective_nchan * fraction


def select_deviation_masks(
    deviation_masks: dict, reduction_group_member: 'MSReductionGroupMember'
) -> list[tuple[int, int]]:
    """Select deviation masks that belongs to given reduction group member.

    Args:
        deviation_masks: List of all deviation masks
        reduction_group_member: Reduction group member instance

    Returns:
        List of (start, end) channels for selected deviation masks
    """
    ms_name = reduction_group_member.ms.basename
    field_id = reduction_group_member.field_id
    spw_id = reduction_group_member.spw_id
    antenna_id = reduction_group_member.antenna_id
    return deviation_masks[ms_name].get((field_id, antenna_id, spw_id), [])


def channel_ranges_for_image(
    edge: tuple[int, int], nchan: int, sideband: int, ranges: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Convert channel ranges in MS coordinate to those in image coordinate.

    Frequency coordinates are different between MS and image product.
    This method converts channel ranges in MS coordinate into the ranges
    in image coordinate. The conversion includes the following operations.

        - to reverse channels if spw is LSB
        - to shift channels by the amount specified by edge parameter

    Args:
        edge: Number of edge channels excluded
        nchan: Number of channels
        sideband: 1 for USB, -1 for LSB
        ranges: List of two tuples representing channel ranges

    Returns:
        Converted channel ranges
    """
    edge_left, edge_right = edge

    if sideband == -1:
        # LSB
        chan_offset = edge_right

        def _reverse_range(x):
            return nchan - 1 - x

        _ranges_image = (map(_reverse_range, x[::-1]) for x in ranges)

    else:
        # USB
        chan_offset = edge_left

        _ranges_image = ranges

    # offset channel ranges
    def _offset_range(x):
        return x - chan_offset

    _ranges_image = (map(_offset_range, x) for x in _ranges_image)

    return sorted(tuple(x) for x in _ranges_image)


@log_qa
def score_sd_line_detection(context: Context, result: SDBaselineResults) -> list[pqa.QAScore]:
    """Compute QA score based on detected lines and deviation/ATM mask overlaps.

    QA scores are evaluated based on the line detection result for
    each combination of spw and field individually. Scoring scheme of
    individual results are as follows:

        - Line detection:
            - 0.55 if lines extend to edge channels
            - 0.6 if lines cover more than 1/3 of SPW bandwidth
            - 1.0 otherwise
            - 0.8 if no lines were detected in any SPW/field (default)

        - Deviation masks:
            - 0.65 if deviation masks are present but do not overlap with lines
            - 0.88 if deviation masks overlap with detected spectral lines

        - Deviation mask and atmospheric lines:
            - 0.88 if deviation masks overlap with atmospheric lines

    Returned QAScore objects include metric values (channel ranges) and
    informative messages that distinguish between spectral lines,
    deviation masks, and atmospheric overlap. The function ensures that
    at least one score is returned, even if no lines are detected.

    Relevant JIRA tickets:
        PIPE-2136
        PIPE-2509
        PIPE-2530
        PIPEREQ-304

    Args:
        context: Pipeline Context
        result: Result object generated by hsd_baseline stage

    Returns:
        List of QAScore objects derived from line detection results
        and/or deviation masks, with atm lines, if available
    """

    def mask_to_ranges(mask: NDArray[np.bool_]) -> list[tuple[int, int]]:
        """Convert a boolean channel mask into a list of contiguous channel ranges.

        Parameters:
            mask: 1D boolean array where True indicates channels to include.

        Returns:
            List of (start, end) tuples for each contiguous run of True values in the mask.
        """
        idx = np.where(mask)[0]
        if idx.size == 0:
            return []
        groups = np.split(idx, np.where(np.diff(idx) != 1)[0] + 1)
        return [(grp[0], grp[-1]) for grp in groups]

    def make_score(
        score_val: float,
        msg: str,
        metric_val: str,
        metric_units: str,
        ms_name: str | None = None,
        field: str | None = None,
        spws: set[int] = None,
        ants: set[str] = None,
    ) -> pqa.QAScore:
        """Build a QAScore object for score_sd_line_detection.

        Parameters:
            score_val: The numeric QA score.
            msg: Description of the QA result.
            metric_val: The metric value of score.
            metric_units: Units for the metric_value.
            ms_name: Name of the Measurement Set (EB). (optional)
            field: Field name (optional).
            spws: Set of spectral window IDs (optional).
            ants: Set of antenna names (optional).

        Returns:
            A fully populated QAScore with long and short messages, origin (metric name/score/units),
            and target selection.
        """
        ms_str = f'EB {ms_name}' if ms_name else ''
        field_str = f'Field {field}' if field else ''
        spw_str = 'Spw ' + ', '.join(map(str, sorted(spws))) if spws else ''
        ant_str = 'Antenna ' + ', '.join(sorted(ants)) if ants else ''
        shortmsg = f'{msg}.'
        keys = ', '.join(filter(None, [ms_str, field_str, spw_str, ant_str]))
        longmsg = f'{msg} in {keys}.' if ms_name or field or spws or ants else shortmsg
        origin = pqa.QAOrigin(metric_name='score_sd_line_detection', metric_score=metric_val, metric_units=metric_units)
        selection = pqa.TargetDataSelection(
            vis={ms_name} if ms_name else None, spw=spws, field={field} if field else None, ant=ants, intent={'TARGET'}
        )
        return pqa.QAScore(score_val, longmsg=longmsg, shortmsg=shortmsg, origin=origin, applies_to=selection)

    reduction_group = context.observing_run.ms_reduction_group

    # Precompute ATM masks per MS/SPW
    import pipeline.hsd.heuristics.SDcalatmcorr as sdatm

    atm_masks = {}
    for bl in result.outcome['baselined']:
        for mid in bl['members']:
            rgm = reduction_group[bl['group_id']][mid]
            ms = rgm.ms.origin_ms
            if ms not in atm_masks:
                if rgm.ms.antenna_array.name == 'NRO':
                    atm_masks.setdefault(ms, {})
                    continue

                spwsetup = sdatm.getSpecSetup(rgm.ms.basename)
                spws = list(map(int, spwsetup['spwlist']))
                tau = sdatm.getTau(rgm.ms.basename, spws, spwsetup)
                skylines = {
                    spw: sdatm.getskylines(tau[spw], spw, spwsetup, fraclevel=0.3, minpeaklevel=0.05) for spw in spws
                }
                atm_masks[ms] = {spw: sdatm.skysel(skylines[spw], linestouse='all') for spw in spws}

    line_detection_scores, dm_scores = [], []

    # edge parameter for image channel mapping
    _edge = result.outcome['edge']
    edge_param = (_edge, _edge) if isinstance(_edge, int) else tuple(_edge[:2])

    # Process each baseline for line detection and DM
    for bl in result.outcome['baselined']:
        reduction_group_id = bl['group_id']
        reduction_group_desc = reduction_group[reduction_group_id]
        member_list = bl['members']
        field_name = reduction_group_desc.field_name

        # vspw_id and sideband are uniform among all the members in a reduction_group
        rgm = reduction_group_desc[member_list[0]]
        vspw_id = context.observing_run.real2virtual_spw_id(rgm.spw.id, rgm.ms)
        sideband = int(rgm.spw.sideband)  # sideband is 1 for USB, -1 for LSB,  rgm.spw.sideband is str

        nchan = reduction_group_desc.nchan
        # PIPE-2959/PIPE-2964 use channelmap_range for QA evaluation
        lines = get_line_ranges(bl['channelmap_range'])

        LOG.debug('Processing reduction group %s, field %s, vspw %s', reduction_group_id, field_name, vspw_id)

        # edge channels
        flagged_edges = bl['flagged_edges']

        # take max of edge channels from user inputs and
        # edge channels flagged by preceding stages
        LOG.info(f'vspw: {vspw_id}, edge_flagged: {flagged_edges}')
        edge = (max(flagged_edges[0], edge_param[0]), max(flagged_edges[1], edge_param[1]))

        # spectral-line scoring
        if len(lines) > 0:
            # sort lines by left channel
            lines.sort(key=operator.itemgetter(0))
            is_edge_line = examine_sd_edge_lines(lines, nchan, edge)
            is_wide_line = examine_sd_wide_lines(lines, nchan, edge)

            if is_edge_line and is_wide_line:
                score = 0.55  # min(0.55, 0.6)
                msg = 'Edge and wide lines were detected'
            elif is_edge_line:
                score = 0.55
                msg = 'Edge line was detected'
            elif is_wide_line:
                score = 0.6
                msg = 'Wide line was detected'
            else:
                # detected lines do not harm baseline subtraction
                score = 1.0
                msg = 'Line ranges were detected'
            lines_image = channel_ranges_for_image(edge, nchan, sideband, lines)
            metric_value = ';'.join([f'{left}~{right}' for left, right in lines_image])

            line_detection_scores.append(
                make_score(
                    score, msg, metric_value, 'Channel range(s) of detected lines', field=field_name, spws={vspw_id}
                )
            )

        # deviation-mask and ATM overlap
        for mid in member_list:
            rgm = reduction_group_desc[mid]
            dmlist = select_deviation_masks(result.outcome['deviation_mask'], rgm)
            if not dmlist:
                continue
            ndm = len(dmlist)
            ms, spw = rgm.ms.origin_ms, rgm.spw_id

            # build masks
            dm_masks = np.zeros((ndm, nchan), bool)
            for i, (l, r) in enumerate(dmlist):
                dm_masks[i, l : r + 1] = True
            line_mask = np.zeros(nchan, bool)
            for l, r in lines:
                line_mask[l : r + 1] = True
            atm_mask = atm_masks[ms].get(spw, np.zeros(nchan, bool))

            # DM scoring
            for dm_mask in dm_masks:
                ranges = mask_to_ranges(dm_mask)
                unit = 'Channel range(s) of deviation mask'
                dm_atm = dm_mask & atm_mask
                if np.any(line_mask & dm_mask):
                    score = 0.88
                    msg = 'Deviation mask overlapped with spectral lines'
                    LOG.debug('Deviation masks overlap with lines. Set deviation mask QA score to %s', score)
                # ATM-DM overlap
                elif np.any(dm_atm):
                    score = 0.88
                    msg = 'Deviation mask overlapped with atmospheric lines'
                    unit = 'Channel range(s) of DM/ATM/Spectral overlap'
                    LOG.debug('Deviation mask overlapped with atmospheric linesSet atm overlap QA score to %s', score)
                else:
                    score = 0.65
                    msg = 'Deviation mask was triggered'
                    LOG.debug('Found deviation mask with no overlapSet deviation mask QA score to %s', score)
                metric = ','.join(f'{l}~{r}' for l, r in ranges)
                dm_scores.append(make_score(score, msg, metric, unit, ms, field_name, {spw}, {rgm.antenna_name}))

    if len(line_detection_scores) == 0:
        # add new entry with score of 0.8 if no spectral lines
        # were detected in any spws/fields
        line_detection_scores.append(
            make_score(0.8, 'No line ranges were detected in all SPWs', 'N/A', 'Channel range(s) of detected lines')
        )

    return line_detection_scores + dm_scores


@log_qa
def score_sd_baseline_quality(vis: str, source: str, ant: str, vspw: str, pol: str, stat: list[tuple]) -> pqa.QAScore:
    """Return Pipeline QA score of baseline quality.

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
    metric_func = interpolate.interp1d(
        ramp_range, score_range, kind='linear', bounds_error=False, fill_value=score_range
    )
    for s in stat:
        diff_score = metric_func(s.bin_diff_ratio)
        scores.append(diff_score)
        LOG.info(f'rdiff = {s.bin_diff_ratio} -> score = {diff_score}')
    final_score = np.nanmin(scores)
    quality = 'Good'
    if final_score <= 0.66:
        quality = 'Poor'
    elif final_score <= 0.9:
        quality = 'Moderate'
    shortmsg = f'{quality} baseline flatness'
    longmsg = f'{quality} baseline flatness in {vis}, {source}, {ant}, virtual spw {vspw}, {pol}'
    origin = pqa.QAOrigin(
        metric_name='score_sd_baseline_quality', metric_score=len(stat), metric_units='Statistics of binned spectra'
    )
    selection = pqa.TargetDataSelection(vis={vis}, field={source}, spw={vspw}, ant={ant}, pol={pol}, intent={'TARGET'})

    return pqa.QAScore(final_score, longmsg=longmsg, shortmsg=shortmsg, origin=origin, applies_to=selection)


@log_qa
def score_sd_skycal_elevation_difference(
    ms: MeasurementSet,
    resultdict: dict,
    el_threshold: float,
) -> list[pqa.QAScore]:
    """Compute QA score based on elevation difference between ON and OFF scans.

    Metric for the scoring is the maximum elevation difference in degrees
    between ON and OFF scans among all the fields, antennas, and spws.
    The QA score is 0.8 if the maximum elevation difference exceeds the
    specified threshold, and 1.0 otherwise.

    Args:
        ms: MeasurementSet object
        resultdict: A dictionary containing elevation difference results
                    for each field, antenna, and spw.
        el_threshold: Elevation difference threshold in degrees for scoring.

    Returns:
        A QAScore object representing the QA score based on elevation
        difference, or None if no valid metric score is available.
    """
    field_ids = list(resultdict.keys())
    qascores = []

    for field_id in field_ids:
        field = ms.fields[field_id]
        if field_id not in resultdict:
            continue

        eldiffant = resultdict[field_id]
        for antenna_id, eldiff in eldiffant.items():
            for spw_id, eld in eldiff.items():
                metric_score = []
                preceding = eld.eldiff0
                subsequent = eld.eldiff1
                max_pred = None
                max_subq = None
                if len(preceding) > 0:
                    max_pred = np.abs(preceding).max()
                    metric_score.append(max_pred)
                if len(subsequent) > 0:
                    max_subq = np.abs(subsequent).max()
                    metric_score.append(max_subq)

                if len(metric_score) == 0:
                    # no valid metric score
                    # this typically happens when ON_SOURCE data are
                    # fully flagged while valid OFF_SOURCE data exist
                    continue

                max_metric_score = np.max(metric_score)
                if max_metric_score < el_threshold:
                    score = 1.0
                    ant = []
                    shortmsg = f'Elevation difference between ON and OFF is within {el_threshold} deg.'
                    longmsg = f'{shortmsg} for {ms.basename}: Field {field.name}'
                else:
                    score = 0.8
                    ant = [ms.antennas[antenna_id].name]
                    shortmsg = f'Elevation difference between ON and OFF exceeds {el_threshold} deg.'
                    longmsg = f'{shortmsg} for {ms.basename}: Field {field.name} Antenna {ant}'

                selection = pqa.TargetDataSelection(vis={ms.basename}, field={field.name}, ant=set(ant))
                origin = pqa.QAOrigin(
                    metric_name='OnOffElevationDifference', metric_score=float(max_metric_score), metric_units='deg'
                )

                qascore = pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin, applies_to=selection)
                qascores.append(qascore)

    return qascores


def log_edge_channels(imagename: str, nchan: int, edge_count_lower: int, edge_count_upper: int):
    """Print proper log message for detected edge channels.

    Args:
        imagename: Name of the input image
        nchan: Number of channels in the image
        edge_count_lower: Number of edge channels
                          excluded from the lower frequency side
        edge_count_upper: Number of edge channels
                          excluded from the higher frequency side
    """
    LOG.debug('nchan %s: edge lower %s, upper %s', nchan, edge_count_lower, edge_count_upper)
    edge_chan_list = []
    # lower edge channels
    if edge_count_lower == 1:
        edge_chan_list.append('0')
    elif edge_count_lower > 1:
        edge_chan_list.append(f'0~{edge_count_lower - 1}')

    # upper edge channels
    if edge_count_lower == nchan:
        # all the channels are invalid, should be covered
        # by edge_count_lower alone
        pass
    elif edge_count_upper == 1:
        edge_chan_list.append(f'{nchan - 1}')
    elif edge_count_upper > 1:
        edge_chan_list.append(f'{nchan - edge_count_upper}~{nchan - 1}')

    # emit log
    LOG.info(f'masked pixel QA for {imagename}: detected edge channels: {";".join(edge_chan_list)}')


def generate_metric_mask(
    context: Context,
    result: SDImagingResultItem,
    cs: coordsys,
    image_shape: NDArray[np.int_],
) -> NDArray[np.bool_]:
    """Generate boolean mask array for metric calculation in
    score_sdimage_masked_pixels. If image pixel contains
    observed points, mask will be True. Otherwise, mask is
    False.

    Arguments:
        context: Pipeline context
        result: result item created by hsd_imaging
        cs: CASA coordsys tool
        image_shape: Shape of the image

    Returns:
        bool array -- metric mask (True: valid, False: invalid)
    """
    outcome = result.outcome
    org_direction = outcome['image'].org_direction

    file_index = np.asarray(outcome['file_index'])
    antenna_list = np.asarray(outcome['assoc_antennas'])
    field_list = np.asarray(outcome['assoc_fields'])
    vspw_list = np.asarray(outcome['assoc_spws'])

    mses = context.observing_run.measurement_sets
    # avoid processing the same MS multiple times
    unique_file_index = np.unique(file_index)

    refval = cs.referencevalue()
    units = cs.units()
    metric_mask = np.zeros(image_shape, dtype=bool)

    for ms_id in unique_file_index:
        target_ms = mses[ms_id]
        origin_basename = os.path.basename(target_ms.origin_ms)
        datatable_name = os.path.join(context.observing_run.ms_datatable_name, origin_basename)
        rotable_name = os.path.join(datatable_name, 'RO')
        _index = np.where(file_index == ms_id)
        if len(_index[0]) == 0:
            continue

        _antlist = antenna_list[_index]
        _fieldlist = field_list[_index]
        _vspwlist = vspw_list[_index]

        # Here, we are trying to process data with the same field
        # and spw in one MS but from different antennas. Therefore,
        # field and spw should be unique in the list.
        field_id = _fieldlist[0]  # should be unique
        if not np.all(_fieldlist == field_id):
            LOG.warning(f'Multiple fields found in MS {target_ms.basename}: {_fieldlist}. Skip evaluating.')
            continue
        vspw_id = _vspwlist[0]  # should be unique
        if not np.all(_vspwlist == vspw_id):
            LOG.warning(f'Multiple SPWs found in MS {target_ms.basename}: {_vspwlist}. Skip evaluating.')
            continue
        spw_id = context.observing_run.virtual2real_spw_id(vspw_id, target_ms)

        with casa_tools.TableReader(rotable_name) as tb:
            taql = f'SRCTYPE==0 && ANTENNA IN {utils.list_to_str(_antlist)} && FIELD_ID == {field_id} && IF == {spw_id}'
            LOG.debug('MS: %s, TaQL string: %s', target_ms.basename, taql)
            tsel = tb.query(taql)
            ofs_ra = tsel.getcol('OFS_RA')
            ofs_dec = tsel.getcol('OFS_DEC')
            origin_ms_rows = tsel.getcol('ROW')
            tsel.close()

        if org_direction is None:
            ra_deg = ofs_ra
            dec_deg = ofs_dec
        else:
            ra_deg = np.empty(len(ofs_ra), dtype=float)
            dec_deg = np.empty(len(ofs_dec), dtype=float)
            for i, rr, dd in zip(range(len(ofs_ra)), ofs_ra, ofs_dec):
                shift_ra, shift_dec = direction_recover(rr, dd, org_direction)
                ra_deg[i] = shift_ra
                dec_deg[i] = shift_dec

        from pipeline.hsd.tasks.common import utils as sdutils

        rowmap = sdutils.make_row_map_between_ms(context.observing_run.get_ms(target_ms.origin_ms), target_ms.name)

        with casa_tools.TableReader(target_ms.name) as tb:
            flag = map(lambda irow: tb.getcell('FLAG', rowmap[irow]), origin_ms_rows)
            # invert flag: True for valid data
            ms_mask = map(lambda f: np.logical_not(f), flag)
            # data will contribute to the image if all polarizations are valid
            ms_mask_collapsed_pol = map(lambda f: np.all(f, axis=0), ms_mask)
            # data will contribute to the image if there are any valid channels
            ms_mask_per_row = map(lambda f: np.any(f), ms_mask_collapsed_pol)
            # validity mask for each row: True for valid data
            validity_mask = np.fromiter(ms_mask_per_row, dtype=bool)

        # world-pixel conversion using cs.topixelmany
        ra_deg = ra_deg[validity_mask]
        dec_deg = dec_deg[validity_mask]

        # skip if no valid data exists
        if len(ra_deg) == 0:
            LOG.info(
                f'No valid data in MS {target_ms.basename},'
                f' field {field_id}, spw {spw_id}, antenna {_antlist}.'
                f' Excluding the MS from mask evaluation.'
            )
            continue

        # unit should be either 'rad' or 'deg'
        deg2rad = np.pi / 180.0
        ra = ra_deg * deg2rad if units[0] == 'rad' else ra_deg
        dec = dec_deg * deg2rad if units[1] == 'rad' else dec_deg
        wpol = np.zeros(len(ra), dtype=float)
        wfreq = np.zeros(len(ra), dtype=float) + refval['numeric'][3]
        world_array = np.stack((ra, dec, wpol, wfreq))
        pixel_array = cs.topixelmany(world_array)['numeric']
        px = pixel_array[0]
        py = pixel_array[1]

        for x, y in zip(map(int, np.round(px)), map(int, np.round(py))):
            if 0 <= x and x <= image_shape[0] - 1 and 0 <= y and y <= image_shape[1] - 1:
                metric_mask[x, y, :, :] = True

    # exclude edge channels
    imagename = outcome['image'].imagename
    nchan = metric_mask.shape[3]
    edge_count_lower, edge_count_upper = outcome.get('extra_edge_channels', (0, 0))
    log_edge_channels(imagename, nchan, edge_count_lower, edge_count_upper)
    if edge_count_lower > 0:
        metric_mask[:, :, :, :edge_count_lower] = False
    if edge_count_upper > 0:
        metric_mask[:, :, :, -edge_count_upper:] = False

    return metric_mask


def direction_recover(ra, dec, org_direction):
    me = casa_tools.measures
    qa = casa_tools.quanta

    direction = me.direction(org_direction['refer'], str(ra) + 'deg', str(dec) + 'deg')
    zero_direction = me.direction(org_direction['refer'], '0deg', '0deg')
    offset = me.separation(zero_direction, direction)
    posang = me.posangle(zero_direction, direction)
    new_direction = me.shift(org_direction, offset=offset, pa=posang)
    new_ra = qa.convert(new_direction['m0'], 'deg')['value']
    new_dec = qa.convert(new_direction['m1'], 'deg')['value']

    return new_ra, new_dec


@log_qa
def score_sdimage_masked_pixels(context: Context, result: SDImagingResultItem) -> pqa.QAScore:
    """Evaluate QA score based on the fraction of masked pixels in image.

    Requirements (PIPE-249):
        - calculate the number of masked pixels in image
        - search area should be the extent of pointing direction
        - QA score should be
            1.0 (if the nuber of masked pixel == 0)
            0.5 (if any of the pixel in pointing area is masked)
            0.0 (if 10% of the pixels in pointing area are masked)
            *linearly interpolate between 0.5 and 0.0

    Arguments:
        context: Pipeline context
        result: Imaging result instance

    Returns:
        QAScore -- QAScore instance holding the score based on number of
                   masked pixels in image
    """
    # metric score is a fraction of masked pixels
    result_item = result.outcome
    image_item = result_item['image']
    imagename = image_item.imagename
    field = image_item.sourcename
    spw = result_item['assoc_spws']
    stokes = result_item['stokes']

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
        metric_mask = generate_metric_mask(context, result, cs, imageshape)
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
    eps = 1.0e-6

    # convert score and threshold for logging purpose
    frac2percentage = lambda x: '{:.4g}%'.format(x * 100)
    imbasename = os.path.basename(imagename.rstrip('/'))

    # force score=0.0 for inappropriate cases
    if metric_score > metric_score_max:
        # metric_score should not exceed 1.0. something wrong.
        _x = frac2percentage(metric_score_max)
        _y = frac2percentage(metric_score)
        lmsg = f'{imbasename}: fraction of number of masked pixels should not exceed {_x}. something went wrong.'
        smsg = f'Masked image pixels ({_y}) exceeds {_x}'
        score = 0.0
    elif metric_score < metric_score_min:
        lmsg = f'{imbasename}: No pixels associated with pointing data exist. something went wrong.'
        smsg = 'No data exists.'
        score = 0.0

    # deal with the realistic cases
    elif abs(metric_score - metric_score_min) < eps:
        lmsg = f'All examined pixels in image {imbasename} are valid.'
        smsg = 'All examined image pixels are valid.'
        score = 1.0
    elif metric_score > metric_score_threshold:
        _x = frac2percentage(metric_score_threshold)
        _y = frac2percentage(metric_score)
        lmsg = f'Fraction of masked pixels in image {imbasename} is {_y}, exceeding threshold value ({_x}).'
        smsg = f'Masked image pixels ({_y}) exceeds threshold of {_x}.'
        score = 0.0
    else:
        # interpolate between 0.5 and 0.0
        _x = frac2percentage(metric_score)
        lmsg = f'Fraction of masked pixels in image {imbasename} is {_x}.'
        smsg = f'{_x} of image pixels are masked.'
        smax = 0.5
        mmax = 0.0
        smin = 0.0
        mmin = 0.1
        score = (smax - smin) / (mmax - mmin) * (metric_score - mmin) + smin

    origin = pqa.QAOrigin(
        metric_name='SingleDishImageMaskedPixels',
        metric_score=metric_score,
        metric_units='Fraction of masked pixels in image',
    )
    selection = pqa.TargetDataSelection(field={field}, spw=set(spw), pol={stokes})

    return pqa.QAScore(score, longmsg=lmsg, shortmsg=smsg, origin=origin, applies_to=selection)


@log_qa
def score_sd_line_emission_off_range_at_peak(context: Context, result: SDImagingResultItem) -> pqa.QAScore:
    """Evaluate QA score based on the detection of off-line-range emission at peak.

    Requirements (PIPE-2416):
        - QA score should be
          - 0.6 if significant off-line-range emission is detected at peak
          - 1.0 if no significant off-line-range emission is detected at peak

    Args:
        context: Pipeline context
        result: Imaging result instance

    Returns:
        QAScore -- QAScore instance holding the score based on the Requirements
    """
    emission_off_range_at_peak = result.outcome.get('line_emission_off_range_at_peak', False)
    imageitem = result.outcome['image']
    field = imageitem.sourcename
    spw = ','.join(map(str, np.unique(imageitem.spwlist)))
    stokes = result.outcome['stokes']

    if emission_off_range_at_peak:
        lmsg = f'Field {field} Spw {spw}: Significant off-line-range emission is detected at peak.'
        smsg = 'Significant off-line-range emission is detected at peak.'
        score = 0.6
    else:
        lmsg = f'Field {field} Spw {spw}: No significant off-line-range emission is detected at peak.'
        smsg = 'No significant off-line-range emission is detected at peak.'
        score = 1.0

    origin = pqa.QAOrigin(metric_name='score_sd_line_emission_off_range_at_peak', metric_score=score, metric_units='')
    selection = pqa.TargetDataSelection(
        spw=set(result.outcome['assoc_spws']), field={field}, intent={'TARGET'}, pol={stokes}
    )
    return pqa.QAScore(score, longmsg=lmsg, shortmsg=smsg, origin=origin, applies_to=selection)


@log_qa
def score_sd_line_emission_off_range_extended(context: Context, result: SDImagingResultItem) -> pqa.QAScore:
    """Evaluate QA score based on the detetion of off-line-range extended emission.

    Requirements (PIPE-2416):
        - QA score should be
          - 0.6 if significant off-line-range extended emission is detected.
          - 1.0 if no significant off-line-range extended emission is detected.

    Args:
        context: Pipeline context
        result: Imaging result instance

    Returns:
        QAScore -- QAScore instance holding the score based on the Requirements
    """
    emission_off_range_extended = result.outcome.get('line_emission_off_range_extended', False)
    imageitem = result.outcome['image']
    field = imageitem.sourcename
    spw = ','.join(map(str, np.unique(imageitem.spwlist)))
    stokes = result.outcome['stokes']

    if emission_off_range_extended:
        lmsg = f'Field {field} Spw {spw}: Significant off-line-range extended emission is detected.'
        smsg = 'Significant off-line-range extended emission is detected.'
        score = 0.6
    else:
        lmsg = f'Field {field} Spw {spw}: No significant off-line-range extended emission is detected.'
        smsg = 'No significant off-line-range extended emission is detected.'
        score = 1.0

    origin = pqa.QAOrigin(metric_name='score_sd_line_emission_off_range_extended', metric_score=score, metric_units='')
    selection = pqa.TargetDataSelection(
        spw=set(result.outcome['assoc_spws']), field={field}, intent={'TARGET'}, pol={stokes}
    )
    return pqa.QAScore(score, longmsg=lmsg, shortmsg=smsg, origin=origin, applies_to=selection)


@log_qa
def score_sdimage_contamination(context: Context, result: SDImagingResultItem) -> pqa.QAScore:
    """Evaluate QA score based on the absorption feature in the image.

    If there is an emission at OFF_SOURCE position (contamination),
    it is emerged as an absorption feature in the calibrated spectra.
    Therefore, this QA score utilizes any significant absorption
    features as an indicator of potential contamination.

    Requirements (PIPE-2066):
        - QA score should be
          - 0.65 if absorption feature exists
          - 1.0 if absorption feature does not exist

    Args:
        context: Pipeline context
        result: Imaging result instance

    Returns:
        QAScore -- QAScore instance holding the score based on the
                   existence of the absorption feature in the image
    """
    contaminated = result.outcome.get('contaminated', False)
    imageitem = result.outcome['image']
    field = imageitem.sourcename
    spw = ','.join(map(str, np.unique(imageitem.spwlist)))
    stokes = result.outcome['stokes']

    if contaminated:
        lmsg = (
            f'Field {field} Spw {spw}: '
            'Possible astronomical line contamination was detected. '
            'Please check the contamination plots.'
        )
        smsg = 'Possible astronomical line contamination was detected.'
        score = 0.65
    else:
        lmsg = f'Field {field} Spw {spw}: No astronomical line contamintaion was detected.'
        smsg = 'No astronomical line contamination was detected.'
        score = 1.0

    origin = pqa.QAOrigin(
        metric_name='SingleDishImageContamination',
        metric_score=contaminated,
        metric_units='Sign of possible line contamination',
    )
    selection = pqa.TargetDataSelection(
        spw=set(result.outcome['assoc_spws']), field={field}, intent={'TARGET'}, pol={stokes}
    )
    return pqa.QAScore(score, longmsg=lmsg, shortmsg=smsg, origin=origin, applies_to=selection)


@log_qa
def score_sdimage_sensitivity_ratio(result: SDImagingResultItem) -> pqa.QAScore:
    """Evaluate QA score based on observed and theoretical sensitivities estimated from the image

    Requirements (PIPE-2958):
        - QA score should be
          - 1.0  if X1 < observed sensitivity / theoretical sensitivity < X2
          - 0.5  for others

    Args:
        result: Imaging result instance

    Returns:
        QAScore -- QAScore instance holding the score based on the sensitivity estimates

    Raises:
        ValueError: when the unit of observed and theoretical sensitivies do not match
                    when the theoretical sensitivity is not a positive
    """
    # threshold values
    X1, X2 = 0.9, 1.6

    imageitem = result.outcome['image']
    field = imageitem.sourcename
    spw = ','.join(map(str, np.unique(imageitem.spwlist)))

    # fetch sensitivities
    observed = result.sensitivity_info.sensitivity['observed_sensitivity']
    theoretical = result.theoretical_rms['theoretical_sensitivity']

    if theoretical['unit'] != observed['unit']:
        msg = f'Field {field} Spw {spw}: Unit mismatch between Observed sensitivity and Theoretical sensitivity'
        raise ValueError(msg)

    if theoretical['value'] <= 0.0:
        msg = f'Field {field} Spw {spw}: Invalid Theoretical sensitivity {theoretical["value"]} {theoretical["unit"]}'
        raise ValueError(msg)

    x = observed['value'] / theoretical['value']
    if X1 < x and x < X2:
        score = 1.0
        smsg = 'Observed sensitivity agrees with Theoretical sensitivity.'
        lmsg = f'Field {field} Spw {spw}: {smsg}'
    else:
        score = 0.5
        smsg = 'Observed sensitivity deviates from Theoretical sensitivity.'
        lmsg = f'Field {field} Spw {spw}: {smsg}'

    origin = pqa.QAOrigin(
        metric_name='score_sd_image_sensitivity_ratio',
        metric_score=x,
        metric_units='Ratio of Observed sensitivity to Theoretical sensitivity',
    )
    selection = pqa.TargetDataSelection(
        spw=set(result.outcome['assoc_spws']), field={field}, intent={'TARGET'}, pol={'I'}
    )
    return pqa.QAScore(score, longmsg=lmsg, shortmsg=smsg, origin=origin, applies_to=selection)


@log_qa
def score_rasterscan_correctness_direction_domain_rasterscan_fail(result: SDImportDataResults) -> list[pqa.QAScore]:
    """Calculate QAScore of direction-domain raster scan heuristics analysis failure in importdata.

    Args:
        result: instance of SDImportDataResults

    Returns:
        A list of QAScores.
    """
    msg = 'Direction-domain raster scan analysis failed, fallback to time-domain analysis'
    return _score_rasterscan_correctness(result.rasterscan_heuristics_results_direction, msg)


@log_qa
def score_rasterscan_correctness_time_domain_rasterscan_fail(result: SDImportDataResults) -> list[pqa.QAScore]:
    """Calculate QAScore of time-domain raster scan heuristics analysis failure in importdata.

    Args:
        result: instance of SDImportDataResults

    Returns:
        A list of QAScores.
    """
    msg = 'Time-domain raster scan analysis issue detected. Failed to identify gap between raster map iteration'
    return _score_rasterscan_correctness(result.rasterscan_heuristics_results_time, msg)


@log_qa
def score_rasterscan_correctness_imaging_raster_gap(result: SDImagingResultItem) -> list[pqa.QAScore]:
    """Calculate QAScore of gap existence in raster pattern of imaging.

    Args:
        result: instance of SDImagingResultItem

    Returns:
        A list of QAScores.
    """
    msg = 'Unable to identify gap between raster map iteration'
    return _score_rasterscan_correctness(result.rasterscan_heuristics_results_rgap, msg)


@log_qa
def score_rasterscan_correctness_imaging_raster_analysis_incomplete(result: SDImagingResultItem) -> list[pqa.QAScore]:
    """Calculate QAScore when raster scan analysis was incomplete in imaging.

    Args:
        result: instance of SDImagingResultItem

    Returns:
        A list of QAScores.
    """
    msg = 'Raster scan analysis incomplete. Skipping calculation of Theoretical sensitivity'
    return _score_rasterscan_correctness(result.rasterscan_heuristics_results_incomp, msg)


def _score_rasterscan_correctness(
    rasterscan_heuristics_results: dict[str, RasterScanHeuristicsResult],
    msg: str,
) -> list[pqa.QAScore]:
    """Generate score of raster scan correctness of importdata or imaging.

    Args:
        rasterscan_heuristics_results: Dictionary of raster heuristics result objects
            treats QAScore of raster scan analysis.
        msg: short message for QA

    Returns:
        A list contains QAScore objects.
    """
    qa_scores = []  # [pqa.QAScore]

    # converting rasterscan_heuristics_results to QA score
    for _execblock_id, _rasterscan_heuristics_results_list in rasterscan_heuristics_results.items():
        for _results_list in _rasterscan_heuristics_results_list:
            _failed_ants = np.unique(_results_list.get_antennas_rasterscan_failed())
            if len(_failed_ants) > 0:
                qa_scores.append(_rasterscan_failed_per_eb(_execblock_id, _failed_ants, msg))

    return qa_scores


def _rasterscan_failed_per_eb(execblock_id: str, failed_ants: list[str], msg: str) -> pqa.QAScore:
    """Return an object which has FAILED information in raster scan analysis.

    Args:
        execblock_id: Execute Block ID
        failed_ants: List of antenna names
        msg: short message for QA

    Returns:
        QA score object
    """
    SCORE_FAIL = 0.8
    longmsg = msg + f' : EB:{execblock_id}:{",".join(failed_ants)}'
    origin = pqa.QAOrigin(
        metric_name='score_rasterscan_correctness', metric_score=SCORE_FAIL, metric_units='raster scan correctness'
    )
    selection = pqa.TargetDataSelection(vis={execblock_id}, ant=set(failed_ants))
    return pqa.QAScore(SCORE_FAIL, longmsg=longmsg, shortmsg=msg, origin=origin, applies_to=selection)


@log_qa
def score_amp_vs_time_plots(context: Context, result: SDApplycalResults) -> list[pqa.QAScore]:
    """Calculate score about calibrated amplitude vs. time plot of Single Dish Applycal.

    Calculate score according to the existence of plot file for each EB, spw and antenna
    and the quality of it.
    Requirement of PIPE-2168:
      When the plot is created successfully, score = 1.
      When the plot is generated but contains no data of target, score = 0.8.
      When the plot generation failed, score = 0.65.
    To give such score values, check the following:
      1. Check whether the file of plot exists or not.
      2. Check whether the number of flagged data is equal to that of total data or not.

    Args:
        context: Pipeline context object containing state information.
        result: SDApplycalResults instance.

    Returns:
        A List which contains QAScore objects..
    """
    if basetask.DISABLE_WEBLOG:
        # skip scoring if weblog is disabled
        return []

    vis = os.path.basename(result.inputs['vis'])
    ms = context.observing_run.get_ms(vis)
    spwids = [spw.id for spw in ms.get_spectral_windows()]
    ants = ['all'] + [ant.name for ant in ms.get_antenna()]

    stage_dir = os.path.join(context.report_dir, 'stage%s' % context.task_counter)

    flagdata = {}
    flagkwargs = [
        f"spw='{spwid}' fieldcnt=False antenna='*&&&' intent='OBSERVE_TARGET#ON_SOURCE' mode='summary' name='spw{spwid}'"
        for spwid in spwids
    ]
    flagdata_task = casa_tasks.flagdata(vis=vis, mode='list', inpfile=flagkwargs, flagbackup=False)
    flagdata = flagdata_task.execute()
    flagdata_summary = list(flagdata.values())
    scores = []
    PlotMetadata = collections.namedtuple('PlotMetadata', ['vis', 'spw', 'ant'])
    all_plots = itertools.chain(result.amp_vs_time_summary_plots, result.amp_vs_time_detail_plots)
    metadata_for_plots = [
        PlotMetadata(vis=x.parameters['vis'], spw=x.parameters['spw'], ant=x.parameters['ant']) for x in all_plots
    ]
    for spwid in spwids:
        shortmsg_success = 'Calibrated amplitude vs time plot is successfully created'
        longmsg_success = f'{shortmsg_success} for EB {vis}, SPW {spwid}'
        shortmsg_failed = 'Failed to create calibrated amplitude vs time plot'
        longmsg_failed = f'{shortmsg_failed} for EB {vis}, SPW {spwid}'
        shortmsg_empty = 'No data for calibrated amplitude vs time plot'
        longmsg_empty = f'{shortmsg_empty} for EB {vis}, SPW {spwid}'
        sumflagged = 0
        sumtotal = 0
        key = f'spw{spwid}'
        target_summary = [x for x in flagdata_summary if x['name'] == key]
        assert len(target_summary) == 1
        target_summary_for_spw = target_summary[0]

        for ant in ants:
            # Instead of checking the existence of a plot file,
            # compare metadata for the plot object associated with
            # the plot file.
            plot_metadata = PlotMetadata(vis=vis, spw=str(spwid), ant=ant)
            if plot_metadata not in metadata_for_plots:
                shortmsg = shortmsg_failed
                longmsg = f'{longmsg_failed}, Antenna {ant}.'
                score = 0.65
            else:
                target_for_spw_ant = target_summary_for_spw['antenna']
                if ant == 'all':
                    for value in target_for_spw_ant.values():
                        sumflagged += value['flagged']
                        sumtotal += value['total']
                    all_flagged = sumflagged == sumtotal
                else:
                    all_flagged = (
                        ant in target_for_spw_ant
                        and target_for_spw_ant[ant]['flagged'] == target_for_spw_ant[ant]['total']
                    )
                if all_flagged:
                    shortmsg = shortmsg_empty
                    longmsg = f'{longmsg_empty}, Antenna {ant}.'
                    score = 0.8
                else:
                    shortmsg = shortmsg_success
                    longmsg = f'{longmsg_success}, Antenna {ant}.'
                    score = 1.0

            origin = pqa.QAOrigin(
                metric_name='AmpVsTimePlotQuality',
                metric_score=score,
                metric_units='Score based on quality of calibrated amp vs time plots',
            )
            applies_to = pqa.TargetDataSelection(vis={vis}, spw={spwid}, intent={'TARGET'}, ant={ant})
            scores.append(pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin, applies_to=applies_to))

    return scores


@log_qa
def score_pointing_outlier(
    ms: MeasurementSet, pointing: bool, pointing_outlier_stats: dict[tuple[int, int], PointingOutlierStats]
) -> list[pqa.QAScore]:
    """Generate QA score for pointing outliers.

    If pointing outliers are detected, the score is set to 0.83.
    In that case, this function creates QAScore objects for each
    combination of field and antenna that have pointing outliers.
    The score is 1.0 if no pointing outliers are detected.

    Args:
        ms: MS domain object.
        pointing: Whether pointing flag is applied or not.
        pointing_outlier_stats: Dictionary of pointing outlier
            statistics indexed by (field_id, antenna_id).

    Returns:
        List of QAScore objects.
    """
    # If no pointing outliers are detected, return QAScore with score of 1.0
    metric_name = 'NumberOfPointingOutliers'
    metric_units = 'number of pointing outliers'
    if len(pointing_outlier_stats) == 0:
        score = 1.0
        longmsg = f'No pointing outliers detected in "{ms.basename}".'
        shortmsg = 'No pointing outliers detected'

        origin = pqa.QAOrigin(metric_name=metric_name, metric_score=0, metric_units=metric_units)
        applies_to = pqa.TargetDataSelection(vis={ms.basename})
        score = pqa.QAScore(
            score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin, applies_to=applies_to
        )
        return [score]

    # score is 0.83 when pointing outlier is detected (PIPEREQ-358/PIPE-2533)
    qa_scores = []
    for (field_id, antenna_id), stats in pointing_outlier_stats.items():
        num_outliers = len(stats.outliers)
        field = ms.get_fields(field_id=field_id)[0]
        antenna = ms.get_antenna(str(antenna_id))[0]
        assert num_outliers > 0
        score = 0.83
        max_separation = np.max(stats.separations)
        assert len(stats.timerange) > 0
        time_range_str = ', '.join(stats.timerange)
        longmsg = (
            f'Pointing outliers detected in "{ms.basename}" , Field "{field.name}", Antenna "{antenna.name}". '
            f'Flagged time range is {time_range_str}. '
            f'Max separation from nominal field center is {max_separation:.2f} deg.'
        )
        shortmsg = 'Pointing outliers detected'
        if not pointing:
            longmsg += ' However, poinging flag was not applied.'
            shortmsg += ' (but not flagged)'

        origin = pqa.QAOrigin(metric_name=metric_name, metric_score=num_outliers, metric_units=metric_units)
        applies_to = pqa.TargetDataSelection(vis={ms.basename}, field={field_id}, ant={antenna_id})
        qa_scores.append(
            pqa.QAScore(
                score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin, applies_to=applies_to
            )
        )

    return qa_scores
