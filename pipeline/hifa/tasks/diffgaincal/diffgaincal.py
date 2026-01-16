import numpy as np

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.callibrary as callibrary
import pipeline.infrastructure.vdp as vdp
from pipeline.domain.measurementset import MeasurementSet
from pipeline.h.tasks.common import commonhelpermethods
from pipeline.hif.tasks.gaincal import common
from pipeline.hif.tasks.gaincal import gtypegaincal
from pipeline.hifa.heuristics.phasespwmap import IntentField, SpwMapping
from pipeline.hifa.heuristics.phasespwmap import combine_spwmap
from pipeline.hifa.heuristics.phasespwmap import update_spwmap_for_band_to_band
from pipeline.infrastructure import casa_tools
from pipeline.infrastructure import task_registry

LOG = infrastructure.get_logger(__name__)

__all__ = [
    'DiffGaincal',
    'DiffGaincalInputs',
    'DiffGaincalResults',
]


class DiffGaincalResults(basetask.Results):
    def __init__(self, vis: str | None = None, final: list | None = None, pool: list | None = None,
                 residual_phase_result: common.GaincalResults | None = None,
                 ref_phase_result: common.GaincalResults | None = None, spwmaps: dict | None = None):
        """
        Initialise the differential gain results object.
        """
        super().__init__()
        self.vis = vis

        # Lists of CalApplications.
        if final is None:
            final = []
        if pool is None:
            pool = []
        self.error = set()
        self.final = final[:]
        self.pool = pool[:]

        # Spectral window mappings (populated if task decides this needs to be
        # updated.
        self.spwmaps = spwmaps if spwmaps is not None else {}

        # QA message about missing SpWs.
        self.qa_message = ''

        # Results from child phase gaincal tasks.
        self.residual_phase_result = residual_phase_result
        self.ref_phase_result = ref_phase_result

    def merge_with_context(self, context):
        # Register all CalApplications from each session.
        for calapp in self.final:
            LOG.info(f'Adding calibration to callibrary:\n{calapp.calto}\n'
                      f'{calapp.calfrom}')
            context.callibrary.add(calapp.calto, calapp.calfrom)

        # If this task derived new spectral window mappings, then merge these
        # into the MS.
        if self.spwmaps:
            ms = context.observing_run.get_ms(name=self.vis)
            ms.spwmaps.update(self.spwmaps)

    def __repr__(self):
        return 'DiffGaincalResults'


class DiffGaincalInputs(vdp.StandardInputs):

    flagging_frac_limit = vdp.VisDependentProperty(default=0.7)
    hm_spwmapmode = vdp.VisDependentProperty(default='auto')

    @hm_spwmapmode.convert
    def hm_spwmapmode(self, value):
        allowed = {'all', 'auto', 'both', 'never', 'offset', 'reference', 'residual'}
        if value not in allowed:
            m = ', '.join(('{!r}'.format(i) for i in allowed))
            raise ValueError('Value not in allowed value set ({!s}): {!r}'.format(m, value))
        return value

    missing_scans_frac_limit = vdp.VisDependentProperty(default=0.7)

    def __init__(self, context, output_dir=None, vis=None, flagging_frac_limit=None, hm_spwmapmode=None,
                 missing_scans_frac_limit=None):
        """Initialize Inputs.

        Args:
            context: Pipeline context object containing state information.

            output_dir: Output directory.
                Defaults to None, which corresponds to the current working directory.

            vis: The list of input MeasurementSets. Defaults to the list of
                MeasurementSets specified in the pipeline context.

                Example: ``['M32A.ms', 'M32B.ms']``

            flagging_frac_limit: if the fraction of flagged data in the
                temporary phase gaintable exceeds this limit then SpW
                combination is triggered.

            hm_spwmapmode: The spectral window mapping heuristic mode. The
                options are:

                - ``'all'``: SpW combination is forced for the diffgain
                    low-frequency reference intent solutions, the diffgain
                    high-frequency source intent solutions (actual band-to-band
                    offsets), and for the diagnostic residual phase offsets on
                    the diffgain high-frequency source intent.
                - ``'auto'``: Assess need for SpW combination based on SpwMapping
                    from hifa_spwphaseup, and where necessary check the
                    gaintable for missing SpWs / too many flagged data / too few
                    scan solutions.
                - ``'both'``: SpW combination is forced for the diffgain
                    low-frequency reference intent solutions and for the
                    diagnostic residual phase offsets on the diffgain
                    high-frequency source intent.
                - ``'offset'``: SpW combination is forced for the diffgain
                    high-frequency source intent solutions (actual band-to-band
                    offsets).
                - ``'reference'``: SpW combination is forced for the diffgain
                    low-frequency reference intent solutions.
                - ``'residual'``: SpW combination is forced for the diagnostic
                    residual phase offsets on the diffgain high-frequency source
                    intent.

                Example: ``hm_spwmapmode='auto'``

            missing_scans_frac_limit: if the fraction of missing scans in the
                temporary phase gaintable exceeds this limit then SpW
                combination is triggered.
        """
        super().__init__()
        # Standard Pipeline inputs.
        self.context = context
        self.vis = vis
        self.output_dir = output_dir

        # Diffgaincal specific inputs.
        self.flagging_frac_limit = flagging_frac_limit
        self.hm_spwmapmode= hm_spwmapmode
        self.missing_scans_frac_limit = missing_scans_frac_limit


@task_registry.set_equivalent_casa_task('hifa_diffgaincal')
@task_registry.set_casa_commands_comment('Compute the differential gain calibration.')
class DiffGaincal(basetask.StandardTaskTemplate):
    Inputs = DiffGaincalInputs

    def prepare(self) -> DiffGaincalResults:
        """
        Execute differential gain calibration heuristics and return Results
        object that includes final caltables.

        Returns:
            DiffGaincalResults instance.
        """
        # Initialize results.
        result = DiffGaincalResults(vis=self.inputs.vis)

        # Compute phase solutions for the diffgain reference intent.
        LOG.info('Computing phase gain table for the diffgain reference intent.')
        result.ref_phase_result, result.spwmaps = self._do_phasecal_for_diffgain_reference()

        # Compute phase solutions for the diffgain on-source spectral windows.
        LOG.info('Computing phase gain table for the diffgain on-source intent.')
        dg_src_phase_results = self._do_phasecal_for_diffgain_onsource()
        # Adopt resulting CalApplication(s) and QA message into final result.
        if dg_src_phase_results is not None:
            result.pool.extend(dg_src_phase_results.pool)
            result.qa_message = dg_src_phase_results.qa_message

        # Compute residual phase offsets for the diffgain on-source intent, for
        # diagnostic plots in the weblog.
        LOG.info('Computing residual phase offsets for the diffgain on-source intent.')
        result.residual_phase_result = self._do_phasecal_for_diffgain_residual_offsets()

        return result

    def analyse(self, result: DiffGaincalResults) -> DiffGaincalResults:
        """
        Analyze the DiffGaincalResults: check that all caltables from
        CalApplications exist on disk.

        Args:
            result: DiffGaincalResults instance.

        Returns:
            DiffGaincalResults instance.
        """
        # Check that the caltables were all generated.
        on_disk = [ca for ca in result.pool if ca.exists()]
        result.final[:] = on_disk

        missing = [ca for ca in result.pool if ca not in on_disk]
        result.error.clear()
        result.error.update(missing)

        return result

    def _assess_if_spw_combination_is_necessary(self, intent: str, spw: list[int], force_for_spwmapmodes: list[str],
                                                scan_groups: list[str] | None = None) -> bool:
        """
        Assess whether spectral window combination is necessary based on
        `hm_spwmapmode`, the SpwMapping for given intent, and/or whether SpWs
        would be missing in final gaintable.

        Args:
            intent: Intent to assess.
            spw: List of Spectral Window IDs to assess.
            force_for_spwmapmodes: List of values for `hm_spwmapmode` for which
                to force SpW combination.
            scan_groups: Optional, list of group(s) of scans to assess.

        Returns:
            Boolean declaring whether to use SpW combination.
        """
        inputs = self.inputs

        # Force SpW combination if hm_spwmapmode matches any of the specified
        # "forced" modes, which can include any of the allowed values for the
        # input parameter hm_spwmapmode *except* for hm_spwmapmode='auto'
        # ('auto' is separately evaluated below).
        if inputs.hm_spwmapmode in force_for_spwmapmodes:
            return True

        # For automatic hm_spwmapmode, check whether SpW combination is
        # required based on SpwMapping or in case the resulting caltable would
        # contain any missing/fully flagged SpWs.
        combine_spw = False
        if inputs.hm_spwmapmode == 'auto':
            # Assess the SpwMapping for diffgain calibrator for whether SpW
            # combination is required.
            for field in inputs.ms.get_fields(intent=intent):
                combine_spw = self._assess_spw_combine_based_on_spwmapping_and_snr(
                    intent, field.name, spw, scan_groups=scan_groups)
                # Assessment is made in a loop over all diffgain calibrator
                # fields, and as soon as SpW combination is needed for one, it
                # is required for all. In practice, it is currently expected
                # that band-to-band datasets only have a single diffgain
                # calibrator. Should this change in operations in the future,
                # then it should be revisited whether to apply a single SpW
                # combination strategy to all diffgain calibrators and their
                # corresponding phase calibrator sources.
                if combine_spw:
                    break

            # If no SpW combination is needed based on SpwMapping, then generate
            # a temporary (diagnostic) phase caltable without SpW combination,
            # and check whether any SpWs would be missing / fully flagged; if
            # so, then force SpW combination after all.
            if not combine_spw:
                # If provided groups of scans, then do combination over scan.
                combine = '' if scan_groups is None else 'scan'
                diag_result = self._do_phasecal(intent=intent, spw=spw, combine=combine)
                bad_spws = self._assess_spws_in_gaintable(diag_result, combine_spw, spw, scan_groups=scan_groups)
                if bad_spws:
                    combine_spw = True

        return combine_spw

    def _assess_spw_combine_based_on_spwmapping_and_snr(self, intent: str, field: str, spwids: list[int],
                                                        scan_groups: list[str] | None = None) -> bool:
        """
        Assess whether spectral window combination is necessary based on
        spectral window mapping and scaling estimated SNR (for solint) to full
        aggregate exposure time of scans.

        Args:
            intent: Intent to assess; should be DIFFGAINREF or DIFFGAINSRC.
            field: Field to assess.
            spwids: Spectral window IDs to assess SNR for in case SpwMapping
                specified to use spectral window combination.
            scan_groups: Optional: list of scan groups to assess.

        Returns:
            Boolean declaring whether to use spectral window combination.
        """
        # Try to retrieve SpW mapping info from MS for requested intent and
        # field.
        spwmapping: SpwMapping | None = self.inputs.ms.spwmaps.get((intent, field), None)

        # If no SpW mapping info is available, then the default is to use no SpW
        # combination.
        if spwmapping is None:
            return False

        # Otherwise, proceed to assess the info in the SpW mapping info to
        # determine whether to use SpW combination:

        # Track whether SpWs were re-mapped or combined.
        spws_mapped_or_combined = False
        # If SpWs are combined, then use input spectral windows for SNR
        # assessment.
        if spwmapping.combine:
            spws_mapped_or_combined = True
            spwids_mapped = spwids
            LOG.info(f"{self.inputs.ms.basename}: SpwMapping for intent {intent} is using spectral window combination,"
                     f" re-assessing estimated SNR based on full exposure times of corresponding scans.")
        # Otherwise, check if any SpWs are re-mapped, and select those SpWs
        # for SNR assessment.
        else:
            spwids_mapped = [idx for idx, spwid in enumerate(spwmapping.spwmap) if idx != spwid]
            if spwids_mapped:
                spws_mapped_or_combined = True
                LOG.info(f"{self.inputs.ms.basename}: SpwMapping for intent {intent} is using spectral window mapping,"
                         f" re-assessing estimated SNR based on full exposure times of corresponding scans.")

        # If SpWs are to be re-mapped or combined, proceed to assess if SpW
        # combination would still be needed after scaling estimated SNR from
        # solint to full exposure time (scan time * nr. scans).
        if spws_mapped_or_combined:
            # Retrieve scan and integration time.
            scantime, inttime = self._get_scan_and_integration_time(self.inputs.ms, intent, field, spwids)

            # Retrieve solution interval time in seconds from SpW mapping.
            if spwmapping.solint == 'int':
                solint = inttime
            else:
                # Assume solint was recorded as string in units of seconds,
                # convert to float with CASA quanta.
                solint = casa_tools.quanta.quantity(spwmapping.solint)['value']

            # Get the number of scans from groups of scans if provided, but
            # otherwise assume this to be a single scan.
            # It is assumed that the band-to-band observation uses the same
            # number of scans in each scan group, so the first scan group is
            # taken as representative of how long a scan group should be.
            nr_scans = len(scan_groups[0]) if scan_groups else 1

            # Compute SNR scale factor, to scale estimated SNR for current
            # solint to expected SNR for exposure time.
            snr_scale_factor = np.sqrt(scantime * nr_scans / solint)

            # Loop over SpWs in SNR info and check each re-mapped/combined
            # SpW whether the scaled estimated SNR would (still) be below
            # the minimum required SNR threshold.
            spwids_mapped = [str(s) for s in spwids_mapped]
            for spwid, snr in spwmapping.snr_info:
                if spwid in spwids_mapped and snr * snr_scale_factor < spwmapping.snr_threshold_used:
                    LOG.info(f"{self.inputs.ms.basename}, intent {intent}: estimated SNR is below threshold for good"
                             f" solutions ({spwmapping.snr_threshold_used}) for at least one of the re-mapped"
                             f" / combined SpWs, will use SpW combination.")
                    return True

        # If this is reached, then it is expected that no SpW combination is
        # necessary based on info in SpwMapping.
        return False

    def _assess_spws_in_gaintable(self, gaincal_results: common.GaincalResults, combine_spw: bool, spw: list[int],
                                  scan_groups: list[str] | None = None) -> str:
        """
        If no SpW combination was expected to be used, then this method assesses
        the resulting temporary phase caltable for missing SpWs, fully flagged
        SpWs, and/or SpWs with large fraction of flagged scans, and returns
        these as a single QA message. If this message is not empty, then SpW
        combination is deemed necessary after all.

        Args:
            gaincal_results: List of gaincal worker task results representing
                the temporary phase caltable.
            combine_spw: boolean declaring whether SpW combination is to be used.
            spw: SpW IDs to consider.
            scan_groups: Groups of scans to consider (impacts nr. of scan
                solutions expected in caltable).

        Returns:
            String message described what SpWs in temporary caltable have issues.
        """
        # If SpW combination was already required, return early; no need to
        # assess whether flagged/missing data in gaintable would necessitate SpW
        # combination.
        if combine_spw:
            return ''

        inputs = self.inputs

        # Retrieve caltable and which intent it was derived for.
        caltable = gaincal_results.final[0].gaintable
        intent = gaincal_results.inputs['intent']

        # Retrieve SpW ID, scan, and flagging columns from the caltable.
        with casa_tools.TableReader(caltable) as table:
            tbl_spwids = table.getcol("SPECTRAL_WINDOW_ID")
            tbl_flags = table.getcol("FLAG")
            tbl_scanids = table.getcol("SCAN_NUMBER")

        # Proceed with 3 separate tests, keeping track of what SpWs are missing,
        # or have too few scan solutions, or too much data flagged.
        bad_spws = []

        # First check if all requested SpWs are present in the gaintable.
        missing_spwids = ','.join(str(s) for s in spw if s not in tbl_spwids)
        if missing_spwids:
            LOG.info(f"{caltable}: missing solutions for SpW(s) {missing_spwids}.")
            bad_spws.append(f"SpW(s) {missing_spwids} have no solutions.")

        # Secondly, check if the number of scan solutions in the caltable is
        # significantly lower (set by threshold parameters) than the expected
        # nr. of scan solutions, which can happen if scans are entirely flagged
        # in prior stages.
        #
        # To do so, first determine number of scan solutions expected in
        # caltable. If no scan groups were provided, then expect 1 solution per
        # scan; otherwise expect 1 solution per group (combining over scan).
        if scan_groups is None:
            n_exp_scan_solns = len(self.inputs.ms.get_scans(scan_intent=intent))
        else:
            n_exp_scan_solns = len(scan_groups)
        # And then determine for each SpW ID whether the nr. of scan solutions
        # compared to expected number is acceptable.
        spw_with_too_many_missing_scans = []
        for uniq_spwid in sorted(set(tbl_spwids)):
            # Determine unique scans for current SpW.
            scanids_for_spwid = {tbl_scanids[idx] for idx, spwid in enumerate(tbl_spwids) if spwid == uniq_spwid}

            # Compute fraction of missing scan solutions in table.
            missing_scan_ratio = 1.0 - float(len(scanids_for_spwid)) / n_exp_scan_solns

            # If fraction of missing scans exceeds the limit, then mark this SpW
            # as bad.
            if missing_scan_ratio > inputs.missing_scans_frac_limit:
                spw_with_too_many_missing_scans.append(uniq_spwid)

        # If any SpW has too many missing scans:
        if spw_with_too_many_missing_scans:
            bad_spws.append(f"SpW(s) {','.join(str(s) for s in spw_with_too_many_missing_scans)} have too many missing"
                            f" scans.")

        # Thirdly, assess for each SpW whether the fraction of flagged data is
        # above the maximum threshold.
        spw_with_too_much_flagging = []
        for uniq_spwid in sorted(set(tbl_spwids)):
            # Get indices in caltable data corresponding to current SpW.
            idx_spw = np.where(tbl_spwids == uniq_spwid)[0]

            # Get number of correlations (polarizations) for this SpW.
            corr_type = commonhelpermethods.get_corr_products(inputs.ms, uniq_spwid)
            ncorrs = len(corr_type)

            # For single-polarization data, the caltable is expected to still
            # contain at least 2 columns, so identify which polarization index
            # to use. For multi-pol data, assess all polarizations.
            if ncorrs == 1:
                pol_to_assess = [commonhelpermethods.get_pol_id(inputs.ms, uniq_spwid, corr_type[0])]
            else:
                pol_to_assess = list(range(len(tbl_flags)))

            # Separately assess each polarization, but as soon as 1 pol has too
            # much flagged data, then consider SpW bad.
            for idx_pol in pol_to_assess:
                # Compute fraction of flagged rows for current polarization and
                # SpW. Numpy treats True as 1 and False as 0, so can use mean.
                flag_ratio = np.mean(tbl_flags[idx_pol, 0, idx_spw])
                # If fraction of flagged data in even just one polarization
                # exceeds the limit, then mark this SpW as bad, and continue
                # with next SpW.
                if flag_ratio > inputs.flagging_frac_limit:
                    spw_with_too_much_flagging.append(uniq_spwid)
                    break

        # If any SpW has too much flagged data:
        if spw_with_too_much_flagging:
            bad_spws.append(f"SpW(s) {','.join(str(s) for s in spw_with_too_much_flagging)} have too high fraction of"
                            f" flagged data.")

        # Return as single string.
        bad_spws_message = ' '.join(bad_spws)
        return bad_spws_message

    def _do_gaincal(self, intent: str, spw: str, combine: str | None = None, caltable: str | None = None,
                    scan: str | None = None, append: bool = False) -> common.GaincalResults:
        """
        Local method to call the G-type gaincal worker task, with pre-defined
        values for parameters that are shared among all gaincal steps in this
        task.

        Args:
            intent: intent selection to use.
            spw: spectral windows to use.
            combine: axis to combine solutions over.
            caltable: name of caltable to use.
            scan: scan selection to use.
            append: boolean whether to append to existing caltable.

        Returns:
            GaincalResults
        """
        task_args = {
            'output_dir': self.inputs.output_dir,
            'vis': self.inputs.vis,
            'caltable': caltable,
            'intent': intent,
            'spw': spw,
            'scan': scan,
            'combine': combine,
            'solint': 'inf',
            'calmode': 'p',
            'minsnr': 3.0,
            'refantmode': 'strict',
            'append': append,
        }
        task_inputs = gtypegaincal.GTypeGaincalInputs(self.inputs.context, **task_args)
        task = gtypegaincal.GTypeGaincal(task_inputs)
        result = self._executor.execute(task)

        return result

    def _do_phasecal(self, intent: str, spw: list[int], combine: str | None = None) -> common.GaincalResults:
        """
        Local method to perform phase gaincal with pre-defined values for
        parameters shared among all gaincal steps in this task.

        If combination over scan is required, then this method identifies the
        scan groups and calls gaincal for each scan group, ensuring solutions
        are appended to the same final caltable.

        Args:
            intent: intent selection to use.
            spw: spectral windows to use.
            combine: axis to combine solutions over.

        Returns:
            GaincalResults
        """
        # SpW IDs as string for CASA gaincal.
        spwids_str = ','.join(str(s) for s in spw)

        # If combine is not specified or not combining over scans, then perform
        # single gaincal for given intent, spw, and combine.
        if combine is None or 'scan' not in combine:
            result = self._do_gaincal(intent=intent, spw=spwids_str, combine=combine)
        # Otherwise, perform separate gaincal for each scan group:
        else:
            # Determine scan groups for intent.
            scan_groups = self._get_scan_groups(intent=intent)

            # Run gaincal for the first scan group.
            result = self._do_gaincal(intent=intent, spw=spwids_str, combine=combine, scan=scan_groups[0])

            # Run gaincal for any additional scan groups, appending to the initial caltable.
            if len(scan_groups) > 1:
                caltable = result.inputs['caltable']
                for scan_group in scan_groups[1:]:
                    self._do_gaincal(intent=intent, spw=spwids_str, combine=combine, caltable=caltable, scan=scan_group,
                                     append=True)

        return result

    def _do_phasecal_for_diffgain_reference(self) -> tuple[common.GaincalResults, dict[IntentField, SpwMapping]]:
        """
        Compute phase gain solutions for the diffgain reference intent and
        register the resulting caltable in the local task context to be applied
        to the diffgain on-source intent.

        Returns:
            2-tuple containing:
            * GaincalResults for diffgain reference.
            * Updated SpW mapping dictionary; can be empty if no updates were necessary.
        """
        intent = 'DIFFGAINREF'

        # Select which spectral windows to act on.
        spwids = [spw.id for spw in self.inputs.ms.get_spectral_windows(intent=intent)]

        # Assess if SpW combination is necessary.
        combine_spw = self._assess_if_spw_combination_is_necessary(
            intent, spwids, force_for_spwmapmodes=['all', 'both', 'reference'])

        # With choice made of whether SpW combination is necessary, now run
        # phase calibration for the diffgain reference intent scans.
        combine = 'spw' if combine_spw else ''
        phasecal_result = self._do_phasecal(intent=intent, spw=spwids, combine=combine)

        # Check phase caltable for missing / fully flagged SpW, turn into QA
        # message, and attach message to phase GaincalResults.
        phasecal_result.qa_message = self._assess_spws_in_gaintable(phasecal_result, combine_spw, spwids)

        # Update SpW mapping for phase calibrator based on whether SpW
        # combination is necessary for the diffgain reference.
        updated_spwmaps = self._update_spwmap_for_phase(self.inputs.ms, combine_spw)

        # If a caltable was created, then create a modified CalApplication to
        # correctly register the caltable.
        if phasecal_result.pool:
            # Retrieve the diffgain spectral windows, and create SpW mapping to
            # re-map diffgain on-source SpWs to diffgain reference SpWs.
            dg_refspws = self.inputs.ms.get_spectral_windows(intent='DIFFGAINREF')
            dg_srcspws = self.inputs.ms.get_spectral_windows(intent='DIFFGAINSRC')
            dg_spwmap = update_spwmap_for_band_to_band([], dg_refspws, dg_srcspws, combine_spw)

            # Define CalApplication overrides to specify how the diffgain
            # reference phase solutions should be registered in the callibrary.
            # Note: solutions derived for the diffgain reference intent are
            # registered here to be applied to the diffgain on-source intent and
            # SpWs with a corresponding SpW mapping.
            calapp_overrides = {
                'calwt': False,
                'intent': 'DIFFGAINSRC',
                'interp': 'linearPD,linear',
                'spw': ','.join(str(spw.id) for spw in dg_srcspws),
                'spwmap': dg_spwmap,
            }

            # There should be only 1 caltable, so replace the CalApp for that
            # one.
            modified_calapp = callibrary.copy_calapplication(phasecal_result.pool[0], **calapp_overrides)
            phasecal_result.pool[0] = modified_calapp
            phasecal_result.final[0] = modified_calapp

            # Register these diffgain reference phase solutions into local
            # context to ensure that these are used in pre-apply when computing
            # phase solutions for the diffgain on-source intent.
            phasecal_result.accept(self.inputs.context)

        return phasecal_result, updated_spwmaps

    def _do_phasecal_for_diffgain_onsource(self) -> common.GaincalResults | None:
        """
        Compute phase gain solutions for the diffgain on-source intent. Gain
        solutions are created separately for groups of scans, using
        combine='scan', and appended to a single caltable. Each scan group is
        intended to comprise scans taken closely together in time (typically
        alternated with the diffgain reference scans), and these groups are
        typically done before and after the science target scans. In practice,
        scan groups are identified as scans with IDs separated by less than 4.

        The resulting caltable is immediately registered with the callibrary in
        the local task context (to ensure pre-apply in the subsequent
        computation of residual offset). For final acceptance of this caltable
        in the top-level callibrary, the CalApplication is updated to ensure the
        resulting caltable will be applied to the science target or check
        source.

        Returns:
            GaincalResults for the diffgain on-source phase solutions caltable,
            or None if no diffgain scan groups are identified.
        """
        intent = 'DIFFGAINSRC'

        # Determine scan groups for diffgain on-source intent. Exit early if no
        # scan groups could be identified.
        scan_groups = self._get_scan_groups(intent=intent)
        if not scan_groups:
            LOG.warning(f"{self.inputs.ms.basename}: no scan groups found for diffgain on-source intent.")
            return None

        # Select which spectral windows to act on.
        spwids = [spw.id for spw in self.inputs.ms.get_spectral_windows(intent=intent)]

        # Assess if SpW combination is necessary.
        combine_spw = self._assess_if_spw_combination_is_necessary(
            intent, spwids, force_for_spwmapmodes=['all', 'offset'], scan_groups=scan_groups)

        # With choice made of whether SpW combination is necessary, now run
        # phase calibration for the diffgain on-source intent scans. Note, for
        # the diffgain on-source intent, solves are done separately per-scan,
        # using combination over the scan.
        combine = 'scan,spw' if combine_spw else 'scan'
        phasecal_result = self._do_phasecal(intent=intent, spw=spwids, combine=combine)

        # Check phase caltable for missing / fully flagged SpW, turn into QA
        # message, and attach message to phase GaincalResults.
        phasecal_result.qa_message = self._assess_spws_in_gaintable(phasecal_result, combine_spw, spwids,
                                                                    scan_groups=scan_groups)

        # If a caltable was created, then create a modified CalApplication to
        # correctly register the caltable.
        if phasecal_result.pool:
            # If SpW combination was used for the diffgain on-source, then
            # compute a corresponding SpW map.
            if combine_spw:
                dg_srcspws = self.inputs.ms.get_spectral_windows(intent=intent)
                dg_spwmap = combine_spwmap(dg_srcspws)
            else:
                dg_spwmap = []
                
            # Prior to registering this caltable into the local context, set
            # overrides in the CalApplication:
            calapp_overrides = {
                'calwt': False,
                'intent': intent,
                'spwmap': dg_spwmap,
            }
            modified_calapp = callibrary.copy_calapplication(phasecal_result.pool[0], **calapp_overrides)
            phasecal_result.pool[0] = modified_calapp
            phasecal_result.final[0] = modified_calapp

            # Register the diffgain on-source phase solutions into local context
            # to ensure that these are used in pre-apply when computing the
            # residual phase offsets (diagnostic) caltable.
            phasecal_result.accept(self.inputs.context)

            # Update the CalApplication again, this time to ensure this diffgain
            # phase offsets caltable will be applied to the science target
            # and/or check source.
            calapp_overrides = {
                'calwt': False,
                'intent': 'TARGET,CHECK',
                'spwmap': dg_spwmap,
            }
            modified_calapp = callibrary.copy_calapplication(phasecal_result.pool[0], **calapp_overrides)
            phasecal_result.pool[0] = modified_calapp
            phasecal_result.final[0] = modified_calapp

        return phasecal_result

    def _do_phasecal_for_diffgain_residual_offsets(self) -> common.GaincalResults:
        """
        Compute residual phase offsets caltable for the diffgain on-source intent.

        Returns:
            GaincalResults for the diffgain on-source residual phase solutions
            caltable.
        """
        intent = 'DIFFGAINSRC'

        # Select which spectral windows to act on.
        spwids = [spw.id for spw in self.inputs.ms.get_spectral_windows(intent=intent)]

        # Assess if SpW combination is necessary.
        combine_spw = self._assess_if_spw_combination_is_necessary(
            intent, spwids, force_for_spwmapmodes=['all', 'both', 'residual'])

        # With choice made of whether SpW combination is necessary, now run
        # phase calibration for the diffgain on-source intent scans, with the
        # phase solutions for diffgain on-source intent in pre-apply, to assess
        # the residual phase offsets.
        combine = 'spw' if combine_spw else ''
        phasecal_result = self._do_phasecal(intent=intent, spw=spwids, combine=combine)

        # Check phase caltable for missing / fully flagged SpW, turn into QA
        # message, and attach message to phase GaincalResults.
        phasecal_result.qa_message = self._assess_spws_in_gaintable(phasecal_result, combine_spw, spwids)

        return phasecal_result

    def _get_scan_groups(self, intent: str) -> list[str]:
        """
        Return list of scan groups associated with given intent, where each
        group are scans separated by less than 4 in ID.

        E.g., if the scans for given intent are:
          '5,7,9,11,79,81,83'
        Then this will return:
          ['5,7,9,11', '79,81,83']

        Returns:
            List of groups of scans.
        """
        # Get IDs of DIFFGAIN scans for given intent.
        dg_scanids = sorted(scan.id for scan in self.inputs.ms.get_scans(scan_intent=intent))

        # Group scans separated in ID by less than 4.
        scan_groups = [','.join(map(str, group))
                       for group in np.split(dg_scanids, np.where(np.diff(dg_scanids) > 3)[0] + 1)]

        return scan_groups

    @staticmethod
    def _update_spwmap_for_phase(ms: MeasurementSet, combine_spw: bool) -> dict[IntentField, SpwMapping]:
        # If SpW combination is not necessary, then no need for updated
        # SpW mapping.
        if not combine_spw:
            return {}

        # Otherwise, check whether there exists a SpwMapping for the PHASE
        # calibrator; if this was already specifying to use SpW combination,
        # then no need for an updated SpwMapping.
        phase_spwmappings = {k: v for k, v in ms.spwmaps.items() if k.intent == 'PHASE'}
        if not phase_spwmappings or any(spwmapping.combine for spwmapping in phase_spwmappings.values()):
            return {}

        # Otherwise, proceed to create a new SpW map for the PHASE calibrator
        # that is appropriate for SpW combination.
        #
        # First create a SpW map for combining the (low frequency) diffgain
        # reference SpWs.
        dg_refspws = ms.get_spectral_windows(intent='DIFFGAINREF')
        spwmap = combine_spwmap(dg_refspws)
        # Then, update the SpW map for band-to-band, adding in the (high
        # frequency) diffgain science SpWs.
        dg_srcspws = ms.get_spectral_windows(intent='DIFFGAINSRC')
        spwmap = update_spwmap_for_band_to_band(spwmap, dg_refspws, dg_srcspws, combine=True)

        # Update the SpwMapping for the PHASE calibrators.
        for intfld, spwmapping in phase_spwmappings.items():
            # Retrieve SNR estimates for diffgain reference SpWs, compute their
            # estimated combined SNR.
            dg_refspwids = [str(s.id) for s in dg_refspws]
            combined_snr = np.linalg.norm([snr for spwid, snr in spwmapping.snr_info
                                           if spwid in dg_refspwids])
            # Create new SNR info dictionary with the combined SNR entry, and
            # add the SNR info for individual SpWs from the original SpwMapping.
            snr_info = {f"Combined ({', '.join(dg_refspwids)})": combined_snr}
            snr_info.update(spwmapping.snr_info)

            # Store as a new SpwMapping with updated values for combine, spwmap,
            # and the SNR info.
            phase_spwmappings[intfld] = spwmapping._replace(combine=True, spwmap=spwmap, snr_info=snr_info)

        return phase_spwmappings

    @staticmethod
    def _get_scan_and_integration_time(ms: MeasurementSet, intent: str, field: str, spwids: list[int]) -> tuple[float, float]:
        """
        Retrieve the scan (exposure) and integration time, in seconds, used for
        given intent and field in given measurement set.

        Args:
            ms: measurement set to use.
            intent: intent to retrieve times for.
            field: field to retrieve times for.
            spwids: spectral window ids to retrieve times for.

        Returns:
            2-Tuple containing:
            - scan (exposure) time in seconds for given ms, intent, field.
            - integration time in seconds for given ms, intent, field.
        """
        # Get scans for given intent, field, spwids.
        scans = ms.get_scans(scan_intent=intent, field=field, spw=spwids)

        # Assume that the integration time and scan time are the same for all
        # scans and all SpWs for given intent, so use the first scan and first
        # spectral window as the representative ones.
        int_time = scans[0].mean_interval(spwids[0]).total_seconds()
        scan_time = scans[0].exposure_time(spwids[0]).total_seconds()

        return scan_time, int_time
