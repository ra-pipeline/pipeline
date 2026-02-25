import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.refant.referenceantenna.RefAntInputs.__init__
@utils.cli_wrapper
def hif_refant(vis=None, field=None, spw=None, intent=None, hm_refant=None,
               refant=None, geometry=None, flagging=None, parallel=None,
               refantignore=None):
    """Select the best reference antennas.

    The hif_refant task selects a list of reference antennas and stores them
    in the pipeline context in priority order.

    The priority order is determined by a weighted combination of scores derived
    by the antenna selection heuristics. In manual mode the reference antennas
    can be set by hand.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Compute the references antennas to be used for bandpass and gain calibration.

        >>> hif_refant()

    """
