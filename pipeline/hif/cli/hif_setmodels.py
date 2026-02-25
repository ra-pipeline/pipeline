import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.setmodel.setmodel.SetModelsInputs.__init__
@utils.cli_wrapper
def hif_setmodels(vis=None, reference=None, refintent=None, transfer=None, transintent=None, reffile=None,
                  normfluxes=None, scalebychan=None, parallel=None):
    """Set calibrator source models.

    Set model fluxes values for calibrator reference and transfer sources using lookup
    values. By default the reference sources are the flux calibrators and the transfer
    sources are the bandpass, phase, and check source calibrators. Reference sources
    which are also in the transfer source list are removed from the transfer source list.

    Built-in lookup tables are used to compute models for solar system object calibrators.
    Point source models are used for other calibrators with flux densities provided in the reference file.
    Normalized fluxes are computed for transfer sources if the ``normfluxes`` parameter is
    set to True.

    The default reference file is 'flux.csv' in the current working directory.
    This file is usually created in the importdata stage. The file is in
    'csv' format and contains the following comma delimited columns.

    vis,fieldid,spwid,I,Q,U,V,pix,comment

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Set model fluxes for the flux, bandpass, phase, and check sources.

        >>> hif_setmodels()

    """
