import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsd.tasks.atmcor.atmcor.SDATMCorrectionInputs.__init__
@utils.cli_wrapper
def hsd_atmcor(
        atmtype=None, dtem_dh=None, h0=None,
        infiles=None, antenna=None, parallel=None,
        field=None, spw=None, pol=None
):
    """Apply offline ATM correction for residual atmospheric effects in calibrated single-dish spectra.

    Corrects residual atmospheric line features in the science target spectra caused by incomplete
    sky calibration due to elevation differences between ON_SOURCE and OFF_SOURCE measurements.
    The correction is based on the atmospheric model described in :cite:`2021PASP..133c4504S`.

    By default (``atmtype='auto'``), the pipeline evaluates all four standard atmospheric models
    and selects the best fit:

    - ``atmtype=1``: tropical
    - ``atmtype=2``: mid-latitude summer
    - ``atmtype=3``: mid-latitude winter
    - ``atmtype=4``: subarctic summer

    All models use a fixed temperature gradient (``dTem_dh=-5.6 K/km``) and fixed water vapour
    scale height (``h0=2 km``). If user-defined parameters are provided, the automatic model
    selection is disabled.

    The WebLog shows a list of the calibrated MSs with the selected model parameters (``atmType``,
    ``h0``, ``dTem_dh``) and integrated spectra (amplitude vs. frequency) after correction;
    magenta curves show the atmospheric transmission. Spectra before correction can be found on the
    :py:func:`hsd_applycal <hsd_applycal>` WebLog page.

    Notes:
        QA scoring:

        - QA = 1.0 if ATM correction is successfully applied.
        - QA = N/A if ATM correction is not applied.
        - QA = 0.0 if an error occurs during the correction.

    Examples:
        1. Apply ATM correction with automatic model selection:

        >>> hsd_atmcor()

        2. Specify an atmospheric model and data selection:

        >>> hsd_atmcor(atmtype=1, antenna='PM03,PM04', field='*Sgr*,M100')

        3. Specify a different model per EB:

        >>> hsd_atmcor(atmtype=[1, 2])

    """