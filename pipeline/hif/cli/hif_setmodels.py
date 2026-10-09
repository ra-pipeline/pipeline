import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.setmodel.setmodel.SetModelsInputs.__init__
@utils.cli_wrapper
def hif_setmodels(vis=None, reference=None, refintent=None, transfer=None, transintent=None, reffile=None,
                  normfluxes=None, scalebychan=None, parallel=None):
    """Set calibrator source models.

    The model flux density of the amplitude calibrator is set, either from an internal CASA model
    (solar system objects), or from the results of observatory calibrator monitoring (quasars) which
    ultimately appear in the file ``flux.csv`` (see :func:`~pipeline.hifa.cli.hifa_importdata` and the
    User's Guide :ref:`Helper text files <sec-helperfiledescription>` for more detail).
    These flux densities are listed on the WebLog page, along with plots of the amplitude calibrator as a
    function of uv distance (which is useful to assess resolved solar system objects).

    ``flux.csv`` contains the following comma-delimited columns::
    
        vis, fieldid, spwid, I, Q, U, V, pix, comment


    In the default pipeline flux calibration process, reference sources are the flux calibrators and the
    transfer sources are the bandpass, phase, and check source calibrators. Reference sources which are
    also in the transfer source list are removed from the transfer source list.
    Transfer source fluxe densities and spectral indices are also set in this stage, if that information
    is known (generally for frequently monitored quasars).

    Normalized fluxes are computed for transfer sources if the ``normfluxes`` parameter is set to True.


    Notes:
        **QA Scoring**

        The QA score is set to 1.0 if the flux density of the amplitude calibrator is successfully set for all
        spectral windows and if the spectral index of the bandpass calibrator is set; otherwise it is set to 0.0.

    Examples:
        1. Set model fluxes for the flux calibrator, and for transfer sources if available in the context.

        >>> hif_setmodels()

    """
