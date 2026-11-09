"""Generic interferometric QA score calculators."""

from __future__ import annotations

import functools
import operator
import os

import numpy as np
from scipy import special

import pipeline.infrastructure.pipelineqa as pqa
from pipeline import infrastructure
from pipeline.domain import measures
from pipeline.infrastructure import casa_tools, utils
from pipeline.infrastructure.renderer import rendererutils
from pipeline.qa import checksource
from pipeline.qa.common_scores import (
    calc_flags_per_agent,
    calc_frac_newly_flagged,
    log_qa,
)

LOG = infrastructure.logging.get_logger(__name__)

__all__ = [
    'linear_score_fraction_newly_flagged',
    'linear_score_fraction_unflagged_newly_flagged_for_intent',
    'score_checksources',
    'score_flagging_view_exists',
    'score_mom8_fc_image',
    'score_multiply',
    'score_setjy_measurements',
]


@log_qa
def linear_score_fraction_newly_flagged(filename, summaries, vis):
    """Calculate a score for the flagging task based on the fraction of
    data newly flagged.

    fraction flagged   -> score
    """
    # Calculate fraction of flagged data.
    frac_flagged = calc_frac_newly_flagged(summaries)

    # Convert fraction of flagged data into a score.
    score = 1.0 - frac_flagged

    # Set score messages and origin.
    percent = 100.0 * frac_flagged
    longmsg = '%0.2f%% of data in %s was newly flagged' % (percent, filename)
    shortmsg = '%0.2f%% data flagged' % percent

    origin = pqa.QAOrigin(
        metric_name='linear_score_fraction_newly_flagged',
        metric_score=frac_flagged,
        metric_units='Fraction of data that is newly flagged',
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=os.path.basename(vis), origin=origin)


@log_qa
def linear_score_fraction_unflagged_newly_flagged_for_intent(ms, summaries, intent):
    """Calculate a score for the flagging task based on the fraction of unflagged
    data for scans belonging to specified intent that got newly flagged.

    If no unflagged data was found in the before summary, then return a score
    of 0.0.
    """
    # Identify scan IDs belonging to intent.
    scanids = [str(scan.id) for scan in ms.get_scans(scan_intent=intent)]

    # Calculate flags for scans belonging to intent.
    agent_stats = calc_flags_per_agent(summaries, scanids=scanids)

    # Calculate counts of unflagged data.
    unflaggedcount = agent_stats[0].total - agent_stats[0].flagged

    # If the "before" summary had unflagged data, then proceed to compute
    # the fraction fo unflagged data that got newly flagged.
    if unflaggedcount > 0:
        frac_flagged = functools.reduce(operator.add, [float(s.flagged) / unflaggedcount for s in agent_stats[1:]], 0)

        score = 1.0 - frac_flagged
        percent = 100.0 * frac_flagged
        longmsg = '{:0.2f}% of unflagged data with intent {} in {} was newly flagged.'.format(
            percent, intent, ms.basename
        )
        shortmsg = '{:0.2f}% unflagged data flagged.'.format(percent)

        origin = pqa.QAOrigin(
            metric_name='linear_score_fraction_unflagged_newly_flagged_for_intent',
            metric_score=frac_flagged,
            metric_units='Fraction of unflagged data for intent {} that is newly flagged'.format(intent),
        )
    # If no unflagged data was found at the start, return score of 0.
    else:
        score = 0.0
        longmsg = 'No unflagged data with intent {} found in {}.'.format(intent, ms.basename)
        shortmsg = 'No unflagged data.'
        origin = pqa.QAOrigin(
            metric_name='linear_score_fraction_unflagged_newly_flagged_for_intent',
            metric_score=False,
            metric_units='Presence of unflagged data.',
        )

    # Append extra warning to QA message if score falls at-or-below the "warning" threshold.
    if score <= rendererutils.SCORE_THRESHOLD_WARNING:
        longmsg += ' Please investigate!'
        shortmsg += ' Please investigate!'

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_setjy_measurements(ms, reqfields, reqintents, reqspws, measurements):
    """Score is equal to the ratio of the number of actual flux
    measurements to expected number of flux measurements
    """
    # Expected fields
    scifields = {field for field in ms.get_fields(reqfields, intent=reqintents)}

    # Expected science windows
    scispws = {spw.id for spw in ms.get_spectral_windows(reqspws, science_windows_only=True)}

    # Loop over the expected fields
    nexpected = 0
    for scifield in scifields:
        validspws = {spw.id for spw in scifield.valid_spws}
        nexpected += len(validspws.intersection(scispws))

    # Loop over the measurements
    nmeasured = 0
    for value in measurements.values():
        # Loop over the flux measurements
        nmeasured += len(value)

    # Compute score
    if nexpected == 0:
        score = 0.0
        longmsg = 'No flux calibrators for %s ' % ms.basename
        shortmsg = 'No flux calibrators'
    elif nmeasured == 0:
        score = 0.0
        longmsg = 'No flux measurements for %s ' % ms.basename
        shortmsg = 'No flux measurements'
    elif nexpected == nmeasured:
        score = 1.0
        longmsg = 'All expected flux calibrator measurements present for %s ' % ms.basename
        shortmsg = 'All expected flux calibrator measurements present'
    elif nmeasured < nexpected:
        score = float(nmeasured) / float(nexpected)
        longmsg = 'Missing flux calibrator measurements for %s %d/%d ' % (ms.basename, nmeasured, nexpected)
        shortmsg = 'Missing flux calibrator measurements'
    else:
        score = 0.0
        longmsg = 'Too many flux calibrator measurements for %s %d/%d' % (ms.basename, nmeasured, nexpected)
        shortmsg = 'Too many flux measurements'

    origin = pqa.QAOrigin(
        metric_name='score_setjy_measurements',
        metric_score=score,
        metric_units='Ratio of number of flux measurements to number expected',
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)


@log_qa
def score_flagging_view_exists(filename, result):
    """Assign a score of zero if the flagging view cannot be computed"""
    # By default, assume no flagging views were found.
    score = 0.0
    longmsg = 'No flagging views for %s' % filename
    shortmsg = 'No flagging views'

    # Check if this is a flagging result for a single metric, where
    # the flagging view is stored directly in the result.
    try:
        view = result.view
        if view:
            score = 1.0
            longmsg = 'Flagging views exist for %s' % filename
            shortmsg = 'Flagging views exist'
    except AttributeError:
        pass

    # Check if this flagging results contains multiple metrics,
    # and look for flagging views among components.
    try:
        # Set score to 1 as soon as a single metric contains a
        # valid flagging view.
        for metricresult in result.components.values():
            view = metricresult.view
            if view:
                score = 1.0
                longmsg = 'Flagging views exist for %s' % filename
                shortmsg = 'Flagging views exist'
    except AttributeError:
        pass

    origin = pqa.QAOrigin(
        metric_name='score_flagging_view_exists', metric_score=bool(score), metric_units='Presence of flagging view'
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=filename, origin=origin)


@log_qa
def score_checksources(mses, fieldname, spwid, imagename, rms, gfluxscale, gfluxscale_err):
    """Score a single field image of a point source by comparing the source
    reference position to the fitted position and the source reference flux
    to the fitted flux.

    The source is assumed to be near the center of the image.
    The fit is performed using pixels in a circular regions
    around the center of the image
    """
    qa = casa_tools.quanta
    me = casa_tools.measures

    # Get the reference direction of the check source field
    #    There is at least one field with check source intent
    #    Protect against the same source having multiple fields
    #    with different intent.
    #    Assume that the same field as defined by its field name
    #    has the same direction in all the mses that contributed
    #    to the input image. Loop through the ms(s) and find the
    #    first occurrence of the specified field. Convert the
    #    direction to ICRS to match the default image coordinate
    #    system

    refdirection = None
    for ms in mses:
        field = ms.get_fields(name=fieldname)
        # No fields with the check source name. Should be
        # impossible at this point but check just in case
        if not field:
            continue
        # Find check field for that ms
        chkfield = None
        for fielditem in field:
            if 'CHECK' not in fielditem.intents:
                continue
            chkfield = fielditem
            break
        # No matching check field for that ms, next ms
        if chkfield is None:
            continue
        # Found field, get reference direction in ICRS coordinates
        LOG.info(
            'Using field name %s id %s to determine check source reference direction'
            % (chkfield.name, str(chkfield.id))
        )
        refdirection = me.measure(chkfield.mdirection, 'ICRS')
        break

    # Get the reference flux of the check source field
    #    Loop over all the ms(s) extracting the derived flux
    #    values for the specified field and spw. Set the reference
    #    flux to the maximum of these values.
    reffluxes = []
    for ms in mses:
        if not ms.derived_fluxes:
            continue
        for field_arg, measurements in ms.derived_fluxes.items():
            mfield = ms.get_fields(field_arg)
            chkfield = None
            for mfielditem in mfield:
                if mfielditem.name != fieldname:
                    continue
                if 'CHECK' not in mfielditem.intents:
                    continue
                chkfield = mfielditem
                break
            # No matching check field for this ms
            if chkfield is None:
                continue
            LOG.info(
                'Using field name %s id %s to identify check source flux densities' % (chkfield.name, str(chkfield.id))
            )
            for measurement in sorted(measurements, key=lambda m: int(m.spw_id)):
                if int(measurement.spw_id) != spwid:
                    continue
                for stokes in ['I']:
                    try:
                        flux = getattr(measurement, stokes)
                        flux_jy = float(flux.to_units(measures.FluxDensityUnits.JANSKY))
                        reffluxes.append(flux_jy)
                    except:
                        pass

    # Use the maximum reference flux
    if not reffluxes:
        refflux = None
    else:
        median_flux = np.median(np.array(reffluxes))
        refflux = qa.quantity(median_flux, 'Jy')

    # Do the fit and compute positions offsets and flux ratios
    fitdict = checksource.checkimage(imagename, rms, refdirection, refflux)

    msnames = ','.join(utils.remove_trailing_string(os.path.basename(ms.name), '.ms') for ms in mses)

    # Compute the scores the default score is the geometric mean of
    # the position and flux scores if both are available.
    if not fitdict:
        offset = None
        offset_err = None
        beams = None
        beams_err = None
        fitflux = None
        fitflux_err = None
        fitpeak = None
        score = 0.34
        longmsg = 'Check source fit failed for %s field %s spwid %d' % (msnames, fieldname, spwid)
        shortmsg = 'Check source fit failed'
        metric_score = 'N/A'
        metric_units = 'Check source fit failed'

    else:
        offset = fitdict['positionoffset']['value'] * 1000.0
        offset_err = fitdict['positionoffset_err']['value'] * 1000.0
        beams = fitdict['beamoffset']['value']
        beams_err = fitdict['beamoffset_err']['value']
        fitflux = fitdict['fitflux']['value']
        fitflux_err = fitdict['fitflux_err']['value']
        fitpeak = fitdict['fitpeak']['value']
        shortmsg = 'Check source fit successful'

        warnings = []

        offset_score = 0.0
        offset_metric = 'N/A'
        offset_unit = 'beams'
        if beams is None:
            warnings.append('unfitted offset')
        else:
            offset_score = max(0.33, 1.0 - min(1.0, beams))
            offset_metric = beams
            if beams > 0.30:
                warnings.append('large fitted offset of %.2f marcsec and %.2f synth beam' % (offset, beams))

        # PIPE-3042: fitflux score and QA message based on gfluxscale are not used anymore, so they are removed.
        fitpeak_score = 0.0
        fitpeak_metric = 'N/A'
        fitpeak_unit = 'fitpeak/fitflux'
        if fitflux is None:
            warnings.append('undefined check fit result')
        elif fitflux == 0.0:
            warnings.append('Fitted Flux Density value of 0.0 mJy')
        else:
            chk_fitpeak_fitflux_ratio = fitpeak / fitflux
            fitpeak_score = max(0.33, 1.0 - abs(1.0 - (chk_fitpeak_fitflux_ratio)))
            fitpeak_metric = chk_fitpeak_fitflux_ratio
            if chk_fitpeak_fitflux_ratio < 0.7:
                warnings.append(
                    'low Fitted [Peak Intensity / Flux Density] Ratio of %.2f' % (chk_fitpeak_fitflux_ratio)
                )

        # PIPE-3042: fitflux score is not used anymore and the aggregated QA is minimum of offset_score and peak_fitflux score,
        # both of which is >0.33 and <1.0, so we just need to use min(offset_score, peak_fitflux score) for QA score
        score = min(offset_score, fitpeak_score)

        metric_score = [offset_metric, fitpeak_metric]
        metric_units = '%s, %s' % (offset_unit, fitpeak_unit)

        if warnings != []:
            # PIPE-3042: QA message based on gfluxscale is not used anymore
            longmsg = 'EB %s field %s spwid %d: has a %s' % (msnames, fieldname, spwid, ' and a '.join(warnings))
        else:
            if score <= 0.9:
                longmsg = 'EB %s field %s spwid %d: Check source fit not optimal' % (msnames, fieldname, spwid)
            else:
                longmsg = 'EB %s field %s spwid %d: Check source fit successful' % (msnames, fieldname, spwid)

        if score <= 0.9:
            shortmsg = 'Check source fit not optimal'

    origin = pqa.QAOrigin(metric_name='ScoreChecksources', metric_score=metric_score, metric_units=metric_units)

    return (
        pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin),
        offset,
        offset_err,
        beams,
        beams_err,
        fitflux,
        fitflux_err,
        fitpeak,
    )


@log_qa
def score_multiply(scores_list):
    score = functools.reduce(operator.mul, scores_list, 1.0)
    longmsg = 'Multiplication of scores.'
    shortmsg = 'Multiplication of scores.'
    origin = pqa.QAOrigin(
        metric_name='score_multiply', metric_score=len(scores_list), metric_units='Number of multiplied scores.'
    )

    return pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin)


@log_qa
def score_mom8_fc_image(
    mom8_fc_name,
    mom8_fc_peak_snr,
    mom8_10_fc_histogram_asymmetry,
    mom8_fc_max_segment_beams,
    mom8_fc_frac_max_segment,
):
    """Check the MOM8 FC image for outliers above a given SNR threshold. The score
    can vary between 0.33 and 1.0 depending on the fraction of outlier pixels.
    """
    mom8_fc_outlier_threshold1 = 5.0
    mom8_fc_outlier_threshold2 = 3.5
    mom8_fc_histogram_asymmetry_threshold1 = 0.20
    mom8_fc_histogram_asymmetry_threshold2 = 0.05
    mom8_fc_max_segment_beams_threshold = 1.0
    mom8_fc_score_min = 0.33
    mom8_fc_score_max = 1.00
    mom8_fc_metric_scale = 100.0
    if mom8_fc_frac_max_segment != 0.0:
        mom8_fc_score = mom8_fc_score_min + 0.5 * (mom8_fc_score_max - mom8_fc_score_min) * (
            1.0 + special.erf(-np.log10(mom8_fc_metric_scale * mom8_fc_frac_max_segment))
        )
    else:
        mom8_fc_score = mom8_fc_score_max

    with casa_tools.ImageReader(mom8_fc_name) as image:
        info = image.miscinfo()
        field = info.get('field')
        spw = info.get('virtspw')

    if (
        mom8_fc_peak_snr > mom8_fc_outlier_threshold1
        and mom8_10_fc_histogram_asymmetry > mom8_fc_histogram_asymmetry_threshold1
    ) or (
        mom8_fc_peak_snr > mom8_fc_outlier_threshold2
        and mom8_10_fc_histogram_asymmetry > mom8_fc_histogram_asymmetry_threshold2
        and mom8_fc_max_segment_beams > mom8_fc_max_segment_beams_threshold
    ):
        mom8_fc_final_score = min(mom8_fc_score, 0.65)
    else:
        mom8_fc_final_score = max(mom8_fc_score, 0.67)

    if 0.33 <= mom8_fc_final_score < 0.66:
        longmsg = (
            f'MOM8 FC image for field {field} virtspw {spw} with a peak SNR of {mom8_fc_peak_snr:#.5g} '
            f'and a flux histogram asymmetry which indicate that there may be residual line emission '
            f'in the findcont channels.'
        )
        shortmsg = 'MOM8 FC image indicates residual line emission'
        weblog_location = pqa.WebLogLocation.UNSET
    else:
        longmsg = (
            f'MOM8 FC image for field {field} virtspw {spw} has a peak SNR of {mom8_fc_peak_snr:#.5g} and no '
            f'significant flux histogram asymmetry.'
        )
        shortmsg = 'MOM8 FC peak SNR and flux histogram'
        weblog_location = pqa.WebLogLocation.ACCORDION

    origin = pqa.QAOrigin(
        metric_name='score_mom8_fc_image',
        metric_score=(
            mom8_fc_peak_snr,
            mom8_10_fc_histogram_asymmetry,
            mom8_fc_max_segment_beams,
            mom8_fc_frac_max_segment,
        ),
        metric_units='Peak SNR / Histogram asymmetry, Max. segment size in beams, Max. segment fraction',
    )

    return pqa.QAScore(
        mom8_fc_final_score,
        longmsg=longmsg,
        shortmsg=shortmsg,
        origin=origin,
        weblog_location=weblog_location,
    )
