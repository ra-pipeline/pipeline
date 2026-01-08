from __future__ import annotations

import copy
from typing import Optional, Union

import numpy as np

import pipeline.domain.measures as measures
import pipeline.infrastructure as infrastructure
from pipeline.infrastructure import casa_tasks

from .imageparams_vlass_single_epoch_continuum import ImageParamsHeuristicsVlassSeContMosaic

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.infrastructure.vdp import StandardInputs
    from pipeline.hif.tasks.makeimlist import CleanTarget


LOG = infrastructure.get_logger(__name__)


class ImageParamsHeuristicsVlassSeCube(ImageParamsHeuristicsVlassSeContMosaic):

    def __init__(self, vislist, spw, observing_run, imagename_prefix='', proj_params=None, contfile=None, linesfile=None, imaging_params={}, processing_intents={}):
        super().__init__(vislist, spw, observing_run, imagename_prefix, proj_params, contfile, linesfile, imaging_params, processing_intents)
        self.imaging_mode = 'VLASS-SE-CUBE'
        self.vlass_stage = 3

    def reffreq(self, deconvolver: Optional[str]=None, specmode: Optional[str]=None, spwsel: Optional[dict]=None) -> Optional[str]:
        """Tclean reffreq parameter heuristics.

        tclean(reffreq=None) will automatically calculate the referenece frequency using the mean frequency of the selected spws.
        For VLASS-SE-CONT, this is hardcoded to '3.0GHz'.
        For VLASS-SE-CUBE, PIPE-1401 requests this to be explicitly set as the central freq derived from individual SPW groups.
        None is returned here as a fallback and hif_editimlist() will set actual values.
        """
        return None

    def meanfreq_spwgroup(self, spw_selection):
        """Calculate the mean frequency of a spw group (specified by a selection string, e.g. '2,3,4')."""
        vis = self.vislist[0]
        ms = self.observing_run.get_ms(vis)
        spwid_list = [int(spw) for spw in spw_selection.split(',')]

        spwfreq_list = []
        for spwid in spwid_list:
            real_spwid = self.observing_run.virtual2real_spw_id(spwid, ms)
            spw = ms.get_spectral_window(real_spwid)
            spwfreq_list.append(float(spw.mean_frequency.to_units(measures.FrequencyUnits.GIGAHERTZ)))
        meanfreq_value = np.mean(spwfreq_list)

        return str(meanfreq_value)+'GHz'

    def _flagpct_spwgroup(self, results_list: Union[list, None] = None, spw_selection=None):
        """Get the flag percentage of a spw group (specified by a selection string, e.g. '2,3,4').

        Note: Quick check using cached results from hifv_flagtargetsdata() (PIPE-1401).
        For more comprehensive validation, use ImageParamsHeuristics.has_data() (see PIPE-557).
        Deprecated since PIPE-2641 - scheduled for removal.
        """
        flagpct = None

        # Catch exception as the success of result parsing is not guaranteed.
        try:
            if results_list and type(results_list) is list:
                for result in results_list:
                    result_meta = result.read()
                    if hasattr(result_meta, 'pipeline_casa_task') and result_meta.pipeline_casa_task.startswith(
                        'hifv_flagtargetsdata'
                    ):
                        flagtargets_summary = [r.summaries for r in result_meta][0][-1]

            n_flagged = n_total = 0.0
            for spwid in [spw.strip() for spw in spw_selection.split(',')]:
                n_flagged += flagtargets_summary['spw'][str(spwid)]['flagged']
                n_total += flagtargets_summary['spw'][str(spwid)]['total']
            flagpct = n_flagged / n_total
        except Exception as e:
            pass

        return flagpct

    def _plane_rejection(self, imlist_entry, vlass_plane_reject_ms):
        """Decide whether to reject a spw group based on the number of high-flagging-percentage fields."""
        vis_name = self.vislist[-1]
        job = casa_tasks.flagdata(vis=vis_name, mode='summary', fieldcnt=True)
        flag_stats = job.execute()

        # PIPE-1800: for plane-rejection, we restrict the flagging stats evaluation within the
        # 1deg^2 box based on the cutout layout.
        mosaic_side_arcsec = 3600  # 1 degree
        dist = mosaic_side_arcsec / 2.0
        dist_arcsec = str(dist) + 'arcsec'

        fid_list = self.select_fields(
            offsets=dist_arcsec,
            intent='TARGET',
            phasecenter=imlist_entry['phasecenter'],
            name='0*,"0*,1*,"1*,2*,"2*,T*,"T*',
        )
        # for the existing VLASS workflow, only one MS is used, though this might change in the future.
        fid_list = fid_list[0]

        msobj = self.observing_run.get_ms(vis_name)
        field_objs = msobj.get_fields(field_id=fid_list)
        n_spwgroup = len(imlist_entry['spw'])
        n_flagged_field_spwgroup = np.zeros((len(field_objs), n_spwgroup))
        n_total_field_spwgroup = np.zeros((len(field_objs), n_spwgroup))
        scan_list = np.zeros(len(field_objs))
        fname_list = []

        for field_idx, field_obj in enumerate(field_objs):
            fname_list.append(field_obj.name)
            for spwgroup_idx, spwgroup_sel in enumerate(imlist_entry['spw']):
                n_flagged = n_total = 0.0
                spw_list = spwgroup_sel.split(',')
                for spw_str in spw_list:
                    n_flagged += flag_stats[field_obj.name]['spw'][spw_str]['flagged']
                    n_total += flag_stats[field_obj.name]['spw'][spw_str]['total']
                n_flagged_field_spwgroup[field_idx, spwgroup_idx] = n_flagged
                n_total_field_spwgroup[field_idx, spwgroup_idx] = n_total
                scan_list[field_idx] = list(flag_stats[field_obj.name]['scan'].keys())[0]

        nfield_above_flagpct = np.sum(
            n_flagged_field_spwgroup / n_total_field_spwgroup > vlass_plane_reject_ms['flagpct_thresh'], axis=0
        )
        spwgroup_reject = [False] * n_spwgroup
        for idx, nfield in enumerate(nfield_above_flagpct):
            is_spwgroup_excluded = set(imlist_entry['spw'][idx].split(',')) & set(
                vlass_plane_reject_ms['exclude_spw'].split(',')
            )
            if (
                vlass_plane_reject_ms['apply']
                and nfield >= vlass_plane_reject_ms['nfield_thresh']
                and not is_spwgroup_excluded
            ):
                spwgroup_reject[idx] = True

        vlass_flag_stats = {}
        vlass_flag_stats['spwgroup_list'] = imlist_entry['spw']
        vlass_flag_stats['scan_list'] = scan_list
        vlass_flag_stats['fname_list'] = fname_list
        vlass_flag_stats['flagpct_field_spwgroup'] = n_flagged_field_spwgroup / n_total_field_spwgroup
        vlass_flag_stats['flagpct_spwgroup'] = np.sum(n_flagged_field_spwgroup, axis=0) / np.sum(
            n_total_field_spwgroup, axis=0
        )
        vlass_flag_stats['nfield_above_flagpct'] = nfield_above_flagpct
        vlass_flag_stats['flagpct_thresh'] = vlass_plane_reject_ms['flagpct_thresh']
        vlass_flag_stats['nfield_thresh'] = vlass_plane_reject_ms['nfield_thresh']
        vlass_flag_stats['spwgroup_reject'] = spwgroup_reject

        return vlass_flag_stats

    def get_subtargets(self, cleantarget: CleanTarget, inputs: StandardInputs) -> list[CleanTarget] | None:
        """Derive sub-/child-targets from the original clean target for VLASS-SE-CUBE imaging.

        Processes the initial full-bandwidth continuum CleanTarget specification to generate per-"plane" CleanTarget
        list for the VLASS "Coarse Cube" imaging. The function derives relevant child-targets based on VLASS plane
        rejection settings and also attaches flagging statistics for downstream analysis.

        For the "coarse cube" workflow, we perform the following operations using the base CleanTarget specs:
            - Loop over individual spw groups
            - Generate corresponding per-spw(plane)-targets using modified copies of the original CleanTarget object
            as a template
            - Filter clean targets list after the VLASS-SE-CUBE plane rejection criteria is applied

        Note: The initial 'spw' from the base CleanTarget object template, i.e., imlist_entry['spw'], is expected to
        be a list here (different from norm). For VLASS-SE-CUBE, we also attach additional attributes (`misc` field)
        to CleanTarget objects which can be rendered by Mako templates later.

        Args:
            cleantarget: The original clean target object to process
            inputs: TaskInput object containing VLASS plane rejection settings

        Returns:
            List ofsub-targets
        """
        vlass_plane_reject_keys_allowed = {'apply', 'exclude_spw', 'flagpct_thresh', 'nfield_thresh'}
        vlass_plane_reject_ms = inputs.vlass_plane_reject_ms

        # Validate input keys and warn about unexpected ones
        for key in vlass_plane_reject_ms:
            if key not in vlass_plane_reject_keys_allowed:
                LOG.warning(
                    "The key %r in the 'vlass_plane_reject_ms' task input dictionary is not expected and will be "
                    'ignored.',
                    key,
                )

        vlass_flag_stats = self._plane_rejection(cleantarget, vlass_plane_reject_ms)
        cleantarget['misc_vlass'] = (cleantarget['misc_vlass'] or {}) | vlass_flag_stats

        spwgroup_reject_list = []
        imlist_entries = []

        for idx, spw in enumerate(cleantarget['spw']):
            imlist_entry_per_spwgroup = copy.deepcopy(cleantarget)
            imlist_entry_per_spwgroup['spw'] = spw
            imlist_entry_per_spwgroup['imagename'] = (
                cleantarget['imagename'] + '.spw' + spw.replace('~', '-').replace(',', '_')
            )
            imlist_entry_per_spwgroup['reffreq'] = self.meanfreq_spwgroup(spw)

            # PIPE-1800: flagpct per spw group within the 1deg^2 box
            imlist_entry_per_spwgroup['misc_vlass']['flagpct'] = vlass_flag_stats['flagpct_spwgroup'][idx]

            # PIPE-1800/PIPE-2641: flagpct_threshold is the flag percent rejection threshold over selected fields.
            # We hardcode the value to 1.0 which means we reject any spw that is completely flagged.
            # Note that this differs from vlass_plane_reject_ms['flagpct_thresh'] which is a per-field flagging
            # threshold to define "bad" fields.
            flagpct_threshold = 1.0
            if imlist_entry_per_spwgroup['misc_vlass']['flagpct'] >= flagpct_threshold:
                LOG.warning(
                    'VLASS Data for spw=%r is %.2f%% flagged, and we will skip it as an imaging target.',
                    spw,
                    imlist_entry_per_spwgroup['misc_vlass']['flagpct'] * 100,
                )
                continue

            if vlass_flag_stats['spwgroup_reject'][idx]:
                spwgroup_reject_list.append(spw)
                continue

            imlist_entries.append(imlist_entry_per_spwgroup)

        if spwgroup_reject_list:
            LOG.warning(
                'VLASS Data for spw=%r meets the plane rejection criteria: nfield>=%i with flagpct>=%.2f%%.',
                ','.join(spwgroup_reject_list),
                vlass_plane_reject_ms['nfield_thresh'],
                vlass_plane_reject_ms['flagpct_thresh'] * 100,
            )

        return imlist_entries

    def mask(
        self,
        hm_masking=None,
        rootname=None,
        iteration=None,
        mask=None,
        results_list: Union[list, None] = None,
        clean_no_mask=None,
    ) -> Union[str, list]:
        """Tier-1 mask name to be used for computing Tier-1 and Tier-2 combined mask.

            Obtain the mask name from the latest MakeImagesResult object in context.results.
            If not found, then set empty string (as base heuristics)."""
        mask_list = ''
        if results_list and type(results_list) is list:
            for result in results_list:
                result_meta = result.read()
                if hasattr(result_meta, 'pipeline_casa_task') and result_meta.pipeline_casa_task.startswith(
                        'hifv_restorepims'):
                    mask_list = [r.mask_list for r in result_meta][0]

        # Add 'pb' string as a placeholder for cleaning without mask (pbmask only, see PIPE-977). This should
        # always stand at the last place in the mask list.
        # On request for first imaging stage (selfcal image) and automatically for the final imaging stage.
        if (clean_no_mask and self.vlass_stage == 1) or self.vlass_stage == 3:
            if clean_no_mask:
                LOG.info('Cleaning without user mask is performed in pre-self calibration imaging stage '
                         '(clean_no_mask_selfcal_image=True)')
            if type(mask_list) is list:
                mask_list.append('pb')
            elif mask_list != '':  # mask is non-empty string
                mask_list = [mask_list, 'pb']
            else:
                mask_list = 'pb'

        # In case hif_makeimages result was not found or results_list was not provided
        return mask_list

    def nterms(self, spwspec) -> Union[int, None]:
        """Tclean nterms parameter heuristics."""
        return 1

    def stokes(self, intent: str = '', joint_intents: str = '') -> str:
        """Tclean stokes parameter heuristics."""
        return 'IQUV'

    def psfcutoff(self) -> float:
        """Tclean psfcutoff parameter heuristics.

        PIPE-1466: use psfcutoff=0.5 to properly fit the PSF for all spws in the VLASS Coarse Cube pipeline,
        rather than the default value of 0.35 from CASA/tclean ver6.4.1.
        """
        return 0.5
