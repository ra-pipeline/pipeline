"""Phase 1 plumbing tests for PIPE-2956 on ``hifa_gfluxscaleflag``.

Verifies that ``examineCrossPolSum`` is exposed on ``GfluxscaleflagInputs`` and
the CLI wrapper, and that it is forwarded to ``hif_correctedampflag``.
"""

import inspect
from unittest.mock import Mock

from pipeline.hifa.cli.hifa_gfluxscaleflag import hifa_gfluxscaleflag
from pipeline.hifa.tasks.gfluxscaleflag import gfluxscaleflag as gfluxscaleflag_module
from pipeline.hifa.tasks.gfluxscaleflag.gfluxscaleflag import GfluxscaleflagInputs
from pipeline.infrastructure.launcher import Context

PARAM = 'examineCrossPolSum'


def test_inputs_descriptor_default_is_false():
    """Tests whether the default descriptor value is False."""
    descriptor = getattr(GfluxscaleflagInputs, PARAM)
    assert descriptor.default is False


def test_inputs_init_signature_includes_param():
    """Tests whether the parameter is included in the init signature."""
    params = inspect.signature(GfluxscaleflagInputs.__init__).parameters
    assert PARAM in params
    assert params[PARAM].default is None


def test_cli_signature_includes_param():
    """Tests whether the parameter is included in the CLI signature."""
    params = inspect.signature(hifa_gfluxscaleflag).parameters
    assert PARAM in params
    assert params[PARAM].default is None


def test_inputs_default_resolves_to_false():
    """Tests whether the default input value is False."""
    context = Mock(spec=Context)
    inputs = GfluxscaleflagInputs(context=context, vis=None)
    assert getattr(inputs, PARAM) is False


def test_inputs_explicit_true_resolves_to_true():
    """Test whether the parameter can be set to True."""
    context = Mock(spec=Context)
    inputs = GfluxscaleflagInputs(context=context, vis=None, **{PARAM: True})
    assert getattr(inputs, PARAM) is True


def test_module_forwards_param_to_correctedampflag_inputs():
    """The wrapper must pass examineCrossPolSum into Correctedampflag.Inputs(...)."""
    source = inspect.getsource(gfluxscaleflag_module)
    assert f'{PARAM}=inputs.{PARAM}' in source
