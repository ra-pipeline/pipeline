"""ALMA-specific interferometric QA score calculators."""

from __future__ import annotations

import collections
import os
import re
import traceback
from typing import TYPE_CHECKING

import numpy as np

import pipeline.infrastructure.pipelineqa as pqa
from pipeline import infrastructure
from pipeline.domain import measures
from pipeline.infrastructure import casa_tools, utils
from pipeline.infrastructure.renderer import rendererutils
from pipeline.qa.common_scores import (
    calc_frac_newly_flagged,
    linear_score,
    log_qa,
)

if TYPE_CHECKING:
    from pipeline.domain.measurementset import MeasurementSet
    from pipeline.hif.tasks.gaincal.common import GaincalResults
    from pipeline.hif.tasks.polcal.polcalworker import PolcalWorkerResults
    from pipeline.hifa.tasks.importdata.almaimportdata import ALMAImportDataResults

LOG = infrastructure.logging.get_logger(__name__)

__all__ = [
    'score_bands',
    'score_combine_spwmapping',
    'score_decoherence_assessment',
    'score_derived_fluxes_snr',
    'score_diffgaincal_combine',
    'score_diffgaincal_residuals',
    'score_fluxcsv',
    'score_fluxservice',
    'score_fluxservicemessages',
    'score_fluxservicestatuscodes',
    'score_gfluxscale_k_spw',
    'score_lowtrans_flagcmds',
    'score_missing_bandpass_snrs',
    'score_missing_derived_fluxes',
    'score_missing_phase_snrs',
    'score_missing_phaseup_snrs',
    'score_number_antenna_offsets',
    'score_observing_modes',
    'score_phaseup_mapping_fraction',
    'score_phaseup_spw_median_snr_for_cal',
    'score_phaseup_spw_median_snr_for_check',
    'score_polcal_gain_ratio',
    'score_polcal_gain_ratio_rms',
    'score_polcal_leakage',
    'score_polcal_residual_pol',
    'score_polcal_results',
    'score_polintents',
    'score_poor_bandpass_solutions',
    'score_poor_phase_snrs',
    'score_poor_phaseup_solutions',
    'score_refspw_mapping_fraction',
    'score_samecalobjects',
    'score_separation_angles',
    'score_tsysflagcontamination_contamination_flagged',
    'score_tsysflagcontamination_external_heuristic',
    'score_wvrgcal',
]


@log_qa
def score_observing_modes(mses: list[MeasurementSet]) -> list[pqa.QAScore]:
    """This QA heuristic evaluates a list of measurement sets, creating a QA score
    for each MS, and returning the aggregate list of QA scores for all MSes.
    Each MS is scored based on consistency checks between their registered
    Observing Mode(s) and e.g. the presence of differential gain SpWs / fields.

    Args:
        mses: list of measurement sets to score.

    Returns:
        List of QA scores.
    """
    # Create separate score for each MS.
    scores = []
    for ms in mses:
        # If the Observing Modes include "band to band", perform a few validity
        # checks w.r.t. the presence of DIFFGAIN* fields and diffgain SpW setup:
        if 'BandToBand Interferometry' in ms.observing_modes:
            if ms.get_diffgain_mode() != 'B2B':
                score = 0.0
                shortmsg = 'Incorrect Observing Mode'
                longmsg = (
                    f'Incorrect BandToBand Observing Mode, {ms.basename} does not contain a DIFFGAIN* intent'
                    f' and/or SpW setup consistent with band-to-band.'
                )
            elif len(ms.get_fields(intent='DIFFGAINREF,DIFFGAINSRC')) > 1:
                score = 0.0
                shortmsg = 'Too many DIFFGAIN* fields'
                longmsg = f'Unable to process BandToBand dataset {ms.basename}, found more than 1 DIFFGAIN* field'
            else:
                score = 0.9
                shortmsg = 'BandToBand mode used'
                longmsg = f'BandToBand mode used in {ms.basename}'

        # If the Observing Modes do not include "band to band", but the MS
        # contains a DIFFGAIN* intent and a SpW setup consistent with
        # band-to-band, then lower the score.
        elif 'BandToBand Interferometry' not in ms.observing_modes and ms.get_diffgain_mode() == 'B2B':
            score = 0.0
            shortmsg = 'Incorrect Observing Mode'
            longmsg = f'Incorrect Observing Mode, unexpectedly found a BandToBand DIFFGAIN* intent in {ms.basename}'

        # If the Observing Modes include "bandwidth switching", then lower the
        # score, since processing these data has not yet been validated.
        elif 'BandwidthSwitching Interferometry' in ms.observing_modes:
            score = 0.0
            shortmsg = 'BandwidthSwitching mode used'
            longmsg = f'BandwidthSwitching mode used in {ms.basename}'

        # If all validity checks are passed, score the MS as ok.
        else:
            score = 1.0
            shortmsg = 'Observing mode(s) ok.'
            longmsg = f'Observing mode(s) ok for {ms.basename}'

        # Append score for current MS.
        origin = pqa.QAOrigin(
            metric_name='score_observing_modes',
            metric_score=score,
            metric_units='MS score based on the observing modes',
        )
        scores.append(pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin))

    return scores


@log_qa
def score_diffgaincal_combine(vis: str, combine: str, qa_message: str, phaseup_type: str) -> pqa.QAScore:
    """Compute QA score based on whether the phase solution gaintable, computed as
    part of the hifa_diffgaincal stage, used spectral window combination, and
    whether any SpWs were missing (in case of no SpW combination).

    Args:
        vis: Name of measurement set to score.
        combine: combine parameter used in diffgain gaincal.
        qa_message: String representing QA message derived during task, included
            when no SpW combination is used (presumably forced by user) even
            though there were indicators that would have triggered SpW
            combination in automatic mode.
        phaseup_type: String representing the type of diffgain phase-up.

    Returns:
        QA score.
    """
    # If SpW combination was used, turn this into a blue QA score.
    if 'spw' in combine:
        score = rendererutils.SCORE_THRESHOLD_SUBOPTIMAL
        shortmsg = 'SpW combination used.'
        longmsg = f'{vis}: Spectral window combination used for B2B {phaseup_type} to improve phase-up solution SNR.'
    # If no SpW combination was used and a SpW is missing, then turn this into a
    # warning QA score.
    elif qa_message:
        score = rendererutils.SCORE_THRESHOLD_WARNING
        shortmsg = 'SpWs missing or heavily flagged.'
        longmsg = f'{vis}: No spectral window combination used for diffgain {phaseup_type} solution but {qa_message}.'
    # Otherwise, no missing SpWs or SpW combination, so return good score of 1.
    else:
        score = 1.0
        shortmsg = 'No SpW combination used.'
        longmsg = f'{vis}: No spectral window combination used for diffgain {phaseup_type} solution.'

    origin = pqa.QAOrigin(
        metric_name='score_diffgaincal_combine',
        metric_score=score,
        metric_units='Score based on whether diffgain used combine',
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_diffgaincal_residuals(residuals_info: dict, score_type: str) -> pqa.QAScore:
    """Compute QA score for diffgain residual phase offsets for given score type
    based on pre-computed statistics provided in residual_info dictionary.

    The premise is:
        - mean should be around 0.
        - no outlier values above set limits.
        - RMS at set limits.

    Args:
        residuals_info: Dictionary containing info on diffgain residual phase.
        score_type: Type of statistic to compute QA score for. Valid options:

            RESIDUAL:
            - 'offsets': use mean.
            - 'rms': use RMS
            - 'outliers': use maximum (per antenna)

    Returns:
        QA score.
    """

    def get_expanded_message(dict_use: dict) -> str:
        """Generate expanded QA message for selection of residuals dictionary."""
        # Group antennas by (spw, corr).
        spw_corr_to_ants = collections.defaultdict(set)
        for (spw, corr, ant, _), _ in dict_use.items():
            spw_corr_to_ants[(str(spw), str(corr))].add(str(ant))

        # Group (spw, corr) pairs by shared antenna sets.
        antset_to_spw_corr = collections.defaultdict(list)
        for (spw, corr), ants in spw_corr_to_ants.items():
            key = frozenset(ants)
            antset_to_spw_corr[key].append((spw, corr))

        # Build the full message.
        full_msg = []
        for antset, spw_corr_list in antset_to_spw_corr.items():
            spws = sorted({spw for spw, _ in spw_corr_list})
            corrs = sorted({corr for _, corr in spw_corr_list})

            spw_msg = 'all SpWs' if spws == ['all'] else f'SpW {",".join(spws)}'
            ant_msg = 'all antennas' if antset == {'all'} else f'antenna(s) {",".join(sorted(antset))}'
            corr_msg = f'corr {",".join(corrs)}'

            full_msg.append(f' {ant_msg}, in {spw_msg} {corr_msg}')

        return ','.join(full_msg)

    ms_name = residuals_info['ms_name']

    # Use a message phrase based on score type.
    # In the future, a b2b offset score will be added with a different `messph`
    messph = 'phase difference for residual phase'

    # If the diffgain residual phase offsets caltable had overall low SNR, then
    # return a suboptimal (blue) score without scoring variability or outliers.
    if residuals_info['low_snr']:
        score = rendererutils.SCORE_THRESHOLD_SUBOPTIMAL
        shortmsg = f'Low SNR in diffgaincal {messph} {score_type}'
        longmsg = (
            f'Low SNR in diffgaincal {messph} {score_type} for {ms_name}: not scoring based on variability or outliers.'
        )
    else:
        # Get info from residuals statistics dict.
        intent = residuals_info['intent']
        field = residuals_info['field']
        data = residuals_info['data']

        # Convert score type to what statistic to score.
        type_to_param = {
            'offsets': 'mean',
            'rms': 'rms',
            'outliers': 'max',
        }
        param = type_to_param[score_type]

        # Identify where the residual phase statistic is poor, elevated, or
        # good, using pre-defined thresholds.
        thresholds = {'good': 30.0, 'elevated': 50.0, 'poor': 70.0}
        good = {k: v for k, v in data.items() if param in k and thresholds['good'] < v <= thresholds['elevated']}
        elevated = {k: v for k, v in data.items() if param in k and thresholds['elevated'] < v <= thresholds['poor']}
        poor = {k: v for k, v in data.items() if param in k and v > thresholds['poor']}

        # Poor phase statistics are scored as a yellow warning.
        if poor:
            score = rendererutils.SCORE_THRESHOLD_WARNING
            shortmsg = f'High Diffgaincal {messph} {score_type}'
            longmsg = (
                f'For {ms_name}, field={field} intent={intent} has high {messph} {score_type} >70 deg for'
                f' {get_expanded_message(poor)}.'
            )
        # Elevated phase statistics are scored as the lowest blue score.
        elif elevated:
            score = rendererutils.SCORE_THRESHOLD_WARNING + 0.01  # lowest blue score
            shortmsg = f'Elevated Diffgaincal {messph} {score_type}'
            longmsg = (
                f'For {ms_name}, field={field} intent={intent} has elevated {messph} {score_type} between'
                f' 50-70 deg for {get_expanded_message(elevated)}.'
            )
        # Good phase statistics are scored as a blue suboptimal score.
        elif good:
            score = rendererutils.SCORE_THRESHOLD_SUBOPTIMAL
            shortmsg = f'Good Diffgaincal {messph} {score_type}'
            longmsg = f'For {ms_name}, field={field} intent={intent} has good {messph} {score_type} between 30-50 deg.'
        # Phase statistics better than "good" are excellent with green score of 1.
        else:
            score = 1.0
            shortmsg = f'Excellent Diffgaincal {messph} {score_type}'
            longmsg = f'For {ms_name}, field={field} intent={intent} has excellent {messph} {score_type} <30 deg.'

    # Specify score type. In the future, a b2b offset score with a different
    # `originmess` will be added
    originmess = 'residual'
    origin = pqa.QAOrigin(
        metric_name=f'score_diffgaincal_{originmess}',
        metric_score=score,
        metric_units=f'Score based on diffgain {originmess} analysis',
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_bands(mses):
    """Score a MeasurementSet object based on the presence of
    ALMA bands with calibration issues.
    """
    # ALMA receiver bands. Warnings will be raised for any
    # measurement sets containing the following bands.
    score = 1.0
    score_map = {'9': -1.0, '10': -1.0}

    unsupported = set(score_map.keys())

    num_mses = len(mses)
    all_ok = True
    complaints = []

    # analyse each MS
    for ms in mses:
        msbands = []
        for spw in ms.get_spectral_windows(science_windows_only=True):
            bandnum = spw.band.split(' ')[2]
            msbands.append(bandnum)
        msbands = set(msbands)
        overlap = unsupported.intersection(msbands)
        if not overlap:
            continue
        all_ok = False
        for m in overlap:
            score += score_map[m] / num_mses
        longmsg = '%s contains band %s data' % (ms.basename, utils.commafy(overlap, False))
        complaints.append(longmsg)

    if all_ok:
        longmsg = 'No high frequency %s band data were found in %s.' % (
            list(unsupported),
            utils.commafy([ms.basename for ms in mses], False),
        )
        shortmsg = 'No high frequency band data found'
    else:
        longmsg = '%s.' % utils.commafy(complaints, False)
        shortmsg = 'High frequency band data found'

    origin = pqa.QAOrigin(
        metric_name='score_bands', metric_score=score, metric_units='MS score based on presence of high-frequency data'
    )

    # Make score linear
    return pqa.QAScore(
        max(rendererutils.SCORE_THRESHOLD_SUBOPTIMAL, score), longmsg=longmsg, shortmsg=shortmsg, origin=origin
    )


@log_qa
def score_polintents(recipe_name: str, mses: list[MeasurementSet]) -> list[pqa.QAScore]:
    """Score a MeasurementSet object based on the presence of
    polarization intents.
    """
    pol_intents = {'POLARIZATION', 'POLANGLE', 'POLLEAKAGE'}
    # these recipes are allowed to process polarisation data
    pol_recipes = {'hifa_polcal', 'hifa_polcalimage', 'hifa_polcal_renorm', 'hifa_polcalimage_renorm'}

    # Sort to ensure presentation consistency
    mses = sorted(mses, key=lambda ms: ms.basename)

    # are polarisation intents expected? true if pol recipe, false if not
    pol_intents_expected = recipe_name in pol_recipes

    # holds the final list of QA scores
    scores: list[pqa.QAScore] = []

    # Spec from PIPE-606:
    #
    # Currently, hifa_importdata sets the score of that stage to 0 if a
    # polarization calibrator is found (in qa/scorecalculator.py). This score
    # should now become 1 if one of these recipes is being run, or 0.5 if any
    # other recipe is being run.

    # analyse each MS, recording an accordion warning if there's an unexpected
    # pol calibrator

    if pol_intents_expected:
        pol_intents_present = any([pol_intents.intersection(ms.intents) for ms in mses])

        ms_names = {ms.basename for ms in mses}
        mses_for_msg = utils.commafy(sorted(ms_names), False)

        # and an 'all OK' accordion message if pol scans were expected and found
        if pol_intents_present:
            longmsg = f'Polarization calibrations expected and found: {mses_for_msg}'
            shortmsg = 'Polarization calibrators'
            origin = pqa.QAOrigin(
                metric_name='score_polintents',
                metric_score=1.0,
                metric_units='MS score based on presence of polarisation data',
            )
            score = pqa.QAScore(
                1.0,
                longmsg=longmsg,
                shortmsg=shortmsg,
                origin=origin,
                weblog_location=pqa.WebLogLocation.ACCORDION,
                applies_to=pqa.TargetDataSelection(vis=ms_names),
            )
            scores.append(score)

        # and complain with a banner message if they weren't. Perhaps this
        # should be part of score_missing_intents?
        else:
            longmsg = f'Expected polarization calibrations not found in {mses_for_msg}'
            shortmsg = 'Polarization calibrators'
            origin = pqa.QAOrigin(
                metric_name='score_polintents',
                metric_score=0.5,
                metric_units='MS score based on presence of polarisation data',
            )
            score = pqa.QAScore(
                0.5,
                longmsg=longmsg,
                shortmsg=shortmsg,
                origin=origin,
                weblog_location=pqa.WebLogLocation.BANNER,
                applies_to=pqa.TargetDataSelection(vis=ms_names),
            )
            scores.append(score)

        return scores

    # so, pol data not expected. Find any problem scans and record an accordion warning
    for ms in mses:
        pol_intents_in_ms = sorted(pol_intents.intersection(ms.intents))

        if pol_intents_in_ms:
            longmsg = f'{ms.basename} contains polarization calibrations: {utils.commafy(pol_intents_in_ms, False)}'
            shortmsg = 'Polarization intents'
            origin = pqa.QAOrigin(
                metric_name='score_polintents',
                metric_score=0.5,
                metric_units='MS score based on presence of polarisation data',
            )
            score = pqa.QAScore(
                0.5,
                longmsg=longmsg,
                shortmsg=shortmsg,
                origin=origin,
                weblog_location=pqa.WebLogLocation.ACCORDION,
                applies_to=pqa.TargetDataSelection(vis={ms.basename}),
            )
            scores.append(score)

    # if there are accordion warnings, summarise them in a banner warning too
    if scores:
        affected_mses = {v for score in scores for v in score.applies_to.vis}
        longmsg = f'Unexpected polarization calibrations in {utils.commafy(affected_mses, False)}'
        shortmsg = 'Polarization intents'
        origin = pqa.QAOrigin(
            metric_name='score_polintents',
            metric_score=0.5,
            metric_units='MS score based on presence of polarisation data',
        )
        score = pqa.QAScore(
            0.5,
            longmsg=longmsg,
            shortmsg=shortmsg,
            origin=origin,
            weblog_location=pqa.WebLogLocation.BANNER,
            applies_to=pqa.TargetDataSelection(vis=affected_mses),
        )
        scores.append(score)

    # Add an 'all OK' accordion message if no unexpected intents detected
    if not scores and not pol_intents_expected:
        ms_names = {ms.basename for ms in mses}
        longmsg = f'No polarization calibrations found: {utils.commafy(sorted(ms_names), False)}'
        shortmsg = 'No polarization calibrators'
        origin = pqa.QAOrigin(
            metric_name='score_polintents',
            metric_score=1.0,
            metric_units='MS score based on presence of polarisation data',
        )
        score = pqa.QAScore(
            1.0,
            longmsg=longmsg,
            shortmsg=shortmsg,
            origin=origin,
            weblog_location=pqa.WebLogLocation.ACCORDION,
            applies_to=pqa.TargetDataSelection(vis=ms_names),
        )
        scores.append(score)

    return scores


@log_qa
def score_samecalobjects(recipe_name: str, mses: list[MeasurementSet]) -> list[pqa.QAScore]:
    """Check if BP/Phcal/Ampcal are all the same object and score appropriately"""
    alma_recipes = {'hifa_cal', 'hifa_calimage', 'hifa_calsurvey', 'hifa"image', 'hifa_polcal', 'hifa_polcalimage'}

    # Sort to ensure presentation consistency
    mses = sorted(mses, key=lambda ms: ms.basename)

    # We are just considering ALMA recipes.   True if an ALMA recipe, false if not
    alma_recipes_expected = recipe_name in alma_recipes

    # holds the final list of QA scores
    scores: list[pqa.QAScore] = []

    if alma_recipes_expected:
        for ms in mses:
            # Get list of calibrator names
            calfields = ms.get_fields(intent='AMPLITUDE,PHASE,BANDPASS')
            calfieldnames = [field.name for field in calfields]

            # Check for any duplicate names in the list of calibrator field names
            # samefieldnames = all(element == calfieldnames[0] for element in calfieldnames)
            samefieldnames = any(calfieldnames.count(x) > 1 for x in calfieldnames)
            if samefieldnames:
                scorevalue = 0.3
                msg = 'Some calibrators are the same object.'
            else:
                scorevalue = 1.0
                msg = 'Calibrators are different objects.'

            origin = pqa.QAOrigin(
                metric_name='score_samecalobjects', metric_score=scorevalue, metric_units='samecalobjects'
            )

            score = pqa.QAScore(scorevalue, longmsg=msg, shortmsg=msg, origin=origin)

            scores.append(score)

    return scores


@log_qa
def score_lowtrans_flagcmds(ms, result):
    """Get a score for data flagged by the low transmission agent.

    Heuristic from PIPE-624: search for SpW(s) flagged for low transmission,
    and set score to:
    * 1 if no SpWs are flagged.
    * red warning threshold if the representative SpW is flagged, or otherwise,
    * blue suboptimal threshold if any non-representative SpW is flagged.
    """
    # Search in flag commands for SpW(s) flagged for low transmission.
    spws = []
    flagcmds = [f for f in result.flagcmds() if 'low_transmission' in f]
    for flagcmd in flagcmds:
        match = re.search(r"spw='(\d*)'", flagcmd)
        if match:
            spws.append(int(match.group(1)))

    # If successful in finding SpWs that were flagged for low transmission,
    # then create a score that depends on whether the representative SpW was
    # among those flagged.
    if spws:
        # Get representative SpW for MS.
        _, rspw = ms.get_representative_source_spw()
        if rspw in spws:
            score = rendererutils.SCORE_THRESHOLD_ERROR
            longmsg = f'Representative SpW {rspw} flagged for low transmission'
            shortmsg = 'Representative SpW flagged for low transmission'
        else:
            score = rendererutils.SCORE_THRESHOLD_SUBOPTIMAL
            longmsg = f'Non-representative SpW(s) {", ".join(str(s) for s in spws)} flagged for low transmission'
            shortmsg = 'Non-representative SpW(s) flagged for low transmission'
    else:
        score = 1.0
        longmsg = 'No SpW(s) flagged for low transmission'
        shortmsg = 'No SpW(s) flagged for low transmission'

    origin = pqa.QAOrigin(
        metric_name='score_lowtrans', metric_score=score, metric_units='SpW(s) flagged by low transmission agent.'
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_wvrgcal(ms_name, dataresult):

    wvr_score = dataresult.qa_wvr.overall_score
    score = wvr_score.copy()

    # create lists for disc, rms, and flagged antennas checks
    disc_list = []
    rms_list = []
    flagant_list = []
    for WVRinfo in dataresult.wvr_infos:
        disc_list.append(WVRinfo.disc.value)
        rms_list.append(WVRinfo.rms.value)
        if WVRinfo.flag:
            flagant_list.append(WVRinfo.antenna)

    # limits for disc and rms triggers -
    # same as hard coded in wvrg_qa to make the remcloud
    # trigger result object boolean
    disc_max = 500  # in um
    rms_max = 500  # in um
    # subset lists for ants exceeding the limits
    disc_limit = [dval for dval in disc_list if dval > disc_max]
    rms_limit = [rval for rval in rms_list if rval > rms_max]

    qa_messages = []

    # check the booleans that pass important information
    if dataresult.PHnoisy:
        qa_messages.append('Only Bandpass used for WVR improvement assessment')
    if dataresult.suggest_remcloud:
        qa_messages.append('Remcloud suggested')

    if score > 1.0:
        # if nothing else score passes will be >1.0
        # truncate to 1.0 - ratio_score now holding improvement
        score = 1.0
        if len(flagant_list) > 0 or len(disc_limit) > 0 or len(rms_limit) > 0 or dataresult.PHnoisy is True:
            score = 0.9  # i.e. to blue as a maximum value
            # now adjust 0.1 per bad entry
            reduceBy = len(flagant_list) * 0.1
            reduceBy += len(disc_limit) * 0.1
            reduceBy += len(rms_limit) * 0.1
            score = score - reduceBy
            # Crude check for the message - check if flag or disc/rms
            if len(flagant_list) > 0:
                qa_messages.append('Flagged antenna(s)')
            if len(disc_limit) > 0:
                qa_messages.append('Elevated disc value(s)')
            if len(rms_limit) > 0:
                qa_messages.append('Elevated rms value(s)')
            # before making the score check if noisy BP was triggered
            if dataresult.BPnoisy:
                score = 0.66  # downgrade to yellow to trigger a warning
                qa_messages.append('Atmospheric phases appear unstable')
                if len(flagant_list) > 0 or len(disc_limit) > 0 or len(rms_limit) > 0:
                    # inherit previous reduceBy values
                    score = score - reduceBy
                # new linear score for yellow truncation
                score = linear_score(score, 0.0, 0.66, 0.34, 0.66)
            else:
                score = linear_score(score, 0.0, 0.9, 0.67, 0.9)
                # i.e. inputs will be truncated to between 0.0 and 0.9, linfited to be then between 0.67 and 0.9 - blue

    # now for scores < 1.0
    elif score < 1.0:
        qa_messages.append('No WVR improvement')  # PIPE-1837 message changed, now below

        # presuming disc list and rms list are all filled
        if np.median(disc_list) > disc_max or np.median(rms_list) > rms_max:
            score = 0.33
            qa_messages.append('Elevated disc/rms value(s) - Check atmospheric phase stability')
            if len(flagant_list) > 0:
                reduceBy = len(disc_limit) * 0.1
                qa_messages.append('Flagged antenna(s)')
                score = score - reduceBy
            score = linear_score(score, 0.0, 0.33, 0.0, 0.33)
            # i.e. inputs will be truncated to between 0.0 and 0.33, linfited to be then between 0.0 and 0.33 RED

        else:
            score = 0.66
            reduceBy = 0.0  # initiate due to PIPE-1837 if/else loops
            if len(flagant_list) > 0 or len(disc_limit) > 0 or len(rms_limit) > 0:
                # now adjust 0.1 per bad entry
                reduceBy += len(flagant_list) * 0.1
                reduceBy += len(disc_limit) * 0.1
                reduceBy += len(rms_limit) * 0.1
                score = score - reduceBy
                # Crude check for the message - check if flag or disc/rms
                if len(flagant_list) > 0:
                    qa_messages.append('Flagged antenna(s)')
                if len(disc_limit) > 0:
                    qa_messages.append('Elevated disc value(s)')
                if len(rms_limit) > 0:
                    qa_messages.append('Elevated rms value(s)')

            # PIPE-1837 before final yellow scoring we assess if the
            # phase rms from wvrg_qa was 'good' i.e. <1 radian
            # but only when there are no other WVR soln issues, i.e.
            # disc or rms are below the fixed limits - note
            # message changes explicitly if only BP is 'good' or both BP and Phase
            # technically the phase can be noisy due to SNR, not atmospheric variations
            if len(disc_limit) == 0 and len(rms_limit) == 0:
                # here we would check if initscore > 0.X: "limit'
                if dataresult.BPgood:
                    qa_messages.append(
                        'Bandpass '
                        + ('and Phase ' if dataresult.PHgood else '')
                        + 'calibrator atmospheric phase stability appears to be good'
                    )
                    score = 0.9 - reduceBy  # still account for flagged antennas
                    score = linear_score(score, 0.0, 0.9, 0.67, 0.9)
                else:
                    # we don't modify from the previous assessment - i.e. data seem ok, no poor rms or disc,
                    # but the phase RMS is not explicitly reported as good - I suspect some LB and HF might come here
                    qa_messages.append('Check atmospheric phase stability')
                    # if disc and rms didn't trigger but phase stability not reported as good - still yellow
                    score = linear_score(score, 0.0, 0.66, 0.34, 0.66)

            # Otherwise now we are back to yellow when disc or rms also triggered on any ant and append message now
            else:
                qa_messages.append('Check atmospheric phase stability')
                score = linear_score(score, 0.0, 0.66, 0.34, 0.66)
                # i.e. inputs will be truncated to between 0.0 and 0.66, linfited to be then between 0.34 and 0.66

    # join the short messages for the QA score (are these stored?? )
    qa_mesg = ' - '.join(qa_messages)

    if qa_mesg:
        longmsg = 'phase RMS improvement was %0.2f for %s - %s' % (wvr_score, ms_name, qa_mesg)
    else:
        longmsg = 'phase RMS improvement was %0.2f for %s' % (wvr_score, ms_name)

    # should be made always
    shortmsg = '%0.2fx improvement' % wvr_score

    origin = pqa.QAOrigin(
        metric_name='score_wvrgcal',
        metric_score=wvr_score,
        metric_units='Phase RMS improvement after applying WVR correction',
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=os.path.basename(ms_name), origin=origin)


@log_qa
def score_number_antenna_offsets(ms, offsets):
    """Score is 1.0 if no antenna needed a position offset correction, and
    set to the "suboptimal" threshold if at least one antenna needed a
    correction.
    """
    nant_with_offsets = len(offsets) // 3

    if nant_with_offsets == 0:
        score = 1.0
        longmsg = 'No antenna position offsets for %s ' % ms.basename
        shortmsg = 'No antenna position offsets'
    else:
        # CAS-8877: if at least 1 antenna needed correction, then set the score
        # to the "suboptimal" threshold.
        score = rendererutils.SCORE_THRESHOLD_SUBOPTIMAL
        longmsg = '%d nonzero antenna position offsets for %s ' % (nant_with_offsets, ms.basename)
        shortmsg = 'Nonzero antenna position offsets'

    origin = pqa.QAOrigin(
        metric_name='score_number_antenna_offsets',
        metric_score=nant_with_offsets,
        metric_units='Number of antennas requiring position offset correction',
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_missing_derived_fluxes(ms, reqfields, reqintents, measurements):
    """Score is equal to the ratio of actual flux
    measurement to expected flux measurements
    """
    # Expected fields
    scifields = {field for field in ms.get_fields(reqfields, intent=reqintents)}

    # Expected science windows
    scispws = ms.get_spectral_windows(science_windows_only=True)

    # Requested intents as set.
    reqintents = set(reqintents.split(','))

    # Loop over the expected fields
    nexpected = 0
    for scifield in scifields:
        # PIPE-2458: flux measurements are only expected for science SpWs that
        # are valid for this field and that cover one or more of the requested
        # intents. This will filter out cases where a SpW is a science SpW
        # but not used for one of the requested intents for this field.
        scifield_req_intents = scifield.intents.intersection(reqintents)
        scifield_valid_spws = {
            spw for spw in scifield.valid_spws if spw in scispws and spw.intents.intersection(scifield_req_intents)
        }
        nexpected += len(scifield_valid_spws)

    # Loop over measurements
    nmeasured = 0
    for key, value in measurements.items():
        # Loop over the flux measurements
        for flux in value:
            fluxjy = getattr(flux, 'I').to_units(measures.FluxDensityUnits.JANSKY)
            uncjy = getattr(flux.uncertainty, 'I').to_units(measures.FluxDensityUnits.JANSKY)
            if fluxjy <= 0.0 or uncjy <= 0.0:
                continue
            nmeasured += 1

    # Compute score
    if nexpected == 0:
        score = 0.0
        longmsg = 'No secondary calibrators for %s ' % ms.basename
        shortmsg = 'No secondary calibrators'
    elif nmeasured == 0:
        score = 0.0
        longmsg = 'No derived fluxes for %s ' % ms.basename
        shortmsg = 'No derived fluxes'
    elif nexpected == nmeasured:
        score = 1.0
        longmsg = 'All expected derived fluxes present for %s ' % ms.basename
        shortmsg = 'All expected derived fluxes present'
    elif nmeasured < nexpected:
        score = float(nmeasured) / float(nexpected)
        longmsg = 'Missing derived fluxes for %s %d/%d' % (ms.basename, nmeasured, nexpected)
        shortmsg = 'Missing derived fluxes'
    else:
        score = 0.0
        longmsg = 'Extra derived fluxes for %s %d/%d' % (ms.basename, nmeasured, nexpected)
        shortmsg = 'Extra derived fluxes'

    origin = pqa.QAOrigin(
        metric_name='score_missing_derived_fluxes',
        metric_score=score,
        metric_units='Ratio of number of flux measurements to number expected',
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_refspw_mapping_fraction(ms, ref_spwmap):
    """Compute the fraction of science spws that have not been
    mapped to other windows.
    """
    if ref_spwmap == [-1]:
        score = 1.0
        longmsg = 'No mapped science spws for %s ' % ms.basename
        shortmsg = 'No mapped science spws'

        origin = pqa.QAOrigin(
            metric_name='score_refspw_mapping_fraction', metric_score=0, metric_units='Number of unmapped science spws'
        )
    else:
        # Expected science windows
        scispws = {spw.id for spw in ms.get_spectral_windows(science_windows_only=True)}
        nexpected = len(scispws)

        nunmapped = 0
        for spwid in scispws:
            if spwid == ref_spwmap[spwid]:
                nunmapped += 1

        if nunmapped >= nexpected:
            score = 1.0
            longmsg = 'No mapped science spws for %s ' % ms.basename
            shortmsg = 'No mapped science spws'
        else:
            # Replace the previous score with a warning
            score = rendererutils.SCORE_THRESHOLD_WARNING
            longmsg = 'There are %d mapped science spws for %s ' % (nexpected - nunmapped, ms.basename)
            shortmsg = 'There are mapped science spws'

        origin = pqa.QAOrigin(
            metric_name='score_refspw_mapping_fraction',
            metric_score=nunmapped,
            metric_units='Number of unmapped science spws',
        )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_combine_spwmapping(ms, intent, field, spwmapping):
    """Evaluate whether or not a spw mapping is using combine.
    If not, then set score to 1. If so, then set score to the sub-optimal
    threshold (for blue info message).
    """
    if spwmapping.combine:
        score = rendererutils.SCORE_THRESHOLD_SUBOPTIMAL
        longmsg = f'Using combined spw mapping for {ms.basename}, intent={intent}, field={field}'
        shortmsg = 'Using combined spw mapping'
    else:
        score = 1.0
        longmsg = f'No combined spw mapping for {ms.basename}, intent={intent}, field={field}'
        shortmsg = 'No combined spw mapping'

    origin = pqa.QAOrigin(
        metric_name='score_check_phaseup_combine_mapping',
        metric_score=spwmapping.combine,
        metric_units='Using combined spw mapping',
    )

    applies_to = pqa.TargetDataSelection(vis={ms.basename}, intent={intent}, field={field})

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin, applies_to=applies_to)


@log_qa
def score_phaseup_mapping_fraction(ms, intent, field, spwmapping):
    """Compute the fraction of science spws that have not been
    mapped to other probably wider windows.
    """
    if not spwmapping.spwmap:
        nunmapped = len([spw for spw in ms.get_spectral_windows(science_windows_only=True)])
        score = 1.0
        longmsg = f'No spw mapping for {ms.basename}, intent={intent}, field={field}'
        shortmsg = 'No spw mapping'
    elif spwmapping.combine:
        nunmapped = 0
        score = rendererutils.SCORE_THRESHOLD_WARNING
        longmsg = f'Combined spw mapping for {ms.basename}, intent={intent}, field={field}'
        shortmsg = 'Combined spw mapping'
    else:
        # Expected science windows
        scispws = [spw for spw in ms.get_spectral_windows(science_windows_only=True)]
        scispwids = [spw.id for spw in ms.get_spectral_windows(science_windows_only=True)]
        nexpected = len(scispwids)

        nunmapped = 0
        samesideband = True
        for spwid, scispw in zip(scispwids, scispws):
            if spwid == spwmapping.spwmap[spwid]:
                nunmapped += 1
            else:
                if scispw.sideband != ms.get_spectral_window(spwmapping.spwmap[spwid]).sideband:
                    samesideband = False

        if nunmapped >= nexpected:
            score = 1.0
            longmsg = f'No spw mapping for {ms.basename}, intent={intent}, field={field}'
            shortmsg = 'No spw mapping'
        else:
            # Replace the previous score with a warning
            if samesideband is True:
                score = rendererutils.SCORE_THRESHOLD_SUBOPTIMAL
                longmsg = f'Spw mapping within sidebands for {ms.basename}, intent={intent}, field={field}'
                shortmsg = 'Spw mapping within sidebands'
            else:
                score = rendererutils.SCORE_THRESHOLD_WARNING
                longmsg = f'Spw mapping across sidebands required for {ms.basename}, intent={intent}, field={field}'
                shortmsg = 'Spw mapping across sidebands'

    origin = pqa.QAOrigin(
        metric_name='score_phaseup_mapping_fraction',
        metric_score=nunmapped,
        metric_units='Number of unmapped science spws',
    )

    applies_to = pqa.TargetDataSelection(vis={ms.basename}, intent={intent}, field={field})

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin, applies_to=applies_to)


@log_qa
def score_phaseup_spw_median_snr_for_cal(ms, field, spw, intent, median_snr, snr_threshold):
    """Score the median achieved SNR for a given calibrator field and SpW.
    Introduced for hifa_spwphaseup (PIPE-665, PIPE-2499).
    """
    if median_snr <= 0.3 * snr_threshold:
        score = rendererutils.SCORE_THRESHOLD_ERROR
        shortmsg = 'Low median SNR'
        longmsg = (
            f'For {ms.basename}, field={field} (intent={intent}), SpW={spw}, the median achieved SNR'
            f' ({median_snr:.1f}) is <= 30% of the phase SNR threshold ({snr_threshold:.1f}).'
        )
    elif median_snr <= 0.5 * snr_threshold:
        score = rendererutils.SCORE_THRESHOLD_WARNING
        shortmsg = 'Low median SNR'
        longmsg = (
            f'For {ms.basename}, field={field} (intent={intent}), SpW={spw}, the median achieved SNR'
            f' ({median_snr:.1f}) is <= 50% of the phase SNR threshold ({snr_threshold:.1f}).'
        )
    elif median_snr <= 0.75 * snr_threshold:
        score = rendererutils.SCORE_THRESHOLD_SUBOPTIMAL
        shortmsg = 'Low median SNR'
        longmsg = (
            f'For {ms.basename}, field={field} (intent={intent}), SpW={spw}, the median achieved SNR'
            f' ({median_snr:.1f}) is <= 75% of the phase SNR threshold ({snr_threshold:.1f}).'
        )
    else:
        score = 1.0
        shortmsg = 'Median SNR is ok'
        longmsg = (
            f'For {ms.basename}, field={field} (intent={intent}), SpW={spw}, the median achieved SNR'
            f' ({median_snr:.1f}) is > 75% of the phase SNR threshold ({snr_threshold:.1f}).'
        )

    origin = pqa.QAOrigin(
        metric_name='score_phaseup_spw_median_snr_for_cal', metric_score=median_snr, metric_units='Median SNR'
    )

    applies_to = pqa.TargetDataSelection(vis={ms.basename}, field={field}, spw={spw}, intent={intent})

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin, applies_to=applies_to)


@log_qa
def score_phaseup_spw_median_snr_for_check(ms, field, spw, median_snr, snr_threshold):
    """Score the median achieved SNR for a given check source field and SpW.
    Introduced for hifa_spwphaseup (PIPE-665).
    """
    intent = 'CHECK'
    if median_snr <= 0.3 * snr_threshold:
        score = 0.7
        shortmsg = 'Low median SNR'
        longmsg = (
            f'For {ms.basename}, field={field} (intent={intent}), SpW={spw}, the median achieved SNR'
            f' ({median_snr:.1f}) is <= 30% of the phase SNR threshold ({snr_threshold:.1f}).'
        )
    elif median_snr <= 0.5 * snr_threshold:
        score = 0.8
        shortmsg = 'Low median SNR'
        longmsg = (
            f'For {ms.basename}, field={field} (intent={intent}), SpW={spw}, the median achieved SNR'
            f' ({median_snr:.1f}) is <= 50% of the phase SNR threshold ({snr_threshold:.1f}).'
        )
    elif median_snr <= 0.75 * snr_threshold:
        score = 0.9
        shortmsg = 'Low median SNR'
        longmsg = (
            f'For {ms.basename}, field={field} (intent={intent}), SpW={spw}, the median achieved SNR'
            f' ({median_snr:.1f}) is <= 75% of the phase SNR threshold ({snr_threshold:.1f}).'
        )
    else:
        score = 1.0
        shortmsg = 'Median SNR is ok'
        longmsg = (
            f'For {ms.basename}, field={field} (intent={intent}), SpW={spw}, the median achieved SNR'
            f' ({median_snr:.1f}) is > 75% of the phase SNR threshold ({snr_threshold:.1f}).'
        )

    origin = pqa.QAOrigin(
        metric_name='score_phaseup_spw_median_snr_for_check', metric_score=median_snr, metric_units='Median SNR'
    )

    applies_to = pqa.TargetDataSelection(vis={ms.basename}, field={field}, spw={spw}, intent={intent})

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin, applies_to=applies_to)


@log_qa
def score_decoherence_assessment(ms: MeasurementSet, phaserms_results, outlier_antennas: str):
    """Assess the cycle time phase RMS value, which is important as everything longer than a cycle time
    is corrected by phase referencing (in terms of atmospheric phase variations).

    Also checks the outlier antennas and the 80th percentile baseline with and without flagged antennas.
    """
    try:
        phasermscycle_p80: float = phaserms_results['phasermscycleP80']
        bl_p80: float = phaserms_results['blP80']
        bl_p80_orig: float = phaserms_results['blP80orig']

        initial_score = 1.0 - phasermscycle_p80 / 100.0
        RMSstring = str(round(phasermscycle_p80, 2))

        LOG.info(
            'For {0}, the Phase RMS calculated over the cycle time for the unflagged baselines longer than 80th percentile is {1} \
                    deg'.format(ms.basename, RMSstring)
        )

        # Stable Phases, < 30 deg phaseRMS
        if initial_score > 0.7:
            base_score = 1.0
            shortmsg = 'Excellent stability Phase RMS (<30deg).'
            longmsg = (
                'For {0}, excellent stability: The baseline-based median phase RMS for baselines longer than P80 is {1} \
                        deg over the cycle time.'.format(ms.basename, RMSstring)
            )

            # Check for problem antennas and update the score if needed.
            # these are outliers >100 deg, or those beyond "outlier_limit" in SSFherusitics (6 MAD)
            if len(outlier_antennas) > 0:
                base_score = 0.9

        elif initial_score > 0.5 and initial_score <= 0.7:
            # 30 to 50 deg phase RMS: not really a problem just informative
            # that the phase noise is elevated - no 'need' to look
            # as 50 deg phase RMS can still cause ~30% decoherence
            base_score = 0.9
            shortmsg = 'Stable conditions phase RMS (30-50deg).'
            longmsg = (
                'For {0}, good stability: The baseline-based median phase RMS for baselines longer than P80 is {1} \
                            deg over the cycle time.'.format(ms.basename, RMSstring)
            )

        # These are high phase noise -
        # outliers have already been clipped past 100 degrees
        # and those >4 MAD above the P80 phase RMS value
        # so, if we still get here, the phases were poor/v.bad - or there
        # were too many antennas classed as bad in the analysis function
        elif initial_score <= 0.5 and initial_score > 0.3:
            # 50 - 70 deg phase RMS, i.e. 30-50% lost due to decoherence
            # The initial score is representative
            base_score = initial_score
            shortmsg = 'Elevated Phase RMS (50-70deg) exceeds stable parameters.'
            longmsg = (
                'For {0}, elevated phase instability: The baseline-based median phase RMS for baselines longer than P80 is {1} \
                            deg over the cycle time. Some image artifacts/defects may occur.'.format(
                    ms.basename, RMSstring
                )
            )

        elif initial_score <= 0.3:
            if initial_score <= 0.0:
                base_score = 0.0
            else:
                base_score = initial_score

            shortmsg = 'High Phase RMS (>70deg) exceeds limit for poor stability'
            longmsg = (
                'For {0}, very poor phase stability: The baseline-based median phase RMS for baselines longer than P80 is {1} \
                        deg over the cycle time. Significant image artifacts/defects may be present.'.format(
                    ms.basename, RMSstring
                )
            )

        else:  # This should never happen
            base_score = 0.0
            shortmsg = 'The phase RMS could not be assessed.'
            longmsg = 'For {}, the spatial structure function could not be assessed'.format(ms)

        # Append antenna outlier information to longmsg if present
        if len(outlier_antennas) > 0:
            if len(outlier_antennas.split(',')) == 1:
                longmsg = '{0} {1} has higher phase RMS.'.format(longmsg, outlier_antennas)
            else:
                longmsg = '{0} {1} have higher phase RMS'.format(longmsg, outlier_antennas)

        # The P80 is shorter than the P80 of all data due to notable baseline flagging
        #       tbd but if the P80 is 10-15% lower than expected - i.e. can later impact QA2
        #       as the longer baselines have maybe been flagged out
        if bl_p80 < bl_p80_orig * 0.85:
            LOG.info(
                'P80 of unflagged data is more than 15% shorter than P80 of all baselines due to baseline and antennas flags'
            )
            if base_score == 1.0:
                base_score = 0.9
            longmsg = '{} P80 of unflagged data is more than 15% shorter than P80 of all baselines'.format(longmsg)

    except:
        # For any error in the above:
        base_score = 0.0
        phasermscycle_p80 = 0.0
        shortmsg = 'The phase RMS could not be assessed.'
        longmsg = 'For {}, the spatial structure function could not be assessed.'.format(ms.basename)
        LOG.error(traceback.format_exc())

    # Create metric origin
    phase_stability_origin = pqa.QAOrigin(
        metric_name='Phase stability', metric_score=phasermscycle_p80, metric_units='Degrees'
    )

    return pqa.QAScore(
        base_score,
        longmsg=longmsg,
        shortmsg=shortmsg,
        vis=ms.basename,
        origin=phase_stability_origin,
        weblog_location=pqa.WebLogLocation.ACCORDION,
    )


@log_qa
def score_missing_phaseup_snrs(ms, spwids, phsolints):
    """Score is the fraction of spws with phaseup SNR estimates"""
    # Compute the number of expected and missing SNR measurements
    nexpected = len(spwids)
    missing_spws = []
    for i in range(len(spwids)):
        if not phsolints[i]:
            missing_spws.append(spwids[i])
    nmissing = len(missing_spws)

    if nexpected <= 0:
        score = 0.0
        longmsg = 'No phaseup SNR estimates for %s ' % ms.basename
        shortmsg = 'No phaseup SNR estimates'
    elif nmissing <= 0:
        score = 1.0
        longmsg = 'No missing phaseup SNR estimates for %s ' % ms.basename
        shortmsg = 'No missing phaseup SNR estimates'
    else:
        score = float(nexpected - nmissing) / nexpected
        longmsg = 'Missing phaseup SNR estimates for spws %s in %s ' % (missing_spws, ms.basename)
        shortmsg = 'Missing phaseup SNR estimates'

    origin = pqa.QAOrigin(
        metric_name='score_missing_phaseup_snrs',
        metric_score=nmissing,
        metric_units='Number of spws with missing SNR measurements',
    )

    applies_to = pqa.TargetDataSelection(vis={ms.basename}, spw={spwid for spwid in spwids})

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin, applies_to=applies_to)


@log_qa
def score_poor_phaseup_solutions(ms, spwids, nphsolutions, min_nsolutions):
    """Score is the fraction of spws with poor phaseup solutions"""
    # Compute the number of expected and poor SNR measurements
    nexpected = len(spwids)
    poor_spws = []
    for i in range(len(spwids)):
        if not nphsolutions[i]:
            poor_spws.append(spwids[i])
        elif nphsolutions[i] < min_nsolutions:
            poor_spws.append(spwids[i])
    npoor = len(poor_spws)

    if nexpected <= 0:
        score = 0.0
        longmsg = 'No phaseup solutions for %s ' % ms.basename
        shortmsg = 'No phaseup solutions'
    elif npoor <= 0:
        score = 1.0
        longmsg = 'No poorly determined phaseup solutions for %s ' % ms.basename
        shortmsg = 'No poorly determined phaseup solutions'
    else:
        score = float(nexpected - npoor) / nexpected
        longmsg = 'Poorly determined phaseup solutions for spws %s in %s ' % (poor_spws, ms.basename)
        shortmsg = 'Poorly determined phaseup solutions'

    origin = pqa.QAOrigin(
        metric_name='score_poor_phaseup_solutions', metric_score=npoor, metric_units='Number of poor phaseup solutions'
    )

    applies_to = pqa.TargetDataSelection(vis={ms.basename}, spw={spwid for spwid in spwids})

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin, applies_to=applies_to)


@log_qa
def score_missing_bandpass_snrs(ms, spwids, bpsolints):
    """Score is the fraction of spws with bandpass SNR estimates"""
    # Compute the number of expected and missing SNR measurements
    nexpected = len(spwids)
    missing_spws = []
    for i in range(len(spwids)):
        if not bpsolints[i]:
            missing_spws.append(spwids[i])
    nmissing = len(missing_spws)

    if nexpected <= 0:
        score = 0.0
        longmsg = 'No bandpass SNR estimates for %s ' % ms.basename
        shortmsg = 'No bandpass SNR estimates'
    elif nmissing <= 0:
        score = 1.0
        longmsg = 'No missing bandpass SNR estimates for %s ' % ms.basename
        shortmsg = 'No missing bandpass SNR estimates'
    else:
        score = float(nexpected - nmissing) / nexpected
        longmsg = 'Missing bandpass SNR estimates for spws %s in%s ' % (missing_spws, ms.basename)
        shortmsg = 'Missing bandpass SNR estimates'

    origin = pqa.QAOrigin(
        metric_name='score_missing_bandpass_snrs',
        metric_score=nmissing,
        metric_units='Number of missing bandpass SNR estimates',
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_poor_bandpass_solutions(ms, spwids, nbpsolutions, min_nsolutions):
    """Score is the fraction of spws with poor bandpass solutions"""
    # Compute the number of expected and poor solutions
    nexpected = len(spwids)
    poor_spws = []
    for i in range(len(spwids)):
        if not nbpsolutions[i]:
            poor_spws.append(spwids[i])
        elif nbpsolutions[i] < min_nsolutions:
            poor_spws.append(spwids[i])
    npoor = len(poor_spws)

    if nexpected <= 0:
        score = 0.0
        longmsg = 'No bandpass solutions for %s ' % ms.basename
        shortmsg = 'No bandpass solutions'
    elif npoor <= 0:
        score = 1.0
        longmsg = 'No poorly determined bandpass solutions for %s ' % ms.basename
        shortmsg = 'No poorly determined bandpass solutions'
    else:
        score = float(nexpected - npoor) / nexpected
        longmsg = 'Poorly determined bandpass solutions for spws %s in %s ' % (poor_spws, ms.basename)
        shortmsg = 'Poorly determined bandpass solutions'

    origin = pqa.QAOrigin(
        metric_name='score_missing_bandpass_snrs', metric_score=npoor, metric_units='Number of poor bandpass solutions'
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_missing_phase_snrs(ms, spwids, snrs):
    """Score is the fraction of spws with SNR estimates"""
    # Compute the number of expected and missing SNR measurements
    nexpected = len(spwids)
    missing_spws = []
    for i in range(len(spwids)):
        if not snrs[i]:
            missing_spws.append(spwids[i])
    nmissing = len(missing_spws)

    if nexpected <= 0:
        score = 0.0
        longmsg = 'No gaincal SNR estimates for %s ' % ms.basename
        shortmsg = 'No gaincal SNR estimates'
    elif nmissing <= 0:
        score = 1.0
        longmsg = 'No missing gaincal SNR estimates for %s ' % ms.basename
        shortmsg = 'No missing gaincal SNR estimates'
    else:
        score = float(nexpected - nmissing) / nexpected
        longmsg = 'Missing gaincal SNR estimates for spws %s in %s ' % (missing_spws, ms.basename)
        shortmsg = 'Missing gaincal SNR estimates'

    origin = pqa.QAOrigin(
        metric_name='score_missing_phase_snrs',
        metric_score=nmissing,
        metric_units='Number of missing phase SNR estimates',
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_poor_phase_snrs(ms, spwids, minsnr, snrs):
    """Score is the fraction of spws with poor snr estimates"""
    # Compute the number of expected and poor solutions
    nexpected = len(spwids)
    poor_spws = []
    for i in range(len(spwids)):
        if not snrs[i]:
            poor_spws.append(spwids[i])
        elif snrs[i] < minsnr:
            poor_spws.append(spwids[i])
    npoor = len(poor_spws)

    if nexpected <= 0:
        score = 0.0
        longmsg = 'No gaincal SNR estimates for %s ' % ms.basename
        shortmsg = 'No gaincal SNR estimates'
    elif npoor <= 0:
        score = 1.0
        longmsg = 'No low gaincal SNR estimates for %s ' % ms.basename
        shortmsg = 'No low gaincal SNR estimates'
    else:
        score = float(nexpected - npoor) / nexpected
        longmsg = 'Low gaincal SNR estimates for spws %s in %s ' % (poor_spws, ms.basename)
        shortmsg = 'Low gaincal SNR estimates'

    origin = pqa.QAOrigin(
        metric_name='score_poor_phase_snrs', metric_score=npoor, metric_units='Number of poor phase SNR estimates'
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_derived_fluxes_snr(ms, measurements):
    """Score the SNR of the derived flux measurements.

    See PIPE-644 for latest description.

    Linearly scale QA score based on SNR value, where
      QA = 1.0 if SNR >= 26.25
      QA = 0.66 if SNR < 5.0
    and QA linearly scales from 0.66 to 1.0 between SNR 5 to 26.25.

    These QA and SNR threshold were chosen such that SNR values in the range of
    5-20 should map to QA scores in the range that will show as a blue
    "suboptimal" level QA message.
    """
    # Loop over measurements
    nmeasured = 0
    score = 0.0
    minscore = 1.0
    minsnr = None
    snr_thresh = 26.25
    low_snr_flux = collections.defaultdict(list)

    for fieldid, field_measurements in measurements.items():
        # Loop over the flux measurements
        for measurement in field_measurements:
            fluxjy = measurement.I.to_units(measures.FluxDensityUnits.JANSKY)
            uncjy = measurement.uncertainty.I.to_units(measures.FluxDensityUnits.JANSKY)
            if fluxjy <= 0.0 or uncjy <= 0.0:
                continue
            snr = fluxjy / uncjy
            minsnr = snr if minsnr is None else min(minsnr, snr)
            nmeasured += 1
            score1 = linear_score(float(snr), 5.0, snr_thresh, 0.66, 1.0)
            minscore = min(minscore, score1)
            score += score1
            if score1 < 1.0:
                low_snr_flux[fieldid].append(measurement.spw_id)

    if nmeasured > 0:
        score /= nmeasured

    if nmeasured == 0:
        score = 0.0
        longmsg = 'No derived fluxes for %s ' % ms.basename
        shortmsg = 'No derived fluxes'
    elif minscore >= 1.0:
        score = 1.0
        longmsg = 'No low SNR derived fluxes for %s ' % ms.basename
        shortmsg = 'No low SNR derived fluxes'
    else:
        # Report which field(s) and SpW(s) had low SNR.
        fld_summaries = [
            f'field {fid}, SpW(s) {", ".join(str(s) for s in sorted(spwids))}'
            for fid, spwids in sorted(low_snr_flux.items())
        ]
        longmsg = (
            f'For {ms.basename}, the fractional uncertainty in the derived scaling factor is large'
            f' (> {100 / snr_thresh:.1f}%) for {"; ".join(fld_summaries)}. The calibrator may be too faint.'
        )
        shortmsg = 'Uncertainty in some of the derived fluxes'

    origin = pqa.QAOrigin(
        metric_name='score_derived_fluxes_snr',
        metric_score=minsnr,
        metric_units='Minimum SNR of derived flux measurement',
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_gfluxscale_k_spw(vis, field, spw_id, k_spw, ref_spw):
    """Convert internal spw_id-spw_id consistency ratio to a QA score.

    See CAS-10792 for full specification.
    See PIPE-644 for update to restrict range of scores.

    k_spw is equal to the ratio:

                       calibrated visibility flux / catalogue flux
    k_spw = --------------------------------------------------------------------
            (calibrated visibility flux / catalogue flux) for highest SNR window

    Q_spw = abs(1 - k_spw)

    If        Q_spw < 0.1 then QA score = 1.0  (green)
    If 0.1 <= Q_spw < 0.2 then QA score = 0.75 (Blue/below standard)
    If 0.2 <= Q_spw       then QA score = 0.5  (Yellow/warning)

    :param k_spw: numeric k_spw ratio, as per spec
    :param vis: name of measurement set to which k_spw applies
    :param field: field domain object to which k_spw applies
    :param spw_id: name of spectral window to which k_spw applies
    :return: QA score
    """
    q_spw = abs(1 - k_spw)
    if q_spw < 0.1:
        score = 1.0
    elif q_spw < 0.2:
        score = 0.75
    else:
        score = 0.5

    longmsg = (
        'Ratio of <i>S</i><sub>calibrated</sub>/<i>S</i><sub>catalogue</sub> for {} ({}) spw {} in {} differs by'
        ' {:.0%} from the ratio for the highest SNR spw ({})'
        ''.format(utils.dequote(field.name), ','.join(field.intents), spw_id, vis, q_spw, ref_spw)
    )
    shortmsg = 'Internal spw-spw consistency'

    origin = pqa.QAOrigin(
        metric_name='score_gfluxscale_k_spw',
        metric_score=float(k_spw),
        metric_units='Number of spws with missing SNR measurements',
    )

    return pqa.QAScore(
        score,
        longmsg=longmsg,
        shortmsg=shortmsg,
        vis=vis,
        origin=origin,
        applies_to=pqa.TargetDataSelection(vis={vis}, field={field.id}, spw={spw_id}),
    )


@log_qa
def score_polcal_gain_ratio(
    session_name: str, ant_names: dict, xyratio_result: GaincalResults, threshold: float = 0.1
) -> list[pqa.QAScore]:
    """This QA heuristic inspects the gain ratios in an X/Y gain ratio caltable
    and creates a score based on how large the deviation from one is.

    Args:
        session_name: name of session being evaluated.
        ant_names: dictionary mapping antenna IDs to names.
        xyratio_result: Gaincal task result object containing the
            CalApplication for the caltable to analyze.
        threshold: threshold used to determine whether the gain ratio deviates
            too much from 1 (resulting in a lowered score).

    Returns:
        List of QAScore objects.
    """
    scores = []
    # Score each caltable in result.
    for calapp in xyratio_result.final:
        # Retrieve data from caltable.
        with casa_tools.TableReader(calapp.gaintable) as table:
            gains = np.squeeze(table.getcol('CPARAM'))
            spws = table.getcol('SPECTRAL_WINDOW_ID')
            ants = table.getcol('ANTENNA1')

        # Score each SpW separately.
        for spwid in sorted(set(spws)):
            ind_spw = np.where(spws == spwid)[0]
            ratios = np.abs(gains[0, ind_spw]) / np.abs(gains[1, ind_spw])
            ind_bad = np.where(np.abs(1 - ratios) > threshold)[0]

            if len(ind_bad) > 0:
                score = 0.65
                ant_str = utils.commafy([f'{ant_names[i]} (#{i})' for i in ants[ind_bad]], quotes=False)
                longmsg = (
                    f"Session '{session_name}' has gain ratios deviate from 1 by more than {threshold} for SpW"
                    f' {spwid}, antenna(s) {ant_str}'
                )
                shortmsg = 'Large gain ratio deviation'
                origin = pqa.QAOrigin(
                    metric_name='score_polcal_gain_ratio', metric_score=score, metric_units='gain ratio'
                )
                scores.append(pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin))

    # If no large deviations in gain ratio are found, then create a good score.
    if not scores:
        score = 1.0
        longmsg = (
            f"Session '{session_name}' has gain ratios with deviations from 1 <= the threshold of {threshold}"
            f' for all SpWs and all antennas.'
        )
        shortmsg = 'Gain ratio'
        origin = pqa.QAOrigin(metric_name='score_polcal_gain_ratio', metric_score=score, metric_units='gain ratio')
        scores.append(pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin))

    return scores


@log_qa
def score_polcal_gain_ratio_rms(
    session_name: str, gain_ratio_rms: tuple[list, list], threshold: float = 0.02
) -> pqa.QAScore:
    """This QA heuristic receives gain ratio RMS corresponding to scan IDs, and
    scores outliers beyond the threshold.

    Args:
        session_name: name of session being evaluated.
        gain_ratio_rms: tuple containing a list of scan IDs and a list of
            corresponding gain ratio RMS.
        threshold: threshold used to determine whether the gain ratio RMS is
            high enough to return a lowered score.

    Returns:
        QAScore object
    """
    # Retrieve the gain ratio RMS and scan IDs.
    scanids, ratio_rms = gain_ratio_rms

    # Identify outlier gain ratio RMS
    ind_bad = np.where(np.asarray(ratio_rms) > threshold)[0]

    if len(ind_bad) > 0:
        score = 0.6
        longmsg = (
            f"Session '{session_name}' has gain ratio RMS greater than {threshold} in scan(s)"
            f' {utils.commafy([str(s) for s in np.asarray(scanids)[ind_bad]], quotes=False)}.'
        )
        shortmsg = 'High gain ratio RMS'
    else:
        score = 1.0
        longmsg = f"Session '{session_name}' has gain ratio RMS <= the threshold of {threshold} for all scans."
        shortmsg = 'Gain ratio RMS'

    origin = pqa.QAOrigin(metric_name='score_polcal_gain_ratio_rms', metric_score=score, metric_units='gain ratio rms')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_polcal_leakage(
    session_name: str, ant_names: dict, leakage_result: PolcalWorkerResults, th_poor: float = 0.10, th_bad: float = 0.15
) -> list[pqa.QAScore]:
    """This heuristic inspects the polarization calibrator leakage (D-terms)
    solutions caltable and create a score based on how large the deviation from
    zero is.

    Args:
        session_name: name of session being evaluated.
        ant_names: dictionary mapping antenna IDs to names.
        leakage_result: PolcalWorker task result object containing the
            CalApplication for the leakage caltable to analyze.
        th_poor: threshold used to declare that leakage solutions are poor.
        th_bad: threshold used to declare that leakage solutions are bad.

    Returns:
        List of QAScore objects.
    """
    scores = []
    # Score each caltable in result.
    for calapp in leakage_result.final:
        # Retrieve data from leakage solutions caltable.
        with casa_tools.TableReader(calapp.gaintable) as table:
            # Retrieve unique SpWs and antennas.
            uniq_spws = sorted(set(table.getcol('SPECTRAL_WINDOW_ID')))
            uniq_ants = sorted(set(table.getcol('ANTENNA1')))

            # Score each SpW separately.
            for spwid in uniq_spws:
                # Retrieve D-terms for current SpW.
                data = table.query(f'SPECTRAL_WINDOW_ID=={spwid}', columns='CPARAM')
                dterms = data.getcol('CPARAM')

                # For each antenna, check if the D-terms solutions exceed the
                # threshold.
                bad_antids = []
                poor_antids = []
                for antid in uniq_ants:
                    pol1 = dterms[0, :, antid]
                    pol2 = dterms[1, :, antid]

                    rpol1 = abs(np.real(pol1)) > th_bad
                    ipol1 = abs(np.imag(pol1)) > th_bad
                    rpol2 = abs(np.real(pol2)) > th_bad
                    ipol2 = abs(np.imag(pol2)) > th_bad

                    if rpol1.any() or ipol1.any() or rpol2.any() or ipol2.any():
                        bad_antids.append(antid)
                        continue

                    rpol1 = abs(np.real(pol1)) > th_poor
                    ipol1 = abs(np.imag(pol1)) > th_poor
                    rpol2 = abs(np.real(pol2)) > th_poor
                    ipol2 = abs(np.imag(pol2)) > th_poor

                    if rpol1.any() or ipol1.any() or rpol2.any() or ipol2.any():
                        poor_antids.append(antid)

                if poor_antids:
                    score = 0.75
                    longmsg = (
                        f"Session '{session_name}' has D-terms solutions that deviate by {th_poor}-{th_bad} for"
                        f' SpW {spwid}, antenna(s)'
                        f' {utils.commafy([ant_names[i] for i in poor_antids], quotes=False)}.'
                    )
                    shortmsg = 'Large deviation D-terms solutions'
                    origin = pqa.QAOrigin(
                        metric_name='score_polcal_leakage',
                        metric_score=score,
                        metric_units='D-terms solutions deviation',
                    )
                    scores.append(pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin))

                if bad_antids:
                    score = 0.55
                    longmsg = (
                        f"Session '{session_name}' has D-terms solutions that deviate by more than {th_bad} for"
                        f' SpW {spwid}, antenna(s)'
                        f' {utils.commafy([ant_names[i] for i in bad_antids], quotes=False)}.'
                    )
                    shortmsg = 'Very large deviation D-terms solutions'
                    origin = pqa.QAOrigin(
                        metric_name='score_polcal_leakage',
                        metric_score=score,
                        metric_units='D-terms solutions deviation',
                    )
                    scores.append(pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin))

    # If no poor D-terms solutions are found, then create a good score.
    if not scores:
        score = 1.0
        longmsg = (
            f"Session '{session_name}' has D-terms solutions <= the threshold of {th_poor} for all SpWs and antennas."
        )
        shortmsg = 'D-terms solutions'
        origin = pqa.QAOrigin(
            metric_name='score_polcal_leakage', metric_score=score, metric_units='D-terms solutions deviation'
        )
        scores.append(pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin))

    return scores


@log_qa
def score_polcal_residual_pol(session_name: str, pfg_result: dict, threshold: float = 0.001) -> list[pqa.QAScore]:
    """This heuristic inspects the dictionary returned by CASA's polfromgain and
    scores the residual polarization in Q and U, compared to a threshold.

    Args:
        session_name: name of session being evaluated.
        pfg_result: dictionary of results produced by polfromgain
        threshold: threshold for residual polarization, above which the score
            should be lowered.

    Returns:
        List of QAScore objects.
    """
    scores = []

    # Create score for each field.
    for field_name, field_result in pfg_result.items():
        # Check residual polarization for each SpW.
        bad_spwids = []
        for spwid, spw_result in field_result.items():
            # Skip the result for "Average SpW".
            if 'Ave' in spwid:
                continue

            # The SpW result is a list of [I, Q, U, V], check whether Q or U
            # exceed threshold.
            if abs(spw_result[1]) > threshold or abs(spw_result[2]) > threshold:
                bad_spwids.append(spwid[3:])

        # Create a score depending on whether any SpW had too high residual
        # polarization.
        if bad_spwids:
            score = 0.5
            longmsg = (
                f"Session '{session_name}' has residual polarization greater than {threshold} in SpW(s)"
                f' {utils.commafy(bad_spwids, quotes=False)}.'
            )
            shortmsg = 'High residual polarization'
        else:
            score = 1.0
            longmsg = f"Session '{session_name}' residual polarization <= the threshold of {threshold}."
            shortmsg = 'Residual polarization'
        origin = pqa.QAOrigin(
            metric_name='score_polcal_residual_pol', metric_score=score, metric_units='residual polarization'
        )
        scores.append(pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin))

    return scores


@log_qa
def score_polcal_results(session_name: str, caltables: list) -> pqa.QAScore:
    """This heuristic tests whether calibrations were derived for a polcal session.

    Args:
        session_name: name of session being evaluated.
        caltables: list of calibration tables derived for session.

    Returns:
        QAScore object
    """
    if not caltables:
        score = 0.0
        longmsg = f"No polarisation calibration derived for session '{session_name}'."
        shortmsg = 'No polarisation calibration for session'
    else:
        score = 1.0
        longmsg = f"Polarisation calibration derived for session '{session_name}'."
        shortmsg = 'Polarisation calibration derived for session'

    origin = pqa.QAOrigin(metric_name='score_polcal_results', metric_score=score, metric_units='polarisation caltables')

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_separation_angles(mses: MeasurementSet, sepangles: dict) -> list[pqa.QAScore]:
    """The current heuristic exists only to
    reports the separation angles between the TARGET
    (and CHECK) intents to the PHASE intent for
    each measurement set

    Args:
        mses: the measurement set name to use as the key
        for the separation angle dictionary
        sepangles: dictionary of separations angles

    Returns:
        QAScore object
    """
    # holds the final list of QA scores
    scores: list[pqa.QAScore] = []

    # Sort to ensure presentation consistency
    mses = sorted(mses, key=lambda ms: ms.basename)
    for ms in mses:
        # filter the dict
        for primary, secondaries in sepangles[ms.basename].items():
            # primary will be intent, fieldid, fieldname
            # secondaries is another dict with intent, fieldid, fieldname as key,
            # and a dict as the value with unit and value
            intent1 = primary[0]
            field1 = f'{primary[2]}'  # can use other string process like -->>  f"{field} (#{fieldid})"
            # pull the items into a tuple
            intent2 = [(fld2, id2, nm2, ang['unit'], ang['value']) for (fld2, id2, nm2), ang in secondaries.items()][
                0
            ]  # only item per secondary
            field2 = f'{intent2[2]}'
            if intent2[3] == 'deg':
                sepvalue = round(intent2[4], 2)  # or 3 dp ?
                # do the score
                score = 1.0
                longmsg = 'For %s the %s %s to %s %s separation angle is %s deg' % (
                    ms.basename,
                    intent1,
                    field1,
                    intent2[0],
                    field2,
                    str(sepvalue),
                )
                shortmsg = ' %s to %s is %s' % (field1, field2, str(sepvalue))
                reportsep = str(sepvalue)
            else:
                # do the score
                score = 0.90
                longmsg = 'For %s the %s %s to %s %s separation angle cannot be extracted' % (
                    ms.basename,
                    intent1,
                    field1,
                    intent2[0],
                    field2,
                )
                shortmsg = ' %s to %s is n/a' % (field1, field2)
                reportsep = 'n/a'
            # for QA score data selection
            fieldqa = field1 + ',' + field2
            intentqa = intent1 + ',' + intent2[0]

            origin = pqa.QAOrigin(
                metric_name='report_separation_angles',
                metric_score=reportsep,  # this is the value not a 0 to 1 score
                metric_units='degrees',
            )

            score = pqa.QAScore(
                score,
                longmsg=longmsg,
                shortmsg=shortmsg,
                vis=ms.basename,
                origin=origin,
                weblog_location=pqa.WebLogLocation.NOWEB,
                applies_to=pqa.TargetDataSelection(vis={ms.basename}, field={fieldqa}, intent={intentqa}),
            )
            # weblog location can be NOWEB - do not render it
            scores.append(score)

    return scores


@log_qa
def score_fluxservice(result: ALMAImportDataResults) -> list[pqa.QAScore]:
    """Returns QA scores based on:
    1. Flux catalog service usage and flux origin
    2. Age of the nearest monitoring point (if applicable)
    """
    flux_qa_dict = {
        'FIRSTURL': (1.0, 'Flux catalog service used.'),
        'BACKUPURL': (0.9, 'Backup flux catalog service used.'),
        'FAIL': (0.3, 'Online flux catalog unavailable. Pipeline halted after weblog creation.'),
        None: (1.0, 'Flux catalog service not used.'),
    }

    if result.fluxservice not in flux_qa_dict:
        LOG.warning(
            'Unrecognized flux catalog service result: %s. Falling back to default suboptimal qa score of 0.9.',
            result.fluxservice,
        )

    flux_score, flux_msg = flux_qa_dict.get(result.fluxservice, (0.9, 'Unknown result from flux catalogue service.'))

    ampcal = None
    ampcal_spws = []
    agecounter = 0
    scores = []

    if result.fluxservice in ('FIRSTURL', 'BACKUPURL'):
        for setjy_result in result.setjy_results:
            for fieldid, measurements in setjy_result.measurements.items():
                fieldobjs = result.mses[0].get_fields(field_id=fieldid)
                ampcals = [f for f in fieldobjs if 'AMPLITUDE' in f.intents]
                if not ampcals:
                    continue

                ampcal = ampcals[0]

                for m in measurements:
                    if getattr(m, 'origin', None) == 'Source.xml':
                        flux_score = min(flux_score, 0.3)
                        ampcal_spws.append(str(m.spw_id))

                    age = getattr(m, 'age', None)
                    if age is None:
                        LOG.debug('Skipping measurement due to missing age data.')
                    elif abs(int(age)) > 14:
                        agecounter += 1

        if ampcal_spws and ampcal:
            flux_msg = (
                f'For {result.mses[0].basename}, the origin of the adopted flux for the flux '
                f'calibrator {ampcal.name} is the ASDM for the following spws: {", ".join(ampcal_spws)}.'
            )

        # Score based on monitor point age
        age_score = 0.5 if agecounter > 0 else 1.0
        age_msg = (
            f'Age of nearest monitoring point exceeds 14 days for {agecounter} measurement(s).'
            if agecounter > 0
            else 'All monitoring points are within acceptable age range.'
        )

        scores.append(
            pqa.QAScore(
                age_score, longmsg=age_msg, shortmsg=age_msg, origin=pqa.QAOrigin('flux_monitor_age', age_score, 'days')
            )
        )

    # Score for flux catalog usage
    scores.append(
        pqa.QAScore(
            flux_score,
            longmsg=flux_msg,
            shortmsg=flux_msg,
            origin=pqa.QAOrigin('flux_catalog_service', flux_score, 'flux service'),
        )
    )

    return scores


@log_qa
def score_fluxservicemessages(result):
    """Report any flux service messaging and status codes"""
    if result.inputs['dbservice'] is False:
        score = 1.0
        longmsg = 'Flux catalog service not used.  No warning messages reported.'
        shortmsg = longmsg
    elif result.inputs['dbservice'] is True:
        score = 1.0
        longmsg = 'No warning messages from the flux catalog service.'
        shortmsg = longmsg
        if result.qastatus:
            longmsg = ''
            for qacode in result.qastatus:
                if qacode['clarification']:
                    score = 0.5
                    # Queries a per source, so there may be more than one message returned.
                    longmsg += 'Source: {!s},  Status code: {!s},     Message: {!s}\n'.format(
                        qacode['source'], qacode['status_code'], qacode['clarification']
                    )
                    shortmsg = 'Flux service returned warning messages.'

    origin = pqa.QAOrigin(
        metric_name='score_fluxservice_messaging', metric_score=score, metric_units='flux service messaging'
    )
    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_fluxservicestatuscodes(result):
    """Report any flux service codes for status_code > 1"""
    if result.inputs['dbservice'] is False:
        score = 1.0
        msg = 'Flux catalog service not used.  No status codes to report.'
    elif result.inputs['dbservice'] is True:
        score = 1.0
        msg = 'Flux catalog service status queries returned code 0 or 1.'
        if result.qastatus:
            scores = []
            for qacode in result.qastatus:
                # Status code can be 0,1,2,3
                if int(qacode['status_code']) > 1:
                    score = 0.3
                    msg = 'A query of the flux catalog service returned a status code: {!s}'.format(
                        str(qacode['status_code'])
                    )

    origin = pqa.QAOrigin(
        metric_name='score_fluxservice_statuscode', metric_score=score, metric_units='flux service status code'
    )
    return pqa.QAScore(score, longmsg=msg, shortmsg=msg, origin=origin)


@log_qa
def score_fluxcsv(result):
    """Check for existence of flux.csv file on import"""
    if os.path.exists('flux.csv'):
        score = 1.0
        msg = 'flux.csv exists on disk'
    else:
        score = 0.3
        msg = 'flux.csv does not exist'

    origin = pqa.QAOrigin(metric_name='score_fluxcsv', metric_score=score, metric_units='flux csv')
    return pqa.QAScore(score, longmsg=msg, shortmsg=msg, origin=origin)


@log_qa
def score_tsysflagcontamination_contamination_flagged(vis, summaries) -> pqa.QAScore:
    """Calculate a score for the hifa_tsysflagcontamination task based on whether
    any line contamination was flagged.

    0% flagged  -> 1
    >0% flagged -> 0.9
    """
    frac_flagged = calc_frac_newly_flagged(summaries)

    if frac_flagged:
        score = 0.9
        longmsg = f'Tsys line contamination detected in {vis}.'
        shortmsg = 'Tsys contamination flagged'
    else:
        score = 1.0
        longmsg = f'No Tsys line contamination detected in {vis}.'
        shortmsg = 'No Tsys line contamination'

    origin = pqa.QAOrigin(
        metric_name='score_tsys_line_contamination_flagged',
        metric_score=frac_flagged,
        metric_units='Fraction of Tsys data that was identified as line contamination and flagged',
    )
    return pqa.QAScore(
        score,
        longmsg=longmsg,
        shortmsg=shortmsg,
        vis=os.path.basename(vis),
        origin=origin,
        applies_to=pqa.TargetDataSelection(vis={vis}),
    )


@log_qa
def score_tsysflagcontamination_external_heuristic(foreign_qascores: list[pqa.QAScore]) -> list[pqa.QAScore]:
    """Adopt QA scores that originate from the Tsysflag line contamination
    heuristic.

    The QA scores are generated in an external heuristic. This metric
    is here mainly to log the QA scores to console for non-weblog runs
    via the @log_qa decorator.
    """
    origin = pqa.QAOrigin(
        metric_name='score_tsysflagcontamination_external_heuristic',
        metric_score='N/A',
        metric_units='',
    )
    qascores = []
    for fq in foreign_qascores:
        adopted_qascore = pqa.QAScore(
            score=fq.score, shortmsg=fq.shortmsg, longmsg=fq.longmsg, applies_to=fq.applies_to, origin=origin
        )
        qascores.append(adopted_qascore)
    return qascores
