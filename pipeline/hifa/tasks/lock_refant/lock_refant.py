from __future__ import annotations

from typing import TYPE_CHECKING

import os
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.callibrary as callibrary
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.vdp as vdp
from pipeline.infrastructure import task_registry

if TYPE_CHECKING:
    from pipeline.infrastructure.launcher import Context

__all__ = [
    'LockRefAnt',
    'LockRefAntInputs',
    'LockRefAntResults',
]

LOG = infrastructure.logging.get_logger(__name__)


class LockRefAntInputs(vdp.StandardInputs):
    # PIPE-3016 the default use case of lock_refant is within the polcal
    # recipe prior to second loop of calibration stages. Before that second loop,
    # the spwphaseup caltables need to be unregistered. This will be
    # unregistered by default (i.e. unregister_spwphaseup = True).
    unregister_spwphaseup = vdp.VisDependentProperty(default=True)

    def to_casa_args(self):
        # refant does not use CASA tasks
        raise NotImplementedError

    # docstring and type hints: supplements hifa_lock_refant
    def __init__(self, context, output_dir=None, vis=None, unregister_spwphaseup=None):
        """Initialize Inputs.

        Args:
            context: Pipeline context object containing state information.

            vis: List of input MeasurementSets. Defaults to the list of
                MeasurementSets specified in the pipeline context.

                Example: ``vis=['ngc5921.ms']``

            output_dir: Output directory.
                Defaults to None, which corresponds to the current working directory.

            unregister_spwphaseup: Boolean option to remove any caltable created by
                any hifa_spwphaseup stage run prior to lock_refant.
                In the current Pipeline use case, hifa_spwphaseup makes phase
                offset tables (per spectral spec) to align spws.
                Defaults to True

        """
        self.context = context
        self.vis = vis
        self.output_dir = output_dir
        self.unregister_spwphaseup = unregister_spwphaseup

        
class LockRefAntResults(basetask.Results):
    def __init__(self, vis: str, unregister_spwphaseup: bool):
        super().__init__()
        self._vis = vis
        self.unregister_spwphaseup = unregister_spwphaseup

    def merge_with_context(self, context: Context):
        if self._vis is None:
            LOG.error('No results to merge')
            return

        ms = context.observing_run.get_ms(name=self._vis)
        if ms:
            LOG.debug('Locking refant for %s', ms.basename)
            ms.reference_antenna_locked = True

        # PIPE-3016: if requested (True by default), unregister previous
        # hifa_spwphaseup caltables from the context upon completion of
        # the hifa_lock_refant stage.
        if self.unregister_spwphaseup:
            # Identify the MS to process
            ms_basename = os.path.basename(str(self._vis))

            # predicate function that triggers when the spwphaseup caltable is
            # detected for this MS
            def spwphaseup_matcher(calto: callibrary.CalToArgs, calfrom: callibrary.CalFrom) -> bool:
                calto_vis = {os.path.basename(v) for v in calto.vis}
                do_delete = 'hifa_spwphaseup' in calfrom.gaintable and ms_basename in calto_vis
                if do_delete:
                    LOG.info('Unregistering previous spwphaseup offset table for %s', ms_basename)
                return do_delete

            context.callibrary.unregister_calibrations(spwphaseup_matcher)


    def __str__(self):
        return 'Lock reference antenna results: refant list locked'

    def __repr__(self):
        return f'LockRefAntResults({self._vis})'


@task_registry.set_equivalent_casa_task('hifa_lock_refant')
@task_registry.set_casa_commands_comment(
    'The reference antenna list for all measurement sets is locked to prevent further modification'
)
class LockRefAnt(basetask.StandardTaskTemplate):
    Inputs = LockRefAntInputs

    def prepare(self, **parameters):
        return LockRefAntResults(self.inputs.vis, self.inputs.unregister_spwphaseup)

    def analyse(self, results):
        return results
