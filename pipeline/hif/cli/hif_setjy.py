import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.setmodel.setjy.SetjyInputs.__init__
@utils.cli_wrapper
def hif_setjy(vis=None, field=None, intent=None, spw=None, model=None,
              reffile=None, normfluxes=None, reffreq=None, fluxdensity=None,
              spix=None, scalebychan=None, standard=None):
    """Fill the model column with calibrated visibilities.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Set the model flux densities for all the amplitude calibrators:

        >>> hif_setjy()

    """
