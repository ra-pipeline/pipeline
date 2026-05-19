import collections
import os

import pipeline.infrastructure as infrastructure
from pipeline.h.tasks.common.displays import sky as sky

LOG = infrastructure.get_logger(__name__)

# class used to transfer image statistics through to plotting routines
ImageStats = collections.namedtuple('ImageStats', 'rms max')


class RmsimagesSummary:
    def __init__(self, context, result):
        self.context = context
        self.result = result
        # self.image_stats = image_stats

    def plot(self):
        stage_dir = os.path.join(self.context.report_dir,
                                 'stage%d' % self.result.stage_number)
        if not os.path.exists(stage_dir):
            os.mkdir(stage_dir)

        LOG.info("Making PNG RMS images for weblog")
        plot_wrappers = []
        for rmsimagename in self.result.rmsimagenames:
            plot_wrappers.extend(sky.SkyDisplay().plot_per_stokes(self.context, rmsimagename,
                                                                  reportdir=stage_dir, intent='', stokes_list=None,
                                                                  collapseFunction='mean'))

        return [p for p in plot_wrappers if p is not None]


class VlassCubeRmsimagesSummary:
    def __init__(self, context, result):
        self.context = context
        self.result = result
        self.result.stats = []

    def plot(self):
        stage_dir = os.path.join(self.context.report_dir,
                                 'stage%d' % self.result.stage_number)
        if not os.path.exists(stage_dir):
            os.mkdir(stage_dir)

        LOG.info("Making PNG RMS images for weblog")
        plot_wrappers = []

        for rmsimagename in self.result.rmsimagenames:
            plot_wrappers.extend(sky.SkyDisplay().plot_per_stokes(self.context, rmsimagename,
                                                                  reportdir=stage_dir, intent='', stokes_list=None,
                                                                  collapseFunction='mean'))
            self.result.rmsstats[rmsimagename]['virtspw'] = plot_wrappers[-1].parameters['virtspw']

        return [p for p in plot_wrappers if p is not None]
