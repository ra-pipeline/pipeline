from __future__ import annotations

import collections
import os
import shutil
from typing import TYPE_CHECKING

import numpy as np

import pipeline.domain.measures as measures
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.callibrary as callibrary
import pipeline.infrastructure.utils as utils
import pipeline.infrastructure.vdp as vdp
from pipeline.h.heuristics import caltable as caltable_heuristic
from pipeline.h.tasks.common import commonhelpermethods
from pipeline.hif.tasks import gaincal
from pipeline.hifa.heuristics import atm as atm_heuristic
from pipeline.hifa.heuristics import wvrgcal as wvrgcal_heuristic
from pipeline.hifa.tasks import bandpass
from pipeline.infrastructure import casa_tasks, task_registry
from . import resultobjects
from . import wvrg_qa

if TYPE_CHECKING:
    from collections.abc import Callable

    from pipeline.hif.tasks.bandpass.common import BandpassResults
    from pipeline.hif.tasks.gaincal.common import GaincalResults

__all__ = [
    'Wvrgcal',
    'WvrgcalInputs'
]

LOG = infrastructure.logging.get_logger(__name__)

WVRInfo = collections.namedtuple('WVRInfo',
                                 'antenna wvr flag rms disc')


class WvrgcalInputs(vdp.StandardInputs):
    """
    WvrgcalInputs defines the inputs for the Wvrgcal pipeline task.
    """
    accept_threshold = vdp.VisDependentProperty(default=1.0)
    bandpass_result = vdp.VisDependentProperty(default='', hidden=True)
    disperse = vdp.VisDependentProperty(default=False)
    hm_smooth = vdp.VisDependentProperty(default='automatic')
    hm_tie = vdp.VisDependentProperty(default='automatic')
    hm_toffset = vdp.VisDependentProperty(default='automatic')

    @vdp.VisDependentProperty(null_input=[None, '', -1, -1.0])
    def maxdistm(self):
        # Identify fraction of antennas that are 7m.
        nants_7m = len([ant
                        for ant in self.ms.antennas
                        if ant.diameter == 7.0])
        frac = float(nants_7m) / len(self.ms.antennas)

        # If more than 50% of the antennas are 7m, then set maxdistm to a
        # lower value.
        if frac > 0.5:
            return 100.0
        else:
            return 500.0

    minnumants = vdp.VisDependentProperty(default=2)
    mingoodfrac = vdp.VisDependentProperty(default=0.8)
    nowvr_result = vdp.VisDependentProperty(default='', hidden=True)
    nsol = vdp.VisDependentProperty(default=1)
    # Default for offsetstable is blank, which means the wvrgcal task will not
    # apply any offsets.
    offsetstable = vdp.VisDependentProperty(default='')
    refant = vdp.VisDependentProperty(default='')
    # Default for qa_bandpass_intent is blank, which allows the bandpass task
    # to select a sensible default if the dataset lacks data with BANDPASS
    # intent.
    qa_bandpass_intent = vdp.VisDependentProperty(default='')
    qa_intent = vdp.VisDependentProperty(default='')
    qa_spw = vdp.VisDependentProperty(default='', hidden=True)
    qa_combine = vdp.VisDependentProperty(default='', hidden=True)
    qa_solint = vdp.VisDependentProperty(default='int', hidden=True)
    scale = vdp.VisDependentProperty(default=1.0)
    segsource = vdp.VisDependentProperty(default=True)
    smooth = vdp.VisDependentProperty(default='')

    @vdp.VisDependentProperty
    def sourceflag(self):
        return []

    @vdp.VisDependentProperty
    def tie(self):
        return []

    toffset = vdp.VisDependentProperty(default=0)

    @vdp.VisDependentProperty
    def wvrflag(self):
        return []

    @wvrflag.convert
    def wvrflag(self, value):
        if isinstance(value, str):
            if value.startswith('['):
                # Remove the characters [, ], and ' from the value.
                value = value.translate(str.maketrans("[]'"))
            return value.split(',')
        else:
            return value

    # docstring and type hints: supplements hifa_wvrgcal
    def __init__(self, context, output_dir=None, vis=None, caltable=None, offsetstable=None, hm_toffset=None,
                 toffset=None, segsource=None, hm_tie=None, tie=None, sourceflag=None, nsol=None, disperse=None,
                 wvrflag=None, hm_smooth=None, smooth=None, scale=None, maxdistm=None, minnumants=None,
                 mingoodfrac=None, refant=None, qa_intent=None, qa_bandpass_intent=None, qa_spw=None, qa_combine=None,
                 qa_solint=None, accept_threshold=None, bandpass_result=None, nowvr_result=None):
        """Initialize Inputs.

        Args:
            context: Pipeline context object containing state information.

            output_dir: Output directory.
                Defaults to ``None``, which corresponds to the current working directory.

            vis: List of input visibility files.
                Default: ``None``, in which case the vis files to be used
                will be read from the context.

                Example: ``vis=['ngc5921.ms']``

            caltable: List of output gain calibration tables.
                Default: none, in which case the names of the caltables
                will be generated automatically.

                Example: ``caltable='ngc5921.wvr'``

            offsetstable: List of input temperature offsets table files to subtract
                from WVR measurements before calculating phase corrections.
                Default: none, in which case no offsets are applied.

                Example: ``offsetstable=['ngc5921.cloud_offsets']``

            hm_toffset: If 'manual', set the ``toffset`` parameter to the user-specified value.
                If 'automatic', set the ``toffset`` parameter according to the
                date of the MeasurementSet; ``toffset=-1`` if before 2013-01-21T00:00:00
                ``toffset=0`` otherwise.

            toffset: Time offset (sec) between interferometric and WVR data.

            segsource: If True calculate new atmospheric phase correction coefficients
                for each source, subject to the constraints of the ``tie`` parameter.
                'segsource' is forced to be True if the ``tie`` parameter is set to a
                non-empty value by the user or by the automatic heuristic.

            hm_tie: If 'manual', set the ``tie`` parameter to the
                user-specified value. If 'automatic', set the ``tie``
                parameter to include with the target all calibrators
                that are within 15 degrees of it: if no calibrators are
                that close then ``tie`` is left empty.

            tie: Use the same atmospheric phase correction coefficients
                when calculating the WVR correction for all sources in
                the ``tie``. If ``tie`` is not empty then ``segsource``
                is forced to be True. Ignored unless ``hm_tie`` = 'manual'.

                Example: ``tie=['3C273,NGC253', 'IC433,3C279']``

            sourceflag: Flag the WVR data for these source(s) as bad and do not
                produce corrections for it. Requires ``segsource`` = True.

                Example: ``['3C273']``

            nsol: Number of solutions for phase correction coefficients during this
                observation, evenly distributed in time throughout the observation. It
                is used only if ``segsource`` = False because if ``segsource`` = True then the
                coefficients are recomputed whenever the telescope moves to a new
                source (within the limits imposed by ``tie``).

            disperse: Apply correction for dispersion. (Deprecated; will be removed)

            wvrflag: Flag the WVR data for the listed antennas as bad and replace
                their data with values interpolated from the 3 nearest antennas with
                unflagged data.

                Example: ``['DV03','DA05','PM02']``

            hm_smooth: If 'manual' set the ``smooth`` parameter to the user-specified value.
                If 'automatic', run the wvrgcal task with the range of ``smooth`` parameters
                required to match the integration time of the wvr data to that of the
                interferometric data in each spectral window.

            smooth: Smooth WVR data on this timescale before calculating the correction.
                Ignored unless hm_smooth='manual'.

            scale: Scale the entire phase correction by this factor.

            maxdistm: Maximum distance in meters of an antenna used for interpolation
                from a flagged antenna.
                Default: -1  (automatically set to 100m if >50% of
                antennas are 7m antennas without WVR and otherwise set to
                500m).

                Example: ``maxdistm=550``

            minnumants: Minimum number of nearby antennas (up to 3) used for
                interpolation from a flagged antenna.

                Example: ``minnumants=3``

            mingoodfrac: Minimum fraction of good data per antenna.

            refant: Ranked comma delimited list of reference antennas.

                Example: ``refant='DV01,DV02'``

            qa_intent: The list of data intents on which the wvr correction is to be
                tried as a means of estimating its effectiveness.
                A QA 'view' will be calculated for each specified intent, in each spectral
                window in each vis file.
                Each QA 'view' will consist of a pair of 2-d images with dimensions
                ['ANTENNA', 'TIME'], one showing the data phase-noise before the
                wvr application, the second showing the phase noise after (both 'before'
                and 'after' images have a bandpass calibration applied as well).
                An overall QA score is calculated for each vis file, by dividing the
                'before' images by the 'after' and taking the median of the result. An
                overall score of 1 would correspond to no change in the phase noise,
                a score > 1 implies an improvement.
                If the overall score for a vis file is less than the value in
                'accept_threshold' then the wvr calibration file is not made available
                for merging into the context for use in the subsequent reduction.
                If you do not want any QA calculations then set qa_intent=''.

                Example: ``qa_intent='PHASE'``

            qa_bandpass_intent: The data intent to use for the bandpass calibration in
                the qa calculation. The default is blank to allow the underlying bandpass
                task to select a sensible intent if the dataset lacks BANDPASS data.

            qa_spw: The SpW(s) to use for the qa calculation, in the order that they
                should be tried. Input as a comma-separated list. The default is blank, in
                which case the task will try SpWs in order of decreasing median sky
                opacity.

            qa_combine: Used to set whether the spws can be combined.
                The trigger to combine SpW in the phase based gaincal when lowSNR
                data are present. This parameter is reported back from the pre-bandpass 
                phaseup lowSNR assessment. Default is no combine, i.e. = '' 

            qa_solint:  The solution interval in the phase based gaincal when lowSNR
                data are present. This parameter is reported back from the pre-bandpass 
                phaseup lowSNR assessment. Default is 'int'

            accept_threshold: The phase-rms improvement ratio
                (rms without wvr / rms with wvr) above which the wrvg file will be
                accepted into the context for subsequent application.

            bandpass_result:

            nowvr_result:

        """
        super().__init__()

        # pipeline inputs
        self.context = context
        # vis must be set first, as other properties may depend on it
        self.vis = vis
        self.output_dir = output_dir

        # data selection arguments
        self.caltable = caltable
        self.offsetstable = offsetstable

        # solution parameters
        self.hm_toffset = hm_toffset
        self.toffset = toffset
        self.segsource = segsource
        self.hm_tie = hm_tie
        self.tie = tie
        self.sourceflag = sourceflag
        self.nsol = nsol
        self.disperse = disperse
        self.wvrflag = wvrflag
        self.hm_smooth = hm_smooth
        self.smooth = smooth
        self.scale = scale
        self.maxdistm = maxdistm
        self.minnumants = minnumants
        self.mingoodfrac = mingoodfrac
        self.refant = refant
        self.qa_intent = qa_intent
        self.qa_bandpass_intent = qa_bandpass_intent
        self.qa_spw = qa_spw
        self.qa_combine = qa_combine
        self.qa_solint = qa_solint
        self.accept_threshold = accept_threshold
        self.bandpass_result = bandpass_result
        self.nowvr_result = nowvr_result           

@task_registry.set_equivalent_casa_task('hifa_wvrgcal')
class Wvrgcal(basetask.StandardTaskTemplate):
    Inputs = WvrgcalInputs

    def __init__(self, inputs):
        super().__init__(inputs)

    def prepare(self):
        inputs = self.inputs
        result = resultobjects.WvrgcalResult(vis=inputs.vis)
        jobs = []
       
        # get parameters that can be set from outside or which will be derived
        # from heuristics otherwise
        wvrheuristics = wvrgcal_heuristic.WvrgcalHeuristics(
            context=inputs.context, vis=inputs.vis, hm_tie=inputs.hm_tie,
            tie=inputs.tie, hm_smooth=inputs.hm_smooth, smooth=inputs.smooth,
            sourceflag=inputs.sourceflag, nsol=inputs.nsol,
            segsource=inputs.segsource)

        # return an empty results object if no WVR data available
        if not wvrheuristics.wvr_available():
            # only 12m antennas are expected to have WVRs fitted
            if any([a for a in inputs.ms.antennas if a.diameter == 12.0]):
                LOG.error('WVR data expected but not found in %s'
                          '' % os.path.basename(inputs.vis))
            return result
        elif len([a for a in inputs.ms.antennas if a.diameter == 12.0]) <= 1:
            # WVR data available for only 1 antenna
            LOG.error('WVR data available for only 1 antenna in %s'
                      '' % os.path.basename(inputs.vis))
            return result

        if inputs.hm_toffset == 'automatic':
            toffset = wvrheuristics.toffset()
        else:
            toffset = inputs.toffset

        if inputs.segsource is None:
            segsource = wvrheuristics.segsource()
        else:
            segsource = inputs.segsource

        if inputs.hm_tie == 'automatic':
            tie = wvrheuristics.tie()
        else:
            tie = inputs.tie
        # add tie to results object for display in the weblog. Tie is not spw
        # dependent, so we can add it early.
        result.tie = tie

        if inputs.sourceflag is None:
            sourceflag = wvrheuristics.sourceflag()
        else:
            sourceflag = inputs.sourceflag

        if inputs.nsol is None:
            nsol = wvrheuristics.nsol()
        else:
            nsol = inputs.nsol

        # get parameters that must be set from outside
        disperse = inputs.disperse
        wvrflag = inputs.wvrflag
        scale = inputs.scale
        maxdistm = inputs.maxdistm
        minnumants = inputs.minnumants
        mingoodfrac = inputs.mingoodfrac

        ms = inputs.context.observing_run.get_ms(name=inputs.vis)

        # Set the reference antenna
        refant = inputs.refant
        if refant == '':
            refant = ms.reference_antenna
            if not (refant and refant.strip()):
                msg = ('No reference antenna specified and none found in '
                       'context for %s' % ms.basename)
                LOG.error(msg)
                refant = []
            else:
                refant = refant.split(',')

        # smooth may vary with spectral window so need to ensure we calculate
        # results that can cover them all
        science_spws = ms.get_spectral_windows(science_windows_only=True)
        science_spwids = [spw.id for spw in science_spws]
        wvr_spwids = sorted([spw.id for spw in ms.spectral_windows if
                             spw.num_channels == 4 and 'WVR' in spw.intents])

        smooths_done = set()
        callist = []
        caltables = []
        for spw in science_spwids:
            if inputs.hm_smooth == 'automatic':
                # smooth = wvrheuristics.smooth(spw)
                # Force the smooth heuristics to a single value
                # (If integration times vary between spws this may not be
                # the right thing to do). Integration times varying between
                # intents within an spw then it is right to smooth according
                # to the longest.
                smooth = wvrheuristics.smoothall(science_spwids)
            else:
                smooth = inputs.smooth

            # prepare to run the wvrgcal task if necessary
            caltable = caltable_heuristic.WvrgCaltable()
            caltable = caltable(output_dir=inputs.output_dir,
                                stage=inputs.context.stage,
                                vis=inputs.vis, smooth=smooth)
            if smooth not in smooths_done:
                # different caltable for each smoothing, remove old versions
                shutil.rmtree(caltable, ignore_errors=True)

                task = casa_tasks.wvrgcal(vis=inputs.vis, caltable=caltable,
                                          offsetstable=inputs.offsetstable,
                                          toffset=toffset, segsource=segsource,
                                          tie=tie, sourceflag=sourceflag,
                                          nsol=nsol, disperse=disperse,
                                          wvrflag=wvrflag, smooth=smooth,
                                          scale=scale, maxdistm=maxdistm,
                                          minnumants=minnumants,
                                          mingoodfrac=mingoodfrac,
                                          spw=science_spwids,
                                          wvrspw=[wvr_spwids[0]],
                                          refant=refant)
                jobs.append(task)

                smooths_done.add(smooth)

            # add this wvrg table to the callibrary for this spw
            calto = callibrary.CalTo(vis=inputs.vis, spw=spw)
            calfrom = callibrary.CalFrom(caltable, caltype='wvr', spwmap=[],
                                         interp='nearest', calwt=False)
            calapp = callibrary.CalApplication(calto, calfrom)
            callist.append(calapp)
            caltables.append(caltable)

        # execute the jobs
        for job in jobs:
            job_result = self._executor.execute(job)

            if job_result['success']:
                # extract flags found by CASA job
                job_name = np.array(job_result['Name'])
                job_flag = np.array(job_result['Flag'])
                job_wvrflag = set(job_name[job_flag])
            else:
                LOG.warning('CASA wvrgcal job terminated unexpectedly with '
                            'exit code %s; no flags generated.' % (job_result['rval']))
                job_wvrflag = set([])

            input_wvrflag = set(wvrflag)
            generated_wvrflag = job_wvrflag.difference(input_wvrflag)
            if generated_wvrflag:
                LOG.warning('%s wvrgcal has flagged antennas: %s' % (
                    os.path.basename(inputs.vis), list(generated_wvrflag)))

            wvrflag_set = set(result.wvrflag)
            wvrflag_set.update(job_wvrflag)
            result.wvrflag = list(wvrflag_set)

            result.wvr_infos = self._get_wvrinfos(job_result)

        LOG.info('wvrgcal complete')

        # removed any 'unsmoothed' wvrcal tables generated by the wvrgcal jobs
        for caltable in caltables:
            shutil.rmtree('%s_unsmoothed' % caltable, ignore_errors=True)

        result.pool[:] = callist

        return result

    def analyse(self, result):
        inputs = self.inputs

        # check that the caltable was actually generated
        on_disk = [ca for ca in result.pool if ca.exists()]
        missing = [ca for ca in result.pool if ca not in on_disk]
        result.error.clear()
        result.error.update(missing)

        # wvrcal files to be applied
        result.final[:] = on_disk

        # If no QA intent was provided, then return early. Otherwise, continue
        # with computing the QA results.
        qa_intent = inputs.qa_intent.strip()
        if not qa_intent:
            return result

        # Return early if no WVR caltable was created.
        if not result.final:
            return result

        # Determine the list of SpWs for which QA results are needed. If no QA
        # SpW order was specified explicitly, then calculate an order here based
        # on SpW bandwidth and Tsys; otherwise use the specified order.
        # PIPE-3006 if in the second loop after any antenna flags reestablish spwlist again
        if inputs.qa_spw == '' or inputs.qa_combine == 'spw':
            # PIPE-2056: if the observing mode is band-to-band, then restrict
            # the list of QA SpWs to only the diffgain on-source SpWs, otherwise
            # use all science SpWs.
            if inputs.ms.is_band_to_band:
                spws = inputs.ms.get_spectral_windows(intent='DIFFGAINSRC')
            else:
                spws = inputs.ms.get_spectral_windows(science_windows_only=True)

            # Initialize atmosphere heuristics.
            atmheuristics = atm_heuristic.AtmHeuristics(context=inputs.context, vis=inputs.vis, spw=spws)

            # Create a ranked list preferably by Tsys and SpW bandwidth.
            qa_spw_list = atmheuristics.spwid_rank_by_tsys_and_bandwidth(qa_intent)

            # If ranking by Tsys failed (e.g. no Tsys table, or due to
            # flagging), then fall back to ranking by opacity and bandwidth:
            if qa_spw_list is None:
                LOG.info(f"qa: ranking spws by bandwidth and Tsys failed for {inputs.ms.basename}; will rank by"
                         f" bandwidth and opacity instead.")
                qa_spw_list = atmheuristics.spwid_rank_by_opacity_and_bandwidth()                
        else:
            qa_spw_list = inputs.qa_spw.split(',')

        # PIPE-3006 get string of all spws required and pass to the bandpass to run lowSNR heuristics       
        # for a spectral scan we want to avoid passing all spws as this will take unnecessary time
        # to solve the bandpass. Thus, loop the spws per spectral spec and use those spws of the spectral spec
        # matching the top ranked qa_spw_list spw.
        spspec_to_spwid = utils.get_spectralspec_to_spwid_map(inputs.ms.get_spectral_windows(','.join(sorted(qa_spw_list))))
        for spwids in spspec_to_spwid.values():
            if int(qa_spw_list[0]) in spwids:
                qa_spw_list = [qa_spw for qa_spw in qa_spw_list if int(qa_spw) in spwids]
        LOG.info(f'filtered spw rank: {qa_spw_list}')
        
        # Do a bandpass calibration
        LOG.info('qa: calculating bandpass calibration')
        bp_result = self._do_qa_bandpass(inputs, ','.join(sorted(qa_spw_list)))
        if not bp_result.final:
            LOG.warning('qa: calculating phase calibration without bandpass applied')
        else:
            LOG.info('qa: calculating phase calibration with bandpass applied')
            # PIPE-3006 establish the combine and solint used for pre-bandpass phaseup
            # combine and solint are passed as hidden inputs the same as qa_spw which was already coded
            inputs.qa_combine, inputs.qa_solint = self._check_for_combine(bp_result)
            
        # if combine was used in pre-bandpass phaseup we can piggy-back
        # that we know any subsequent gaincal will also need combine as not to
        # fail or drop lots of solutions. 
        if inputs.qa_combine == 'spw':
            LOG.info(f'lowSNR data for {inputs.ms.basename}, combining spectral windows to calculate wvrgcal QA')
            inputs.qa_spw = ','.join(sorted(qa_spw_list))
            
            # PIPE-3006 protect against doing phasediff again in a second loop after
            # antenna flags if there is a 'no-wvr' caltable already
            if not inputs.nowvr_result:
                # A phasediff is required to offset all SpW before doing the no wvr gaincal with combine='spw'
                nowvr_phasediff_result = self._do_phasediff_gaincal(inputs, False)
                # Temporarily accept the result into the local context
                nowvr_phasediff_result.accept(inputs.context) 
                nowvr_result = self._do_nowvr_gaincal(inputs)
                # must now remove the gaintable from the local context as the
                # phasediff without wvr is not valid for further solves
            
                def phasediff_matcher(calto: callibrary.CalToArgs, calfrom: callibrary.CalFrom) -> bool:
                    calto_vis = {os.path.basename(v) for v in calto.vis}
                    return 'solintinf.gpcal.nowvr' in calfrom.gaintable and inputs.ms.basename in calto_vis

                LOG.info('Unregistering previous phasediff without wvr calibration while task executes')
                inputs.context.callibrary.unregister_calibrations(phasediff_matcher)

                LOG.info(f'qa: wvrgcal QA calculation was successful')
                LOG.info(f'    will pass solutions in combined SpW {sorted(qa_spw_list)[0]} for with/without WVR assessment')
            else:
                # result of no-wvr gaincal is passed through
                nowvr_result = self._do_nowvr_gaincal(inputs)
                LOG.info(f'qa: wvrgcal QA calculation without WVR is reused')                
                LOG.info(f'    will pass solutions in combined SpW {sorted(qa_spw_list)[0]} for with/without WVR assessment')

                
            # set the single result qa spw as the minimum spw of the qa_spw_list
            result.qa_wvr.qa_spw = sorted(qa_spw_list)[0]


        else:
            # If no combine='spw' loop over the qa_spw_list as ordered
            # in a second loop this qa_spw_list is "the" QA spw
            for qa_spw in qa_spw_list:
                LOG.info(f'qa: {inputs.ms.basename} attempting to calculate wvrgcal QA using spw {qa_spw}')
                inputs.qa_spw = qa_spw
                nowvr_result = self._do_nowvr_gaincal(inputs)
                if not nowvr_result.final:
                    continue
                else:
                    LOG.info('qa: wvrgcal QA calculation was successful')
                    LOG.info(f'   will pass solutions in SpW {qa_spw} for with/without WVR assessment')
                    result.qa_wvr.qa_spw = qa_spw
                    break

        # PIPE-3006 Need to be set as in subsequent loops (after flags) these are cached and reused
        result.qa_wvr.qa_combine = inputs.qa_combine
        result.qa_wvr.qa_solint = inputs.qa_solint
                     
        # note full result saving out of the loop                
        inputs.bandpass_result = bp_result
        inputs.nowvr_result = nowvr_result
        result.qa_wvr.bandpass_result = bp_result
        result.qa_wvr.nowvr_result = nowvr_result
 

        # Accept the result object into the local copy of the context, thus
        # adding the WVR table to the callibrary of this local copy.
        # PIPE-1058: accepting the result requires a stage number. Normally,
        # this would be added by the task execution infrastructure. In this
        # the result of the currently-still-running task is being accepted
        # into a local context already, before the result has been finalised,
        # so need to explicitly set stage number now.
        LOG.debug('qa: accept WVR results into copy of context')
        result.stage_number = inputs.context.task_counter
        result.accept(inputs.context)

        # do a phase calibration on the bandpass and phase calibrators, now
        # with bandpas *and* wvr preapplied.
        if not bp_result.final:
            LOG.warning('qa: calculating phase calibration with wvr applied')
        else:
            LOG.info('qa: calculating phase calibration with bandpass and wvr applied')

        # PIPE-3006 now with the WVR solution we have to process combine or not
        # this should always run even if a second loop after antenna flagging
        if inputs.qa_combine =='spw':
            # A phasediff is required to offset all
            # SpW before doing the no wvr gaincal with combine='spw'
            # result needs to be in local context
            wvr_phasediff_result = self._do_phasediff_gaincal(inputs, True)
            wvr_phasediff_result.accept(inputs.context) 
            wvr_result = self._do_wvr_gaincal(inputs)
            # must now remove the gaintable from the local context as the
            # phasediff is not valid for further solves
            
            def phasediff_matcher(calto: callibrary.CalToArgs, calfrom: callibrary.CalFrom) -> bool:
                calto_vis = {os.path.basename(v) for v in calto.vis}
                return 'solintinf.gpcal.wvr' in calfrom.gaintable and inputs.ms.basename in calto_vis

            LOG.info('Unregistering previous phasediff with wvr calibration while task executes')
            inputs.context.callibrary.unregister_calibrations(phasediff_matcher)
        else:
            wvr_result = self._do_wvr_gaincal(inputs)

        # finally save both with and without WVR result caltables     
        nowvr_caltable = nowvr_result.inputs['caltable']
        wvr_caltable = wvr_result.inputs['caltable']
        result.qa_wvr.gaintable_wvr = wvr_caltable

        # Edited for PIPE-1837 adding BPgood and PHgood
        LOG.info('qa: calculate ratio with-WVR phase RMS / without-WVR phase rms')
        result.PHnoisy, result.BPnoisy, result.PHgood, result.BPgood = wvrg_qa.calculate_view(inputs.context, nowvr_caltable, wvr_caltable,
                                                                  result.qa_wvr, qa_intent)

        result.suggest_remcloud = wvrg_qa.calculate_qa_numbers(result.qa_wvr, result.wvr_infos, result.PHnoisy, result.BPnoisy)

        # PIPE-846: report improvement factors.
        self._report_wvr_improvement(result)

        # if the qa score indicates that applying the wvrg file will
        # make things worse then remove it from the results so that
        # it cannot be accepted into the context.
        if result.qa_wvr.overall_score < inputs.accept_threshold:
            LOG.warning('wvrgcal has qa score (%s) below accept_threshold '
                        '(%s) and will not be applied' %
                        (result.qa_wvr.overall_score, inputs.accept_threshold))
            result.final[:] = []

        return result

    def _report_wvr_improvement(self, result: resultobjects.WvrgcalResult):
        """
        Report the improvement factors from QA data views to the log (PIPE-846).
        """
        # Get translation from antenna IDs to names.
        ms = self.inputs.context.observing_run.get_ms(name=self.inputs.vis)
        ant_names, _ = commonhelpermethods.get_antenna_names(ms)

        # Report improvement values for each view:
        for description in result.qa_wvr.descriptions():
            # Get list of antennas and timestamps from data view.
            qa_result = result.qa_wvr.last(description)
            antids = qa_result.axes[0].data
            timestamps = qa_result.axes[1].data

            # For each antenna, and then each timestamp, report the improvement
            # factor, and whether that entry was flagged.
            LOG.info(f"Phase improvement ratios for {result.vis}, intent {qa_result.intent}, SpW {qa_result.spw}:")
            for xid, antid in enumerate(antids):
                for yid, timestamp in enumerate(timestamps):
                    LOG.info(f"Ant #{antid} ({ant_names[antid]}), time {timestamp}: {qa_result.data[xid, yid]:.2f}"
                             f" {'(flagged)' if qa_result.flag[xid, yid] else ''}")

    def _do_qa_bandpass(self, inputs: WvrgcalInputs, spws: str) -> BandpassResults:
        """
        Create a bandpass caltable for QA analysis, returning the result of
        the worker bandpass task.

        If a suitable bandpass caltable already exists, it will be reused.
        """
        if inputs.bandpass_result:
            # table already exists use it
            LOG.info('Reusing B calibration result:\n%s' %
                     inputs.bandpass_result)
            return self._do_user_qa_bandpass(inputs)
        else:
            LOG.info('Calculating new bandpass for QA analysis')
            result = self._do_new_qa_bandpass(inputs, spws)
            return result

    @staticmethod
    def _do_user_qa_bandpass(inputs: WvrgcalInputs) -> BandpassResults:
        """
        Accept and return the bandpass result affixed to the inputs.

        This code path is used as an optimisation, so identical caltables
        need not be recalculated.
        """
        bp_result = inputs.bandpass_result
        bp_result.accept(inputs.context)
        return bp_result

    def _do_new_qa_bandpass(self, inputs: WvrgcalInputs, spws:str) -> BandpassResults:
        """
        Create a new bandpass caltable by spawning a bandpass worker task,
        merging the results with the context.
        """
        # passing an empty string as intent tells bandpass to use all intents,
        # which resolves to all fields. Convert empty/blank string to None,
        # which will tell bandpass to use the default bandpass intents, as
        # expected.
        if inputs.qa_bandpass_intent and inputs.qa_bandpass_intent.strip():
            # qa_bandpass_intent is not None and is not empty/blank string.
            intent = inputs.qa_bandpass_intent
        else:
            intent = None

        # PIPE-3006 allow lowSNR heuristics for phaseup and bandpass 
        args = {'vis': inputs.vis,
                'mode': 'channel',
                'intent': intent,
                'spw': spws,
                'phaseupsnr': 5.0}

        inputs = bandpass.SerialALMAPhcorBandpass.Inputs(inputs.context, **args)
        task = bandpass.SerialALMAPhcorBandpass(inputs)
        result = self._executor.execute(task, merge=False)
        if not result.final:
            pass
        else:
            result.accept(inputs.context)
        return result

    @staticmethod
    def _check_for_combine(bp_result) -> tuple[str, str]:
        # For PIPE-3006
        # this method loops over the pre-applies of the bandpass result
        # which can include a 'phasediff' and a 'phaseup', as to
        # find whether combine='spw' was an option used in phaseup

        # set defaults to return
        combine = ''
        solint = 'int'
        
        # same code as bandpass/qa.py
        for calapp_list in bp_result.preceding:
            for calapp in calapp_list: # only ever 2 are possible
                # Skip the phase-offset tables (created with solint='inf').
                if utils.get_origin_input_arg(calapp, 'solint') == 'inf':
                    continue

                # Evaluate whether CalApp used spw combination.
                combine = utils.get_origin_input_arg(calapp, 'combine')

                # if combine is set for this caltable check the solution interval too
                # there still could be time > 'int' if very low SNR
                solint = utils.get_origin_input_arg(calapp, 'solint')
                
        return combine, solint
    
    def _do_nowvr_gaincal(self, inputs: WvrgcalInputs) -> GaincalResults:
        # do a phase calibration on the bandpass and phase calibrators

        if inputs.nowvr_result:
            # if table already exists use it
            LOG.info('Reusing WVR-uncorrected gain result for RMS:\n %s' %
                      inputs.nowvr_result)
            return inputs.nowvr_result
        else:
            LOG.debug('Calculating new gaincal with B but no WVR')
            # get namer that will add '.wvr' to caltable filename
            nowvr_caltable_namer = self._get_nowvr_caltable_namer()
            result = self._do_qa_gaincal(inputs, nowvr_caltable_namer)
            return result

    def _do_wvr_gaincal(self, inputs: WvrgcalInputs) -> GaincalResults:
        # get namer that will add '.flags_1_2.wvr' to caltable filename
        wvr_caltable_namer = self._get_wvr_caltable_namer(inputs)
        return self._do_qa_gaincal(inputs, wvr_caltable_namer)

    def _do_qa_gaincal(self, inputs: WvrgcalInputs, caltable_namer: Callable[[str], str]) -> GaincalResults:
        """
        Generate a new gain caltable via a call to a child pipeline task.

        Analysing the improvement gained by applying the WVR requires that
        exactly the same gaincal job is called with and without the WVR
        preapply. Coding the gaincal as a separate function with minimal
        outside interaction helps enforce that requirement.
        """
        # PIPE-3006 has established qa_combine and qa_solint
        # from the pre-bandpass phaseup
        args = {'vis': inputs.vis,
                'intent': inputs.qa_intent,
                'spw': inputs.qa_spw,
                'solint': inputs.qa_solint,
                'combine': inputs.qa_combine,
                'calmode': 'p',
                'minsnr': 2.0} # was 0.0 - not sure this propagates

        inputs = gaincal.GTypeGaincal.Inputs(inputs.context, **args)

        # give calling code a chance to customise the caltable name via the
        # callback passed as an argument
        inputs.caltable = caltable_namer(inputs.caltable)

        task = gaincal.GTypeGaincal(inputs)
        result = self._executor.execute(task, merge=False)

        return result


    def _do_phasediff_gaincal(self, inputs: WvrgcalInputs, withWVR: bool) -> GaincalResults:
        """
        Generate a new gain caltable via a call to a child pipeline task.

        Before performing the phase gaincal for with and without WVR assessment
        some low SNR data my required SpWs to be combined. If so, a 
        phasediff solve is required to align all SpWs in common phase
        """     
        if withWVR:
            caltable_namer = self._get_wvr_caltable_namer(inputs)
        else:
            caltable_namer = self._get_nowvr_caltable_namer()
            
        # PIPE-3006 has established qa_combine and qa_solint
        # from the pre-bandpass phaseup
        args = {'vis': inputs.vis,
                'intent': 'BANDPASS',
                'spw': inputs.qa_spw,
                'solint': 'inf',
                'calmode': 'p',
                'minsnr': 2.0} # was 0.0 

        inputs = gaincal.GTypeGaincal.Inputs(inputs.context, **args)

        LOG.info(f'{inputs.ms.basename}: since phaseup will use spw combination, first computing temporary'
                 f' spw-to-spw phase offsets table to use in pre-apply.')
        # give calling code a chance to customise the caltable name via the
        # callback passed as an argument
        inputs.caltable = caltable_namer(inputs.caltable)

        task = gaincal.GTypeGaincal(inputs)
        result = self._executor.execute(task, merge=False)

        return result
    
    @staticmethod
    def _get_nowvr_caltable_namer() -> Callable[[str], str]:
        """
        Returns a function that inserts a '.nowvr' component into a filename.
        """
        def caltable_namer(caltable: str) -> str:
            root, ext = os.path.splitext(caltable)
            new_caltable_name = '%s.nowvr%s' % (root, ext)
            LOG.debug('WVR uncorrected phase RMS gain table is %s' %
                      new_caltable_name)
            return new_caltable_name

        return caltable_namer

    @staticmethod
    def _get_wvr_caltable_namer(inputs: WvrgcalInputs) -> Callable[[str], str]:
        """
        Returns a function that inserts a ''.flagged_<N>_antennas.wvr' component into a
        filename.
        """
        flags = '.flagged_%d_antennas' % len(inputs.wvrflag) if inputs.wvrflag else ''

        def caltable_namer(caltable: str) -> str:
            root, ext = os.path.splitext(caltable)
            new_caltable = '%s%s.wvr%s' % (root, flags, ext)
            LOG.debug('WVR-corrected phase RMS gain table is %s' %
                      os.path.basename(new_caltable))
            return new_caltable

        return caltable_namer

    @staticmethod
    def _get_wvrinfos(result: dict) -> list[WVRInfo]:
        """
        Retrieve necessary information from the result returned by the CASA
        'wvrgcal' task.

        Args:
            result: result dictionary returned by CASA 'wvrgcal'

        Returns:
            List containing WVR info for each antenna.
        """
        def to_microns(x: float) -> measures.Distance:
            return measures.Distance(x, measures.DistanceUnits.MICROMETRE)

        # copy result in case we need it unaltered elsewhere, then convert raw
        # values to domain measures
        copied = dict(result)
        copied['RMS_um'] = [to_microns(v) for v in copied['RMS_um']]
        copied['Disc_um'] = [to_microns(v) for v in copied['Disc_um']]

        attrs = ['Name', 'WVR', 'Flag', 'RMS_um', 'Disc_um']
        zipped = list(zip(*[copied.get(attr) for attr in attrs]))
        wvr_infos = [WVRInfo(*row) for row in zipped]

        return wvr_infos
