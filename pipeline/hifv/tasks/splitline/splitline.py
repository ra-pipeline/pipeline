import os

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.vdp as vdp
from pipeline.infrastructure import casa_tasks, task_registry
import pipeline.infrastructure.callibrary as callibrary
import pipeline.infrastructure.tablereader as tablereader
from pipeline.domain import DataType

LOG = infrastructure.get_logger(__name__)


class SplitlineResults(basetask.Results):
    def __init__(self, vis, line_ms):
        super(SplitlineResults, self).__init__()
        self.pipeline_casa_task = 'Splitline'
        self.vis = vis
        self.line_ms = line_ms
        self.mses = []

    def merge_with_context(self, context):
        """
        See :method:`~pipeline.infrastructure.api.Results.merge_with_context`
        """

        target = context.observing_run

        # Adding mses to context
        for ms in self.mses:
            LOG.info('Adding {} to context'.format(ms.name))
            target.add_measurement_set(ms)

        calto = callibrary.CalTo(vis=self.line_ms)
        LOG.info('Registering {} with callibrary'.format(self.line_ms))
        context.callibrary.add(calto, [])

        return

    def __repr__(self):
        return 'SplitlineResults:\n\t{0}'.format(
            '\n\t'.join([ms.name for ms in self.mses]))


class SplitlineInputs(vdp.StandardInputs):

    spw = vdp.VisDependentProperty(default='spw')

    def __init__(self, context, vis=None, spw=None):
        """
            spw assumes format of spw='0:256~768,1:256~768'
        """
        self.context = context
        self.vis = vis
        self.spw = spw


@task_registry.set_equivalent_casa_task('hifv_splitline')
@task_registry.set_casa_commands_comment('VLA spectral line pipeline mstransform task')
class Splitline(basetask.StandardTaskTemplate):
    Inputs = SplitlineInputs

    def prepare(self):

        LOG.info("This Splitline class is running.")

        flagjob1 = casa_tasks.flagmanager(mode='restore', vis=self.inputs.vis, versionname='before_rflag_statwt')
        self._executor.execute(flagjob1)

        line_ms = os.path.splitext(self.inputs.vis)[0] + '_line.ms'
        mstransform_job = casa_tasks.mstransform(vis=self.inputs.vis, outputvis=line_ms, spw=self.inputs.spw)
        self._executor.execute(mstransform_job)

        flagjob2 = casa_tasks.flagmanager(mode='save', vis=line_ms, versionname='before_rflag_statwt')
        self._executor.execute(flagjob2)

        flagjob3 = casa_tasks.flagmanager(mode='restore', vis=self.inputs.vis, versionname='rfi_flagged_statwt')
        self._executor.execute(flagjob3)

        return SplitlineResults(vis=self.inputs.vis, line_ms=line_ms)

    def analyse(self, result):

        # Check for existence of the output line vis.
        if not os.path.exists(result.line_ms):
            LOG.debug('Error creating line MS %s' % (os.path.basename(result.linems)))
            return result

        # Import the new measurement set.
        to_import = os.path.abspath(result.line_ms)
        observing_run = tablereader.ObservingRunReader.get_observing_run(to_import)

        # Adopt same session as source measurement set
        for ms in observing_run.measurement_sets:
            LOG.debug('Setting session to %s for %s', self.inputs.ms.session, ms.basename)
            ms.session = self.inputs.ms.session
            LOG.debug('Setting data_column and origin_ms.')
            ms.origin_ms = self.inputs.ms.origin_ms
            ms.set_data_column(DataType.REGCAL_LINE_SCIENCE, 'DATA')

        result.mses.extend(observing_run.measurement_sets)

        return result

    def _do_somethingsplitline(self):

        task = casa_tasks.splitlinecal(vis=self.inputs.vis, caltable='tempcal.splitline')

        return self._executor.execute(task)
