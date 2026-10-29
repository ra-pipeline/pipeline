"""Pipeline statistics extractors.

Every extractor is registered with pipeline_statistics.registry at import time and produces statistics by calling
emit(name, value, **dims). Every name emitted must be defined in pipeline_stats_definitions.py.

    * Context extractors are called once per run: func(context, emit).
    * Results extractors are called for every Results object of the registered class (and generating task):
      func(result, context, emit). The stage number and task name are filled in automatically.

An exception raised by an extractor discards everything that extractor emitted for that call and is recorded in the
errors section of the stats file, so keep extractors small enough that one failure does not hide unrelated values.
"""
from __future__ import annotations

import datetime
import re
from typing import TYPE_CHECKING

import numpy as np

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.renderer.htmlrenderer as htmlrenderer
import pipeline.infrastructure.utils as utils
from pipeline import environment
from pipeline.domain import measures
from pipeline.domain.datatype import DataType
from pipeline.domain.measures import FluxDensityUnits
from pipeline.h.tasks.applycal.applycal import ApplycalResults
from pipeline.h.tasks.common import flagging_renderer_utils as flagutils
from pipeline.h.tasks.common.commonfluxresults import FluxCalibrationResults
from pipeline.hif.tasks.applycal.ifapplycal import IFApplycal
from pipeline.hifa.tasks.flagging.flagdeteralma import FlagDeterALMAResults
from pipeline.hifa.tasks.fluxscale.gcorfluxscale import GcorFluxscale
from pipeline.hifa.tasks.gfluxscaleflag import Gfluxscaleflag
from pipeline.hifa.tasks.gfluxscaleflag.resultobjects import GfluxscaleflagResults
from pipeline.hifv.tasks.finalcals.applycals import Applycals
from pipeline.hifv.tasks.finalcals.finalcals import Finalcals, FinalcalsResults
from pipeline.hifv.tasks.flagging.checkflag import Checkflag, CheckflagResults
from pipeline.hifv.tasks.flagging.flagdetervla import FlagDeterVLA, FlagDeterVLAResults
from pipeline.hifv.tasks.flagging.targetflag import Targetflag, TargetflagResults
from pipeline.hifv.tasks.fluxscale.fluxboot import Fluxboot, FluxbootResults
from pipeline.hifv.tasks.fluxscale.solint import Solint, SolintResults
from pipeline.hifv.tasks.importdata.importdata import VLAImportData, VLAImportDataResults
from pipeline.hifv.tasks.priorcals import Priorcals
from pipeline.hifv.tasks.priorcals.resultobjects import PriorcalsResults
from pipeline.hifv.tasks.semiFinalBPdcals.semiFinalBPdcals import semiFinalBPdcals, semiFinalBPdcalsResults
from pipeline.hifv.tasks.setmodel.vlasetjy import VLASetjy
from pipeline.hifv.tasks.statwt.statwt import Statwt, StatwtResults
from pipeline.hifv.tasks.testBPdcals.testBPdcals import testBPdcals, testBPdcalsResults
from pipeline.hsd.tasks.applycal.applycal import SDApplycal
from pipeline.hsd.tasks.baselineflag.baselineflag import SDBLFlag, SDBLFlagResults
from pipeline.hsd.tasks.restoredata.restoredata import SDRestoreData, SDRestoreDataResults
from pipeline.hsdn.tasks.restoredata.restoredata import NRORestoreData, NRORestoreDataResults
from pipeline.infrastructure import basetask
from pipeline.infrastructure.pipeline_statistics import registry, stage_number, task_name, to_serializable, vis_name

if TYPE_CHECKING:
    from pipeline.domain.measurementset import MeasurementSet
    from pipeline.infrastructure.launcher import Context

LOG = infrastructure.logging.get_logger(__name__)


# ---------------------------------------------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------------------------------------------

def determine_import_program(context: Context, ms: MeasurementSet) -> str:
    """Returns the name of the import task used to create the MS; used as the task of context statistics."""
    if ms.antenna_array.name == 'ALMA':
        if utils.contains_single_dish(context):
            return 'hsd_importdata'
        return 'hifa_importdata'
    if ms.antenna_array.name == 'VLA':
        return 'hifv_importdata'
    return 'unknown'


def strip_html(text: str) -> str:
    return re.sub(re.compile('<.*?>'), '', text)


def _measurement_sets(context: Context) -> list[MeasurementSet]:
    # Fetch the MSes for only the first datatype found in this list, so that information is not repeated for the
    # ms and the _targets.ms when both are present.
    datatypes = [DataType.REGCAL_CONTLINE_ALL, DataType.REGCAL_CONTLINE_SCIENCE, DataType.SELFCAL_CONTLINE_SCIENCE,
                 DataType.REGCAL_LINE_SCIENCE, DataType.SELFCAL_LINE_SCIENCE, DataType.RAW]
    ms_list = context.observing_run.get_measurement_sets_of_type(datatypes)
    if not ms_list:
        raise ValueError('No measurement sets found in the context')
    return ms_list


def _science_sources(ms: MeasurementSet) -> list:
    return sorted({source for source in ms.sources if 'TARGET' in source.intents}, key=lambda source: source.name)


def _hours(dt: datetime.timedelta) -> float:
    return dt.total_seconds() / 3600.0


def _summaries_by_name(summaries) -> dict:
    return {s['name']: s for s in summaries}


def _emit_flagged_rows(emit, name: str, flag_summary: dict, **dims) -> None:
    """Emit the total number of flagged rows in a flagdata summary and, as <name>_per_scan, the number per scan."""
    emit(name, int(flag_summary['flagged']), **dims)
    for scan_id, scan_summary in flag_summary.get('scan', {}).items():
        emit(f'{name}_per_scan', int(scan_summary['flagged']), scan=scan_id, **dims)


# ---------------------------------------------------------------------------------------------------------------------
# Context extractors: project and pipeline run information
# ---------------------------------------------------------------------------------------------------------------------

@registry.context
def run_info(context: Context, emit) -> None:
    """MOUS-level information about the project and the pipeline run."""
    task = determine_import_program(context, _measurement_sets(context)[0])
    emit('project_id', next(iter(context.observing_run.project_ids)), task=task)
    emit('pipeline_version', environment.pipeline_revision, task=task)
    emit('pipeline_recipe', context.project_structure.recipe_name, task=task)
    emit('casa_version', environment.casa_version_string, task=task)
    emit('mous_uid', context.get_oussid(), task=task)
    emit('n_EB', len(context.observing_run.execblock_ids), task=task)


@registry.context
def observation_info(context: Context, emit) -> None:
    """MOUS-level information about the observations, taken from the first EB."""
    first_ms = _measurement_sets(context)[0]
    task = determine_import_program(context, first_ms)
    science_source_names = [source.name for source in _science_sources(first_ms)]

    emit('bands', sorted({spw.band for spw in first_ms.get_all_spectral_windows()}), task=task)
    emit('n_target', len(science_source_names), task=task)
    emit('target_list', science_source_names, task=task)
    emit('rep_target', first_ms.representative_target[0], task=task)
    emit('n_spw', len(first_ms.get_all_spectral_windows()), task=task)


@registry.context
def eb_properties(context: Context, emit) -> None:
    """Per-EB information."""
    ms_list = _measurement_sets(context)
    task = determine_import_program(context, ms_list[0])
    for ms in ms_list:
        eb = vis_name(ms.name)
        emit('n_ant', len(ms.antennas), task=task, eb=eb)
        emit('n_scan', len(ms.get_scans()), task=task, eb=eb)
        emit('L80', np.percentile(ms.antenna_array.baselines_m, 80), task=task, eb=eb)


@registry.context
def spw_properties(context: Context, emit) -> None:
    """Properties of each spw, which apply to the whole MOUS. Taken from the first EB."""
    ms = _measurement_sets(context)[0]
    task = determine_import_program(context, ms)
    for spw in ms.get_all_spectral_windows():
        emit('spw_width', float(spw.bandwidth.to_units(measures.FrequencyUnits.MEGAHERTZ)), task=task, spw=spw.id)
        emit('spw_freq', float(spw.centre_frequency.to_units(measures.FrequencyUnits.GIGAHERTZ)), task=task,
             spw=spw.id)
        emit('n_chan', spw.num_channels, task=task, spw=spw.id)
        emit('nbin_online', spw.sdm_num_bin, task=task, spw=spw.id)
        emit('chan_width', spw.channels.chan_widths[0] * 1e-6, task=task, spw=spw.id)
        emit('n_pol', ms.get_data_description(spw=int(spw.id)).num_polarizations, task=task, spw=spw.id)


@registry.context
def source_properties(context: Context, emit) -> None:
    """Per science target information, taken from the first EB."""
    first_ms = _measurement_sets(context)[0]
    task = determine_import_program(context, first_ms)
    for source in _science_sources(first_ms):
        n_pointings = len([f for f in first_ms.fields if f.source_id == source.id])
        emit('n_pointings', n_pointings, task=task, source=source.name)


@registry.context
def processing_time(context: Context, emit) -> None:
    """Total processing time: from the start of the first stage to the end of the last one."""
    emit('total_time',
         _hours(context.results[-1].read().timestamps.end - context.results[0].read().timestamps.start))


@registry.context
def stage_info(context: Context, emit) -> None:
    """Stage number and description of every stage."""
    info = {}
    for results_proxy in context.results:
        result = results_proxy.read()
        info[stage_number(result)] = strip_html(htmlrenderer.get_task_description(result, context))
    emit('stage_info', info)


@registry.context
def stage_durations(context: Context, emit) -> None:
    """Duration of each stage, measured as in the weblog: the time from the start of a stage to the start of the
    next one. The last stage ends at its own end time."""
    results = [results_proxy.read() for results_proxy in context.results]
    for i, result in enumerate(results):
        end = results[i + 1].timestamps.start if i + 1 < len(results) else result.timestamps.end
        emit('stage_duration', _hours(end - result.timestamps.start),
             stage=stage_number(result), task=task_name(result))


# ---------------------------------------------------------------------------------------------------------------------
# Results extractors
# ---------------------------------------------------------------------------------------------------------------------

@registry.results(basetask.Results, top_level_only=True)
def qa_scores(result, context: Context, emit) -> None:
    """Every QA score of the stage, with the value of the metric it was calculated from.

    The stage-level result is used because list QA handlers collect the scores of their children into it.
    """
    for score in result.qa.pool:
        dims = {'metric': score.origin.metric_name}
        applies_to = score.applies_to
        if applies_to is not None:
            for attribute, dim in (('vis', 'eb'), ('session', 'session'), ('field', 'field'), ('intent', 'intent'),
                                   ('spw', 'spw'), ('ant', 'ant'), ('scan', 'scan'), ('pol', 'pol')):
                selection = getattr(applies_to, attribute, None)
                if selection:
                    dims[dim] = sorted(vis_name(v) for v in selection) if dim == 'eb' else selection
        emit('qa_score', score.score, **dims)
        try:
            metric = to_serializable(score.origin.metric_score)
        except TypeError:
            metric = str(score.origin.metric_score)
        emit('qa_metric', metric, **dims)


@registry.results(FlagDeterALMAResults)
def flagdata_percentage(result: FlagDeterALMAResults, context: Context, emit) -> None:
    """Percentage of data newly flagged by each flagging reason, per EB."""
    intents_to_summarise = flagutils.intents_to_summarise(context)
    flag_totals = utils.dict_merge({}, flagutils.flags_for_result(result, context,
                                                                  intents_to_summarise=intents_to_summarise))
    reasons_to_export = ['online', 'shadow', 'qa0', 'qa2', 'before', 'template']

    for ms, reasons in flag_totals.items():
        for reason, intents in reasons.items():
            if reason not in reasons_to_export:
                continue
            for intent, counts in intents.items():
                if 'TOTAL' in intent:
                    flagged, total = float(counts[0]), float(counts[1])
                    emit('flagdata_percentage', flagged / total * 100, eb=vis_name(ms), reason=reason)


@registry.results(GfluxscaleflagResults, Gfluxscaleflag)
def gfluxscaleflag_flags(result: GfluxscaleflagResults, context: Context, emit) -> None:
    summaries = _summaries_by_name(result.cafresult.summaries)
    before = int(summaries['before']['flagged'])
    after = int(summaries['after']['flagged']) if 'after' in summaries else before
    eb = vis_name(result.inputs['vis'])
    emit('gfluxscaleflag_num_rows_flagged', before, eb=eb, summary='before')
    emit('gfluxscaleflag_num_rows_flagged', after, eb=eb, summary='after')


@registry.results(FluxCalibrationResults, GcorFluxscale)
def gcorfluxscale_fluxes(result: FluxCalibrationResults, context: Context, emit) -> None:
    eb = vis_name(result.inputs['vis'])
    for field_id, measurements in result.measurements.items():
        for m in measurements:
            emit('gcorfluxscale_flux_I', float(m.I.to_units(FluxDensityUnits.JANSKY)), eb=eb, field=field_id,
                 spw=m.spw_id)


def _applycal_flags(result: ApplycalResults, context: Context, emit) -> None:
    summaries = _summaries_by_name(getattr(result, 'summaries', []))
    if 'before' not in summaries or 'applycal' not in summaries:
        LOG.info('Flag summaries missing from %s; omitting applycal flagging statistics.', type(result).__name__)
        return
    eb = vis_name(result.inputs['vis'])
    _emit_flagged_rows(emit, 'applycal_num_rows_flagged', summaries['before'], eb=eb, summary='before')
    _emit_flagged_rows(emit, 'applycal_num_rows_flagged', summaries['applycal'], eb=eb, summary='after')


registry.results(ApplycalResults, IFApplycal)(_applycal_flags)
registry.results(ApplycalResults, SDApplycal)(_applycal_flags)
registry.results(ApplycalResults, Applycals)(_applycal_flags)


@registry.results(CheckflagResults, Checkflag)
def checkflag_flags(result: CheckflagResults, context: Context, emit) -> None:
    summaries = _summaries_by_name(result.summaries)
    eb = vis_name(result.inputs['vis'])
    for summary_name in ('before', 'after'):
        if summary_name in summaries:
            _emit_flagged_rows(emit, 'checkflag_num_rows_flagged', summaries[summary_name], eb=eb,
                               summary=summary_name)
        else:
            emit('checkflag_num_rows_flagged', None, eb=eb, summary=summary_name)


@registry.results(TargetflagResults, Targetflag)
def targetflag_flags(result: TargetflagResults, context: Context, emit) -> None:
    summary = _summaries_by_name(result.summarydict)['Summary']
    _emit_flagged_rows(emit, 'targetflag_num_rows_flagged', summary, eb=vis_name(result.inputs['vis']),
                       summary='Summary')


@registry.results(FluxbootResults, Fluxboot)
def fluxboot_fluxes(result: FluxbootResults, context: Context, emit) -> None:
    eb = vis_name(result.inputs['vis'])
    # There may be spws without a solution, which aren't included here, so don't index by spw
    for i, spw in enumerate(sorted(result.spws)):
        emit('fluxboot_flux_density', result.flux_densities[i][0], eb=eb, spw=spw)
    spindex = result.spindex_results[0]
    emit('fluxboot_spix', float(spindex['spix']), eb=eb)
    emit('fluxboot_curvature', float(spindex['curvature']), eb=eb)
    emit('fluxboot_delta', float(spindex['delta']), eb=eb)
    emit('fluxboot_gamma', float(spindex['gamma']), eb=eb)


@registry.results(SolintResults, Solint)
def solint_intervals(result: SolintResults, context: Context, emit) -> None:
    eb = vis_name(result.inputs['vis'])
    for band, value in result.longsolint.items():
        emit('solint_longsolint', value, eb=eb, band=band)
        emit('solint_short_solint', result.short_solint[band], eb=eb, band=band)
        emit('solint_shortsol2', result.shortsol2[band], eb=eb, band=band)


@registry.results(PriorcalsResults, Priorcals)
def priorcals_opacities(result: PriorcalsResults, context: Context, emit) -> None:
    eb = vis_name(result.inputs['vis'])
    for spw, opacity in zip(result.oc_result.spw, result.oc_result.opacities):
        emit('priorcals_opacity', opacity, eb=eb, spw=spw)


@registry.results(FluxCalibrationResults, VLASetjy)
def vlasetjy_fluxes(result: FluxCalibrationResults, context: Context, emit) -> None:
    eb = vis_name(result.inputs['vis'])
    for field, fluxlist in result.measurements.items():
        emit('vlasetjy_flux_I', float(fluxlist[0].I.to_units(FluxDensityUnits.JANSKY)), eb=eb, field=field)


@registry.results(StatwtResults, Statwt)
def statwt_stats(result: StatwtResults, context: Context, emit) -> None:
    eb = vis_name(result.inputs['vis'])
    emit('statwt_mean', result.jobs[0]['mean'], eb=eb)
    emit('statwt_variance', result.jobs[0]['variance'], eb=eb)


@registry.results(VLAImportDataResults, VLAImportData)
def vla_importdata(result: VLAImportDataResults, context: Context, emit) -> None:
    ms = result.mses[0]
    eb = vis_name(ms.name)
    emit('importdata_n_ant', len(ms.antennas), eb=eb)
    emit('importdata_max_integration_time', ms.get_integration_time_stats(stat_type='max'), eb=eb)


@registry.results(FlagDeterVLAResults, FlagDeterVLA)
def flagdetervla_flags(result: FlagDeterVLAResults, context: Context, emit) -> None:
    eb = vis_name(result.inputs['vis'])
    for summary in result.summaries:
        emit('flagdata_num_rows_flagged', int(summary['flagged']), eb=eb, summary=summary['name'])


def _bpdcals_flags(prefix: str):
    def extractor(result, context: Context, emit) -> None:
        eb = vis_name(result.inputs['vis'])
        for band, flagdict in result.flaggedSolnApplycalbandpass.items():
            emit(f'{prefix}_bandpass_flagged_solutions', int(flagdict['all']['flagged']), eb=eb, band=band)
        for band, flagdict in result.flaggedSolnApplycaldelay.items():
            emit(f'{prefix}_delay_flagged_solutions', int(flagdict['all']['flagged']), eb=eb, band=band)
    extractor.__name__ = f'{prefix}_flags'
    return extractor


registry.results(testBPdcalsResults, testBPdcals)(_bpdcals_flags('testbpdcals'))
registry.results(semiFinalBPdcalsResults, semiFinalBPdcals)(_bpdcals_flags('semifinalbpdcals'))


@registry.results(FinalcalsResults, Finalcals)
def finalcals_flags(result: FinalcalsResults, context: Context, emit) -> None:
    eb = vis_name(result.inputs['vis'])
    emit('finalcals_bandpass_flagged_solutions', int(result.flaggedSolnApplycalbandpass['all']['flagged']), eb=eb)
    emit('finalcals_delay_flagged_solutions', int(result.flaggedSolnApplycaldelay['all']['flagged']), eb=eb)


@registry.results(SDBLFlagResults, SDBLFlag)
def sd_blflag_flags(result: SDBLFlagResults, context: Context, emit) -> None:
    eb = vis_name(result.inputs['vis'])
    for summary in result.outcome['flagdata_summary']:
        name = summary.get('name')
        flag_summary = next((v for k, v in summary.items() if k != 'name' and isinstance(v, dict)), None)
        if name is not None and flag_summary is not None:
            _emit_flagged_rows(emit, 'sd_blflag_num_rows_flagged', flag_summary, eb=eb, summary=name)


def _restoredata_flags(result, context: Context, emit) -> None:
    for session, mses in result.flagging_summaries.items():
        for ms_name, targets in mses.items():
            for target_name, target in targets.items():
                if isinstance(target, dict):
                    _emit_flagged_rows(emit, 'restoredata_num_rows_flagged', target, eb=vis_name(ms_name),
                                       session=session, source=target_name)


registry.results(SDRestoreDataResults, SDRestoreData)(_restoredata_flags)
registry.results(NRORestoreDataResults, NRORestoreData)(_restoredata_flags)
