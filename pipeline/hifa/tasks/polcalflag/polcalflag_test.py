"""Phase 1 plumbing tests for PIPE-2956 on ``hifa_polcalflag``.

Verifies that ``examineCrossPolSum`` is exposed on ``PolcalflagInputs`` and the
CLI wrapper, and that it is forwarded to ``hif_correctedampflag``.
"""

import inspect
from unittest.mock import Mock

from pipeline.hifa.cli.hifa_polcalflag import hifa_polcalflag
from pipeline.hifa.tasks.polcalflag import polcalflag as polcalflag_module
from pipeline.hifa.tasks.polcalflag.polcalflag import PolcalflagInputs
from pipeline.infrastructure.launcher import Context

PARAM = 'examineCrossPolSum'


def test_inputs_descriptor_default_is_false():
    """Tests whether the default descriptor value is False."""
    descriptor = getattr(PolcalflagInputs, PARAM)
    assert descriptor.default is False


def test_inputs_init_signature_includes_param():
    """Tests whether the parameter is included in the init signature."""
    params = inspect.signature(PolcalflagInputs.__init__).parameters
    assert PARAM in params
    assert params[PARAM].default is None


def test_cli_signature_includes_param():
    """Tests whether the parameter is included in the CLI signature."""
    params = inspect.signature(hifa_polcalflag).parameters
    assert PARAM in params
    assert params[PARAM].default is None


def test_inputs_default_resolves_to_false():
    """Tests whether the default input value is False."""
    context = Mock(spec=Context)
    inputs = PolcalflagInputs(context=context, vis=None)
    assert getattr(inputs, PARAM) is False


def test_inputs_explicit_true_resolves_to_true():
    """Tests whether the explicit True value is resolved to True."""
    context = Mock(spec=Context)
    inputs = PolcalflagInputs(context=context, vis=None, **{PARAM: True})
    assert getattr(inputs, PARAM) is True


def test_module_forwards_param_to_correctedampflag_inputs():
    """The wrapper must pass examineCrossPolSum into Correctedampflag.Inputs(...)."""
    source = inspect.getsource(polcalflag_module)
    assert f'{PARAM}=inputs.{PARAM}' in source
