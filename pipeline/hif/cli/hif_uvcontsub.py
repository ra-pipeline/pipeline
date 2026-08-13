import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.uvcontsub.uvcontsub.UvcontSubInputs.__init__
@utils.cli_wrapper
def hif_uvcontsub(vis=None, field=None, intent=None, spw=None, fitorder=None, parallel=None):
    """Subtract the continuum from the uv-data using the ranges in ``cont.dat``.

    Fits and subtracts the continuum emission for each science target and spw independently using
    the LSRK frequency ranges from the ``cont.dat`` file (produced by :py:func:`hif_findcont <hif_findcont>`). The
    ``cont.dat`` LSRK ranges are translated to the topocentric (TOPO) frame per MS and reported
    in the WebLog.

    Starting in PL2024 the fit order is ``fitorder=1`` by default, but ``fitorder=0`` is used when
    the ``LowBW`` or ``LowSpread`` condition was flagged for that spw in :py:func:`hif_findcont <hif_findcont>` (i.e.
    the selected continuum bandwidth is very small or the selected channels are not well spread
    across the spw). For any spw listed in ``cont.dat`` with no channel ranges specified, the spw
    is treated as ``AllContinuum`` (PL2024+) and no line MS output is produced for that spw.

    After this stage the original continuum + line data reside in the ``DATA`` column of
    ``*_targets.ms``, while the continuum-subtracted data are written to the ``DATA`` column of
    the new ``*_targets_line.ms``.

    Notes:
        QA = 1.0 if a continuum fit table is successfully created; 0.0 otherwise.

    Examples:
        1. Subtract continuum for all science targets and spws:

        >>> hif_uvcontsub()

        2. Subtract continuum for a subset of fields only:

        >>> hif_uvcontsub(field='3C279,M82')

        3. Subtract continuum for selected spws only:

        >>> hif_uvcontsub(spw='11,13')

        4. Override the automatic fit order per field and spw:

        >>> hif_uvcontsub(fitorder={'3C279': {'15': 1, '17': 2}, 'M82': {'13': 2}})

    """
