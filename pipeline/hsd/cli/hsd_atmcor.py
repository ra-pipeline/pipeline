import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsd.tasks.atmcor.atmcor.SDATMCorrectionInputs.__init__
@utils.cli_wrapper
def hsd_atmcor(
        atmtype=None, dtem_dh=None, h0=None,
        infiles=None, antenna=None, parallel=None,
        field=None, spw=None, pol=None
):

    """Apply offline ATM correction to the data.

    The hsd_atmcor task provides the capability of offline correction of
    residual atmospheric features in the calibrated single-dish spectra
    originated from incomplete calibration mainly due to a difference of
    elevation angles between ON_SOURCE and OFF_SOURCE measurements.

    Optimal atmospheric model is automatically determined by default
    (atmtype = 'auto'). You may specify desired atmospheric model by giving
    either single integer (apply to all EBs) or a list of integers (models
    per EB) to atmtype parameter. Please see parameter description for the
    meanings of integer values.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Basic usage

        >>> hsd_atmcor()

        2. Specify atmospheric model and data selection

        >>> hsd_atmcor(atmtype=1, antenna='PM03,PM04', field='*Sgr*,M100')

        3. Specify atmospheric model per EB (atmtype 1 for 1st EB, 2 for 2nd EB)

        >>> hsd_atmcor(atmtype=[1, 2])

    """