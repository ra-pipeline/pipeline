"""This module is an adaptation from the original auto_selfcal prototype.

see: https://github.com/jjtobin/auto_selfcal
"""

import fnmatch
import glob
import os
import shutil

import numpy as np

import pipeline.infrastructure as infrastructure
from pipeline.domain.observingrun import ObservingRun
from pipeline.infrastructure import casa_tools, filenamer, logging, utils
from pipeline.infrastructure.casa_tasks import CasaTasks
from pipeline.infrastructure.casa_tools import imager as im
from pipeline.infrastructure.casa_tools import msmd
from pipeline.infrastructure.casa_tools import table as tb
from pipeline.infrastructure.tablereader import MeasurementSetReader

from .selfcal_helpers import (analyze_inf_EB_flagging, checkmask,
                              compare_beams, copy_products,
                              estimate_near_field_SNR, estimate_SNR,
                              fetch_targets, get_dr_correction, get_intflux,
                              get_n_ants, get_nterms, get_SNR_self,
                              get_SNR_self_update, get_solints_simple,
                              get_spw_bandwidth, get_spw_map, get_uv_range,
                              importdata, rank_refants, unflag_failed_antennas)

# from pipeline.infrastructure.utils import request_omp_threading

LOG = infrastructure.get_logger(__name__)


class SelfcalHeuristics(object):
    """Class to hold the heuristics for selfcal."""

    def __init__(
        self,
        scal_target,
        gaincal_minsnr=2.0,
        minsnr_to_proceed=3.0,
        delta_beam_thresh=0.05,
        apply_cal_mode_default='calflag',
        rel_thresh_scaling='log10',
        dividing_factor=None,
        check_all_spws=False,
        n_solints=4.0,
        do_amp_selfcal=False,
        inf_EB_gaincal_combine='scan',
        refantignore=None,
        executor=None,
    ):
        """Initialize the class."""
        self.executor = executor
        self.cts = CasaTasks(executor=self.executor)
        self.scaltarget = scal_target
        self.image_heuristics = scal_target['heuristics']
        self.cell = scal_target['cell']
        self.imsize = scal_target['imsize']
        self.phasecenter = scal_target['phasecenter']  # explictly set phasecenter for now
        self.spw_virtual = scal_target['spw']
        self.gridder = scal_target['gridder']
        self.wprojplanes = scal_target['wprojplanes']
        self.vislist = scal_target['sc_vislist']
        self.parallel = scal_target['sc_parallel']
        self.telescope = scal_target['sc_telescope']

        self.usermask = scal_target['sc_usermask']
        self.usermodel = scal_target['sc_usermodel']

        self.vis = self.vislist[-1]
        self.uvtaper = scal_target['uvtaper']
        self.robust = scal_target['robust']
        self.field = scal_target['field']
        self.target = utils.dequote(scal_target['field'])
        self.uvrange = scal_target['uvrange']
        # Note: scal_target['reffreq'] is either None or a frequency (in GHz) string representation
        self.reffreq = scal_target['reffreq']
        self.is_mosaic = scal_target['is_mosaic']

        self.n_solints = n_solints
        self.do_amp_selfcal = do_amp_selfcal
        self.gaincal_minsnr = gaincal_minsnr
        self.minsnr_to_proceed = minsnr_to_proceed
        self.delta_beam_thresh = delta_beam_thresh
        self.apply_cal_mode_default = apply_cal_mode_default
        self.rel_thresh_scaling = rel_thresh_scaling
        self.dividing_factor = dividing_factor
        self.check_all_spws = check_all_spws
        if refantignore is None:
            self.refantignore = {}
        else:
            self.refantignore = refantignore
        self.inf_EB_gaincal_combine = inf_EB_gaincal_combine    # Options: 'spw,scan' or 'scan' or 'spw' or 'none'
        self.inf_EB_gaintype = 'G'                              # Options: 'G' or 'T' or 'G,T'

        self.gaincal_unflag_minsnr = 5.0
        self.unflag_only_lbants = False
        self.unflag_only_lbants_onlyap = False
        self.calonly_max_flagged = 0.0
        self.second_iter_solmode = ''
        self.unflag_fb_to_prev_solint = False
        self.rerank_refants = False
        self.allow_gain_interpolation = False
        self.guess_scan_combine = False
        self.aca_use_nfmask = False
        self.allow_cocal = False
        self.scale_fov = 1.0  # option to make field of view larger than the default

        LOG.info('recreating observing run from per-selfcal-target MS(es): %r', self.vislist)
        self.image_heuristics.observing_run = self.get_observing_run(self.vislist)

    @staticmethod
    def get_observing_run(ms_files):
        if isinstance(ms_files, str):
            ms_files = [ms_files]

        observing_run = ObservingRun()
        for ms_file in ms_files:
            with logging.log_level('pipeline.infrastructure.tablereader', logging.WARNING+1):
                # avoid trigger warnings from MeasurementSetReader
                ms = MeasurementSetReader.get_measurement_set(ms_file)
            ms.exclude_num_chans = ()
            observing_run.add_measurement_set(ms)
        return observing_run

    def tclean_wrapper(
            self, selfcal_library, imagename, band, telescope='undefined', scales=[0],
            smallscalebias=0.6, mask='', nsigma=5.0, interactive=False, robust=0.5, gain=0.1, niter=50000,
            cycleniter=300, uvtaper=[],
            savemodel='none', sidelobethreshold=3.0, smoothfactor=1.0,  noisethreshold=5.0, lownoisethreshold=1.5,
            parallel=False, cyclefactor=3, threshold='0.0Jy', startmodel='', pblimit=0.1, pbmask=0.1, field='',
            datacolumn='', spw='all', obstype='single-point', nfrms_multiplier=1.0,
            savemodel_only=False, resume=False, image_mosaic_fields_separately=True, store_threshold=''):
        """
        Wrapper for tclean with keywords set to values desired for the Large Program imaging
        See the CASA 6.1.1 documentation for tclean to get the definitions of all the parameters
        """

        LOG.info('NF RMS Multiplier: %r', nfrms_multiplier)
        # Minimize out the nfrms_multiplier at 1.
        nfrms_multiplier = max(nfrms_multiplier, 1.0)

        # select the proper mask heuristics
        if mask == '':
            if selfcal_library['usermask'] != '':
                mask = selfcal_library['usermask']
                usemask = 'user'
            else:
                usemask = 'auto-multithresh'
        else:
            usemask = 'user'

        growiterations, negativethreshold, minbeamfrac, dogrowprune, minpercentchange, fastnoise = None, None, None, None, None, None
        baselineThresholdALMA = 400.0

        if telescope == 'ALMA':

            #LOG.info('ALMA band properties: %s', band_properties)
            uv75pct = selfcal_library['75thpct_uv']
            if uv75pct > baselineThresholdALMA:
                fastnoise = True
            else:
                fastnoise = False
            sidelobethreshold = 2.5
            smoothfactor = 1.0
            noisethreshold = 5.0*nfrms_multiplier
            lownoisethreshold = 1.5*nfrms_multiplier
            cycleniter = -1
            negativethreshold = 0.0
            dogrowprune = True
            minpercentchange = 1.0
            growiterations = 75
            minbeamfrac = 0.3
            # cyclefactor=1.0
            if uv75pct > 2000.0:
                sidelobethreshold = 2.0
            if uv75pct < 300.0:
                sidelobethreshold = 2.0
                smoothfactor = 1.0
                noisethreshold = 4.25*nfrms_multiplier
                lownoisethreshold = 1.5*nfrms_multiplier
            if uv75pct < baselineThresholdALMA:
                sidelobethreshold = 2.0

        if telescope == 'ACA':
            sidelobethreshold = 1.25
            smoothfactor = 1.0
            noisethreshold = 5.0*nfrms_multiplier
            lownoisethreshold = 2.0*nfrms_multiplier
            cycleniter = -1
            fastnoise = False
            negativethreshold = 0.0
            dogrowprune = True
            minpercentchange = 1.0
            growiterations = 75
            minbeamfrac = 0.1
            # cyclefactor=1.0

        elif 'VLA' in telescope:

            #LOG.info('VLA band properties: %s', band_properties)
            fastnoise = True
            sidelobethreshold = 2.0
            smoothfactor = 1.0
            noisethreshold = 5.0*nfrms_multiplier
            lownoisethreshold = 1.5*nfrms_multiplier
            pblimit = -0.1
            cycleniter = -1
            negativethreshold = 0.0
            dogrowprune = True
            minpercentchange = 1.0
            growiterations = 75
            minbeamfrac = 0.3
            pbmask = 0.0
            # cyclefactor=3.0

        if spw == 'all':
            vlist = selfcal_library['vislist']
            spws_per_vis = selfcal_library['spws_per_vis']
            nterms = selfcal_library['nterms']
        else:
            vlist = [vis for vis in selfcal_library['vislist'] if vis in selfcal_library['spw_map'][spw]]
            spws_per_vis = self.image_heuristics.observing_run.get_real_spwsel([spw]*len(vlist), vlist)
            nterms = 1

        if 'theoretical' in threshold:
            dr_mod = 1.0
            if self.telescope == 'ALMA' or self.telescope == 'ACA':
                if spw == 'all':
                    sensitivity, _, _ = self.get_sensitivity()
                else:
                    sensitivity, _, _ = self.get_sensitivity(spw=spw)
                if spw == 'all':
                    dr_mod = get_dr_correction(self.telescope, selfcal_library['SNR_dirty']*selfcal_library['RMS_dirty'], sensitivity, vlist)
                else:
                    dr_mod = get_dr_correction(self.telescope, selfcal_library['per_spw_stats'][spw]['SNR_dirty']*selfcal_library['per_spw_stats'][spw]['RMS_dirty'], sensitivity, vlist)
                LOG.info(f'DR modifier: {dr_mod} SPW: {spw}')

                sensitivity_nomod = sensitivity.copy()
                sensitivity = sensitivity*dr_mod   # apply DR modifier
                if (band == 'Band_9' or band == 'Band_10') and spw != 'all':   # adjust for DSB noise increase
                    sensitivity = sensitivity  # *4.0  might be unnecessary with DR mods

                selfcal_library['theoretical_sensitivity']=sensitivity_nomod
                for fid in selfcal_library['sub-fields']:
                    selfcal_library[fid]['theoretical_sensitivity']=sensitivity_nomod
            else:
                sensitivity_vla, _, self.reffreq = self.get_sensitivity()

                selfcal_library['theoretical_sensitivity'] = sensitivity_vla
                for fid in selfcal_library['sub-fields']:
                    selfcal_library[fid]['theoretical_sensitivity'] = sensitivity_vla

            if threshold == "theoretical_with_drmod":
                threshold = str(4.0*sensitivity)+'Jy'
            else:
                if spw == 'all':
                    sensitivity_scale_factor = 1.0
                else:
                    sensitivity_agg=self.get_sensitivity()
                    sensitivity_scale_factor=selfcal_library['RMS_NF_curr']/sensitivity_agg
                threshold = str(4.0*sensitivity_nomod*sensitivity_scale_factor)+'Jy'

        if threshold != '0.0Jy':
            nsigma = 0.0

        if nsigma != 0.0:
            if nsigma*nfrms_multiplier*0.66 > nsigma:
                nsigma = nsigma*nfrms_multiplier*0.66

        tclean_args = {'vis': vlist,
                       'imagename': imagename,
                       'field': field,
                       'specmode': 'mfs',
                       'deconvolver': 'mtmfs',
                       'scales': scales,
                       'gridder': self.gridder,
                       'wprojplanes': self.wprojplanes,
                       'weighting': 'briggs',
                       'robust': robust,
                       'gain': gain,
                       'imsize': self.imsize,
                       'cell': self.cell,
                       'smallscalebias': smallscalebias,  # set to CASA's default of 0.6 unless manually changed
                       'niter': niter,  # we want to end on the threshold
                       'interactive': interactive,
                       'nsigma': nsigma,
                       'cycleniter': cycleniter,
                       'cyclefactor': selfcal_library['cyclefactor'],
                       'growiterations': growiterations,
                       'negativethreshold': negativethreshold,
                       'dogrowprune': dogrowprune,
                       'minpercentchange': minpercentchange,
                       'minbeamfrac': minbeamfrac,
                       'fastnoise': fastnoise,
                       'uvtaper': uvtaper,
                       'mask': mask,
                       'usemask': usemask,
                       'savemodel': 'none',
                       'sidelobethreshold': sidelobethreshold,
                       'noisethreshold': noisethreshold,
                       'lownoisethreshold': lownoisethreshold,
                       'smoothfactor': smoothfactor,
                       'pbmask': pbmask,
                       'pblimit': pblimit,
                       'nterms': nterms,
                       'uvrange': selfcal_library['uvrange'],
                       'threshold': threshold,
                       'parallel': parallel,
                       'phasecenter': self.phasecenter,
                       'reffreq': self.reffreq,
                       'startmodel': startmodel,
                       'datacolumn': datacolumn,
                       'spw': spws_per_vis,
                       'fullsummary': False,
                       'verbose': True}
        # PIPE-2173: only use the Pipeline heuristics reffreq in hif_selfcal() when:
        #     * deconvolver: 'mtmfs', and
        #     * nterms = None (casa default to 2) or nterms >=2
        if not (tclean_args['nterms'] is None or tclean_args['nterms'] >= 2):
            tclean_args.pop('reffreq', None)

        tc_ret = None
        if not savemodel_only:
            if not resume:
                image_exts = ['.image*', '.mask', '.model*', '.pb*', '.psf*', '.residual*',
                              '.sumwt*', '.gridwt*', '.weight'
                              '.alpha', '.alpha.error', '.beta']
                self.remove_dirs([imagename+ext for ext in image_exts])
            tc_ret = self.cts.tclean(**tclean_args)

            if store_threshold != '':
                if telescope == "ALMA" or telescope == "ACA":
                    selfcal_library["clean_threshold_"+store_threshold] = float(threshold[0:-2])
                elif "VLA" in telescope and tc_ret['iterdone'] > 0:
                    selfcal_library["clean_threshold_"+store_threshold] = tc_ret['summaryminor'][0][0][0]['peakRes'][-1]

            if image_mosaic_fields_separately and selfcal_library['obstype'] == 'mosaic':
                for field_id in selfcal_library['sub-fields-phasecenters']:
                    # field imagename pattern: {santinized_sourcename}_field_field_{fid}_{band}_{version}
                    imagename_field = imagename.replace(f'_{band}_', f'_field_{field_id}_{band}_')

                    if 'VLA' in telescope:
                        fov = 45.0e9/selfcal_library['meanfreq']*60.0*1.5*0.5
                        if selfcal_library['meanfreq'] < 12.0e9:
                            fov = fov*2.0
                    if telescope == 'ALMA':
                        fov = 63.0*100.0e9/selfcal_library['meanfreq']*1.5*0.5*1.15
                    if telescope == 'ACA':
                        fov = 108.0*100.0e9/selfcal_library['meanfreq']*1.5*0.5
                    center = np.copy(selfcal_library['sub-fields-phasecenters'][field_id])
                    if self.phasecenter == 'TRACKFIELD':
                        center += self.cts.imhead(imagename+".image.tt0")['refval'][0:2]

                    region = 'circle[[{0:f}rad, {1:f}rad], {2:f}arcsec]'.format(center[0], center[1], fov)

                    for ext in [".image.tt0", ".mask", ".residual.tt0", ".psf.tt0", ".pb.tt0"]:
                        shutil.rmtree(imagename_field+ext.replace("pb", "mospb"), ignore_errors=True)
                        if ext == ".psf.tt0":
                            shutil.copytree(imagename+ext, imagename_field+ext)
                        else:
                            self.cts.imsubimage(imagename+ext, outfile=imagename_field +
                                                ext.replace("pb", "mospb.tmp"), region=region, overwrite=True)
                            if ext == ".pb.tt0":
                                self.cts.immath(imagename=[imagename_field+ext.replace("pb", "mospb.tmp")],
                                                outfile=imagename_field+ext.replace("pb", "mospb"),
                                                expr="IIF(IM0 == 0, 0.1, IM0)")
                                shutil.rmtree(imagename_field+ext.replace("pb", "mospb.tmp"), ignore_errors=True)

                    # Make an image of the primary beam for each sub-field.
                    if isinstance(selfcal_library['vislist'], list):
                        for v in selfcal_library['vislist']:
                            # Since not every field is in every v, we need to check them all so that we don't accidentally get a v without a given field_id
                            if field_id in selfcal_library['sub-fields-fid_map'][v]:
                                fid = selfcal_library['sub-fields-fid_map'][v][field_id]
                                break
                        im.open(v)
                    else:
                        fid = selfcal_library['sub-fields-fid_map'][selfcal_library['vislist']][field_id]
                        im.open(selfcal_library['vislist'])

                    nx, ny, _, _ = self.cts.imhead(imagename=imagename_field+".image.tt0", mode="get",
                                                   hdkey="shape")
                    im.selectvis(field=str(fid), spw=spws_per_vis)
                    if isinstance(self.cell, list):
                        cell = self.cell[0]
                    else:
                        cell = self.cell
                    im.defineimage(nx=nx, ny=ny, cellx=cell, celly=cell, phasecenter=fid, mode="mfs", spw=spws_per_vis)
                    im.setvp(dovp=True)
                    im.makeimage(type="pb", image=imagename_field + ".pb.tt0")
                    im.close()

        if savemodel == 'modelcolumn' and not selfcal_library['usermodel']:
            LOG.info("")
            LOG.info("Running tclean in the prediction-only setting to fill the MS model column.")
            # A workaround for CAS-14386
            parallel_predict = parallel
            if parallel_predict and 'mosaic' in tclean_args['gridder']:
                LOG.debug("A parallel model write operation does not work with gridder='mosaic': enforcing parallel=False.")
                parallel_predict = False
            tclean_args.update({'niter': 0,
                                'interactive': False,
                                'nsigma': 0.0,
                                'mask': '',
                                'usemask': 'user',
                                'savemodel': 'modelcolumn',
                                'calcres': False,
                                'calcpsf': False,
                                'restoration': False,
                                'threshold': '0.0mJy',
                                'parallel': parallel_predict,
                                'startmodel': ''})
            tc_ret = self.cts.tclean(**tclean_args)

        if savemodel == 'modelcolumn' and selfcal_library['usermodel'] != '':
            LOG.info('Using user model %s already filled to model column, skipping model write.', selfcal_library['usermodel'])

        if not savemodel_only:
            return tc_ret

    def usermodel_wrapper(self, selfcal_library, imagename, telescope='undefined', scales=[0], smallscalebias=0.6, mask='',
                          nsigma=5.0, interactive=False, robust=0.5, gain=0.1, niter=50000,
                          cycleniter=300, uvtaper=[], savemodel='none', gridder='standard', sidelobethreshold=3.0, smoothfactor=1.0, noisethreshold=5.0,
                          lownoisethreshold=1.5, parallel=False, cyclefactor=3, threshold='0.0Jy', phasecenter='',
                          startmodel='', pblimit=0.1, pbmask=0.1, field='', datacolumn='', spw='',
                          savemodel_only=False, resume=False):
        # this method is not fully veried.
        vlist = selfcal_library['vislist']
        if isinstance(selfcal_library['usermodel'], list):
            nterms = len(selfcal_library['usermodel'])
            for i, image in enumerate(selfcal_library['usermodel']):
                if 'fits' in image:
                    self.cts.importfits(fitsimage=image, imagename=image.replace('.fits', ''))
                    selfcal_library['usermodel'][i] = image.replace('.fits', '')
        elif isinstance(selfcal_library['usermodel'], str):
            self.cts.importfits(fitsimage=selfcal_library['usermodel'], imagename=selfcal_library['usermodel'].replace('.fits', ''))
            nterms = 1

        if mask == '':
            if selfcal_library['usermask'] != '':
                mask = selfcal_library['usermask']
                usemask = 'user'
            else:
                usemask = 'auto-multithresh'
        else:
            usemask = 'user'

        if not resume:
            for ext in ['.image*', '.mask', '.model*', '.pb*', '.psf*', '.residual*', '.sumwt*', '.gridwt*']:
                os.system('rm -rf ' + imagename + ext)
        # regrid start model
        self.cts.tclean(vis=vlist,
                        imagename=imagename+'_usermodel_prep',
                        field=field,
                        specmode='mfs',
                        deconvolver='mtmfs',
                        scales=scales,
                        gridder=gridder,
                        weighting='briggs',
                        robust=robust,
                        gain=gain,
                        imsize=self.imsize,
                        cell=self.cell,
                        smallscalebias=smallscalebias,  # set to CASA's default of 0.6 unless manually changed
                        niter=0,  # we want to end on the threshold
                        interactive=interactive,
                        nsigma=nsigma,
                        cycleniter=cycleniter,
                        cyclefactor=selfcal_library['cyclefactor'],
                        uvtaper=uvtaper,
                        mask=mask,
                        usemask=usemask,
                        sidelobethreshold=sidelobethreshold,
                        noisethreshold=noisethreshold,
                        lownoisethreshold=lownoisethreshold,
                        smoothfactor=smoothfactor,
                        pbmask=pbmask,
                        pblimit=pblimit,
                        nterms=nterms,
                        reffreq=self.reffreq,
                        uvrange=selfcal_library['uvrange'],
                        threshold=threshold,
                        parallel=False,
                        phasecenter=phasecenter,
                        datacolumn=datacolumn, spw=spw, wprojplanes=self.wprojplanes, verbose=True, startmodel=selfcal_library['usermodel'], savemodel='none')

        # this step is a workaround a bug in tclean that doesn't always save the model during multiscale clean. See the "Known Issues" section for CASA 5.1.1 on NRAO's website
        if savemodel == 'modelcolumn':
            LOG.info("")
            LOG.info("Running tclean a second time to save the model...")
            self.cts.tclean(vis=vlist,
                            imagename=imagename+'_usermodel_prep',
                            field=field,
                            specmode='mfs',
                            deconvolver='mtmfs',
                            scales=scales,
                            gridder=gridder,
                            weighting='briggs',
                            robust=robust,
                            gain=gain,
                            imsize=self.imsize,
                            cell=self.cell,
                            smallscalebias=smallscalebias,  # set to CASA's default of 0.6 unless manually changed
                            niter=0,
                            interactive=False,
                            nsigma=0.0,
                            cycleniter=cycleniter,
                            cyclefactor=selfcal_library['cyclefactor'],
                            uvtaper=uvtaper,
                            usemask='user',
                            savemodel=savemodel,
                            sidelobethreshold=sidelobethreshold,
                            noisethreshold=noisethreshold,
                            lownoisethreshold=lownoisethreshold,
                            smoothfactor=smoothfactor,
                            pbmask=pbmask,
                            pblimit=pblimit,
                            calcres=False,
                            calcpsf=False,
                            restoration=False,
                            nterms=nterms,
                            reffreq=self.reffreq,
                            uvrange=selfcal_library['uvrange'],
                            threshold=threshold,
                            parallel=False,
                            phasecenter=phasecenter, spw=spw, wprojplanes=self.wprojplanes)

    def gaincal_wrapper(self, slib, selfcal_plan, target, band, vis, solint, applymode, iteration, telescope, 
            gaincal_minsnr, gaincal_unflag_minsnr=5.0, minsnr_to_proceed=3.0, rerank_refants=False, unflag_only_lbants=False, unflag_only_lbants_onlyap=False,
            calonly_max_flagged=0.0, second_iter_solmode="", unflag_fb_to_prev_solint=False,
            refantmode="flex", mode="selfcal", calibrators="", gaincalibrator_dict={}, allow_gain_interpolation=False,
            guess_scan_combine=False):
        
        sani_target = 'sc.'+filenamer.sanitize(target)
        ##
        # Solve gain solutions per MS, target, solint, and band
        ##
        os.system('rm -rf '+sani_target+'_'+vis+'_'+band+'_'+solint+'_' +
                    str(iteration)+'_'+selfcal_plan['solmode'][iteration]+'*.g')
        ##
        # Set gaincal parameters depending on which iteration and whether to use combine=spw for inf_EB or not
        # Defaults should assume combine='scan' and gaintpe='G' will fallback to combine='scan,spw' if too much flagging
        # At some point remove the conditional for use_inf_EB_preapply, since there isn't a reason not to do it
        ##

        if selfcal_plan['solmode'][iteration] == 'p':
            if solint == 'inf_EB':
                gaincal_spwmap = []
                gaincal_preapply_gaintable = []
                gaincal_interpolate = []
                gaincal_gaintype = selfcal_plan[vis]['inf_EB_gaintype']
                gaincal_solmode = ""
                selfcal_plan['gaincal_combine'][iteration] = selfcal_plan[vis]['inf_EB_gaincal_combine']
                if 'spw' in selfcal_plan[vis]['inf_EB_gaincal_combine']:
                    applycal_spwmap = [slib[vis]['spwmap']]
                    gaincal_spwmap = [slib[vis]['spwmap']]
                else:
                    applycal_spwmap = []
                applycal_interpolate = [slib['applycal_interp']]
                applycal_gaintable = [sani_target+'_'+vis+'_'+band+'_'+solint +
                                            '_'+str(iteration)+'_'+selfcal_plan['solmode'][iteration]+'.g']
            # elif selfcal_plan['solmode'][iteration]=='p':
            else:
                gaincal_spwmap = []
                gaincal_preapply_gaintable = [sani_target+'_'+vis+'_'+band+'_inf_EB_0_p.g']
                gaincal_interpolate = [slib['applycal_interp']]
                gaincal_gaintype = 'T' if applymode == "calflag" or second_iter_solmode == "" else "GSPLINE" if second_iter_solmode == "GSPLINE" else "G"
                gaincal_solmode = "" if applymode == "calflag" or second_iter_solmode == "GSPLINE" else second_iter_solmode
                if 'spw' in selfcal_plan[vis]['inf_EB_gaincal_combine']:
                    applycal_spwmap = [slib[vis]
                                            ['spwmap'], slib[vis]['spwmap']]
                    gaincal_spwmap = [slib[vis]['spwmap']]
                elif selfcal_plan[vis]['inf_EB_fallback_mode'] == 'spwmap':
                    applycal_spwmap = slib[vis]['inf_EB']['spwmap'] + \
                        [slib[vis]['spwmap']]
                    gaincal_spwmap = slib[vis]['inf_EB']['spwmap']
                else:
                    applycal_spwmap = [[], slib[vis]['spwmap']]
                    gaincal_spwmap = []
                applycal_interpolate = [slib['applycal_interp'], slib['applycal_interp']]
                applycal_gaintable = [sani_target+'_'+vis+'_'+band+'_inf_EB_0' +
                                            '_p.g', sani_target+'_'+vis+'_'+band+'_'+solint+'_'+str(iteration)+'_p.g']
            slib[vis][solint]['gaintable'] = applycal_gaintable
            slib[vis][solint]['iteration'] = iteration+0
            slib[vis][solint]['spwmap'] = applycal_spwmap
            slib[vis][solint]['applycal_mode'] = selfcal_plan['applycal_mode'][iteration]+''
            slib[vis][solint]['applycal_interpolate'] = applycal_interpolate
            slib[vis][solint]['gaincal_combine'] = selfcal_plan['gaincal_combine'][iteration]+''
            slib[vis][solint]['solmode'] = selfcal_plan['solmode'][iteration]+''
            for fid in np.intersect1d(slib['sub-fields-to-selfcal'], list(slib['sub-fields-fid_map'][vis].keys())):
                slib[fid][vis][solint]['gaintable'] = applycal_gaintable
                slib[fid][vis][solint]['iteration'] = iteration+0
                slib[fid][vis][solint]['spwmap'] = applycal_spwmap
                slib[fid][vis][solint]['applycal_mode'] = selfcal_plan['applycal_mode'][iteration]+''
                slib[fid][vis][solint]['applycal_interpolate'] = applycal_interpolate
                slib[fid][vis][solint]['gaincal_combine'] = selfcal_plan['gaincal_combine'][iteration]+''
                slib[fid][vis][solint]['solmode'] = selfcal_plan['solmode'][iteration]+''

            fallback = ''
            if selfcal_plan['solmode'][iteration] == 'ap':
                solnorm = True
            else:
                solnorm = False

            if gaincal_gaintype == "GSPLINE":
                splinetime = solint.replace('_EB', '').replace('_ap', '')
                if splinetime == "inf":
                    splinetime = slib["Median_scan_time"]
                else:
                    splinetime = float(splinetime[0:-1])

            if solint == "scan_inf":
                if len(gaincalibrator_dict[vis]) > 0:
                    scans = []
                    intents = []
                    times = []
                    for t in gaincalibrator_dict[vis].keys():
                        scans += [gaincalibrator_dict[vis][t]["scans"]]
                        intents += [np.repeat(gaincalibrator_dict[vis][t]["intent"],
                                                len(gaincalibrator_dict[vis][t]["scans"]))]
                        times += [gaincalibrator_dict[vis][t]["times"]]

                    times = np.concatenate(times)
                    order = np.argsort(times)
                    times = times[order]

                    scans = np.concatenate(scans)[order]
                    intents = np.concatenate(intents)[order]

                    is_gaincalibrator = intents == "phase"
                    scans = scans[is_gaincalibrator]

                    msmd.open(vis)
                    scan_ids_for_target = msmd.scansforfield(target)
                    include_scans = []
                    for iscan in range(scans.size - 1):
                        scan_group = np.intersect1d(
                            scan_ids_for_target,
                            np.array(list(range(scans[iscan] + 1, scans[iscan + 1]))),
                        ).astype(str)
                        if scan_group.size > 0:
                            include_scans.append(','.join(scan_group))
                    # PIPE-2471: find all target scan IDs that are out of for the phasecal scan id range,
                    # collect them as extra scan groups. This is used to deal with the situation where
                    # some target scans are not bracketed by phase calibrator scans.
                    if scans.size > 0:
                        extra_scans = scan_ids_for_target[scan_ids_for_target > max(scans)]
                        if extra_scans.size > 0:
                            # convert id to strings and join them into a single comma-separated string.
                            include_scans.append(','.join(extra_scans.astype(str)))
                        extra_scans = scan_ids_for_target[scan_ids_for_target < min(scans)]
                        if extra_scans.size > 0:
                            include_scans.insert(0, ','.join(extra_scans.astype(str)))
                    msmd.close()
                elif guess_scan_combine:
                    msmd.open(vis)
                    scan_ids_for_target = msmd.scansforfield(target)
                    include_scans = []
                    for iscan in range(scan_ids_for_target.size):
                        if len(include_scans) > 0:
                            if str(scan_ids_for_target[iscan]) in include_scans[-1]:
                                continue
                        scan_group = str(scan_ids_for_target[iscan])
                        if iscan < scan_ids_for_target.size - 1:
                            if (
                                msmd.fieldsforscan(scan_ids_for_target[iscan + 1]).size
                                < msmd.fieldsforscan(scan_ids_for_target[iscan]).size / 3
                            ):
                                scan_group += ',' + str(scan_ids_for_target[iscan + 1])
                        include_scans.append(scan_group)
                    msmd.close()
                else:
                    msmd.open(vis)
                    include_scans = [str(scan) for scan in msmd.scansforfield(target)]
                    msmd.close()
            else:
                include_scans = ['']

            # Fields that don't have any mask in the primary beam should be removed from consideration, as their models are likely bad.
            if slib['obstype'] == 'mosaic':
                msmd.open(vis)
                include_targets = []
                remove = []
                for incl_scan in include_scans:
                    scan_targets = []
                    for fid in [slib['sub-fields-fid_map'][vis][fid] for fid in
                                np.intersect1d(slib['sub-fields-to-gaincal'], list(slib['sub-fields-fid_map'][vis].keys()))] if incl_scan == '' else \
                            np.intersect1d(msmd.fieldsforscans(np.array(incl_scan.split(",")).astype(int)),
                                            [slib['sub-fields-fid_map'][vis][fid] for fid in
                                            np.intersect1d(slib['sub-fields-to-gaincal'], list(slib['sub-fields-fid_map'][vis].keys()))]):
                        # Note: because of the msmd above getting actual fids from the MS, we just need to append fid below.
                        scan_targets.append(fid)

                    if len(scan_targets) > 0:
                        include_targets.append(','.join(np.array(scan_targets).astype(str)))
                    else:
                        remove.append(incl_scan)

                for incl_scan in remove:
                    include_scans.remove(incl_scan)

                msmd.close()
            else:
                include_targets = [str(slib['sub-fields-fid_map'][vis][0])]

            slib[vis][solint]["include_scans"] = include_scans
            slib[vis][solint]["include_targets"] = include_targets

            slib[vis][solint]['gaincal_return'] = []
            for incl_scans, incl_targets in zip(include_scans, include_targets):
                if solint == 'inf_EB':
                    if slib['spws_set'][vis].ndim == 1:
                        nspw_sets = 1
                    else:
                        nspw_sets = slib['spws_set'][vis].shape[0]
                else:  # only necessary to loop over gain cal when in inf_EB to avoid inf_EB solving for all spws
                    nspw_sets = 1
                for i in range(nspw_sets):  # run gaincal on each spw set to handle spectral scans
                    if solint == 'inf_EB':
                        if nspw_sets == 1 and slib['spws_set'][vis].ndim == 1:
                            spwselect = ','.join(str(spw) for spw in slib['spws_set'][vis].tolist())
                        else:
                            spwselect = ','.join(str(spw) for spw in slib['spws_set'][vis][i].tolist())
                    else:
                        spwselect = slib[vis]['spws']
                    LOG.info('Running gaincal on '+spwselect+' for '+sani_target+'_'+vis+'_'+band +
                                '_'+solint+'_'+str(iteration)+'_'+selfcal_plan['solmode'][iteration]+'.g')
                    gaincal_return_tmp = self.cts.gaincal(vis=vis,
                                                            caltable=sani_target+'_'+vis+'_'+band+'_'+solint+'_' +
                                                            str(iteration)+'_' +
                                                            selfcal_plan['solmode'][iteration]+'.g',
                                                            gaintype=gaincal_gaintype, spw=spwselect,
                                                            refant=slib[vis]['refant'], calmode=selfcal_plan['solmode'][iteration], solnorm=solnorm if applymode == "calflag" else False,
                                                            solint=solint.replace('_EB', '').replace('_ap', '').replace('scan_', ''), minsnr=gaincal_minsnr if applymode == 'calflag' else max(gaincal_minsnr, gaincal_unflag_minsnr), minblperant=4, combine=selfcal_plan['gaincal_combine'][iteration],
                                                            field=incl_targets, scan=incl_scans, gaintable=gaincal_preapply_gaintable, spwmap=gaincal_spwmap, uvrange=slib['uvrange'],
                                                            interp=gaincal_interpolate, solmode=gaincal_solmode, refantmode='flex', append=os.path.exists(sani_target+'_'+vis+'_'+band+'_'+solint+'_'+str(iteration)+'_'+selfcal_plan['solmode'][iteration]+'.g'))
                    #
                    slib[vis][solint]['gaincal_return'].append(gaincal_return_tmp)
                    if solint != 'inf_EB':
                        break
        else:
            slib[vis][solint]['gaincal_return'] = []
            for fid in np.intersect1d(slib['sub-fields-to-selfcal'], list(slib['sub-fields-fid_map'][vis].keys())):
                gaincal_spwmap = []
                gaincal_preapply_gaintable = slib[fid][vis][slib[fid]
                                                                    ['final_phase_solint']]['gaintable']
                gaincal_interpolate = [slib['applycal_interp']]*len(gaincal_preapply_gaintable)
                gaincal_gaintype = 'T' if applymode == "calflag" or second_iter_solmode == "" else "GSPLINE" if second_iter_solmode == "GSPLINE" else "G"
                gaincal_solmode = "" if applymode == "calflag" or second_iter_solmode == "GSPLINE" else second_iter_solmode
                if 'spw' in selfcal_plan['inf_EB_gaincal_combine'][vis]:
                    applycal_spwmap = [slib[fid][vis]['spwmap'],
                                            slib[fid][vis]['spwmap'], slib[fid][vis]['spwmap']]
                    gaincal_spwmap = [slib[fid][vis]
                                            ['spwmap'], slib[fid][vis]['spwmap']]
                elif selfcal_plan['inf_EB_fallback_mode'][vis] == 'spwmap':
                    applycal_spwmap = slib[fid][vis]['inf_EB']['spwmap'] + [
                        slib[fid][vis]['spwmap'], slib[fid][vis]['spwmap']]
                    gaincal_spwmap = slib[fid][vis]['inf_EB']['spwmap'] + \
                        [slib[fid][vis]['spwmap']]
                else:
                    applycal_spwmap = [[], slib[fid][vis]
                                            ['spwmap'], slib[fid][vis]['spwmap']]
                    gaincal_spwmap = [[], slib[fid][vis]['spwmap']]
                applycal_interpolate = [slib['applycal_interp']] * \
                    len(gaincal_preapply_gaintable)+['linearPD']
                applycal_gaintable = slib[fid][vis][slib[fid]
                                                            ['final_phase_solint']]['gaintable']+[sani_target+'_'+vis+'_'+band+'_'+solint+'_'+str(iteration)+'_ap.g']

                slib[vis][solint]['gaintable'] = applycal_gaintable
                slib[vis][solint]['iteration'] = iteration+0
                slib[vis][solint]['spwmap'] = applycal_spwmap
                slib[vis][solint]['applycal_mode'] = selfcal_plan['applycal_mode'][iteration]+''
                slib[vis][solint]['applycal_interpolate'] = applycal_interpolate
                slib[vis][solint]['gaincal_combine'] = selfcal_plan['gaincal_combine'][iteration]+''
                slib[vis][solint]['solmode'] = selfcal_plan['solmode'][iteration]+''
                slib[fid][vis][solint]['gaintable'] = applycal_gaintable
                slib[fid][vis][solint]['iteration'] = iteration+0
                slib[fid][vis][solint]['spwmap'] = applycal_spwmap
                slib[fid][vis][solint]['applycal_mode'] = selfcal_plan['applycal_mode'][iteration]+''
                slib[fid][vis][solint]['applycal_interpolate'] = applycal_interpolate
                slib[fid][vis][solint]['gaincal_combine'] = selfcal_plan['gaincal_combine'][iteration]+''
                slib[fid][vis][solint]['solmode'] = selfcal_plan['solmode'][iteration]+''

                fallback = ''
                if selfcal_plan['solmode'][iteration] == 'ap':
                    solnorm = True
                else:
                    solnorm = False

                if gaincal_gaintype == "GSPLINE":
                    splinetime = solint.replace('_EB', '').replace('_ap', '')
                    if splinetime == "inf":
                        splinetime = slib[fid]["Median_scan_time"]
                    else:
                        splinetime = float(splinetime[0:-1])

                gaincal_return_tmp = self.cts.gaincal(vis=vis, \
                                                        # caltable=sani_target+'_'+vis+'_'+band+'_'+solint+'_'+str(iteration)+'_'+selfcal_plan['solmode'][iteration]+'.g',\
                                                        caltable="temp.g", \
                                                        gaintype=gaincal_gaintype, spw=slib[fid][vis]['spws'],
                                                        refant=slib[vis]['refant'], calmode=selfcal_plan['solmode'][iteration], solnorm=solnorm if applymode == "calflag" else False,
                                                        solint=solint.replace('_EB', '').replace('_ap', '').replace('scan_', ''), minsnr=gaincal_minsnr if applymode == 'calflag' else max(gaincal_minsnr, gaincal_unflag_minsnr), minblperant=4, combine=selfcal_plan['gaincal_combine'][iteration],
                                                        field=str(slib['sub-fields-fid_map'][vis][fid]), gaintable=gaincal_preapply_gaintable, spwmap=gaincal_spwmap, uvrange=slib['uvrange'],
                                                        # interp=gaincal_interpolate[vis], solmode=gaincal_solmode, append=os.path.exists(sani_target+'_'+vis+'_'+band+'_'+
                                                        # solint+'_'+str(iteration)+'_'+selfcal_plan['solmode'][iteration]+'.g'))
                                                        interp=gaincal_interpolate, solmode=gaincal_solmode, append=os.path.exists('temp.g'), refantmode='flex')
                slib[vis][solint]['gaincal_return'].append(gaincal_return_tmp)

            tb.open("temp.g")
            subt = tb.query("OBSERVATION_ID==0", sortlist="TIME,ANTENNA1")
            tb.close()

            subt.copy(sani_target+'_'+vis+'_'+band+'_'+solint+'_'+str(iteration) +
                        '_'+selfcal_plan['solmode'][iteration]+'.g', deep=True)
            subt.close()

            os.system("rm -rf temp.g")

        if rerank_refants:
            slib[vis]["refant"] = rank_refants(
                vis, caltable=sani_target+'_'+vis+'_'+band+'_'+solint+'_'+str(iteration)+'_'+selfcal_plan['solmode'][iteration]+'.g')

            # If we are falling back to a previous solution interval on the unflagging, we need to make sure all tracks use a common
            # reference antenna.
            if unflag_fb_to_prev_solint:

                for it, sint in enumerate(selfcal_plan['solints'][0:iteration+1]):
                    if not os.path.exists(sani_target+'_'+vis+'_'+band+'_'+sint+'_'+str(it)+'_'+selfcal_plan['solmode'][it]+'.g'):
                        continue

                    # If a previous iteration went through the unflagging routine, it is possible that some antennas fell back to
                    # a previous solint. In that case, rerefant will flag those antennas because they can't be re-referenced with
                    # a different time interval. So to be safe, we go back to the pre-pass solutions and then re-run the passing.
                    # We could probably check more carefully whether this is the case to avoid having to do this... but the
                    # computing time isn't significant so it's easy just to run through again.
                    if os.path.exists(sani_target+'_'+vis+'_'+band+'_'+sint+'_'+str(it)+'_'+selfcal_plan['solmode'][it]+'.pre-pass.g'):
                        self.cts.rerefant(vis, sani_target+'_'+vis+'_'+band+'_'+sint+'_'+str(it)+'_'+selfcal_plan['solmode'][it]+'.pre-pass.g',
                                            refant=slib[vis]["refant"], refantmode=refantmode if 'inf_EB' not in sint else 'flex')

                        os.system("rm -rf "+sani_target+'_'+vis+'_'+band+'_'+sint +
                                    '_'+str(it)+'_'+selfcal_plan['solmode'][it]+'.g')
                        os.system("cp -r "+sani_target+'_'+vis+'_'+band+'_'+sint+'_'+str(it)+'_'+selfcal_plan['solmode'][it]+'.pre-pass.g ' +
                                    sani_target+'_'+vis+'_'+band+'_'+sint+'_'+str(it)+'_'+selfcal_plan['solmode'][it]+'.g')

                        if sint == "inf_EB" and len(slib[vis][sint]["spwmap"][0]) > 0:
                            unflag_spwmap = slib[vis][sint]["spwmap"][0]
                        else:
                            unflag_spwmap = []

                        unflag_failed_antennas(vis, sani_target+'_'+vis+'_'+band+'_'+sint+'_'+str(it)+'_' +
                                                selfcal_plan['solmode'][it]+'.g', slib[vis][sint]['gaincal_return'], flagged_fraction=0.25, solnorm=solnorm,
                                                only_long_baselines=selfcal_plan['solmode'][it] == "ap" if unflag_only_lbants and
                                                unflag_only_lbants_onlyap else unflag_only_lbants, calonly_max_flagged=calonly_max_flagged,
                                                spwmap=unflag_spwmap, fb_to_prev_solint=unflag_fb_to_prev_solint, solints=selfcal_plan['solints'], iteration=it)
                    else:
                        self.cts.rerefant(vis, sani_target+'_'+vis+'_'+band+'_'+sint+'_'+str(it)+'_'+selfcal_plan['solmode'][it]+'.g',
                                            refant=slib[vis]["refant"], refantmode=refantmode if 'inf_EB' not in sint else 'flex')
            else:
                os.system("cp -r "+sani_target+'_'+vis+'_'+band+'_'+solint+'_'+str(iteration)+'_'+selfcal_plan['solmode'][iteration]+'.g ' +
                            sani_target+'_'+vis+'_'+band+'_'+solint+'_'+str(iteration)+'_'+selfcal_plan['solmode'][iteration]+'.pre-rerefant.g')
                self.cts.rerefant(vis, sani_target+'_'+vis+'_'+band+'_'+solint+'_'+str(iteration)+'_'+selfcal_plan['solmode'][iteration]+'.g',
                                    refant=slib[vis]["refant"], refantmode=refantmode if 'inf_EB' not in solint else 'flex')

        ##
        # default is to run without combine=spw for inf_EB, here we explicitly run a test inf_EB with combine='scan,spw' to determine
        # the number of flagged antennas when combine='spw' then determine if it needs spwmapping or to use the gaintable with spwcombine.
        ##
        if solint == 'inf_EB' and fallback == '':
            os.system('rm -rf test_inf_EB.g')
            test_gaincal_combine = 'scan,spw'
            if slib['obstype'] == 'mosaic':
                test_gaincal_combine += ',field'
            test_gaincal_return = {'G': [], 'T': []}
            for gaintype in np.unique([gaincal_gaintype, 'T']):
                # run gaincal on each spw set to handle spectral scans
                for i in range(slib['spws_set'][vis].shape[0]):
                    if nspw_sets == 1 and slib['spws_set'][vis].ndim == 1:
                        spwselect = ','.join(str(spw) for spw in slib['spws_set'][vis].tolist())
                    else:
                        spwselect = ','.join(str(spw) for spw in slib['spws_set'][vis][i].tolist())
                    test_gaincal_return[gaintype] += [self.cts.gaincal(vis=vis,
                                                                        caltable='test_inf_EB_'+gaintype+'.g',
                                                                        gaintype=gaintype, spw=spwselect,
                                                                        refant=slib[vis]['refant'], calmode='p',
                                                                        solint=solint.replace('_EB', '').replace('_ap', ''), minsnr=gaincal_minsnr if applymode == "calflag" else max(gaincal_minsnr, gaincal_unflag_minsnr), minblperant=4, combine=test_gaincal_combine,
                                                                        field=include_targets[0], gaintable='', spwmap=[], uvrange=slib['uvrange'], refantmode=refantmode, append=os.path.exists('test_inf_EB_'+gaintype+'.g'))]
            spwlist = slib[vis]['spws'].split(',')
            fallback, map_index, spwmap, applycal_spwmap_inf_EB = analyze_inf_EB_flagging(slib, band, spwlist, sani_target+'_'+vis+'_'+band+'_'+solint+'_'+str(
                iteration)+'_'+selfcal_plan['solmode'][iteration]+'.g', vis, target, 'test_inf_EB_'+gaincal_gaintype+'.g', slib['spectral_scan'], telescope, selfcal_plan['solint_snr_per_spw'], minsnr_to_proceed, 'test_inf_EB_T.g' if gaincal_gaintype == 'G' else None)

            selfcal_plan[vis]['inf_EB_fallback_mode'] = fallback+''
            LOG.info('inf_EB %s %s', fallback, applycal_spwmap_inf_EB)
            if fallback != '':
                if 'combinespw' in fallback:
                    gaincal_spwmap = [slib[vis]['spwmap']]
                    selfcal_plan['gaincal_combine'][iteration] = 'scan,spw'
                    selfcal_plan[vis]['inf_EB_gaincal_combine'] = 'scan,spw'
                    applycal_spwmap = [slib[vis]['spwmap']]
                    os.system('rm -rf           '+sani_target+'_'+vis+'_'+band+'_'+solint +
                                '_'+str(iteration)+'_'+selfcal_plan['solmode'][iteration]+'.g')
                    for gaintype in np.unique([gaincal_gaintype, 'T']):
                        os.system('cp -r test_inf_EB_'+gaintype+'.g '+sani_target+'_'+vis+'_'+band+'_'+solint +
                                    '_'+str(iteration)+'_'+selfcal_plan['solmode'][iteration]+'.gaintype'+gaintype+'.g')
                    if fallback == 'combinespw':
                        gaincal_gaintype = 'G'
                    else:
                        gaincal_gaintype = 'T'
                    os.system('mv test_inf_EB_'+gaincal_gaintype+'.g '+sani_target+'_'+vis+'_' +
                                band+'_'+solint+'_'+str(iteration)+'_'+selfcal_plan['solmode'][iteration]+'.g')
                    slib[vis][solint]['gaincal_return'] = test_gaincal_return[gaincal_gaintype]
                if fallback == 'spwmap':
                    gaincal_spwmap = applycal_spwmap_inf_EB
                    selfcal_plan[vis]['inf_EB_gaincal_combine'] = 'scan'
                    selfcal_plan['gaincal_combine'][iteration] = 'scan'
                    applycal_spwmap = [applycal_spwmap_inf_EB]

                # Update the appropriate selfcal_library entries.
                slib[vis][solint]['spwmap'] = applycal_spwmap
                slib[vis][solint]['gaincal_combine'] = selfcal_plan['gaincal_combine'][iteration]+''
                for fid in np.intersect1d(slib['sub-fields-to-selfcal'], list(slib['sub-fields-fid_map'][vis].keys())):
                    slib[fid][vis][solint]['spwmap'] = applycal_spwmap
                    slib[fid][vis][solint]['gaincal_combine'] = selfcal_plan['gaincal_combine'][iteration]+''

            os.system('rm -rf test_inf_EB_*.g')

        slib[vis][solint]['fallback']=fallback+''
        for fid in np.intersect1d(slib['sub-fields-to-selfcal'],list(slib['sub-fields-fid_map'][vis].keys())):
            slib[fid][vis][solint]['fallback']=fallback+''

        # If iteration two, try restricting to just the antennas with enough unflagged data.
        # Should we also restrict to just long baseline antennas?
        if applymode == "calonly":
            # Make a copy of the caltable before unflagging, for reference.
            os.system("cp -r "+sani_target+'_'+vis+'_'+band+'_'+solint+'_'+str(iteration)+'_' +
                        selfcal_plan['solmode'][iteration]+'.g '+sani_target+'_'+vis+'_'+band+'_'+solint+'_'+str(iteration)+'_' +
                        selfcal_plan['solmode'][iteration]+'.pre-pass.g')

            if solint == "inf_EB" and len(applycal_spwmap[vis]) > 0:
                unflag_spwmap = applycal_spwmap[vis][0]
            else:
                unflag_spwmap = []

            slib[vis][solint]['unflag_spwmap'] = unflag_spwmap
            slib[vis][solint]['unflagged_lbs'] = True

            unflag_failed_antennas(vis, sani_target+'_'+vis+'_'+band+'_'+solint+'_'+str(iteration)+'_' +
                                    selfcal_plan['solmode'][iteration]+'.g', slib[vis][solint]['gaincal_return'], flagged_fraction=0.25, solnorm=solnorm,
                                    only_long_baselines=selfcal_plan['solmode'][iteration] == "ap" if unflag_only_lbants and unflag_only_lbants_onlyap else
                                    unflag_only_lbants, calonly_max_flagged=calonly_max_flagged, spwmap=unflag_spwmap,
                                    fb_to_prev_solint=unflag_fb_to_prev_solint, solints=selfcal_plan['solints'], iteration=iteration)

        # Do some post-gaincal cleanup for mosaics.
        if slib['obstype'] == 'mosaic':
            os.system("cp -r "+sani_target+'_'+vis+'_'+band+'_'+solint+'_'+str(iteration)+'_'+selfcal_plan['solmode'][iteration]+'.g ' +
                        sani_target+'_'+vis+'_'+band+'_'+solint+'_'+str(iteration)+'_'+selfcal_plan['solmode'][iteration]+'.pre-drop.g')
            tb.open(sani_target+'_'+vis+'_'+band+'_'+solint+'_'+str(iteration) +
                    '_'+selfcal_plan['solmode'][iteration]+'.g', nomodify=False)
            antennas = tb.getcol("ANTENNA1")
            fields = tb.getcol("FIELD_ID")
            scans = tb.getcol("SCAN_NUMBER")
            flags = tb.getcol("FLAG")

            if (solint != "inf_EB" and not allow_gain_interpolation) or (allow_gain_interpolation and "inf" not in solint):
                # If a given field has > 25% of its solutions flagged then just flag the whole field because it will have too much
                # interpolation.
                if solint == "scan_inf":
                    max_n_solutions = max([(scans == scan).sum() for scan in np.unique(scans)])
                    for scan in np.unique(scans):
                        scan_n_solutions = (flags[0, 0, scans == scan] == False).sum()
                        if scan_n_solutions < 0.75 * max_n_solutions:
                            flags[:, :, scans == scan] = True
                else:
                    n_all_flagged = np.sum([np.all(flags[:, :, antennas == ant])
                                            for ant in np.unique(antennas)])
                    max_n_solutions = max([(fields == fid).sum()
                                            for fid in np.unique(fields)]) - n_all_flagged
                    for fid in np.unique(fields):
                        fid_n_solutions = (flags[0, 0, fields == fid] == False).sum()
                        if fid_n_solutions < 0.75 * max_n_solutions:
                            flags[:, :, fields == fid] = True
            bad = np.where(np.any(flags, axis=0)[0])[0]
            tb.removerows(rownrs=bad)
            tb.flush()
            tb.close()

    def applycal_wrapper(self, vis, target, band, solint, selfcal_library, current=lambda f: False, final=lambda f: False, 
            clear=lambda f: False, restore_flags=None):

        if restore_flags != None:
            self.cts.flagmanager(vis=vis,mode='restore',versionname=restore_flags)

        for fid in [fid for fid in np.intersect1d(selfcal_library['sub-fields'],
                list(selfcal_library['sub-fields-fid_map'][vis].keys())) if current(fid)]:
            self.cts.applycal(vis=vis,\
                     gaintable=selfcal_library[fid][vis][solint]['gaintable'],\
                     interp=selfcal_library[fid][vis][solint]['applycal_interpolate'], calwt=False,\
                     spwmap=selfcal_library[fid][vis][solint]['spwmap'],\
                     #applymode=applymode,field=target,spw=selfcal_library[vis]['spws'])
                     applymode='calflag',field=str(selfcal_library['sub-fields-fid_map'][vis][fid]),\
                     spw=selfcal_library[vis]['spws'])

        for fid in [fid for fid in np.intersect1d(selfcal_library['sub-fields'],
                list(selfcal_library['sub-fields-fid_map'][vis].keys())) if final(fid)]:
            LOG.info('****************Applying '+str(selfcal_library[fid][vis]['gaintable_final'])+' to '+target+' field '+\
                    str(fid)+' '+band+'*************')
            self.cts.applycal(vis=vis,\
                    gaintable=selfcal_library[fid][vis]['gaintable_final'],\
                    interp=selfcal_library[fid][vis]['applycal_interpolate_final'],\
                    calwt=False,spwmap=selfcal_library[fid][vis]['spwmap_final'],\
                    applymode=selfcal_library[fid][vis]['applycal_mode_final'],\
                    field=str(selfcal_library['sub-fields-fid_map'][vis][fid]),\
                    spw=selfcal_library[vis]['spws'])    

        for fid in [fid for fid in np.intersect1d(selfcal_library['sub-fields'],
                list(selfcal_library['sub-fields-fid_map'][vis].keys())) if clear(fid)]:
            LOG.info('****************Removing all calibrations for '+target+' '+str(fid)+' '+band+'**************')
            self.cts.clearcal(vis=vis,field=str(selfcal_library['sub-fields-fid_map'][vis][fid]),\
                    spw=selfcal_library[vis]['spws'])

    def remove_dirs(self, dir_names):
        """Remove dirs based on a list of glob pattern."""
        if isinstance(dir_names, str):
            dir_name_list = [dir_names]
        else:
            dir_name_list = dir_names
        for dir_name in dir_name_list:
            for dir_select in glob.glob(dir_name):
                self.cts.rmtree(dir_select)

    def move_dir(self, old_dirname, new_dirname):
        """Move a directory to a new location."""
        if os.path.isdir(new_dirname):
            LOG.info("%s already exists. Will remove it first.", new_dirname)
            self.cts.rmtree(new_dirname)
        if os.path.isdir(old_dirname):
            self.cts.move(old_dirname, new_dirname)
        else:
            LOG.info("%s does not exist", old_dirname)

    def copy_dir(self, old_dirname, new_dirname):
        """Copy a directory to a new location."""
        if os.path.isdir(new_dirname):
            LOG.info("%s already exists. Will remove it first.", new_dirname)
            self.cts.rmtree(new_dirname)
        if os.path.isdir(old_dirname):
            self.cts.copytree(old_dirname, new_dirname)
        else:
            LOG.info("%s does not exist", old_dirname)

    def get_sensitivity(self, spw=None):
        """Calculate sensitivty from the Pipeline standard imaging heuristics."""
        if spw is None:
            spw = self.spw_virtual

        def custom_filter(record):
            return not fnmatch.fnmatch(record.getMessage(), '*channel bandwidths ratio*')

        # PIPE-1827: filter out the "channel bandwidths ratio" warning messages during sensitivity calculations.
        with logging.log_level('pipeline.hif.heuristics.imageparams_base', level=None, filter=custom_filter):
            sensitivity, eff_ch_bw, sens_bw, sens_reffreq, known_per_spw_cont_sensitivities_all_chan = self.image_heuristics.calc_sensitivities(
                self.vislist, self.field, 'TARGET', spw, -1, {},
                'cont', self.gridder, self.cell, self.imsize, 'briggs', self.robust, self.uvtaper, True, {},
                False, calc_reffreq=True)
        # Note: sensitivity and sens_bw are expected to be one-elements Numpy arrays.
        sensitivity = sensitivity[0]
        sens_bw = sens_bw[0]
        sens_reffreq = f'{sens_reffreq/1e9}GHz'

        return sensitivity, sens_bw, sens_reffreq

    def get_dr_correction(self):
        raise NotImplementedError(f'{self.__class__.__name__}.get_dr_correction() is not implemented yet!')

    def get_image_stats(self, image, mask, backup_mask, selfcal_library, use_nfmask, solint, suffix, mosaic_sub_field=False, spw='all'):
        ##
        ## Do the assessment of the post- (and pre-) selfcal images.
        ##
        SNR, RMS = estimate_SNR(image, maskname=mask, mosaic_sub_field=mosaic_sub_field)
        if use_nfmask:
           SNR_NF,RMS_NF = estimate_near_field_SNR(image, maskname=mask, las=selfcal_library['LAS'], mosaic_sub_field=mosaic_sub_field)
           if RMS_NF < 0 and backup_mask != '':
               SNR_NF, RMS_NF = estimate_near_field_SNR(image, maskname=backup_mask, las=selfcal_library['LAS'], mosaic_sub_field=mosaic_sub_field)
        else:
           SNR_NF, RMS_NF = SNR, RMS

        for vis in selfcal_library['vislist']:
           if suffix in ['dirty','orig','initial','final']:
               if spw == 'all':
                   update_dict = selfcal_library
               else:
                   update_dict = selfcal_library['per_spw_stats'][spw]
           else:
               update_dict = selfcal_library[vis][solint]

           ##
           ## record self cal results/details for this solint
           ##
           update_dict['SNR_'+suffix]=SNR.copy()
           update_dict['RMS_'+suffix]=RMS.copy()
           update_dict['SNR_NF_'+suffix]=SNR_NF.copy()
           update_dict['RMS_NF_'+suffix]=RMS_NF.copy()

           with casa_tools.ImageReader(image) as image_reader:
               bm = image_reader.restoringbeam(polarization=0)
           update_dict['Beam_major_'+suffix] = bm['major']['value']
           update_dict['Beam_minor_'+suffix] = bm['minor']['value']
           update_dict['Beam_PA_'+suffix] = bm['positionangle']['value']

           if checkmask(imagename=mask):
               update_dict['intflux_'+suffix], update_dict['e_intflux_'+suffix] = get_intflux(image, RMS, maskname=mask,
                       mosaic_sub_field=mosaic_sub_field)
           elif backup_mask != '' and checkmask(imagename=backup_mask):
               update_dict['intflux_'+suffix], update_dict['e_intflux_'+suffix] = get_intflux(image, RMS, maskname=backup_mask,
                       mosaic_sub_field=mosaic_sub_field)
           else:
               update_dict['intflux_'+suffix], update_dict['e_intflux_'+suffix] = -99.0, -99.0

           if suffix in ['dirty','orig','initial','final']:
               break

        return SNR, RMS, SNR_NF, RMS_NF

    def __call__(self):
        """Execute auto_selfcal on a set of per-targets MSes.

        cleantarget: a list of CleanTarget objects.
        """

        n_ants = get_n_ants(self.scaltarget['sc_vislist'])

        selfcal_library, selfcal_plan, gaincalibrator_dict = self._prep_selfcal()

        # Currently, we are still using a modified version of the prototype selfcal preparation scheme to prepare "selfcal_library".
        # Then we override a subset of selfcal input parameters using PL-heuristics-based values.
        # Eventually, we will retire the prototype selfcal preparation function entirely.

        # selfcal_libray: target->band
        # solints: band->target

        vislist = self.vislist
        parallel = self.parallel

        vis = vislist[-1]
        ##
        # create initial images for each target to evaluate SNR and beam
        # replicates what a preceding hif_makeimages would do
        # Enables before/after comparison and thresholds to be calculated
        # based on the achieved S/N in the real data
        ##
        for target in selfcal_library:
            sani_target = 'sc.'+filenamer.sanitize(target)
            for band in selfcal_library[target].keys():
                # check if the imaging target is mosaic
                is_mosaic = selfcal_library[target][band]['obstype'] == 'mosaic'

                # make images using the appropriate tclean heuristics for each telescope
                # Because tclean doesn't deal in NF masks, the automask from the initial image is likely to contain a lot of noise unless
                # we can get an estimate of the NF modifier for the auto-masking thresholds. To do this, we need to create a very basic mask
                # with the dirty image. So we just use one iteration with a tiny gain so that nothing is really subtracted off.
                self.tclean_wrapper(selfcal_library[target][band],
                    sani_target + '_' + band + '_dirty', band, telescope=self.telescope, nsigma=4.0,
                    scales=[0], threshold='0.0Jy', niter=1, gain=0.00001, savemodel='none', 
                    parallel=parallel, field=self.field)

                dirty_SNR, dirty_RMS, dirty_NF_SNR, dirty_NF_RMS = self.get_image_stats(sani_target+'_'+band+'_dirty.image.tt0', 
                        sani_target+'_'+band+'_dirty.mask', '', selfcal_library[target][band], (self.telescope != 'ACA' or self.aca_use_nfmask),
                        'dirty', 'dirty')

                mosaic_dirty_SNR, mosaic_dirty_RMS, mosaic_dirty_NF_SNR, mosaic_dirty_NF_RMS = {}, {}, {}, {}
                for fid in selfcal_library[target][band]['sub-fields']:
                    if is_mosaic:
                        imagename = sani_target+'_field_'+str(fid)+'_'+band+'_dirty.image.tt0'
                    else:
                        imagename = sani_target+'_'+band+'_dirty.image.tt0'

                    mosaic_dirty_SNR[fid], mosaic_dirty_RMS[fid], mosaic_dirty_NF_SNR[fid], mosaic_dirty_NF_RMS[fid] = self.get_image_stats(imagename, 
                            imagename.replace('image.tt0', 'mask'), '', selfcal_library[target][band][fid], 
                            (self.telescope != 'ACA' or self.aca_use_nfmask), 'dirty', 'dirty', mosaic_sub_field=is_mosaic)

                initial_tclean_return = self.tclean_wrapper(selfcal_library[target][band],
                    sani_target + '_' + band + '_initial', band, telescope=self.telescope,
                    nsigma=4.0, scales=[0],
                    threshold='theoretical_with_drmod', savemodel='none', parallel=parallel,
                    field=self.field,
                    nfrms_multiplier=dirty_NF_RMS / dirty_RMS, store_threshold='orig')
                
                initial_SNR, initial_RMS, initial_NF_SNR, initial_NF_RMS = self.get_image_stats(sani_target+'_'+band+'_initial.image.tt0', 
                        sani_target+'_'+band+'_initial.mask', '', selfcal_library[target][band], (self.telescope != 'ACA' or self.aca_use_nfmask),
                        'orig', 'orig')

                mosaic_initial_SNR, mosaic_initial_RMS, mosaic_initial_NF_SNR, mosaic_initial_NF_RMS = {}, {}, {}, {}
                for fid in selfcal_library[target][band]['sub-fields']:
                    if is_mosaic:
                        imagename = sani_target+'_field_'+str(fid)+'_'+band+'_initial.image.tt0'
                    else:
                        imagename = sani_target+'_'+band+'_initial.image.tt0'

                    mosaic_initial_SNR[fid], mosaic_initial_RMS[fid], mosaic_initial_NF_SNR[fid], mosaic_initial_NF_RMS[fid] = self.get_image_stats(imagename, 
                            imagename.replace('image.tt0', 'mask'), '', selfcal_library[target][band][fid], 
                            (self.telescope != 'ACA' or self.aca_use_nfmask), 'orig', 'orig', mosaic_sub_field=is_mosaic)

                if "VLA" in self.telescope and "clean_threshold_orig" not in selfcal_library[target][band]:
                    selfcal_library[target][band]['clean_threshold_orig']=4.0*initial_RMS

                if selfcal_library[target][band]['nterms'] < 2:
                    # updated nterms if needed based on S/N and fracbw
                    selfcal_library[target][band]['nterms'] = get_nterms(
                        selfcal_library[target][band]['fracbw'],
                        selfcal_library[target][band]['SNR_orig'])

                selfcal_library[target][band]['RMS_curr'] = initial_RMS
                selfcal_library[target][band]['RMS_NF_curr'] = initial_NF_RMS if initial_NF_RMS > 0 else initial_RMS

                for fid in selfcal_library[target][band]['sub-fields']:
                    if selfcal_library[target][band][fid]['SNR_orig'] > 500.0:
                        selfcal_library[target][band][fid]['nterms'] = 2

                    selfcal_library[target][band][fid]['RMS_curr'] = mosaic_initial_RMS[fid]
                    selfcal_library[target][band][fid]['RMS_NF_curr'] = mosaic_initial_NF_RMS[fid] if mosaic_initial_NF_RMS[fid] > 0 else mosaic_initial_RMS[fid]

        # MAKE DIRTY PER SPW IMAGES TO PROPERLY ASSESS DR MODIFIERS
        ##
        # Make a initial image per spw images to assess overall improvement
        ##

        if self.check_all_spws:
            for target in selfcal_library:
                sani_target ='sc.'+filenamer.sanitize(target)
                for band in selfcal_library[target].keys():
                    vislist = selfcal_library[target][band]['vislist'].copy()
                    # potential place where diff spws for different VLA EBs could cause problems
                    spwlist = self.spw_virtual.split(',')
                    for spw in spwlist:
                        keylist = selfcal_library[target][band]['per_spw_stats'].keys()
                        if spw not in keylist:
                            selfcal_library[target][band]['per_spw_stats'][spw] = {}
                        if not os.path.exists(sani_target+'_'+band+'_'+spw+'_dirty.image.tt0'):
                            self.tclean_wrapper(selfcal_library[target][band],
                                sani_target + '_' + band + '_' + spw + '_dirty', band,
                                telescope=self.telescope, nsigma=4.0, scales=[0],
                                threshold='0.0Jy', niter=0, savemodel='none', parallel=parallel,
                                field=self.field, spw=spw)

                        dirty_per_spw_SNR, dirty_per_spw_RMS, dirty_per_spw_NF_SNR, dirty_per_spw_NF_RMS = self.get_image_stats(
                                sani_target+'_'+band+'_'+spw+'_dirty.image.tt0', 
                                sani_target+'_'+band+'_'+spw+'_dirty.mask', '', selfcal_library[target][band], 
                                (self.telescope != 'ACA' or self.aca_use_nfmask), 'dirty', 'dirty', spw=spw)

                        if not os.path.exists(sani_target+'_'+band+'_'+spw+'_initial.image.tt0'):
                            self.tclean_wrapper(selfcal_library[target][band],
                                sani_target + '_' + band + '_' + spw + '_initial', band,
                                telescope=self.telescope, nsigma=4.0, threshold='theoretical_with_drmod', scales=[0],
                                savemodel='none', parallel=parallel,
                                field=self.field, datacolumn='corrected', spw=spw,
                                nfrms_multiplier=dirty_per_spw_NF_RMS/dirty_per_spw_RMS)

                        per_spw_SNR, per_spw_RMS, per_spw_NF_SNR, per_spw_NF_RMS = self.get_image_stats(
                                sani_target+'_'+band+'_'+spw+'_initial.image.tt0', 
                                sani_target+'_'+band+'_'+spw+'_initial.mask', '', selfcal_library[target][band], 
                                (self.telescope != 'ACA' or self.aca_use_nfmask), 'orig', 'orig', spw=spw)

        ##
        # estimate per scan/EB S/N using time on source and median scan times
        ##

        get_SNR_self(selfcal_library, selfcal_plan, n_ants, self.inf_EB_gaincal_combine,
                     self.inf_EB_gaintype)

        ##
        # Set clean selfcal thresholds
        # Open question about determining the starting and progression of clean threshold for
        # each iteration
        # Peak S/N > 100; SNR/15 for first, successivly reduce to 3.0 sigma through each iteration?
        # Peak S/N < 100; SNR/10.0
        ##
        # Switch to a sensitivity for low frequency that is based on the residuals of the initial image for the
        # first couple rounds and then switch to straight nsigma? Determine based on fraction of pixels that the # initial mask covers to judge very extended sources?

        self.set_clean_thresholds(selfcal_library, selfcal_plan, dividing_factor=self.dividing_factor, rel_thresh_scaling=self.rel_thresh_scaling, telescope=self.telescope)

        ##
        # Save self-cal library
        ##
        # with open('selfcal_library.pickle', 'wb') as handle:
        #     pickle.dump(selfcal_library, handle, protocol=pickle.HIGHEST_PROTOCOL)

        ##
        # Begin Self-cal loops
        ##

        for target in selfcal_library:
            sani_target = 'sc.'+filenamer.sanitize(target)
            for band in selfcal_library[target]:
                # self.selfcal_iteration(target, band, solints, solmode, solint_snr, selfcal_library,
                #                       sani_target, parallel, band_properties,
                #                       inf_EB_gaintype_dict, inf_EB_gaincal_combine_dict, gaincal_combine, applycal_interp,
                #                       inf_EB_fallback_mode_dict, spws_set, applycal_mode, integration_time, n_ants, spectral_scan)
                self.run_selfcal(selfcal_library[target][band], selfcal_plan[target][band], target, band, self.telescope, n_ants,
                                 gaincal_minsnr=self.gaincal_minsnr, gaincal_unflag_minsnr=self.gaincal_unflag_minsnr, minsnr_to_proceed=self.minsnr_to_proceed, delta_beam_thresh=self.delta_beam_thresh, do_amp_selfcal=self.do_amp_selfcal,
                                 inf_EB_gaincal_combine=self.inf_EB_gaincal_combine, inf_EB_gaintype=self.inf_EB_gaintype, unflag_only_lbants=self.unflag_only_lbants,
                                 unflag_only_lbants_onlyap=self.unflag_only_lbants_onlyap, calonly_max_flagged=self.calonly_max_flagged,
                                 second_iter_solmode=self.second_iter_solmode, unflag_fb_to_prev_solint=self.unflag_fb_to_prev_solint, rerank_refants=self.rerank_refants,
                                 gaincalibrator_dict=gaincalibrator_dict, allow_gain_interpolation=self.allow_gain_interpolation, guess_scan_combine=self.guess_scan_combine,
                                 aca_use_nfmask=self.aca_use_nfmask)

        ##
        # If we want to try amplitude selfcal, should we do it as a function out of the main loop or a separate loop?
        # Mechanics are likely to be a bit more simple since I expect we'd only try a single solint=inf solution
        ##

        ##
        # Make a final image per target to assess overall improvement
        ##
        for target in selfcal_library:
            sani_target = 'sc.'+filenamer.sanitize(target)
            for band in selfcal_library[target].keys():
                nfsnr_modifier = selfcal_library[target][band]['RMS_NF_curr'] / \
                    selfcal_library[target][band]['RMS_curr']
                
                clean_threshold = min(
                    selfcal_library[target][band]['clean_threshold_orig'],
                    selfcal_library[target][band]['RMS_NF_curr'] * 3.0)
                if selfcal_library[target][band]['clean_threshold_orig'] < selfcal_library[target][band][
                        'RMS_NF_curr'] * 3.0:
                    LOG.info('The clean threshold used for the initial image was less than 3*RMS_NF_curr; '
                             'the final image will use the same threshold as the initial image')
                    
                if selfcal_library[target][band]['SC_success']:
                    self.tclean_wrapper(selfcal_library[target][band],
                        sani_target + '_' + band + '_final', band, telescope=self.telescope,
                        nsigma=3.0, threshold=str(clean_threshold) + 'Jy', scales=[0],
                        savemodel='none', parallel=parallel,
                        field=self.field, datacolumn='corrected',
                        nfrms_multiplier=nfsnr_modifier)
                else:
                    copy_products(sani_target + '_' + band + '_initial', sani_target + '_' + band + '_final')
                    if is_mosaic:
                        for field_id in selfcal_library[target][band]['sub-fields-phasecenters']:
                            imagename_field_initial = sani_target + '_' + band + '_initial'
                            imagename_field_initial = imagename_field_initial.replace(
                                f'_{band}_', f'_field_{field_id}_{band}_'
                            )
                            imagename_field_final = sani_target + '_' + band + '_final'
                            imagename_field_final = imagename_field_final.replace(
                                f'_{band}_', f'_field_{field_id}_{band}_'
                            )
                            copy_products(imagename_field_initial, imagename_field_final)

                final_SNR, final_RMS, final_NF_SNR, final_NF_RMS = self.get_image_stats(sani_target+'_'+band+'_final.image.tt0', 
                        sani_target+'_'+band+'_final.mask', '', selfcal_library[target][band], (self.telescope != 'ACA' or self.aca_use_nfmask),
                        'final', 'final')

                mosaic_final_SNR, mosaic_final_RMS, mosaic_final_NF_SNR, mosaic_final_NF_RMS = {}, {}, {}, {}
                for fid in selfcal_library[target][band]['sub-fields']:
                    if is_mosaic:
                        imagename = sani_target + '_field_' + str(fid) + '_' + band + '_final.image.tt0'
                    else:
                        imagename = sani_target + '_' + band + '_final.image.tt0'

                    mosaic_final_SNR[fid], mosaic_final_RMS[fid], mosaic_final_NF_SNR[fid], mosaic_final_NF_RMS[fid] = self.get_image_stats(imagename, 
                            imagename.replace('image.tt0', 'mask'), '', selfcal_library[target][band][fid], 
                            (self.telescope != 'ACA' or self.aca_use_nfmask), 'final', 'final', mosaic_sub_field=is_mosaic)

                # recalc inital stats using final mask
                orig_final_SNR, orig_final_RMS, orig_final_NF_SNR, orig_final_NF_RMS = self.get_image_stats(sani_target+'_'+band+'_initial.image.tt0', 
                        sani_target+'_'+band+'_final.mask', '', selfcal_library[target][band], (self.telescope != 'ACA' or self.aca_use_nfmask),
                        'orig', 'orig')

                for fid in selfcal_library[target][band]['sub-fields']:
                    if selfcal_library[target][band]['obstype'] == 'mosaic':
                        imagename = sani_target + '_field_' + str(fid) + '_' + band
                    else:
                        imagename = sani_target + '_' + band

                    # recalc inital stats using final mask
                    mosaic_initial_final_SNR, mosaic_initial_final_RMS, mosaic_initial_final_NF_SNR, mosaic_initial_final_NF_RMS = self.get_image_stats(imagename+'_initial.image.tt0', 
                            imagename+'_final.mask', '', selfcal_library[target][band][fid], 
                            (self.telescope != 'ACA' or self.aca_use_nfmask), 'orig', 'orig', mosaic_sub_field=is_mosaic)

        ##
        # Make a final image per spw images to assess overall improvement
        ##
        if self.check_all_spws:
            for target in selfcal_library:
                sani_target = 'sc.'+filenamer.sanitize(target)
                for band in selfcal_library[target].keys():
                    spwlist = self.spw_virtual.split(',')
                    LOG.info('Generating final per-SPW images for '+target+' in '+band)
                    for spw in selfcal_library[target][band]['spw_map']:
                        # omit DR modifiers here since we should have increased DR significantly
                        if selfcal_library[target][band]['SC_success']:
                            self.tclean_wrapper(selfcal_library[target][band], sani_target + '_' + band + '_' + spw + '_final', band,
                                                telescope=self.telescope, nsigma=4.0,
                                                #threshold=str(sensitivity * sensitivity_scale_factor * 4.0) + 'Jy'
                                                threshold='theoretical', scales=[0],
                                                savemodel='none', parallel=parallel,
                                                field=self.field, datacolumn='corrected', spw=spw,
                                                nfrms_multiplier=nfsnr_modifier)
                        else:
                            copy_products(sani_target + '_' + band + '_' + spw + '_initial',
                                          sani_target + '_' + band + '_' + spw + '_final')

                        final_per_spw_SNR, final_per_spw_RMS, final_per_spw_NF_SNR, final_per_spw_NF_RMS = self.get_image_stats(
                                sani_target+'_'+band+'_'+spw+'_final.image.tt0', 
                                sani_target+'_'+band+'_'+spw+'_final.mask', '', selfcal_library[target][band], 
                                (self.telescope != 'ACA' or self.aca_use_nfmask), 'final', 'final', spw=spw)

                        # reccalc initial stats with final mask
                        orig_final_per_spw_SNR, orig_final_per_spw_RMS, orig_final_per_spw_NF_SNR, orig_final_per_spw_NF_RMS = self.get_image_stats(
                                sani_target+'_'+band+'_'+spw+'_initial.image.tt0', 
                                sani_target+'_'+band+'_'+spw+'_final.mask', '', selfcal_library[target][band], 
                                (self.telescope != 'ACA' or self.aca_use_nfmask), 'orig', 'orig', spw=spw)

        ##
        # Print final results
        ##
        for target in selfcal_library:
            for band in selfcal_library[target].keys():
                LOG.info(target+' '+band+' Summary')
                LOG.info(f"At least 1 successful selfcal iteration?:  {selfcal_library[target][band]['SC_success']}")
                LOG.info(f"Final solint:  {selfcal_library[target][band]['final_solint']}")
                LOG.info(f"Original SNR:  {selfcal_library[target][band]['SNR_orig']}")
                LOG.info(f"Final SNR:  {selfcal_library[target][band]['SNR_final']}")
                LOG.info(f"Original RMS:  {selfcal_library[target][band]['RMS_orig']}")
                LOG.info(f"Final RMS:  {selfcal_library[target][band]['RMS_final']}")
                #   for vis in vislist:
                #      LOG.info('Final gaintables: '+selfcal_library[target][band][vis]['gaintable'])
                #      LOG.info('Final spwmap: ',selfcal_library[target][band][vis]['spwmap'])
                # else:
                #   LOG.info('Selfcal failed on '+target+'. No solutions applied.')

        #
        # Perform a check on the per-spw images to ensure they didn't lose quality in self-calibration
        #
        if self.check_all_spws:
            for target in selfcal_library:
                sani_target = 'sc.'+filenamer.sanitize(target)
                for band in selfcal_library[target].keys():
                    vislist = selfcal_library[target][band]['vislist'].copy()
                    spwlist = selfcal_library[target][band][vis]['spws'].split(',')
                    for spw in spwlist:
                        delta_beamarea = compare_beams(sani_target+'_'+band+'_'+spw+'_initial.image.tt0',
                                                       sani_target+'_'+band+'_'+spw+'_final.image.tt0')
                        delta_SNR = selfcal_library[target][band]['per_spw_stats'][spw]['SNR_final'] -\
                            selfcal_library[target][band]['per_spw_stats'][spw]['SNR_orig']
                        delta_RMS = selfcal_library[target][band]['per_spw_stats'][spw]['RMS_final'] -\
                            selfcal_library[target][band]['per_spw_stats'][spw]['RMS_orig']
                        selfcal_library[target][band]['per_spw_stats'][spw]['delta_SNR'] = delta_SNR
                        selfcal_library[target][band]['per_spw_stats'][spw]['delta_RMS'] = delta_RMS
                        selfcal_library[target][band]['per_spw_stats'][spw]['delta_beamarea'] = delta_beamarea
                        LOG.info(sani_target + '_' + band + '_' + spw+' ' +
                                 'Pre SNR: {:0.2f}, Post SNR: {:0.2f} Pre RMS: {:0.3f}, Post RMS: {:0.3f}'.format(
                                     selfcal_library[target][band]['per_spw_stats'][spw]['SNR_orig'],
                                     selfcal_library[target][band]['per_spw_stats'][spw]['SNR_final'],
                                     selfcal_library[target][band]['per_spw_stats'][spw]['RMS_orig'] * 1000.0,
                                     selfcal_library[target][band]['per_spw_stats'][spw]['RMS_final'] * 1000.0))
                        if delta_SNR < 0.0:
                            LOG.info('WARNING SPW '+spw+' HAS LOWER SNR POST SELFCAL')
                        if delta_RMS > 0.0:
                            LOG.info('WARNING SPW '+spw+' HAS HIGHER RMS POST SELFCAL')
                        if delta_beamarea > 0.05:
                            LOG.info('WARNING SPW '+spw+' HAS A >0.05 CHANGE IN BEAM AREA POST SELFCAL')

        # attached solints to selfcal_library as a short-term workaround

        target = list(selfcal_library.keys())[0]
        band = list(selfcal_library[target].keys())[0]
        selfcal_library[target][band]['solints'] = selfcal_plan[target][band]['solints']

        return selfcal_library

    def _prep_selfcal(self):
        """Prepare the selfcal heuristics."""

        scaltarget = self.scaltarget
        vislist = scaltarget['sc_vislist']
        telescope = scaltarget['sc_telescope']
        ##
        # Find targets, assumes all targets are in all ms files for simplicity and only science targets, will fail otherwise
        ##
        all_targets = fetch_targets(vislist[0])

        ##
        # Global environment variables for control of selfcal
        ##

        bands, band_properties, scantimesdict, scanfieldsdict, scannfieldsdict,  scanstartsdict, scanendsdict, \
            integrationtimesdict, _, _, spwsarray_dict, mosaic_field, gaincalibrator_dict, spectral_scan, spws_set = importdata(
                vislist, all_targets, telescope)

        ##
        # Save/restore starting flags
        ##

        for vis in vislist:
            if os.path.exists(vis+'.flagversions/flags.selfcal_starting_flags'):
                self.cts.flagmanager(vis=vis, mode='restore', versionname='selfcal_starting_flags')
            else:
                self.cts.flagmanager(vis=vis, mode='save', versionname='selfcal_starting_flags')

        ##
        # begin setting up a selfcal_library with all relevant metadata to keep track of during selfcal
        ##
        selfcal_library = {}

        for target in all_targets:
            selfcal_library[target] = {}
            for band in bands:
                if target in scantimesdict[band][vislist[0]].keys():
                    selfcal_library[target][band] = {}
                else:
                    continue

                for vis in vislist:
                    selfcal_library[target][band][vis] = {}

                if mosaic_field[band][vislist[0]][target]['mosaic']:
                    selfcal_library[target][band]['obstype'] = 'mosaic'
                else:
                    selfcal_library[target][band]['obstype'] = 'single-point'

                # Fill in the usermask and usermodel, if supplied.

                print(self.usermask)
                print(self.usermodel)
                if band in self.usermask:
                    selfcal_library[target][band]['usermask'] = self.usermask[band]
                else:
                    selfcal_library[target][band]['usermask'] = ''

                if band in self.usermodel:
                    selfcal_library[target][band]['usermodel'] = self.usermodel[band]
                else:
                    selfcal_library[target][band]['usermodel'] = ''

                # Make sure the fields get mapped properly, in case the order in which they are observed changes from EB to EB.

                selfcal_library[target][band]['sub-fields-fid_map'] = {}
                all_phasecenters = []
                for vis in vislist:
                    selfcal_library[target][band]['sub-fields-fid_map'][vis] = {}
                    for i in range(len(mosaic_field[band][vis][target]['field_ids'])):
                        found = False
                        for j in range(len(all_phasecenters)):
                            distance = ((all_phasecenters[j][0] - mosaic_field[band][vis][target]['phasecenters'][i][0])**2 +
                                        (all_phasecenters[j][1] - mosaic_field[band][vis][target]['phasecenters'][i][1])**2)**0.5
                            if distance < 4.84814e-6:
                                selfcal_library[target][band]['sub-fields-fid_map'][vis][j] = mosaic_field[band][vis][target]['field_ids'][i]
                                found = True
                                break
                        if not found:
                            all_phasecenters.append(mosaic_field[band][vis][target]['phasecenters'][i])
                            selfcal_library[target][band]['sub-fields-fid_map'][vis][
                                len(all_phasecenters) - 1] = mosaic_field[band][vis][target]['field_ids'][i]

                selfcal_library[target][band]['sub-fields'] = list(range(len(all_phasecenters)))
                selfcal_library[target][band]['sub-fields-to-selfcal'] = list(range(len(all_phasecenters)))
                selfcal_library[target][band]['sub-fields-phasecenters'] = dict(
                    zip(selfcal_library[target][band]['sub-fields'], all_phasecenters))

                # Now we can start to create a sub-field selfcal_library entry for each sub-field.
                for fid in selfcal_library[target][band]['sub-fields']:
                    selfcal_library[target][band][fid] = {}
                    for vis in vislist:
                        if fid not in selfcal_library[target][band]['sub-fields-fid_map'][vis]:
                            continue
                        selfcal_library[target][band][fid][vis] = {}

        ##
        # puts stuff in right place from other MS metadata to perform proper data selections
        # in tclean, gaincal, and applycal
        # Also gets relevant times on source to estimate SNR per EB/scan
        ##
        for target in all_targets:
            for band in selfcal_library[target].keys():
                LOG.info(f'{target} {band}')
                selfcal_library[target][band]['SC_success'] = False
                selfcal_library[target][band]['final_solint'] = 'None'
                selfcal_library[target][band]['Total_TOS'] = 0.0
                selfcal_library[target][band]['spws'] = []
                selfcal_library[target][band]['spws_per_vis'] = []
                selfcal_library[target][band]['nterms'] = get_nterms(band_properties[vislist[0]][band]['fracbw'])
                selfcal_library[target][band]['reffreq'] = self.reffreq
                selfcal_library[target][band]['vislist'] = vislist.copy()

                allscantimes = np.array([])
                allscannfields = np.array([])
                for vis in vislist:
                    selfcal_library[target][band][vis]['gaintable'] = []
                    selfcal_library[target][band][vis]['TOS'] = np.sum(scantimesdict[band][vis][target])
                    selfcal_library[target][band][vis]['Median_scan_time'] = np.median(scantimesdict[band][vis][target])
                    selfcal_library[target][band][vis]['Median_fields_per_scan'] = np.median(
                        scannfieldsdict[band][vis][target]
                    )
                    allscantimes = np.append(allscantimes, scantimesdict[band][vis][target])
                    allscannfields = np.append(allscannfields, scannfieldsdict[band][vis][target])
                    selfcal_library[target][band][vis]['refant'] = rank_refants(
                        vis, refantignore=self.refantignore.get(vis, '')
                    )
                    selfcal_library[target][band][vis]['spws'] = band_properties[vis][band]['spwstring']
                    selfcal_library[target][band][vis]['spwsarray'] = band_properties[vis][band]['spwarray']
                    selfcal_library[target][band][vis]['spwlist'] = band_properties[vis][band]['spwarray'].tolist()
                    selfcal_library[target][band][vis]['n_spws'] = len(selfcal_library[target][band][vis]['spwsarray'])
                    selfcal_library[target][band][vis]['minspw'] = int(
                        np.min(selfcal_library[target][band][vis]['spwsarray'])
                    )

                    if band_properties[vis][band]['ncorrs'] == 1:
                        selfcal_library[target][band][vis]['pol_type'] = 'single-pol'
                    elif band_properties[vis][band]['ncorrs'] == 2:
                        selfcal_library[target][band][vis]['pol_type'] = 'dual-pol'
                    else:
                        selfcal_library[target][band][vis]['pol_type'] = 'full-pol'

                    if spectral_scan:
                        spwmap = np.zeros(np.max(spws_set[band][vis])+1, dtype='int')
                        spwmap.fill(np.min(spws_set[band][vis]))
                        for i in range(spws_set[band][vis].shape[0]):
                            indices = np.arange(np.min(spws_set[band][vis][i]), np.max(spws_set[band][vis][i])+1)
                            spwmap[indices] = np.min(spws_set[band][vis][i])
                        selfcal_library[target][band][vis]['spwmap'] = spwmap.tolist()
                    else:
                        selfcal_library[target][band][vis]['spwmap'] = [selfcal_library[target][band][
                            vis]['minspw']]*(np.max(selfcal_library[target][band][vis]['spwsarray'])+1)

                    selfcal_library[target][band]['Total_TOS'] = selfcal_library[target][band][vis]['TOS'] + \
                        selfcal_library[target][band]['Total_TOS']
                    selfcal_library[target][band]['spws_per_vis'].append(band_properties[vis][band]['spwstring'])
                selfcal_library[target][band]['Median_scan_time'] = np.median(allscantimes)
                selfcal_library[target][band]['Median_fields_per_scan'] = np.median(allscannfields)
                prototype_uvrange = get_uv_range(band, band_properties, vislist)
                selfcal_library[target][band]['uvrange'] = self.uvrange
                LOG.info(
                    f'using the Pipeline standard heuristics uvrange: {self.uvrange}, instead of the prototype uvrange: {prototype_uvrange}')
                selfcal_library[target][band]['75thpct_uv'] = band_properties[vislist[0]][band]['75thpct_uv']
                selfcal_library[target][band]['LAS'] = band_properties[vislist[0]][band]['LAS']
                selfcal_library[target][band]['fracbw'] = band_properties[vislist[0]][band]['fracbw']
                selfcal_library[target][band]['meanfreq']=band_properties[vislist[0]][band]['meanfreq']
                selfcal_library[target][band]['spectral_scan'] = spectral_scan
                selfcal_library[target][band]['spws_set'] = spws_set[band]

                if selfcal_library[target][band]['meanfreq'] > 12.0e9:
                    selfcal_library[target][band]['applycal_interp'] = 'linearPD'
                else:
                    selfcal_library[target][band]['applycal_interp'] = 'linear'

                uv75pct = selfcal_library[target][band]['75thpct_uv']
                if "VLA" in self.telescope or (selfcal_library[target][band]['obstype'] == 'mosaic' and
                                               selfcal_library[target][band]['Median_scan_time'] / selfcal_library[target][band]['Median_fields_per_scan'] < 60.) \
                        or uv75pct > 2000.0:
                    selfcal_library[target][band]['cyclefactor'] = 3.0
                else:
                    selfcal_library[target][band]['cyclefactor'] = 1.0

                for fid in selfcal_library[target][band]['sub-fields']:
                    selfcal_library[target][band][fid]['SC_success'] = False
                    selfcal_library[target][band][fid]['final_solint'] = 'None'
                    selfcal_library[target][band][fid]['Total_TOS'] = 0.0
                    selfcal_library[target][band][fid]['spws'] = []
                    selfcal_library[target][band][fid]['spws_per_vis'] = []
                    selfcal_library[target][band][fid]['nterms'] = selfcal_library[target][band]['nterms']
                    selfcal_library[target][band][fid]['reffreq'] = self.reffreq
                    selfcal_library[target][band][fid]['vislist'] = [vis for vis in vislist
                                                                     if fid in selfcal_library[target][band]['sub-fields-fid_map'][vis]]
                    selfcal_library[target][band][fid]['obstype'] = 'single-point'
                    allscantimes = np.array([])
                    allscannfields = np.array([])
                    for vis in selfcal_library[target][band][fid]['vislist']:
                        good = np.array([str(selfcal_library[target][band]['sub-fields-fid_map'][vis][fid]) in scan_fields
                                         for scan_fields in scanfieldsdict[band][vis][target]])
                        selfcal_library[target][band][fid][vis]['gaintable'] = []
                        selfcal_library[target][band][fid][vis]['TOS'] = np.sum(
                            scantimesdict[band][vis][target][good]/scannfieldsdict[band][vis][target][good])
                        selfcal_library[target][band][fid][vis]['Median_scan_time'] = np.median(
                            scantimesdict[band][vis][target][good]/scannfieldsdict[band][vis][target][good])
                        selfcal_library[target][band][fid][vis]['Median_fields_per_scan'] = 1
                        allscantimes = np.append(allscantimes, scantimesdict[band][vis]
                                                 [target][good]/scannfieldsdict[band][vis][target][good])
                        allscannfields = np.append(allscannfields, [1])
                        selfcal_library[target][band][fid][vis]['refant'] = selfcal_library[target][band][vis]['refant']
                        # n_spws,minspw,spwsarray=fetch_spws([vis],[target])
                        # spwslist=spwsarray.tolist()
                        # spwstring=','.join(str(spw) for spw in spwslist)
                        selfcal_library[target][band][fid][vis]['spws'] = band_properties[vis][band]['spwstring']
                        selfcal_library[target][band][fid][vis]['spwsarray'] = band_properties[vis][band]['spwarray']
                        selfcal_library[target][band][fid][vis]['spwlist'] = band_properties[vis][band]['spwarray'].tolist()
                        selfcal_library[target][band][fid][vis]['n_spws'] = len(
                            selfcal_library[target][band][fid][vis]['spwsarray'])
                        selfcal_library[target][band][fid][vis]['minspw'] = int(
                            np.min(selfcal_library[target][band][fid][vis]['spwsarray']))

                        if band_properties[vis][band]['ncorrs'] == 1:
                            selfcal_library[target][band][fid][vis]['pol_type'] = 'single-pol'
                        elif band_properties[vis][band]['ncorrs'] == 2:
                            selfcal_library[target][band][fid][vis]['pol_type'] = 'dual-pol'
                        else:
                            selfcal_library[target][band][fid][vis]['pol_type'] = 'full-pol'

                        if spectral_scan:
                            spwmap = np.zeros(np.max(spws_set[band][vis])+1, dtype='int')
                            spwmap.fill(np.min(spws_set[band][vis]))
                            for i in range(spws_set[band][vis].shape[0]):
                                indices = np.arange(np.min(spws_set[band][vis][i]), np.max(spws_set[band][vis][i])+1)
                                spwmap[indices] = np.min(spws_set[band][vis][i])
                            selfcal_library[target][band][fid][vis]['spwmap'] = spwmap.tolist()
                        else:
                            selfcal_library[target][band][fid][vis]['spwmap'] = [selfcal_library[target][band][fid]
                                                                                 [vis]['minspw']]*(np.max(selfcal_library[target][band][fid][vis]['spwsarray'])+1)

                        selfcal_library[target][band][fid]['Total_TOS'] = selfcal_library[target][band][fid][vis]['TOS'] + \
                            selfcal_library[target][band][fid]['Total_TOS']
                        selfcal_library[target][band][fid]['spws_per_vis'].append(
                            band_properties[vis][band]['spwstring'])
                    selfcal_library[target][band][fid]['Median_scan_time'] = np.median(allscantimes)
                    selfcal_library[target][band][fid]['Median_fields_per_scan'] = np.median(allscannfields)
                    selfcal_library[target][band][fid]['uvrange'] = get_uv_range(band, band_properties, vislist)
                    selfcal_library[target][band][fid]['75thpct_uv'] = band_properties[vislist[0]][band]['75thpct_uv']
                    selfcal_library[target][band][fid]['LAS'] = band_properties[vislist[0]][band]['LAS']

        for target in all_targets:
            for band in selfcal_library[target].keys():
                if selfcal_library[target][band]['Total_TOS'] == 0.0:
                    selfcal_library[target].pop(band)

        # Get the per-spw stats.

        for target in all_targets:
            for band in selfcal_library[target].keys():
                selfcal_library[target][band]['per_spw_stats'] = {}
                vislist = selfcal_library[target][band]['vislist'].copy()

                selfcal_library[target][band]['spw_map'], selfcal_library[target][band]['reverse_spw_map'] = get_spw_map(
                    self.image_heuristics.observing_run)

                # code to work around some VLA data not having the same number of spws due to missing BlBPs
                # selects spwlist from the visibilities with the greates number of spws
                # PS: We now track spws on an EB by EB basis soI have removed much of the maxspwvis code.
                spw_bandwidths_dict = {}
                spw_effective_bandwidths_dict = {}
                for vis in selfcal_library[target][band]['vislist']:
                    selfcal_library[target][band][vis]['per_spw_stats'] = {}

                    spw_bandwidths_dict[vis], spw_effective_bandwidths_dict[vis] = get_spw_bandwidth(
                        vis, target, self.image_heuristics.observing_run
                    )

                    selfcal_library[target][band][vis]['total_bandwidth'] = 0.0
                    selfcal_library[target][band][vis]['total_effective_bandwidth'] = 0.0
                    if len(spw_effective_bandwidths_dict[vis].keys()) != len(spw_bandwidths_dict[vis].keys()):
                        LOG.info('cont.dat does not contain all spws; falling back to total bandwidth')
                        for spw in spw_bandwidths_dict[vis].keys():
                            if spw not in spw_effective_bandwidths_dict[vis].keys():
                                spw_effective_bandwidths_dict[vis][spw] = spw_bandwidths_dict[vis][spw]

                    for spw in selfcal_library[target][band][vis]['spwlist']:
                        keylist = selfcal_library[target][band][vis]['per_spw_stats'].keys()
                        if spw not in keylist:
                            selfcal_library[target][band][vis]['per_spw_stats'][spw] = {}

                        selfcal_library[target][band][vis]['per_spw_stats'][spw]['effective_bandwidth'] = spw_effective_bandwidths_dict[vis][spw]
                        selfcal_library[target][band][vis]['per_spw_stats'][spw]['bandwidth'] = spw_bandwidths_dict[vis][spw]
                        selfcal_library[target][band][vis]['total_bandwidth'] += spw_bandwidths_dict[vis][spw]
                        selfcal_library[target][band][vis]['total_effective_bandwidth'] += spw_effective_bandwidths_dict[vis][spw]

                for fid in selfcal_library[target][band]['sub-fields']:
                    selfcal_library[target][band][fid]['per_spw_stats'] = {}
                    selfcal_library[target][band][fid]['spw_map'] = selfcal_library[target][band]['spw_map']
                    selfcal_library[target][band][fid]['reverse_spw_map'] = selfcal_library[target][band]['reverse_spw_map']
                    for vis in selfcal_library[target][band][fid]['vislist']:
                        selfcal_library[target][band][fid][vis]['per_spw_stats'] = {}
                        spw_bandwidths, spw_effective_bandwidths = get_spw_bandwidth(
                            vis, target, self.image_heuristics.observing_run
                        )
                        selfcal_library[target][band][fid][vis]['total_bandwidth'] = 0.0
                        selfcal_library[target][band][fid][vis]['total_effective_bandwidth'] = 0.0
                        if len(spw_effective_bandwidths.keys()) != len(spw_bandwidths.keys()):
                            LOG.info('cont.dat does not contain all spws; falling back to total bandwidth')
                            for spw in spw_bandwidths.keys():
                                if spw not in spw_effective_bandwidths.keys():
                                    spw_effective_bandwidths[spw] = spw_bandwidths[spw]
                        for spw in selfcal_library[target][band][fid][vis]['spwlist']:
                            keylist = selfcal_library[target][band][fid][vis]['per_spw_stats'].keys()
                            if spw not in keylist:
                                selfcal_library[target][band][fid][vis]['per_spw_stats'][spw] = {}
                            selfcal_library[target][band][fid][vis]['per_spw_stats'][spw]['effective_bandwidth'] = spw_effective_bandwidths[spw]
                            selfcal_library[target][band][fid][vis]['per_spw_stats'][spw]['bandwidth'] = spw_bandwidths[spw]
                            selfcal_library[target][band][fid][vis]['total_bandwidth'] += spw_bandwidths[spw]
                            selfcal_library[target][band][fid][vis]['total_effective_bandwidth'] += spw_effective_bandwidths[spw]

        ##
        # finds solints, starting with inf, ending with int, and tries to align
        # solints with number of integrations
        # solints reduce by factor of 2 in each self-cal interation
        # e.g., inf, max_scan_time/2.0, prev_solint/2.0, ..., int
        # starting solints will have solint the length of the entire EB to correct bulk offsets
        ##

        selfcal_plan = {}
        for target in all_targets:
            selfcal_plan[target] = {}

            for band in selfcal_library[target]:
                selfcal_plan[target][band] = {}
                if band in selfcal_library[target]:
                    selfcal_plan[target][band]['solints'], selfcal_plan[target][band]['integration_time'], selfcal_plan[target][band]['gaincal_combine'], selfcal_plan[target][band]['solmode'] = get_solints_simple(vislist, scantimesdict[band], 
                                                                               scannfieldsdict[band], 
                                                                               scanstartsdict[band], 
                                                                               scanendsdict[band], 
                                                                               integrationtimesdict[band], 
                                                                               self.inf_EB_gaincal_combine, 
                                                                               do_amp_selfcal=self.do_amp_selfcal, 
                                                                               mosaic=mosaic_field[band][vislist[0]][target]['mosaic'])
                LOG.info('%s %s %s', band, target, selfcal_plan[target][band]['solints'])
                selfcal_plan[target][band]['applycal_mode'] = [self.apply_cal_mode_default]*len(selfcal_plan[target][band]['solints'])


        for target in selfcal_plan:
            for band in selfcal_plan[target]:
                for vis in selfcal_library[target][band]['vislist']:
                    selfcal_plan[target][band][vis] = {}
                    selfcal_plan[target][band][vis]['inf_EB_gaincal_combine']=self.inf_EB_gaincal_combine #'scan'
                    if selfcal_library[target][band]['obstype']=='mosaic':
                        selfcal_plan[target][band][vis]['inf_EB_gaincal_combine']+=',field'   

                    if selfcal_library[target][band][vis]['pol_type'] == 'single-pol':
                        selfcal_plan[target][band][vis]['inf_EB_gaintype']='T'
                    else:
                        selfcal_plan[target][band][vis]['inf_EB_gaintype']=self.inf_EB_gaintype #G

                    selfcal_plan[target][band][vis]['inf_EB_fallback_mode']='' #'scan'


        return selfcal_library, selfcal_plan, gaincalibrator_dict

    def set_clean_thresholds(self, selfcal_library, selfcal_plan, dividing_factor=-99.0, rel_thresh_scaling='log10', telescope='ALMA'):
        for target in selfcal_library:
            for band in selfcal_library[target].keys():
                if dividing_factor is None:
                    if selfcal_library[target][band]['meanfreq'] < 8.0e9:
                        dividing_factor_band = 40.0
                    else:
                        dividing_factor_band = 15.0
                else:
                    dividing_factor_band = dividing_factor

                # restricts initial nsigma to be at least 5
                nsigma_init = np.max([selfcal_library[target][band]['SNR_orig']/dividing_factor_band, 5.0])

                # count number of amplitude selfcal solints, repeat final clean depth of phase-only for amplitude selfcal
                n_ap_solints = sum(1 for solint in selfcal_plan[target][band]['solints'] if 'ap' in solint)
                if rel_thresh_scaling == 'loge':
                    selfcal_library[target][band]['nsigma'] = np.append(
                        np.exp(np.linspace(np.log(nsigma_init),
                                           np.log(3.0),
                                           len(selfcal_plan[target][band]['solints']) - n_ap_solints)),
                        np.array([np.exp(np.log(3.0))] * n_ap_solints))
                elif rel_thresh_scaling == 'linear':
                    selfcal_library[target][band]['nsigma'] = np.append(
                        np.linspace(nsigma_init, 3.0, len(selfcal_plan[target][band]['solints']) - n_ap_solints),
                        np.array([3.0] * n_ap_solints))
                else:  # implicitly making log10 the default
                    selfcal_library[target][band]['nsigma'] = np.append(
                        10 ** np.linspace(np.log10(nsigma_init),
                                          np.log10(3.0),
                                          len(selfcal_plan[target][band]['solints']) - n_ap_solints),
                        np.array([10 ** (np.log10(3.0))] * n_ap_solints))
                if telescope == 'ALMA' or telescope == 'ACA':  # or ('VLA' in telescope)
                    sensitivity, _, _ = self.get_sensitivity()
                    if band == 'Band_9' or band == 'Band_10':   # adjust for DSB noise increase
                        sensitivity = sensitivity*4.0
                    if ('VLA' in telescope):
                        sensitivity = sensitivity*0.0  # empirical correction, VLA estimates for sensitivity have tended to be a factor of ~3 low
                else:
                    sensitivity = 0.0
                selfcal_library[target][band]['thresholds'] = selfcal_library[target][band]['nsigma']*sensitivity

    def evaluate_subfields_to_gaincal(self, slib, sani_target, band, solint, iteration, selfcal_plan, 
                                      minsnr_to_proceed, allow_gain_interpolation=False):

        new_fields_to_selfcal = []
        for fid in slib['sub-fields-to-selfcal']:
            os.system('rm -rf test*.mask')
            tmp_SNR_NF, tmp_RMS_NF = estimate_near_field_SNR(sani_target+'_field_'+str(fid)+'_'+band+'_'+solint+'_'+str(iteration)+'.image.tt0',
                                                                las=slib['LAS'], mosaic_sub_field=True, save_near_field_mask=False)

            self.cts.immath(imagename=[sani_target+"_field_"+str(fid)+"_"+band+"_"+solint+"_"+str(iteration)+".image.tt0",
                            sani_target+"_field_"+str(fid)+"_"+band+"_"+solint +
                            "_"+str(iteration)+".pb.tt0",
                            sani_target+"_field_"+str(fid)+"_"+band+"_"+solint+"_"+str(iteration)+".mospb.tt0"], outfile="test.mask",
                            expr="IIF(IM0*IM1/IM2 > "+str(5*tmp_RMS_NF)+", 1., 0.)")

            bmaj = ''.join(np.array(list(self.cts.imhead(sani_target+"_field_"+str(fid)+"_"+band+"_"+solint+"_"+str(iteration)+".image.tt0",
                                                            mode="get", hdkey="bmaj").values())[::-1]).astype(str))
            bmin = ''.join(np.array(list(self.cts.imhead(sani_target+"_field_"+str(fid)+"_"+band+"_"+solint+"_"+str(iteration)+".image.tt0",
                                                            mode="get", hdkey="bmin").values())[::-1]).astype(str))
            bpa = ''.join(np.array(list(self.cts.imhead(sani_target+"_field_"+str(fid)+"_"+band+"_"+solint+"_"+str(iteration)+".image.tt0",
                                                        mode="get", hdkey="bpa").values())[::-1]).astype(str))

            self.cts.imsmooth("test.mask", kernel="gauss", major=bmaj,
                                minor=bmin, pa=bpa, outfile="test.smoothed.mask")

            self.cts.immath(imagename=["test.smoothed.mask", sani_target+"_field_"+str(fid)+"_"+band+"_"+solint+"_"+str(iteration)+".mask"],
                            outfile="test.smoothed.truncated.mask", expr="IIF(IM0 > 0.01 || IM1 > 0., 1., 0.)")

            original_intflux = get_intflux(sani_target+"_field_"+str(fid)+"_"+band+"_"+solint+"_"+str(iteration)+".image.tt0",
                                            rms=tmp_RMS_NF, maskname=sani_target+"_field_" +
                                            str(fid)+"_"+band+"_"+solint+"_"+str(iteration)+".mask",
                                            mosaic_sub_field=True)[0]
            updated_intflux = get_intflux(sani_target+"_field_"+str(fid)+"_"+band+"_"+solint+"_"+str(iteration)+".image.tt0",
                                            rms=tmp_RMS_NF, maskname="test.smoothed.truncated.mask", mosaic_sub_field=True)[0]
            os.system('rm -rf test*.mask')

            if not checkmask(sani_target+'_field_'+str(fid)+'_'+band+'_'+solint+'_'+str(iteration)+'.image.tt0'):
                LOG.info("Removing field "+str(fid)+" from "+sani_target+'_'+vis+'_'+band+'_'+solint+'_'+str(iteration)+'_' +
                            selfcal_plan['solmode'][iteration]+'.g'+" because there is no signal within the primary beam.")
                skip_reason = "No signal"
            elif selfcal_plan[fid]['solint_snr_per_field'][selfcal_plan['solints'][iteration]] < minsnr_to_proceed and solint not in ['inf_EB', 'scan_inf']:
                LOG.info("Removing field "+str(fid)+" from "+sani_target+'_'+vis+'_'+band+'_'+solint+'_'+str(iteration)+'_' +
                            selfcal_plan['solmode'][iteration]+'.g'+' because the estimated solint snr is too low.')
                skip_reason = "Estimated SNR"
            elif updated_intflux > 1.25 * original_intflux:
                LOG.info("Removing field "+str(fid)+" from "+sani_target+'_'+vis+'_'+band+'_'+solint+'_'+str(iteration)+'_' +
                            selfcal_plan['solmode'][iteration]+'.g'+" because there appears to be significant flux missing from the model.")
                skip_reason = "Missing flux"
            else:
                new_fields_to_selfcal.append(fid)

            if fid not in new_fields_to_selfcal and solint != "inf_EB" and not allow_gain_interpolation:
                for vis in slib[fid]['vislist']:
                    # slib[fid][vis][solint]['interpolated_gains'] = True
                    # slib[fid]['Stop_Reason'] = "Gaincal solutions would be interpolated"
                    slib[fid]['Stop_Reason'] = skip_reason
                    slib[fid][vis][solint]['Pass'] = "None"
                    slib[fid][vis][solint]['Fail_Reason'] = skip_reason

        return new_fields_to_selfcal

    def evaluate_subfields_after_gaincal(self, slib, sani_target, band, solint, iteration, selfcal_plan, allow_gain_interpolation=False):

        new_fields_to_selfcal = slib['sub-fields-to-selfcal'].copy()

        if slib['obstype'] == 'mosaic' and ((solint != "inf_EB" and not allow_gain_interpolation) or
                                            (allow_gain_interpolation and "inf" not in solint)):
            # With gaincal done and bad fields removed from gain tables if necessary, check whether any fields should no longer be selfcal'd
            # because they have too much interpolation.
            for vis in slib['vislist']:
                # If an EB had no fields to gaincal on, remove all fields in that EB from being selfcal'd as there is no calibration available
                # in this EB.
                if np.intersect1d(slib['sub-fields-to-gaincal'],
                                    list(slib['sub-fields-fid_map'][vis].keys())).size == 0:
                    for fid in np.intersect1d(new_fields_to_selfcal, list(slib['sub-fields-fid_map'][vis].keys())):
                        new_fields_to_selfcal.remove(fid)

                        slib[fid]['Stop_Reason'] = 'No viable calibrator fields in at least 1 EB'
                        for v in slib[fid]['vislist']:
                            slib[fid][v][solint]['Pass'] = 'None'
                            if 'Fail_Reason' in slib[fid][v][solint]:
                                slib[fid][v][solint]['Fail_Reason'] += '; '
                            else:
                                slib[fid][v][solint]['Fail_Reason'] = ''
                            slib[fid][v][solint]['Fail_Reason'] += 'No viable fields'
                    continue
                # NEXT TO DO: check % of flagged solutions - DONE, see above
                # After that enable option for interpolation through inf - DONE
                tb.open(sani_target+'_'+vis+'_'+band+'_'+solint+'_' +
                        str(iteration)+'_'+selfcal_plan['solmode'][iteration]+'.g')
                fields = tb.getcol("FIELD_ID")
                scans = tb.getcol("SCAN_NUMBER")

                for fid in np.intersect1d(new_fields_to_selfcal, list(slib['sub-fields-fid_map'][vis].keys())):
                    if solint == "scan_inf":
                        # For the 'scan_inf' solint, solutions are computed using combine='field,scan' or 'spw,field,scan' with 
                        # scan=scangroup, covering each scan group, and the results are incrementally aggregated into the same gain table.  
                        #   * The resulting table (before any modifications) has a row count of n_antenna * n_scangroup.  
                        #   * Note that a scangroup may consist of one or multiple scans.  
                        #   * The scan_number and field_id columns generally contain the first scan/field of the scangroup.  
                        msmd.open(vis)
                        scans_for_field = []
                        cals_for_scan = []
                        total_cals_for_scan = []
                        for incl_scan in slib[vis][solint]['include_scans']:
                            scans_array = np.array(incl_scan.split(",")).astype(int)
                            fields_for_scans = msmd.fieldsforscans(scans_array)

                            if slib['sub-fields-fid_map'][vis][fid] in fields_for_scans:
                                # because the gaintable SCAN_NUMBER column should only contain first entry of scan_array, or, 
                                # not intersect with scan_array at all, scans_for_field[-1] should contain either 0-element or 1-element.
                                scans_for_field.append(np.intersect1d(scans_array, np.unique(scans)))
                                if scans_for_field[-1].size>0 and scans_for_field[-1] in scans:
                                    cals_for_scan.append((scans == scans_for_field[-1]).sum())
                                else:
                                    cals_for_scan.append(0)
                                total_cals_for_scan.append(len(msmd.antennanames()))
                        if (
                            sum(total_cals_for_scan) == 0
                            or sum(cals_for_scan) / sum(total_cals_for_scan) < 0.75
                        ):
                            new_fields_to_selfcal.remove(fid)

                        msmd.close()
                    else:
                        if slib['sub-fields-fid_map'][vis][fid] not in fields:
                            new_fields_to_selfcal.remove(fid)

                    if fid not in new_fields_to_selfcal:
                        # We need to update all the EBs, not just the one that failed.
                        for v in slib[fid]['vislist']:
                            slib[fid][v][solint]['Pass'] = 'None'
                            if allow_gain_interpolation:
                                slib[fid][v][solint]['Fail_Reason'] = 'Interpolation beyond inf'
                            else:
                                slib[fid][v][solint]['Fail_Reason'] = 'Bad gaincal solutions'

                tb.close()
        elif slib['obstype'] == 'mosaic' and solint == "inf_EB":
            # If an EB had no fields to gaincal on, remove all fields in that EB from being selfcal'd as there is no calibration available
            # in this EB.
            for vis in slib['vislist']:
                if np.intersect1d(slib['sub-fields-to-gaincal'],
                                    list(slib['sub-fields-fid_map'][vis].keys())).size == 0:
                    for fid in np.intersect1d(new_fields_to_selfcal, list(slib['sub-fields-fid_map'][vis].keys())):
                        new_fields_to_selfcal.remove(fid)

                        slib[fid]['Stop_Reason'] = 'No viable calibrator fields for inf_EB in at least 1 EB'
                        for v in slib[fid]['vislist']:
                            slib[fid][v][solint]['Pass'] = 'None'
                            slib[fid][v][solint]['Fail_Reason'] = 'No viable inf_EB fields'

        return new_fields_to_selfcal

    def run_selfcal(self, selfcal_library, selfcal_plan, target, band, telescope, n_ants,
                    gaincal_minsnr=2.0, gaincal_unflag_minsnr=5.0, minsnr_to_proceed=3.0, delta_beam_thresh=0.05, do_amp_selfcal=True,
                    inf_EB_gaincal_combine='scan', inf_EB_gaintype='G',
                    unflag_only_lbants=False, unflag_only_lbants_onlyap=False, calonly_max_flagged=0.0,
                    second_iter_solmode="", unflag_fb_to_prev_solint=False,
                    rerank_refants=False, gaincalibrator_dict={}, allow_gain_interpolation=False,
                    guess_scan_combine=False, aca_use_nfmask=False):

        # If we are running this on a mosaic, we want to rerank reference antennas and have a higher gaincal_minsnr by default.

        slib = selfcal_library

        if self.is_mosaic:
            gaincal_minsnr = 2.0
            rerank_refants = True
            refantmode = "strict"
        else:
            refantmode = "flex"

        # Start looping over the solints.

        iterjump = -1   # useful if we want to jump iterations
        sani_target = 'sc.'+filenamer.sanitize(target)
        vislist = slib['vislist'].copy()
        LOG.info('Starting selfcal procedure on: '+target+' '+band)
        if selfcal_library['usermodel'] != '':
            LOG.info('Setting model column to user model')
            self.usermodel_wrapper(selfcal_library, sani_target+'_'+band,
                                   telescope=self.telescope, nsigma=0.0, scales=[0],
                                   threshold='0.0Jy',
                                   savemodel='modelcolumn', parallel=self.parallel,
                                   field=target, spw=slib['spws_per_vis'], 
                                   resume=False, cyclefactor=slib['cyclefactor'])

        for iteration in range(len(selfcal_plan['solints'])):
            if (iterjump != -1) and (iteration < iterjump):  # allow jumping to amplitude selfcal and not need to use a while loop
                continue
            elif iteration == iterjump:
                iterjump = -1

            if 'ap' in selfcal_plan['solints'][iteration] and not do_amp_selfcal:
                break

            if selfcal_plan['solint_snr'][selfcal_plan['solints'][iteration]] < minsnr_to_proceed and np.all([selfcal_plan['solint_snr_per_field'][fid][selfcal_plan['solints'][iteration]] < minsnr_to_proceed for fid in slib['sub-fields']]):
                LOG.info('*********** estimated SNR for solint='+selfcal_plan['solints'][iteration]+' too low, measured: '+str(
                    selfcal_plan['solint_snr'][selfcal_plan['solints'][iteration]])+', Min SNR Required: '+str(minsnr_to_proceed)+' **************')
                # if a solution interval shorter than inf for phase-only SC has passed, attempt amplitude selfcal
                if iteration > 1 and selfcal_plan['solmode'][iteration] != 'ap' and do_amp_selfcal:
                    iterjump = selfcal_plan['solmode'].index('ap')
                    LOG.info('****************Attempting amplitude selfcal*************')
                    continue

                slib['Stop_Reason'] = 'Estimated_SNR_too_low_for_solint ' + \
                    selfcal_plan['solints'][iteration]
                break
            else:
                solint = selfcal_plan['solints'][iteration]
                if iteration == 0:
                    LOG.info('Starting with solint: '+solint)
                else:
                    LOG.info('Continuing with solint: '+solint)
                os.system('rm -rf '+sani_target+'_'+band+'_'+solint+'_'+str(iteration)+'*')
                ##
                # make images using the appropriate tclean heuristics for each telescope
                # set threshold based on RMS of initial image and lower if value becomes lower
                # during selfcal by resetting 'RMS_curr' after the post-applycal evaluation
                ##
                if slib['final_solint'] != 'None':
                    prev_solint = slib['final_solint']
                    prev_iteration = slib[vislist[0]][prev_solint]['iteration']

                    nterms_changed = (len(glob.glob(sani_target+'_'+band+'_'+prev_solint+'_'+str(prev_iteration)+"_post.model.tt*")) <
                                      slib['nterms'])

                    if nterms_changed:
                        resume = False
                    else:
                        resume = True
                        files = glob.glob(sani_target+'_'+band+'_'+prev_solint+'_'+str(prev_iteration)+"_post.*")
                        for f in files:
                            if "nearfield" in f:
                                continue
                            os.system("cp -r "+f+" "+f.replace(prev_solint+"_" +
                                                               str(prev_iteration)+"_post", solint+'_'+str(iteration)))
                else:
                    resume = False

                nfrms_multiplier = slib['RMS_NF_curr'] / slib['RMS_curr']

                # Record solint details.
                for vis in vislist:
                    slib[vis][solint] = {}
                    slib[vis][solint]['clean_threshold'] = slib['nsigma'][iteration]*slib['RMS_NF_curr']
                    slib[vis][solint]['nfrms_multiplier'] = nfrms_multiplier
                    for fid in np.intersect1d(slib['sub-fields-to-selfcal'], list(slib['sub-fields-fid_map'][vis].keys())):
                        slib[fid][vis][solint] = {}
                        slib[fid][vis][solint]['clean_threshold'] = slib['nsigma'][iteration]*slib['RMS_NF_curr']
                        slib[fid][vis][solint]['nfrms_multiplier'] = nfrms_multiplier

                # remove mask if exists from previous selfcal _post image user is specifying a mask
                if os.path.exists(sani_target+'_'+band+'_'+solint+'_'+str(iteration)+'.mask') and selfcal_library['usermask'] != '':
                    os.system('rm -rf '+sani_target+'_'+band+'_'+solint+'_'+str(iteration)+'.mask')
                self.tclean_wrapper(selfcal_library, sani_target+'_'+band+'_'+solint+'_'+str(iteration),
                                    band, telescope=telescope, nsigma=slib['nsigma'][iteration], scales=[
                                        0],
                                    # threshold=str(slib['nsigma'][iteration]* slib['RMS_NF_curr'])+'Jy',
                                    threshold=str(slib[vislist[0]][solint]['clean_threshold'])+'Jy',
                                    savemodel='none', parallel=self.parallel,
                                    field=target,
                                    nfrms_multiplier=slib[vislist[0]][solint]['nfrms_multiplier'], resume=resume)

                # Check that a mask was actually created, because if not the model will be empty and gaincal will do bad things and the
                # code will break.
                if not checkmask(sani_target+'_'+band+'_'+solint+'_'+str(iteration)+'.image.tt0'):
                    slib['Stop_Reason'] = 'Empty model for solint '+solint
                    break  # breakout of loop because the model is empty and gaincal will therefore fail

                # Loop through up to two times. On the first attempt, try applymode = 'calflag' (assuming this is requested by the user). On the
                # second attempt, use applymode = 'calonly'.
                for applymode in np.unique([selfcal_plan['applycal_mode'][iteration], 'calonly']):
                    for vis in vislist:
                        ##
                        # Restore original flagging state each time before applying a new gaintable
                        ##
                        if os.path.exists(vis+".flagversions/flags.selfcal_starting_flags_"+sani_target+'_'+band):
                            self.cts.flagmanager(vis=vis, mode='restore', versionname='selfcal_starting_flags_' +
                                                 sani_target+'_'+band, comment='Flag states at start of reduction')
                        else:
                            self.cts.flagmanager(vis=vis, mode='save',
                                                 versionname='selfcal_starting_flags_'+sani_target+'_'+band)

                    # We need to redo saving the model now that we have potentially unflagged some data.
                    if applymode == "calflag":
                        self.tclean_wrapper(selfcal_library, sani_target+'_'+band+'_'+solint+'_'+str(iteration),
                                            band, telescope=telescope, nsigma=slib['nsigma'][iteration], scales=[
                                                0],
                                            # threshold=str(slib['nsigma'][iteration]* slib['RMS_NF_curr'])+'Jy',
                                            threshold=str(slib[vislist[0]][solint]['clean_threshold'])+'Jy',
                                            savemodel='modelcolumn', parallel=self.parallel,
                                            field=target,
                                            nfrms_multiplier=slib[vislist[0]][solint]['nfrms_multiplier'],
                                            savemodel_only=True)

                    # Fields that don't have any mask in the primary beam should be removed from consideration, as their models are likely bad.
                    if slib['obstype'] == 'mosaic':
                        slib['sub-fields-to-gaincal'] = self.evaluate_subfields_to_gaincal(slib, sani_target, band, solint, iteration, selfcal_plan, 
                                      minsnr_to_proceed, allow_gain_interpolation=allow_gain_interpolation)

                        if solint != 'inf_EB' and not allow_gain_interpolation:
                            slib['sub-fields-to-selfcal'] = slib['sub-fields-to-gaincal']
                    else:
                        slib['sub-fields-to-gaincal'] = slib['sub-fields-to-selfcal']

                    # Calculate the complex gains.
                    for vis in vislist:
                        if np.intersect1d(slib['sub-fields-to-gaincal'],
                                          list(slib['sub-fields-fid_map'][vis].keys())).size == 0:
                            continue

                        self.gaincal_wrapper(slib, selfcal_plan, target, band, vis, solint, applymode, iteration, telescope,
                                        gaincal_minsnr, gaincal_unflag_minsnr=gaincal_unflag_minsnr, minsnr_to_proceed=minsnr_to_proceed, 
                                        rerank_refants=rerank_refants, unflag_only_lbants=unflag_only_lbants, unflag_only_lbants_onlyap=unflag_only_lbants_onlyap,
                                        calonly_max_flagged=calonly_max_flagged, second_iter_solmode=second_iter_solmode, 
                                        unflag_fb_to_prev_solint=unflag_fb_to_prev_solint, refantmode=refantmode, gaincalibrator_dict=gaincalibrator_dict, 
                                        allow_gain_interpolation=allow_gain_interpolation, guess_scan_combine=guess_scan_combine)

                    # With gaincal done and bad fields removed from gain tables if necessary, check whether any fields should no longer be 
                    # selfcal'd because they have too much interpolation.
                    if selfcal_library['obstype'] == 'mosaic':
                        slib['sub-fields-to-selfcal'] = self.evaluate_subfields_after_gaincal(slib, sani_target, band, solint, iteration, selfcal_plan, 
                                                                                              allow_gain_interpolation=allow_gain_interpolation)

                    ##
                    # Apply gain solutions per MS, target, solint, and band
                    ##
                    for vis in vislist:
                        self.applycal_wrapper(vis, target, band, solint, slib, 
                                current=lambda f: f in slib['sub-fields-to-selfcal'],
                                final=lambda f: f not in slib['sub-fields-to-selfcal'] and slib[f]['SC_success'])

                    # Create post self-cal image using the model as a startmodel to evaluate how much selfcal helped
                    ##

                    os.system('rm -rf '+sani_target+'_'+band+'_'+solint+'_'+str(iteration)+'_post*')
                    self.tclean_wrapper(selfcal_library, sani_target+'_'+band+'_'+solint+'_'+str(iteration)+'_post',
                                        band, telescope=telescope, nsigma=slib['nsigma'][iteration], scales=[
                                            0],
                                        # threshold=str(slib['nsigma'][iteration]* slib['RMS_NF_curr'])+'Jy',
                                        threshold=str(slib[vislist[0]][solint]['clean_threshold'])+'Jy',
                                        savemodel='none', parallel=self.parallel,
                                        field=target,
                                        nfrms_multiplier=slib[vislist[0]][solint]['nfrms_multiplier'])

                    ##
                    # Do the assessment of the post- (and pre-) selfcal images.
                    ##
                    LOG.info('Pre selfcal assessemnt: '+target)
                    SNR, RMS, SNR_NF, RMS_NF = self.get_image_stats(sani_target+'_'+band+'_'+solint+'_'+str(iteration)+'.image.tt0', 
                            sani_target+'_'+band+'_'+solint+'_'+str(iteration)+'_post.mask', sani_target+'_'+band+'_'+solint+'_'+str(iteration)+'.mask', 
                            slib, (telescope != 'ACA' or aca_use_nfmask), solint, 'pre')

                    LOG.info('Post selfcal assessemnt: '+target)
                    post_SNR, post_RMS, post_SNR_NF, post_RMS_NF = self.get_image_stats(sani_target+'_'+band+'_'+solint+'_'+str(iteration)+'_post.image.tt0', 
                            sani_target+'_'+band+'_'+solint+'_'+str(iteration)+'_post.mask', sani_target+'_'+band+'_'+solint+'_'+str(iteration)+'.mask', 
                            slib, (telescope != 'ACA' or aca_use_nfmask), solint, 'post')

                    mosaic_SNR, mosaic_RMS, mosaic_SNR_NF, mosaic_RMS_NF = {}, {}, {}, {}
                    post_mosaic_SNR, post_mosaic_RMS, post_mosaic_SNR_NF, post_mosaic_RMS_NF = {}, {}, {}, {}
                    for fid in slib['sub-fields-to-selfcal']:
                        if slib['obstype'] == 'mosaic':
                            imagename = sani_target+'_field_'+str(fid)+'_'+band+'_'+solint+'_'+str(iteration)
                        else:
                            imagename = sani_target+'_'+band+'_'+solint+'_'+str(iteration)

                        LOG.info('')
                        LOG.info('Pre selfcal assessemnt: '+target+', field '+str(fid))
                        mosaic_SNR[fid], mosaic_RMS[fid], mosaic_SNR_NF[fid], mosaic_RMS_NF[fid] = self.get_image_stats(imagename+'.image.tt0', 
                                imagename+'_post.mask', imagename+'.mask', slib[fid], (telescope != 'ACA' or aca_use_nfmask), solint, 'pre', 
                                mosaic_sub_field=slib["obstype"]=="mosaic")

                        LOG.info('Post selfcal assessemnt: '+target+', field '+str(fid))
                        post_mosaic_SNR[fid], post_mosaic_RMS[fid], post_mosaic_SNR_NF[fid], post_mosaic_RMS_NF[fid] = self.get_image_stats(
                                imagename+'_post.image.tt0', imagename+'_post.mask', imagename+'.mask', slib[fid], 
                                (telescope != 'ACA' or aca_use_nfmask), solint, 'post', mosaic_sub_field=slib["obstype"]=="mosaic")
                        LOG.info('')

                    if slib['nterms'] < 2:
                        # Change nterms to 2 if needed based on fracbw and SNR
                        slib['nterms'] = get_nterms(
                            slib['fracbw'], post_SNR)

                    for vis in vislist:
                        # Update RMS value if necessary
                        if slib[vis][solint]['RMS_post'] < slib['RMS_curr'] and vis == vislist[-1]:
                            slib['RMS_curr'] = slib[vis][solint]['RMS_post'].copy()
                        if slib[vis][solint]['RMS_NF_post'] < slib['RMS_NF_curr'] and \
                                slib[vis][solint]['RMS_NF_post'] > 0 and vis == vislist[-1]:
                            slib['RMS_NF_curr'] = slib[vis][solint]['RMS_NF_post'].copy()

                    ##
                    # compare beam relative to original image to ensure we are not incrementally changing the beam in each iteration
                    ##
                    beamarea_orig = slib['Beam_major_orig'] * \
                        slib['Beam_minor_orig']
                    beamarea_post = slib[vislist[0]][solint]['Beam_major_post'] * \
                        slib[vislist[0]][solint]['Beam_minor_post']

                    delta_beamarea = (beamarea_post-beamarea_orig)/beamarea_orig
                    ##
                    # if S/N improvement, and beamarea is changing by < delta_beam_thresh, accept solutions to main calibration dictionary
                    # allow to proceed if solint was inf_EB and SNR decrease was less than 2%
                    ##
                    strict_field_by_field_success = []
                    loose_field_by_field_success = []
                    beam_field_by_field_success = []
                    rms_field_by_field_success = []
                    for fid in slib['sub-fields-to-selfcal']:
                        strict_field_by_field_success += [(post_mosaic_SNR[fid] >= mosaic_SNR[fid])
                                                          and (post_mosaic_SNR_NF[fid] >= mosaic_SNR_NF[fid])]
                        loose_field_by_field_success += [((post_mosaic_SNR[fid]-mosaic_SNR[fid])/mosaic_SNR[fid] > -0.02) and
                                                         ((post_mosaic_SNR_NF[fid] - mosaic_SNR_NF[fid])/mosaic_SNR_NF[fid] > -0.02)]
                        beam_field_by_field_success += [delta_beamarea < delta_beam_thresh]
                        rms_field_by_field_success = ((post_mosaic_RMS[fid] - mosaic_RMS[fid])/mosaic_RMS[fid] < 1.05 and
                                                      (post_mosaic_RMS_NF[fid] - mosaic_RMS_NF[fid])/mosaic_RMS_NF[fid] < 1.05) or \
                            (((post_mosaic_RMS[fid] - mosaic_RMS[fid])/mosaic_RMS[fid] > 1.05 or
                              (post_mosaic_RMS_NF[fid] - mosaic_RMS_NF[fid])/mosaic_RMS_NF[fid] > 1.05) and
                             selfcal_plan['solint_snr_per_field'][fid][solint] > 5)

                    if solint == 'inf_EB':
                        # If any of the fields succeed in the "strict" sense, then allow for minor reductions in the evaluation quantity in other
                        # fields because there's a good chance that those are just noise being pushed around.
                        field_by_field_success = np.logical_and(np.logical_and(loose_field_by_field_success, beam_field_by_field_success),
                                                                rms_field_by_field_success)
                    else:
                        field_by_field_success = np.logical_and(np.logical_and(strict_field_by_field_success, beam_field_by_field_success),
                                                                rms_field_by_field_success)

                    # If not all fields were successful, we need to make an additional image to evaluate whether the image as a whole improved,
                    # otherwise the _post image won't be exactly representative.
                    if slib['obstype'] == "mosaic" and not np.all(field_by_field_success):
                        field_by_field_success_dict = dict(
                            zip(slib['sub-fields-to-selfcal'], field_by_field_success))
                        LOG.info(
                            '****************Not all fields were successful, so re-applying and re-making _post image*************')
                        for vis in vislist:
                            self.applycal_wrapper(vis, target, band, solint, slib, 
                                    current=lambda f: f in field_by_field_success_dict and field_by_field_success_dict[f],
                                    final=lambda f: (f not in field_by_field_success_dict or not field_by_field_success_dict[f]) and 
                                        selfcal_library[f]['SC_success'],
                                    clear=lambda f: (f not in field_by_field_success_dict or not field_by_field_success_dict[f]) and 
                                        not selfcal_library[f]['SC_success'],
                                    restore_flags='selfcal_starting_flags_'+sani_target+'_'+band)

                        files = glob.glob(sani_target+'_'+band+'_'+solint+'_'+str(iteration)+"_post.*")
                        for f in files:
                            os.system("mv "+f+" "+f.replace("_post", "_post_intermediate"))

                        self.tclean_wrapper(selfcal_library, sani_target+'_'+band+'_'+solint+'_'+str(iteration)+'_post',
                                            band, telescope=telescope, nsigma=slib['nsigma'][iteration], scales=[
                                                0],
                                            threshold=str(slib[vislist[0]][solint]['clean_threshold'])+'Jy',
                                            savemodel='none', parallel=self.parallel,
                                            field=target, 
                                            nfrms_multiplier=slib[vislist[0]][solint]['nfrms_multiplier'],
                                            image_mosaic_fields_separately=False)

                        ##
                        # Do the assessment of the post- (and pre-) selfcal images.
                        ##
                        LOG.info('Pre selfcal assessemnt: '+target)
                        SNR, RMS, SNR_NF, RMS_NF = self.get_image_stats(sani_target+'_'+band+'_'+solint+'_'+str(iteration)+'.image.tt0', 
                                sani_target+'_'+band+'_'+solint+'_'+str(iteration)+'_post.mask', sani_target+'_'+band+'_'+solint+'_'+str(iteration)+'.mask', 
                                slib, (telescope != 'ACA' or aca_use_nfmask), solint, 'pre')

                        LOG.info('Post selfcal assessemnt: '+target)
                        post_SNR, post_RMS, post_SNR_NF, post_RMS_NF = self.get_image_stats(sani_target+'_'+band+'_'+solint+'_'+str(iteration)+'_post.image.tt0', 
                                sani_target+'_'+band+'_'+solint+'_'+str(iteration)+'_post.mask', sani_target+'_'+band+'_'+solint+'_'+str(iteration)+'.mask', 
                                slib, (telescope != 'ACA' or aca_use_nfmask), solint, 'post')

                        for vis in vislist:
                            slib[vis][solint]['solmode'] = selfcal_plan['solmode'][iteration]+''
                            # Update RMS value if necessary
                            if slib[vis][solint]['RMS_post'] < slib['RMS_curr']:
                                slib['RMS_curr'] = slib[vis][solint]['RMS_post'].copy()
                            if slib[vis][solint]['RMS_NF_post'] < slib['RMS_NF_curr'] and \
                                    slib[vis][solint]['RMS_NF_post'] > 0:
                                slib['RMS_NF_curr'] = slib[vis][solint]['RMS_NF_post'].copy(
                                )

                    marginal_inf_EB_will_attempt_next_solint = False
                    # run a pre-check as to whether a marginal inf_EB result will go on to attempt inf, if not we will fail a marginal inf_EB
                    if (solint == 'inf_EB') and ((((post_SNR-SNR)/SNR > -0.02) and ((post_SNR-SNR)/SNR < 0.00)) or (((post_SNR_NF - SNR_NF)/SNR_NF > -0.02) and ((post_SNR_NF - SNR_NF)/SNR_NF < 0.00))) and (delta_beamarea < delta_beam_thresh):
                        if selfcal_plan['solint_snr'][selfcal_plan['solints'][iteration+1]] < minsnr_to_proceed and np.all([selfcal_plan['solint_snr_per_field'][fid][selfcal_plan['solints'][iteration+1]] < minsnr_to_proceed for fid in slib['sub-fields']]):
                            marginal_inf_EB_will_attempt_next_solint = False
                        else:
                            marginal_inf_EB_will_attempt_next_solint = True

                    RMS_change_acceptable = (post_RMS/RMS < 1.05 and post_RMS_NF/RMS_NF < 1.05) or \
                        ((post_RMS/RMS > 1.05 or post_RMS_NF/RMS_NF > 1.05) and selfcal_plan['solint_snr'][solint] > 5)

                    if (((post_SNR >= SNR) and (post_SNR_NF >= SNR_NF) and (delta_beamarea < delta_beam_thresh)) or ((solint == 'inf_EB') and marginal_inf_EB_will_attempt_next_solint and ((post_SNR-SNR)/SNR > -0.02) and ((post_SNR_NF - SNR_NF)/SNR_NF > -0.02) and (delta_beamarea < delta_beam_thresh))) and np.any(field_by_field_success) and RMS_change_acceptable:
                        slib['SC_success'] = True
                        slib['Stop_Reason'] = 'None'
                        # keep track of whether inf_EB had a S/N decrease
                        if (solint == 'inf_EB') and (((post_SNR-SNR)/SNR < 0.0) or ((post_SNR_NF - SNR_NF)/SNR_NF < 0.0)):
                            slib['inf_EB_SNR_decrease'] = True
                        elif (solint == 'inf_EB') and (((post_SNR-SNR)/SNR > 0.0) and ((post_SNR_NF - SNR_NF)/SNR_NF > 0.0)):
                            slib['inf_EB_SNR_decrease'] = False
                        for vis in vislist:
                            slib[vis]['gaintable_final'] = slib[vis][solint]['gaintable']
                            slib[vis]['spwmap_final'] = slib[vis][solint]['spwmap'].copy()
                            slib[vis]['applycal_mode_final'] = slib[vis][solint]['applycal_mode']
                            slib[vis]['applycal_interpolate_final'] = slib[vis][solint]['applycal_interpolate']
                            slib[vis]['gaincal_combine_final'] = slib[vis][solint]['gaincal_combine']
                            slib[vis][solint]['Pass'] = True
                            slib[vis][solint]['Fail_Reason'] = 'None'
                        if selfcal_plan['solmode'][iteration] == 'p':
                            slib['final_phase_solint'] = solint
                        slib['final_solint'] = solint
                        slib['final_solint_mode'] = selfcal_plan['solmode'][iteration]
                        slib['iteration'] = iteration

                        for ind, fid in enumerate(slib['sub-fields-to-selfcal']):
                            if field_by_field_success[ind]:
                                slib[fid]['SC_success'] = True
                                slib[fid]['Stop_Reason'] = 'None'
                                if (solint == 'inf_EB') and not strict_field_by_field_success[ind]:
                                    slib[fid]['inf_EB_SNR_decrease'] = True
                                elif (solint == 'inf_EB') and strict_field_by_field_success[ind]:
                                    slib[fid]['inf_EB_SNR_decrease'] = False

                                for vis in slib[fid]['vislist']:
                                    slib[fid][vis]['gaintable_final'] = slib[fid][vis][solint]['gaintable']
                                    slib[fid][vis]['spwmap_final'] = slib[fid][vis][solint]['spwmap'].copy(
                                    )
                                    slib[fid][vis]['applycal_mode_final'] = slib[fid][vis][solint]['applycal_mode']
                                    slib[fid][vis]['applycal_interpolate_final'] = slib[fid][vis][solint]['applycal_interpolate']
                                    slib[fid][vis]['gaincal_combine_final'] = slib[fid][vis][solint]['gaincal_combine']
                                    slib[fid][vis][solint]['Pass'] = True
                                    slib[fid][vis][solint]['Fail_Reason'] = 'None'
                                if selfcal_plan['solmode'][iteration] == 'p':
                                    slib[fid]['final_phase_solint'] = solint
                                slib[fid]['final_solint'] = solint
                                slib[fid]['final_solint_mode'] = selfcal_plan['solmode'][iteration]
                                slib[fid]['iteration'] = iteration
                            else:
                                for vis in slib[fid]['vislist']:
                                    slib[fid][vis][solint]['Pass'] = False
                                if solint == 'inf_EB':
                                    slib[fid]['inf_EB_SNR_decrease'] = False

                        # To exit out of the applymode loop.
                        break
                    ##
                    # If the beam area got larger, this could be because of flagging of long baseline antennas. Try with applymode = "calonly".
                    ##

                    elif delta_beamarea > delta_beam_thresh and applymode == "calflag":
                        LOG.info('****************************Selfcal failed**************************')
                        LOG.info('REASON: Beam change beyond '+str(delta_beam_thresh))
                        if iteration > 0:  # reapply only the previous gain tables, to get rid of solutions from this selfcal round
                            LOG.info('****************Reapplying previous solint solutions*************')
                            for vis in vislist:
                                self.applycal_wrapper(vis, target, band, solint, slib, 
                                                 final=lambda f: selfcal_library[f]['SC_success'],
                                                 restore_flags='selfcal_starting_flags_'+sani_target+'_'+band)
                        else:
                            for vis in vislist:
                                selfcal_plan['inf_EB_gaincal_combine'][vis] = inf_EB_gaincal_combine  # 'scan'
                                if slib['obstype'] == 'mosaic':
                                    selfcal_plan['inf_EB_gaincal_combine'][vis] += ',field'
                                selfcal_plan['inf_EB_gaintype'][vis] = inf_EB_gaintype  # G
                                selfcal_plan['inf_EB_fallback_mode'][vis] = ''  # 'scan'
                        LOG.info('****************Attempting applymode="calonly" fallback*************')
                    else:
                        for vis in vislist:
                            slib[vis][solint]['Pass'] = False

                        for fid in slib['sub-fields-to-selfcal']:
                            for vis in slib[fid]['vislist']:
                                slib[fid][vis][solint]['Pass'] = False
                        break

                ##
                # if S/N worsens, and/or beam area increases reject current solutions and reapply previous (or revert to origional data)
                ##

                if not slib[vislist[0]][solint]['Pass'] or (solint == 'inf_EB' and slib['inf_EB_SNR_decrease']):
                    reason = ''
                    if (post_SNR <= SNR):
                        reason = reason+' S/N decrease'
                    if (post_SNR_NF < SNR_NF):
                        if reason != '':
                            reason += '; '
                        reason = reason + ' NF S/N decrease'
                    if (delta_beamarea > delta_beam_thresh):
                        if reason != '':
                            reason = reason+'; '
                        reason = reason+'Beam change beyond '+str(delta_beam_thresh)
                    if (post_RMS/RMS > 1.05 and selfcal_plan['solint_snr'][solint] <= 5):
                        if reason != '':
                            reason = reason+'; '
                        reason = reason+'RMS increase beyond 5%'
                    if (post_RMS_NF/RMS_NF > 1.05 and selfcal_plan['solint_snr'][solint] <= 5):
                        if reason != '':
                            reason = reason+'; '
                        reason = reason+'NF RMS increase beyond 5%'
                    if not np.any(field_by_field_success):
                        if reason != '':
                            reason = reason+'; '
                        reason = reason+'All sub-fields failed'
                    slib['Stop_Reason'] = reason
                    for vis in vislist:
                        # slib[vis][solint]['Pass']=False
                        slib[vis][solint]['Fail_Reason'] = reason

                mosaic_reason = {}
                new_fields_to_selfcal = []
                for fid in slib['sub-fields-to-selfcal']:
                    if not slib[fid][slib[fid]['vislist'][0]][solint]['Pass'] or \
                            (solint == "inf_EB" and slib[fid]['inf_EB_SNR_decrease']):
                        mosaic_reason[fid] = ''
                        if (post_mosaic_SNR[fid] <= mosaic_SNR[fid]):
                            mosaic_reason[fid] = mosaic_reason[fid]+' SNR decrease'
                        if (post_mosaic_SNR_NF[fid] < mosaic_SNR_NF[fid]):
                            if mosaic_reason[fid] != '':
                                mosaic_reason[fid] += '; '
                            mosaic_reason[fid] = mosaic_reason[fid] + ' NF SNR decrease'
                        if (delta_beamarea > delta_beam_thresh):
                            if mosaic_reason[fid] != '':
                                mosaic_reason[fid] = mosaic_reason[fid]+'; '
                            mosaic_reason[fid] = mosaic_reason[fid]+'Beam change beyond '+str(delta_beam_thresh)
                        if (post_RMS/RMS > 1.05 and selfcal_plan['solint_snr'][solint] <= 5):
                            if mosaic_reason[fid] != '':
                                mosaic_reason[fid] = mosaic_reason[fid]+'; '
                            mosaic_reason[fid] = mosaic_reason[fid]+'RMS increase beyond 5%'
                        if (post_RMS_NF/RMS_NF > 1.05 and selfcal_plan['solint_snr'][solint] <= 5):
                            if mosaic_reason[fid] != '':
                                mosaic_reason[fid] = mosaic_reason[fid]+'; '
                            mosaic_reason[fid] = mosaic_reason[fid]+'NF RMS increase beyond 5%'
                        if mosaic_reason[fid] == '':
                            mosaic_reason[fid] = "Global selfcal failed"
                        slib[fid]['Stop_Reason'] = mosaic_reason[fid]
                        for vis in slib[fid]['vislist']:
                            # slib[fid][vis][solint]['Pass']=False
                            slib[fid][vis][solint]['Fail_Reason'] = mosaic_reason[fid]

                    if slib[fid][slib[fid]['vislist'][0]][solint]['Pass']:
                        new_fields_to_selfcal.append(fid)

                # If any of the fields failed self-calibration, we need to re-apply calibrations for all fields because we need to revert flagging back
                # to the starting point.
                if np.any([slib[fid][slib[fid]['vislist'][0]][solint]['Pass'] == False for fid in
                           slib['sub-fields-to-selfcal']]) or len(slib['sub-fields-to-selfcal']) < \
                        len(slib['sub-fields']):
                    LOG.info('****************Selfcal failed for some sub-fields:*************')
                    for fid in slib['sub-fields']:
                        if fid in slib['sub-fields-to-selfcal']:
                            if slib[fid][slib[fid]['vislist'][0]][solint]['Pass'] == False:
                                LOG.info('FIELD: '+str(fid)+', REASON: '+mosaic_reason[fid])
                        else:
                            LOG.info('FIELD: '+str(fid)+', REASON: Failed earlier solint')
                    LOG.info('****************Reapplying previous solint solutions where available*************')

                    # PIPE-2534: reset inf_EB outcome after an unsuccessful follow-up solint trial.
                    # Because a mosaic can have sub-fields fail outright when the mosaic as a whole and/or sub-fields fail with inf_EB_SNR_decrease
                    # we need to make sure this part is only entered if we are not in the inf_EB solint, so the inf_EB_SNR_decrease flag doesn't cause
                    # all of those fields to fail before the next solint can be tried.
                    if solint != 'inf_EB':
                        # if the final successful solint was inf_EB but inf_EB had a S/N decrease, don't count it as a success and revert to no selfcal
                        if slib['final_solint'] == 'inf_EB' and slib['inf_EB_SNR_decrease']:
                            slib['SC_success'] = False
                            slib['final_solint'] = 'None'
                            for vis in vislist:
                                # remove the success from inf_EB
                                # TODO: to be evaluted after the release of PL2025.
                                # if slib[vis]['inf_EB'].get('Pass') is True:
                                #     slib[vis]['inf_EB']['Pass'] = False
                                slib[vis]['inf_EB']['Pass'] = False
                                slib[vis]['inf_EB']['Fail_Reason'] += ' with no successful solints later'

                        # Only set the inf_EB Pass flag to False if the mosaic as a whole failed or if this is the last phase-only solint (either because it is int or
                        # because the solint failed, because for mosaics we can keep trying the field as we clean deeper. If we set to False now, that wont happen.
                        for fid in np.intersect1d(slib['sub-fields'], list(slib['sub-fields-fid_map'][vis].keys())):
                            if (slib['final_solint'] == 'inf_EB' and slib['inf_EB_SNR_decrease']) or (
                                (not slib[vislist[0]][solint]['Pass'] or solint == 'int')
                                and (slib[fid]['final_solint'] == 'inf_EB' and slib[fid]['inf_EB_SNR_decrease'])
                            ):
                                slib[fid]['SC_success'] = False
                                slib[fid]['final_solint'] = 'None'
                                for vis in slib[fid]['vislist']:
                                    # remove the success from inf_EB
                                    # TODO: to be evaluted after the release of PL2025.
                                    # if slib[fid][vis]['inf_EB']['Pass'] is 'None':
                                    #     slib[fid][vis]['inf_EB']['Pass'] = False
                                    slib[fid][vis]['inf_EB']['Pass'] = False
                                    slib[fid][vis]['inf_EB']['Fail_Reason'] += ' with no successful solints later'

                    for vis in vislist:
                        self.applycal_wrapper(vis, target, band, solint, slib, 
                                         final=lambda f: selfcal_library[f]['SC_success'],
                                         clear=lambda f: not selfcal_library[f]['SC_success'], 
                                         restore_flags='selfcal_starting_flags_'+sani_target+'_'+band)
                                         
                        for fid in np.intersect1d(slib['sub-fields'], list(slib['sub-fields-fid_map'][vis].keys())):
                            if not slib[fid]['SC_success']:
                                slib['SNR_post'] = slib['SNR_orig'].copy()
                                slib['RMS_post'] = slib['RMS_orig'].copy()

                                for fid in slib['sub-fields']:
                                    slib[fid]['SNR_post'] = slib[fid]['SNR_orig'].copy()
                                    slib[fid]['RMS_post'] = slib[fid]['RMS_orig'].copy()

                # If any of the sub-fields passed, and the whole mosaic passed, then we can move on to the next solint, otherwise we have to back out.
                if slib[vislist[0]][solint]['Pass'] == True and \
                        np.any([slib[fid][slib[fid]['vislist'][0]][solint]['Pass'] == True for fid in
                                slib['sub-fields-to-selfcal']]):
                    if (iteration < len(selfcal_plan['solints'])-1) and (slib[vis][solint]['SNR_post'] >
                                                                       slib['SNR_orig']):  # (iteration == 0) and
                        LOG.info('Updating solint = '+selfcal_plan['solints'][iteration+1]+' SNR')
                        LOG.info('Was: %s', selfcal_plan['solint_snr'][selfcal_plan['solints'][iteration+1]])
                        get_SNR_self_update([target], band, vislist, slib, n_ants,
                                            solint, selfcal_plan['solints'][iteration+1], selfcal_plan['integration_time'], selfcal_plan['solint_snr'])
                        LOG.info('Now: %s', selfcal_plan['solint_snr'][selfcal_plan['solints'][iteration+1]])

                        for fid in slib['sub-fields-to-selfcal']:
                            LOG.info('Field '+str(fid)+' Was: %s',
                                     selfcal_plan[fid]['solint_snr_per_field'][selfcal_plan['solints'][iteration+1]])
                            get_SNR_self_update([target], band, vislist, slib[fid], n_ants, solint,
                                                selfcal_plan['solints'][iteration+1], selfcal_plan['integration_time'], selfcal_plan[fid]['solint_snr_per_field'])
                            LOG.info('Field '+str(fid)+' Now: %s',
                                     selfcal_plan[fid]['solint_snr_per_field'][selfcal_plan['solints'][iteration+1]])
                    # If not all fields succeed for inf_EB or scan_inf/inf, depending on mosaic or single field, then don't go on to amplitude selfcal,
                    # even if *some* fields succeeded.
                    if iteration <= 1 and ((not np.all([slib[fid][slib[fid]['vislist'][0]][solint]['Pass'] == True for fid in
                                                        slib['sub-fields-to-selfcal']])) or len(slib['sub-fields-to-selfcal']) <
                                           len(slib['sub-fields'])) and do_amp_selfcal:
                        LOG.info(
                            "***** NOTE: Amplitude self-calibration turned off because not all fields succeeded at non-inf_EB phase self-calibration")
                        do_amp_selfcal = False

                    if iteration < (len(selfcal_plan['solints'])-1):
                        LOG.info('****************Selfcal passed, shortening solint*************')
                    else:
                        LOG.info('****************Selfcal passed for Minimum solint*************')
                else:
                    LOG.info('****************Selfcal failed*************')
                    LOG.info('REASON: '+reason)
                    # if a solution interval shorter than inf for phase-only SC has passed, attempt amplitude selfcal
                    if iteration > 1 and selfcal_plan['solmode'][iteration] != 'ap' and do_amp_selfcal:
                        iterjump = selfcal_plan['solmode'].index('ap')
                        slib['sub-fields-to-selfcal'] = slib['sub-fields']
                        LOG.info('****************Selfcal halted for phase, attempting amplitude*************')
                        continue
                    else:
                        LOG.info('****************Aborting further self-calibration attempts for ' +
                                 target+' '+band+'**************')
                        break  # breakout of loops of successive solints since solutions are getting worse

                # Finally, update the list of fields to be self-calibrated now that we don't need to know the list at the beginning of this solint.
                new_fields_to_selfcal = []
                for fid in slib['sub-fields']:
                    if slib[fid][slib[fid]['vislist'][0]]["inf_EB"]["Pass"]:
                        new_fields_to_selfcal.append(fid)

                slib['sub-fields-to-selfcal'] = new_fields_to_selfcal
