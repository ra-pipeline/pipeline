import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.setmodel.setmodel.SetModelsInputs.__init__
@utils.cli_wrapper
def hif_setmodels(vis=None, reference=None, refintent=None, transfer=None, transintent=None, reffile=None,
                  normfluxes=None, scalebychan=None, parallel=None):
    """Set calibrator source models.

    The model flux density of the amplitude calibrator is set, either from an internal CASA model (solar system
    objects), or from the results of observatory calibrator monitoring (quasars) which ultimately appear in the file
    ``flux.csv`` (see :py:func:`hifa_importdata <hifa_importdata>`). These flux densities are listed on the WebLog page, along with plots of
    the amplitude calibrator as a function of uv distance (which is useful to assess resolved solar system objects).
    If the bandpass calibrator is distinct from the amplitude calibrator and is a frequently monitored quasar, its
    model is also set at this stage.

    Set model fluxes values for calibrator reference and transfer sources using lookup values. By default the
    reference sources are the flux calibrators and the transfer sources are the bandpass, phase, and check source
    calibrators. Reference sources which are also in the transfer source list are removed from the transfer source
    list.

    Built-in lookup tables are used to compute models for solar system object calibrators. Point source models are
    used for other calibrators with flux densities provided in the reference file. Normalized fluxes are computed for
    transfer sources if the ``normfluxes`` parameter is set to True.

    The default reference file is ``flux.csv`` in the current working directory. This file is usually created in the
    importdata stage. The file is in CSV format and contains the following comma-delimited columns::

        vis, fieldid, spwid, I, Q, U, V, pix, comment

    Notes:
        **QA Scoring**

        The QA score is set to 1.0 if the flux density of the amplitude calibrator is successfully set for all
        spectral windows and if the spectral index of the bandpass calibrator is set; otherwise it is set to 0.0.

    Examples:
        1. Set model fluxes for the flux, bandpass, phase, and check sources.

        >>> hif_setmodels()

    """
