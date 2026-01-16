import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.statwt.statwt.StatwtInputs.__init__
@utils.cli_wrapper
def hifv_statwt(vis=None, datacolumn=None, overwrite_modelcol=None, statwtmode=None):
    """Compute statistical weights and write them to measurement set.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Statistical weighting of the visibilities:

        >>> hifv_statwt()

        2. Statistical weighting of the visibilities in the Very Large Array Sky Survey Single Epoch use case:

        >>> hifv_statwt(mode='vlass-se', datacolumn='residual_data')

    """
