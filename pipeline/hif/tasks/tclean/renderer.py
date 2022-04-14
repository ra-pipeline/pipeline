"""
Created on 7 Jan 2015

@author: sjw
"""
import collections
import itertools
import os
import string
from random import randint
import re

import numpy

import pipeline.infrastructure.filenamer as filenamer
import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.renderer.basetemplates as basetemplates
import pipeline.infrastructure.renderer.rendererutils as rendererutils
import pipeline.infrastructure.utils as utils
from pipeline.infrastructure import casa_tasks
from pipeline.infrastructure import casa_tools
from . import display

LOG = logging.get_logger(__name__)


ImageRow = collections.namedtuple('ImageInfo', (
    'vis field fieldname intent spw spwnames pol frequency_label frequency beam beam_pa sensitivity '
    'cleaning_threshold_label cleaning_threshold initial_nsigma_mad_label initial_nsigma_mad '
    'final_nsigma_mad_label final_nsigma_mad residual_ratio non_pbcor_label non_pbcor '
    'pbcor score fractional_bw_label fractional_bw aggregate_bw_label aggregate_bw aggregate_bw_num '
    'nsigma_label nsigma vis_amp_ratio_label vis_amp_ratio  '
    'image_file nchan plot qa_url iterdone stopcode stopreason '
    'chk_pos_offset chk_frac_beam_offset chk_fitflux chk_fitpeak_fitflux_ratio img_snr '
    'chk_gfluxscale chk_gfluxscale_snr chk_fitflux_gfluxscale_ratio cube_all_cont tclean_command result '
    'model_pos_flux model_neg_flux model_flux_inner_deg nmajordone_total nmajordone_per_iter majorcycle_stat_plot '
    'tab_dict tab_url outmaskratio outmaskratio_label'))


class T2_4MDetailsTcleanRenderer(basetemplates.T2_4MDetailsDefaultRenderer):
    def __init__(self, uri='tclean.mako', 
                 description='Produce a cleaned image', 
                 always_rerender=False):
        super(T2_4MDetailsTcleanRenderer, self).__init__(uri=uri,
                description=description, always_rerender=always_rerender)

    def update_mako_context(self, ctx, context, results):
        # There is only ever one CleanListResult in the ResultsList as it
        # operates over multiple measurement sets, so we can set the result to
        # the first item in the list
        if not results[0]:
            return

        makeimages_result = results[0]
        clean_results = makeimages_result.results

        weblog_dir = os.path.join(context.report_dir, 'stage%s' % results.stage_number)
        qaTool = casa_tools.quanta

        # Get results info
        image_rows = []

        # Holds a mapping of image name to image stats. This information is used to scale the MOM8 images.
        image_stats = {}

        for r in clean_results:
            if r.empty():
                continue
            if not r.iterations:
                continue
            if r.multiterm:
                extension = '.tt0'
            else:
                extension = ''

            maxiter = max(r.iterations.keys())

            vis = ','.join([os.path.basename(v).strip('.ms') for v in r.vis])

            field = None
            fieldname = None
            intent = None

            image_path = r.iterations[maxiter]['image'].replace('.image', '.image%s' % extension)

            LOG.info('Getting properties of %s for the weblog' % image_path)
            with casa_tools.ImageReader(image_path) as image:
                image_name = str(image.name(strippath=True))
                info = image.miscinfo()
                coordsys = image.coordsys()
                brightness_unit = image.brightnessunit()
                summary = image.summary()
                beam = image.restoringbeam()

                # While the image tool is open, read and cache the image
                # stats for use in the plot generation classes.
                stats = image.statistics(robust=False)

            # cache image statistics while we have them in scope.
            image_rms = stats.get('rms')[0]
            image_max = stats.get('max')[0]
            image_stats[image_path] = display.ImageStats(rms=image_rms, max=image_max)

            spw = info.get('virtspw', None)
            if spw is not None:
                nspwnam = info.get('nspwnam', None)
                spwnames = ','.join([info.get('spwnam%02d' % (i + 1)) for i in range(nspwnam)])
            else:
                spwnames = None
            if 'field' in info:
                field = '%s (%s)' % (info['field'], r.intent)
                fieldname = info['field']
                intent = r.intent

            coord_names = numpy.array(coordsys.names())
            coord_refs = coordsys.referencevalue(format='s')
            pol = coord_refs['string'][coord_names == 'Stokes'][0]

            coordsys.done()

            #
            # beam calculation
            #
            if 'beams' in beam:
                # 'beams' dict has results for each channel and
                # each pol product. For now, just use the first beam.
                beam = beam['beams']['*0']['*0']
                LOG.warning('%s has per-plane beam shape, displaying only first',
                            r.iterations[maxiter]['image'].replace('.image', '.image%s' % extension))

            #
            # beam value
            #
            try:
                beam_major = qaTool.convert(beam['major'], 'arcsec')
                beam_minor = qaTool.convert(beam['minor'], 'arcsec')
                row_beam = '%#.3g x %#.3g %s' % (beam_major['value'], beam_minor['value'], beam_major['unit'])
            except:
                row_beam = '-'

            #
            # beam position angle
            #
            try:
                beam_pa = qaTool.convert(beam['positionangle'], 'deg')
                row_beam_pa = casa_tools.quanta.tos(beam_pa, 1)
            except:
                row_beam_pa = '-'

            nchan = summary['shape'][3]
            width = qaTool.quantity(summary['incr'][3], summary['axisunits'][3])
            width = qaTool.convert(width, 'MHz')
            width = qaTool.tos(width, 4)

            # eff_ch_bw_MHz = qaTool.convert(r.eff_ch_bw, 'MHz')['value']
            # eff_ch_bw_text = '%.5g MHz (TOPO)' % (eff_ch_bw_MHz)
            # effective_channel_bandwidth = eff_ch_bw_text

            #
            # centre frequency heading
            #
            if nchan > 1:
                row_frequency_label = 'centre / rest frequency of cube'
            elif nchan == 1:
                row_frequency_label = 'centre frequency of image'
            else:
                row_frequency_label = 'centre frequency'

            #
            # centre and optionally rest frequency value
            #
            try:
                frequency_axis = list(summary['axisnames']).index('Frequency')
                center_frequency = summary['refval'][frequency_axis] + \
                    (summary['shape'][frequency_axis] / 2.0 - 0.5 - summary['refpix'][frequency_axis]) \
                    * summary['incr'][frequency_axis]
                centre_ghz = qaTool.convert('%s %s' % (center_frequency, summary['axisunits'][frequency_axis]), 'GHz')
                if nchan > 1:
                    job = casa_tasks.imhead(image_path, mode='get', hdkey='restfreq')
                    restfreq = job.execute(dry_run=False)
                    rest_ghz = qaTool.convert(restfreq, 'GHz')
                    row_frequency = '%s / %s (LSRK)' % (casa_tools.quanta.tos(centre_ghz, 4),
                                                        casa_tools.quanta.tos(rest_ghz, 4))
                else:
                    row_frequency = '%s (LSRK)' % casa_tools.quanta.tos(centre_ghz, 4)
            except:
                row_frequency = '-'

            #
            # residual peak / scaled MAD
            #
            with casa_tools.ImageReader(r.iterations[maxiter]['residual'] + extension) as residual:
                residual_stats = residual.statistics(robust=True)

            residual_robust_rms = residual_stats.get('medabsdevmed')[0] * 1.4826  # see CAS-9631
            if abs(residual_stats['min'])[0] > abs(residual_stats['max'])[0]:  # see CAS-10731 & PIPE-374
                residual_peak_value = residual_stats['min'][0]
            else:
                residual_peak_value = residual_stats['max'][0]
            residual_snr = (residual_peak_value / residual_robust_rms)
            row_residual_ratio = '%.2f' % residual_snr
            # preserve the sign of the largest magnitude value for printout
            LOG.info('{field} clean value of maximum absolute residual / scaled MAD'
                     ' = {peak:.12f} / {rms:.12f} = {ratio:.2f} '.format(field=field,
                                                                         peak=residual_peak_value,
                                                                         rms=residual_robust_rms,
                                                                         ratio=residual_snr))

            #
            # theoretical sensitivity
            #
            if 'VLA' in r.imaging_mode:
                row_sensitivity = '-'
            else:
                sp_str, sp_scale = utils.get_si_prefix(r.sensitivity, lztol=1)
                row_sensitivity = '{:.2g} {}'.format(r.sensitivity/sp_scale, sp_str+brightness_unit)

            #
            # Model image statistics for VLASS, PIPE-991
            #
            if 'VLASS-SE-CONT' in r.imaging_mode:
                model_image = r.iterations[maxiter]['model'] + extension
                with casa_tools.ImageReader(model_image) as image:
                    # In some cases there might not be any negative (or positive) pixels
                    try:
                        pos_flux = image.statistics(mask='"%s" > %f'%(model_image, 0.0), robust=False)['sum'][0]
                    except IndexError:
                        pos_flux = 0.0
                    row_model_pos_flux = '{:.2g} {}'.format(pos_flux, image.brightnessunit())
                    try:
                        neg_flux = image.statistics(mask='"%s" < %f'%(model_image, 0.0), robust=False)['sum'][0]
                    except IndexError:
                        neg_flux = 0.0
                    row_model_neg_flux = '{:.2g} {}'.format(neg_flux, image.brightnessunit())
                    # Create region for inner degree
                    # TODO: refactor because this code is partially a duplicate of vlassmasking.py
                    image_csys = image.coordsys()

                    xpixel = image_csys.torecord()['direction0']['crpix'][0]
                    ypixel = image_csys.torecord()['direction0']['crpix'][1]
                    xdelta = image_csys.torecord()['direction0']['cdelt'][0]  # in radians
                    ydelta = image_csys.torecord()['direction0']['cdelt'][1]  # in radians
                    onedeg = 1.0 * numpy.pi / 180.0  # conversion
                    widthdeg = 1.0  # degrees
                    boxhalfxwidth = numpy.abs((onedeg * widthdeg / 2.0) / xdelta)
                    boxhalfywidth = numpy.abs((onedeg * widthdeg / 2.0) / ydelta)

                    blcx = xpixel - boxhalfxwidth
                    blcy = ypixel - boxhalfywidth
                    if blcx < 0:
                        blcx = 0
                    if blcy < 0:
                        blcy = 0
                    blc = [blcx, blcy]

                    trcx = xpixel + boxhalfxwidth
                    trcy = ypixel + boxhalfywidth
                    if trcx > image.getchunk().shape[0]:
                        trcx = image.getchunk().shape[0]
                    if trcy > image.getchunk().shape[1]:
                        trcy = image.getchunk().shape[1]
                    trc = [trcx, trcy]

                    myrg = casa_tools.regionmanager
                    r1 = myrg.box(blc=blc, trc=trc)

                    y = image.getregion(r1)
                    row_model_flux_inner_deg = '{:.2g} {}'.format(y.sum(), image.brightnessunit())
            else:
                row_model_pos_flux = None
                row_model_neg_flux = None
                row_model_flux_inner_deg = None

            #
            # Major cycle statistics for VLASS
            #
            if 'VLASS-SE-CONT' in r.imaging_mode:
                row_nmajordone_per_iter = {}
                for iteration, iterdata in r.iterations.items():
                    iter_dict = {'cleanmask': iterdata['cleanmask'] if 'cleanmask' in iterdata.keys() else '',
                                 'nmajordone': iterdata['nmajordone'] if 'nmajordone' in iterdata.keys() else 0,
                                 'nminordone_array': iterdata['nminordone_array'] if 'nminordone_array'
                                                                                     in iterdata.keys() else None,
                                 'peakresidual_array': iterdata['peakresidual_array'] if 'peakresidual_array'
                                                                               in iterdata.keys() else None,
                                 'totalflux_array': iterdata['totalflux_array'] if 'totalflux_array'
                                                                                   in iterdata.keys() else None}
                    row_nmajordone_per_iter[iteration] = iter_dict
                row_nmajordone_total = numpy.sum([item['nmajordone'] for key, item in row_nmajordone_per_iter.items()])
                # Major cycle stats figure
                plotter = display.TcleanMajorCycleSummaryFigure(context, makeimages_result, row_nmajordone_per_iter)
                majorcycle_stat_plot = plotter.plot()
                tab_dict = {0: {'cols': ['iteration', 'cleanmask', 'nmajordone'],
                                  'nrow': len(row_nmajordone_per_iter.keys()),
                                  'iteration': [k for k in row_nmajordone_per_iter.keys()],
                                  'cleanmask': [item['cleanmask'] for iter, item in row_nmajordone_per_iter.items()],
                                  'nmajordone': [item['nmajordone'] for iter, item in row_nmajordone_per_iter.items()]
                                  }
                              }
            else:
                row_nmajordone_per_iter = None
                row_nmajordone_total = None
                majorcycle_stat_plot = None
                tab_dict = None

            #
            # Amount of flux inside and outside QL for VLASS-SE-CONT, PIPE-1081
            #
            if 'VLASS-SE-CONT' in r.imaging_mode and r.outmaskratio:
                row_outmaskratio_label = 'flux fraction outside clean mask'
                row_outmaskratio = '%#.3g' % r.outmaskratio
            else:
                row_outmaskratio_label = None
                row_outmaskratio = None

            #
            # clean iterations, for VLASS
            #
            if 'VLASS' in r.imaging_mode:
                row_iterdone = r.tclean_iterdone
                row_stopcode = r.tclean_stopcode
                row_stopreason = r.tclean_stopreason
            else:
                row_iterdone = None
                row_stopcode = None
                row_stopreason = None

            #
            # cleaning threshold cell
            #

            cleaning_threshold_label = 'cleaning threshold'

            if 'VLASS' in r.imaging_mode:
                if r.threshold:
                    threshold_quantity = utils.get_casa_quantity(r.threshold)
                    row_cleaning_threshold = '%.2g %s' % (threshold_quantity['value'], threshold_quantity['unit'])
                else:
                    row_cleaning_threshold = '-'
            elif 'VLA' in r.imaging_mode:
                cleaning_threshold_label = None
                row_cleaning_threshold = '-'
            else:
                if r.threshold:
                    threshold_quantity = qaTool.convert(r.threshold, 'Jy')
                    sp_str, sp_scale = utils.get_si_prefix(threshold_quantity['value'], lztol=1)
                    row_cleaning_threshold = '{:.2g} {}'.format(
                        threshold_quantity['value']/sp_scale, sp_str+brightness_unit)
                    if r.dirty_dynamic_range:
                        row_cleaning_threshold += '<br>Dirty DR: %.2g' % r.dirty_dynamic_range
                        row_cleaning_threshold += '<br>DR correction: %.2g' % r.DR_correction_factor
                    else:
                        row_cleaning_threshold += '<br>No DR information'
                else:
                    row_cleaning_threshold = '-'

            #
            # nsigma * initial and final scaled MAD for residual image, See PIPE-488
            #
            nsigma_final = r.iterations[maxiter]['imaging_params']['nsigma']

            # dirty image statistics (iter 0)
            with casa_tools.ImageReader(r.iterations[0]['residual'] + extension) as residual:
                initial_residual_stats = residual.statistics(robust=True)

            initial_nsigma_mad = nsigma_final * initial_residual_stats.get('medabsdevmed')[0] * 1.4826
            final_nsigma_mad = nsigma_final * residual_stats.get('medabsdevmed')[0] * 1.4826

            if (nsigma_final != 0.0):
                row_initial_nsigma_mad = '%#.3g %s' % (initial_nsigma_mad, brightness_unit)
                row_final_nsigma_mad = '%#.3g %s' % (final_nsigma_mad, brightness_unit)
            else:
                row_initial_nsigma_mad = '-'
                row_final_nsigma_mad = '-'

            # store values in log file
            LOG.info('n-sigma * initial scaled MAD of residual: %s %s' % (("%.12f" % initial_nsigma_mad, brightness_unit)
                                                                           if row_initial_nsigma_mad != '-'
                                                                           else (row_initial_nsigma_mad,"")))
            LOG.info('n-sigma * final scaled MAD of residual: %s %s' % (("%.12f" % final_nsigma_mad, brightness_unit)
                                                                           if row_final_nsigma_mad != '-'
                                                                           else (row_final_nsigma_mad,"")))

            #
            # heading for non-pbcor RMS cell
            #
            if nchan is None:
                non_pbcor_label = 'No RMS information'
            elif nchan == 1:
                non_pbcor_label = 'non-pbcor image RMS'
            else:
                non_pbcor_label = 'non-pbcor image RMS / RMS<sub>min</sub> / RMS<sub>max</sub>'

            #
            # value for non-pbcor RMS cell
            #
            if nchan is None or r.image_rms is None:
                row_non_pbcor = '-'
            else:
                sp_str, sp_scale = utils.get_si_prefix(r.image_rms, lztol=1)
                if nchan == 1:
                    row_non_pbcor = '{:.2g} {}'.format(r.image_rms/sp_scale, sp_str+brightness_unit)
                else:
                    row_non_pbcor = '{:.2g} / {:.2g} / {:.2g} {}'.format(
                        r.image_rms/sp_scale, r.image_rms_min/sp_scale, r.image_rms_max/sp_scale, sp_str+brightness_unit)

            #
            # pbcor image max / min cell
            #
            if r.image_max is None or r.image_min is None:
                row_pbcor = '-'
            else:
                sp_str, sp_scale = utils.get_si_prefix(r.image_max, lztol=0)
                row_pbcor = '{:.3g} / {:.3g} {}'.format(r.image_max/sp_scale,
                                                        r.image_min/sp_scale, sp_str+brightness_unit)

            #
            # fractional bandwidth calculation
            #
            try:
                frequency1 = summary['refval'][frequency_axis] + (-0.5 - summary['refpix'][frequency_axis]) * summary['incr'][frequency_axis]
                frequency2 = summary['refval'][frequency_axis] + (summary['shape'][frequency_axis] - 0.5 - summary['refpix'][frequency_axis]) * summary['incr'][frequency_axis]
                # full_bw_GHz = qaTool.convert(abs(frequency2 - frequency1), 'GHz')['value']
                fractional_bw = (frequency2 - frequency1) / (0.5 * (frequency1 + frequency2))
                fractional_bandwidth = '%.2g%%' % (fractional_bw * 100.)
            except:
                fractional_bandwidth = 'N/A'

            #
            # fractional bandwidth heading and value
            #
            nterms = r.multiterm if r.multiterm else 1
            if nchan is None:
                row_fractional_bw_label = 'No channel / width information'
                row_fractional_bw = '-'
            elif nchan > 1:
                row_fractional_bw_label = 'channels'
                if r.orig_specmode == 'repBW':
                    row_fractional_bw = '%d x %s (repBW, LSRK)' % (nchan, width)
                else:
                    row_fractional_bw = '%d x %s (LSRK)' % (nchan, width)
            else:
                row_fractional_bw_label = 'fractional bandwidth / nterms'
                row_fractional_bw = '%s / %s' % (fractional_bandwidth, nterms)

            #
            # aggregate bandwidth heading
            #
            if nchan == 1:
                row_bandwidth_label = 'aggregate bandwidth'
            else:
                row_bandwidth_label = None

            #
            # aggregate bandwidth value
            #
            aggregate_bw_GHz = qaTool.convert(r.aggregate_bw, 'GHz')['value']
            row_aggregate_bw = '%.3g GHz (LSRK)' % aggregate_bw_GHz
            row_aggregate_bw_num = '%.4g' % aggregate_bw_GHz

            #
            # VLA statistics (PIPE-764)
            #
            initial_nsigma_mad_label = None
            final_nsigma_mad_label = None

            if 'VLA' in r.imaging_mode:   # VLA and VLASS
                initial_nsigma_mad_label = 'n-sigma * initial scaled MAD of residual'
                final_nsigma_mad_label = 'n-sigma * final scaled MAD of residual'

            nsigma_label = None
            row_nsigma = None
            vis_amp_ratio_label = None
            row_vis_amp_ratio = None

            if 'VLA' == r.imaging_mode:  # VLA only
                nsigma_label = 'nsigma'
                row_nsigma = nsigma_final
                vis_amp_ratio_label = 'vis. amp. ratio'
                row_vis_amp_ratio = r.bl_ratio

            #
            #  score value
            #
            if r.qa.representative is not None:
                badge_class = rendererutils.get_badge_class(r.qa.representative)
                row_score = '<span class="badge %s">%0.2f</span>' % (badge_class, r.qa.representative.score)
            else:
                row_score = '-'

            #
            # check source fit parameters
            #
            if r.check_source_fit is not None:
                try:
                    chk_pos_offset = '%.2f +/- %.2f' % (r.check_source_fit['offset'], r.check_source_fit['offset_err'])
                except:
                    chk_pos_offset = 'N/A'
                try:
                    chk_frac_beam_offset = '%.2f +/- %.3f' % (r.check_source_fit['beams'], r.check_source_fit['beams_err'])
                except:
                    chk_frac_beam_offset = 'N/A'
                try:
                    chk_fitflux = '%d +/- %d' % (int(utils.round_half_up(r.check_source_fit['fitflux'] * 1000.)), int(utils.round_half_up(r.check_source_fit['fitflux_err'] * 1000.)))
                except:
                    chk_fitflux = 'N/A'

                if r.check_source_fit['fitflux'] != 0.0:
                    try:
                        chk_fitpeak_fitflux_ratio = '%.2f' % (r.check_source_fit['fitpeak'] / r.check_source_fit['fitflux'])
                    except:
                        chk_fitpeak_fitflux_ratio = 'N/A'
                else:
                    chk_fitpeak_fitflux_ratio = 'N/A'

                if r.check_source_fit['gfluxscale'] is not None and r.check_source_fit['gfluxscale_err'] is not None:
                    try:
                        chk_gfluxscale = '%.2f +/- %.2f' % (r.check_source_fit['gfluxscale'], r.check_source_fit['gfluxscale_err'])
                    except:
                        chk_gfluxscale = 'N/A'

                    if r.check_source_fit['gfluxscale_err'] != 0.0:
                        try:
                            chk_gfluxscale_snr = '%.2f' % (r.check_source_fit['gfluxscale'] / r.check_source_fit['gfluxscale_err'])
                        except:
                            chk_gfluxscale_snr = 'N/A'
                    else:
                        chk_gfluxscale_snr = 'N/A'

                    if r.check_source_fit['gfluxscale'] != 0.0:
                        try:
                            chk_fitflux_gfluxscale_ratio = '%.2f' % (r.check_source_fit['fitflux'] * 1000. / r.check_source_fit['gfluxscale'])
                        except:
                            chk_fitflux_gfluxscale_ratio = 'N/A'
                    else:
                        chk_fitflux_gfluxscale_ratio = 'N/A'

                else:
                    chk_gfluxscale = 'N/A'
                    chk_gfluxscale_snr = 'N/A'
                    chk_fitflux_gfluxscale_ratio = 'N/A'
            else:
                chk_pos_offset = 'N/A'
                chk_frac_beam_offset = 'N/A'
                chk_fitflux = 'N/A'
                chk_fitpeak_fitflux_ratio = 'N/A'
                chk_gfluxscale = 'N/A'
                chk_gfluxscale_snr = 'N/A'
                chk_fitflux_gfluxscale_ratio = 'N/A'

            if r.image_max is not None and r.image_rms is not None:
                try:
                    img_snr = '%.2f' % (r.image_max / r.image_rms)
                except:
                    img_snr = 'N/A'
            else:
                img_snr = 'N/A'

            cube_all_cont = r.cube_all_cont

            tclean_command = r.tclean_command

            # create our table row for this image.
            # Plot is set to None as we have a circular dependency: the row
            # needs the plot, but the plot generator needs the image_stats
            # cache. We will later set plot to the correct value.
            row = ImageRow(
                vis=vis,
                field=field,
                fieldname=fieldname,
                intent=intent,
                spw=spw,
                spwnames=spwnames,
                pol=pol,
                frequency_label=row_frequency_label,
                frequency=row_frequency,
                beam=row_beam,
                beam_pa=row_beam_pa,
                sensitivity=row_sensitivity,
                cleaning_threshold_label=cleaning_threshold_label,
                cleaning_threshold=row_cleaning_threshold,
                initial_nsigma_mad_label=initial_nsigma_mad_label,
                initial_nsigma_mad=row_initial_nsigma_mad,
                final_nsigma_mad_label=final_nsigma_mad_label,
                final_nsigma_mad=row_final_nsigma_mad,
                model_pos_flux=row_model_pos_flux,
                model_neg_flux=row_model_neg_flux,
                model_flux_inner_deg=row_model_flux_inner_deg,
                nmajordone_total=row_nmajordone_total,
                nmajordone_per_iter=row_nmajordone_per_iter,
                majorcycle_stat_plot=majorcycle_stat_plot,
                tab_dict=tab_dict,
                tab_url=None,
                residual_ratio=row_residual_ratio,
                non_pbcor_label=non_pbcor_label,
                non_pbcor=row_non_pbcor,
                pbcor=row_pbcor,
                score=row_score,
                fractional_bw_label=row_fractional_bw_label,
                fractional_bw=row_fractional_bw,
                aggregate_bw_label=row_bandwidth_label,
                aggregate_bw=row_aggregate_bw,
                aggregate_bw_num=row_aggregate_bw_num,
                nsigma_label=nsigma_label,
                nsigma=row_nsigma,
                vis_amp_ratio_label=vis_amp_ratio_label,
                vis_amp_ratio=row_vis_amp_ratio,
                image_file=image_name.replace('.pbcor', ''),
                nchan=nchan,
                plot=None,
                qa_url=None,
                outmaskratio=row_outmaskratio,
                outmaskratio_label=row_outmaskratio_label,
                iterdone=row_iterdone,
                stopcode=row_stopcode,
                stopreason=row_stopreason,
                chk_pos_offset=chk_pos_offset,
                chk_frac_beam_offset=chk_frac_beam_offset,
                chk_fitflux=chk_fitflux,
                chk_fitpeak_fitflux_ratio=chk_fitpeak_fitflux_ratio,
                img_snr=img_snr,
                chk_gfluxscale=chk_gfluxscale,
                chk_gfluxscale_snr=chk_gfluxscale_snr,
                chk_fitflux_gfluxscale_ratio=chk_fitflux_gfluxscale_ratio,
                cube_all_cont=cube_all_cont,
                tclean_command=tclean_command,
                result=r
            )
            image_rows.append(row)

        plotter = display.CleanSummary(context, makeimages_result, image_stats)
        plots = plotter.plot()

        plots_dict = make_plot_dict(plots)

        # construct the renderers so we know what the back/forward links will be
        temp_urls = (None, None, None)
        qa_renderers = [TCleanPlotsRenderer(context, results, row.result, plots_dict, row.image_file.split('.')[0], row.field, str(row.spw), row.pol, temp_urls, row.cube_all_cont)
                        for row in image_rows]
        qa_links = triadwise([renderer.path for renderer in qa_renderers])

        # PIPE-991: render tclean major cycle table, but only if tab_dict is specified (currently VLASS-SE-CONT)
        tab_renderer = [TCleanTablesRenderer(context, results, row.result,
                                             row.tab_dict, row.image_file.split('.')[0], row.field, str(row.spw),
                                             row.pol, temp_urls) if row.tab_dict else None for row in image_rows]
        tab_links = triadwise([renderer.path if renderer else None for renderer in tab_renderer])

        final_rows = []
        for row, renderer, qa_urls, tab_url in zip(image_rows, qa_renderers, qa_links, tab_links):
            prefix = row.image_file.split('.')[0]
            try:
                final_iter = sorted(plots_dict[prefix][row.field][str(row.spw)].keys())[-1]
                plot = get_plot(plots_dict, prefix, row.field, str(row.spw), final_iter, 'image')

                renderer = TCleanPlotsRenderer(context, results, row.result,
                                               plots_dict, prefix, row.field, str(row.spw), row.pol,
                                               qa_urls, row.cube_all_cont)
                with renderer.get_file() as fileobj:
                    fileobj.write(renderer.render())

                values = row._asdict()
                values['plot'] = plot
                values['qa_url'] = renderer.path

                # PIPE-991: render tclean major cycle table, but only if tab_dict exists (currently VLASS-SE-CONT)
                if any(tab_url):
                    tab_renderer = TCleanTablesRenderer(context, results, row.result,
                                                        row.tab_dict, prefix, row.field, str(row.spw), row.pol,
                                                        tab_url)
                    with tab_renderer.get_file() as fileobj:
                        fileobj.write(tab_renderer.render())
                    values['tab_url'] = tab_renderer.path

                new_row = ImageRow(**values)
                final_rows.append(new_row)
            except IOError as e:
                LOG.error(e)
            except:
                final_rows.append(row)

        chk_fit_rows = []
        for row in final_rows:
            if row.frequency is not None:
                chk_fit_rows.append((row.vis, row.fieldname, row.spw, row.aggregate_bw_num, row.chk_pos_offset, row.chk_frac_beam_offset, row.chk_fitflux, row.img_snr, row.chk_fitpeak_fitflux_ratio, row.chk_gfluxscale, row.chk_gfluxscale_snr, row.chk_fitflux_gfluxscale_ratio))
        chk_fit_rows = utils.merge_td_columns(chk_fit_rows, num_to_merge=2)

        ctx.update({
            'plots': plots,
            'plots_dict': plots_dict,
            'image_info': final_rows,
            'dirname': weblog_dir,
            'chk_fit_info': chk_fit_rows
        })


class TCleanPlotsRenderer(basetemplates.CommonRenderer):
    def __init__(self, context, makeimages_results, result, plots_dict, prefix, field, spw, pol, urls, cube_all_cont):
        super(TCleanPlotsRenderer, self).__init__('tcleanplots.mako', context, makeimages_results)

        # Set HTML page name
        # VLA needs a slightly different name for some cases
        # For that we need to check imaging_mode and specmode but we have to
        # protect against iteration errors for empty results.
        if not result.empty():
            if 'VLA' in result.imaging_mode and 'VLASS' not in result.imaging_mode and result.specmode == 'cont':
                # ms = context.observing_run.get_ms(result[0].results[0].vis[0])
                # band = ms.get_vla_spw2band()
                # band_spws = {}
                # for k, v in band.items():
                #     band_spws.setdefault(v, []).append(k)
                # for k, v in band_spws.items():
                #     for spw in spw.split(','):
                #         if int(spw) in v:
                #             band = k
                #             break
                # TODO: Not sure if a random number will work in all cases.
                #       While working on PIPE-129 it happened that this code
                #       was run 4 times for 2 targets. Better make sure the
                #       name is well defined (see new setup for per EB images below).
                outfile = '%s-field%s-pol%s-cleanplots-%d.html' % (prefix, field, pol, randint(1, 1e12))
            else:
                # The name needs to be unique also for the per EB imaging. Thus prepend the image name
                # which contains the OUS or EB ID.
                outfile = '%s-field%s-spw%s-pol%s-cleanplots.html' % (prefix, field, spw, pol)
        # TODO: Check if this is useful since the result is empty.
        else:
            outfile = '%s-field%s-spw%s-pol%s-cleanplots.html' % (prefix, field, spw, pol)

        # HTML encoded filenames, so can't have plus sign
        valid_chars = "_.-%s%s" % (string.ascii_letters, string.digits)
        self.path = os.path.join(self.dirname, filenamer.sanitize(outfile, valid_chars))

        # Determine whether this target was run with specmode = 'cube',
        # in which case the weblog will need to show the MOM0_FC and
        # MOM8_FC columns.
        show_mom0_8_fc = result.specmode == 'cube'

        if show_mom0_8_fc:
            colorder = ['pbcorimage', 'residual', 'cleanmask', 'mom0_fc', 'mom8_fc', 'spectra']
        else:
            colorder = ['pbcorimage', 'residual', 'cleanmask']

        self.extra_data = {
            'plots_dict': plots_dict,
            'prefix': prefix.split('.')[0],
            'field': field,
            'spw': spw,
            'colorder': colorder,
            'qa_previous': urls[0],
            'qa_next': urls[2],
            'base_url': os.path.join(self.dirname, 't2-4m_details.html'),
            'cube_all_cont': cube_all_cont
        }

    def update_mako_context(self, mako_context):
        mako_context.update(self.extra_data)


class TCleanTablesRenderer(basetemplates.CommonRenderer):
    def __init__(self, context, makeimages_results, result, table_dict, prefix, field, spw, pol, urls):
        super(TCleanTablesRenderer, self).__init__('tcleantables.mako', context, makeimages_results)

        # Set HTML page name
        outfile = '%s-field%s-spw%s-pol%s-cleantables.html' % (prefix, field, spw, pol)

        # HTML encoded filenames, so can't have plus sign
        valid_chars = "_.-%s%s" % (string.ascii_letters, string.digits)
        self.path = os.path.join(self.dirname, filenamer.sanitize(outfile, valid_chars))

        self.extra_data = {
            'table_dict': table_dict,
            'prefix': prefix.split('.')[0],
            'field': field,
            'spw': spw,
            'qa_previous': urls[0],
            'qa_next': urls[2],
            'base_url': os.path.join(self.dirname, 't2-4m_details.html'),
        }

    def update_mako_context(self, mako_context):
        mako_context.update(self.extra_data)


def get_plot(plots, prefix, field, spw, i, colname):
    try:
        return plots[prefix][field][spw][i][colname]
    except KeyError:
        return None


def make_plot_dict(plots):
    # Make the plots
    prefixes = sorted({p.parameters['prefix'] for p in plots})
    fields = sorted({p.parameters['field'] for p in plots})
    spws = sorted({p.parameters['virtspw'] for p in plots})
    iterations = sorted({p.parameters['iter'] for p in plots})
    types = sorted({p.parameters['type'] for p in plots})

    iteration_dim = lambda: collections.defaultdict(dict)
    spw_dim = lambda: collections.defaultdict(iteration_dim)
    field_dim = lambda: collections.defaultdict(spw_dim)
    plots_dict = collections.defaultdict(field_dim)
    for prefix in prefixes:
        for field in fields:
            for spw in spws:
                for iteration in iterations:
                    for t in types:
                        matching = [p for p in plots
                                    if p.parameters['prefix'] == prefix
                                    and p.parameters['field'] == field
                                    and p.parameters['virtspw'] == spw
                                    and p.parameters['iter'] == iteration
                                    and p.parameters['type'] == t]
                        if matching != []:
                            plots_dict[prefix][field][spw][iteration][t] = matching[0]

    return plots_dict


def triadwise(iterable):
    with_nones = [None] + list(iterable) + [None]
    "s -> (s0,s1,s2), (s1,s2,s3), (s2,s3,s4), ..."
    a, b, c = itertools.tee(with_nones, 3)
    next(b, None)
    next(c, None)
    next(c, None)
    return list(zip(a, b, c))
