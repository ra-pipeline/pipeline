"""QA Handler module."""
from __future__ import annotations

from typing import TYPE_CHECKING

import pipeline.h.tasks.importdata.qa as importdataqa
import pipeline.infrastructure as infrastructure
import pipeline.qa.scorecalculator as qacalc
from pipeline.infrastructure.pipelineqa import QAPlugin, QAScore

from . import importdata

LOG = infrastructure.logging.get_logger(__name__)

if TYPE_CHECKING:
    from pipeline.domain.measurementset import MeasurementSet
    from pipeline.infrastructure.launcher import Context


class SDImportDataQAHandler(importdataqa.ImportDataQAHandler, QAPlugin):
    """ImportDataQAHandler class for Single Dish.

    Extending another QAHandler does not automatically register the extending
    implemention with the pipeline's QA handling system, even if the class being
    extended extends QAPlugin. Extending classes must also extend QAPlugin to be
    registered with the handler.
    """

    result_cls = importdata.SDImportDataResults
    child_cls = None
    generating_task = importdata.SerialSDImportData

    def _check_intents(self, mses: list[MeasurementSet]) -> QAScore:
        """
        Check each measurement set in the list for a set of required intents.

        TODO Should we terminate execution on missing intents?

        Args:
            mses: list of MeasurementSet

        Returns:
            QAScore object
        """
        return qacalc.score_missing_intents(mses, array_type='ALMA_TP')

    def handle(self, context: Context, result: importdata.SDImportDataResults) -> None:
        """Generate QA score for hsd_importdata.

        Most scores are calculated with the QA handler of h_importdata.

        Args:
            context (Context): The context object of pipeline executing.
            result (importdata.SDImportDataResults): The result object of SDImportData executing.
        """
        super().handle(context, result)
        score = qacalc.score_rasterscan_correctness_direction_domain_rasterscan_fail(result)
        result.qa.pool.extend(score)
        score = qacalc.score_rasterscan_correctness_time_domain_rasterscan_fail(result)
        result.qa.pool.extend(score)


class SDImportDataListQAHandler(importdataqa.ImportDataListQAHandler, QAPlugin):
    """QA handling class to combine QA scores of a list of SDImportDataResults."""

    child_cls = importdata.SDImportDataResults
