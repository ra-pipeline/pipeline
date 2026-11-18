"""QA score calculators re-exported from the specialized scoring modules.

Each module's __all__ defines its public exports. Add new scoring functions there
to expose them through this facade automatically when it is imported.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:

    def __getattr__(name: str) -> Any: ...


from pipeline.qa import common_scores, hif_scores, hifa_scores, hifv_scores, hsd_scores

_modules = (common_scores, hif_scores, hifa_scores, hifv_scores, hsd_scores)

__all__: list[str] = []

for _module in _modules:
    for _name in _module.__all__:
        if _name in __all__:
            raise ImportError(f'Duplicate QA export: {_name}')
        globals()[_name] = getattr(_module, _name)
        __all__.append(_name)

__all__.sort()

del _module, _name
