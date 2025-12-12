import copy
import json
import os
import shutil
import tarfile
import traceback
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import numpy as np
from astropy.utils.misc import JsonCustomEncoder

import pipeline.domain.measures as measures
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.filenamer as filenamer
import pipeline.infrastructure.mpihelpers as mpihelpers
import pipeline.infrastructure.vdp as vdp
from pipeline import environment
from pipeline.domain import DataType
from pipeline.hif.heuristics.auto_selfcal import auto_selfcal
from pipeline.hif.tasks.applycal import SerialIFApplycal
from pipeline.hif.tasks.makeimlist import MakeImList
from pipeline.infrastructure import callibrary, casa_tasks, casa_tools, logging, task_registry, utils
from pipeline.infrastructure.contfilehandler import contfile_to_chansel
from pipeline.infrastructure.mpihelpers import TaskQueue

LOG = infrastructure.get_logger(__name__)


class SelfcalResults(basetask.Results):
    def __init__(self, targets, applycal_result_contline=None, applycal_result_line=None, selfcal_resources=None,
                 is_restore=False):
        super().__init__()
        self.pipeline_casa_task = 'Selfcal'
        self.targets = targets
        self.applycal_result_contline = applycal_result_contline
        self.applycal_result_line = applycal_result_line
        self.is_restore = is_restore
        self.selfcal_resources = selfcal_resources

    def merge_with_context(self, context):
        """See :method:`~pipeline.infrastructure.api.Results.merge_with_context`."""

        # save selfcal results into the Pipeline context
        if context.selfcal_targets:
            LOG.warning('context.selfcal_targets is being over-written.')

        scal_targets_ctx = copy.deepcopy(self.targets)
        for target in scal_targets_ctx:
            target.pop('heuristics', None)
        context.selfcal_targets = scal_targets_ctx

        # if selfcal_resources is None, then the selfcal solver is not triggered and no need to register the
        # selfcal resources for auxproducts exporting.
        if self.selfcal_resources is not None:
            context.selfcal_resources = self.selfcal_resources

        if self.applycal_result_contline is not None:
            self._register_datatype(context, self.applycal_result_contline)
        if self.applycal_result_line is not None:
            self._register_datatype(context, self.applycal_result_line)

    def _register_datatype(self, context, appycal_result):

        calto_list = []
        for r in appycal_result:
            for calapp in r.applied:
                calto_list.append(calapp.calto)

        # register the selfcal results to the observing run
        for calto in calto_list:

            vis = calto.vis
            spw_sel = calto.spw

            # Create a mapping of regcal data types to their applied selfcal types
            data_type_mapping = {
                DataType.REGCAL_CONTLINE_SCIENCE: DataType.SELFCAL_CONTLINE_SCIENCE,
                DataType.REGCAL_LINE_SCIENCE: DataType.SELFCAL_LINE_SCIENCE,
                DataType.REGCAL_CONT_SCIENCE: DataType.SELFCAL_CONT_SCIENCE
            }

            # `calto.field` is a reduced CASA-style selection string derived from the calapp-apply consolidation.
            # The value can be a field name, a comma separated field id selection string, or an empty string.
            # See `CaltoIDAdapter.field` for more details on this structure.
            # Here, its selection scope needs to be translated back to the source name(s) used in `cleantarget`.

            # Retrieve the MS object for the observing run associated with the given visibility (`vis`).
            ms = context.observing_run.get_ms(vis)

            # Fetch the field names matching the given `calto.field` and `calto.intent`.
            # Use a set comprehension to collect unique field names, and join them into a single string.
            field_name = ','.join({field.name for field in ms.get_fields(task_arg=calto.field, intent=calto.intent)})

            # Retrieve the data type
            data_dtype = ms.get_data_type('DATA', field_name, spw_sel)

            # Find the corresponding selfcal type
            dtype_applied = data_type_mapping.get(data_dtype, None)
            if dtype_applied is None:
                LOG.warning('No selfcal data type found corresponding to the data type: %s '
                            'associated with field=%r, spw=%r in vis=%s. Skipping registration.',
                            data_dtype, field_name, spw_sel, vis)
                continue

            with casa_tools.TableReader(vis) as tb:
                # check for the existance of CORRECTED_DATA first
                if 'CORRECTED_DATA' not in tb.colnames():
                    LOG.warning('No CORRECTED_DATA column in %s, skip %s registration', vis, dtype_applied)
                    continue
                LOG.debug('DataType registeration: overwrite=%s', self.inputs['overwrite'])
                LOG.info('Registering the CORRECTED_DATA column as %s for %s: field=%r spw=%r',
                         dtype_applied, vis, field_name, spw_sel)
                ms.set_data_column(dtype_applied, 'CORRECTED_DATA', source=field_name,
                                   spw=spw_sel, overwrite=self.inputs['overwrite'])

    def __repr__(self):
        return 'SelfcalResults:'


class SelfcalInputs(vdp.StandardInputs):

    # restrict input vis to be of type REGCAL_CONTLINE_SCIENCE
    # potentially we could allow REGCAL_CONTLINE_ALL here (e.g. tmp ms splitted from 'corrected' data column),
    # but there is no space for applying final selfcal solutions to the data.

    processing_data_type = [DataType.REGCAL_CONT_SCIENCE, DataType.REGCAL_CONTLINE_SCIENCE]

    field = vdp.VisDependentProperty(default='')

    @field.convert
    def field(self, val):
        if not isinstance(val, (str, type(None))):
            # PIPE-1881: allow field names that mistakenly get casted into non-string datatype by
            # recipereducer (utils.string_to_val) and executeppr (XmlObjectifier.castType)
            LOG.warning('The field selection input %r is not a string and will be converted.', val)
            val = str(val)
        return val

    spw = vdp.VisDependentProperty(default='')
    contfile = vdp.VisDependentProperty(default='cont.dat')
    hm_imsize = vdp.VisDependentProperty(default=None)
    hm_cell = vdp.VisDependentProperty(default=None)
    apply = vdp.VisDependentProperty(default=True)
    parallel = vdp.VisDependentProperty(default='automatic')
    recal = vdp.VisDependentProperty(default=False)
    restore_only = vdp.VisDependentProperty(default=False)
    overwrite = vdp.VisDependentProperty(default=False)

    n_solints = vdp.VisDependentProperty(default=4.0)
    amplitude_selfcal = vdp.VisDependentProperty(default=False)
    gaincal_minsnr = vdp.VisDependentProperty(default=2.0)
    minsnr_to_proceed = vdp.VisDependentProperty(default=3.0)
    delta_beam_thresh = vdp.VisDependentProperty(default=0.05)
    apply_cal_mode_default = vdp.VisDependentProperty(default='calflag')
    rel_thresh_scaling = vdp.VisDependentProperty(default='log10')
    dividing_factor = vdp.VisDependentProperty(default=None)
    check_all_spws = vdp.VisDependentProperty(default=False)
    inf_EB_gaincal_combine = vdp.VisDependentProperty(default=False)
    refantignore = vdp.VisDependentProperty(default='')

    @refantignore.postprocess
    def refantignore(self, unprocessed):
        if not isinstance(unprocessed, (str, dict)):
            LOG.error('refantignore must be string or dictionary')
            raise ValueError('refantignore must be string or dictionary')
        refantignore_per_ms = {}
        if isinstance(unprocessed, dict):
            vis_not_selected = set(unprocessed) - set(self.vis)
            if vis_not_selected:
                LOG.warning(
                    '%s specified in refantignore not in task input MS list, will be ignored.',
                    utils.commafy(sorted(vis_not_selected), quotes=False),
                )
        for vis in self.vis:
            if isinstance(unprocessed, str):
                refantignore_per_ms[vis] = unprocessed
            if isinstance(unprocessed, dict):
                refantignore_per_ms[vis] = unprocessed.get(vis, '')

        return refantignore_per_ms

    usermask = vdp.VisDependentProperty(default=None)
    # input as dictionary for individual clean targets, e.g.
    #   usermask={'IRAS32':'IRAS32.rgn', 'IRS5N':'IRS5N.rgn'}
    #   usermask={'IRAS32':{'Band_6':'IRAS32.rgn'}, 'IRS5N':{'Band_6': 'IRS5N.rgn'}}
    #   in which .rgn is a CRTF region (CASA region format)
    # for clean targets not found in the (nested) dictionary structure (source->band), the usermask value will be empty (default)
    usermodel = vdp.VisDependentProperty(default=None)
    # input as dictiionary for individual clean targets, e.g.
    #   usermodel={'IRAS32':['IRAS32-model.tt0','IRAS32-model.tt1'], 'IRS5N':['IRS5N-model.tt0','IRS5N-model.tt1']}
    #   usermodel={'IRAS32':{'Band_6':['IRAS32-model.tt0','IRAS32-model.tt1']}, 'IRS5N':{'Band_6':['IRS5N-model.tt0','IRS5N-model.tt1']}}
    # for clean targets not found in the (nested) dictionary structure (source->band), the usermask value will be empty (default)

    allow_wproject = vdp.VisDependentProperty(default=False)
    restore_resources = vdp.VisDependentProperty(default=None)

    # docstring and type hints: supplements hif_selfcal
    def __init__(self, context, vis=None, field=None, spw=None, contfile=None, hm_imsize=None, hm_cell=None, n_solints=None,
                 amplitude_selfcal=None, gaincal_minsnr=None, refantignore=None,
                 minsnr_to_proceed=None, delta_beam_thresh=None, apply_cal_mode_default=None,
                 rel_thresh_scaling=None, dividing_factor=None, check_all_spws=None, inf_EB_gaincal_combine=None,
                 usermask=None, usermodel=None, allow_wproject=None,
                 apply=None, parallel=None, recal=None, restore_only=None, overwrite=None,
                 restore_resources=None):
        r"""Initialize Inputs.

        Args:
            context: Pipeline context object containing state information.

            vis: The list of input MeasurementSets. Defaults to the list of MeasurementSets defined in the pipeline context.

            field: Select field(s) for self-calibration. Use field name(s) NOT id(s). Mosaics are assumed to have common source/field names.

            spw: Select spectral windows for self-calibration.

            contfile: Name of file to specify line-free frequency ranges for selfcal continuum imaging. Defaults to ``'cont.dat'``.


            hm_imsize: self-calibration imaging dimension in pixels, or PB level for single fields.

            hm_cell: self-calibration imaging cell size.

            n_solints: number of solution intervals to attempt for self-calibration. Defaults to ``4``.

            amplitude_selfcal: Attempt amplitude self-calibration following phase-only self-calibration; if median time
                between scans of a given target is < 150s, solution intervals of ``300s`` and ``inf`` will be attempted,
                otherwise just ``inf`` will be attempted. Defaults to ``False``.

            gaincal_minsnr: Minimum S/N for a solution to not be flagged by gaincal. Defaults to ``2.0``.

            refantignore: Antennas to be ignored as reference antennas. Defaults to ``''``. Examples:

                * ``refantignore='ea02,ea03'``
                * ``refantignore={'ms1.ms':'ea02,ea03','ms2.ms': 'ea03'}``, specified at the per-ms level.

            minsnr_to_proceed: Minimum estimated S/N on a per antenna basis to attempt self-calibration of a source.
                Defaults to ``3.0``.

            delta_beam_thresh: Allowed fractional change in beam size for selfcalibration to accept results of a solution interval.
                Defaults to ``0.05``.

            apply_cal_mode_default: Apply mode to use for applycal task during self-calibration; same options as applycal.
                Defaults to ``'calflag'``.

            rel_thresh_scaling: Scaling type to determine how clean thresholds per solution interval should be determined going
                from the starting clean threshold to 3.0 * RMS for the final solution interval. Defaults to ``'log10'``.
                Available options: ``'linear'``, ``'log10'``, or ``'loge'`` (natural log)

            dividing_factor: Scaling factor to determine clean threshold for first self-calibration solution interval.
                Equivalent to (Peak S/N / dividing_factor) \* RMS as the first clean threshold;
                however, if  `(Peak S/N / dividing_factor) < 5.0`;
                a value of 5.0 is used for the first clean threshold.
                Defaults to ``40`` for < 8 GHz or ``15`` for > 8 GHz.

            check_all_spws: If ``True``, the S/N of mfs images created on a per-spectral-window basis will be compared at the
                initial stages final self-calibration. Defaults to ``False``.

            inf_EB_gaincal_combine: change gain solution combination parameters for the inf_EB solution interval. if ``True``,
                the gaincal combine parameter will be set to ``'scan,spw'``; if ``False``, the gaincal combine parameter will
                be set to ``'scan'``. Defaults to ``False``.


            allow_wproject: Allow the wproject heuristics for self-calibration imaging. Defaults to ``False``.

            apply: Apply final selfcal solutions back to the input MeasurementSets. Defaults to ``True``.

            parallel: Process multiple MeasurementSets in parallel using the casampi parallelization framework, and use CASA/tclean
                parallel imaging, when possible.

                Options: ``'automatic'``, ``'true'``, ``'false'``, ``True``, ``False``

                Default: ``None`` (equivalent to ```'automatic'``)

            recal: Always re-do self-calibration even solutions/caltables are found in the Pipeline context or json restore file.
                Defaults to `False`.

                Note that the selfcal solutions might not be applied if self-calibrated data labeled by the pipeline Datatypes already
                exists. See ``overwrite`` below.

            restore_only:   Only attempt to apply pre-existing selfcal calibration tables and would not run
                            the self-calibration sequence if their records (.selfcal.json, gaintables) are not present.
                            Defaults to `False`. ``restore_only`` will take precedence over ``recal``.

            overwrite: Allow overwriting pre-existing self-calibrated data of applicable field/spw labeled by DataType.
                Defaults to ``False``.

            restore_resources: Path to the restore resources from a standard run of hif_selfcal. hif_selfcal will automatically
                do an exhaustive search to lookup/extract/verify
                the selfcal restore resources, i.e., selfcal.json and all selfcal-caltable referred
                in selfcal.json, starting from *working/*, to *products/* and *rawdata/*.
                If restore_resources is specified, this file path will be evaluated first
                before the pre-defined exhaustive search list.
                The value can be the file path of *\*auxproducts.tgz* file or *\*selfcal.json* file.

            usermask: User mask to be used for self-calibration imaging. (not implemented)

            usermodel: User model to be used for self-calibration imaging. (not implemented)

        """
        super().__init__()
        self.context = context
        self.vis = vis
        self.field = field
        self.spw = spw
        self.contfile = contfile
        self.hm_imsize = hm_imsize
        self.hm_cell = hm_cell
        self.apply = apply
        self.parallel = parallel
        self.recal = recal
        self.restore_only = restore_only
        self.overwrite = overwrite
        self.refantignore = refantignore

        self.n_solints = n_solints
        self.amplitude_selfcal = amplitude_selfcal
        self.gaincal_minsnr = gaincal_minsnr
        self.minsnr_to_proceed = minsnr_to_proceed
        self.delta_beam_thresh = delta_beam_thresh
        self.apply_cal_mode_default = apply_cal_mode_default
        self.rel_thresh_scaling = rel_thresh_scaling
        self.dividing_factor = dividing_factor
        self.check_all_spws = check_all_spws
        self.inf_EB_gaincal_combine = inf_EB_gaincal_combine
        self.restore_resources = restore_resources
        self.usermask = usermask
        self.usermodel = usermodel
        self.allow_wproject = allow_wproject


@task_registry.set_equivalent_casa_task('hif_selfcal')
@task_registry.set_casa_commands_comment('Run self-calibration using the science target visibilities.')
class Selfcal(basetask.StandardTaskTemplate):
    Inputs = SelfcalInputs
    is_multi_vis_task = True

    def __init__(self, inputs):
        super().__init__(inputs)

    @staticmethod
    def _scal_targets_to_json(scal_targets: list[dict[str, Any]], filename: str | Path = 'selfcal.json') -> None:
        """Serialize scal_targets to a JSON file.
        
        Creates a JSON file containing the scal_targets data along with metadata including
        version, timestamp, and pipeline version. The 'heuristics' key is removed from
        each target before serialization.
        
        Args:
            scal_targets: List of target dictionaries containing calibration data
            filename: Output JSON filename or path
        """
        current_version = 1.0
        current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        scal_targets_copy = copy.deepcopy(scal_targets)

        # Remove heuristics from each target
        for target in scal_targets_copy:
            target.pop('heuristics', None)

        scal_targets_json = {
            'scal_targets': scal_targets_copy,
            'version': current_version,
            'datetime': current_datetime,
            'pipeline_version': environment.pipeline_revision,
        }

        output_path = Path(filename)

        # Write JSON with custom formatting (keys may include mixed strings/integers, so no sorting)
        with output_path.open('w', encoding='utf-8') as fp:
            json.dump(
                scal_targets_json,
                fp,
                sort_keys=False,
                indent=2,
                cls=JsonCustomEncoder,
                separators=(',', ': '),
            )

    @staticmethod
    def _json_debug_to_json_lite(filename='selfcal.debug.json'):
        """Convert a debug JSON file to a lightweight JSON file.

        This function reads a debug selfcal JSON file containing full self-calibration targets/library data and
        generates a lightweight version of with essential calibration data fields suitable for archival and selfcal solution 
        restoration.

        Args:
            filename: Path to the debug JSON file. Defaults to 'selfcal.debug.json'.
        """
        json_path = Path(filename)
        scal_targets = json.loads(json_path.read_text(encoding='utf-8'))
        Selfcal._scal_targets_to_json_lite(scal_targets['scal_targets'], filename=filename.replace('.debug.json', '.json'))

    @staticmethod
    def _scal_targets_to_json_lite(scal_targets: list[dict[str, Any]], filename: str | Path = 'selfcal.json') -> None:
        """Serialize scal_targets to a lightweight JSON file.

        Creates a JSON file with only essential calibration data fields. This reduces file size by
        including only critical information like field, spw_real, exceptions, and selected calibration
        library data.

        Args:
            scal_targets: List of target dictionaries containing calibration data.
            filename: Output JSON filename or path. Defaults to 'selfcal.json'.

        PIPE-2769: This function is not currently in use. It was originally intended to generate a "lite" selfcal.json 
        file as described in PIPE-2646. Howeever, we decide to export a full selfcal diagnostic instead as of PL2025.
        This private method is kept for future reference.       
        """
        current_version = 1.0
        current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        scal_targets_copy: list[dict[str, Any]] = []

        for target in scal_targets:
            target_lite = {
                'field': target['field'],
                'phasecenter': target['phasecenter'],
                'cell': target['cell'],
                'imsize': target['imsize'],
                'field_name': target['field_name'],
                'is_repr_target': target['is_repr_target'],
                'is_mosaic': target['is_mosaic'],
                'spw': target['spw'],
                'spw_real': target['spw_real'],
                'sc_exception': target['sc_exception'],
                'sc_workdir': target['sc_workdir'],
            }

            # Extract essential calibration library data if present
            if not target_lite['sc_exception'] and isinstance(target.get('sc_lib'), dict):
                target_lite['sc_lib'] = {}
                sc_lib = target['sc_lib']

                # Copy success status and RMS values; required for QA and weblog rendering
                for key in ('SC_success', 'RMS_orig', 'RMS_final'):
                    if key in sc_lib:
                        target_lite['sc_lib'][key] = sc_lib[key]

                # Copy solution intervals and band information; required for QA and weblog rendering
                for key in ('sc_solints', 'sc_band'):
                    if key in target:
                        target_lite[key] = target[key]

                # Copy final solution intervals; required for QA and weblog rendering
                for key in ('final_solints', 'final_phase_solints'):
                    if key in sc_lib:
                        target_lite['sc_lib'][key] = sc_lib[key]

                # Copy visibility list and essential calibration parameters
                if 'vislist' in sc_lib:
                    target_lite['sc_lib']['vislist'] = sc_lib['vislist']

                    # Copy essential calibration parameters for each visibility
                    for vis in target_lite['sc_lib']['vislist']:
                        target_lite['sc_lib'][vis] = {}
                        essential_keys = [
                            'gaintable_final',
                            'applycal_interpolate_final',
                            'spwmap_final',
                        ]

                        # Copy essential keys if they exist; required for QA and weblog rendering
                        for key in essential_keys:
                            if key in sc_lib.get(vis, {}):
                                target_lite['sc_lib'][vis][key] = sc_lib[vis][key]

                        # Copy solution interval data
                        for solint in target_lite.get('sc_solints', []):
                            if solint in sc_lib.get(vis, {}):
                                target_lite['sc_lib'][vis][solint] = {}

            scal_targets_copy.append(target_lite)

        scal_targets_json = {
            'scal_targets': scal_targets_copy,
            'version': current_version,
            'datetime': current_datetime,
            'pipeline_version': environment.pipeline_revision,
        }

        output_path = Path(filename)

        # Write JSON with custom formatting (keys may include mixed strings/integers, so no sorting)
        with output_path.open('w', encoding='utf-8') as fp:
            json.dump(
                scal_targets_json,
                fp,
                sort_keys=False,
                indent=2,
                cls=JsonCustomEncoder,
                separators=(',', ': '),
            )

    @staticmethod
    def _scal_targets_from_json(filename='selfcal.json'):
        """Deserilize scal_targets from a json file."""

        LOG.info('Reading the selfcal targets list from %s', filename)
        with open(filename, 'r', encoding='utf-8') as fp:
            scal_targets_json = json.load(fp)
        return scal_targets_json['scal_targets']

    def _apply_scal_check_caltable(self, sc_targets, mses=None):
        """Check if all calibration tables required for applying the selfcal solutions are ready to use.

        Returns:
            caltable_list:  a list of calibration tables requested based on the calapply information inside scal_targets
            caltable_ready: a list of the requested cal tables that are ready to be applied.
        """
        if mses is None:
            obs_run = self.inputs.context.observing_run
            mses_regcal_contline = obs_run.get_measurement_sets_of_type(
                [DataType.REGCAL_CONT_SCIENCE, DataType.REGCAL_CONTLINE_SCIENCE], msonly=True)
            mses_regcal_line = obs_run.get_measurement_sets_of_type([DataType.REGCAL_LINE_SCIENCE], msonly=True)
            mses = mses_regcal_contline+mses_regcal_line

        # collect a name list of MSes which we could apply the selfcal solutions to.
        vislist_calto = [ms.name for ms in mses]
        caltable_list = []
        caltable_ready = []
        for cleantarget in sc_targets:
            if cleantarget['sc_exception']:
                continue
            sc_lib = cleantarget['sc_lib']
            sc_workdir = cleantarget['sc_workdir']
            if not sc_lib['SC_success']:
                continue

            for vis in sc_lib['vislist']:
                vis_base = os.path.splitext(os.path.basename(vis))[0]
                if vis_base.endswith('_cont'):
                    vis_base = vis_base[:-5]
                for idx, gaintable in enumerate(sc_lib[vis]['gaintable_final']):
                    for vis_calto in vislist_calto:
                        if vis_calto.startswith(vis_base):
                            gaintable = os.path.join(sc_workdir, sc_lib[vis]['gaintable_final'][idx])
                            if gaintable not in caltable_list:
                                caltable_list.append(gaintable)
                            if os.path.exists(gaintable):
                                if gaintable not in caltable_ready:
                                    caltable_ready.append(gaintable)
        LOG.info('selfcal/caltable(s) request : %r', caltable_list)
        LOG.info('selfcal/caltable(s) ready   : %r', caltable_ready)

        return caltable_list, caltable_ready

    def _check_restore_from_resources(self):
        """Check if we can do selfcal restore from the restore resources."""
        scal_targets = None
        pat_list = ['*.auxproducts.tgz', '*.selfcal.json',
                    '../products/*.auxproducts.tgz', '*.selfcal.json',
                    '../rawdata/*.auxproducts.tgz', '*.selfcal.json']
        match_list = ('sc_workdir*', '*.selfcal.json')

        if self.inputs.restore_resources is not None:
            pat_list = [self.inputs.restore_resources, '*selfcal.json']+pat_list

        for pat in pat_list:
            for check_file in utils.glob_ordered(pat):
                if check_file.endswith('.auxproducts.tgz') and tarfile.is_tarfile(check_file):
                    with tarfile.open(check_file, 'r:gz') as tar:
                        members = []
                        for member in tar.getmembers():
                            is_resource = any([fnmatch(member.name, pat) for pat in match_list])
                            if is_resource:
                                members.append(member)
                                LOG.info('extracting: %s from %s', member.name, check_file)
                        tar.extractall(members=members)
                if check_file.endswith('.selfcal.json'):
                    scal_targets_json = self._scal_targets_from_json(check_file)
                    if scal_targets_json is not None:
                        caltable_list, caltable_ready = self._apply_scal_check_caltable(scal_targets_json)
                        # we verify the existances of required caltables in-flight as the file search progresses.
                        if len(caltable_ready) < len(caltable_list):
                            LOG.warning(
                                'The required selfcal caltable(s) is missing if we use scal_targets from the json file %s',
                                check_file)
                        else:
                            scal_targets = scal_targets_json
            if scal_targets is not None:
                break

        return scal_targets

    def _check_restore_from_context(self):
        """Check if we can do selfcal restore from scal_targets saved in the context."""
        scal_targets = None
        if self.inputs.context.selfcal_targets:
            scal_targets_last = self.inputs.context.selfcal_targets
            LOG.info(
                'Found selfcal results in the context. Looking for the required caltables for applying the selfcal solutions.'
            )
            caltable_list, caltable_ready = self._apply_scal_check_caltable(scal_targets_last)
            if len(caltable_ready) < len(caltable_list):
                LOG.warning('The required selfcal caltable(s) is missing if we use scal_targets from the context.')
            else:
                scal_targets = scal_targets_last

        return scal_targets

    def prepare(self):

        inputs = self.inputs
        if inputs.vis in (None, [], ''):
            # If no suitable datatype, by-pass the hif_selfcal stage.
            required_data_type_desc = ', '.join(dt.name for dt in SelfcalInputs.processing_data_type)

            LOG.warning('No data matching any of the required datatypes: %s; '
                        'please review the registered MS datatype information.',
                        required_data_type_desc)
                
            return SelfcalResults([], None, None, None, False)

        if not isinstance(inputs.vis, list):
            inputs.vis = [inputs.vis]

        scal_targets_last = scal_targets_json = None

        # Check if we can use a scal_targets list from the Pipeline context
        scal_targets_last = self._check_restore_from_context()

        # Check if we can use a scal_targets list from restore_resources
        scal_targets_json = self._check_restore_from_resources()

        obs_run = self.inputs.context.observing_run

        mses_columns_regcal_contline, _ = obs_run.get_measurement_sets_of_type(
            [DataType.REGCAL_CONT_SCIENCE, DataType.REGCAL_CONTLINE_SCIENCE], msonly=False)
        mses_columns_selfcal_contline, _ = obs_run.get_measurement_sets_of_type(
            [DataType.SELFCAL_CONT_SCIENCE, DataType.SELFCAL_CONTLINE_SCIENCE], msonly=False)
        mses_regcal_contline = list(mses_columns_regcal_contline)
        mses_selfcal_contline = list(mses_columns_selfcal_contline)

        mses_regcal_line = obs_run.get_measurement_sets_of_type([DataType.REGCAL_LINE_SCIENCE], msonly=True)
        mses_selfcal_line = obs_run.get_measurement_sets_of_type([DataType.SELFCAL_LINE_SCIENCE], msonly=True)

        scal_targets = []
        if not self.inputs.recal:
            # only sideload the selfcal restore information from the context or json if recal=False
            if scal_targets_last is not None:
                scal_targets = scal_targets_last
                LOG.info('Staging the previous selfcal solutions from the pipeline context.')
            if scal_targets_json is not None:
                scal_targets = scal_targets_json
                LOG.info('Staging the previous selfcal solutions from selfcal.json.')

        # if applycal_result_contline is None, then contline applycal is not triggered.
        # if applycal_result_line is None, then line applycal is not triggered.
        # if selfcal_resources is None, then the selfcal solver is not triggered, even selfcal solution could be applied.
        applycal_result_contline = applycal_result_line = selfcal_resources = None
        is_restore = True

        if not scal_targets:

            if self.inputs.restore_only:
                LOG.info('No valid selfcal restoration resource is found and restore_only=True; skip a new self-calibration sequence.')
                return SelfcalResults(
                    scal_targets, applycal_result_contline, applycal_result_line, selfcal_resources, is_restore)

            if self.inputs.recal:
                LOG.info('recal=True, override any existing selfcal solution in context or json, '
                         'and alway execute the selfcal solver.')
            LOG.info('Execute the selfcal solver.')
            scal_targets = self._solve_selfcal()
            is_restore = False

            selfcal_json = self.inputs.context.name+'.selfcal.json'
            self._scal_targets_to_json(scal_targets, filename=selfcal_json)

            scal_caltable, _ = self._apply_scal_check_caltable(scal_targets, mses_regcal_contline+mses_regcal_line)
            selfcal_resources = [selfcal_json] + scal_caltable
            LOG.debug('selfcal resources list: %r', selfcal_resources)

            if not scal_targets:
                LOG.info('No valid selfcal field returned by the selfcal solver; skip the selfcal apply step.')
                return SelfcalResults(
                    scal_targets, applycal_result_contline, applycal_result_line, selfcal_resources, is_restore)

        if self.inputs.apply:

            if mses_regcal_contline:
                if mses_selfcal_contline:
                    LOG.warning(
                        'Found DataType:SELFCAL_CONT*_SCIENCE before attempting to apply selfcal solutions.'
                    )
                    for ms in mses_selfcal_contline:
                        LOG.debug('  %s: %s', ms.basename, ms.data_column)
                else:
                    LOG.info(
                        'No DataType:SELFCAL_CONT*_SCIENCE found before attempting to apply selfcal solutions.'
                    )

                if mses_selfcal_contline and not self.inputs.overwrite:
                    LOG.warning(
                        'Skip applying selfcal solutions to the REGCAL_CONT*_SCIENCE MS(es) due to '
                        'the presence of DataType:SELFCAL_CONT*_SCIENCE and recal/overwrite=False.'
                    )
                else:
                    LOG.info('Applying selfcal solutions to the REGCAL_CONT*_SCIENCE data.')
                    applycal_result_contline = self._apply_scal(scal_targets, mses_regcal_contline)
                    LOG.info(
                        'DataType info for he REGCAL_CONT*_SCIENCE MS(es) after applying selfcal solutions:'
                    )
                    for ms in mses_regcal_contline:
                        LOG.debug('  %s: %s', ms.basename, ms.data_column)

            if mses_regcal_line:
                if mses_selfcal_line:
                    LOG.warning('Found DataType:SELFCAL_LINE_SCIENCE before attempting to apply selfcal solutions.')
                    for ms in mses_selfcal_line:
                        LOG.debug('  %s: %s', ms.basename, ms.data_column)
                else:
                    LOG.info('No DataType:SELFCAL_LINE_SCIENCE found before attempting to apply selfcal solutions.')

                if mses_selfcal_line and not self.inputs.overwrite:
                    LOG.warning(
                        'Skip applying selfcal solutions to the REGCAL_LINE_SCIENCE MS(es). due to '
                        'the presence of DataType:SELFCAL_CONT*_SCIENCE and recal=False.'
                    )
                else:
                    LOG.info('Attempt to apply any selfcal solutions to the REGCAL_LINE_SCIENCE MS(es)')

                    applycal_result_line = self._apply_scal(scal_targets, mses_regcal_line)
                    LOG.info('DataType info for the REGCAL_LINE_SCIENCE MS(es) after applying selfcal solutions:')
                    for ms in mses_regcal_line:
                        LOG.debug('  %s: %s', ms.basename, ms.data_column)

        return SelfcalResults(
            scal_targets, applycal_result_contline, applycal_result_line, selfcal_resources, is_restore
        )

    def _solve_selfcal(self):

        # collect the target list
        scal_targets = self._get_scaltargets(scal=True)
        scal_targets = self._check_scaltargets(scal_targets)
        if not scal_targets:
            return scal_targets

        # split per-cleantarget MSes with optional spectral line flagging
        self._split_scaltargets(scal_targets)

        # start the selfcal sequence.

        if self.inputs.inf_EB_gaincal_combine:
            inf_EB_gaincal_combine = 'scan,spw'
        else:
            inf_EB_gaincal_combine = 'scan'

        parallel = mpihelpers.parse_parallel_input_parameter(self.inputs.parallel)
        taskqueue_parallel_request = len(scal_targets) > 1 and parallel
        self.inputs.refantignore
        with TaskQueue(parallel=taskqueue_parallel_request) as tq:
            for target in scal_targets:
                target['sc_parallel'] = (parallel and mpihelpers.is_mpi_ready() and not tq.is_async())
                tq.add_functioncall(self._run_selfcal_sequence, target,
                                    gaincal_minsnr=self.inputs.gaincal_minsnr,
                                    minsnr_to_proceed=self.inputs.minsnr_to_proceed,
                                    delta_beam_thresh=self.inputs.delta_beam_thresh,
                                    apply_cal_mode_default=self.inputs.apply_cal_mode_default,
                                    rel_thresh_scaling=self.inputs.rel_thresh_scaling,
                                    dividing_factor=self.inputs.dividing_factor,
                                    refantignore=self.inputs.refantignore,
                                    check_all_spws=self.inputs.check_all_spws,
                                    n_solints=self.inputs.n_solints,
                                    do_amp_selfcal=self.inputs.amplitude_selfcal,
                                    inf_EB_gaincal_combine=inf_EB_gaincal_combine,
                                    executor=self._executor,
                                    use_pickle=True)
        tq_results = tq.get_results()

        for idx, target in enumerate(scal_targets):
            scal_library, _ = tq_results[idx]
            sc_exception = False
            if scal_library is None:
                sc_exception = True
            if not sc_exception:
                try:
                    # scal_library here is expected to contain only a single target/band combination.
                    sc_field = list(scal_library.keys())[0]                  # the selfcal heuristics target name
                    sc_band = list(scal_library[sc_field].keys())[0]        # the selfcal heuristics band name

                    if sc_field != target['sc_field']:
                        # note scal_library is keyed by field name without quotes at this moment.
                        # see. https://casadocs.readthedocs.io/en/stable/notebooks/visibility_data_selection.html#The-field-Parameter
                        #       utils.fieldname_for_casa() and
                        #       utils.dequote()
                        LOG.warning(
                            'The field name of the selfcal library is different from the clean target dequoted field name: %s != %s',
                            sc_field, target['sc_field'])
                    target['sc_band'] = sc_band

                    target['sc_lib'] = scal_library[sc_field][sc_band]
                    target['sc_solints'] = target['sc_lib']['solints']
                    target['sc_rms_scale'] = target['sc_lib']['RMS_final'] / target['sc_lib']['theoretical_sensitivity']
                    target['sc_success'] = target['sc_lib']['SC_success']
                except Exception as err:
                    traceback_msg = traceback.format_exc()
                    LOG.debug('Exception: %s', err)
                    LOG.info(traceback_msg)
                    sc_exception = True
            if sc_exception:
                LOG.warning(
                    'An exception was triggered during the self-calibration sequence for target=%r spw=%r in the working directory: %s .',
                    target['field'],
                    target['spw'],
                    target['sc_workdir'])
            target['sc_exception'] = sc_exception

        return scal_targets

    @staticmethod
    def _run_selfcal_sequence(scal_target, **kwargs):
        """Run the selfcal sequence for a single target.
        
        Note that this function is executed in a TaskQueue so potentially on an MPI server process.
        """
        workdir = os.path.abspath('./')
        selfcal_library = trackback_msg = None

        try:
            os.chdir(scal_target['sc_workdir'])
            LOG.info('')
            LOG.info('Running auto_selfcal heuristics on target %s spw %s from %s',
                     scal_target['field'], scal_target['spw'], scal_target['sc_workdir'])
            LOG.info('')
            selfcal_heuristics = auto_selfcal.SelfcalHeuristics(scal_target, **kwargs)
            # import pickle
            # with open('selfcal_heuristics.pickle', 'wb') as handle:
            #     pickle.dump(selfcal_library, handle, protocol=pickle.HIGHEST_PROTOCOL)

            selfcal_library = selfcal_heuristics()
        except Exception as err:
            traceback_msg = traceback.format_exc()
            LOG.debug('Exception: %s', err)
            LOG.info(traceback_msg)
        finally:
            os.chdir(workdir)
            if scal_target['sc_parallel']:
                # sc_parallel=True indicats that we are certainly running tclean(parallel=true) in a sequential TaskQueue.
                # A side effect of doing this while changing cwd is that the working directory of MPIServers will be "stuck"
                # to the one where tclean(paralllel=True) started.
                # As a workaround, we send the chdir command to the MPIServers explicitly.
                mpihelpers.mpiclient.push_command_request(
                    f'os.chdir({workdir!r})', block=True, target_server=mpihelpers.mpi_server_list)

        return selfcal_library, trackback_msg

    def _apply_scal(self, sc_targets, mses):

        calapps = []
        vislist = []

        # collect a name list of MSes which we could apply the selfcal solutions to.
        vislist_calto = [ms.name for ms in mses]

        for cleantarget in sc_targets:
            if cleantarget['sc_exception']:
                continue
            sc_lib = cleantarget['sc_lib']
            if not sc_lib['SC_success']:
                continue
            sc_workdir = cleantarget['sc_workdir']

            for vis in sc_lib['vislist']:
                vis_base = os.path.splitext(os.path.basename(vis))[0]
                if vis_base.endswith('_cont'):
                    vis_base = vis_base[:-5]
                for idx, gaintable in enumerate(sc_lib[vis]['gaintable_final']):
                    for vis_calto in vislist_calto:
                        if vis_calto.startswith(vis_base):

                            # workaround a potential issue from heuristics.auto_selfcal when gaintable has only one element, when it's not a list of list.
                            spwmap_final = sc_lib[vis]['spwmap_final']
                            if any(not isinstance(spwmap, list) for spwmap in spwmap_final) or not spwmap_final:
                                spwmap_final = [spwmap_final]

                            gaintable = os.path.join(sc_workdir, sc_lib[vis]['gaintable_final'][idx])
                            calfrom = callibrary.CalFrom(
                                gaintable=gaintable, interp=sc_lib[vis]['applycal_interpolate_final'][idx],
                                calwt=False, spwmap=spwmap_final[idx],
                                caltype='gaincal')
                            calto = callibrary.CalTo(
                                vis=vis_calto, field=cleantarget['field'],
                                spw=cleantarget['spw_real'][vis])
                            calapps.append(callibrary.CalApplication(calto, calfrom))
                            vislist.append(vis_calto)

        for calapp in calapps:
            self.inputs.context.callibrary.add(calapp.calto, calapp.calfrom)

        vislist = sorted(set(vislist))
        parallel = mpihelpers.parse_parallel_input_parameter(self.inputs.parallel)
        taskqueue_parallel_request = len(vislist) > 1 and parallel
        with TaskQueue(parallel=taskqueue_parallel_request, executor=self._executor) as tq:
            for vis in vislist:
                task_args = {'vis': vis, 'applymode': self.inputs.apply_cal_mode_default, 'intent': 'TARGET'}
                tq.add_pipelinetask(SerialIFApplycal, task_args, self.inputs.context)

        tq_results = tq.get_results()

        return tq_results

    def analyse(self, results):
        return results

    def _check_scaltargets(self, scal_targets):
        """Filter out the sources that the selfcal heuristics should not process.

        PIPE-1447/PIPE-1915: we do not execute selfcal heuristics for mosaic or ephemeris sources.
        """
        final_scal_target = []
        for scal_target in scal_targets:
            disable_mosaic = False
            if disable_mosaic and scal_target['is_mosaic']:
                LOG.warning(
                    'The self-calibration heuristics do not fully support mosaic yet. Skipping target=%r spw=%r.',
                    scal_target['field'],
                    scal_target['spw'])
                continue
            if scal_target['is_eph_obj']:
                LOG.warning(
                    'The self-calibration heuristics do not fully support ephemeris sources yet. Skipping target=%r spw=%r.',
                    scal_target['field'],
                    scal_target['spw'])
                continue
            final_scal_target.append(scal_target)

        return final_scal_target

    def _get_scaltargets(self, scal=True):
        """Get the cleantarget list from the context.

        This essenially runs MakeImList and go through all nesscary steps to get the target list.
        However, it will pick up the selfcal heuristics from imageparams_factory,ImageParamsHeuristicsFactory
        """
        telescope = self.inputs.context.project_summary.telescope
        if telescope == 'ALMA':
            repr_ms = self.inputs.ms[0]
            diameter = min([a.diameter for a in repr_ms.antennas])
            if diameter == 7.0:
                telescope = 'ACA'
            else:
                telescope = 'ALMA'

        makeimlist_inputs = MakeImList.Inputs(
            self.inputs.context,
            vis=None,
            intent='TARGET',
            specmode='cont',
            clearlist=True,
            scal=scal,
            contfile=self.inputs.contfile,
            field=self.inputs.field,
            spw=self.inputs.spw,
            hm_imsize=self.inputs.hm_imsize,
            hm_cell=self.inputs.hm_cell,
            allow_wproject=self.inputs.allow_wproject,
            datatype='regcal',
            parallel=self.inputs.parallel,
            # PIPE-2449: prevent applying imageprecheck customizations during planning
            # During imaging planning for self-calibration targets, customizations
            # from the imageprecheck step should not be applied. Here we removes those
            # customizations from the local context.
            uvtaper=[''],  # disable possible uvtaper specification from context/imageprecheck
            robust=0.5,  # disable potential robust specification from context/imageprecheck
        )
        makeimlist_task = MakeImList(makeimlist_inputs)
        makeimlist_results = makeimlist_task.execute()

        scal_targets = makeimlist_results.targets

        if isinstance(self.inputs.usermask, dict):
            usermask = self.inputs.usermask
        else:
            usermask = {}
        if isinstance(self.inputs.usermodel, dict):
            usermodel = self.inputs.userrmodel
        else:
            usermodel = {}

        for scal_target in scal_targets:
            scal_target['sc_telescope'] = telescope
            _, repr_source, repr_spw, _, _, repr_real, _, _, _, _ = scal_target['heuristics'].representative_target()
            if str(repr_spw) in scal_target['spw'].split(',') and repr_source == utils.dequote(scal_target['field']):
                is_representative = True
            else:
                is_representative = False
            scal_target['is_repr_target'] = is_representative
            scal_target['is_mosaic'] = scal_target['heuristics'].is_mosaic(scal_target['field'], scal_target['intent'])
            scal_target['is_eph_obj'] = scal_target['heuristics'].is_eph_obj(scal_target['field'])
            # Note that scal_library is currently keyed by field name without quotes.
            # We use the 'field_name' value to retrieve self-calibration results from scal_library generated by the self-cal solver.
            scal_target['field_name'] = utils.dequote(scal_target['field'])
            scal_target['sc_field'] = utils.dequote(scal_target['field'])
            # not supporting the target->band nest dictionary structure yet.
            scal_target['sc_usermask'] = usermask.get(scal_target['sc_field'], '')
            scal_target['sc_usermodel'] = usermodel.get(scal_target['sc_field'], '')

        LOG.debug('scal_targets: %s', scal_targets)

        return scal_targets

    def _remove_ms(self, vis):

        vis_dirs = [vis, vis+'.flagversions']
        for vis_dir in vis_dirs:
            if os.path.isdir(vis_dir):
                LOG.debug(f'removing {vis_dir}')
                self._executable.rmtree(vis_dir)

    def _split_scaltargets(self, scal_targets):
        """Split the input MSes into smaller MSes per cleantargets effeciently."""
        # mt_inputvis_list aggregates input vis argument values of expected mstransform calls
        # therefore len(mt_inputvis_list) represents the number of ms to be split out
        mt_inputvis_list = [(vis, '_CONTLINE_' in target['datatype'])
                            for target in scal_targets for vis in target['vis']]

        parallel = mpihelpers.parse_parallel_input_parameter(self.inputs.parallel)
        taskqueue_parallel_request = len(mt_inputvis_list) > 1 and parallel

        inputvis_list = utils.deduplicate([m[0] for m in mt_inputvis_list])
        outputvis_list = []

        # PIPE-2497: Attempting line flagging for all input visibilities,
        # regardless of whether the datatype is "CONTLINE" or "CONT".
        self._flag_lines(inputvis_list)

        with utils.ignore_pointing(inputvis_list):
            with TaskQueue(parallel=taskqueue_parallel_request) as tq:

                for target in scal_targets:

                    vislist = []

                    band_str = self._get_band_name(target).lower().replace(' ', '_')
                    sc_workdir = filenamer.sanitize(f'sc_workdir_{target["field"]}_{band_str}')

                    if os.path.isdir(sc_workdir):
                        shutil.rmtree(sc_workdir)
                    os.mkdir(sc_workdir)

                    sc_workdir_contfile = os.path.join(sc_workdir, 'cont.dat')
                    if os.path.isfile(self.inputs.contfile) and not os.path.isfile(sc_workdir_contfile):
                        shutil.copy(self.inputs.contfile, sc_workdir_contfile)

                    spw_real = {}
                    field = target['field']
                    uvrange = target['uvrange']
                    for vis in target['vis']:

                        # we use virtualspw here for the naming convention (similar to the imaging naming convention).
                        real_spwsel = self.inputs.context.observing_run.get_real_spwsel([target['spw']], [vis])[0]
                        spw_real[vis] = real_spwsel
                        outputvis = os.path.join(sc_workdir, os.path.basename(vis))
                        self._remove_ms(outputvis)

                        ms = self.inputs.context.observing_run.get_ms(vis)
                        spws = ms.get_spectral_windows(real_spwsel)

                        mean_freq = np.mean([float(spw.mean_frequency.to_units(
                            measures.FrequencyUnits.HERTZ)) for spw in spws])
                        bwarray = np.array([float(spw.bandwidth.to_units(measures.FrequencyUnits.HERTZ))
                                           for spw in spws])
                        chanarray = np.array([spw.num_channels for spw in spws])
                        chanwidth_desired_hz = self.get_desired_width(mean_freq)
                        chanbin = self.get_spw_chanbin(bwarray, chanarray, chanwidth_desired_hz)

                        task_args = {'vis': vis, 'outputvis': outputvis, 'field': field, 'spw': real_spwsel,
                                     'uvrange': uvrange, 'chanaverage': True, 'chanbin': chanbin, 'usewtspectrum': True,
                                     'datacolumn': 'data', 'reindex': False, 'keepflags': True}
                        outputvis_list.append((vis, outputvis))

                        tq.add_jobrequest(casa_tasks.mstransform, task_args, executor=self._executor)
                        vislist.append(os.path.basename(outputvis))

                    target['sc_workdir'] = sc_workdir
                    target['spw_real'] = spw_real
                    target['sc_vislist'] = vislist

        self._restore_flags(inputvis_list)

        for outputvis in outputvis_list:
            # Copy across requisite XML files.
            self._copy_xml_files(outputvis[0], outputvis[1])

        return scal_targets

    def _get_band_name(self, target):
        """Get the band name for the target."""
        spw_virtual = target['spw'].split(',')[0]
        ms = self.inputs.context.observing_run.get_ms(target['vis'][0])
        spw_real = self.inputs.context.observing_run.virtual2real_spw_id(spw_virtual, ms)
        if self.inputs.context.project_summary.telescope in ('VLA', 'JVLA', 'EVLA'):
            spw2band = ms.get_vla_spw2band()
            band_name = spw2band[ms.get_spectral_windows(spw_real)[0].id]+' band'
        else:
            band_name = ms.get_spectral_windows(spw_real)[0].band
        return band_name

    @staticmethod
    def _copy_xml_files(vis, outputvis):
        for xml_filename in ['SpectralWindow.xml', 'DataDescription.xml']:
            vis_source = os.path.join(vis, xml_filename)
            outputvis_targets_contline = os.path.join(outputvis, xml_filename)
            if os.path.exists(vis_source) and os.path.exists(outputvis):
                LOG.info('Copying %s from original MS to science targets cont+line MS', xml_filename)
                LOG.trace('Copying %s: %s to %s', xml_filename, vis_source, outputvis_targets_contline)
                shutil.copyfile(vis_source, outputvis_targets_contline)

    @staticmethod
    def get_desired_width(meanfreq):
        """Get the desired channel width for the given mean frequency."""
        if meanfreq >= 50.0e9:
            chanwidth = 15.625e6
        elif (meanfreq < 50.0e9) and (meanfreq >= 40.0e9):
            chanwidth = 16.0e6
        elif (meanfreq < 40.0e9) and (meanfreq >= 26.0e9):
            chanwidth = 8.0e6
        elif (meanfreq < 26.0e9) and (meanfreq >= 18.0e9):
            chanwidth = 16.0e6
        elif (meanfreq < 18.0e9) and (meanfreq >= 8.0e9):
            chanwidth = 8.0e6
        elif (meanfreq < 8.0e9) and (meanfreq >= 4.0e9):
            chanwidth = 4.0e6
        elif (meanfreq < 4.0e9) and (meanfreq >= 2.0e9):
            chanwidth = 4.0e6
        elif (meanfreq < 4.0e9):
            chanwidth = 2.0e6
        return chanwidth

    @staticmethod
    def get_spw_chanbin(bwarray, chanarray, chanwidth=15.625e6):
        """Calculate the number of channels to average over for each spw.

        note: mstransform only accept chanbin as integer.
        """
        avgarray = [1]*len(bwarray)
        for idx, bw in enumerate(bwarray):
            nchan = bw/chanwidth
            nchan = max(np.round(nchan), 1.0)
            avgarray[idx] = int(chanarray[idx]/nchan)
            if avgarray[idx] < 1.0:
                avgarray[idx] = 1
        return avgarray

    def _restore_flags(self, vislist):
        """Restore the before lineflagging flag state, after splitting per_cleantarget tmp MS."""

        for vis in vislist:
            # restore to the starting flags
            # self._executable.initweights(vis=vis, wtmode='delwtsp')  # remove channelized weights
            if os.path.exists(vis+".flagversions/flags.before_hif_selfcal"):
                self._executable.flagmanager(vis=vis, mode='restore', versionname='before_hif_selfcal',
                                             comment='Flag states before hif_selfcal')

    def _flag_lines(self, vislist):
        """Flag the lines when cont.dat is present, before splitting per_cleantarget tmp MS."""

        for vis in vislist:
            # self._executable.initweights(vis=vis, wtmode='weight', dowtsp=True)  # initialize channelized weights
            # save starting flags or restore to the starting flags
            if os.path.exists(vis+".flagversions/flags.before_hif_selfcal"):
                self._executable.flagmanager(vis=vis, mode='restore', versionname='before_hif_selfcal',
                                             comment='Flag states before hif_selfcal')
            else:
                self._executable.flagmanager(vis=vis, mode='save', versionname='before_hif_selfcal')

            # note that contfile_to_chansel will do the virtual2real spw translation automatically.
            lines_sel_dict = contfile_to_chansel(
                vis, self.inputs.context, contfile=self.inputs.contfile, excludechans=True)

            for field, lines_sel in lines_sel_dict.items():
                LOG.info("Flagging lines in field {} with the spw selection {}".format(field, lines_sel))
                # lines_sel_dict is keyed with original field names, which might not be safe for CASA/field
                # selections.
                self._executable.flagdata(vis=vis, field=utils.fieldname_for_casa(field), mode='manual',
                                          spw=lines_sel, flagbackup=False, action='apply')
