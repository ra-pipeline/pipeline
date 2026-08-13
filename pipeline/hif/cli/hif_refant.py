import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.refant.referenceantenna.RefAntInputs.__init__
@utils.cli_wrapper
def hif_refant(vis=None, field=None, spw=None, intent=None, hm_refant=None,
               refant=None, geometry=None, flagging=None, parallel=None,
               refantignore=None):
    """Select the best reference antennas.

    The ``hif_refant`` task selects a list of reference antennas and stores them in the pipeline context in priority
    order. An ordered list of preferred reference antennas is calculated, with preference given to antennas closest
    to the center of the array and those with a low flagging fraction through the following metric M::

        M = n_ant * ([1 - (normalized_distance_from_center)] + normalized_fraction_of_unflagged_data)

    The center of the array is defined by the median values of the lists of antenna latitudes and longitudes. The
    WebLog page shows that ordered list of antennas, and the metric for each antenna can be found in the CASA log for
    this stage. A single refant can be selected manually in the PPR (but it will be applied to all EBs of the MOUS).

    To avoid picking a reference antenna that is fully flagged on any particular calibrator intent (for example due
    to shadowing on a low-elevation calibrator), the following procedure is followed:

    1. The per-antenna flagging subscore is calculated for each calibrator intent independently.
    2. Intent-based flagging subscores are calculated by taking the minimum value across intents to establish the
       antenna flagging subscore.
    3. Antennas with a zero flagging subscore are removed entirely from the refant list.

    The priority order is determined by a weighted combination of scores derived by the antenna selection heuristics.
    In manual mode the reference antennas can be set by hand.

    Notes:
        **QA Scoring**

        The QA score is 1.0 if a suitable reference antenna is found, otherwise 0.0.

    Examples:
        1. Compute the references antennas to be used for bandpass and gain calibration.

        >>> hif_refant()

    """
