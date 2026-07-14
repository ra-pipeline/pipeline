"""
T2_4MDetailsSDTsysflagRenderer class.

Created on 24 Oct 2014

@author: sjw
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import pipeline.infrastructure.renderer.basetemplates as basetemplates
import pipeline.infrastructure.logging as logging
from pipeline.hsd.tasks.common import qautils

if TYPE_CHECKING:
    from pipeline.h.tasks.exportdata.exportdata import ExportDataResults
    from pipeline.infrastructure.launcher import Context
LOG = logging.get_logger(__name__)


class T2_4MDetailsSDExportDataRenderer(basetemplates.T2_4MDetailsDefaultRenderer):
    """SDTsysflagRenderer class for t2_4m."""

    def __init__(self, always_rerender: bool = False):
        """Initialise the class.

        Args:
            always_rerender : rerendering execution flag, default: False
        """
        super().__init__(uri='exportdata.mako',
                         description='Prepare pipeline data products for export',
                         always_rerender=always_rerender)

    @qautils.sort_qascores
    def render(self, context: Context, result: ExportDataResults) -> str:
        """
        Custom renderer for hsd_exportdata()

        This method sorts the QAScores with their scores, and renders the weblog,

        Args:
            context: Pipeline context
            result:  ExportDataResults object
        Returns:
            Rendered html document
        """
        # This method modifies the result object,
        # but the changes do not propergate to the original result or context,
        # since they are local in render() thanks to the mechanism of PL infrastructure.
        # Therefore there is no need to bracket the aggregation process
        # with stashing and recovering the original result.qa.pool here.

        return super().render(context, result)

