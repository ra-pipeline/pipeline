import re
from typing import Union, Tuple

import numpy

import pipeline.domain.measures as measures
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.filenamer as filenamer
from pipeline.infrastructure import casa_tasks
from pipeline.infrastructure import casa_tools
from .imageparams_base import ImageParamsHeuristics

LOG = infrastructure.get_logger(__name__)


class ImageParamsHeuristicsVLA(ImageParamsHeuristics):

    def __init__(self, vislist, spw, observing_run, imagename_prefix='', proj_params=None, contfile=None,
                 linesfile=None, imaging_params={}):
        ImageParamsHeuristics.__init__(self, vislist, spw, observing_run, imagename_prefix, proj_params, contfile,
                                       linesfile, imaging_params)
        self.imaging_mode = 'VLA'

    def robust(self) -> float:
        """Tclean robust parameter heuristics.
        See PIPE-680 and CASR-543"""
        return 0.5

    def uvtaper(self, beam_natural=None, protect_long=None) -> Union[str, list]:
        """Tclean uvtaper parameter heuristics."""
        return []

    def uvrange(self, field=None, spwspec=None) -> tuple:
        """Tclean uvrange parameter heuristics.

        Restrict uvrange in case of very extended emission.

        If the amplitude of the shortest 5 per cent of the covered baselines
        is more than 2 times that of the 50-55 per cent baselines, then exclude
        the shortest 5 per cent of the baselines.

        See PIPE-681 and CASR-543.

        :param field:
        :param spwspec:
        :return: (None or string in the form of '> {x}klambda', where
            {x}=0.05*max(baseline), baseline ratio)
        """
        def get_mean_amplitude(vis, uvrange=None, axis='amplitude', field='', spw=None):
            stat_arg = {'vis': vis, 'uvrange': uvrange, 'axis': axis,
                        'useflags': True, 'field': field, 'spw': spw,
                        'correlation': 'LL,RR'}
            job = casa_tasks.visstat(**stat_arg)
            stats = job.execute(dry_run=False)  # returns stat in meter

            # Get means of spectral windows with data in the selected uvrange
            spws_means = [v['mean'] for (k, v) in stats.items() if numpy.isfinite(v['mean'])]

            # Determine mean and 95% percentile
            mean = numpy.mean(spws_means)
            percentile_95 = numpy.percentile(spws_means, 95)

            return (mean, percentile_95)

        if not field:
            field = ''
        if spwspec:
            spwids = sorted(set(spwspec.split(',')), key=int) # list
        else:
            spwids = self.spwids # set
        #
        qa = casa_tools.quanta
        #
        LOG.info('Computing uvrange heuristics for field="{:s}", spwsids={:s}'.format(
            field, ','.join([str(spw) for spw in spwids])))

        # Can it be that more than one visibility (ms file) is used?
        vis = self.vislist[0]
        ms = self.observing_run.get_ms(vis)

        # Determine the largest covered baseline in klambda. Assume that
        # the maximum baseline is associated with the highest frequency spw.
        light_speed = qa.getvalue(qa.convert(qa.constants('c'), 'm/s'))[0]
        max_mean_freq_Hz = 0.0   # spw mean frequency in the highest frequency spw
        real_spwids = []
        for spwid in spwids:
            real_spwid = self.observing_run.virtual2real_spw_id(spwid, ms)
            spw = ms.get_spectral_window(real_spwid)
            real_spwids.append(real_spwid)
            mean_freq_Hz = spw.mean_frequency.to_units(measures.FrequencyUnits.HERTZ)
            if float(mean_freq_Hz) > max_mean_freq_Hz:
                max_mean_freq_Hz = float(mean_freq_Hz)
                max_freq_spw = real_spwid
        # List of real spws
        real_spwids_str = ','.join([str(spw) for spw in real_spwids])

        # Check for maximum frequency
        if max_mean_freq_Hz == 0.0:
            LOG.warning("Highest frequency spw and largest baseline cannot be determined for spwids={:s}. "
                        "Using default uvrange.".format(','.join([str(spw) for spw in spwids])))
            return None, None
        # Get max baseline
        mean_wave_m = light_speed / max_mean_freq_Hz  # in meter
        job = casa_tasks.visstat(vis=vis, field=field, spw=str(max_freq_spw), axis='uvrange', useflags=False)
        uv_stat = job.execute(dry_run=False) # returns stat in meter
        max_bl = uv_stat['DATA_DESC_ID=%s' % max_freq_spw]['max'] / mean_wave_m

        # Define bin for lowest 5% of baselines (in wavelength units)
        uvll = 0.0
        uvul = 0.05 * max_bl

        uvrange_SBL = '{:0.1f}~{:0.1f}klambda'.format(uvll / 1000.0, uvul / 1000.0)

        try:
            mean_SBL, p95_SBL = get_mean_amplitude(vis=vis, uvrange=uvrange_SBL, field=field, spw=real_spwids_str)
        except Exception as e:
            LOG.warning(e)
            LOG.warning("Data selection error   Field: {!s}, spw: {!s}.   uvrange set to >0.0klambda ".format(
                str(field), real_spwids_str))
            return '>0.0klambda', 1.0

        # Range for  50-55% bin
        uvll = 0.5 * max_bl
        uvul = 0.5 * max_bl + 0.05 * max_bl
        uvrange_MBL = '{:0.1f}~{:0.1f}klambda'.format(uvll / 1000.0, uvul / 1000.0)
        try:
            mean_MBL, p95_MBL = get_mean_amplitude(vis=vis, uvrange=uvrange_MBL, field=field, spw=real_spwids_str)
        except Exception as e:
            LOG.warning(e)
            LOG.warning("Data selection error   Field: {!s}, spw: {!s}.   uvrange set to >0.0klambda ".format(
                str(field), real_spwids_str))
            return '>0.0klambda', 1.0

        # Compare amplitudes and decide on return value
        ratio = p95_SBL / mean_MBL

        # Report results
        LOG.info('Mean amplitude in uvrange bins: {:s} is {:0.2E}Jy, '
                 '{:s} is {:0.2E}Jy'.format(uvrange_SBL, mean_SBL, uvrange_MBL, mean_MBL))
        LOG.info('95 percentile in uvrange bins: {:s} is {:0.2E}Jy, '
                 '{:s} is {:0.2E}Jy'.format(uvrange_SBL, p95_SBL, uvrange_MBL, p95_MBL))
        LOG.info('Ratio between 95 percentile small baseline bin '
                 'and mean of middle baseline bin is {:0.2E}'.format(ratio))
        if ratio > 2.0:
            LOG.info('Selecting uvrange>{:0.1f}klambda to avoid very extended emission.'.format(0.05 * max_bl / 1000.0))
            return ">{:0.1f}klambda".format(0.05 * max_bl / 1000.0), ratio
        else:
            # Use complete uvrange
            return '>0.0klambda', ratio

    def pblimits(self, pb):
        """PB gain level at which to cut off normalizations (tclean parameter).
        See PIPE-674 and CASR-543
        """
        # pblimits used in pipeline tclean._do_iterative_imaging() method (eventually in cleanbox.py) for
        # computing statistics on residual image products.
        if (pb not in [None, '']):
            pblimit_image, pblimit_cleanmask = super().pblimits(pb)
        # used for setting CASA tclean task pblimit parameter in pipeline tclean.prepare() method
        else:
            pblimit_image = -0.1
            pblimit_cleanmask = 0.3

        return pblimit_image, pblimit_cleanmask

    def get_autobox_params(self, iteration: int, intent: str, specmode: str, robust: float) -> tuple:
        """VLA auto-boxing parameters.

        See PIPE-677 for TARGET-specific heuristic
        """
        sidelobethreshold = None
        noisethreshold = None
        lownoisethreshold = None
        negativethreshold = None
        minbeamfrac = None
        growiterations = None
        dogrowprune = None
        minpercentchange = None
        fastnoise = None

        if 'TARGET' in intent:
            # iter1, shallow clean, with pruning off, other automasking settings are the default
            if iteration in [1, 2]:
                sidelobethreshold = 2.0
                minbeamfrac = 0.0
            # iter2, same settings, but pruning is turned back on
            if iteration == 2:
                minbeamfrac = 0.3

        return (sidelobethreshold, noisethreshold, lownoisethreshold, negativethreshold, minbeamfrac, growiterations,
                dogrowprune, minpercentchange, fastnoise)

    def nterms(self, spwspec) -> Union[int, None]:
        """Tclean nterms parameter heuristics.

        Determine nterms depending on the fractional bandwidth.
        Returns 1 if the fractional bandwidth is < 10 per cent, 2 otherwise.

        See PIPE-679 and CASR-543
        """
        if spwspec is None:
            return None
        # Fractional bandwidth
        fr_bandwidth = self.get_fractional_bandwidth(spwspec)
        if fr_bandwidth >= 0.1:
            return 2
        else:
            return 1

    def deconvolver(self, specmode, spwspec) -> str:
        """Tclean deconvolver parameter heuristics.
        See PIPE-679 and CASR-543"""
        return 'mtmfs'

    def niter_correction(self, niter, cell, imsize, residual_max, threshold, residual_robust_rms, mask_frac_rad=0.0, intent='TARGET') -> int:
        """Adjustment of number of cleaning iterations due to mask size.

        Uses residual_robust_rms instead threshold to compute the new niter value.

        See PIPE-682 and CASR-543 and base class method for parameter description."""
        if mask_frac_rad == 0.0:
            # The motivation here is that while EVLA images can be large, only a small fraction of pixels
            # will typically have emission (for continuum images).
            mask_frac_rad = 0.05

        # VLA specific threshold
        # set to nsigma=4.0, rather than a hm_masking-specific nsigma value
        nsigma = 4.0
        threshold_vla = casa_tools.quanta.quantity(nsigma * residual_robust_rms, 'Jy')

        # Set allowed niter range
        max_niter = 1000000
        min_niter = 10000

        # Compute new niter
        new_niter = super().niter_correction(niter, cell, imsize, residual_max, threshold_vla, residual_robust_rms,
                                             mask_frac_rad=mask_frac_rad)
        # Apply limits
        if new_niter < min_niter:
            LOG.info('niter heuristic: Modified niter %d is smaller than lower limit (%d)' % (new_niter, min_niter))
            new_niter = min_niter
        elif new_niter > max_niter:
            LOG.info('niter heuristic: Modified niter %d is larger than upper limit (%d)' % (new_niter, max_niter))
            new_niter = max_niter
        return new_niter

    def niter_by_iteration(self, iteration, hm_masking, niter):
        """Tclean niter heuristic at each iteration.

        PIPE-677: niter=50 for iteration=1 of the VLA auto-masking tclean call.
        """
        if iteration == 1 and hm_masking == 'auto':
            new_niter = 50
            LOG.info('niter heuristic for iteration={} / hm_masking={}: Modified niter to {} from {}'.format(iteration,
                     hm_masking, new_niter, niter))
            return new_niter
        else:
            return niter

    def specmode(self) -> str:
        """Tclean specmode parameter heuristics.
        See PIPE-683 and CASR-543"""
        return 'cont'

    def nsigma(self, iteration, hm_nsigma, hm_masking):
        """Tclean nsigma parameter heuristics."""
        if hm_nsigma:
            return hm_nsigma
        else:
            # PIPE-678: VLA 'none' set to 5.0
            # PIPE-677: VLA automasking set to 4.0, reduce from 5.0
            if hm_masking == 'auto':
                return 4.0
            else:
                return 5.0

    def tclean_stopcode_ignore(self, iteration, hm_masking):
        """Tclean stop code(s) to be ignored for warning messages.

        PIPE-677: We will ignore tclean_stopcode=1 (i.e., niter is reached) for iter1 of the VLA automasking sequence.
        """
        if iteration == 1 and hm_masking == 'auto':
            return [1]
        return []

    def keep_iterating(self, iteration, hm_masking, tclean_stopcode, dirty_dynamic_range, residual_max, residual_robust_rms, field, intent, spw, specmode):
        """Determine if another tclean iteration is necessary.

        automasking mode (PIPE-677):
            VLA auto-masking heuristics for TARGET performs two-stage iterations with slightly different auto-multithresh parameters
            iteration=0: keep_iteration=True
            iteration=1: 
                stopcode=0 (no minor or major cycles?): keep_iteration=False
                stopcode=1 (iteration limit): keep_iteration=True
                stopcode=5,6 (doesn't converge): keep_iteration=False
                stopcode=7 (no mask generated from automask): keep_iteration=False
                stopcode=others: keep_iteration=True
            iteration>=2: keep_iteration=False
        
        other modes:
            iteration=0: keep_iteration=True
            iteration=1: keep_iteration=False
        """
        if iteration == 0:
            return True, hm_masking
        elif iteration == 1 and hm_masking == 'auto' and 'TARGET' in intent:
            if tclean_stopcode in [5, 6, 7]:
                return False, hm_masking
            else:
                return True, hm_masking
        else:
            return False, hm_masking

    def threshold(self, iteration: int, threshold: Union[str, float], hm_masking: str) -> Union[str, float]:
        """Tclean threshold parameter heuristics.
        See PIPE-678 and CASR-543"""
        if iteration == 0 or hm_masking in ['none']:
            return '0.0mJy'
        else:
            return threshold

    def imsize(self, fields, cell, primary_beam, sfpblimit=None, max_pixels=None,
               centreonly=False, vislist=None, spwspec=None) -> Union[list, int]:
        """
        Image size heuristics for single fields and mosaics. The pixel count along x and y image dimensions
        is determined by the cell size, primary beam size and the spread of phase centers in case of mosaics.

        Frequency dependent image size may be computed for VLA imaging.

        For single fields, 18 GHz and above FOV extends to the first minimum of the primary beam Airy pattern.
        Below 18 GHz, FOV extends to the second minimum (incorporating the first sidelobes).

        See PIPE-675 and CASR-543

        :param fields: list of comma separated strings of field IDs per MS.
        :param cell: pixel (cell) size in arcsec.
        :param primary_beam: primary beam width in arcsec.
        :param sfpblimit: single field primary beam response. If provided then imsize is chosen such that the image
            edge is at normalised primary beam level equals to sfpblimit.
        :param max_pixels: maximum allowed pixel count, integer. The same limit is applied along both image axes.
        :param centreonly: if True, then ignore the spread of field centers.
        :param vislist: list of visibility path string to be used for imaging. If not set then use all visibilities
            in the context.
        :param spwspec: ID list of spectral windows used to create image product. List or string containing comma
            separated spw IDs list.
        :return: two element list of pixel count along x and y image axes.
        """
        if spwspec is not None:
            if type(spwspec) is not str:
                spwspec = ",".join(spwspec)
            freq_limits = self.get_min_max_freq(spwspec)
            # 18 GHz and above (K, Ka, Q VLA bands)
            if freq_limits['abs_min_freq'] >= 1.79e10:
                # equivalent to first minimum of the Airy diffraction pattern; m = 1.22.
                sfpblimit = 0.294
            else:
                # equivalent to second minimum of the Airy diffraction pattern; m = 2.233 in theta = m*lambda/D
                sfpblimit = 0.016

        return super().imsize(fields, cell, primary_beam, sfpblimit=sfpblimit, max_pixels=max_pixels,
                              centreonly=centreonly, vislist=vislist)

    def imagename(self, output_dir=None, intent=None, field=None, spwspec=None, specmode=None, band=None, datatype: str = None) -> str:
        try:
            nameroot = self.imagename_prefix
            if nameroot == 'unknown':
                nameroot = 'oussid'
            # need to sanitize the nameroot here because when it's added
            # to filenamer as an asdm, os.path.basename is run on it with
            # undesirable results.
            nameroot = filenamer.sanitize(nameroot)
        except:
            nameroot = 'oussid'
        namer = filenamer.Image()
        namer._associations.asdm(nameroot)

        if output_dir:
            namer.output_dir(output_dir)

        namer.stage('STAGENUMBER')
        if intent:
            namer.intent(intent)
        if field:
            namer.source(field)
        if specmode != 'cont' and spwspec:
            # find all the spwids present in the list
            p = re.compile(r"[ ,]+(\d+)")
            spwids = p.findall(' %s' % spwspec)
            spwids = list(set(spwids))
            spw = '_'.join(map(str, sorted(map(int, spwids))))
            namer.spectral_window(spw)
        if specmode == 'cont' and band:
            namer.band('{}_band'.format(band))
        if specmode:
            namer.specmode(specmode)
        if datatype:
            namer.datatype(datatype)

        # filenamer returns a sanitized filename (i.e. one with
        # illegal characters replace by '_'), no need to check
        # the name components individually.
        imagename = namer.get_filename()
        return imagename
