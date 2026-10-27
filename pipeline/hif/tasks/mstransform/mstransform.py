import collections.abc
import operator
import os
import shutil

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.callibrary as callibrary
import pipeline.infrastructure.sessionutils as sessionutils
import pipeline.infrastructure.tablereader as tablereader
import pipeline.infrastructure.vdp as vdp
from pipeline.domain import DataType
from pipeline.hif.heuristics.auto_selfcal.selfcal_helpers import get_calinfo_from_ms
from pipeline.infrastructure import casa_tasks, exceptions, mpihelpers, task_registry
from pipeline.infrastructure.mpihelpers import TaskQueue

LOG = infrastructure.get_logger(__name__)


# Define the minimum set of parameters required to split out
# the TARGET data from the complete and fully calibrated
# original MS or the best calibrated data from a _targets MS.
# Other parameters will be added here as more
# capabilities are added to hif_mstransform.
class MstransformInputs(vdp.StandardInputs):
    # This task is special in the sense that it may need to process multiple
    # data types at once. Changing the framework is not a good option since it
    # could only return *all* MSes which would include duplication of names for
    # different datatypes. So we set the default data types to [].
    processing_data_types = [
        DataType.IM_LINE_SCIENCE,
        DataType.IM_CONTLINE_SCIENCE,
        DataType.SELFCAL_LINE_SCIENCE,
        DataType.SELFCAL_CONTLINE_SCIENCE,
        DataType.REGCAL_LINE_SCIENCE,
        DataType.REGCAL_CONTLINE_SCIENCE,
        DataType.REGCAL_CONTLINE_ALL,
        DataType.RAW
        ]
    in_to_out_data_types = {
        DataType.REGCAL_CONTLINE_ALL: DataType.REGCAL_CONTLINE_SCIENCE,
        DataType.REGCAL_CONTLINE_SCIENCE: DataType.IM_CONTLINE_SCIENCE,
        DataType.REGCAL_LINE_SCIENCE: DataType.IM_LINE_SCIENCE,
        DataType.SELFCAL_CONTLINE_SCIENCE: DataType.IM_CONTLINE_SCIENCE,
        DataType.SELFCAL_LINE_SCIENCE: DataType.IM_LINE_SCIENCE,
        None: None
        }

    @vdp.VisDependentProperty
    def input_data_type(self):
        return None

    @vdp.VisDependentProperty
    def datacolumn(self):
        if self.input_data_type:
            pl_datacolumn = self.context.observing_run.get_ms(self.vis).data_column[self.input_data_type]
            # The CASA mstransform command wants 'data' or 'corrected' while PL
            # uses 'DATA' and 'CORRECTED_DATA' in the domain objects.
            mstransform_datacolumn = 'data' if pl_datacolumn == 'DATA' else 'corrected'
            return mstransform_datacolumn
        else:
            return None

    @vdp.VisDependentProperty
    def all_eph_obj(self):
        return None

    @vdp.VisDependentProperty
    def outputvis(self):
        vis_root = os.path.splitext(self.vis)[0]
        if self.input_data_type == DataType.REGCAL_CONTLINE_ALL:
            return vis_root + '_targets.ms'
        elif self.input_data_type in [DataType.SELFCAL_CONTLINE_SCIENCE, DataType.REGCAL_CONTLINE_SCIENCE]:
            return vis_root.replace('_targets', '_imaging') + '.ms'
        elif self.input_data_type in [DataType.SELFCAL_LINE_SCIENCE, DataType.REGCAL_LINE_SCIENCE]:
            return vis_root.replace('_targets_line', '_imaging_line') + '.ms'
        else:
            return None

    @vdp.VisDependentProperty
    def output_data_type(self):
        vis_root = os.path.splitext(self.vis)[0]
        return self.in_to_out_data_types[self.input_data_type]

    @vdp.VisDependentProperty
    def outframe(self):
        if self.input_data_type == DataType.REGCAL_CONTLINE_ALL:
            # For the first mode of hif_mstransform the specified data (usually TARGET intent)
            # is just split out without changing the frequency frame.
            return None
        else:
            # For the second mode that produces imaging MSes, the frequency frame
            # is changed to the target native one. There are ephemeris and other objects.
            if self.all_eph_obj:
                return 'SOURCE'
            else:
                return 'LSRK'

    @vdp.VisDependentProperty
    def regridms(self):
        if self.input_data_type == DataType.REGCAL_CONTLINE_ALL: # or ephemeris targets
            return None
        else:
            return True

    # By default find all the fields with TARGET intent
    @vdp.VisDependentProperty
    def field(self):

        # Find fields in the current ms that have been observed
        # with the desired intent
        fields = self.ms.get_fields(intent=self.intent)

        # When an observation is terminated the final scan can be a TARGET scan but may
        # not contain any TARGET data for the science spectral windows, e.g. there is square
        # law detector data but nothing else. The following code removes fields that do not contain
        # data for the requested spectral windows - the science spectral windows by default.

        if fields:
            fields_by_id = sorted(fields, key=operator.attrgetter('id'))
            last_field = fields_by_id[-1]

            # While we're here, remove any fields that are not linked with a source. This should
            # not occur since the CAS-9499 tablereader bug was fixed, but check anyway.
            if getattr(last_field, 'source', None) is None:
                fields.remove(last_field)
                LOG.info('Truncated observation detected (no source for field): '
                         'removing Field {!s}'.format(last_field.id))
            else:
                # .. and then any fields that do not contain the
                # requested spectral windows. This should prevent
                # aborted scans from being split into the TARGET
                # measurement set.
                requested_spws = set(self.ms.get_spectral_windows(self.spw))
                if last_field.valid_spws.isdisjoint(requested_spws):
                    LOG.info('Truncated observation detected (missing spws): '
                             'removing Field {!s}'.format(last_field.id))
                    fields.remove(last_field)

        unique_field_names = {f.name for f in fields}
        field_ids = {f.id for f in fields}

        # Fields with different intents may have the same name. Check for this
        # and return the ids rather than the names if necessary to resolve any
        # ambiguities
        if len(unique_field_names) == len(field_ids):
            return ','.join(unique_field_names)
        else:
            return ','.join([str(i) for i in field_ids])

    # Select TARGET data by default
    intent = vdp.VisDependentProperty(default='TARGET')

    # Find all the spws with TARGET intent. These may be a subset of the
    # science spws which include calibration spws.
    @vdp.VisDependentProperty
    def spw(self):
        science_target_intents = set(self.intent.split(','))
        science_target_spws = []

        science_spws = [spw for spw in self.ms.get_spectral_windows(science_windows_only=True)]
        for spw in science_spws:
            if spw.intents.intersection(science_target_intents):
                science_target_spws.append(spw)

        return ','.join([str(spw.id) for spw in science_target_spws])

    @spw.convert
    def spw(self, value):
        science_target_intents = set(self.intent.split(','))
        science_target_spws = []

        science_spws = [spw for spw in self.ms.get_spectral_windows(task_arg=value, science_windows_only=True)]
        for spw in science_spws:
            if spw.intents.intersection(science_target_intents):
                science_target_spws.append(spw)

        return ','.join([str(spw.id) for spw in science_target_spws])

    chanbin = vdp.VisDependentProperty(default=1)
    timebin = vdp.VisDependentProperty(default='0s')
    per_spw = vdp.VisDependentProperty(default=False)

    parallel = sessionutils.parallel_inputs_impl(default=False)

    # docstring and type hints: supplements hif_mstransform
    def __init__(self, context, output_dir=None, vis=None, input_data_type=None, datacolumn=None, all_eph_obj=None, outputvis=None, output_data_type=None,
                 outframe=None, regridms=None, field=None, intent=None, spw=None, chanbin=None, timebin=None, per_spw=None, parallel=None):
        """Initialize Inputs.

        Args:
            context: Pipeline context object containing state information.

            output_dir: Output directory.
                Defaults to None, which corresponds to the current working directory.

            vis: The list of input MeasurementSets. Defaults to the list of MeasurementSets defined in the data type fallback heuristics.
                First, any '*_targets' MSes are searched. If none is in available in the context, the original MSes of the importdata
                steps are used.
                '': use all MeasurementSets in the context

            input_data_type: The input data type to be used.

            datacolumn: The data column to use from the input MeasurementSets. Depending on the processing datatype this can be ``'data'`` or ``'corrected'``.

            all_eph_obj: Boolean to tell if all selected fields are ephemeris objects. Needed for heuristics of other parameters.

            outputvis: A list of output MeasurementSets for line detection and imaging,. This list must have
                the same length as the input list.

                Default Naming: By default, an input MS named `<msrootname>.ms`
                will produce an output named `<msrootname>_targets.ms`.
                An input MS named `<msrootname>_targets.ms` will produce an
                an output named `<msrootname>_imaging.ms`.

                Examples:
                    - ``outputvis='ngc5921_targets.ms'``
                    - ``outputvis=['ngc5921a_targets.ms', 'ngc5921b_targets.ms', 'ngc5921c_targets.ms']``
                    - ``outputvis='ngc5921_imaging.ms'``

            output_data_type: The new data type of the output MeasurementSets

            outframe: The frequency frame of the output MeasurementSets

            regridms: Flag for frame changes

            field: Select fields name(s) or id(s) to transform. Only fields with data matching the intent will be selected.

                Examples: ``'3C279'``, ``'Centaurus*'``, ``'3C279,J1427-421'``

            intent: Select intents for which associated fields will be imaged. By default only TARGET data is selected.

                Examples: ``'PHASE,BANDPASS'``

            spw: Select spectral window/channels to image. By default all science spws for which the specified intent is valid are
                selected.

            chanbin: Width (bin) of input channels to average to form an output channel. If chanbin > 1 then chanaverage is automatically
                switched to True.

            timebin: Bin width for time averaging. If timebin > 0s then timeaverage is automatically switched to True.

            per_spw: If True, execute mstransform separately for each spectral window in spw.

            parallel: Process multiple MeasurementSets in parallel using the casampi parallelization framework.

                Options: ``'automatic'``, ``'true'``, ``'false'``, ``True``, ``False``

                Default: ``None`` (equivalent to ``False``)

        """
        super().__init__()

        # set the properties to the values given as input arguments
        self.context = context
        self.vis = vis
        self.input_data_type = input_data_type
        self.datacolumn = datacolumn
        self.all_eph_obj = all_eph_obj
        self.output_dir = output_dir
        self.outputvis = outputvis
        self.output_data_type = output_data_type
        self.outframe = outframe
        self.regridms = regridms
        self.field = field
        self.intent = intent
        self.spw = spw
        self.chanbin = chanbin
        self.timebin = timebin
        self.per_spw = per_spw
        self.parallel = parallel

    def to_casa_args(self):

        # Get parameter dictionary.
        d = super().to_casa_args()

        # Force the new (with casa 4.6) reindex parameter to be False
        d['reindex'] = False

        if self.chanbin > 1:
            d['chanaverage'] = True
        else:
            d['chanaverage'] = False

        if self.timebin > '0s':
            d['timeaverage'] = True
        else:
            d['timeaverage'] = False

        # Remove a number of inputs parameters that
        # casatasks/mstransform does not support.
        for key in ('parallel', 'per_spw', 'input_data_type', 'output_data_type', 'all_eph_obj'):
            d.pop(key, None)

        return d


class SerialMstransform(basetask.StandardTaskTemplate):
    Inputs = MstransformInputs

    def prepare(self):
        inputs = self.inputs

        # Create the results structure
        result = MstransformResults(vis=inputs.vis, outputvis=inputs.outputvis, output_data_type=inputs.output_data_type)

        # Run CASA task
        mstransform_args = inputs.to_casa_args()
        mstransform_job = casa_tasks.mstransform(**mstransform_args)
        try:
            self._executor.execute(mstransform_job)
        except OSError as ee:
            LOG.warning(f"Caught mstransform exception: {ee}")

        # Copy across requisite XML files.
        self._copy_xml_files(inputs.vis, inputs.outputvis)

        # Update output MS history.
        self._update_history(inputs.vis, inputs.outputvis)

        return result

    def analyse(self, result):

        # Check for existence of the output vis.
        if not os.path.exists(result.outputvis):
            LOG.debug('Error creating output MS %s' % (os.path.basename(result.outputvis)))
            return result

        # Import the new measurement set.
        to_import = os.path.relpath(result.outputvis)
        observing_run = tablereader.ObservingRunReader.get_observing_run(to_import)

        # Adopt same session as source measurement set
        for ms in observing_run.measurement_sets:
            LOG.debug('Setting session to %s for %s', self.inputs.ms.session, ms.basename)
            ms.session = self.inputs.ms.session
            LOG.debug('Setting data_column and origin_ms.')
            ms.origin_ms = self.inputs.ms.origin_ms
            ms.set_data_column(result.output_data_type, 'DATA')

        result.mses.extend(observing_run.measurement_sets)

        return result

    @staticmethod
    def _copy_xml_files(vis, outputvis):
        for xml_filename in ['SpectralWindow.xml', 'DataDescription.xml']:
            vis_source = os.path.join(vis, xml_filename)
            outputvis_targets_contline = os.path.join(outputvis, xml_filename)
            if os.path.exists(vis_source) and os.path.exists(outputvis):
                LOG.info('Copying %s from original MS to transformed MS', xml_filename)
                LOG.trace('Copying %s: %s to %s', xml_filename, vis_source, outputvis_targets_contline)
                shutil.copyfile(vis_source, outputvis_targets_contline)

    @staticmethod
    def _update_history(vis, outputvis):
        get_calinfo_from_ms(vis, save_to_ms=outputvis)


class MstransformResults(basetask.Results):
    def __init__(self, vis, outputvis, output_data_type=None):
        super().__init__()
        self.vis = vis
        self.outputvis = outputvis
        self.output_data_type = output_data_type
        self.mses = []

    def merge_with_context(self, context):
        # Check for an output vis
        if not self.mses:
            LOG.info('No hif_mstransform results to merge')
            return

        target = context.observing_run

        # Adding mses to context
        for ms in self.mses:
            LOG.info('Adding {} to context'.format(ms.name))
            target.add_measurement_set(ms)

        # Create targets flagging template file if it does not already exist
        for ms in self.mses:
            template_flagsfile = os.path.join(
                self.inputs['output_dir'], os.path.splitext(os.path.basename(ms.name))[0] + '.flagtargetstemplate.txt')
            self._make_template_flagfile(template_flagsfile, 'User flagging commands file for the imaging pipeline')

        # Initialize callibrary
        for ms in self.mses:
            calto = callibrary.CalTo(vis=ms.name)
            LOG.info('Registering {} with callibrary'.format(ms.name))
            context.callibrary.add(calto, [])

    def _make_template_flagfile(self, outfile, titlestr):
        # Create a new file if overwrite is true and the file
        # does not already exist.
        if not os.path.exists(outfile):
            template_text = FLAGGING_TEMPLATE_HEADER.replace('___TITLESTR___', titlestr)
            with open(outfile, 'w') as f:
                f.writelines(template_text)

    def __str__(self):
        # Format the Mstransform results.
        s = 'MstransformResults:\n'
        if self.vis:
            s += '\tOriginal MS {vis} transformed to {outputvis}\n'.format(
                vis=os.path.basename(self.vis),
                outputvis=os.path.basename(self.outputvis))

        return s

    def __repr__(self):
        if self.vis:
            return 'MstranformResults({}, {})'.format(os.path.basename(self.vis), os.path.basename(self.outputvis))
        else:
            return 'MstranformResults(N/A, N/A)'


@task_registry.set_equivalent_casa_task('hif_mstransform')
class Mstransform(sessionutils.ParallelTemplate):
    Inputs = MstransformInputs
    Task = SerialMstransform

    def _get_eph_frames(self, vis_list):
        """
        Return a list of booleans telling if the field frame is SOURCE/REST or not.
        """

        inputs = self.inputs
        fields_are_eph_obj = []
        for vis in vis_list:
            fields_are_eph_obj.extend([f.source.is_eph_obj for f in inputs.context.observing_run.get_ms(vis).get_fields(intent=inputs.intent)])
        return fields_are_eph_obj

    def _frames_consistent(self, vis_list):
        """
        Check if all selected sources use the same frequency frame.
        """

        fields_are_eph_obj = self._get_eph_frames(vis_list)
        return all(fields_are_eph_obj) or not any(fields_are_eph_obj)

    def _conversion_possible(self, vis_list, data_type_list):
        """
        Check if the requested mstransform conversion can be done. For ephemeris objects
        we can not convert to SOURCE/REST frame due to a bug in CASA's mstransform command for
        PL 2026 (status as of 04/2026).
        """

        inputs = self.inputs
        fields_are_eph_obj = self._get_eph_frames(vis_list)
        return not(DataType.REGCAL_CONTLINE_ALL not in data_type_list and any(fields_are_eph_obj))

    def _get_task_args_list(self):

        valid_args_list = []
        inputs = self.inputs
        original_vis = inputs.vis
        original_input_data_type = inputs.input_data_type
        original_all_eph_obj = inputs.all_eph_obj

        # hif_mstransform needs to work on multiple datatypes at once.
        # Therefore the auto-selected vis list needs to be modified.
        data_types_groups = [
            [DataType.SELFCAL_LINE_SCIENCE, DataType.SELFCAL_CONTLINE_SCIENCE],
            [DataType.REGCAL_LINE_SCIENCE, DataType.REGCAL_CONTLINE_SCIENCE],
            [DataType.REGCAL_CONTLINE_ALL]
            ]
        vis_list = []
        data_type_list = []
        found_data_type_group = False
        for data_type_group in data_types_groups:
            for data_type in data_type_group:
                ms_objects = inputs.context.observing_run.get_measurement_sets_of_type(dtypes=[data_type], msonly=True)
                if ms_objects:
                    found_data_type_group = True
                    vis_list.extend([ms_object.name for ms_object in ms_objects])
                    data_type_list.extend(len(ms_objects)*[data_type])
            if found_data_type_group:
                break

        if not found_data_type_group:
            return []

        if not self._frames_consistent(vis_list):
            raise Exception('Cannot handle mixture of ephemeris and non-ephemeris objects.')

        if not self._conversion_possible(vis_list, data_type_list):
            return []

        try:
            for vis, data_type in zip(vis_list, data_type_list):
                inputs.vis = vis
                inputs.input_data_type = data_type
                inputs.all_eph_obj = all(self._get_eph_frames([vis]))
                task_args = inputs.as_dict()
                valid_args_list.append(task_args)
        finally:
            inputs.vis = original_vis
            inputs.input_data_type = original_input_data_type
            inputs.all_eph_obj = original_all_eph_obj

        if inputs.per_spw:
            valid_args_list_per_spw = []
            for args in valid_args_list:
                spw_value = args.get('spw')
                # If no SPW is specified, keep the original args unchanged for this entry.
                if spw_value is None:
                    valid_args_list_per_spw.append(args)
                    continue

                spw_list = [s.strip() for s in spw_value.split(',') if s.strip()]
                for spw in spw_list:
                    args_spw = args.copy()
                    args_spw['spw'] = spw
                    base, ext = os.path.splitext(args_spw['outputvis'])
                    args_spw['outputvis'] = f'{base}.spw{spw}{ext}'
                    valid_args_list_per_spw.append(args_spw)

            valid_args_list = valid_args_list_per_spw

        if inputs.per_spw:
            LOG.info(
                'Mstransform will be executed per SPW; the number of tasks to be executed is %d',
                len(valid_args_list),
            )
        else:
            LOG.info(
                'Mstransform will be executed; the number of tasks to be executed is %d',
                len(valid_args_list),
            )

        return valid_args_list

    def prepare(self):

        assessed = []
        parallel = mpihelpers.parse_parallel_input_parameter(self.inputs.parallel)
        task_args_list = self._get_task_args_list()

        if not task_args_list:
            emptyResults = MstransformResults(vis=None, outputvis=None, output_data_type=None)
            emptyResults.task = self.__class__
            emptyResults.inputs = self.inputs.as_dict()
            emptyResults.stage_number = self.inputs.context.task_counter
            return [('', {}, emptyResults)]

        taskqueue_parallel_request = len(task_args_list) > 1 and parallel

        with TaskQueue(parallel=taskqueue_parallel_request, executor=self._executor) as tq:

            for task_args in task_args_list:
                tq.add_pipelinetask(SerialMstransform, task_args, self.inputs.context)
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


FLAGGING_TEMPLATE_HEADER = """#
# ___TITLESTR___
#
# Examples
# Note: Do not put spaces inside the reason string !
#
# mode='manual' correlation='YY' antenna='DV01;DV08;DA43;DA48&DV23' spw='21:1920~2880' autocorr=False reason='bad_channels'
# mode='manual' spw='25:0~3;122~127' reason='stage8_2'
# mode='manual' antenna='DV07' timerange='2013/01/31/08:09:55.248~2013/01/31/08:10:01.296' reason='quack'
#
"""
