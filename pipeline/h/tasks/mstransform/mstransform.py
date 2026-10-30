"""Base classes and utilities for mstransform pipeline tasks.

This module provides common Inputs, Task, and Results classes that wrap the
CASA mstransform task for data splitting, averaging, and spectral regridding.
Specialized pipeline tasks (e.g. hif_mstransform, hsd_mstransform, hifv_mstransform)
inherit from these base classes.
"""
from __future__ import annotations

import collections.abc
import itertools
import os
import shutil
from typing import TYPE_CHECKING, Any

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.sessionutils as sessionutils
import pipeline.infrastructure.tablereader as tablereader
import pipeline.infrastructure.utils as utils
import pipeline.infrastructure.vdp as vdp
from pipeline.domain import DataType
from pipeline.h.heuristics.mstransform_freq_regrid import configure_frequency
from pipeline.infrastructure import casa_tasks, exceptions, mpihelpers, task_registry
from pipeline.infrastructure.mpihelpers import TaskQueue

if TYPE_CHECKING:
    from pipeline.domain import MeasurementSet
    from pipeline.infrastructure.launcher import Context

LOG = infrastructure.get_logger(__name__)

__all__ = [
    'Mstransform',
    'MstransformInputs',
    'MstransformResults',
    'SerialMstransform',
]


class MstransformInputs(vdp.StandardInputs):
    """Inputs class for the base Mstransform pipeline task.

    This class defines the common inputs for all mstransform-derived tasks.
    """

    chanbin = vdp.VisDependentProperty(default=1)
    timebin = vdp.VisDependentProperty(default='0s')
    datacolumn = vdp.VisDependentProperty(default='')
    field = vdp.VisDependentProperty(default='')
    intent = vdp.VisDependentProperty(default='')
    spw = vdp.VisDependentProperty(default='')
    outframe = vdp.VisDependentProperty(default='')
    regridms = vdp.VisDependentProperty(default=None)
    mode = vdp.VisDependentProperty(default='channel')
    start = vdp.VisDependentProperty(default='')
    width = vdp.VisDependentProperty(default='')
    nchan = vdp.VisDependentProperty(default=-1)
    per_spw = vdp.VisDependentProperty(default=False)
    per_field = vdp.VisDependentProperty(default=False)

    parallel = sessionutils.parallel_inputs_impl(default=False)

    @vdp.VisDependentProperty
    def outputvis(self) -> str:
        """Default output visibility name, appending '_targets.ms' to root name."""
        vis_root = os.path.splitext(self.vis)[0]
        return vis_root + '_targets.ms'

    def __init__(
        self,
        context: Context,
        output_dir: str | None = None,
        vis: str | list[str] | None = None,
        outputvis: str | list[str] | None = None,
        field: str | None = None,
        intent: str | None = None,
        spw: str | None = None,
        datacolumn: str | None = None,
        chanbin: int | None = None,
        timebin: str | None = None,
        outframe: str | None = None,
        regridms: bool | None = None,
        mode: str | None = None,
        start: str | None = None,
        width: str | None = None,
        nchan: int | None = None,
        per_spw: bool | None = None,
        per_field: bool | None = None,
        parallel: bool | str | None = None,
    ) -> None:
        """Initialize Inputs.

        Args:
            context: Pipeline context object containing state information.
            output_dir: Output directory. Defaults to None (current working directory).
            vis: The list of input MeasurementSets.
            outputvis: The list of output MeasurementSets.
            field: Select field names or IDs.
            intent: Select intents to transform.
            spw: Select spectral windows to transform.
            datacolumn: Select data column ('data', 'corrected', etc.).
            chanbin: Channel binning factor.
            timebin: Time binning factor.
            outframe: Frequency frame for output MS.
            regridms: Flag for frame changes.
            mode: Mode for regridding ('channel', 'frequency', 'velocity').
            start: Start channel/frequency/velocity for regridding.
            width: Width of output channel for regridding.
            nchan: Number of output channels for regridding.
            per_spw: If True, execute mstransform separately for each spectral window in spw.
            per_field: If True, execute mstransform separately for each field in field.
            parallel: Process multiple MeasurementSets in parallel using the casampi framework.
        """
        super().__init__()

        self.context = context
        self.output_dir = output_dir
        self.vis = vis
        self.outputvis = outputvis
        self.field = field
        self.intent = intent
        self.spw = spw
        self.datacolumn = datacolumn
        self.chanbin = chanbin
        self.timebin = timebin
        self.outframe = outframe
        self.regridms = regridms
        self.mode = mode
        self.start = start
        self.width = width
        self.nchan = nchan
        self.per_spw = per_spw
        self.per_field = per_field
        self.parallel = parallel

    def to_casa_args(self) -> dict[str, Any]:
        """Convert input parameters to a dictionary of arguments for CASA mstransform."""
        d = super().to_casa_args()

        d['reindex'] = False

        if self.chanbin > 1:
            d['chanaverage'] = True
        else:
            d['chanaverage'] = False

        if self.timebin > '0s':
            d['timeaverage'] = True
        else:
            d['timeaverage'] = False

        for key in ('parallel', 'per_spw', 'per_field'):
            d.pop(key, None)

        return d


class SerialMstransform(basetask.StandardTaskTemplate):
    """Serial worker task for executing CASA mstransform."""

    Inputs = MstransformInputs

    def _create_result(self, inputs: MstransformInputs) -> MstransformResults:
        """Create the results structure."""
        output_data_type = getattr(inputs, 'output_data_type', None)
        return MstransformResults(vis=inputs.vis, outputvis=inputs.outputvis, output_data_type=output_data_type)

    def _copy_auxiliary_files(self, vis: str, outputvis: str) -> None:
        """Hook to copy auxiliary files across from input to output MS."""
        self._copy_xml_files(vis, outputvis)

    @staticmethod
    def _copy_xml_files(vis: str, outputvis: str) -> None:
        """Copy requisite XML files from input to output MS if they exist."""
        for xml_filename in ['SpectralWindow.xml', 'DataDescription.xml']:
            vis_source = os.path.join(vis, xml_filename)
            outputvis_dest = os.path.join(outputvis, xml_filename)
            if os.path.exists(vis_source) and os.path.exists(outputvis):
                LOG.info('Copying %s from original MS to transformed MS', xml_filename)
                LOG.trace('Copying %s: %s to %s', xml_filename, vis_source, outputvis_dest)
                shutil.copyfile(vis_source, outputvis_dest)

    @staticmethod
    def _update_history(vis: str, outputvis: str) -> None:
        """Hook to update output MS history."""
        pass

    def prepare(self) -> MstransformResults:
        """Execute CASA mstransform and copy auxiliary metadata files."""
        inputs = self.inputs

        # Create the results structure
        result = self._create_result(inputs)

        # Run CASA task
        mstransform_args = inputs.to_casa_args()
        mstransform_job = casa_tasks.mstransform(**mstransform_args)
        try:
            self._executor.execute(mstransform_job)
        except OSError as ee:
            LOG.warning('Caught mstransform exception: %s', ee)

        # Copy across auxiliary files.
        self._copy_auxiliary_files(inputs.vis, inputs.outputvis)

        # Update output MS history.
        self._update_history(inputs.vis, inputs.outputvis)

        return result

    def _import_new_ms(self, result: MstransformResults) -> MstransformResults:
        """Import the transformed measurement set into an observing run domain object."""
        to_import = os.path.relpath(result.outputvis)
        observing_run = tablereader.ObservingRunReader.get_observing_run(to_import)

        for ms in observing_run.measurement_sets:
            LOG.debug('Setting session to %s for %s', self.inputs.ms.session, ms.basename)
            ms.session = self.inputs.ms.session
            LOG.debug('Setting data_column and origin_ms.')
            ms.origin_ms = self.inputs.ms.origin_ms
            if result.output_data_type:
                ms.set_data_column(result.output_data_type, 'DATA')

        result.mses.extend(observing_run.measurement_sets)
        return result

    def analyse(self, result: MstransformResults) -> MstransformResults:
        """Verify output MeasurementSet existence and import into observing run."""
        if not os.path.exists(result.outputvis):
            LOG.debug('Error creating output MS %s', os.path.basename(result.outputvis))
            return result

        result = self._import_new_ms(result)
        return result


class MstransformResults(basetask.Results):
    """Results object for Mstransform tasks."""

    def __init__(
        self,
        vis: str | None = None,
        outputvis: str | None = None,
        output_data_type: DataType | None = None,
    ) -> None:
        """Initialize MstransformResults.

        Args:
            vis: Input MeasurementSet path.
            outputvis: Transformed MeasurementSet path.
            output_data_type: Data type associated with the output MS.
        """
        super().__init__()
        self.vis = vis
        self.outputvis = outputvis
        self.output_data_type = output_data_type
        self.mses: list[MeasurementSet] = []

    def _post_merge_with_context(self, context: Context) -> None:
        """Hook for post-merge actions (e.g. callibrary registration, flag file creation)."""
        pass

    def merge_with_context(self, context: Context) -> None:
        """Merge output MeasurementSets into the pipeline context observing run."""
        if not self.mses:
            LOG.info('No %s results to merge', self.__class__.__name__)
            return

        target = context.observing_run
        for ms in self.mses:
            LOG.info('Adding %s to context', ms.name)
            target.add_measurement_set(ms)

        self._post_merge_with_context(context)

    def __str__(self) -> str:
        """Return human-readable string representation of the results."""
        s = f'{self.__class__.__name__}:\n'
        if self.vis and self.outputvis:
            s += '\tOriginal MS {vis} transformed to {outputvis}\n'.format(
                vis=os.path.basename(self.vis),
                outputvis=os.path.basename(self.outputvis),
            )
        return s

    def __repr__(self) -> str:
        """Return programmatic string representation of the results."""
        if self.vis and self.outputvis:
            return f'{self.__class__.__name__}({os.path.basename(self.vis)}, {os.path.basename(self.outputvis)})'
        return f'{self.__class__.__name__}(N/A, N/A)'


@task_registry.set_equivalent_casa_task('h_mstransform')
class Mstransform(sessionutils.ParallelTemplate):
    """Base Mstransform task with support for parallel execution."""

    Inputs = MstransformInputs
    Task = SerialMstransform
    Results = MstransformResults

    def _get_vis_list(self) -> list[str]:
        """Return the list of measurement set paths to process."""
        inputs = self.inputs
        if isinstance(inputs.vis, list):
            return inputs.vis
        elif isinstance(inputs.vis, str) and inputs.vis:
            return [inputs.vis]
        else:
            return [ms.name for ms in inputs.context.observing_run.measurement_sets]

    def _expand_task_args(self, valid_args_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Hook to expand task arguments, e.g. for per-spw or per-field splitting."""
        if self.inputs.per_spw and self.inputs.per_field:
            valid_args_list_per_field_spw = []
            observing_run = self.inputs.context.observing_run
            do_regrid = sum(1 for args in valid_args_list if args.get('outframe') in ['LSRK', 'REST']) > 0
            if do_regrid:
                vis_list = utils.deduplicate([args.get('vis') for args in valid_args_list])
                frequency_config = configure_frequency(
                    observing_run,
                    [observing_run.get_ms(vis) for vis in vis_list],
                    utils.contains_single_dish(self.inputs.context)
                )
            else:
                frequency_config = None

            for args in valid_args_list:
                spw_value = args.get('spw')
                field_value = args.get('field')
                if spw_value is None or field_value is None:
                    valid_args_list_per_field_spw.append(args)
                    continue

                spw_list = [s.strip() for s in str(spw_value).split(',') if s.strip()]
                field_list = [s.strip() for s in str(field_value).split(',') if s.strip()]

                for spw, field in itertools.product(spw_list, field_list):
                    args_field_spw = args.copy()
                    ms = observing_run.get_ms(args_field_spw['vis'])
                    vspw_id = observing_run.real2virtual_spw_id(int(spw), ms)
                    fields = ms.get_fields(field)
                    assert len(fields) == 1, f"Expected exactly one field for {field}, found {len(fields)}"
                    source_name = fields[0].source.name
                    args_field_spw['field'] = str(fields[0].id)
                    args_field_spw['spw'] = spw
                    base, ext = os.path.splitext(args_field_spw['outputvis'])
                    args_field_spw['outputvis'] = f'{base}.{utils.fieldname_clean(fields[0].name)}.spw{spw}{ext}'
                    if args.get('outframe') in ['LSRK', 'REST']:
                        freq_config = frequency_config.get((source_name, vspw_id))
                        args_field_spw['mode'] = "frequency"
                        args_field_spw['start'] = "{value}{unit}".format(**freq_config["start"])
                        args_field_spw['width'] = "{value}{unit}".format(**freq_config["width"])
                        args_field_spw['nchan'] = freq_config['nchan']
                    valid_args_list_per_field_spw.append(args_field_spw)
            if len(valid_args_list_per_field_spw) > 0:
                return valid_args_list_per_field_spw
        elif self.inputs.per_spw:
            valid_args_list_per_spw = []
            for args in valid_args_list:
                spw_value = args.get('spw')
                if spw_value is None:
                    valid_args_list_per_spw.append(args)
                    continue

                spw_list = [s.strip() for s in str(spw_value).split(',') if s.strip()]
                for spw in spw_list:
                    args_spw = args.copy()
                    args_spw['spw'] = spw
                    base, ext = os.path.splitext(args_spw['outputvis'])
                    args_spw['outputvis'] = f'{base}.spw{spw}{ext}'
                    valid_args_list_per_spw.append(args_spw)

            return valid_args_list_per_spw
        elif self.inputs.per_field:
            valid_args_list_per_field = []
            for args in valid_args_list:
                field_value = args.get('field')
                if field_value is None:
                    valid_args_list_per_field.append(args)
                    continue

                ms = self.inputs.context.observing_run.get_ms(args['vis'])
                field_list = [s.strip() for s in str(field_value).split(',') if s.strip()]
                for field in field_list:
                    args_field = args.copy()
                    args_field['field'] = field
                    base, ext = os.path.splitext(args_field['outputvis'])
                    fields = ms.get_fields(field)
                    assert len(fields) == 1, f"Expected exactly one field for {field}, found {len(fields)}"
                    args_field['outputvis'] = f'{base}.{utils.fieldname_clean(fields[0].name)}{ext}'
                    valid_args_list_per_field.append(args_field)

            return valid_args_list_per_field

        return valid_args_list

    def _get_task_args_list(self) -> list[dict[str, Any]]:
        """Build the list of task argument dictionaries for all jobs."""
        valid_args_list = []
        inputs = self.inputs
        original_vis = inputs.vis
        try:
            vis_list = self._get_vis_list()
            for vis in vis_list:
                inputs.vis = vis
                task_args = inputs.as_dict()
                valid_args_list.append(task_args)
        finally:
            inputs.vis = original_vis

        valid_args_list = self._expand_task_args(valid_args_list)

        if inputs.per_spw:
            LOG.info(
                '%s will be executed per SPW; the number of tasks to be executed is %d',
                self.__class__.__name__,
                len(valid_args_list),
            )
        else:
            LOG.info(
                '%s will be executed; the number of tasks to be executed is %d',
                self.__class__.__name__,
                len(valid_args_list),
            )

        return valid_args_list

    def prepare(self) -> list[tuple[str, dict[str, Any], Any]]:
        """Distribute mstransform jobs across serial or parallel workers."""
        assessed = []
        parallel = mpihelpers.parse_parallel_input_parameter(self.inputs.parallel)
        task_args_list = self._get_task_args_list()

        if not task_args_list:
            empty_results = self.Results(vis=None, outputvis=None, output_data_type=None)
            empty_results.task = self.__class__
            empty_results.inputs = self.inputs.as_dict()
            empty_results.stage_number = self.inputs.context.task_counter
            return [('', {}, empty_results)]

        taskqueue_parallel_request = len(task_args_list) > 1 and parallel

        with TaskQueue(parallel=taskqueue_parallel_request, executor=self._executor) as tq:
            for task_args in task_args_list:
                tq.add_pipelinetask(self.Task, task_args, self.inputs.context)
            task_results_list = tq.get_results()

        for task_args, worker_result in zip(task_args_list, task_results_list):
            vis = task_args['vis']
            try:
                if isinstance(worker_result, collections.abc.Iterable):
                    result = worker_result[0]
                else:
                    result = worker_result
            except exceptions.PipelineException as e:
                assessed.append((vis, task_args, e))
            else:
                assessed.append((vis, task_args, result))

        return assessed
