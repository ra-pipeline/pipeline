import os
from typing import List, Optional, Tuple

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.callibrary as callibrary
import pipeline.infrastructure.utils as utils
import pipeline.infrastructure.vdp as vdp
import pipeline.infrastructure.sessionutils as sessionutils
from pipeline.domain.measurementset import MeasurementSet
from pipeline.hif.tasks.gaincal import gtypegaincal
from pipeline.hif.tasks.gaincal.common import GaincalResults
from pipeline.hifa.heuristics.phasespwmap import combine_spwmap
from pipeline.infrastructure import task_registry

LOG = infrastructure.get_logger(__name__)

__all__ = [
    'TimeGaincalInputs',
    'TimeGaincal',
]


class TimeGaincalInputs(gtypegaincal.GTypeGaincalInputs):

    # Amplitude caltable that is to be registered in callibrary as
    # applicable to TARGET/CHECK, and to AMPLITUDE,POL*,BANDPASS intents.
    amptable = vdp.VisDependentProperty(default=None)

    # Amplitude caltable used for diagnostic amplitude plots in weblog.
    calamptable = vdp.VisDependentProperty(default=None)

    calminsnr = vdp.VisDependentProperty(default=2.0)

    # Phase caltable to be registered for the non-PHASE calibrators.
    # This is also used for diagnostic phase vs. time plots in weblog.
    calphasetable = vdp.VisDependentProperty(default=None)

    # Default solint used for calibrators.
    calsolint = vdp.VisDependentProperty(default='int')

    # Override default base class intents for ALMA.
    @vdp.VisDependentProperty
    def intent(self):
        return 'PHASE,AMPLITUDE,BANDPASS,POLARIZATION,POLANGLE,POLLEAKAGE,DIFFGAINREF,DIFFGAINSRC'

    # Used for diagnostic phase offsets plots in weblog.
    offsetstable = vdp.VisDependentProperty(default=None)

    targetminsnr = vdp.VisDependentProperty(default=3.0)

    # Used for phase caltable that is to be registered in callibrary as
    # applicable to TARGET/CHECK, and to PHASE calibrator.
    targetphasetable = vdp.VisDependentProperty(default=None)

    targetsolint = vdp.VisDependentProperty(default='inf')

    parallel = sessionutils.parallel_inputs_impl(default=False)

    # docstring and type hints: supplements hifa_timegaincal
    def __init__(self, context, vis=None, output_dir=None, calamptable=None, calphasetable=None, offsetstable=None,
                 amptable=None, targetphasetable=None, calsolint=None, targetsolint=None, calminsnr=None,
                 targetminsnr=None, parallel=None, **parameters):
        """Initialize Inputs.

        Args:
            context: Pipeline context object containing state information.

            vis: The list of input MeasurementSets. Defaults to the list of
                MeasurementSets specified in the pipeline context.

                Example: ``vis=['M82A.ms', 'M82B.ms']``

            output_dir: Output directory.
                Defaults to None, which corresponds to the current working directory.

            calamptable: The list of output diagnostic calibration amplitude tables for
                the calibration targets. Defaults to the standard pipeline naming
                convention.

                Example: ``calamptable=['M82.gacal', 'M82B.gacal']``

            calphasetable: The list of output calibration phase tables for the
                calibration targets. Defaults to the standard pipeline naming convention.

                Example: ``calphasetable=['M82.gpcal', 'M82B.gpcal']``

            offsetstable: The list of output diagnostic phase offset tables for the
                calibration targets. Defaults to the standard pipeline naming convention.

                Example: ``offsetstable=['M82.offsets.gacal', 'M82B.offsets.gacal']``

            amptable: The list of output calibration amplitude tables for the
                calibration and science targets.
                Defaults to the standard pipeline naming convention.

                Example: ``amptable=['M82.gacal', 'M82B.gacal']``

            targetphasetable: The list of output phase calibration tables for the science
                targets. Defaults to the standard pipeline naming convention.

                Example: ``targetphasetable=['M82.gpcal', 'M82B.gpcal']``

            calsolint: Time solution interval in CASA syntax for calibrator source
                solutions.

                Example: ``calsolint='inf'``, ``calsolint='int'``, ``calsolint='100sec'``

            targetsolint: Time solution interval in CASA syntax for target source
                solutions.

                Example: ``targetsolint='inf'``, ``targetsolint='int'``, ``targetsolint='100sec'``

            calminsnr: Solutions below this SNR are rejected for calibrator solutions.

            targetminsnr: Solutions below this SNR are rejected for science target
                solutions.

            field: The list of field names or field ids for which gain solutions are to
                be computed. Defaults to all fields with the standard intent.

                Example: ``field='3C279'``, ``field='3C279, M82'``

            spw: The list of spectral windows and channels for which gain solutions are
                computed. Defaults to all science spectral windows.

                Example: ``spw='11'``, ``spw='11,13'``

            antenna: The selection of antennas for which gains are computed. Defaults to all.

            refant: Reference antenna name(s) in priority order. Defaults to most recent
                values set in the pipeline context. If no reference antenna is defined in
                the pipeline context use the CASA defaults.

                Example: ``refant='DV01'``, ``refant='DV05,DV07'``

            refantmode: Controls how the refant is applied. Currently available
                choices are 'flex', 'strict', and the default value of ''.
                Setting to '' allows the pipeline to select the appropriate
                mode based on the state of the reference antenna list.

                Examples: ``refantmode='strict'``, ``refantmode=''``

            solnorm: Normalise the gain solutions.

            minblperant: Minimum number of baselines required per antenna for each solve.
                Antennas with fewer baselines are excluded from solutions.

                Example: ``minblperant=2``

            smodel: Point source Stokes parameters for source model (experimental)
                Defaults to using standard MODEL_DATA column data.

                Example: ``smodel=[1,0,0,0]``  - (I=1, unpolarized)

            parallel: Process multiple MeasurementSets in parallel using the casampi parallelization framework.

                Options: ``'automatic'``, ``'true'``, ``'false'``, ``True``, ``False``

                Default: ``None`` (equivalent to ``False``)

        """
        super().__init__(context, vis=vis, output_dir=output_dir, **parameters)

        self.amptable = amptable
        self.calamptable = calamptable
        self.calminsnr = calminsnr
        self.calphasetable = calphasetable
        self.calsolint = calsolint
        self.offsetstable = offsetstable
        self.targetminsnr = targetminsnr
        self.targetphasetable = targetphasetable
        self.targetsolint = targetsolint
        self.parallel = parallel



class SerialTimeGaincal(gtypegaincal.GTypeGaincal):
    Inputs = TimeGaincalInputs

    def prepare(self, **parameters) -> GaincalResults:
        inputs = self.inputs

        # Create a results object.
        result = GaincalResults()
        result.phasecal_for_phase_plot = []

        # PIPE-2268: update intents to exclude those that are not present, to
        # avoid these appearing in CalApplications / weblog.
        inputs.intent = utils.filter_intents_for_ms(inputs.ms, inputs.intent)

        # Compute the phase solutions for the science target, check source,
        # and phase calibrator. This caltable will be registered as applicable
        # to the target, check source, and phase calibrator when the result for
        # this task is accepted.
        LOG.info('Computing phase gain table(s) for target(s), check source(s), and phase calibrator(s).')
        target_phasecal_calapps = self._do_phasecal_for_target()
        # Add the solutions to final task result, for adopting into context
        # callibrary, but do not merge them into local task context, so they
        # are not used in pre-apply of subsequent gaincal calls.
        result.pool.extend(target_phasecal_calapps)
        result.final.extend(target_phasecal_calapps)

        # Compute the phase solutions for all calibrators in inputs.intent.
        # These phase cal results include solutions for the PHASE calibrator
        # field(s), and will be temporarily accepted into the local context to
        # have these available as pre-apply in subsequent gaincals (both for
        # amplitude solves and for computing residual phase offsets). But for
        # the final task result, these phase solutions will only be registered
        # as applicable to the bandpass, flux, differential gain, and
        # polarization calibrators.
        LOG.info('Computing phase gain table(s) for bandpass, flux, diffgain, and polarization calibrator(s).')
        cal_phase_results, max_phase_solint = self._do_phasecal_for_calibrators()

        # Merge the phase solutions for the calibrators into the local task
        # context so that it is marked for inclusion in pre-apply (gaintable)
        # in subsequent gaincal calls during this task.
        for cpres in cal_phase_results:
            if not cpres.final:
                continue
            cpres.accept(inputs.context)

        # Look through calibrator phasecal results for any CalApplications for
        # caltables that are applicable to non-PHASE calibrators (i.e.
        # AMPLITUDE, BANDPASS, POL*, and DIFFGAIN*). Add these CalApps to the
        # final task result, to be merged into the final context / callibrary.
        for cpres in cal_phase_results:
            if not cpres.final:
                continue
            cp_calapp = cpres.final[0]
            if cp_calapp.intent != 'PHASE':
                result.final.append(cp_calapp)
                result.pool.append(cp_calapp)

            # PIPE-1377: add all results to the list to be plotted in the
            # phase vs. time diagnostic plots in the renderer.
            result.phasecal_for_phase_plot.append(cp_calapp)

        # Compute the amplitude calibration.
        LOG.info('Computing the final amplitude gain table.')
        amplitude_calapps = self._do_target_ampcal()

        # Accept the amplitude calibration into the final results.
        result.pool.extend(amplitude_calapps)
        result.final.extend(amplitude_calapps)

        # Produce the diagnostic table for displaying amplitude vs time plots.
        # For the solint, use the maximum SpW-mapping-mode-based solint that
        # was used earlier for phase solutions for the PHASE calibrator(s).
        # This table is not applied to the data, and no special mapping is
        # required here.
        LOG.info('Computing diagnostic amplitude gain table for displaying amplitude vs time plots.')
        amp_diagnostic_result = self._do_caltarget_ampcal(solint=max_phase_solint)
        result.calampresult = amp_diagnostic_result

        # To ensure that a diagnostic phase offsets caltable (to be created in
        # an upcoming step) will be sensitive to residual phase offsets, it is
        # necessary to enforce that the phase caltable for PHASE calibrator
        # fields used in pre-apply was solved with combine='spw'. But the
        # caltables for PHASE calibrator fields that earlier got solved and
        # merged into local context (for pre-apply in amplitude solves) may not
        # always have used combine='spw' (since it used optimal parameters
        # based on SpW mapping). Hence, first unregister any phase caltable for
        # PHASE calibrator fields where the SpW mapping recommended combine=''.
        LOG.info("Prior to computing diagnostic residual phase offsets, unregistering any phase gain table(s) for"
                 " phase calibrator(s) that were derived with combine='', earlier in this stage.")
        self._unregister_phasecal_with_no_combine()

        # Next, compute a new phase solutions solve for those PHASE calibrator
        # fields where the recommended combine was '', while this time
        # enforcing combine='spw'.
        LOG.info("Prior to computing diagnostic residual phase offsets, where necessary (caltable was unregistered)"
                 " re-computing phase gain table(s) for phase calibrator(s) while enforcing combine='spw'.")
        phasecal_phase_results = self._do_phasecal_for_phase_calibrators_forcing_combine()

        # Merge the new phase solutions for PHASE calibrator fields into the
        # local task context, so they are marked for inclusion in pre-apply in
        # subsequent diagnostic phase offsets solve.
        for res in phasecal_phase_results:
            res.accept(inputs.context)

        # Now compute a new phase solutions caltable while using previous phase
        # caltables in pre-apply. Assuming that inputs.intent included 'PHASE'
        # (true by default, but can be overridden by user), then the merger of
        # the previous phase solutions result into the local task context will
        # mean that the initial phase corrections will be included in pre-apply
        # during this gaincal, and thus this new caltable will represent the
        # residual phase offsets.
        LOG.info('Computing diagnostic residual phase offsets gain table.')
        phase_offsets_result = self._do_offsets_phasecal()
        result.phaseoffsetresult = phase_offsets_result

        return result

    def analyse(self, result: GaincalResults) -> GaincalResults:
        # Double-check that the caltables were actually generated.
        on_disk = [table for table in result.pool if table.exists()]
        result.final[:] = on_disk

        missing = [table for table in result.pool if table not in on_disk]
        result.error.clear()
        result.error.update(missing)

        return result

    @staticmethod
    def _get_spw_groupings(ms: MeasurementSet, spw: str, spwmap: List[int]) -> List[Tuple[int, str, str]]:
        """
        Group selected SpWs by SpectralSpec.

        Args:
            ms: MeasurementSet to query for spectral specs.
            spw: A comma separated string of SpW IDs to group together
            spwmap: List representing spectral window mapping

        Returns:
            List of tuples representing SpW groupings, containing:
              * Reference Spw ID
              * Spectral Spec ID
              * SpW IDs associated to that SpW grouping (value)
        """
        grouped_spw = []

        if len(spwmap) == 0:  # No SpW combination
            return grouped_spw

        request_spws = set(ms.get_spectral_windows(task_arg=spw))
        for sspec, spws in utils.get_spectralspec_to_spwid_map(request_spws).items():
            ref_spw = {spwmap[i] for i in spws}
            assert len(ref_spw) == 1, 'A SpectralSpec is mapped to more than one SpWs'
            grouped_spw.append((ref_spw.pop(), sspec, str(',').join(str(s) for s in sorted(spws))))

        LOG.debug(f'Spectral window grouping: {grouped_spw}')

        return grouped_spw

    def _do_phasecal_for_target(self) -> List[callibrary.CalApplication]:
        """
        This method is responsible for creating phase gain caltable(s) that
        will be applicable to the TARGET, the CHECK source, and the PHASE
        calibrator.

        Separate phase solutions are created for each PHASE field, and for each
        SpectralSpec when a "combine" SpW mapping is used.

        The resulting caltable(s) will be part of the final task result, with
        separate CalApplications to register the caltable(s) to be applicable
        to PHASE, as well as to TARGET/CHECK.
        """
        inputs = self.inputs
        p_intent = 'PHASE'

        # Initialize output list of CalApplications.
        calapp_list = []

        # Determine non-phase calibrator fields, to be added to gaincal solve
        # for plotting purposes.
        np_intents = ','.join(dict.fromkeys(item for item in inputs.intent.split(',') if item != p_intent))
        np_fields = None
        if np_intents:
            # PIPE-2752: Identify fields that have non-phase intents but lack the PHASE intent.
            candidates = inputs.ms.get_fields(intent=np_intents)
            exclusive_fields = [f.name for f in candidates if p_intent not in f.intents]
            if exclusive_fields:
                np_fields = ','.join(dict.fromkeys(exclusive_fields))
            else:
                LOG.debug('No exclusive non-phase fields for intents=%s selection on %s', np_intents, inputs.ms)

        # Determine which SpWs to solve for, which SpWs the solutions should
        # apply to, and whether to override refantmode. By default, use all
        # input SpW, do not restrict what SpWs the solutions apply to, and do
        # not override the refantmode.
        spw_to_solve = inputs.spw
        refantmode = None
        apply_to_spw = None
        if inputs.ms.is_band_to_band:
            # PIPE-2087: for BandToBand, restrict the solve to the diffgain
            # reference SpWs, use refantmode strict for the solve, and register
            # the solutions to be applied to the diffgain on-source SpWs.
            dg_refspws = inputs.ms.get_spectral_windows(task_arg=inputs.spw, intent='DIFFGAINREF')
            dg_srcspws = inputs.ms.get_spectral_windows(task_arg=inputs.spw, intent='DIFFGAINSRC')
            spw_to_solve = ','.join(str(s.id) for s in dg_refspws)
            refantmode = 'strict'
            apply_to_spw = ','.join(str(s.id) for s in dg_srcspws)

        # Create separate phase solutions for each PHASE field.
        for field in inputs.ms.get_fields(intent=p_intent):
            # Retrieve from MS which TARGET/CHECK fields the gain solutions for
            # the current PHASE field should be applied to.
            tc_fields = ','.join(inputs.ms.phasecal_mapping.get(field.name, {}))

            # If the user specified a filename, then add the field name, to
            # ensure the filenames remain unique in case of multiple fields.
            caltable = None
            if inputs.targetphasetable:
                root, ext = os.path.splitext(inputs.targetphasetable)
                caltable = f'{root}.{field.name}{ext}'

            # Get optimal phase solution parameters for current PHASE field,
            # based on spw mapping info in MS. No need to catch the value for
            # optimal solint as solint will be fixed to inputs.targetsolint.
            combine, gaintype, interp, _, spwmap = self._get_phasecal_params(p_intent, field.name)

            # PIPE-2087: for BandToBand override interp, for these phase
            # solutions that will apply to the science target.
            if inputs.ms.is_band_to_band:
                interp = 'linearPD,linear'

            # PIPE-390: if not combining across spw, then no need to deal with
            # SpectralSpec, so create a gaincal solution for all SpWs, using
            # provided gaintype, spwmap, and interp.
            if not combine:
                calapp_list.extend(self._do_target_phasecal(caltable=caltable, field=field.name, spw=spw_to_solve,
                                                            gaintype=gaintype, combine=combine, spwmap=spwmap,
                                                            interp=interp, apply_to_field=tc_fields,
                                                            apply_to_spw=apply_to_spw, include_field=np_fields,
                                                            refantmode=refantmode))

            # Otherwise, a combined SpW solution is expected, and we need to
            # create separate solutions for each SpectralSpec grouping of Spws.
            else:
                # Group the input SpWs by SpectralSpec.
                spw_groups = self._get_spw_groupings(inputs.ms, spw_to_solve, spwmap)
                if not spw_groups:
                    raise ValueError('Invalid SpW grouping input.')

                # Loop through each grouping of spws.
                for _, sspec, spw_sel in spw_groups:
                    LOG.info(f'Processing spectral spec {sspec} with spws {spw_sel}')

                    # Check if there are scans for current intent and SpWs.
                    selected_scans = inputs.ms.get_scans(scan_intent=p_intent, spw=spw_sel)
                    if len(selected_scans) == 0:
                        LOG.info(f'Skipping table generation for empty selection: spw={spw_sel}, intent={p_intent}')
                        continue

                    # If an explicit output filename is defined, then add the
                    # spw selection to ensure the filenames remain unique.
                    if caltable:
                        root, ext = os.path.splitext(caltable)
                        caltable = f'{root}.{spw_sel}{ext}'

                    # Run phase calibration.
                    calapp_list.extend(self._do_target_phasecal(caltable=caltable, field=field.name, spw=spw_sel,
                                                                gaintype=gaintype, combine=combine, spwmap=spwmap,
                                                                interp=interp, apply_to_field=tc_fields,
                                                                apply_to_spw=apply_to_spw, include_field=np_fields,
                                                                refantmode=refantmode))

        return calapp_list

    def _do_target_phasecal(self, caltable: str = None, field: str = None, spw: str = None, gaintype: str = None,
                            combine: str = None, interp: str = None, spwmap: List[int] = None,
                            apply_to_field: str = None, apply_to_spw: str = None, include_field: str = None,
                            refantmode: Optional[str] = None)\
            -> List[callibrary.CalApplication]:
        """
        This runs the gaincal for creating phase solutions intended for TARGET,
        CHECK, and PHASE. The result contains two CalApplications, one for
        how to apply the caltable to the PHASE calibrator, and a second one for
        how to apply the caltable to the TARGET and CHECK source(s).
        """
        inputs = self.inputs

        gc_fields = field
        if include_field:
            gc_field_list = gc_fields.split(',')
            gc_field_list.extend(include_field.split(','))
            gc_fields = ','.join(dict.fromkeys(gc_field_list))

        # PIPE-1154: for phase solutions of target, check, phase, always use
        # solint=inputs.targetsolint.
        task_args = {
            'output_dir': inputs.output_dir,
            'vis': inputs.vis,
            'caltable': caltable,
            'field': gc_fields,
            'intent': inputs.intent,
            'spw': spw,
            'solint': inputs.targetsolint,
            'gaintype': gaintype,
            'calmode': 'p',
            'minsnr': inputs.targetminsnr,
            'combine': combine,
            'refant': inputs.refant,
            'refantmode': refantmode,
            'minblperant': inputs.minblperant,
            'solnorm': inputs.solnorm
        }
        result = do_gtype_gaincal(inputs.context, self._executor, task_args)

        # Create new CalApplications to correctly register caltable.
        new_calapps = []

        # Define what overrides should be included in the cal application.
        # Phase solution caltables should always be registered with
        # calwt=False (PIPE-1154). Adjust the interpolation and SpW mapping if
        # provided.
        calapp_overrides = {'calwt': False}
        if interp:
            calapp_overrides['interp'] = interp
        if spwmap:
            calapp_overrides['spwmap'] = spwmap

        # Create a modified CalApplication to register this caltable against
        # the PHASE calibrator field itself.
        new_calapps.append(callibrary.copy_calapplication(result.final[0], intent='PHASE', field=field,
                                                          gainfield=field, **calapp_overrides))

        # If the current PHASE field was mapped to TARGET/CHECK field(s), then
        # create a modified CalApplication to register this caltable against
        # those TARGET/CHECK fields, where present in the MS (PIPE-2268).
        if apply_to_field:
            # Adjust what SpWs to apply to, if provided.
            if apply_to_spw:
                calapp_overrides['spw'] = apply_to_spw
            intents_for_calapp = utils.filter_intents_for_ms(inputs.ms, 'CHECK,TARGET')
            if intents_for_calapp:
                new_calapps.append(
                    callibrary.copy_calapplication(
                        result.final[0],
                        intent=intents_for_calapp,
                        field=apply_to_field,
                        gainfield=field,
                        **calapp_overrides,
                    )
                )

        return new_calapps

    def _do_phasecal_for_calibrators(self) -> tuple[list[GaincalResults], float | None]:
        """
        This method is responsible for creating phase gain caltable(s) that
        are applicable to all calibrators specified in inputs.intent, typically:
        phase, amplitude, bandpass, diffgain(ref/src), and polarization.
        """
        inputs = self.inputs
        phasecal_results = []

        # Split intents by PHASE and non-PHASE calibrators.
        p_intent = 'PHASE'
        np_intents = set(inputs.intent.split(',')) - {p_intent}

        # PIPE-1154: first create a phase caltable for the non-PHASE
        # calibrators.
        if np_intents:
            phasecal_results.extend(self._do_phasecal_for_non_phase_calibrators(np_intents))

        # PIPE-1154: next, compute the phase gain solutions for the PHASE
        # calibrator fields. These solutions for the PHASE fields are not
        # intended for the final result, but will be merged into the local task
        # context, so that they are used in pre-apply when computing the
        # residual phase offsets. Track the maximum phase solint that gets
        # used, so the same value can be when computing the diagnostic
        # amplitude caltable.
        max_phase_solint = None
        if p_intent in inputs.intent:
            pcal_results, max_phase_solint = self._do_phasecal_for_phase_calibrators(p_intent)
            phasecal_results.extend(pcal_results)

        return phasecal_results, max_phase_solint

    def _do_phasecal_for_non_phase_calibrators(self, intents: set) -> list[GaincalResults]:
        """
        Compute phase gain caltable(s) for the non-PHASE calibrators, typically:
        amplitude, bandpass, diffgain(ref/src), and polarization.
        """
        inputs = self.inputs
        phasecal_results = []

        # PIPE-645: for bandpass, amplitude, diffgain, and polarisation intents,
        # always use minsnr set to 3.
        minsnr = 3.0

        # Create separate gaincal for each non-phase calibrator field.
        fields = [f for f in inputs.ms.get_fields(intent=','.join(intents))]
        for field in fields:
            # Matching intents in current field.
            fld_intents = field.intents.intersection(intents)
            fld_intents_str = ",".join(fld_intents)
            LOG.info(f'Compute phase gaincal table for intent={fld_intents_str}, field={field.name}.')

            # If this field is used as a bandpass calibrator, then retrieve the
            # optimal phase cal parameters for BANDPASS, and solve for all
            # matching intents at once. This case can cover a number of cases
            # of overlapping calibrators:
            # - BP == AMP: should use optimal parameters for BANDPASS.
            # - BP == DIFFGAIN*: should use optimal parameters for BANDPASS.
            # - BP == POL*: in this case, hifa_spwphaseup will not have
            #     derived any optimal parameters for this field (explicitly
            #     skips fields with POL*), so the look-up should return the
            #     default gaincal parameters, as is required for polarization
            #     calibrators.
            if "BANDPASS" in fld_intents:
                combine, gaintype, interp, solint, spwmap = self._get_phasecal_params('BANDPASS', field.name)
                phasecal_results.append(
                    self._do_calibrator_phasecal(field=field.name, intent=fld_intents_str, spw=inputs.spw,
                                                 gaintype=gaintype, combine=combine, solint=solint, minsnr=minsnr,
                                                 spwmap=spwmap, interp=interp))
            # If this field is a diffgain calibrator (while no overlap with
            # bandpass), then assume that hifa_spwphaseup will have stored
            # separate SpwMapping info for DIFFGAINREF and DIFFGAINSRC and
            # create separate solves for those. It is assumed here that if
            # DIFFGAINSRC is present, DIFFGAINREF must be present as well.
            # It is further assumed that there is no support for band-to-band
            # polarization, so this field should not have also POL* intents.
            # It is further assumed that the diffgain calibrator cannot also be
            # the amplitude calibrator. If it was, then the amplitude scans
            # would not get a phase-up solution here.
            elif "DIFFGAINSRC" in fld_intents:
                for dg_intent in {"DIFFGAINREF", "DIFFGAINSRC"}:
                    combine, gaintype, interp, solint, spwmap = self._get_phasecal_params(dg_intent, field.name)
                    phasecal_results.append(
                        self._do_calibrator_phasecal(field=field.name, intent=dg_intent, spw=inputs.spw,
                                                     gaintype=gaintype, combine=combine, solint=solint, minsnr=minsnr,
                                                     spwmap=spwmap, interp=interp))
            # For all other cases, use all intents of current field to retrieve
            # optimal parameters and compute phase solutions.
            # Typically, this would cover amplitude and/or polarization
            # calibrators.
            # Note: if this field covers both AMP and POL*, then hifa_spwphaseup
            # would not have derived optimal parameters as it currently skips
            # polarization fields; so instead this step would use default
            # phasecal parameters.
            else:
                combine, gaintype, interp, solint, spwmap = self._get_phasecal_params(fld_intents_str, field.name)
                phasecal_results.append(
                    self._do_calibrator_phasecal(field=field.name, intent=fld_intents_str, spw=inputs.spw,
                                                 gaintype=gaintype, combine=combine, solint=solint, minsnr=minsnr,
                                                 spwmap=spwmap, interp=interp))

        return phasecal_results

    def _do_phasecal_for_phase_calibrators(self, intent: str) -> tuple[list[GaincalResults], float]:
        """
        This method is responsible for creating phase gain caltable(s) for each
        field that covers a PHASE calibrator, using optimal gaincal parameters
        based on the SpW mapping registered in the measurement set.
        """
        inputs = self.inputs

        # Initialize list of phase gaincal results and solints used.
        phasecal_results = []
        solints = []

        # Determine which SpWs to solve for: use all input SpWs, filtered for
        # phase calibrator intent.
        spw_to_solve = ','.join(str(s.id) for s in inputs.ms.get_spectral_windows(task_arg=inputs.spw, intent=intent))

        # Create separate phase solutions for each PHASE field. These solutions
        # are intended to be used as a temporary pre-apply when generating the
        # final amplitude caltable and the phase offsets caltable.
        for field in inputs.ms.get_fields(intent=intent):
            # Get optimal phase solution parameters for current PHASE field,
            # based on spw mapping info in MS.
            combine, gaintype, interp, solint, spwmap = self._get_phasecal_params(intent, field.name)

            # PIPE-390: if not combining across spw, then no need to deal with
            # SpectralSpec for solint considerations, so create a gaincal
            # solution for all SpWs, using provided solint, gaintype, and
            # interp.
            if not combine:
                phasecal_results.append(self._do_calibrator_phasecal(field=field.name, intent=intent, spw=spw_to_solve,
                                                                     gaintype=gaintype, combine=combine, solint=solint,
                                                                     minsnr=inputs.calminsnr, interp=interp,
                                                                     spwmap=spwmap))
                solints.append(solint)

            # Otherwise, a combined SpW solution is expected, and we need to
            # create separate solutions for each SpectralSpec grouping of SpWs.
            else:
                # Group the input SpWs by SpectralSpec.
                spw_groups = self._get_spw_groupings(inputs.ms, spw_to_solve, spwmap)
                if not spw_groups:
                    raise ValueError('Invalid SpW grouping input.')

                # Loop through each grouping of SpWs.
                for ref_spw, sspec, spw_sel in spw_groups:
                    LOG.info(f'Processing spectral spec {sspec} with SpWs {spw_sel}')
                    phasecal_results.append(self._do_calibrator_phasecal(field=field.name, intent=intent, spw=spw_sel,
                                                                         gaintype=gaintype, combine=combine,
                                                                         solint=solint, minsnr=inputs.calminsnr,
                                                                         interp=interp, spwmap=spwmap))
                    solints.append(solint)

        # PIPE-1154: determine which was the longest solint used for any of the
        # PHASE fields; this will be re-used for the diagnostic amplitude
        # caltable.
        max_solint = max(solints)

        return phasecal_results, max_solint

    def _do_phasecal_for_phase_calibrators_forcing_combine(self) -> list[GaincalResults]:
        """
        This method will create phase gain caltable(s) for each field that
        both a.) covers a PHASE calibrator, and b.) for which the SpW mapping
        registered in the measurement set recommended to use combine='' in the
        gaincal solve. For these fields, an appropriate "combine" SpW map is
        generated locally, then a new gaincal solve is performed using this SpW
        map and enforcing combine='spw'.

        The resulting caltable is used later during this task for computing the
        residual phase offsets.
        """
        inputs = self.inputs
        intent = "PHASE"

        # Initialize list of phase gaincal results.
        phasecal_results = []

        # Determine which SpWs to solve for: use all input SpWs, filtered for
        # phase calibrator intent.
        spw_to_solve = ','.join(str(s.id) for s in inputs.ms.get_spectral_windows(task_arg=inputs.spw, intent=intent))

        # Create separate phase solutions for each PHASE field.
        for field in inputs.ms.get_fields(intent="PHASE"):
            # Get optimal phase solution parameters for current PHASE field,
            # based on spw mapping info in MS.
            combine, gaintype, interp, solint, spwmap = self._get_phasecal_params(intent, field.name)

            # Skip any field where the recommended combine was already 'spw'.
            if combine == 'spw':
                continue

            # For PHASE calibrator fields where the SpW mapping recommended to
            # use combine='', continue with creating a new caltable while
            # forcing the combination of SpWs, and generate a corresponding
            # combine spwmap with which this caltable should be registered.
            # This is done to ensure that the subsequent phase offsets
            # caltable is always sensitive to residual offsets on the PHASE
            # calibrator and the corresponding plots would display
            # meaningful information.

            # Create a "combine" spwmap for input SpWs.
            spws = inputs.ms.get_spectral_windows(inputs.spw)
            spwmap = combine_spwmap(spws)

            # Run the phase calibration, forcing combination of SpWs with
            # appropriate values for interp and spwmap.
            phasecal_results.append(self._do_calibrator_phasecal(field=field.name, intent=intent, spw=spw_to_solve,
                                                                 gaintype=gaintype, combine='spw', solint=solint,
                                                                 minsnr=inputs.calminsnr, interp='linearPD,linear',
                                                                 spwmap=spwmap))

        return phasecal_results

    # Used to calibrate "selfcaled" targets
    def _do_calibrator_phasecal(self, field: str = None, intent: str = None, spw: str = None, gaintype: str = 'G',
                                combine: str = None, solint: str = None, minsnr: float = None,
                                interp: str = None, spwmap: List[int] = None) -> GaincalResults:
        """
        This runs the gaincal for creating phase solutions intended for the
        calibrators (amplitude, bandpass, polarization, phase, diffgain(ref/src)).
        """
        inputs = self.inputs

        # Construct filename of output caltable:
        # If provided, use the "calphasetable" parameter from top-level task
        # inputs as a basename, but modify to ensure the filename is unique.
        caltable = None
        if inputs.calphasetable:
            root, ext = os.path.splitext(inputs.calphasetable)
            # Always add intent, and if the intent is PHASE then also add field
            # name.
            field_str = f'.{field}' if intent == 'PHASE' else ''
            caltable = f'{root}.{intent}{field_str}{ext}'

        # Filter provided SpWs to only use science SpWs that were covered by
        # current intent(s) and field(s). In principle, it should suffice to
        # only provide intent and field to gaincal, but restricting SpWs here
        # ensures that the filename of the output caltable only contains the
        # SpWs for which solutions are computed.
        fieldlist = inputs.ms.get_fields(task_arg=field)
        sci_spws = set(inputs.ms.get_spectral_windows(task_arg=spw, intent=intent))
        spws_to_solve = ','.join({str(spw.id) for fld in fieldlist for spw in fld.valid_spws.intersection(sci_spws)})

        task_args = {
            'output_dir': inputs.output_dir,
            'vis': inputs.vis,
            'caltable': caltable,
            'field': field,
            'intent': intent,
            'spw': spws_to_solve,
            'solint': solint,
            'gaintype': gaintype,
            'calmode': 'p',
            'minsnr': minsnr,
            'combine': combine,
            'refant': inputs.refant,
            'minblperant': inputs.minblperant,
            'solnorm': inputs.solnorm,
        }
        result = do_gtype_gaincal(inputs.context, self._executor, task_args)

        # Modify the cal application for this caltable based on overrides.
        # Phase solution caltables should always be registered to be applied
        # with calwt=False (PIPE-1154). Register the caltable to be applied
        # only to the calibrator intent(s). Adjust the interpolation and SpW
        # mapping if provided.
        calapp_overrides = {
            'calwt': False,
            'intent': intent,
        }
        if interp:
            calapp_overrides['interp'] = interp
        if spwmap:
            calapp_overrides['spwmap'] = spwmap

        # PIPE-1154: if adding solutions for a field with PHASE intent, then
        # modify the CalApplication to ensure that solutions from this PHASE
        # field are only applied to itself.
        if intent == 'PHASE':
            calapp_overrides['field'] = field
            calapp_overrides['gainfield'] = field

        # Create a modified CalApplication and replace CalApp in result with
        # this new one.
        result.pool = [callibrary.copy_calapplication(c, **calapp_overrides) for c in result.pool]
        result.final = [callibrary.copy_calapplication(c, **calapp_overrides) for c in result.final]

        return result

    def _do_offsets_phasecal(self) -> GaincalResults:
        """
        This method computes a diagnostic phase caltable where the previously
        derived phase caltable is pre-applied, to be used for diagnostic plots
        of the residual phase offsets. Resulting caltable will not be
        registered in the context callibrary, i.e. will not be applied to data.
        """
        inputs = self.inputs

        # PIPE-1154: for the residual phase offset table, always use
        # gaintype = 'G'.
        task_args = {
            'output_dir': inputs.output_dir,
            'vis': inputs.vis,
            'caltable': inputs.offsetstable,
            'field': inputs.field,
            'intent': inputs.intent,
            'spw': inputs.spw,
            'solint': 'inf',
            'gaintype': 'G',
            'calmode': 'p',
            'minsnr': inputs.calminsnr,
            'combine': '',
            'refant': inputs.refant,
            'minblperant': inputs.minblperant,
            'solnorm': inputs.solnorm
        }

        # Create a unique table name. The component filenames depend on task arguments (solint, calmode, gaintype,
        # etc.), hence we create a task to calculate the arguments, then modify the resulting filename
        task_inputs = gtypegaincal.GTypeGaincalInputs(inputs.context, **task_args)
        root, ext = os.path.splitext(task_inputs.caltable)
        task_args['caltable'] = '{}.{}{}'.format(root, 'offsets', ext)

        result = do_gtype_gaincal(inputs.context, self._executor, task_args)

        return result

    def _do_caltarget_ampcal(self, solint: Optional[float] = None) -> GaincalResults:
        """
        Create amplitude caltable used for diagnostic plots. Resulting
        caltable will not be registered in the context callibrary, i.e.
        will not be applied to data.
        """
        inputs = self.inputs

        task_args = {
            'output_dir': inputs.output_dir,
            'vis': inputs.vis,
            'caltable': inputs.calamptable,
            'field': inputs.field,
            'intent': inputs.intent,
            'spw': inputs.spw,
            'solint': solint,
            'gaintype': 'T',
            'calmode': 'a',
            'minsnr': inputs.calminsnr,
            'combine': inputs.combine,
            'refant': inputs.refant,
            'minblperant': inputs.minblperant,
            'solnorm': inputs.solnorm
        }
        result = do_gtype_gaincal(inputs.context, self._executor, task_args)

        return result

    def _do_target_ampcal(self) -> List[callibrary.CalApplication]:
        """
        This method computes the amplitude caltable intended for TARGET,
        CHECK, and all calibrators. It returns a list of two CalApplications,
        one for how to apply the caltable to all the calibrators, and a second
        one for how to apply the caltable to the TARGET and CHECK source(s).
        """
        inputs = self.inputs

        task_args = {
            'output_dir': inputs.output_dir,
            'vis': inputs.vis,
            'caltable': inputs.amptable,
            'field': inputs.field,
            'intent': inputs.intent,
            'spw': inputs.spw,
            'solint': 'inf',
            'gaintype': 'T',
            'calmode': 'a',
            'minsnr': inputs.targetminsnr,
            'combine': inputs.combine,
            'refant': inputs.refant,
            'minblperant': inputs.minblperant,
            'solnorm': inputs.solnorm
        }
        result = do_gtype_gaincal(inputs.context, self._executor, task_args)

        # Create modified CalApplications for registering this amplitude
        # caltable in the callibrary/context, once for TARGET,CHECK, and once
        # for the calibrators.
        #
        # Spec for gainfield application from CAS-12214:
        #
        # 1) When applying phase and/or amp gain tables to calibrators,
        #   continue to use gainfield='nearest'. This will ensure that time
        #   interpolations from one group's complex gain calibrator's
        #   solutions to the next group's complex gain calibrator solutions
        #   will never influence how either calibrator gets calibrated.
        #
        # 2) When applying phase and/or amp gain tables to science targets,
        #    leave gainfield blank (instead of 'nearest'), so that time
        #    interpolation across all gain calibrators will be used to
        #    calibrate science targets. This will automagically take care of
        #    the multiple science groups case. Specifically, since it is
        #    assumed that all science target groups are bracketed on both
        #    sides by "their" complex gain calibrator, there will never be a
        #    case where the interpolated solution between two complex gain
        #    calibrators needs to be used.
        result_calapp = result.final[0]

        # Create CalApplication for the calibrators.
        cal_calapp = callibrary.copy_calapplication(result_calapp, intent=inputs.intent, gainfield='nearest',
                                                    interp='nearest,linear')

        # Create CalApplication for the TARGET/CHECK sources, where present in
        # the MS (PIPE-2268).
        calapp_overrides = {'intent': utils.filter_intents_for_ms(inputs.ms, 'CHECK,TARGET'), 'gainfield': ''}
        fields_targets = inputs.ms.get_fields(intent=calapp_overrides['intent'])
        fields_not_targets = inputs.ms.get_fields(
            intent='BANDPASS,PHASE,AMPLITUDE,POLARIZATION,DIFFGAINREF,DIFFGAINSRC'
        )
        fields_checktarget_only = set(fields_targets) - set(fields_not_targets)
        if not calapp_overrides['intent'] or not fields_checktarget_only:
            LOG.debug(
                'No CHECK-only or TARGET-only intent scans found in %s and we will skip the creation of CalApp for intents="CHECK,TARGET".',
                inputs.ms.name,
            )
            return [cal_calapp]

        # PIPE-2087: for BandToBand, register the solutions to be applied to the
        # diffgain on-source SpWs, and use the amplitude solutions from the
        # BANDPASS intent.
        if inputs.ms.is_band_to_band:
            dg_srcspws = inputs.ms.get_spectral_windows(task_arg=inputs.spw, intent='DIFFGAINSRC')
            calapp_overrides['spw'] = ','.join(str(s.id) for s in dg_srcspws)
            calapp_overrides['gainfield'] = ','.join(f.name for f in inputs.ms.get_fields(intent='BANDPASS'))

        target_calapp = callibrary.copy_calapplication(result_calapp, **calapp_overrides)

        return [cal_calapp, target_calapp]

    def _get_phasecal_params(self, intent: str, field: str) -> tuple[str, str, str | None, str, list[int]]:
        inputs = self.inputs

        # By default, no spw mapping or combining, no interp, gaintype='G',
        # and use solint set by "calsolint" input parameter.
        combine = ''
        gaintype = 'G'
        interp = None
        solint = inputs.calsolint
        spwmap = []

        # Try to fetch spwmapping info from MS for requested intent and field.
        spwmapping = inputs.ms.spwmaps.get((intent, field), None)

        # If a mapping was found, use the spwmap, and update further parameters
        # depending on whether it is a combine spw mapping.
        if spwmapping:
            spwmap = spwmapping.spwmap
            solint = spwmapping.solint 
            gaintype = spwmapping.gaintype 
            # If the spwmap is for combining spws, then override combine and
            # interp accordingly.
            if spwmapping.combine:
                combine = 'spw'
                interp = 'linearPD,linear'
            else:
                # PIPE-1154: when using a phase up spw mapping, ensure that
                # interp = 'linear,linear'; though this may need to be changed
                # in the future, see PIPEREQ-85.
                interp = 'linear,linear'

        return combine, gaintype, interp, solint, spwmap

    def _unregister_phasecal_with_no_combine(self):
        """
        This method will unregister from the callibrary in the local context
        (stored in inputs) any CalApplication that is registered for a PHASE
        calibrator field for which the SpW mapping recommends solving with
        combine='', or for which no SpW mapping exists (assumed the PHASE field
        will in that case have been solved with default combine='').
        """
        inputs = self.inputs

        # Identify the MS to process.
        vis: str = inputs.ms.basename

        # Identify which PHASE calibrator fields to process.
        # First identify all PHASE fields.
        fields = {f.name for f in inputs.ms.get_fields(intent="PHASE")}
        # Next, if a SpW mapping was registered for this PHASE field, check if
        # it already recommended solving with SpW combination, in which case
        # there is no reason to unregister. If no SpW mapping was registered,
        # then the PHASE field is expected to have been solved with the default
        # combine='', and so it's kept for unregistering.
        for (intent, field), spwmapping in inputs.ms.spwmaps.items():
            if intent == "PHASE" and spwmapping.combine:
                fields.remove(field)

        # If there were no PHASE calibrator fields with combine='', then there
        # are no CalApplications to unregister.
        if not fields:
            return

        # Define predicate function that matches the kind of caltable that
        # needs to be removed from the CalLibrary.
        def phase_no_combine_matcher(calto: callibrary.CalToArgs, calfrom: callibrary.CalFrom) -> bool:
            calto_vis = {os.path.basename(v) for v in calto.vis}
            # Find caltables generated by hifa_timegaincal, for current vis,
            # that are to be applied to PHASE calibrator intent, and that were
            # derived from a field that is on the list of fields to re-compute.
            # Use calfrom.gainfield rather than calto.field since the latter
            # may have been translated to field ID rather than name.
            do_delete = 'hifa_timegaincal' in calfrom.gaintable and vis in calto_vis and "PHASE" in calto.intent \
                        and calfrom.gainfield in fields
            if do_delete:
                # This message may appear multiple times for same caltable if
                # that table was registered through multiple CalApplications,
                # e.g. for different SpWs.
                LOG.debug(f'Unregistering phase caltable {calfrom.gaintable} from task-specific context.')
            return do_delete

        inputs.context.callibrary.unregister_calibrations(phase_no_combine_matcher)


@task_registry.set_equivalent_casa_task('hifa_timegaincal')
@task_registry.set_casa_commands_comment('Time dependent gain calibrations are computed.')
class TimeGaincal(sessionutils.ParallelTemplate):
    Inputs = TimeGaincalInputs
    Task = SerialTimeGaincal


def do_gtype_gaincal(context, executor, task_args) -> GaincalResults:
    task_inputs = gtypegaincal.GTypeGaincalInputs(context, **task_args)
    task = gtypegaincal.GTypeGaincal(task_inputs)
    result = executor.execute(task)

    # sanity checks in case gaincal starts returning additional caltable applications
    assert len(result.final) <= 1, '>1 caltable application registered by gaincal'

    return result
