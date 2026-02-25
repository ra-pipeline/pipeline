import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.selmodel.vlasetjy.VLASetjyInputs.__init__
@utils.cli_wrapper
def hifv_vlasetjy(vis=None, field=None, intent=None, spw=None, model=None, reffile=None, fluxdensity=None, spix=None,
                  reffreq=None, scalebychan=None, standard=None):
    """Sets flux density scale and fills calibrator model to MeasurementSets.

    The hifv_vlasetjy task does an initial run of setjy on the vis.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Initial run of setjy:

        >>> hifv_vlasetjy()

    """
