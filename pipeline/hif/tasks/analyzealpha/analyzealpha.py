from __future__ import annotations

from typing import TYPE_CHECKING

from pipeline import infrastructure
from pipeline.infrastructure import basetask, casa_tools, task_registry, utils, vdp

if TYPE_CHECKING:
    from pipeline.infrastructure.launcher import Context
    from pipeline.infrastructure.utils.casa_types import DirectionDict

LOG = infrastructure.logging.get_logger(__name__)


class AnalyzealphaResults(basetask.Results):
    def __init__(
            self,
            max_location: str = None,
            alpha_and_error: str = None,
            image_at_max: str = None,
            zenith_angle: float = None,
            ):
        super().__init__()
        self.pipeline_casa_task = 'Analyzealpha'
        self.max_location = max_location
        self.alpha_and_error = alpha_and_error
        self.image_at_max = image_at_max
        self.zenith_angle = zenith_angle

    def merge_with_context(self, context: Context) -> None:
        """
        See :method:`~pipeline.infrastructure.api.Results.merge_with_context`
        """
        return

    def __repr__(self) -> str:
        return 'AnalyzealphaResults:'


class AnalyzealphaInputs(vdp.StandardInputs):
    # docstring and type hints: supplements hif_analyzealpha
    def __init__(
            self,
            context: Context,
            vis: list[str] = None,
            image: str = None,
            alphafile: str = None,
            alphaerrorfile: str = None,
            ):
        """Initialize Inputs.

        Args:
            context: Pipeline context object containing state information.

            image: Restored subimage

            alphafile: Input spectral index map

            alphaerrorfile: Input spectral index error map
        """
        self.context = context
        self.vis = vis
        self.image = image
        self.alphafile = alphafile
        self.alphaerrorfile = alphaerrorfile


@task_registry.set_equivalent_casa_task('hif_analyzealpha')
@task_registry.set_casa_commands_comment('Diagnostics of spectral index image.')
class Analyzealpha(basetask.StandardTaskTemplate):
    Inputs = AnalyzealphaInputs
    is_multi_vis_task = True

    def prepare(self) -> AnalyzealphaResults:
        inputs = self.inputs

        LOG.info("Analyzealpha is running.")

        imlist = self.inputs.context.subimlist.get_imlist()

        subimagefile = inputs.image
        alphafile = inputs.alphafile
        alphaerrorfile = inputs.alphaerrorfile

        # there should only be one subimage used in this task.  what if there are others in the directory?
        for imageitem in imlist:

            if not subimagefile:
                if imageitem['multiterm']:
                    subimagefile = utils.glob_ordered(imageitem['imagename'].replace('.subim', '.pbcor.tt0.subim'))[0]
                else:
                    subimagefile = utils.glob_ordered(imageitem['imagename'].replace('.subim', '.pbcor.subim'))[0]

            if not alphafile:
                alphafile = utils.glob_ordered(imlist[0]['imagename'].replace('.image.subim', '.alpha'))[0]

            if not alphaerrorfile:
                alphaerrorfile = utils.glob_ordered(imlist[0]['imagename'].replace('.image.subim', '.alpha.error'))[0]

            # Extract the value from the .alpha and .alpha.error images (for wideband continuum MTMFS with nterms>1)
            with casa_tools.ImageReader(subimagefile) as image:
                stats = image.statistics(robust=False)

                # Extract the position of the maximum from imstat return dictionary
                maxposx = stats['maxpos'][0]
                maxposy = stats['maxpos'][1]
                maxposf = stats['maxposf']
                max_location = '%s  (%i, %i)' % (maxposf, maxposx, maxposy)
                LOG.info('|* Restored max at {}'.format(max_location))

                subim_worldcoords = image.toworld(stats['maxpos'][:2], 's')

                image_val = image.pixelvalue(image.topixel(subim_worldcoords)['numeric'][:2].round())
                image_at_max = image_val['value']['value']
                image_at_max_string = '{:.4e}'.format(image_at_max)
                LOG.info('|* Restored image value at max {}'.format(image_at_max_string))

            # Extract the value of that pixel from the alpha subimage
            with casa_tools.ImageReader(alphafile) as image:
                header = image.fitsheader()
                coords = image.topixel(subim_worldcoords)['numeric'][:2]
                alpha_val = image.pixelvalue([utils.round_half_up(c) for c in coords])
                observatory = header['TELESCOP'].strip()

            alpha_at_max = alpha_val['value']['value']
            alpha_string = '{:.3f}'.format(alpha_at_max)

            # Extract the value of that pixel from the alphaerror subimage
            with casa_tools.ImageReader(alphaerrorfile) as image:
                coords = image.topixel(subim_worldcoords)['numeric'][:2]
                alphaerror_val = image.pixelvalue([utils.round_half_up(c) for c in coords])
            alphaerror_at_max = alphaerror_val['value']['value']
            alphaerror_string = '{:.3f}'.format(alphaerror_at_max)

            alpha_and_error = '%s +/- %s' % (alpha_string, alphaerror_string)
            LOG.info('|* Alpha at restored max {}'.format(alpha_and_error))

            # retrieve alpha image information
            qt = casa_tools.quanta
            ra_head = qt.quantity(header['CRVAL'][0], header['CUNIT1'])
            dec_head = qt.quantity(header['CRVAL'][1], header['CUNIT2'])

            # Create DirectionDict measure dictionary for the image center
            direction: DirectionDict = {
                'm0': ra_head,
                'm1': dec_head,
                'refer': header.get('RADESYS', 'J2000'),
                'type': 'direction'
            }

            mid_time = utils.obs_midtime(
                self.inputs.context.observing_run.start_datetime,
                self.inputs.context.observing_run.end_datetime
                )

            # Calculate zenith distance using CASA measures
            zd_rad = utils.compute_zenith_distance(
                field_direction=direction,
                epoch=mid_time,
                observatory=observatory
            )
            zenith_angle = round(qt.convert(zd_rad, 'deg')['value'], 2)
            LOG.info('|* Zenith angle of alpha image in degrees {}'.format(zenith_angle))

        return AnalyzealphaResults(max_location=max_location, alpha_and_error=alpha_and_error,
                                   image_at_max=image_at_max, zenith_angle=zenith_angle)

    def analyse(self, results: AnalyzealphaResults) -> AnalyzealphaResults:
        return results
