import pipeline.h.tasks.applycal.applycal as applycal
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.vdp as vdp
from pipeline.infrastructure import task_registry

__all__ = ['IFApplycal',
           'SerialIFApplycal',
           'IFApplycalInputs']

LOG = infrastructure.get_logger(__name__)


class IFApplycalInputs(applycal.ApplycalInputs):
    flagdetailedsum = vdp.VisDependentProperty(default=True)

    # Override h_applycal default, adding polarisation (PIPE-600) and diffgain
    # (PIPE-2088) to calibrator intents.
    intent = vdp.VisDependentProperty(default='TARGET,PHASE,BANDPASS,AMPLITUDE,CHECK,DIFFGAINREF,DIFFGAINSRC,'
                                              'POLARIZATION,POLANGLE,POLLEAKAGE')

    # docstring and type hints: supplements hif_applycal
    def __init__(self, context, output_dir=None, vis=None, field=None, spw=None, antenna=None, intent=None, parang=None,
                 applymode=None, flagbackup=None, flagsum=None, flagdetailedsum=None,
                 parallel=None):
        """Initialize Inputs.

        Args:
            context: Pipeline context object containing state information.

            output_dir: Output directory.
                Defaults to None, which corresponds to the current working directory.

            vis: The list of input MeasurementSets. Defaults to the list of MeasurementSets in the pipeline context.

                Example: ``['X227.ms']``

            field: A string containing the list of field names or field ids to which the calibration will be applied. Defaults to all fields in the pipeline
                context.

                Examples: ``'3C279'``, ``'3C279, M82'``

            spw: The list of spectral windows and channels to which the calibration will be applied. Defaults to all science windows in the pipeline
                context.

                Examples: ``'17'``, ``'11, 15'``

            antenna: The selection of antennas to which the calibration will be applied. Defaults to all antennas. Not currently supported.

            intent: A string containing the list of intents against which the selected fields will be matched. Defaults to all supported intents
                in the pipeline context.

                Example: ``'*TARGET*'``

            parang: Apply parallactic angle correction

            applymode: Calibration apply mode. Options:

                - ``'calflag'``: calibrate data and apply flags from solutions
                - ``'calflagstrict'``: (default) same as above except flag spws for which calibration is
                  unavailable in one or more tables (instead of allowing them to pass
                  uncalibrated and unflagged)
                - ``'trial'``: report on flags from solutions, dataset entirely unchanged
                - ``'flagonly'``: apply flags from solutions only, data not calibrated
                - ``'flagonlystrict'``: same as above except flag spws for which calibration is
                  unavailable in one or more tables
                - ``'calonly'``: calibrate data only, flags from solutions **not** applied

            calwt: Calibrate the weights as well as the data

            flagbackup: Backup the flags before the apply

            flagsum: Compute before and after flagging summary statistics

            flagdetailedsum: Compute detailed before and after flagging statistics summaries. Parameter available only when if flagsum is True.

            parallel: Process multiple MeasurementSets in parallel using the casampi parallelization framework.

                Options: ``'automatic'``, ``'true'``, ``'false'``, ``True``, ``False``

                Default: ``None`` (equivalent to ``False``)
        """
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
