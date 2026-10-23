import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsd.tasks.tsysflag.tsysflag.TsysflagInputs.__init__
@utils.cli_wrapper
def hsd_tsysflag(vis=None, caltable=None,
                 flag_nmedian=None, fnm_limit=None, fnm_byfield=None,
                 flag_derivative=None, fd_max_limit=None,
                 flag_edgechans=None, fe_edge_limit=None,
                 flag_fieldshape=None, ff_refintent=None, ff_max_limit=None,
                 flag_birdies=None, fb_sharps_limit=None,
                 flag_toomany=None, tmf1_limit=None, tmef1_limit=None,
                 metric_order=None, normalize_tsys=None, filetemplate=None):
    """Flag deviant system temperature measurements for single-dish data.

    Applies a sequence of heuristic flagging tests to the Tsys caltable. If a manual flagging
    template is provided via ``filetemplate``, those flags are applied first. The WebLog shows the
    Tsys spectra per spw per antenna after all flagging has been applied.

    The flagging tests, applied in order, are:

    1. **nmedian** (``flag_nmedian``): flag Tsys spectra whose median value is more than
       ``fnm_limit`` (default 3.0) times the median of all spectra.
    2. **derivative** (``flag_derivative``): flag spectra with a high median derivative
       (``fd_max_limit``), targeting ``ringing`` spectra.
    3. **edgechans** (``flag_edgechans``): flag the edge channels of each spw
       (``fe_edge_limit``).
    4. **fieldshape** (``flag_fieldshape``): flag spectra whose shape differs significantly
       from the reference BANDPASS intent shape (``ff_max_limit``, ``ff_refintent``).
    5. **birdies** (``flag_birdies``): flag narrow spectral features (``fb_sharps_limit``).
    6. **toomany** (``flag_toomany``): flag all antennas in a timestamp/spw if the fraction
       already flagged exceeds ``tmf1_limit``; flag all timestamps in a spw if the fraction
       entirely flagged exceeds ``tmef1_limit``.

    Examples:
        1. Flag Tsys measurements using all recommended tests:

        >>> hsd_tsysflag()

        2. Flag using all tests except ``fieldshape``:

        >>> hsd_tsysflag(flag_fieldshape=False)

    """
