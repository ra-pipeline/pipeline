import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.vdp as vdp
from pipeline.infrastructure import casa_tools, task_registry, utils

LOG = infrastructure.get_logger(__name__)


class AnalyzealphaResults(basetask.Results):
    def __init__(self, max_location=None, alpha_and_error=None, image_at_max=None):
        super(AnalyzealphaResults, self).__init__()
        self.pipeline_casa_task = 'Analyzealpha'
        self.max_location = max_location
        self.alpha_and_error = alpha_and_error
        self.image_at_max = image_at_max

    def merge_with_context(self, context):
        """
        See :method:`~pipeline.infrastructure.api.Results.merge_with_context`
        """
        return

    def __repr__(self):
        #return 'AnalyzealphaResults:\n\t{0}'.format(
        #    '\n\t'.join([ms.name for ms in self.mses]))
        return 'AnalyzealphaResults:'


class AnalyzealphaInputs(vdp.StandardInputs):
    def __init__(self, context, vis=None, image=None, alphafile=None, alphaerrorfile=None):
        self.context = context
        self.vis = vis
        self.image = image
        self.alphafile = alphafile
        self.alphaerrorfile = alphaerrorfile


@task_registry.set_equivalent_casa_task('hif_analyzealpha')
@task_registry.set_casa_commands_comment('Diagnostics of spectral index image.')
class Analyzealpha(basetask.StandardTaskTemplate):
    Inputs = AnalyzealphaInputs

    def prepare(self):
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
            # 
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
                # TODO possibly replace round with round_half_up in python3 pipeline
                alpha_val = image.pixelvalue(image.topixel(subim_worldcoords)['numeric'][:2].round())

            alpha_at_max = alpha_val['value']['value']
            alpha_string = '{:.3f}'.format(alpha_at_max)

            # Extract the value of that pixel from the alphaerror subimage
            with casa_tools.ImageReader(alphaerrorfile) as image:
                # TODO possibly replace round with round_half_up in python3 pipeline
                alphaerror_val = image.pixelvalue(image.topixel(subim_worldcoords)['numeric'][:2].round())
            alphaerror_at_max = alphaerror_val['value']['value']
            alphaerror_string = '{:.3f}'.format(alphaerror_at_max)

            alpha_and_error = '%s +/- %s' % (alpha_string, alphaerror_string)
            LOG.info('|* Alpha at restored max {}'.format(alpha_and_error))

        return AnalyzealphaResults(max_location=max_location, alpha_and_error=alpha_and_error, image_at_max=image_at_max)

    def analyse(self, results):
        return results

