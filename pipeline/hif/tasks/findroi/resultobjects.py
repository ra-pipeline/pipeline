from __future__ import annotations

from typing import Any

import pipeline.infrastructure.basetask as basetask


class FindROIResult(basetask.Results):
    """Lightweight pipeline result for the hif_findroi stage."""

    def __init__(
        self,
        stage_product_path: str | None = None,
        artifacts: dict[str, Any] | None = None,
        summary: dict[str, Any] | None = None,
        errors: list[str] | None = None,
        findroi_resources: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.stage_product_path = stage_product_path
        self.artifacts = artifacts or {}
        self.summary = summary or {}
        self.errors = errors or []
        self.findroi_resources = findroi_resources

    def merge_with_context(self, context: Any) -> None:
        """Register exported findroi resources for later downstream discovery."""
        if self.findroi_resources is not None:
            context.findroi_resources = self.findroi_resources

    def __repr__(self) -> str:
        n_sources = self.summary.get('n_sources', 0)
        n_spws = self.summary.get('n_spws', 0)
        n_source_spws = self.summary.get('n_source_spws', 0)
        status = 'error' if self.errors else 'ok'
        return (
            'FindROIResult:\n'
            f'\tstatus={status}\n'
            f'\tsources={n_sources}\n'
            f'\tspws={n_spws}\n'
            f'\tsource_spws={n_source_spws}\n'
            f'\tstage_product={self.stage_product_path}'
        )
