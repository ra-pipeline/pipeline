# Do not evaluate type annotations at definition time.
from __future__ import annotations

import collections.abc
import itertools
from typing import TYPE_CHECKING

import pipeline.infrastructure.pipelineqa as pqa
import pipeline.qa.scorecalculator as qacalc
from pipeline import infrastructure
from pipeline.h.tasks.exportdata import aqua
from pipeline.hifa.tasks.importdata import almaimportdata
from pipeline.infrastructure.utils import ms_separation_angles
if TYPE_CHECKING:
    from pipeline.domain import MeasurementSet
    from pipeline.infrastructure.basetask import Results
    from pipeline.infrastructure.launcher import Context

LOG = infrastructure.logging.get_logger(__name__)

aqua_exporter = aqua.xml_generator_for_metric('ScoreParallacticAngle', '{:0.3f}')
aqua.register_aqua_metric(aqua_exporter)


class ALMAImportDataListQAHandler(pqa.QAPlugin):
    result_cls = collections.abc.Iterable
    child_cls = almaimportdata.ALMAImportDataResults

    def handle(self, context: Context, result: almaimportdata.ALMAImportDataResults) -> None:
        super().handle(context, result)

        # Check per-session parallactic angle coverage of polarisation calibration
        parallactic_threshold = result.inputs['minparang']
        # gather mses into a flat list
        mses = list(itertools.chain(*(r.mses for r in result)))

        # PIPE-597 spec states to test POLARIZATION intent
        intents_to_test = {'POLARIZATION'}
        parang_scores, parang_ranges = qacalc.score_parallactic_angle_range(mses, intents_to_test, parallactic_threshold)

        result.qa.pool.extend(parang_scores)
        result.parang_ranges = parang_ranges

        # PIPE-65 separation angles of TARGET with PHASE and CHECK
        sep_angle_dict = ms_separation_angles(mses)
        result.sep_angles = sep_angle_dict

        # Make scores for separations angles - all 1.0 for now just to report information
        # hidden from weblog accordion for current implementation
        sepang_scores = qacalc.score_separation_angles(mses, result.sep_angles)
        result.qa.pool.extend(sepang_scores)


class ALMAImportDataQAHandler(pqa.QAPlugin):
    result_cls = almaimportdata.ALMAImportDataResults
    child_cls = None

    def handle(self, context: Context, result: almaimportdata.ALMAImportDataResults) -> None:
        # Check for the presence of polarization intents
        recipe_name = context.project_structure.recipe_name
        polcal_scores = _check_polintents(recipe_name, result.mses)

        # Check for the presence of receiver bands with calibration issues
        score2 = _check_bands(result.mses)

        # Check for validity of observing modes.
        scores3 = _check_observing_modes(result.mses)

        # Check for science spw names matching the virtual spw ID lookup table
        score4 = _check_science_spw_names(result.mses,
                                          context.observing_run.virtual_science_spw_names)

        # Flux service usage
        scores5 = _check_fluxservice(result)

        # Check for flux.csv
        score6 = _check_fluxcsv(result)

        # Check if amp/bp/phcal objects are the same (returns list of pqa)
        scores7 = _check_calobjects(recipe_name, result.mses)

        # Check for flux service messages/warnings
        score8 = _check_fluxservicemessages(result)

        # Check for flux service status codes
        score9 = _check_fluxservicestatuscodes(result)
        
        # Add all scores to QA score pool in result.
        result.qa.pool.extend(polcal_scores)
        result.qa.pool.extend([score2, score4, score6, score8, score9])
        result.qa.pool.extend(scores3)
        result.qa.pool.extend(scores5)
        result.qa.pool.extend(scores7)


def _check_polintents(recipe_name: str, mses: list[MeasurementSet]) -> list[pqa.QAScore]:
    """
    Check each measurement set for polarization intents
    """
    return qacalc.score_polintents(recipe_name, mses)


def _check_bands(mses: list[MeasurementSet]) -> pqa.QAScore:
    """
    Check each measurement set for bands with calibration issues
    """
    return qacalc.score_bands(mses)


def _check_observing_modes(mses: list[MeasurementSet]) -> list[pqa.QAScore]:
    """
    Check each measurement set for issues with observing modes.
    """
    return qacalc.score_observing_modes(mses)


def _check_science_spw_names(mses: list[MeasurementSet], virtual_science_spw_names: list[str]) -> pqa.QAScore:
    """
    Check science spw names
    """
    return qacalc.score_science_spw_names(mses, virtual_science_spw_names)


def _check_fluxservice(result: Results) -> pqa.QAScore:
    """
    Check flux service usage
    """
    return qacalc.score_fluxservice(result)


def _check_fluxservicemessages(result: Results) -> pqa.QAScore:
    """
    Check flux service messages
    """
    return qacalc.score_fluxservicemessages(result)


def _check_fluxservicestatuscodes(result: Results) -> pqa.QAScore:
    """
    Check flux service statuscodes
    """
    return qacalc.score_fluxservicestatuscodes(result)


def _check_fluxcsv(result: Results) -> pqa.QAScore:
    """
    Check for flux.csv file
    """
    return qacalc.score_fluxcsv(result)


def _check_calobjects(recipe_name: str, mses: list[MeasurementSet]) -> list[pqa.QAScore]:
    """
    Check if BP/Phcal/Ampcal are all the same object
    """

    return qacalc.score_samecalobjects(recipe_name, mses)

def _report_separation_angles(sepangles: dict) -> pqa.QAScore:
    """
    Reports the separation angles for the ms's TARGET to 
    PHASE and if present CHECK to PHASE
    """

    # test the scoring here before the qacalc area
    mskeys = sepangles.keys()

    # loop the mskeys and report each source
    # we don't really want to show all these as a score...anyway..

    # holds the final list of QA scores
    scores: list[pqa.QAScore] = []

    LOG.info('doing the sepangle scores')
    
    for mskey in mskeys:
        # filter the dict
        for primary, secondaries in sepangles[mskey].items():
            # primary will be intent, fieldid, fieldname
            # secondaries is another dict with intent, fieldid, fieldname as key, and a dict as the value with unit and value
            intent1 = primary[0]
            field1 = f'{primary[2]}' # can use other string process like -->>  f"{field} (#{fieldid})"
            # pull the items into a tuple
            intent2 = [(fld2,id2,nm2,ang['unit'],ang['value']) for (fld2,id2,nm2),ang in secondaries.items()][0] # only item per secondary
            field2 = f'{intent2[2]}'
            if intent2[3] == 'deg':
                sepvalue=round(intent2[4],2) # or 3 dp ?
                # do the score
                score = 1.0
                longmsg = 'For %s the %s %s to %s %s separation angle is %s deg'%(mskey, intent1, field1, intent2[0], field2, str(sepvalue))
                shortmsg = ' %s to %s is %s'%(field1, field2, str(sepvalue))
                reportsep=str(sepvalue)
            else:
                # do the score
                score = 0.90
                longmsg = 'For %s the %s %s to %s %s separation angle cannot be extracted'%(mskey, intent1, field1, intent2[0], field2)
                shortmsg = ' %s to %s is n/a'
                reportsep='n/a'
                
            origin = pqa.QAOrigin(metric_name='report_separation_angles',
                          metric_score=reportsep, # this is the value not a 0 to 1 score
                          metric_units='degrees')

            score = pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=mskey, origin=origin, weblog_location=pqa.WebLogLocation.HIDDEN)# weblog location can be HIDDEN - doesnt render
       
            scores.append(score)
                                
    return scores
