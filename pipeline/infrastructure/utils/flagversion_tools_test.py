"""Tests for pipeline.infrastructure.utils.flagversion_tools."""
from __future__ import annotations

import os
import shutil

import casatasks
import numpy as np
import pytest

from .. import casa_tools
from .flagversion_tools import transfer_flagversion

_MS_SMALL = 'pl-unittest/uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms'


@pytest.fixture
def ms_copy(tmp_path):
    """Writable copy of the small test MS placed in a temporary directory."""
    src = casa_tools.utils.resolve(_MS_SMALL)
    dst = str(tmp_path / os.path.basename(src))
    shutil.copytree(src, dst)
    return dst


def _assert_flagversions_equal(fv_a, fv_b, ddids):
    """Assert that FLAG_ROW and per-DD FLAG are identical in two flag version tables."""
    with casa_tools.TableReader(fv_a) as ta, \
            casa_tools.TableReader(fv_b) as tb:
        np.testing.assert_array_equal(
            ta.getcol('FLAG_ROW'),
            tb.getcol('FLAG_ROW'),
            err_msg='FLAG_ROW mismatch between flag versions',
        )
        for ddid in np.unique(ddids):
            rows = np.where(ddids == ddid)[0].tolist()
            sub_a = ta.selectrows(rows)
            sub_b = tb.selectrows(rows)
            try:
                flag_a = sub_a.getcol('FLAG')
                flag_b = sub_b.getcol('FLAG')
            finally:
                sub_a.close()
                sub_b.close()
            np.testing.assert_array_equal(
                flag_a, flag_b,
                err_msg=f'FLAG mismatch for DATA_DESC_ID={ddid}',
            )


def test_transfer_flagversion_identity(ms_copy, tmp_path):
    """Identity transfer (ms_source == ms_target) preserves all flags exactly.

    Two flag versions are saved with different flag states to verify that all
    versions in .flagversions are transferred.
    """
    casatasks.flagdata(vis=ms_copy, mode='unflag', flagbackup=False)
    casatasks.flagdata(vis=ms_copy, mode='manual', antenna='0', flagbackup=False)
    casatasks.flagmanager(vis=ms_copy, mode='save', versionname='ver1', merge='replace')
    casatasks.flagdata(vis=ms_copy, mode='manual', antenna='1', flagbackup=False)
    casatasks.flagmanager(vis=ms_copy, mode='save', versionname='ver2', merge='replace')

    source_fvs = f'{ms_copy}.flagversions'
    target_fvs = str(tmp_path / 'target.flagversions')

    transfer_flagversion(ms_copy, ms_copy,
                         source_flagversions=source_fvs,
                         target_flagversions=target_fvs)

    with casa_tools.TableReader(ms_copy) as tb:
        ddids = tb.getcol('DATA_DESC_ID')

    for vname in ('flags.ver1', 'flags.ver2'):
        fv_src = os.path.join(source_fvs, vname)
        fv_tgt = os.path.join(target_fvs, vname)
        assert os.path.isdir(fv_tgt), f'{vname} was not transferred'
        with casa_tools.TableReader(fv_tgt) as tb:
            assert tb.nrows() == len(ddids), (
                f'{vname}: output row count {tb.nrows()} != MS row count {len(ddids)}'
            )
        _assert_flagversions_equal(fv_src, fv_tgt, ddids)


def test_transfer_flagversion_mstransform(ms_copy, tmp_path):
    """Transfer flags to an MS produced by mstransform with spw+field selection.

    The source MS has two DDIDs:
      DDID 0 -> SPW 0 (128-chan full-res)
      DDID 1 -> SPW 1 (1-chan channel-averaged)

    mstransform selects spw='1' and two of four fields, so the output MS has:
      - a single DDID 0 that maps back to original DDID 1  (renumbering test)
      - a strict row subset  (row-selection test)

    The transferred flag version is compared against the result of applying the
    same flagging directly to ms_xform, which is the ground truth.
    """
    casatasks.flagdata(vis=ms_copy, mode='unflag', flagbackup=False)

    # Build the transformed MS: spw='1' (DDID 1 -> new DDID 0), fields 0 and 2.
    ms_xform = str(tmp_path / 'xform.ms')
    casatasks.mstransform(vis=ms_copy, outputvis=ms_xform,
                          spw='1', field='0,2', keepflags=True,
                          datacolumn='data')

    # Flag antenna 0 in the *original* MS and save the flag version.
    casatasks.flagdata(vis=ms_copy, mode='manual', antenna='0', flagbackup=False)
    casatasks.flagmanager(vis=ms_copy, mode='save', versionname='antflag', merge='replace')

    # Transfer the flag version to the transformed MS.
    source_fvs = f'{ms_copy}.flagversions'
    target_fvs = str(tmp_path / 'xform.flagversions')
    transfer_flagversion(ms_copy, ms_xform,
                         source_flagversions=source_fvs,
                         target_flagversions=target_fvs,
                         remap_ids=True)

    fv_tgt = os.path.join(target_fvs, 'flags.antflag')
    assert os.path.isdir(fv_tgt), 'flags.antflag was not transferred'

    # Build the reference: apply the same flagging directly to ms_xform.
    casatasks.flagdata(vis=ms_xform, mode='unflag', flagbackup=False)
    casatasks.flagdata(vis=ms_xform, mode='manual', antenna='0', flagbackup=False)
    casatasks.flagmanager(vis=ms_xform, mode='save', versionname='ref', merge='replace')
    fv_ref = f'{ms_xform}.flagversions/flags.ref'

    with casa_tools.TableReader(ms_xform) as tb:
        nrows = tb.nrows()
        ddids = tb.getcol('DATA_DESC_ID')

    with casa_tools.TableReader(fv_tgt) as tb:
        assert tb.nrows() == nrows, (
            f'Transferred flag version row count {tb.nrows()} != '
            f'transformed MS row count {nrows}'
        )

    _assert_flagversions_equal(fv_ref, fv_tgt, ddids)


def test_transfer_flagversion_reorder(ms_copy, tmp_path):
    """Transfer flags to an MS with rows reordered but no DDID/field changes (remap_ids=False).

    Simulates the VLA Hanning-smoothing case where mstransform changes row
    order without renumbering DDIDs or fields.  Row order is explicitly
    reversed so the permutation is guaranteed to be non-identity, exercising
    the general selectrows copy path rather than the identity fast path.
    """
    casatasks.flagdata(vis=ms_copy, mode='unflag', flagbackup=False)
    casatasks.flagdata(vis=ms_copy, mode='manual', antenna='0', flagbackup=False)
    casatasks.flagmanager(vis=ms_copy, mode='save', versionname='antflag', merge='replace')

    # Build a reordered MS by reversing row order via selectrows.
    ms_rev = str(tmp_path / 'reversed.ms')
    with casa_tools.TableReader(ms_copy) as tb:
        n = tb.nrows()
        sub = tb.selectrows(list(range(n - 1, -1, -1)))
        try:
            sub.copy(ms_rev, deep=True)
        finally:
            sub.close()

    # Transfer the flag version to the reversed MS.
    source_fvs = f'{ms_copy}.flagversions'
    target_fvs = str(tmp_path / 'reversed.flagversions')
    transfer_flagversion(ms_copy, ms_rev,
                         source_flagversions=source_fvs,
                         target_flagversions=target_fvs,
                         remap_ids=False)

    fv_tgt = os.path.join(target_fvs, 'flags.antflag')
    assert os.path.isdir(fv_tgt), 'flags.antflag was not transferred'

    # Ground truth: apply the same flagging directly to ms_rev.
    casatasks.flagdata(vis=ms_rev, mode='unflag', flagbackup=False)
    casatasks.flagdata(vis=ms_rev, mode='manual', antenna='0', flagbackup=False)
    casatasks.flagmanager(vis=ms_rev, mode='save', versionname='ref', merge='replace')
    fv_ref = f'{ms_rev}.flagversions/flags.ref'

    with casa_tools.TableReader(ms_rev) as tb:
        nrows = tb.nrows()
        ddids = tb.getcol('DATA_DESC_ID')

    with casa_tools.TableReader(fv_tgt) as tb:
        assert tb.nrows() == nrows, (
            f'Transferred flag version row count {tb.nrows()} != '
            f'reversed MS row count {nrows}'
        )

    _assert_flagversions_equal(fv_ref, fv_tgt, ddids)
