import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.imageprecheck.imageprecheck.ImagePreCheckInputs.__init__
@utils.cli_wrapper
def hifa_imageprecheck(vis=None, desired_angular_resolution=None, calcsb=None, parallel=None):
    """Select the optimal Briggs ``robust`` parameter and compute sensitivity estimates for science targets.

    Uses the representative source and spw containing the representative frequency (set by the PI in the OT)
    to compute synthesized beam and sensitivity estimates for the aggregate and representative bandwidths over
    a range of Briggs ``robust`` values. The WebLog reports a table of beamsize and sensitivity per ``robust``
    value. If no representative target/frequency information is available the first target and center of the
    first spw are used (e.g. pre-Cycle 5 data does not have this information available).

    The ``robust`` value is selected from the range 0.0-2.0 by checking in order: +0.5, +1.0, 0.0, +2.0.
    Values below 0.0 are not considered (poorer noise characteristics, compromised extended emission recovery).
    For the ACA 7-m array only ``robust=+0.5`` is considered.

    The selected ``cell`` and ``imsize`` are stored in the pipeline context and reused for all subsequent
    imaging stages (continuum, cube, representative bandwidth) to ensure consistent image coordinates.

    Notes:
        QA score based on fit between the predicted synthesized beam and the PI-requested angular resolution
        (AR) range:

        - QA = 1.0 (green): both major and minor axes within the AR range with ``robust=+0.5``.
        - QA = 0.85 (blue): both axes within the AR range with a ``robust`` value other than +0.5.
        - QA = 0.50 (yellow): at least one axis outside the AR range but the beam area within the
          area range corresponding to the PI-requested AR range.
        - QA = 0.25 (red): beam area falls outside the PI-requested AR area range for all ``robust``
          values, meaning imaging products are unlikely to meet PI goals.

        An additional factor of 1.0 vs. 0.5 is applied based on whether representative target/frequency
        information was successfully identified.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Run with default settings to select the best robust parameter prior to imaging:

        >>> hifa_imageprecheck()

        2. Force re-calculation of sensitivities and beams:

        >>> hifa_imageprecheck(calcsb=True)

    """
