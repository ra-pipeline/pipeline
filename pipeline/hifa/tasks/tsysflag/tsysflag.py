import pipeline.h.tasks.tsysflag.tsysflag as tsysflag
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.vdp as vdp
from pipeline.infrastructure import task_registry
import pipeline.infrastructure.sessionutils as sessionutils

__all__ = [
    'Tsysflag',
    'TsysflagInputs'
]

LOG = infrastructure.get_logger(__name__)


class TsysflagInputs(tsysflag.TsysflagInputs):
    """
    TsysflagInputs defines the inputs for the Tsysflag pipeline task.
    """

    fd_max_limit = vdp.VisDependentProperty(default=13)
    parallel = sessionutils.parallel_inputs_impl(default=False)

    # docstring and type hints: supplements hifa_tsysflag
    def __init__(self, context, output_dir=None, vis=None, caltable=None,
                 flag_nmedian=None, fnm_limit=None, fnm_byfield=None,
                 flag_derivative=None, fd_max_limit=None,
                 flag_edgechans=None, fe_edge_limit=None,
                 flag_fieldshape=None, ff_refintent=None, ff_max_limit=None,
                 flag_birdies=None, fb_sharps_limit=None,
                 flag_toomany=None, tmf1_limit=None, tmef1_limit=None,
                 metric_order=None, normalize_tsys=None, filetemplate=None,
                 parallel=None):
        """Initialize Inputs.

        Args:
            context: Pipeline context object containing state information.

            output_dir: Output directory.
                Defaults to None, which corresponds to the current working directory.

            vis: List of input MeasurementSets (Not used).

            caltable: List of input Tsys calibration tables.
                Default: [] - Use the table currently stored in the pipeline context.

                Example: caltable=['X132.ms.tsys.s2.tbl']

            flag_nmedian: True to flag Tsys spectra with high median value.

            fnm_limit: Flag spectra with median value higher than fnm_limit * median
                of this measure over all spectra.

            fnm_byfield: Evaluate the nmedian metric separately for each field.

            flag_derivative: True to flag Tsys spectra with high median derivative.

            fd_max_limit: Flag spectra with median derivative higher than
                fd_max_limit * median of this measure over all spectra.

            flag_edgechans: True to flag edges of Tsys spectra.

            fe_edge_limit: Flag channels whose channel to channel difference >
                fe_edge_limit * median across spectrum.

            flag_fieldshape: True to flag Tsys spectra with a radically different
                shape to those of the ff_refintent.

            ff_refintent: Data intent that provides the reference shape for
                'flag_fieldshape'.

            ff_max_limit: Flag Tsys spectra with 'fieldshape' metric values >
                ff_max_limit.

            flag_birdies: True to flag channels covering sharp spectral features.

            fb_sharps_limit: Flag channels bracketing a channel to channel
                difference > fb_sharps_limit.

            flag_toomany: True to flag Tsys spectra for which a proportion of
                antennas for given timestamp and/or proportion of antennas that are
                entirely flagged in all timestamps exceeds their respective thresholds.

            tmf1_limit: Flag Tsys spectra for all antennas in a timestamp and spw if
                proportion of antennas already flagged in this timestamp and spw exceeds
                tmf1_limit.

            tmef1_limit: Flag Tsys spectra for all antennas and all timestamps
                in a spw, if proportion of antennas that are already entirely flagged
                in all timestamps exceeds tmef1_limit.

            metric_order: Order in which to evaluate the flagging metrics that are
                enabled. Disabled metrics are skipped.

            normalize_tsys: True to create a normalized Tsys table that is used to
                evaluate the Tsys flagging metrics. All newly found flags are also applied
                to the original Tsys caltable that continues to be used for subsequent
                calibration.

            filetemplate: The name of a text file that contains the manual Tsys flagging
                template. If the template flags file is undefined, a name of the form
                'msname.flagtsystemplate.txt' is assumed.

        """
        super().__init__(
            context=context, output_dir=output_dir, vis=vis, caltable=caltable,
            flag_nmedian=flag_nmedian, fnm_limit=fnm_limit, fnm_byfield=fnm_byfield,
            flag_derivative=flag_derivative, fd_max_limit=fd_max_limit,
            flag_edgechans=flag_edgechans, fe_edge_limit=fe_edge_limit,
            flag_fieldshape=flag_fieldshape, ff_refintent=ff_refintent, ff_max_limit=ff_max_limit,
            flag_birdies=flag_birdies, fb_sharps_limit=fb_sharps_limit,
            flag_toomany=flag_toomany, tmf1_limit=tmf1_limit, tmef1_limit=tmef1_limit,
            metric_order=metric_order, normalize_tsys=normalize_tsys, filetemplate=filetemplate)

        self.parallel = parallel


class SerialTsysflag(tsysflag.Tsysflag):
    Inputs = TsysflagInputs


@task_registry.set_equivalent_casa_task('hifa_tsysflag')
@task_registry.set_casa_commands_comment('The Tsys calibration and spectral window map is computed.')
class Tsysflag(sessionutils.ParallelTemplate):
    Inputs = TsysflagInputs
    Task = SerialTsysflag
