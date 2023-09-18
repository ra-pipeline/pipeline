import pipeline.h.tasks.applycal.applycal as applycal
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.sessionutils as sessionutils
import pipeline.infrastructure.vdp as vdp
from pipeline.infrastructure import task_registry

__all__ = ['IFApplycal',
           'SerialIFApplycal',
           'IFApplycalInputs']

LOG = infrastructure.get_logger(__name__)


class IFApplycalInputs(applycal.ApplycalInputs):
    # parallel = sessionutils.parallel_inputs_impl()
    @property
    def parallel(self):
        return self._parallel

    @parallel.setter
    def parallel(self, value):
        if value is None:
            value = False
        else:
            allowed = ('true', 'false', 'automatic', True, False)
            if value not in allowed:
                m = ', '.join(('{!r}'.format(i) for i in allowed))
                raise ValueError('Value not in allowed value set ({!s}): {!r}'.format(m, value))
        self._parallel = value

    flagdetailedsum = vdp.VisDependentProperty(default=True)

    # PIPE-600: Overrides h_applycal default, adding polarisation to
    # calibrated intents
    intent = vdp.VisDependentProperty(default='TARGET,PHASE,BANDPASS,AMPLITUDE,CHECK,POLARIZATION,POLANGLE,POLLEAKAGE')

    def __init__(self, context, output_dir=None, vis=None, field=None, spw=None, antenna=None, intent=None, parang=None,
                 applymode=None, flagbackup=None, flagsum=None, flagdetailedsum=None,
                 parallel=None):
        super().__init__(context, output_dir=output_dir, vis=vis, field=field, spw=spw,
                         antenna=antenna, intent=intent, parang=parang, applymode=applymode,
                         flagbackup=flagbackup, flagsum=flagsum, flagdetailedsum=flagdetailedsum,
                         parallel=parallel)


class SerialIFApplycal(applycal.SerialApplycal):
    Inputs = IFApplycalInputs

    def __init__(self, inputs):
        super().__init__(inputs)


@task_registry.set_equivalent_casa_task('hif_applycal')
@task_registry.set_casa_commands_comment('Calibrations are applied to the data. Final flagging summaries are computed')
class IFApplycal(applycal.Applycal):
    Inputs = IFApplycalInputs
    Task = SerialIFApplycal
