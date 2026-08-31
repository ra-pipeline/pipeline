import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.imageprecheck.imageprecheck.ImagePreCheckInputs.__init__
@utils.cli_wrapper
def hifa_imageprecheck(vis=None, desired_angular_resolution=None, calcsb=None, parallel=None):
    """Select the optimal Briggs ``robust`` parameter and compute sensitivity estimates for science targets.

    Uses the representative source and spectral window associated with the PI-selected representative frequency,
    when available, to calculate predicted synthesized beams and theoretical sensitivity estimates for representative
    and aggregate ``TARGET`` bandwidths. The WebLog reports a table of predicted beam sizes and theoretical
    sensitivity estimates for each ``robust`` value.

    If representative-target metadata are unavailable, the task falls back to the first available source with
    ``TARGET`` intent and the center frequency of the first available spectral window. If no such source exists, it
    tries selected calibration intents. This fallback is used, for example, for pre-Cycle 5 data that do not have
    representative-target metadata.

    For 12-m data, the task evaluates Briggs ``robust`` values 0.0, +0.5, +1.0, and +2.0. Values below 0.0 are not
    considered. When multiple values produce an acceptable beam area, it selects them in the preference order +0.5,
    0.0, +1.0, +2.0. For ACA 7-m data, only ``robust=+0.5`` is evaluated.

    The selection compares predicted synthesized beam area with the area range implied by the requested
    angular-resolution range. The major and minor axes are reported separately, but they are not required to fall
    independently within the requested range.

    The selected ``robust`` value is written to the pipeline context for later imaging. The task also writes the
    selected ``uvtaper`` when it is non-empty; a non-default taper may be calculated for the requested-resolution
    ``ALMA-SRDP`` case. The ``cell`` and ``imsize`` values calculated while testing candidate beams remain local to
    imageprecheck; later imaging stages calculate image geometry from the selected beam and current imaging inputs.

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

    Examples:
        1. Run with default settings to select the best robust parameter prior to imaging:

        >>> hifa_imageprecheck()

        2. Force re-calculation of sensitivities and beams:

        >>> hifa_imageprecheck(calcsb=True)

    """
