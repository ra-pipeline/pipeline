import re

import pytest

from tests import testing_utils


@pytest.fixture(autouse=True)
def _set_current_test_name(request):
    """Expose a normalized test name through ``tests.testing_utils`` for all tests.

    This autouse fixture updates the module-level
    ``testing_utils._current_test_name`` before each test so helper code can
    inspect the currently running test without each test needing to pass that
    information explicitly.

    The normalization removes a leading ``test``/``test_`` prefix and a
    trailing ``regression``/``_regression`` suffix via the regular expression,
    then strips any remaining leading or trailing underscores. After the test
    finishes, the fixture resets ``testing_utils._current_test_name`` to
    ``None`` to avoid leaking state between tests.
    """
    testing_utils._current_test_name = re.sub(r'^test_?|_?regression$', '', request.node.originalname).strip('_')
    yield
    testing_utils._current_test_name = None
