import os
import shutil

import pipeline.h.tasks.applycal.applycal as applycal
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.callibrary as callibrary
import pipeline.infrastructure.tablereader as tablereader
import pipeline.infrastructure.vdp as vdp
from pipeline.infrastructure import casa_tasks
from pipeline.domain import DataType
from pipeline.infrastructure import task_registry


LOG = infrastructure.get_logger(__name__)


class UVcontSubInputs(applycal.ApplycalInputs):
    # Search order of input vis
    processing_data_type = [DataType.REGCAL_CONTLINE_SCIENCE, DataType.REGCAL_CONTLINE_ALL, DataType.RAW]

    applymode = vdp.VisDependentProperty(default='calflag')
    flagsum = vdp.VisDependentProperty(default=False)
    intent = vdp.VisDependentProperty(default='TARGET')

    def __init__(self, context, output_dir=None, vis=None, field=None, spw=None, antenna=None, intent=None, parang=None,
                 applymode=None, flagbackup=None, flagsum=None, flagdetailedsum=None):
        super(UVcontSubInputs, self).__init__(context, output_dir=output_dir, vis=vis, field=field, spw=spw,
                                              antenna=antenna, intent=intent, parang=parang, applymode=applymode,
                                              flagbackup=flagbackup, flagsum=flagsum, flagdetailedsum=flagdetailedsum)


@task_registry.set_equivalent_casa_task('hif_uvcontsub')
class UVcontSub(applycal.Applycal):
    Inputs = UVcontSubInputs

    # Override prepare method with one which sets and unsets the VI1CAL
    # environment variable.
    def prepare(self):
        inputs = self.inputs

        # Check for size mitigation errors.
        if 'status' in inputs.context.size_mitigation_parameters:
            if inputs.context.size_mitigation_parameters['status'] == 'ERROR':
                result = UVcontSubResults()
                result.mitigation_error = True
                return result

        applycal_result = super(UVcontSub, self).prepare()
        result = UVcontSubResults()
        result.applycal_result = applycal_result

        # Create line MS using subtracted data from the corrected column
        outputvis = inputs.vis.replace('_cont', '_line')
        # Check if it already exists and remove it
        if os.path.exists(outputvis):
            LOG.info('Removing {} from disk'.format(outputvis))
            shutil.rmtree(outputvis)
        # Run mstransform to create new line MS.
        mstransform_args = {'vis': inputs.vis, 'outputvis': outputvis, 'datacolumn': 'corrected'}
        mstransform_job = casa_tasks.mstransform(**mstransform_args)
        try:
            self._executor.execute(mstransform_job)
        except OSError as ee:
            LOG.warning(f"Caught mstransform exception: {ee}")

        # Copy across requisite XML files.
        self._copy_xml_files(inputs.vis, outputvis)

        result.vis = inputs.vis
        result.outputvis = outputvis

        return result

    def analyse(self, result):

        # Check for existence of the output vis. 
        if not os.path.exists(result.outputvis):
            LOG.debug('Error creating target line MS %s' % (os.path.basename(result.outputvis)))
            return result

        # Import the new measurement set.
        to_import = os.path.relpath(result.outputvis)
        observing_run = tablereader.ObservingRunReader.get_observing_run(to_import)

        # Adopt same session as source measurement set
        for ms in observing_run.measurement_sets:
            LOG.debug('Setting session to %s for %s', self.inputs.ms.session, ms.basename)
            ms.session = self.inputs.ms.session
            ms.set_data_column(DataType.REGCAL_LINE_SCIENCE, 'DATA')
        result.line_mses.extend(observing_run.measurement_sets)

        return result

    @staticmethod
    def _copy_xml_files(vis, outputvis):
        for xml_filename in ['SpectralWindow.xml', 'DataDescription.xml']:
            vis_source = os.path.join(vis, xml_filename)
            outputvis_target_line = os.path.join(outputvis, xml_filename)
            if os.path.exists(vis_source) and os.path.exists(outputvis):
                LOG.info('Copying %s from original MS to target line MS', xml_filename)
                LOG.trace('Copying %s: %s to %s', xml_filename, vis_source, outputvis_target_line)
                shutil.copyfile(vis_source, outputvis_target_line)


class UVcontSubResults(basetask.Results):
    """
    UVcontSubResults is the results class for the pipeline UVcontSub task.
    """

    def __init__(self, applied=[]):
        super(UVcontSubResults, self).__init__()
        self.mitigation_error = False
        self.applycal_result = None
        self.vis = None
        self.outputvis = None
        self.line_mses = []

    def merge_with_context(self, context):
        # Check for an output vis
        if not self.line_mses:
            LOG.error('No hif_mstransform results to merge')
            return

        target = context.observing_run

        # Register applied calibrations
        for calapp in self.applycal_result.applied:
            LOG.trace('Marking %s as applied' % calapp.as_applycal())
            context.callibrary.mark_as_applied(calapp.calto, calapp.calfrom)

        # Adding line mses to context
        for ms in self.line_mses:
            # Check if MS with the same name had already been registered and remove it
            try:
                index = [existing_ms.basename for existing_ms in target.measurement_sets].index(ms.basename)
                LOG.info('Removing {} from context'.format(ms.name))
                target.measurement_sets.pop(index)
            except:
                # Exception happens if name is not found. No special handling needed.
                pass
            LOG.info('Adding {} to context'.format(ms.name))
            target.add_measurement_set(ms)

        # Create targets flagging template file if it does not already exist
        for ms in self.line_mses:
            template_flagsfile = os.path.join(
                self.inputs['output_dir'], os.path.splitext(os.path.basename(self.vis))[0] + '.flagtargetstemplate.txt')
            self._make_template_flagfile(template_flagsfile, 'User flagging commands file for the imaging pipeline')

        # Initialize callibrary
        for ms in self.line_mses:
            # TODO: Check for existing entries for the line MS and remove them.
            #       This is probably only the case for future selfcal use cases.
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

FLAGGING_TEMPLATE_HEADER = '''#
# ___TITLESTR___
#
# Examples
# Note: Do not put spaces inside the reason string !
#
# mode='manual' correlation='YY' antenna='DV01;DV08;DA43;DA48&DV23' spw='21:1920~2880' autocorr=False reason='bad_channels'
# mode='manual' spw='25:0~3;122~127' reason='stage8_2'
# mode='manual' antenna='DV07' timerange='2013/01/31/08:09:55.248~2013/01/31/08:10:01.296' reason='quack'
#
'''

# May need this full class in the future when keeping records of
# which source/spw combination actually did have valid uvcontsub
# results (cf. "applied" parameter below). Note that the template
# below is quite old and probably needs work to be used.
#
#
#class UVcontSubResults(basetask.Results):
#    """
#    UVcontSubResults is the results class for the pipeline UVcontSub task.
#    """
#
#    def __init__(self, applied=[]):
#        """
#        Construct and return a new UVContSubResults.
#
#        The resulting object should be initialized with a list of
#        CalibrationTables corresponding to the caltables applied by this task.
#
#        :param applied: caltables applied by this task
#        :type applied: list of :class:`~pipeline.domain.caltable.CalibrationTable`
#        """
#        super(UVcontSubResults, self).__init__()
#        self.applied = set()
#        self.applied.update(applied)
#
#    def merge_with_context(self, context):
#        """
#        Merges these results with the given context by examining the context
#        and marking any applied caltables, so removing them from subsequent
#        on-the-fly calibration calculations.
#
#        See :method:`~pipeline.Results.merge_with_context`
#        """
#        if not self.applied:
#            LOG.error('No results to merge')
#
#        for calapp in self.applied:
#            LOG.trace('Marking %s as applied' % calapp.as_applycal())
#            context.callibrary.mark_as_applied(calapp.calto, calapp.calfrom)
#
#    def __repr__(self):
#        for caltable in self.applied:
#            s = 'UVcontSubResults:\n'
#            if isinstance(caltable.gaintable, list):
#                basenames = [os.path.basename(x) for x in caltable.gaintable]
#                s += '\t{name} applied to {vis} spw #{spw}\n'.format(
#                    spw=caltable.spw, vis=os.path.basename(caltable.vis),
#                    name=','.join(basenames))
#            else:
#                s += '\t{name} applied to {vis} spw #{spw}\n'.format(
#                    name=caltable.gaintable, spw=caltable.spw,
#                    vis=os.path.basename(caltable.vis))
#        return s
