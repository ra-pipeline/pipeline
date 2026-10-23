import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsd.tasks.baselineflag.baselineflag.SDBLFlagInputs.__init__
@utils.cli_wrapper
def hsd_blflag(iteration=None, edge=None, flag_tsys=None, tsys_thresh=None,
               flag_prfre=None, prfre_thresh=None,
               flag_pofre=None, pofre_thresh=None,
               flag_prfr=None, prfr_thresh=None,
               flag_pofr=None, pofr_thresh=None,
               flag_prfrm=None, prfrm_thresh=None, prfrm_nmean=None,
               flag_pofrm=None, pofrm_thresh=None, pofrm_nmean=None,
               plotflag=None, parallel=None,
               infiles=None, antenna=None,
               field=None, spw=None, pol=None):
    """Flag spectra based on post-baseline quality criteria for single-dish data.

    Flags spectra using up to five criteria evaluated on both pre-fit and post-fit spectra:

    - **Expected RMS** (``flag_prfre`` / ``flag_pofre``): flag based on the expected RMS
      calculated from the radiometer equation.
    - **Calculated RMS** (``flag_prfr`` / ``flag_pofr``): flag based on the RMS computed
      directly from the spectrum.
    - **Running mean** (``flag_prfrm`` / ``flag_pofrm``): flag based on a running mean
      comparison for pre-fit and post-fit spectra.
    - **Tsys flagging** (``flag_tsys``): flag based on the Tsys values.

    The WebLog shows the percentage of flagged data per MS and detailed per-criterion plots;
    clicking ``Plots`` displays figures evaluating each criterion as a function of rows, with
    flagged data in red and unflagged data in blue.

    Notes:
        QA scoring (per source per spw):

        - QA = 1.0 if additional flagging is 0%-5%.
        - QA = 1.0-0.5 if additional flagging is 5%-50%.
        - QA = 0.0 if additional flagging > 50%.

    Examples:
        1. Run all flagging rules:

        >>> hsd_blflag()

    """
