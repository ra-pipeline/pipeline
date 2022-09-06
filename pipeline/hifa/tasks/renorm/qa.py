import os
import numpy as np
import copy

import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.pipelineqa as pqa
import pipeline.infrastructure.utils as utils

from . import renorm

LOG = logging.get_logger(__name__)


class RenormQAHandler(pqa.QAPlugin):
    """
    QA handler for an uncontained RenormResults.
    """
    result_cls = renorm.RenormResults
    child_cls = None

    def handle(self, context, result):
        # Get task threshold value. In the future one might rely on
        # the automatic defaults in almarenorm. In that case the threshold
        # per spw needs to be fetched from the stats dictionary in the spw
        # loop below (result.stats[source][spw]['threshold']).
        threshold = result.threshold 
        if result.exception is not None:
            score = 0.0
            shortmsg = 'Failure in renormalization'
            longmsg = 'Failure in running renormalization heuristic: {}'.format(result.exception)
            result.qa.pool.append(pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=result.vis))
            return

        if result.apply and result.corrApplied:
            # Request for correcting data that has already been corrected
            score = 0.0
            shortmsg = 'Corrections already applied'
            longmsg = 'EB {}: Corrections already applied to data'.format(os.path.basename(result.vis))
            result.qa.pool.append(pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=result.vis))

        if not result.corrColExists and result.apply:
            # Request for correcting data when there is no CORRECTED_DATA column
            score = 0.0
            shortmsg = 'No corrected data column'
            longmsg = 'EB {}: Corrected data column does not exist'.format(os.path.basename(result.vis))
            result.qa.pool.append(pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=result.vis))

        for source in result.stats: 
            for spw in result.stats[source]:
                try:
                    max_factor = result.stats[source][spw]['max_rn']
                    origin = pqa.QAOrigin(metric_name='MaxRenormFactor',
                                          metric_score=max_factor,
                                          metric_units='')

                    if (max_factor < 1.0) or np.isnan(max_factor):
                        # These values should never occur
                        score = 0.0
                        shortmsg = 'Unexpected values.'
                        longmsg = 'EB {} source {} spw {}: Error calculating corrections. Maximum factor is {}.'.format( \
                                  os.path.basename(result.vis), source, spw, max_factor)
                    elif np.isnan(result.rnstats['N'][source][spw]).any():
                        # Any NaNs apart from max_factor?
                        score = 0.0
                        shortmsg = 'Unexpected values.'
                        longmsg = 'EB {} source {} spw {}: Error calculating corrections. NaNs encountered.'.format( \
                                  os.path.basename(result.vis), source, spw)
                    elif 1.0 <= max_factor <= threshold:
                        score = 1.0
                        shortmsg = 'Renormalization factor within threshold'
                        longmsg = 'EB {} source {} spw {}: maximum renormalization factor of {:.3f} ' \
                                  'is within threshold of {:.1%}'.format( \
                                  os.path.basename(result.vis), source, spw, max_factor, threshold-1.0)
                    elif max_factor > threshold:
                        if result.apply:
                            score = 0.9
                            shortmsg = 'Renormalization applied'
                            longmsg = 'EB {} source {} spw {}: maximum renormalization factor of {:.3f} ' \
                                      'is outside threshold of {:.1%} so corrections were applied to data'.format( \
                                      os.path.basename(result.vis), source, spw, max_factor, threshold-1.0)
                        else:
                            score = max(0.66+threshold-max_factor, 0.34)
                            shortmsg = 'Renormalization factor outside threshold'
                            longmsg = 'EB {} source {} spw {}: maximum renormalization factor of {:.3f} ' \
                                      'is outside threshold of {:.1%} but corrections were not applied to the data.'.format( \
                                      os.path.basename(result.vis), source, spw, max_factor, threshold-1.0)

                    result.qa.pool.append(pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, vis=result.vis, origin=origin))
                except:
                    # No factors for this spw. Just skip it.
                    pass

        # Make a copy of this dict to keep track of whether a QA message was issued for
        # each excludechan SPW yet. 
        excludechan = copy.deepcopy(result.excludechan)

        # Only warn about spws in excludechan not matching the spws for the automated suggestions if there are whole suggested spws
        # not covered by the input excludechan dict. (Without this, there is a QA warning when the input excludechan values are 
        # so close to the ones that would be recommeded by renorm, that no additional automated suggestions are made.) 
        warn_excludechan_spw = False

        for target in result.atmWarning: 
            for spw in result.atmWarning[target]:
                if result.atmWarning[target][spw]:
                    if not result.apply:
                        atm_score = 0.9
                        shortmsg = "Renormalization correction may be incorrect due to an atmospheric feature"
                        longmsg = "Renormalization correction may be incorrect in SPW {} due to an atmospheric feature. Suggested "\
                                  "channel exclusion: {}".format(spw, result.atmExcludeCmd[target][spw])
                    else:
                        if excludechan:
                            excluded_spws = excludechan.keys()
                            if spw in excluded_spws: 
                                longmsg = "Channels {} are being excluded from renormalization correction to SPW {}. Auto-calculated channel " \
                                      "exclusion: {}".format(excludechan[spw], spw, result.atmExcludeCmd[target][spw])
                                # Since we printed a message about the excluded channels for this SPW, remove it from the list that haven't yet been covered.
                                del excludechan[spw]
                            else: 
                                longmsg = "No channels are being excluded from renormalization correction to SPW {}. Auto-calculated channel " \
                                      "exclusion: {}".format(spw, result.atmExcludeCmd[target][spw]) 
                                warn_excludechan_spw = True
                            atm_score = 0.85
                            shortmsg = "Channels are being excluded from renormalization correction"
                        elif result.atmAutoExclude:
                            atm_score = 0.9
                            shortmsg = "Channels are being excluded from renormalization correction due to an atmospheric feature"
                            longmsg = "Channels {} are being excluded from renormalization correction to SPW {} due to an atmospheric " \
                                      "feature.".format(result.atmExcludeCmd[target][spw], spw)
                        else: 
                            atm_score = 0.66
                            shortmsg = "Renormalization correction may be incorrectly applied"
                            longmsg = "A renormalization correction may be incorrectly applied to SPW {} due to an atmospheric feature. " \
                                      "Suggested channel exclusion: {}".format(spw, result.atmExcludeCmd[target][spw])
                    result.qa.pool.append(pqa.QAScore(atm_score, longmsg=longmsg, shortmsg=shortmsg, vis=result.vis))

        # If there were any entries in excludechan for spws that weren't identified as having an atmospheric feature by renorm,
        # when apply=True, and there are also provide a QA message.
        if result.apply and warn_excludechan_spw:
            for exclude_spw in excludechan:
                longmsg = "Channels {} are being excluded from renormalization correction to SPW {}. " \
                          "Auto-calculated channel exclusion indicated that no channels need to be excluded for SPW {}." \
                          .format(excludechan[exclude_spw], exclude_spw, exclude_spw)
                shortmsg = "Channels are being excluded from renormalization correction"
                atm_score = 0.85
                result.qa.pool.append(pqa.QAScore(atm_score, longmsg=longmsg, shortmsg=shortmsg, vis=result.vis))

class RenormListQAHandler(pqa.QAPlugin):
    """
    QA handler for a list containing RenormResults.
    """
    result_cls = basetask.ResultsList
    child_cls = renorm.RenormResults

    def handle(self, context, result):
        # collate the QAScores from each child result, pulling them into our
        # own QAscore list
        collated = utils.flatten([r.qa.pool for r in result])
        result.qa.pool[:] = collated
