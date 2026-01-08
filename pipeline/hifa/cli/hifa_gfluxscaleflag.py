import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.gfluxscaleflag.gfluxscaleflag.GfluxscaleflagInputs.__init__
@utils.cli_wrapper
def hifa_gfluxscaleflag(vis=None, intent=None, phaseupsolint=None, solint=None, minsnr=None, refant=None,
                        antnegsig=None, antpossig=None, tmantint=None, tmint=None, tmbl=None, antblnegsig=None,
                        antblpossig=None, relaxed_factor=None, niter=None, parallel=None):
    """Flag the flux, diffgain, phase calibrators and check source.

    This task computes the flagging heuristics on the flux, diffgain, and phase
    calibrators and the check source, by calling hif_correctedampflag which
    looks for outlier visibility points by statistically examining the scalar
    difference of corrected amplitudes minus model amplitudes, and flags those
    outliers. The philosophy is that only outlier data points that have remained
    outliers after calibration will be flagged. The heuristic works equally well
    on resolved calibrators and point sources because it is not performing a
    vector difference, and thus is not sensitive to nulls in the flux density
    vs. uvdistance domain. Note that the phase of the data is not assessed.

    In further detail, the workflow is as follows: a snapshot of the flagging
    state is preserved at the start, a preliminary phase and amplitude gaincal
    solution is solved and applied, the flagging heuristics are run and
    any outliers are marked for flagging, the flagging state is restored from the
    snapshot. If any outliers were found, then these are flagged. Plots are
    generated at two points in this workflow: after preliminary phase and
    amplitude calibration but before flagging heuristics are run, and after
    flagging heuristics have been run and applied. If no points were flagged,
    the 'after' plots are not generated or displayed. The score for this stage
    is the standard data flagging score, which depends on the fraction of data
    flagged.

    The preliminary phase solutions use the mapping/combine and gaintype options
    as established in hifa_spwphaseup.


    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. run with recommended settings to create flux scale calibration with flagging
        using recommended thresholds:

        >>> hifa_gfluxscaleflag()

    """
