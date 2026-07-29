from __future__ import annotations

import copy

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.sessionutils as sessionutils
import pipeline.infrastructure.vdp as vdp
from pipeline.domain import DataType
from pipeline.infrastructure import task_registry

from pipeline.hif.heuristics import findroi as heuristics

from .resultobjects import FindROIResult

LOG = infrastructure.get_logger(__name__)


class FindROIInputs(vdp.StandardInputs):
    """Inputs for the hif_findroi stage."""

    processing_data_type = [
        DataType.SELFCAL_CONTLINE_SCIENCE,
        DataType.REGCAL_CONTLINE_SCIENCE,
        DataType.REGCAL_CONTLINE_ALL,
        DataType.RAW,
    ]

    field = vdp.VisDependentProperty(default='target')
    spw = vdp.VisDependentProperty(default='')
    parallel = sessionutils.parallel_inputs_impl()

    # docstring and type hints: supplements hif_findroi
    def __init__(
        self,
        context,
        output_dir=None,
        vis=None,
        field=None,
        spw=None,
        parallel=None,
    ):
        super().__init__()
        self.context = context
        self.output_dir = output_dir
        self.vis = vis
        self.field = field
        self.spw = spw
        self.parallel = parallel


@task_registry.set_equivalent_casa_task('hif_findroi')
class FindROI(basetask.StandardTaskTemplate):
    Inputs = FindROIInputs

    is_multi_vis_task = True

    def prepare(self):
        inputs = self.inputs
        tmp_dir = heuristics.default_tmp_dir(inputs.context, inputs.output_dir)
        LOG.info('Writing hif_findroi artifacts under %s', tmp_dir)

        stage_product = heuristics.run_findroi_mpi(
            vis=inputs.vis,
            context=inputs.context,
            executor=self._executor.copy(exclude_context=True),
            field=inputs.field,
            spw=inputs.spw,
            tmp_dir=tmp_dir,
            parallel=inputs.parallel,
        )

        if stage_product is None:
            return FindROIResult(errors=['No successful hif_findroi SPW results were produced.'])

        artifacts = copy.deepcopy(stage_product.get('metadata', {}).get('artifacts', {}))
        errors = list(stage_product.get('metadata', {}).get('errors', []))
        summary = heuristics.summarize_stage_product(stage_product)
        findroi_resources = None
        if artifacts.get('findroi_products_tar'):
            findroi_resources = [artifacts['findroi_products_tar']]
        return FindROIResult(
            stage_product_path=artifacts.get('results_pickle'),
            artifacts=artifacts,
            summary=summary,
            errors=errors,
            findroi_resources=findroi_resources,
        )

    def analyse(self, result):
        return result
