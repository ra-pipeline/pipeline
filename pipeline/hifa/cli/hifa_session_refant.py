import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.sessionrefant.sessionrefant.SessionRefAntInputs.__init__
@utils.cli_wrapper
def hifa_session_refant(vis=None, phase_threshold=None):
    """Select a single common reference antenna per session for polarization observations.

    Re-evaluates the reference antenna lists from all MeasurementSets within a session and selects a single
    common reference antenna per session to be used by all subsequent pipeline stages.

    The selection algorithm:

    1. Rank all antennas by the product of their per-EB rankings (based on flagging fraction and central
       location in the array, as in :py:func:`hif_refant <hif_refant>`).
    2. Starting from the highest-ranked antenna, perform a ``gaincal`` with ``solint='int'``, ``calmode='p'``,
       ``gaintype='G'``, ``minsnr=3`` on all PHASE intent scans for each EB.
    3. Check the resulting caltable to see if the reference antenna ever changes. Choose the first antenna for
       which no refant changes occur.
    4. If none of the top-3 candidates qualify (which should be rare), choose the antenna with the most
       solutions as refant and display the number of phase-solution outliers (integrations where the refant
       phase was non-zero, meaning another refant was used). The total number of possible solutions is
       N_EBs x N_spws x N_integrations x N_pol.

    If a single refant was requested via :py:func:`hif_refant <hif_refant>` in the PPR, a warning is generated indicating that
    only one antenna is common across all MSes.

    Notes:
        QA = 1.0 if a suitable session reference antenna is found, otherwise 0.0.

        Only used in polarization recipes.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Compute a single common reference antenna per session:

        >>> hifa_session_refant()

    """
