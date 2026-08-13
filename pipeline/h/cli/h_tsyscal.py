from . import utils


@utils.cli_wrapper
def h_tsyscal(vis=None, caltable=None, chantol=None, parallel=None):
    """Derive Tsys calibration tables for a list of ALMA MeasurementSets.

    System temperature (Tsys) as a function of frequency is calculated from the atmospheric calibration scan data by the
    online system at the time of observation. These spectra are imported to a table of the MS during
    :py:func:`hifa_importdata <hifa_importdata>`. In :py:func:`h_tsyscal <h_tsyscal>`, these spectra are copied into a CASA calibration table by the ``gencal``
    task, which flags channels with zero or negative Tsys.

    The WebLog shows the mapping of Tsys spectral windows to science spectral windows, and plots Tsys before flagging.
    Mapping is often necessary because Tsys can only be measured in TDM windows on the 64-station baseline correlator.

    Notes:
        **QA Scoring**

        The QA score is 1.0 if all science spws could be mapped to a Tsys spw, otherwise 0.0.

    Examples:
        1. Standard call

        >>> h_tsyscal()
    """
