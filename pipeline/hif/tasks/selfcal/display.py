import collections
import os

import matplotlib.pyplot as plt
import numpy as np
import shutil

import pipeline.infrastructure.logging as logging
from pipeline.h.tasks.common.displays import sky as sky
from pipeline.infrastructure.casa_tasks import CasaTasks
from pipeline.infrastructure.displays.plotstyle import matplotlibrc_formal
from pipeline.infrastructure.mpihelpers import TaskQueue
from pipeline.infrastructure.renderer import logger
from pipeline.infrastructure import casa_tools


LOG = logging.get_logger(__name__)

ct = CasaTasks()


def sanitize_string(string):
    sani_string = string.replace('-', '_').replace(' ', '_').replace('+', '_')
    sani_string = 'Target_'+sani_string
    return sani_string


class SelfcalSummary(object):
    def __init__(self, context, r, target):
        self.context = context
        self.result = r
        self.target = target
        self.stage_dir = os.path.join(self.context.report_dir,
                                      'stage%d' % self.result.stage_number)
        self.report_dir = self.context.report_dir
        self.scal_dir = target['sc_workdir']
        self.slib = target['sc_lib']
        self.field = target['field_name']
        self.band = target['sc_band']
        self.solints = target['sc_solints']

        if not os.path.exists(self.stage_dir):
            os.mkdir(self.stage_dir)
        # self.image_stats = image_stats

    def _get_ims(self):

        im_rootname = self._im_rootname()
        im_initial = im_rootname+'_initial.image.tt0'
        im_final = im_rootname+'_final.image.tt0'

        return im_initial, im_final

    def _im_rootname(self):
        return os.path.join(self.scal_dir, sanitize_string(self.field)+'_'+self.band)

    def _im_solname(self, solint):
        idx = self.solints.index(solint)
        return os.path.join(self.scal_dir, sanitize_string(self.field)+'_'+self.band+'_'+solint+'_'+str(idx))

    @matplotlibrc_formal
    def plot_qa(self, solint):
        """Generate all plots for each QA page per target/band/solint combination."""
        LOG.info("Making Selfcal QA plots for weblog")

        image_plots = []          # pre/post selfcal images
        antpos_plots = {}         # solution flagged fraction at antenna positions, keyed by MS
        phasefreq_plots = {}      # phase vs frequency per antenna, keyed by MS

        im_post = self._im_solname(solint)+'_post.image.tt0'
        im_pre = self._im_solname(solint)+'.image.tt0'
        im_post_mask = self._im_solname(solint)+'_post.mask'
        im_pre_mask = self._im_solname(solint)+'.mask'

        with casa_tools.ImageReader(im_post) as image:
            stats = image.statistics(robust=False)
            vmin = stats['min'][0]
            vmax = stats['max'][0]

        image_plots.extend(sky.SkyDisplay(exclude_desc=True, overwrite=False, figsize=(8, 6), dpi=900).plot_per_stokes(
            self.context, im_pre, reportdir=self.stage_dir, intent='', collapseFunction='mean',
            vmin=vmin, vmax=vmax,
            result_mask=im_pre_mask))
        image_plots[-1].parameters['title'] = 'Pre-Selfcal Image'
        image_plots[-1].parameters['caption'] = f'Pre-Selfcal Image<br>Solint: {solint}'
        image_plots[-1].parameters['group'] = 'Pre-/Post-Selfcal Image Comparison'

        image_plots.extend(sky.SkyDisplay(exclude_desc=True, overwrite=False, figsize=(8, 6), dpi=900).plot_per_stokes(
            self.context, im_post, reportdir=self.stage_dir, intent='', collapseFunction='mean',
            vmin=vmin, vmax=vmax,
            result_mask=im_post_mask))
        image_plots[-1].parameters['title'] = 'Post-Selfcal Image'
        image_plots[-1].parameters['caption'] = f'Post-Selfcal Image<br>Solint: {solint}'
        image_plots[-1].parameters['group'] = 'Pre-/Post-Selfcal Image Comparison'

        vislist = self.slib['vislist']
        for vis in vislist:
            # only evaluate last gaintable not the pre-apply table
            gaintable = self.slib[vis][solint]['gaintable'][-1]
            figname = os.path.join(self.stage_dir, 'plot_ants_'+gaintable+'.png')
            ms = self.context.observing_run.get_ms(vis)
            caltb_loc = os.path.join(self.scal_dir, gaintable)
            self.plot_ants_flagging_colored(figname, ms, caltb_loc)
            nflagged_sols, nsols = self.get_sols_flagged_solns(caltb_loc)
            antpos_plots[vis] = logger.Plot(figname, parameters={'nflagged_sols': nflagged_sols, 'nsols': nsols})
            antpos_plots[vis].parameters['title'] = 'Frac. Flagged Sol. Per Antenna'
            antpos_plots[vis].parameters['caption'] = f'Frac. Flagged Sol. Per Antenna<br>Solint: {solint}'
            antpos_plots[vis].parameters['group'] = 'Frac. Flagged Sol. Per Antenna'

            vis_desc = ('<a class="anchor" id="{0}_byant"></a>'
                        '<a href="#{0}_summary" class="btn btn-link btn-sm">'
                        '  <span class="glyphicon glyphicon-th-list"></span>'
                        '</a>'
                        '{0}'.format(vis))
            phasefreq_plots[vis_desc] = self._plot_gain(ms, gaintable, solint)

        return image_plots, antpos_plots, phasefreq_plots

    @staticmethod
    def get_sols_flagged_solns(gaintable):

        with casa_tools.TableReader(gaintable) as tb:
            flags = tb.getcol('FLAG').squeeze()
            nsols = flags.size
            flagged_sols = np.where(flags == True)
            nflagged_sols = flagged_sols[0].size

        return nflagged_sols, nsols

    @staticmethod
    @matplotlibrc_formal
    def plot_ants_flagging_colored(filename, ms, gaintable):
        names, offset_x, offset_y, _, _, _, fracflagged = SelfcalSummary.get_flagged_solns_per_ant(gaintable, ms)

        ants_zero_flagging = np.where(fracflagged == 0.0)
        ants_lt10pct_flagging = ((fracflagged <= 0.1) & (fracflagged > 0.0)).nonzero()
        ants_lt25pct_flagging = ((fracflagged <= 0.25) & (fracflagged > 0.10)).nonzero()
        ants_lt50pct_flagging = ((fracflagged <= 0.5) & (fracflagged > 0.25)).nonzero()
        ants_lt75pct_flagging = ((fracflagged <= 0.75) & (fracflagged > 0.5)).nonzero()
        ants_gt75pct_flagging = np.where(fracflagged > 0.75)
        ants_missing = np.isnan(fracflagged).nonzero()
        fig, ax = plt.subplots(1, 1, figsize=(8, 8))
        ax.scatter(offset_x[ants_zero_flagging[0]], offset_y[ants_zero_flagging[0]],
                   marker='o', color='green', label='No Flagging', s=120)
        ax.scatter(offset_x[ants_lt10pct_flagging[0]], offset_y[ants_lt10pct_flagging[0]],
                   marker='o', color='blue', label='<10% Flagging', s=120)
        ax.scatter(offset_x[ants_lt25pct_flagging[0]], offset_y[ants_lt25pct_flagging[0]],
                   marker='o', color='yellow', label='<25% Flagging', s=120)
        ax.scatter(offset_x[ants_lt50pct_flagging[0]], offset_y[ants_lt50pct_flagging[0]],
                   marker='o', color='magenta', label='<50% Flagging', s=120)
        ax.scatter(offset_x[ants_lt75pct_flagging[0]], offset_y[ants_lt75pct_flagging[0]],
                   marker='o', color='cyan', label='<75% Flagging', s=120)
        ax.scatter(offset_x[ants_gt75pct_flagging[0]], offset_y[ants_gt75pct_flagging[0]],
                   marker='o', color='black', label='>75% Flagging', s=120)
        if ants_missing[0].size > 0:
            ax.scatter(offset_x[ants_missing[0]], offset_y[ants_missing[0]],
                       marker='o', color='black', facecolors='none', edgecolors='black', label='Excluded', s=120)
        ax.legend()
        for i in range(len(names)):
            ax.text(offset_x[i], offset_y[i], names[i])
        ax.set_xlabel('Latitude Offset (m)')
        ax.set_ylabel('Longitude Offset (m)')
        ax.set_title('Antenna Positions colorized by Selfcal Flagging')
        ax.axes.set_aspect('equal')
        fig.savefig(filename)
        plt.close(fig)

    @staticmethod
    def get_flagged_solns_per_ant(gaintable, ms):
        """Get the antenna names and offsets."""

        antennas = ms.antenna_array.antennas
        names = []
        ids = []
        offset = []
        for ant in antennas:
            ids.append(ant.id)
            names.append(ant.name)
            offset.append(ant.offset)

        # Calculate the mean longitude and latitude.

        mean_longitude = np.mean([offset[i]["longitude offset"]
                                  ['value'] for i in range(len(names))])
        mean_latitude = np.mean([offset[i]["latitude offset"]
                                ['value'] for i in range(len(names))])

        # Calculate the offsets from the center.

        offsets = [np.sqrt((offset[i]["longitude offset"]['value'] -
                            mean_longitude)**2 + (offset[i]["latitude offset"]
                                                  ['value'] - mean_latitude)**2) for i in
                   range(len(names))]
        offset_y = [(offset[i]["latitude offset"]['value']) for i in
                    range(len(names))]
        offset_x = [(offset[i]["longitude offset"]['value']) for i in
                    range(len(names))]

        with casa_tools.TableReader(gaintable) as tb:
            nflags = []
            nunflagged = []
            fracflagged = []
            for idx in range(len(names)):
                tbant = tb.query(query='ANTENNA1=='+str(ids[idx]))
                ant_flags = tbant.getcol('FLAG')
                if ant_flags.size == 0:
                    nflags.append(0)
                    nunflagged.append(0)
                    fracflagged.append(np.nan)
                    continue
                nflags.append(ant_flags.sum())
                nunflagged.append(ant_flags.size - nflags[-1])
                fracflagged.append(nflags[-1]/ant_flags.size)
                tbant.close()
        offset_x = np.array(offset_x)
        offset_y = np.array(offset_y)
        nflags = np.array(nflags)
        nunflagged = np.array(nunflagged)
        fracflagged = np.array(fracflagged)

        return names, offset_x, offset_y, offsets, nflags, nunflagged, fracflagged

    def _plot_gain(self, ms, gaintable, solint):

        caltb_loc = os.path.join(self.scal_dir, gaintable)

        antennas = ms.antenna_array.antennas
        ant_names = []
        for ant_name in antennas:
            ant_names.append(ant_name.name)

        phasefreq_plots = []

        with TaskQueue() as tq:

            for ant_name in ant_names:
                if solint == 'inf_EB':
                    xaxis = 'frequency'
                    xtitle = 'Freq.'
                else:
                    xaxis = 'time'
                    xtitle = 'Time'
                if 'ap' in solint:
                    yaxis = 'amp'
                    ytitle = 'Amp'
                    plotrange = [0, 0, 0, 2.0]
                else:
                    yaxis = 'phase'
                    ytitle = 'Phase'
                    plotrange = [0, 0, -180, 180]
                try:
                    figname = os.path.join(self.stage_dir, 'plot_' + ant_name + '_' + gaintable.replace('.g', '.png'))
                    tq.add_functioncall(self._plot_gain_perant, caltb_loc, xaxis, yaxis, plotrange, ant_name, figname)
                    phasefreq_plots.append(logger.Plot(figname, x_axis=f'{xtitle} ({ant_name})', y_axis=f'{ytitle}'))
                except Exception as e:
                    continue

        return phasefreq_plots

    @staticmethod
    def _plot_gain_perant(caltb_loc, xaxis, yaxis, plotrange, ant, figname):
        """Plot gain for a given antenna."""
        if os.path.exists(figname):
            LOG.info(f'plotfile already exists: {figname}; skip plotting')
        else:
            title = os.path.basename(caltb_loc).replace('Target_', '')
            ct.plotms(gridrows=2, gridcols=1, plotindex=0, rowindex=0, vis=caltb_loc, xaxis=xaxis, yaxis=yaxis,
                      showgui=False, xselfscale=True, antenna=ant, plotrange=plotrange,
                      customflaggedsymbol=True, plotfile=figname,
                      title=f'{title} {ant}', xlabel=' ',
                      overwrite=True, clearplots=True,
                      titlefont=10, xaxisfont=10, yaxisfont=10)
            ct.plotms(gridrows=2, gridcols=1, rowindex=1, plotindex=1, vis=caltb_loc, xaxis=xaxis, yaxis='SNR',
                      showgui=False, xselfscale=True, antenna=ant,
                      customflaggedsymbol=True, plotfile=figname,
                      title=' ',
                      overwrite=True, clearplots=False,
                      titlefont=10, xaxisfont=10, yaxisfont=10)
        return

    @matplotlibrc_formal
    def plot(self):

        LOG.info("Making Selfcal assesment image for weblog")
        summary_plots = {}

        sc_imagenames = collections.OrderedDict()

        im_initial, im_final = self._get_ims()
        sc_imagenames[(self.field, self.band)] = {'initial': im_initial,
                                                  'final': im_final}
        self.result.ims_dict = sc_imagenames

        for tb, ims in self.result.ims_dict.items():
            plot_wrappers = []
            image_types = [('initial', 'Initial Image'), ('final', 'Final Image')]
            with casa_tools.ImageReader(ims['final']) as image:
                stats = image.statistics(robust=False)
                vmin = stats['min'][0]
                vmax = stats['max'][0]
            for image_type, image_desc in image_types:
                plot_wrappers.extend(sky.SkyDisplay(exclude_desc=True, overwrite=False, dpi=900).plot_per_stokes(
                    self.context, ims[image_type], reportdir=self.stage_dir, intent='', collapseFunction='mean',
                    vmin=vmin, vmax=vmax,
                    result_mask=ims[image_type].replace('.image.tt0', '.mask')))
                plot_wrappers[-1].parameters['title'] = image_desc
                plot_wrappers[-1].parameters['caption'] = image_desc
                plot_wrappers[-1].parameters['group'] = 'Initial/Final Comparisons'
            summary_plots = plot_wrappers

            n_initial, intensity_initial, rms_inital = self.create_noise_histogram(ims['initial'])
            n_final, intensity_final, rms_final = self.create_noise_histogram(ims['final'])
            if 'theoretical_sensitivity' in self.slib:
                rms_theory = self.slib['theoretical_sensitivity']
                if rms_theory != -99.0:
                    rms_theory = self.slib['theoretical_sensitivity']
                else:
                    rms_theory = 0.0
            else:
                rms_theory = 0.0

            noise_histogram_plots_path = os.path.join(self.stage_dir, sanitize_string(tb[0])+'_'+tb[1]+'_noise_plot.png')

            self.create_noise_histogram_plots(
                n_initial, n_final, intensity_initial, intensity_final, rms_inital, rms_final,
                noise_histogram_plots_path, rms_theory)
            noisehist_plot = logger.Plot(noise_histogram_plots_path)
            noisehist_plot.parameters['title'] = 'Noise Histogram'
            noisehist_plot.parameters['caption'] = 'Noise Histogram'
            noisehist_plot.parameters['group'] = 'Initial/Final Comparisons'

        return summary_plots, noisehist_plot

    @staticmethod
    @matplotlibrc_formal
    def create_noise_histogram_plots(N_1, N_2, intensity_1, intensity_2, rms_1, rms_2, outfile, rms_theory=0.0):

        def gaussian_norm(x, mean, sigma):
            gauss_dist = np.exp(-(x-mean)**2/(2*sigma**2))
            norm_gauss_dist = gauss_dist/np.max(gauss_dist)
            return norm_gauss_dist

        fig, ax = plt.subplots(figsize=(9.6, 7.2))
        ax.set_yscale('log')
        plt.ylim([0.0001, 2.0])
        ax.step(intensity_1, N_1/np.max(N_1), label='Initial Data')
        ax.step(intensity_2, N_2/np.max(N_2), label='Final Data')
        ax.plot(intensity_1, gaussian_norm(intensity_1, 0, rms_1), label='Initial Gaussian')
        ax.plot(intensity_2, gaussian_norm(intensity_2, 0, rms_2), label='Final Gaussian')
        if rms_theory != 0.0:
            ax.plot([-1.0*rms_theory, rms_theory], [0.606, 0.606], label='Theoretical Sensitivity')
        ax.legend(fontsize=10)
        ax.set_xlabel('Intensity (mJy/Beam)')
        ax.set_ylabel('N')
        ax.set_title('Initial vs. Final Noise (Unmasked Pixels)', fontsize=20)
        fig.savefig(outfile)
        plt.close(fig)

    @staticmethod
    def create_noise_histogram(imagename):

        MADtoRMS = 1.4826

        with casa_tools.ImageReader(imagename) as image:
            telescope = image.coordsys().telescope()

        maskImage = imagename.replace('image', 'mask').replace('.tt0', '')
        residualImage = imagename.replace('image', 'residual')

        shutil.rmtree('temp.mask', ignore_errors=True)
        shutil.rmtree('temp.residual', ignore_errors=True)

        if os.path.exists(maskImage):
            shutil.copytree(maskImage, 'temp.mask')
            maskImage = 'temp.mask'
        shutil.copytree(residualImage, 'temp.residual')

        residualImage = 'temp.residual'
        if os.path.exists(maskImage):
            with casa_tools.ImageReader(residualImage) as image:
                image.calcmask("'"+maskImage+"'"+" <0.5"+"&& mask("+residualImage+")", name='madpbmask0')
                mask0Stats = image.statistics(robust=True, axes=[0, 1])
                image.maskhandler(op='set', name='madpbmask0')
                rms = mask0Stats['medabsdevmed'][0] * MADtoRMS
                pix = np.squeeze(image.getchunk())
                mask = np.squeeze(image.getchunk(getmask=True))
                dimensions = mask.ndim
                if dimensions == 4:
                    mask = mask[:, :, 0, 0]
                if dimensions == 3:
                    mask = mask[:, :, 0]
                unmasked = (mask == True).nonzero()
                pix_unmasked = pix[unmasked]
                N, intensity = np.histogram(pix_unmasked, bins=50)

        elif telescope == 'ALMA':
            with casa_tools.ImageReader(residualImage) as image:
                image.calcmask("mask("+residualImage+")", name='madpbmask0')
                mask0Stats = image.statistics(robust=True, axes=[0, 1])
                image.maskhandler(op='set', name='madpbmask0')
                rms = mask0Stats['medabsdevmed'][0] * MADtoRMS
                pix = np.squeeze(image.getchunk())
                mask = np.squeeze(image.getchunk(getmask=True))
                mask = mask[:, :, 0, 0]
                unmasked = (mask == True).nonzero()
                pix_unmasked = pix[unmasked]
        elif 'VLA' in telescope:
            with casa_tools.ImageReader(imagename.replace('image', 'residual')) as image:
                rms = image.statistics(algorithm='chauvenet')['rms'][0]
            with casa_tools.ImageReader(residualImage) as image:
                pix_unmasked = np.squeeze(image.getchunk())

        N, intensity = np.histogram(pix_unmasked, bins=100)
        intensity = np.diff(intensity)+intensity[:-1]

        shutil.rmtree('temp.mask', ignore_errors=True)
        shutil.rmtree('temp.residual', ignore_errors=True)

        return N, intensity, rms
