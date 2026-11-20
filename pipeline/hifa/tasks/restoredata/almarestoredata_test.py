from types import SimpleNamespace
from unittest import mock

import pytest

from pipeline.hifa.tasks.importdata import almaimportdata
from pipeline.hifa.tasks.restoredata import almarestoredata
from pipeline.infrastructure.launcher import Context


@pytest.fixture
def context(tmp_path, monkeypatch, request):
    monkeypatch.chdir(tmp_path)
    return Context(name=request.node.name)


def test_alma_importdata_inputs_preserves_empty_exclude_spw(context):
    default_inputs = almaimportdata.ALMAImportDataInputs(context=context)
    assert default_inputs.exclude_spw == '*#SQLD'

    none_inputs = almaimportdata.ALMAImportDataInputs(context=context, exclude_spw=None)
    assert none_inputs.exclude_spw == '*#SQLD'

    empty_inputs = almaimportdata.ALMAImportDataInputs(context=context, exclude_spw='')
    assert empty_inputs.exclude_spw == ''


@pytest.mark.parametrize(
    'pipeline_version, expected_exclude_spw',
    [
        ('2026.3.0.48', ''),
        ('2026.3.0.49', '*#SQLD'),
        ('2026.3.0.50+dev', '*#SQLD'),
        (None, ''),
        ('not-a-version', ''),
    ],
)
def test_almarestoredata_do_importasdm_exclude_spw_cutoff(
    context,
    monkeypatch,
    pipeline_version,
    expected_exclude_spw,
):
    task = almarestoredata.ALMARestoreData.__new__(almarestoredata.ALMARestoreData)
    task.inputs = SimpleNamespace(
        context=context,
        lazy=False,
        bdfflags=True,
        asis='Annotation',
        ocorr_mode='ca',
    )
    task._executor = mock.Mock()
    task._executor.execute.return_value = 'import_result'
    task._do_get_manifest = mock.Mock(return_value=object())
    task._extract_casa_pipeline_version = mock.Mock(return_value=('6.7.4', pipeline_version, 1))

    captured = {}

    def _fake_container(*args, **kwargs):
        captured.update(kwargs)
        return mock.Mock()

    monkeypatch.setattr(almarestoredata.vdp, 'InputsContainer', _fake_container)
    monkeypatch.setattr(almarestoredata.almaimportdata, 'ALMAImportData', lambda container: container)

    result = task._do_importasdm(sessionlist=['default'], vislist=['uid___A002_test'])
    assert result == 'import_result'
    assert captured['exclude_spw'] == expected_exclude_spw
