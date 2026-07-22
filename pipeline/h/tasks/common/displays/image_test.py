"""Unit and regression tests for _SentinelMap and _SentinelNorm."""
from __future__ import annotations

import matplotlib
matplotlib.use('Agg')

import numpy as np
import pytest
from matplotlib import cm
from matplotlib.colors import Colormap, Normalize

from pipeline.h.tasks.common.displays.image import _SentinelMap, _SentinelNorm


class TestSentinelMap:

    def test_instantiation(self):
        cmap = _SentinelMap(cm.gray)
        assert isinstance(cmap, Colormap)
        assert cmap.N == cm.gray.N
        assert cmap.name == 'SentinelMap'
        assert cmap.sentinels == {}

    def test_no_mutable_default_sentinels(self):
        s1 = _SentinelMap(cm.gray)
        s2 = _SentinelMap(cm.gray)
        s1.sentinels[99.0] = (1, 0, 0)
        assert s2.sentinels == {}

    def test_with_sentinels(self):
        sentinels = {2.0: (0.5, 0.0, 0.0), 5.0: (0.0, 0.5, 0.0)}
        cmap = _SentinelMap(cm.gray, sentinels=sentinels)
        assert cmap.sentinels == sentinels

    def test_call_no_sentinels(self):
        cmap = _SentinelMap(cm.gray)
        data = np.array([[0.0, 0.5], [1.0, 0.25]])
        result = cmap(data)
        assert result.shape == (*data.shape, 4)
        assert result.dtype == np.float64

    def test_call_replaces_sentinels(self):
        r, g, b = 0.8, 0.1, 0.2
        sentinels = {2.0: (r, g, b)}
        cmap = _SentinelMap(cm.gray, sentinels=sentinels)
        data = np.array([[0.0, 2.0], [1.0, 0.5]])
        result = cmap(data)
        mask = np.isclose(data, 2.0)
        assert np.allclose(result[mask, 0], r)
        assert np.allclose(result[mask, 1], g)
        assert np.allclose(result[mask, 2], b)

    def test_call_bytes(self):
        sentinels = {2.0: (1.0, 0.0, 0.0)}
        cmap = _SentinelMap(cm.gray, sentinels=sentinels)
        data = np.array([0.0, 2.0])
        result = cmap(data, bytes=True)
        assert result.dtype == np.uint8
        mask = np.isclose(data, 2.0)
        assert np.allclose(result[mask, 0], 255)

    def test_regression_super_init_called(self):
        cmap = _SentinelMap(cm.gray, sentinels={2.0: (1, 0, 0)})
        data = np.array([[0.0, 0.5], [2.0, 1.0]], dtype=float)
        result = cmap(data)
        assert result.shape == (2, 2, 4)

    def test_regression_fidelity_with_wrapped_cmap(self):
        cmap = _SentinelMap(cm.gray)
        data = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
        result = cmap(data)
        expected = cm.gray(data)
        np.testing.assert_array_almost_equal(result, expected)


class TestSentinelNorm:

    def test_instantiation(self):
        norm = _SentinelNorm(vmin=0, vmax=10)
        assert isinstance(norm, Normalize)
        assert norm.sentinels == []

    def test_with_sentinels(self):
        norm = _SentinelNorm(vmin=0, vmax=10, sentinels=[2.0, 5.0])
        assert norm.sentinels == [2.0, 5.0]

    def test_normalize_preserves_sentinels(self):
        norm = _SentinelNorm(vmin=0, vmax=10, sentinels=[2.0, 5.0])
        data = np.array([0.0, 2.0, 5.0, 10.0], dtype=float)
        result = norm(data)
        assert np.isclose(result[1], 2.0), 'sentinel 2.0 was changed'
        assert np.isclose(result[2], 5.0), 'sentinel 5.0 was changed'

    def test_normalize_values(self):
        norm = _SentinelNorm(vmin=0, vmax=10, sentinels=[2.0, 5.0])
        data = np.array([0.0, 10.0], dtype=float)
        result = norm(data)
        assert np.isclose(result[0], 0.0), 'vmin not mapped to 0'
        assert np.isclose(result[1], 1.0), 'vmax not mapped to 1'

    def test_clip_default(self):
        norm = _SentinelNorm(vmin=0, vmax=10)
        data = np.array([-5.0, 15.0], dtype=float)
        result = norm(data)
        assert np.isclose(result[0], 0.0), 'below vmin not clipped to 0'
        assert np.isclose(result[1], 1.0), 'above vmax not clipped to 1'

    def test_no_mutable_default_sentinels(self):
        n1 = _SentinelNorm(vmin=0, vmax=10)
        n2 = _SentinelNorm(vmin=0, vmax=10)
        n1.sentinels.append(99.0)
        assert n2.sentinels == []
