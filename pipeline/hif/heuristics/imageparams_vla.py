import os
import re
import traceback
from typing import Optional, Union

import numpy as np

import pipeline.domain.measures as measures
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.filenamer as filenamer
from pipeline.infrastructure import casa_tasks, casa_tools
from pipeline.infrastructure.tablereader import find_EVLA_band
import pipeline.infrastructure.utils as utils

from .auto_selfcal.selfcal_helpers import estimate_near_field_SNR, estimate_SNR
from .imageparams_base import ImageParamsHeuristics

LOG = infrastructure.get_logger(__name__)


class ImageParamsHeuristicsVLA(ImageParamsHeuristics):

    def __init__(self, vislist, spw, observing_run, imagename_prefix='', proj_params=None, contfile=None,
                 linesfile=None, imaging_params={}, processing_intents={}):
        ImageParamsHeuristics.__init__(self, vislist, spw, observing_run, imagename_prefix, proj_params, contfile,
                                       linesfile, imaging_params, processing_intents)
        self.imaging_mode = 'VLA'

    def robust(self, specmode=None) -> float:
        """Tclean robust parameter heuristics.
        See PIPE-680 and CASR-543"""
        if specmode in ('cube', 'repBW'):
            # PIPE-1346: use robust=2.0 for VLA cube imaging.
            return 2.0
        else:
            return 0.5

    def uvtaper(self, beam_natural=None, protect_long=None, beam_user=None, tapering_limit=None, repr_freq=None) -> Union[str, list]:
        """Tclean uvtaper parameter heuristics."""
        return []

    def uvrange(self, field=None, spwspec=None, specmode=None) -> tuple:
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
        if specmode in ('cube', 'repBW'):
            # PIPE-1346: do not restrict uvrange for VLA cube imaging.
            return None, None

        def get_mean_amplitude(vis, uvrange=None, axis='amplitude', field='', spw=None):
            stat_arg = {'vis': vis, 'uvrange': uvrange, 'axis': axis,
                        'useflags': True, 'field': field, 'spw': spw,
                        'correlation': 'LL,RR', 'doquantiles': 'False'}
            job = casa_tasks.visstat(**stat_arg)
            stats = job.execute()  # returns stat in meter

            # Get means of spectral windows with data in the selected uvrange
            spws_means = [v['mean'] for (k, v) in stats.items() if np.isfinite(v['mean'])]

            # Determine mean and 95% percentile
            mean = np.mean(spws_means)
            percentile_95 = np.percentile(spws_means, 95)

            # PIPE-2370: convert np.float64 to a native float for better weblog presentations.
            return (float(mean), float(percentile_95))

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
        job = casa_tasks.visstat(vis=vis, field=field, spw=str(max_freq_spw),
                                 axis='uvrange', useflags=False, doquantiles=False)
        uv_stat = job.execute() # returns stat in meter
        max_bl = uv_stat['DATA_DESC_ID=%s' % max_freq_spw]['max'] / mean_wave_m

        # Define bin for lowest 5% of baselines (in wavelength units)
        uvll = 0.0
        uvul = 0.05 * max_bl

        uvrange_SBL = '{:0.1f}~{:0.1f}klambda'.format(uvll / 1000.0, uvul / 1000.0)

        try:
            mean_SBL, p95_SBL = get_mean_amplitude(vis=vis, uvrange=uvrange_SBL, field=field, spw=real_spwids_str)
        except Exception as e:
            LOG.debug(e)
            LOG.info("Data selection error   Field: {!s}, spw: {!s}.   uvrange set to >0.0klambda ".format(
                str(field), real_spwids_str))
            return '>0.0klambda', 1.0

        # Range for  50-55% bin
        uvll = 0.5 * max_bl
        uvul = 0.5 * max_bl + 0.05 * max_bl
        uvrange_MBL = '{:0.1f}~{:0.1f}klambda'.format(uvll / 1000.0, uvul / 1000.0)
        try:
            mean_MBL, p95_MBL = get_mean_amplitude(vis=vis, uvrange=uvrange_MBL, field=field, spw=real_spwids_str)
        except Exception as e:
            LOG.debug(e)
            LOG.info("Data selection error   Field: {!s}, spw: {!s}.   uvrange set to >0.0klambda ".format(
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

    def pblimits(self, pb: Union[None, str], specmode: Optional[str] = None):
        """PB gain level at which to cut off normalizations (tclean parameter).
        See PIPE-674 and CASR-543
        """
        # pblimits used in pipeline tclean._do_iterative_imaging() method (eventually in cleanbox.py) for
        # computing statistics on residual image products.
        if (pb not in [None, '']):
            pblimit_image, pblimit_cleanmask = super().pblimits(pb, specmode=specmode)
        # used for setting CASA tclean task pblimit parameter in pipeline tclean.prepare() method
        else:
            if specmode == 'cube':
                pblimit_image = 0.2
            else:
                pblimit_image = -0.1
            pblimit_cleanmask = 0.3

        return pblimit_image, pblimit_cleanmask

    def get_autobox_params(
        self,
        iteration: int,
        intent: str,
        specmode: str,
        robust: float,
        rms_multiplier: Optional[Union[int, float]] = None,
    ) -> tuple:
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

        if "TARGET" in intent:
            # iter1, shallow clean, with pruning off, other automasking settings are the default
            if iteration in [1, 2]:
                minbeamfrac = 0.0
                sidelobethreshold = 2.0
                noisethreshold = 5.0
                lownoisethreshold = 1.5
                negativethreshold = 0.0
            # PIPE-677: iter2, same settings, but pruning is turned back on
            # PIPE-1878: explicitly set noisethreshold/lownoisethreshold values for the nfrms/rms-ratio-based scaling
            if iteration == 2:
                minbeamfrac = 0.3

        # PIPE-1878: adjust the threshold based on a rms scaling factor, e.g. the ratio of rms values from ROIs vs rms from entire image
        if rms_multiplier is not None:
            if noisethreshold is not None:
                noisethreshold *= rms_multiplier
            if lownoisethreshold is not None:
                lownoisethreshold *= rms_multiplier
            if negativethreshold is not None:
                negativethreshold *= rms_multiplier

        return (
            sidelobethreshold,
            noisethreshold,
            lownoisethreshold,
            negativethreshold,
            minbeamfrac,
            growiterations,
            dogrowprune,
            minpercentchange,
            fastnoise,
        )

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

    def deconvolver(self, specmode, spwspec, intent: str = '', stokes: str = '') -> str:
        """Tclean deconvolver parameter heuristics.
        
        See PIPE-679 and CASR-543
        """
        if specmode == 'cube':
            return 'hogbom'
        else:
            return 'mtmfs'

    def _get_vla_band(self, spwspec):
        """Get VLA band from spwspec, assuming spwspec from the same band."""
        vla_band = None
        if isinstance(spwspec, str) and spwspec != '':
            freq_limits = self.get_min_max_freq(spwspec)
            mean_freq_hz = (freq_limits['abs_max_freq'] + freq_limits['abs_min_freq'])/2.0
            vla_band = find_EVLA_band(mean_freq_hz)
        return vla_band

    def gridder(self, intent: str, field: str, spwspec: Optional[str] = None) -> str:
        """Determine the appropriate tclean gridder parameter for VLA.

        Args:
            intent (str): The intent of the observation.
            field (str): The field of the observation.
            spwspec (str, optional): The spectral window specification. Defaults to None.

        Returns:
            str: The selected gridder parameter.
        """

        # Default gridder selection.
        gridder_select = 'standard'

        # The heuristic which decides whether this is a mosaic or not.
        field_str_list = self.field(intent, field)
        is_mosaic = self._is_mosaic(field_str_list)

        # Adjust gridder selection based on mosaic status and antenna diameters.
        # Not really necessary for VLA, but as a placeholder for PIPE-684.
        if is_mosaic or (len(self.antenna_diameters()) > 1):
            gridder_select = 'mosaic'

        # PIPE-1641: switch to gridder='wproject' for L and S band sci-target imaging
        # PIPE-2225/2230: disable the L/S-band wproject heuristics for efficient imaging by default,
        # but expose it as an option (allow_wproject)
        use_wproject = self.imaging_params.get('allow_wproject', False)
        if use_wproject:
            vla_band = self._get_vla_band(spwspec)
            if vla_band in ['L', 'S'] and 'TARGET' in intent:
                gridder_select = 'wproject'

        return gridder_select

    def wprojplanes(self, gridder=None, spwspec=None):
        """Tclean wprojplanes parameter heuristics for VLA."""

        wplanes = None
        vla_band = self._get_vla_band(spwspec)

        # PIPE-1641: heuristics for wprojplanes when gridder='wproject'
        # note that the scaling logic inside this block is only valid for L-/S-band data.
        if gridder == 'wproject' and vla_band in ['L', 'S']:

            # calculate 75th percentile uv distance
            uvrange_pct75_meter, _ = self.calc_percentile_baseline_length(75.)
            # normalized to S-band A-config
            wplanes = 384
            # scaled by 75th percentile uv distance divided by A-config value
            wplanes = wplanes * uvrange_pct75_meter/20000.0

            if vla_band == 'L':
                # compensate for 1.5 GHz being 2x longer than 3 GHz
                wplanes = wplanes*2.0
            wplanes = int(np.ceil(wplanes))
        return wplanes

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

    def nmajor(self, iteration: int) -> Union[None, int]:
        """Tclean nmajor parameter heuristics."""
        if iteration == 0:
            return None
        else:
            # PIPE-2495: default value of nmajor=300 for all imaging stages of the VLA workflow
            return 300

    def specmode(self) -> str:
        """Tclean specmode parameter heuristics.
        See PIPE-683 and CASR-543"""
        return 'cont'

    def nsigma(self, iteration, hm_nsigma, hm_masking, rms_multiplier=None):
        """Tclean nsigma parameter heuristics."""
        if hm_nsigma:
            return hm_nsigma
        else:
            # PIPE-678: VLA 'none' set to 5.0
            # PIPE-677: VLA automasking set to 4.0, reduce from 5.0
            if hm_masking == 'auto':
                if rms_multiplier is not None:
                    return 4.0 * rms_multiplier
                else:
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
               centreonly=False, vislist=None, spwspec=None, intent: str = '', joint_intents: str = '',
               specmode=None) -> Union[list, int]:
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
        :param intent: field/source intent
        :param joint_intents: stage intents
        :return: two element list of pixel count along x and y image axes.
        """
        if specmode in ('cube', 'repBW'):
            return super().imsize(fields, cell, primary_beam, sfpblimit=sfpblimit, max_pixels=max_pixels,
                                  centreonly=centreonly, vislist=vislist, intent=intent, specmode=specmode)
        else:
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
                                  centreonly=centreonly, vislist=vislist, intent=intent, specmode=specmode)

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

    def get_sensitivity(self, ms_do, field, intent, spw, chansel, specmode, cell, imsize, weighting, robust, uvtaper):
        """Correct the VLA theoretical sensitivity for the Hanning smoothed SPW.

        PIPE-2131: Hanning smoothing introduces noise correlation between adjacent visibility channels,
        which is not accounted for in the statwt() outcome. Here, we introduce a scaling factor of 1.633 
        to correct this effect in sensitivity calculation.

        Args:
            ms_do (object): Measurement set data object.
            field (str): Field selection.
            intent (str): Observation intent.
            spw (int): Spectral window.
            chansel (str): Channel selection.
            specmode (str): Spectral mode.
            cell (float): Cell size.
            imsize (int): Image size.
            weighting (str): Weighting scheme.
            robust (float): Robust parameter for weighting.
            uvtaper (str): UV taper.

        Returns:
            tuple: Corrected sensitivity values.
        """
        ret = super().get_sensitivity(ms_do, field, intent, spw, chansel, specmode, cell, imsize, weighting, robust, uvtaper)
        ret = list(ret)

        # PIPE-2311: scale continuum theoretical noise for hanning-smoothed spws.
        if specmode in ('mfs', 'cont'):
            real_spwid = self.observing_run.virtual2real_spw_id(spw, ms_do)
            with casa_tools.TableReader(ms_do.name + '/SPECTRAL_WINDOW') as table:
                if 'OFFLINE_HANNING_SMOOTH' in table.colnames():
                    is_smoothed = table.getcol('OFFLINE_HANNING_SMOOTH')[real_spwid]
                    if is_smoothed:
                        LOG.info(
                            'EB %s spw %s has been Hanning-smoothed; multiplying apparent sensitivity return by a factor of 1.633.',
                            ms_do.name, real_spwid)
                        ret[0] *= 1.633
                    else:
                        LOG.info('EB %s spw %s has not been Hanning-smoothed; assuming the visibility noise is channel-independent.',
                                 ms_do.name, real_spwid)
                else:
                    LOG.warning(
                        'No offline Hanning smooth history is detected in EB %s spw %s; no correction for the VLA theoretical sensitivity.',
                        ms_do.name, real_spwid)

        return tuple(ret)

    def restfreq(
            self, specmode: Optional[str] = None, nchan: Optional[int] = None, start: Optional[Union[str, float]] = None,
            width: Optional[Union[str, float]] = None) -> Optional[str]:
        """Determine the rest frequency for CASA/tclean.

        VLA often lacks valid rest frequencies in the SOURCE subtable. Therefore, the SPW center frequency
        is used as the rest frequency when certain conditions are met.

        Args:
            specmode (Optional[str]): The spectral mode, typically 'cube' or 'repBW'.
            nchan (Optional[int]): Number of channels.
            start (Optional[Union[str, float]]): Start frequency, expected to be a string with units (e.g., 'Hz').
            width (Optional[Union[str, float]]): Width frequency, expected to be a string with units (e.g., 'Hz').

        Returns:
            Optional[str]: The calculated rest frequency in GHz if conditions are met; otherwise, None.
        """
        rest_freq = None

        if specmode in ('cube', 'repBW'):
            if all(isinstance(param, str) and 'Hz' in param for param in (start, width)) and nchan not in (None, -1):
                try:
                    qa = casa_tools.quanta
                    start_hz = qa.convert(start, 'Hz')['value']
                    width_hz = qa.convert(width, 'Hz')['value']
                    center_freq_hz = start_hz + (nchan // 2) * width_hz
                    rest_freq = f'{center_freq_hz / 1e9:.10f}GHz'
                    LOG.info('Use the cube center frequency as the rest frequency for VLA cube imaging: %s', rest_freq)
                except Exception:
                    LOG.warning('Failed to derive the heuristics-based rest frequency for VLA cube imaging.')
                    traceback_msg = traceback.format_exc()
                    LOG.debug(traceback_msg)
            else:
                LOG.warning('Cannot derive the heuristics-based rest frequency for VLA cube imaging.')

        return rest_freq

    def get_nfrms_multiplier(self, iteration: int, intent: str, specmode: str, imagename: str) -> Optional[float]:
        """PIPE-1878: Determine the nfrms-based threshold multiplier for TARGET imaging.

        Args:
            iteration (int): The iteration number.
            intent (str): The intent.
            specmode (str): The spectral mode.
            imagename (str): The name of the shallowly cleaned image to calculate the multiplier.

        Returns:
            float: The multiplier for the nfrms-based threshold.
        """
        nfrms_multiplier = None

        # PIPE-1878: utilize the nfrms/rms ratio inherited from self-calibration final imaging
        if iteration > 0 and specmode == "cont" and "TARGET" in intent:
            nfrms_multiplier = self.imaging_params.get("nfrms_multiplier", None)
            if nfrms_multiplier is not None:
                LOG.info(
                    "Use the selfcal-final nfrms multiplier for TARGET imaging (%s): %s",
                    imagename,
                    nfrms_multiplier,
                )
                return nfrms_multiplier

        if iteration == 2 and specmode in ('cont', 'mfs') and 'TARGET' in intent:
            image_name = imagename if os.path.exists(imagename) else imagename + \
                '.tt0' if os.path.exists(imagename + '.tt0') else None

            if image_name:
                try:
                    with casa_tools.ImageReader(image_name) as ia:
                        qa = casa_tools.quanta
                        restfreq_hz = qa.convert(ia.coordsys().restfrequency(), 'Hz')['value'][0]

                    bl_pt5_m, _ = self.calc_percentile_baseline_length(5.)
                    c_mps = 299792458.
                    lambda_m = c_mps / restfreq_hz

                    las_as = 0.6 * (lambda_m / bl_pt5_m) * 180 / np.pi * 3600
                    _, rms = estimate_SNR(image_name)
                    _, nfrms = estimate_near_field_SNR(image_name, las=las_as)

                    LOG.info('The ratio of nf_rms and rms before TARGET imaging (%s): %s', imagename, nfrms / rms)
                    mask_name = imagename.rsplit('.image', 1)[0] + '.mask'

                    nfrms_multiplier = max(nfrms / rms, 1.0)
                    LOG.info('The nfrms multiplier for TARGET imaging (%s): %s', imagename, nfrms_multiplier)

                    LOG.info('Remove any clean mask inherited from TARGET .iter1 imaging.')
                    casa_tasks.rmtree(mask_name, ignore_errors=True).execute()

                except Exception as err:
                    LOG.info('NF rms threshold scaling heuristics failed: %s', str(err))
                    LOG.info(traceback.format_exc())

            if nfrms_multiplier is None:
                LOG.warning(
                    'Failed to calculate the nf_rms/rms ratio before TARGET imaging (%s); '
                    'will not assign a scaling factor for nsigma and auto-multithresh threshold values.', imagename
                )

        return nfrms_multiplier

    def representative_target(self) -> tuple[tuple[str | None, any, any], str, int, any, str, bool, str, str, str, str]:
        """Determine representative target source and observing performance parameters.

        Selects a representative source from TARGET intents, falling back to calibration
        intents if necessary. Computes the least flagged spectral window and derives
        frequency/bandwidth parameters for image heuristics.

        Returns:
            Tuple containing representative target info, source name, virtual SPW ID,
            frequency, bandwidth mode, real target flag, and angular resolution parameters.

        Raises:
            Exception: If no suitable representative target can be found from any intent.
        """
        cqa = casa_tools.quanta

        repr_ms = self.observing_run.get_ms(self.vislist[0])

        # PIPE-2625: VLA lacks real representative source/frequency/bandwidth info
        # ALMA provides repr_ms.representative_target tuple, but VLA returns (None, None, None)
        repr_target = (None, None, None)
        reprBW_mode = 'nbin'
        real_repr_target = False

        # Select representative source from TARGET intents
        target_sources = [s.name for s in repr_ms.sources if 'TARGET' in s.intents]

        if not target_sources:
            if repr_target[0] == 'none':
                LOG.warning('No TARGET intent found. Selecting from calibration intents.')
                # Try calibration intents in priority order
                for repr_intent in ['PHASE', 'CHECK', 'AMPLITUDE', 'FLUX', 'BANDPASS']:
                    target_sources = [s.name for s in repr_ms.sources if repr_intent in s.intents]
                    if target_sources:
                        break

                if not target_sources:
                    raise Exception('Cannot select representative target from any calibration intent.')
            else:
                raise Exception('Cannot select representative target from TARGET intent.')

        repr_source = target_sources[0]

        # Determine least flagged spectral window
        job = casa_tasks.flagdata(vis=repr_ms.name, field=utils.fieldname_for_casa(repr_source), mode='summary')
        flag_stats = job.execute()
        flag_stats_spw = flag_stats['spw']

        spw_flagfrac = {
            spw: flag_stats_spw[str(spw.id)]['flagged'] / flag_stats_spw[str(spw.id)]['total']
            for spw in repr_ms.get_spectral_windows() if str(spw.id) in flag_stats_spw
        }

        # Select SPW with minimum flagging fraction
        repr_spw_obj = min(spw_flagfrac, key=spw_flagfrac.get)
        repr_spw = repr_spw_obj.id

        # Get central channel for frequency/bandwidth calculation
        repr_chan_obj = repr_spw_obj.channels[repr_spw_obj.num_channels // 2]
        repr_freq = cqa.quantity(
            float(repr_chan_obj.getCentreFrequency().convert_to(measures.FrequencyUnits.HERTZ).value), 'Hz'
        )
        repr_bw = cqa.quantity(float(repr_chan_obj.getWidth().convert_to(measures.FrequencyUnits.HERTZ).value), 'Hz')
        repr_target = (repr_source, repr_freq, repr_bw)

        # Default imaging parameters for VLA
        minAcceptableAngResolution = '0.0arcsec'
        maxAcceptableAngResolution = '0.0arcsec'
        maxAllowedBeamAxialRatio = '0.0'
        sensitivityGoal = '0.0mJy'

        LOG.info(
            'No representative target for VLA. Choosing %s as representative source '
            'and SPW=%s as representative spwid, based on the imaging heuristics.',
            repr_source,
            repr_spw,
        )

        virtual_repr_spw = self.observing_run.real2virtual_spw_id(repr_spw, repr_ms)

        return (
            repr_target,
            repr_source,
            virtual_repr_spw,
            repr_freq,
            reprBW_mode,
            real_repr_target,
            minAcceptableAngResolution,
            maxAcceptableAngResolution,
            maxAllowedBeamAxialRatio,
            sensitivityGoal,
        )

    def check_psf(self, psf_name, field, spw):
        """Check for bad psf fits.

        PIPE-2603: always enable the "medium" beam evaluation.
        """
        return True

    @staticmethod
    def find_good_medianbeam(psf_filename: str, field: str, spw: str):
        """Find outlier beams and calculate a good "median" restoring beam recommendation.

        Analyzes per-channel restoring beams in the PSF image to identify the beam closest to the median
        major axis size. This approach helps find a representative beam while avoiding outliers that
        could skew the common beam calculation.

        Args:
            psf_filename: Path to the PSF image file containing per-channel beam information.

        Returns:
            A tuple containing:
            - The median beam dictionary with beam parameters (major, minor, positionangle)
            - Array of channel numbers with invalid beams (currently returns empty array)

        Note:
            The current implementation returns an empty list for bad channels. This may be enhanced
            in future versions to identify and return problematic beam channels.
            PIPE-2758: Decided not to use the median beam algorithm for restoring beam as the absence 
            of convolution of residual map in planes with per-plane beam > median beam could 
            potentially cause flux scaling issues in those planes.
        """
        cqa = casa_tools.quanta

        with casa_tools.ImageReader(psf_filename) as image:
            allbeams = image.restoringbeam()
            commonbeam = image.commonbeam()

        nchan = allbeams['nChannels']

        # Pre-allocate arrays for beam parameters
        bmajor = np.zeros(nchan, dtype=np.float64)
        bminor = np.zeros(nchan, dtype=np.float64)
        bpa = np.zeros(nchan, dtype=np.float64)

        LOG.info('Per-plane restoring beam analysis for %s (channels: %d)', psf_filename, nchan)

        # Extract beam parameters for each channel
        for chan_idx in range(nchan):
            beam_key = f'*{chan_idx}'
            beam_data = allbeams['beams'][beam_key]['*0']

            # Convert beam parameters to consistent units
            major_arcsec = cqa.convert(cqa.quantity(beam_data['major']), 'arcsec')['value']
            minor_arcsec = cqa.convert(cqa.quantity(beam_data['minor']), 'arcsec')['value']
            pa_deg = cqa.convert(cqa.quantity(beam_data['positionangle']), 'deg')['value']

            # Store converted values
            bmajor[chan_idx] = major_arcsec
            bminor[chan_idx] = minor_arcsec
            bpa[chan_idx] = pa_deg

            LOG.info('Channel %8d: major %.3f arcsec, minor %.3f arcsec, pa %.3f deg',
                     chan_idx, bmajor[chan_idx], bminor[chan_idx], bpa[chan_idx])

        # Find channel with beam major axis closest to median
        bmajor_median = np.median(bmajor)
        bmajor_deviations = np.abs(bmajor - bmajor_median)
        closest_to_median_idx = np.argmin(bmajor_deviations)

        # Extract the "median" beam parameters
        median_beam_key = f'*{closest_to_median_idx}'
        median_beam = allbeams['beams'][median_beam_key]['*0']
        LOG.info(
            'The beam selected from the median-based find_good_commonbeam() heuristics: %s from channel=%s',
            median_beam,
            closest_to_median_idx,
        )
        # modify the pa key name due to the different convention in returns of ia.commonbeam() and ia.restoringbeam()
        median_beam['pa'] = median_beam.pop('positionangle', {'unit': 'deg', 'value': 0.0})

        LOG.info('commonbeam of %s, by ia.commonbeam():        %s', psf_filename, commonbeam)
        LOG.info('commonbeam of %s, by find_good_commonbeam(): %s', psf_filename, median_beam)

        BEAM_RATIO_THRESHOLD = 1.5

        # Extract beam major axis dimensions in arcsec
        commonbeam_major_arcsec = cqa.convert(cqa.quantity(commonbeam['major']), 'arcsec')['value']
        median_beam_major_arcsec = cqa.convert(cqa.quantity(median_beam['major']), 'arcsec')['value']

        # Compare common beam recommendations
        beam_ratio = commonbeam_major_arcsec / median_beam_major_arcsec

        # Identify channels with significant beam differences
        beam_ratio_per_channel = bmajor / median_beam_major_arcsec
        exceeds_upper_threshold = beam_ratio_per_channel > BEAM_RATIO_THRESHOLD
        exceeds_lower_threshold = beam_ratio_per_channel < 1 / BEAM_RATIO_THRESHOLD
        bad_psf_channels = np.where(exceeds_upper_threshold | exceeds_lower_threshold)[0]

        def beam_to_string(beam):
            beam_major_arcsec = cqa.getvalue(cqa.convert(beam['major'], 'arcsec'))[0]
            beam_minor_arcsec = cqa.getvalue(cqa.convert(beam['minor'], 'arcsec'))[0]

            beam_pa_deg = cqa.getvalue(cqa.convert(beam['pa'], 'deg'))[0]
            return f'{beam_major_arcsec:#.3g}"x{beam_minor_arcsec:#.3g}"@{beam_pa_deg:.1f}deg'

        if bad_psf_channels.size:
            channel_ranges = utils.find_ranges(bad_psf_channels.astype(str))
            LOG.warning(
                'Common beam (%s) major axis is %#.3gx larger than the median of per-plane beams (%s) '
                'for field %s, spw %s. Channels with per-plane beams deviating from the median by a '
                'factor >%#.2gx: %s. Adopting the median beam for all channels.',
                beam_to_string(commonbeam),
                beam_ratio,
                beam_to_string(median_beam),
                field,
                spw,
                BEAM_RATIO_THRESHOLD,
                channel_ranges,
            )

        return median_beam, bad_psf_channels

    @staticmethod
    def restoringbeam_from_psf(psf_filename: str, field: str, spw: str):
        """Provide a restoringbeam recommendaton based on .psf images."""
        cqa = casa_tools.quanta

        with casa_tools.ImageReader(psf_filename) as image:
            allbeams = image.restoringbeam()
            commonbeam = image.commonbeam()

        nchan = allbeams['nChannels']

        BEAM_RATIO_THRESHOLD = 1.1

        good_restoringbeam = None
        bad_psf_channels = np.array([], dtype=np.int64)

        # Pre-allocate arrays for beam parameters
        bmajor = np.zeros(nchan, dtype=np.float64)
        bminor = np.zeros(nchan, dtype=np.float64)
        bpa = np.zeros(nchan, dtype=np.float64)

        LOG.info('Per-plane restoring beam analysis for %s (channels: %d)', psf_filename, nchan)

        # Extract beam parameters for each channel
        for chan_idx in range(nchan):
            beam_key = f'*{chan_idx}'
            beam_data = allbeams['beams'][beam_key]['*0']

            # Convert beam parameters to consistent units
            major_arcsec = cqa.convert(cqa.quantity(beam_data['major']), 'arcsec')['value']
            minor_arcsec = cqa.convert(cqa.quantity(beam_data['minor']), 'arcsec')['value']
            pa_deg = cqa.convert(cqa.quantity(beam_data['positionangle']), 'deg')['value']

            # Store converted values
            bmajor[chan_idx] = major_arcsec
            bminor[chan_idx] = minor_arcsec
            bpa[chan_idx] = pa_deg

            LOG.info(
                'Channel %8d: major %.3f arcsec, minor %.3f arcsec, pa %.3f deg',
                chan_idx,
                bmajor[chan_idx],
                bminor[chan_idx],
                bpa[chan_idx],
            )

        try:
            good_commonbeam, bad_psf_channels = ImageParamsHeuristics.find_good_commonbeam(psf_filename)

            commonbeam_major_arcsec = cqa.convert(cqa.quantity(commonbeam['major']), 'arcsec')['value']
            good_commonbeam_major_arcsec = cqa.convert(cqa.quantity(good_commonbeam['major']), 'arcsec')['value']

            if commonbeam_major_arcsec > BEAM_RATIO_THRESHOLD * good_commonbeam_major_arcsec:
                beam_ratio = commonbeam_major_arcsec / good_commonbeam_major_arcsec
                beam_ratio_per_channel = bmajor / good_commonbeam_major_arcsec
                outlier_channels = np.where(beam_ratio_per_channel > BEAM_RATIO_THRESHOLD)[0]
                channel_ranges = utils.find_ranges(outlier_channels.astype(str))

                good_restoringbeam = good_commonbeam
                LOG.warning(
                    'Common beam (%s) major axis is %#.3gx larger than the robust common beam with outlier-plane removal (%s) '
                    'for field %s, spw %s. Adopting the robust beam for restoration of all channels. '
                    'Channels with per-plane beams > %#.2gx robust beam: %s.',
                    ImageParamsHeuristics._commonbeam_to_string(commonbeam, include_pa=False),
                    beam_ratio,
                    ImageParamsHeuristics._commonbeam_to_string(good_commonbeam, include_pa=False),
                    field,
                    spw,
                    BEAM_RATIO_THRESHOLD,
                    channel_ranges,
                )
        except Exception as ex:
            traceback_msg = traceback.format_exc()
            LOG.debug(traceback_msg)
            LOG.info(ex)

        return good_restoringbeam, bad_psf_channels
