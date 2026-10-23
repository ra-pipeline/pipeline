import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.analysestokescubes.analysestokescubes.AnalysestokescubesInputs.__init__
@utils.cli_wrapper
def hifv_analyzestokescubes(vis=None):
    """Characterize stokes IQUV flux densities as a function of frequency for VLASS Coarse Cube (CC) images.

    Examples:
        1. Basic analyzestokescubes task

        >>> hifv_analyzestokescubes()

    """
