"""QA Handler module."""

from typing import List

import pipeline.h.tasks.importdata.qa as importdataqa
import pipeline.infrastructure.logging as logging
import pipeline.qa.scorecalculator as qacalc
from pipeline.domain.measurementset import MeasurementSet
from pipeline.infrastructure.pipelineqa import QAPlugin, QAScore

from . import importdata

LOG = logging.get_logger(__name__)


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

    def _check_intents(self, mses: List[MeasurementSet]) -> QAScore:
        """
        Check each measurement set in the list for a set of required intents.

        TODO Should we terminate execution on missing intents?

        Args:
            mses: list of MeasurementSet

        Returns:
            QAScore object
        """
        return qacalc.score_missing_intents(mses, array_type='ALMA_TP')


class SDImportDataListQAHandler(importdataqa.ImportDataListQAHandler, QAPlugin):
    """QA handling class to combine QA scores of a list of SDImportDataResults."""

    child_cls = importdata.SDImportDataResults
