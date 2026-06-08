from __future__ import annotations

from typing import TYPE_CHECKING

import pipeline.h.tasks.tsysflag.tsysflag as tsysflag
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.sessionutils as sessionutils
from pipeline.infrastructure import task_registry

if TYPE_CHECKING:
    from numbers import Integral

    from pipeline.infrastructure import Context

__all__ = [
    'Tsysflag',
    'TsysflagInputs'
]

LOG = infrastructure.logging.get_logger(__name__)


class TsysflagInputs(tsysflag.TsysflagInputs):
    """
    TsysflagInputs defines the inputs for the Tsysflag pipeline task.
    """
    parallel = sessionutils.parallel_inputs_impl()

    # docstring and type hints: supplements hsd_tsysflag
    def __init__(self,
                 context: Context,
                 output_dir: str | None = None,
                 vis: list[str] | None = None,
                 caltable: list[str] | None = None,
                 flag_nmedian: bool | str | None = None,
                 fnm_limit: Integral | str | None = None,
                 fnm_byfield: bool | str | None = None,
                 flag_derivative: bool | str | None = None,
                 fd_max_limit: Integral | str | None = None,
                 flag_edgechans: bool | str | None = None,
                 fe_edge_limit: Integral | str | None = None,
                 flag_fieldshape: bool | str | None = None,
                 ff_refintent: str | None = None,
                 ff_max_limit: Integral | str | None = None,
                 flag_birdies: bool | str | None = None,
                 fb_sharps_limit: Integral | str | None = None,
                 flag_toomany: bool | str | None = None,
                 tmf1_limit: Integral | str | None = None,
                 tmef1_limit: Integral | str | None = None,
                 metric_order: str | None = None,
                 normalize_tsys: bool | str | None = None,
                 filetemplate: str | None = None,
                 parallel: str | bool | None = None):
        """Construct TsysflagInputs instance for SD Tsysflag task.

        Args:
            context: Pipeline context object containing state information.

            output_dir: Output directory.

            vis: List of input MeasurementSets (Not used)

            caltable: List of input Tsys calibration tables.

                Example: caltable=['X132.ms.tsys.s2.tbl']

                Default: None (equivalent to [] - Use the table currently stored in the pipeline context)

            flag_nmedian: True to flag Tsys spectra with high median value.

                Default: None (equivalent to True)

            fnm_limit: Flag spectra with median value higher than
                fnm_limit * median of this measure over all spectra.

                Default: None (equivalent to 2.0)

            fnm_byfield: Evaluate the nmedian metric separately for each field.

                Default: None (equivalent to True)

            flag_derivative: True to flag Tsys spectra with high median derivative.

                Default: None (equivalent to True)

            fd_max_limit: Flag spectra with median derivative higher than
                fd_max_limit * median of this measure over all spectra.

                Default: None (equivalent to 5.0)

            flag_edgechans: True to flag edges of Tsys spectra.

                Default: None (equivalent to True)

            fe_edge_limit: Flag channels whose channel to
                channel difference > fe_edge_limit * median
                across spectrum.

                Default: None (equivalent to 3.0)

            flag_fieldshape: True to flag Tsys spectra with a radically
                different shape to those of the ff_refintent.

                Default: None (equivalent to True)

            ff_refintent: Data intent that provides the reference shape
                for 'flag_fieldshape'.

                Default: None (equivalent to 'BANDPASS')

            ff_max_limit: Flag Tsys spectra with 'fieldshape'
                metric values > ff_max_limit.

                Default: None (equivalent to 13)

            flag_birdies: True to flag channels covering sharp spectral features.

                Default: None (equivalent to True)

            fb_sharps_limit: Flag channels bracketing a channel to
                channel difference > fb_sharps_limit.

                Default: None (equivalent to 0.15)

            flag_toomany: True to flag Tsys spectra for which a proportion of
                antennas for given timestamp and/or proportion of antennas that are
                entirely flagged in all timestamps exceeds their respective thresholds.

                Default: None (equivalent to True)

            tmf1_limit: Flag Tsys spectra for all antennas in a timestamp
                and spw if proportion of antennas already flagged in this
                timestamp and spw exceeds tmf1_limit.

                Default: None (equivalent to 0.666)

            tmef1_limit: Flag Tsys spectra for all antennas and all timestamps
                in a spw, if proportion of antennas that are already entirely
                flagged in all timestamps exceeds tmef1_limit.

                Default: None (equivalent to 0.666)

            metric_order: Order in which to evaluate the flagging metrics
                that are enabled. Disabled metrics are skipped.
                Default order is as follows:

                    nmedian derivative edgechans fieldshape birdies toomany

            normalize_tsys: True to create a normalized Tsys table that is
                used to evaluate the Tsys flagging metrics. All newly found
                flags are also applied to the original Tsys caltable that
                continues to be used for subsequent calibration.

                Default: None (equivalent to False)

            filetemplate: The name of a text file that contains the manual
                Tsys flagging template. If the template flags file is undefined,
                a name of the form 'msname.flagtsystemplate.txt' is assumed.

            parallel: Execute using CASA HPC functionality, if available.
                Default is None, which intends to turn on parallel
                processing if possible.
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


@task_registry.set_equivalent_casa_task('hsd_tsysflag')
@task_registry.set_casa_commands_comment('The Tsys calibration and spectral window map is computed.')
class SerialTsysflag(tsysflag.Tsysflag):
    Inputs = TsysflagInputs


class Tsysflag(sessionutils.ParallelTemplate):
    Inputs = TsysflagInputs
    Task = SerialTsysflag
