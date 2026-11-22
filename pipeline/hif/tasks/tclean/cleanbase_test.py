"""Tests for CleanBase fractional_bw parameter handling."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pipeline.hif.heuristics.imageparams_base import ImageParamsHeuristics
from pipeline.hif.tasks.tclean.cleanbase import CleanBase, CleanBaseInputs
from pipeline.hif.tasks.tclean.resultobjects import TcleanResult
from pipeline.infrastructure import launcher


def _make_clean_task(weighting: str) -> tuple[CleanBase, MagicMock]:
    """Create a CleanBase task with mocked context, heuristics, and executor."""
    ms_mock = MagicMock()
    ms_mock.name = 'uid___A002_X000000_X000.ms'

    context = MagicMock(spec=launcher.Context)
    context.output_dir = '.'
    context.observing_run = MagicMock()
    context.observing_run.get_ms.return_value = ms_mock
    context.observing_run.virtual2real_spw_id.return_value = 0
    context.observing_run.get_real_spwsel.return_value = ['0']

    heuristics = ImageParamsHeuristics([ms_mock.name], '0', None)
    heuristics.get_nfrms_multiplier = MagicMock(return_value=1.0)
    heuristics.is_eph_obj = MagicMock(return_value=False)
    heuristics.wprojplanes = MagicMock(return_value=1)
    heuristics.deconvolver = MagicMock(return_value='hogbom')
    heuristics.savemodel = MagicMock(return_value='none')
    heuristics.cycleniter = MagicMock(return_value=None)
    heuristics.cyclefactor = MagicMock(return_value=1.0)
    heuristics.nmajor = MagicMock(return_value=None)
    heuristics.minpsffraction = MagicMock(return_value=0.05)
    heuristics.maxpsffraction = MagicMock(return_value=0.8)
    heuristics.scales = MagicMock(return_value=None)
    heuristics.mask = MagicMock(return_value='')
    heuristics.pbmask = MagicMock(return_value=None)
    heuristics.restfreq = MagicMock(return_value=None)
    heuristics.conjbeams = MagicMock(return_value=None)
    heuristics.usepointing = MagicMock(return_value=None)
    heuristics.mosweight = MagicMock(return_value=False)
    heuristics.nsigma = MagicMock(return_value=0.0)
    heuristics.rotatepastep = MagicMock(return_value=None)
    heuristics.smallscalebias = MagicMock(return_value=None)
    heuristics.pointingoffsetsigdev = MagicMock(return_value=None)
    heuristics.psfcutoff = MagicMock(return_value=None)
    heuristics.tclean_stopcode_ignore = MagicMock(return_value=[])

    inputs = CleanBaseInputs(
        context,
        vis=[ms_mock.name],
        imagename='test_cube',
        datacolumn='data',
        intent='TARGET',
        field='SourceA',
        spw='0',
        spwsel=['0'],
        specmode='cube',
        hm_specmode='cube',
        gridder='standard',
        deconvolver='hogbom',
        imsize=[64, 64],
        cell=['1.0arcsec'],
        phasecenter='J2000 00:00:00 00.00.00',
        stokes='I',
        nchan=100,
        start='100.0GHz',
        width='10.0MHz',
        outframe='LSRK',
        weighting=weighting,
        robust=0.5,
        niter=0,
        threshold='0.0mJy',
        pblimit=0.2,
        hm_perchanweightdensity=True,
        hm_npixels=0,
        heuristics=heuristics,
        parallel=False,
    )
    executor = MagicMock()
    executor.execute.return_value = {}
    task = CleanBase(inputs)
    task._executor = executor
    return task, executor


@pytest.mark.parametrize(
    ('weighting', 'has_param', 'expect_fractional_bw'),
    [
        ('briggsbwtaper', True, True),
        ('briggs', True, False),
        ('briggsbwtaper', False, False),
    ],
)
def test_cleanbase_passes_fractional_bw(
    weighting: str,
    has_param: bool,
    expect_fractional_bw: bool,
) -> None:
    """Verify CleanBase passes fractional_bw only for briggsbwtaper when supported."""
    task, _ = _make_clean_task(weighting)
    result = TcleanResult(vis=task.inputs.vis, sourcename='SourceA', intent='TARGET', spw='0', specmode='cube')

    if has_param:

        def fake_tclean(vis: str = '', weighting: str = 'natural', fractional_bw: float = 0.0) -> None:
            return None

    else:

        def fake_tclean(vis: str = '', weighting: str = 'natural') -> None:
            return None

    with (
        patch('pipeline.hif.heuristics.imageparams_base.casatasks.tclean', fake_tclean),
        patch('pipeline.hif.tasks.tclean.cleanbase.casa_tasks.tclean') as mock_casa_tclean,
    ):
        mock_casa_tclean.return_value = MagicMock()
        task._do_clean_cycle(scanidlist=[], result=result, iter=0)

    call_kwargs = mock_casa_tclean.call_args.kwargs
    if expect_fractional_bw:
        assert 'fractional_bw' in call_kwargs
        assert call_kwargs['fractional_bw'] == pytest.approx((100 * 10e6) / (100e9 + 0.5 * 99 * 10e6))
    else:
        assert 'fractional_bw' not in call_kwargs
