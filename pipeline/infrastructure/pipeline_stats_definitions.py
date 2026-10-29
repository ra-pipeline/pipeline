"""Definitions of all pipeline statistics.

Every statistic written to a pipeline stats file needs exactly one definition here; emitting a statistic without
a definition is reported as an extraction error. See pipeline_statistics.StatDefinition for the meaning of each
field. Priorities follow the pipeline statistics specification.

Tolerances (rel_tol, abs_tol) of None mean that regression tests use the test's default tolerance.
"""
from pipeline.infrastructure.pipeline_statistics import Audience, StatDefinition, build_definitions

PRODUCT = Audience.PRODUCT
TEST = Audience.TEST

_DEFINITIONS = [
    # ---- Project information (MOUS level) --------------------------------------------------------------------------
    StatDefinition('project_id', 'Proposal id number', priority=1),
    StatDefinition('mous_uid', 'Member Obs Unit Set ID', priority=1),
    StatDefinition('n_EB', 'number of execution blocks', priority=1),
    StatDefinition('bands', 'Band(s) used in observations.', priority=1),
    StatDefinition('n_spw', 'number of spectral windows', priority=1),
    StatDefinition('target_list', 'list of science target names', priority=1),
    StatDefinition('n_target', 'total number of science targets in the MOUS', priority=1),
    StatDefinition('rep_target', 'representative target name', priority=1),

    # ---- Project information (EB level) ----------------------------------------------------------------------------
    StatDefinition('n_ant', 'Number of antennas per execution block', priority=1),
    StatDefinition('n_scan', 'number of scans per EB', priority=1),
    StatDefinition('L80', '80th percentile baseline', units='m', priority=1),

    # ---- Project information (spw level; spw properties taken from the first EB) -----------------------------------
    StatDefinition('spw_width', 'width of the spectral window', units='MHz', priority=1),
    StatDefinition('spw_freq', 'central frequency of the spectral window in TOPO', units='GHz', priority=1),
    StatDefinition('n_chan', 'number of channels in the spectral window', priority=1),
    StatDefinition('n_pol', 'number of polarizations in the spectral window', priority=1),
    StatDefinition('chan_width', 'frequency width of the channels in the spectral window', units='MHz', priority=1),
    StatDefinition('nbin_online', 'online nbin factor', priority=1),

    # ---- Project information (source level) ------------------------------------------------------------------------
    StatDefinition('n_pointings', 'number of mosaic pointings for the science target', priority=1),

    # ---- Pipeline run information ----------------------------------------------------------------------------------
    StatDefinition('pipeline_version', 'pipeline version string', priority=1, compare=False),
    StatDefinition('pipeline_recipe', 'recipe name', priority=1),
    StatDefinition('casa_version', 'casa version string', priority=1, compare=False),
    StatDefinition('total_time', 'total processing time', units='hours', priority=1, compare=False),
    StatDefinition('stage_info', 'stage number and name', priority=1),
    StatDefinition('stage_duration', 'time spent in each stage', units='hours', per_stage=True, priority=1,
                   compare=False),

    # ---- Calibration information -----------------------------------------------------------------------------------
    StatDefinition('flagdata_percentage',
                   'percentage of data newly flagged by the given flagging reason (online, shadow, qa0, qa2, before '
                   'and template flagging agents)',
                   units='%', priority=1),

    # ---- QA scores (regression tests) ------------------------------------------------------------------------------
    StatDefinition('qa_score', 'QA score', audience=TEST, per_stage=True),
    StatDefinition('qa_metric', 'value of the metric the QA score was calculated from', audience=TEST,
                   per_stage=True),

    # ---- Regression test values, by task ---------------------------------------------------------------------------
    StatDefinition('gfluxscaleflag_num_rows_flagged', 'number of flagged rows before/after hifa_gfluxscaleflag',
                   audience=TEST),
    StatDefinition('gcorfluxscale_flux_I', 'Stokes I flux density derived by hifa_gcorfluxscale per field and spw',
                   units='Jy', audience=TEST),
    StatDefinition('applycal_num_rows_flagged', 'number of flagged rows before/after applycal', audience=TEST),
    StatDefinition('applycal_num_rows_flagged_per_scan', 'number of flagged rows per scan before/after applycal',
                   audience=TEST),
    StatDefinition('checkflag_num_rows_flagged', 'number of flagged rows before/after hifv_checkflag',
                   audience=TEST),
    StatDefinition('checkflag_num_rows_flagged_per_scan', 'number of flagged rows per scan before/after '
                   'hifv_checkflag', audience=TEST),
    StatDefinition('targetflag_num_rows_flagged', 'number of flagged rows in the hifv_targetflag summary',
                   audience=TEST),
    StatDefinition('targetflag_num_rows_flagged_per_scan', 'number of flagged rows per scan in the hifv_targetflag '
                   'summary', audience=TEST),
    StatDefinition('fluxboot_flux_density', 'flux density derived by hifv_fluxboot per spw', units='Jy',
                   audience=TEST),
    StatDefinition('fluxboot_spix', 'spectral index derived by hifv_fluxboot', audience=TEST),
    StatDefinition('fluxboot_curvature', 'spectral curvature derived by hifv_fluxboot', audience=TEST),
    StatDefinition('fluxboot_delta', 'delta coefficient derived by hifv_fluxboot', audience=TEST),
    StatDefinition('fluxboot_gamma', 'gamma coefficient derived by hifv_fluxboot', audience=TEST),
    StatDefinition('solint_longsolint', 'long solution interval per band from hifv_solint', audience=TEST),
    StatDefinition('solint_short_solint', 'short solution interval per band from hifv_solint', audience=TEST),
    StatDefinition('solint_shortsol2', 'shortsol2 solution interval per band from hifv_solint', audience=TEST),
    StatDefinition('priorcals_opacity', 'opacity per spw from hifv_priorcals', audience=TEST),
    StatDefinition('vlasetjy_flux_I', 'Stokes I flux density set by hifv_vlasetjy per field', units='Jy',
                   audience=TEST),
    StatDefinition('statwt_mean', 'mean of the weights from hifv_statwt', audience=TEST),
    StatDefinition('statwt_variance', 'variance of the weights from hifv_statwt', audience=TEST),
    StatDefinition('importdata_n_ant', 'number of antennas from hifv_importdata', audience=TEST),
    StatDefinition('importdata_max_integration_time', 'maximum integration time from hifv_importdata', units='s',
                   audience=TEST),
    StatDefinition('flagdata_num_rows_flagged', 'number of flagged rows per flagging category from hifv_flagdata',
                   audience=TEST),
    StatDefinition('testbpdcals_bandpass_flagged_solutions', 'number of flagged bandpass solutions per band from '
                   'hifv_testBPdcals', audience=TEST),
    StatDefinition('testbpdcals_delay_flagged_solutions', 'number of flagged delay solutions per band from '
                   'hifv_testBPdcals', audience=TEST),
    StatDefinition('semifinalbpdcals_bandpass_flagged_solutions', 'number of flagged bandpass solutions per band '
                   'from hifv_semiFinalBPdcals', audience=TEST),
    StatDefinition('semifinalbpdcals_delay_flagged_solutions', 'number of flagged delay solutions per band from '
                   'hifv_semiFinalBPdcals', audience=TEST),
    StatDefinition('finalcals_bandpass_flagged_solutions', 'number of flagged bandpass solutions from '
                   'hifv_finalcals', audience=TEST),
    StatDefinition('finalcals_delay_flagged_solutions', 'number of flagged delay solutions from hifv_finalcals',
                   audience=TEST),
    StatDefinition('sd_blflag_num_rows_flagged', 'number of flagged rows per flagging summary from hsd_blflag',
                   audience=TEST),
    StatDefinition('sd_blflag_num_rows_flagged_per_scan', 'number of flagged rows per scan per flagging summary '
                   'from hsd_blflag', audience=TEST),
    StatDefinition('restoredata_num_rows_flagged', 'number of flagged rows per target after restoredata',
                   audience=TEST),
    StatDefinition('restoredata_num_rows_flagged_per_scan', 'number of flagged rows per target and scan after '
                   'restoredata', audience=TEST),
]

DEFINITIONS = build_definitions(_DEFINITIONS)
