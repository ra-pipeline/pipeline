import collections
import copy
import os
import traceback

import numpy as np

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.sessionutils as sessionutils
import pipeline.infrastructure.vdp as vdp
from pipeline.extern.almarenorm import alma_renorm
from pipeline.infrastructure import task_registry

LOG = infrastructure.get_logger(__name__)


class RenormResults(basetask.Results):
    def __init__(self, renorm_applied, vis, apply, threshold, correctATM, spw, excludechan, corrApplied, corrColExists,
                 stats, rnstats, alltdm, atmAutoExclude, atmWarning, atmExcludeCmd, bwthreshspw, exception=None):
        super().__init__()
        self.renorm_applied = renorm_applied
        self.vis = vis
        self.apply = apply
        self.threshold = threshold
        self.correctATM = correctATM
        self.spw = spw
        self.excludechan = excludechan
        self.corrApplied = corrApplied
        self.corrColExists = corrColExists
        self.stats = stats
        self.rnstats = rnstats
        self.alltdm = alltdm
        self.atmAutoExclude = atmAutoExclude
        self.atmWarning = atmWarning
        self.atmExcludeCmd = atmExcludeCmd
        self.bwthreshspw = bwthreshspw
        self.exception = exception

    def merge_with_context(self, context):
        """
        See :method:`~pipeline.infrastructure.api.Results.merge_with_context`
        """
        return

    def __repr__(self):
        return (f'RenormResults:\n'
                f'\trenorm_applied={self.renorm_applied}\n'
                f'\tvis={self.vis}\n'
                f'\tapply={self.apply}\n'
                f'\tthreshold={self.threshold}\n'
                f'\tcorrectATM={self.correctATM}\n'
                f'\tspw={self.spw}\n'
                f'\texcludechan={self.excludechan}\n'
                f'\talltdm={self.alltdm}\n'
                f'\tstats={self.stats}\n'
                f'\tatmAutoExclude={self.atmAutoExclude}\n'
                f'\tbwthreshspw={self.bwthreshspw}\n')


class RenormInputs(vdp.StandardInputs):
    apply = vdp.VisDependentProperty(default=False)
    threshold = vdp.VisDependentProperty(default=1.02)
    correctATM = vdp.VisDependentProperty(default=False)
    spw = vdp.VisDependentProperty(default='')
    excludechan = vdp.VisDependentProperty(default={})
    atm_auto_exclude = vdp.VisDependentProperty(default=False)
    bwthreshspw = vdp.VisDependentProperty(default={})

    parallel = sessionutils.parallel_inputs_impl()

    def __init__(self, context, vis=None, apply=None, threshold=None, correctATM=None, spw=None,
                 excludechan=None, atm_auto_exclude=None, bwthreshspw=None, parallel=None):
        super().__init__()
        self.context = context
        self.vis = vis
        self.apply = apply
        self.threshold = threshold
        self.correctATM = correctATM
        self.spw = spw
        self.excludechan = excludechan
        self.atm_auto_exclude = atm_auto_exclude
        self.bwthreshspw = bwthreshspw
        self.parallel = parallel


class SerialRenorm(basetask.StandardTaskTemplate):
    Inputs = RenormInputs

    def prepare(self):
        inp = self.inputs

        # Issue warning if current MS contains Band 9 and/or 10 data.
        bands_in_ms = {spw.band for spw in inp.ms.get_spectral_windows()}
        for band in ('ALMA Band 9', 'ALMA Band 10'):
            if band in bands_in_ms:
                LOG.warning(f"{inp.ms.basename}: running hifa_renorm on {band} (DSB) data.")

        # PIPE-2150: safely create the "RN_plots" directory before calling the renormalization external code to prevent
        # potential race condition when checking/examining the directory existence in the tier0 setup.
        # This workaround might be removed after the changes from PIPE-2151
        os.makedirs('RN_plots', exist_ok=True)

        # Create inputs for the call to the ALMA renorm function.
        alma_renorm_inputs = {
            'vis': inp.vis,
            'spw': [int(x) for x in inp.spw.split(',') if x],  # alma_renorm expects SpWs as list of integers
            'apply': inp.apply,
            'threshold': inp.threshold,
            'excludechan': copy.deepcopy(inp.excludechan),  # create copy, PIPE-1612.
            'correct_atm': inp.correctATM,
            'atm_auto_exclude': inp.atm_auto_exclude,
            'bwthreshspw': inp.bwthreshspw,
        }

        # Call the ALMA renormalization function and collect its output in task
        # result.
        try:
            LOG.info("Calling the renormalization heuristic function.")
            alltdm, atmExcludeCmd, atmWarning, corrApplied, corrColExists, renorm_applied, rnstats, stats = \
                alma_renorm(**alma_renorm_inputs)
            rnstats_light = self._get_rnstats_light(stats, rnstats)

            result = RenormResults(renorm_applied, inp.vis, inp.apply, inp.threshold, inp.correctATM, inp.spw,
                                   inp.excludechan, corrApplied, corrColExists, stats, rnstats_light, alltdm,
                                   inp.atm_auto_exclude, atmWarning, atmExcludeCmd, inp.bwthreshspw)
        except Exception as e:
            LOG.error('Failure in running renormalization heuristic: {}'.format(e))
            LOG.error(traceback.format_exc())
            result = RenormResults(False, inp.vis, inp.apply, inp.threshold, inp.correctATM, inp.spw,
                                   inp.excludechan, False, False, {}, {}, True, inp.atm_auto_exclude, {}, {}, {}, e)

        return result

    def analyse(self, results):
        return results

    def _get_rnstats_light(self, stats, rnstats):
        """
        Extracts and summarizes the presence of NaN values in rnstats.

        Args:
            stats (dict): Dictionary containing statistics for each source and spectral window.
            rnstats (dict): Dictionary containing numerical values for each source and spectral window.

        Returns:
            dict: A dictionary indicating whether any NaN values are present for each source and spectral window.
                If the source or spectral window is not present in rnstats, it is marked as invalid (True).
        """
        rnstats_light = {'invalid': collections.defaultdict(dict)}

        for source, spws in stats.items():
            for spw in spws:
                rnstats_light['invalid'][source][spw] = np.isnan(rnstats['N'].get(source, {}).get(spw, np.nan)).any()

        return rnstats_light

@task_registry.set_equivalent_casa_task('hifa_renorm')
@task_registry.set_casa_commands_comment('Renormalize data affected by strong line emission.')
class Renorm(sessionutils.ParallelTemplate):
    Inputs = RenormInputs
    Task = SerialRenorm
