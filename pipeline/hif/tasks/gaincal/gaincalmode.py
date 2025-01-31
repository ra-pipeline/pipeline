import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.vdp as vdp
from pipeline.infrastructure import task_registry
from . import gsplinegaincal
from . import gtypegaincal
from . import ktypegaincal

LOG = infrastructure.get_logger(__name__)


class GaincalModeInputs(vdp.ModeInputs):
    _modes = {
        'gtype': gtypegaincal.GTypeGaincal,
        'gspline': gsplinegaincal.GSplineGaincal,
        'ktype': ktypegaincal.KTypeGaincal
    }

    # docstring and type hints: supplements hif_gaincal
    def __init__(self, context, mode='gtype', **parameters):
        """Initialize Inputs.

        Args:
            context: Pipeline context.

            mode: Gain calibration mode

            vis: The list of input MeasurementSets. Defaults to the list of MeasurementSets specified in the h_init or hif_importdata task.
                '': use all MeasurementSets in the context

                Examples: 'ngc5921.ms', ['ngc5921a.ms', ngc5921b.ms', 'ngc5921c.ms']

            caltable: The list of output calibration tables. Defaults to the standard pipeline naming convention.

                Example: caltable=['M82.gcal', 'M82B.gcal']

            field: The list of field names or field ids for which gain solutions are to be computed. Defaults to all fields with the standard
                intent.

                Example: field='3C279', field='3C279, M82'

            intent: A string containing a comma delimited list of intents against which the selected fields are matched. Defaults to `*PHASE*`.

                Examples: intent='', intent='`*AMP*,*PHASE*`'

            spw: The list of spectral windows and channels for which gain solutions are computed. Defaults to all science spectral
                windows.

                Examples: spw='21', spw='21, 23'

            antenna: Set of data selection antenna ids

            hm_gaintype: The type of gain calibration. The options are 'gtype' and 'gspline' for CASA gain types = 'G' and 'GSPLINE' respectively.

            calmode: Type of solution. The options are 'ap' (amp and phase), 'p' (phase only) and 'a' (amp only).

                Examples: calmode='p', calmode='a', calmode='ap'

            solint: Time solution intervals in CASA syntax. Works for hm_gaintype='gtype' only.

                Examples: solint='inf', solint='int', solint='100sec'

            combine: Data axes to combine for solving. Options are  '', 'scan', 'spw', 'field' or any comma-separated combination. Works for
                hm_gaintype='gtype' only.

            refant: Reference antenna name(s) in priority order. Defaults to most recent values set in the pipeline context. If no reference
                antenna is defined in the pipeline context use the CASA
                defaults.

                Examples: refant='DV01', refant='DV05,DV07'

            refantmode: Controls how the refant is applied. Currently available choices are 'flex', 'strict', and the default value of ''.
                Setting to '' allows the pipeline to select the appropriate
                mode based on the state of the reference antenna list.

                Examples: refantmode='strict', refantmode=''

            solnorm: Normalize average solution amplitudes to 1.0

            minblperant: Minimum number of baselines required per antenna for each solve. Antennas with fewer baselines are excluded from
                solutions. Works for hm_gaintype='gtype' only.

            minsnr: Solutions below this SNR are rejected. Works for hm_gaintype='channel' only.

            smodel: Point source Stokes parameters for source model (experimental). Defaults to using standard MODEL_DATA column data.

                Example: smodel=[1,0,0,0]  - (I=1, unpolarized)

            splinetime: Spline timescale (sec). Used for hm_gaintype='gspline'. Typical splinetime should cover about 3 to 5 calibrator scans.

            npointaver: Tune phase-unwrapping algorithm. Used for hm_gaintype='gspline'. Keep at default value.

            phasewrap: Wrap the phase for changes larger than this amount (degrees). Used for hm_gaintype='gspline'. Keep at default value.

        """
        super(GaincalModeInputs, self).__init__(context, mode, **parameters)


@task_registry.set_equivalent_casa_task('hif_gaincal')
class GaincalMode(basetask.ModeTask):
    Inputs = GaincalModeInputs
