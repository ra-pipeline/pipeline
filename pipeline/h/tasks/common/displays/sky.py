# ******************************************************************************
# ALMA - Atacama Large Millimeter Array
# Copyright (c) ATC - Astronomy Technology Center - Royal Observatory Edinburgh, 2011
# (in the framework of the ALMA collaboration).
# All rights reserved.
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307  USA
# *******************************************************************************
"""Module to plot sky images."""

import copy
import os
import string
import shutil

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.text as mtext
import numpy as np

from typing import Optional

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.renderer.logger as logger

from matplotlib.offsetbox import AnnotationBbox, HPacker, TextArea
from pipeline.hif.tasks.makeimages.resultobjects import MakeImagesResult
from pipeline.infrastructure import casa_tools
from pipeline.infrastructure import casa_tasks
from pipeline.infrastructure.utils import get_stokes

LOG = infrastructure.get_logger(__name__)

_valid_chars = "_.%s%s" % (string.ascii_letters, string.digits)


def _char_replacer(s):
    """A small utility function that echoes the argument or returns '_' if the
    argument is in a list of forbidden characters.
    """
    if s not in _valid_chars:
        return '_'
    return s


def sanitize(text):
    filename = ''.join(_char_replacer(c) for c in text)
    return filename


def plotfilename(image, reportdir, collapseFunction=None):
    if collapseFunction is None:
        name = '%s.sky.png' % (os.path.basename(image))
    else:
        name = '%s.%s.sky.png' % (os.path.basename(image), collapseFunction)
    name = sanitize(name)
    name = os.path.join(reportdir, name)
    return name


class SkyDisplay(object):
    """Class to plot sky images."""

    def plot_per_stokes(self, *args, stokes_list: Optional[list] = None, **kwargs):
        """Plot sky images from a image file with multiple Stokes planes (one image per Stokes).
        
        PIPE-1401: a new keyword argument 'stokes' is added into SkyDisplay.plot(), SkyDisplay._plot_panel(), etc.
        By design, the default stokes=None will preserve the behavior before PIPE-1401: it won't add
        additional stokes-related suffix in .png or attach the 'stokes' key in the plot wrapper object.
        """
        plots = []
        if stokes_list is None:
            stokes_list = get_stokes(args[1])
        for stokes in stokes_list:
            plots.append(self.plot(*args, stokes=stokes, **kwargs))

        return plots

    def plot(self, context, result, reportdir, intent=None, collapseFunction='mean', stokes: Optional[str] = None, vmin=None, vmax=None, mom8_fc_peak_snr=None,
             dpi=None, **imshow_args):

        self.dpi = dpi
        if not result:
            return []

        if vmin is not None and vmax is not None:
            imshow_args['norm'] = plt.Normalize(vmin, vmax, clip=True)

        if isinstance(context.results[-1], MakeImagesResult):
            if (context.results[-1].results[0].imaging_mode in ('VLA', 'EVLA', 'JVLA') and
                    context.results[-1].results[0].specmode == 'cont'):
                ms = context.observing_run.get_measurement_sets()[0]  # only 1 ms for VLA
            else:
                ms = None
        else:
            ms = None

        plotfile, coord_names, field, band = self._plot_panel(context, reportdir, result, collapseFunction=collapseFunction, stokes=stokes, ms=ms,
                                                              mom8_fc_peak_snr=mom8_fc_peak_snr, **imshow_args)

        # field names may not be unique, which leads to incorrectly merged
        # plots in the weblog output. As a temporary fix, change to field +
        # intent - which is better but again, not guaranteed unique.
        if intent:
            field = '%s (%s)' % (field, intent)

        with casa_tools.ImageReader(result) as image:
            miscinfo = image.miscinfo()

        parameters = {k: miscinfo[k] for k in ['virtspw', 'pol', 'field', 'type', 'iter'] if k in miscinfo}
        parameters['ant'] = None
        parameters['band'] = band
        parameters['moment'] = collapseFunction
        if isinstance(stokes, str):
            # PIPE-1401: only save the 'stokes' keyword when it was explicitly requested.
            parameters['stokes'] = stokes

        try:
            parameters['prefix'] = miscinfo['filnam01']
        except:
            parameters['prefix'] = None

        plot = logger.Plot(plotfile, x_axis=coord_names[0],
                           y_axis=coord_names[1], field=field,
                           parameters=parameters)

        return plot

    def _plot_panel(self, context, reportdir, result, collapseFunction='mean', stokes: Optional[str] = None, ms=None, mom8_fc_peak_snr=None, **imshow_args):
        """Method to plot a map."""

        if isinstance(stokes, str):
            # PIPE-1410: only attach the Stokes suffix when it's explicily specified.
            plotfile = plotfilename(image=os.path.basename(result)+f'.{stokes}', reportdir=reportdir, collapseFunction=collapseFunction)
        else:
            plotfile = plotfilename(image=os.path.basename(result), reportdir=reportdir, collapseFunction=collapseFunction)

        LOG.info('Plotting %s' % result)

        stokes_present = get_stokes(result)

        with casa_tools.ImageReader(result) as image:

            if stokes not in stokes_present:
                stokes_select = stokes_present[0]
                # PIPE-1401: plot mask sky images for different stokes plane even when the mask file has a single Stokes plane.
                # note: the fallback is required for vlass-se-cube because the user input mask is from vlass-se-cont with only Stokes=I.
                if isinstance(stokes, str):
                    LOG.warning(f'Stokes {stokes_select} is requested, but only Stokes={stokes_present} is present.')
                    LOG.warning(f'We will try to create a plot with a fallback of Stokes={stokes_select}.')
                else:
                    LOG.info(
                        f'No Stokes selection is specified, we will use the first present Stokes plane: Stokes={stokes_select}.')
            else:
                stokes_select = stokes
                LOG.info(f'Stokes={stokes_select} is selected.')

            try:
                if collapseFunction == 'center':
                    collapsed = image.collapse(function='mean', chans=str(
                        image.summary()['shape'][3]//2), stokes=stokes_select, axes=3)
                elif collapseFunction == 'mom0':
                    # image.collapse does not have a true "mom0" option. "sum" is close, but the
                    # scaling is different.
                    # TODO: Switch the whole _plot_panel method to using immoments(?) Though the
                    #       downside is that images can no longer be made just in memory. They
                    #       always have to be written to disk.
                    tmpfile = f'{os.path.basename(result)}_mom0_tmp.img'
                    job = casa_tasks.immoments(imagename=result, moments=[0], outfile=tmpfile, stokes=stokes_select)
                    job.execute(dry_run=False)
                    assert os.path.exists(tmpfile)
                    collapsed = image.newimagefromimage(infile=tmpfile)
                    shutil.rmtree(tmpfile)
                elif collapseFunction == 'mom8':
                    collapsed = image.collapse(function='max', stokes=stokes_select, axes=3)
                else:
                    # Note: in case 'max' and non-pbcor image a moment 0 map was written to disk
                    # in the past. With PIPE-558 this is done in hif/tasks/tclean.py tclean._calc_mom0_8()
                    collapsed = image.collapse(function=collapseFunction, stokes=stokes_select, axes=3)
            except:
                # All channels flagged or some other error. Make collapsed zero image.
                collapsed_new = image.newimagefromimage(infile=result)
                collapsed_new.set(pixelmask=True, pixels='0')
                collapsed = collapsed_new.collapse(function='mean', stokes=stokes_select, axes=3)
                collapsed_new.done()

            name = image.name(strippath=True)

            cs = collapsed.coordsys()
            coord_names = cs.names()
            cs.setunits(type='direction', value='arcsec arcsec')
            coord_units = cs.units()
            coord_refs = cs.referencevalue(format='s')

            brightness_unit = collapsed.brightnessunit()
            miscinfo = collapsed.miscinfo()

            beam_rec = collapsed.restoringbeam()
            if 'major' in beam_rec:
                cqa = casa_tools.quanta
                bpa = cqa.convert(beam_rec['positionangle'], 'deg')['value']
                bmaj = cqa.convert(beam_rec['major'], 'arcsec')['value']
                bmin = cqa.convert(beam_rec['minor'], 'arcsec')['value']
                beam = [bmaj, bmin, bpa]
            else:
                beam = None

            # don't replot if a file of the required name already exists
            if os.path.exists(plotfile):
                LOG.info('plotfile already exists: %s', plotfile)

                # We make sure that 'band' is still defined as if the figure is plotted.
                # The code below is directly borrowed from the block inside the actual plotting sequence.

                # VLA only, not VLASS (in which ms==None)
                if ms:
                    band = ms.get_vla_spw2band()
                    band_spws = {}
                    for k, v in band.items():
                        band_spws.setdefault(v, []).append(k)
                    for k, v in band_spws.items():
                        for spw in miscinfo['virtspw'].split(','):
                            if int(spw) in v:
                                miscinfo['band'] = k
                                del miscinfo['virtspw']
                                break
                        if 'virtspw' not in miscinfo:
                            break
                band = miscinfo.get('band', None)
                # if the band name is not available, use ref_frequencey (in Hz) as the fallback.
                if band is None:
                    band = cs.referencevalue(format='n')['numeric'][3]

                return plotfile, coord_names, miscinfo.get('field'), band

            # otherwise do the plot
            data = collapsed.getchunk()
            mask = np.invert(collapsed.getchunk(getmask=True))
            shape = np.shape(data)
            data = data.reshape(shape[0], shape[1])
            mask = mask.reshape(shape[0], shape[1])
            mdata = np.ma.array(data, mask=mask)
            collapsed.done()

            # get tl/tr corner positions in offset
            blc = cs.toworld([-0.5, -0.5, 0, 0])
            blc = cs.torel(blc)['numeric']
            trc = cs.toworld([shape[0]-0.5, shape[1]-0.5, 0, 0])
            trc = cs.torel(trc)['numeric']

            # remove any incomplete matplotlib plots, if left these can cause weird errors
            plt.close('all')
            fig, ax = plt.subplots(figsize=(6.4, 4.8))

            # plot data
            if 'cmap' not in imshow_args:
                # matplotlib Colormap has its own __copy__ implementation:
                #   https://github.com/matplotlib/matplotlib/blob/v3.3.x/lib/matplotlib/colors.py#L616
                imshow_args['cmap'] = copy.copy(plt.cm.jet)
            imshow_args['cmap'].set_bad('k', 1.0)
            im = ax.imshow(mdata.T, interpolation='nearest', origin='lower', aspect='equal',
                           extent=[blc[0], trc[0], blc[1], trc[1]], **imshow_args)

            ax.axis('image')
            lims = ax.axis()

            # make ticks and labels white
            for line in ax.xaxis.get_ticklines() + ax.yaxis.get_ticklines():
                line.set_color('white')
            for label in ax.xaxis.get_ticklabels() + ax.yaxis.get_ticklabels():
                label.set_fontsize(0.5 * label.get_fontsize())

            # colour bar
            cb = plt.colorbar(im, ax=ax, shrink=0.5)
            fontsize = 8
            for label in cb.ax.get_yticklabels() + cb.ax.get_xticklabels():
                label.set_fontsize(fontsize)
            cb.set_label(brightness_unit, fontsize=fontsize)

            # image reference pixel
            yoff = 0.10
            yoff = self.plottext(1.05, yoff, 'Reference position:', 40)
            for i, k in enumerate(coord_refs['string']):
                # note: the labels present the reference value at individual axes of the collapsed image
                # https://casa.nrao.edu/docs/casaref/image.collapse.html
                yoff = self.plottext(1.05, yoff, '%s: %s' % (coord_names[i], k), 40, mult=0.8)

            # if peaksnr is available for the mom8_fc image, include it in the plot
            if 'mom8_fc' in result and mom8_fc_peak_snr is not None:
                yoff = 0.90
                self.plottext(1.05, yoff, 'Peak SNR: {:.5f}'.format(mom8_fc_peak_snr), 40)

            # plot beam
            if beam is not None:
                beam_patch = mpatches.Ellipse((lims[0] + 0.1 * (lims[1]-lims[0]), lims[2] + 0.1 * (lims[3]-lims[2])),
                                              width=beam[1], height=beam[0],
                                              linestyle='solid', edgecolor='yellow', fill=False,
                                              angle=-beam[2])
                ax.add_patch(beam_patch)

            # add xy labels
            ax.set_xlabel('%s (%s)' % (coord_names[0], coord_units[0]))
            ax.set_ylabel('%s (%s)' % (coord_names[1], coord_units[1]))

            mode_texts = {'mean': 'mean', 'mom0': 'integ. line int. (mom0)', 'max': 'peak line int. (mom8)', 'mom8': 'peak line int. (mom8)', 'center': 'center slice'}
            image_info = {'display': mode_texts[collapseFunction]}
            image_info.update(miscinfo)
            if 'type' in image_info:
                if image_info['type'] == 'flux':
                    image_info['type'] = 'pb'
                if image_info['type'] == 'mom0_fc':
                    image_info['type'] = 'Line-free Moment 0'
                if image_info['type'] == 'mom8_fc':
                    image_info['type'] = 'Line-free Moment 8'

            # VLA only, not VLASS
            if ms:
                band = ms.get_vla_spw2band()
                band_spws = {}
                for k, v in band.items():
                    band_spws.setdefault(v, []).append(k)
                for k, v in band_spws.items():
                    for spw in image_info['virtspw'].split(','):
                        if int(spw) in v:
                            image_info['band'] = k
                            del image_info['virtspw']
                            break
                    if 'virtspw' not in image_info:
                        break

            if 'band' in image_info:
                label = [TextArea('%s:%s' % (key, image_info[key]), textprops=dict(color=color))
                         for key, color in [('type', 'k'),
                                            ('display', 'r'),
                                            ('field', 'k'),
                                            ('band', 'k'),
                                            ('pol', 'k'),
                                            ('iter', 'k')]
                         if image_info.get(key) is not None]
                band = image_info.get('band')
            else:
                label = [TextArea('%s:%s' % (key, image_info[key]), textprops=dict(color=color))
                         for key, color in [('type', 'k'),
                                            ('display', 'r'),
                                            ('field', 'k'),
                                            ('virtspw', 'k'),
                                            ('pol', 'k'),
                                            ('iter', 'k')]
                         if image_info.get(key) is not None]
                band = None

            # if the band name is not available, use ref_frequencey (in Hz) as the fallback.
            if band is None:
                band = cs.referencevalue(format='n')['numeric'][3]

            # PIPE-997: plot a 41pix-wide PSF inset if the image is larger than 41*3
            if 'type' in image_info:
                if image_info['type'] == 'psf':

                    npix_inset_half = 20
                    maxfrac_inset = 1./3
                    npix_inset = npix_inset_half*2.+1

                    if npix_inset < shape[0]*maxfrac_inset or npix_inset < shape[1]*maxfrac_inset:
                        x0 = shape[0]//2-npix_inset_half
                        x1 = shape[0]//2+npix_inset_half+1
                        y0 = shape[1]//2-npix_inset_half
                        y1 = shape[1]//2+npix_inset_half+1
                        mdata_sub = mdata[x0:x1, y0:y1]
                        axinset = ax.inset_axes(bounds=[0.60, 0.02, 0.38, 0.38])

                        blc = cs.toworld([-0.5+x0, -0.5+y0, 0, 0])
                        blc = cs.torel(blc)['numeric']
                        trc = cs.toworld([x1-0.5, y1-0.5, 0, 0])
                        trc = cs.torel(trc)['numeric']

                        # use the same vmin/vmax as the full-size plot.
                        if 'norm' not in imshow_args:
                            vmin, vmax = im.get_clim()
                            imshow_args['norm'] = plt.Normalize(vmin, vmax, clip=True)
                        axinset.imshow(mdata_sub.T, extent=[blc[0], trc[0], blc[1], trc[1]],
                                       interpolation='nearest', origin='lower', aspect='equal',
                                       **imshow_args)

                        for spine in ['bottom', 'top', 'right', 'left']:
                            axinset.spines[spine].set_color('white')
                        axinset.contour(mdata_sub.T, [0.5], colors='k', linestyles='dotted',
                                        extent=[blc[0], trc[0], blc[1], trc[1]], origin='lower')
                        axinset.set_xticks([])
                        axinset.set_yticks([])

                        if beam is not None:
                            beam_patch = mpatches.Ellipse((0, 0), width=beam[1], height=beam[0],
                                                          linestyle='solid', edgecolor='k', fill=False,
                                                          angle=-beam[2])
                            axinset.add_patch(beam_patch)

            # finally done with ia.coordsys()
            cs.done()

            # color text box
            txt = HPacker(children=label, align="baseline", pad=0, sep=7)
            bbox = AnnotationBbox(txt, xy=(0.5, 1.05),
                                  xycoords='axes fraction',
                                  frameon=True,
                                  box_alignment=(0.5, 0.5))
            ax.add_artist(bbox)

            # save the image
            fig.tight_layout()
            fig.savefig(plotfile, bbox_inches='tight', bbox_extra_artists=ax.findobj(mtext.Text), dpi=self.dpi)
            plt.close(fig)

            return plotfile, coord_names, miscinfo.get('field'), band

    @staticmethod
    def plottext(xoff, yoff, text, maxchars, ny_subplot=1, mult=1):
        """Utility method to plot text and put line breaks in to keep the
        text within a given limit.

        Keyword arguments:
        xoff       -- world x coord where text is to start.
        yoff       -- world y coord where text is to start.
        text       -- Text to print.
        maxchars   -- Maximum number of characters before a newline is
                      inserted.
        ny_subplot -- Number of sub-plots along the y-axis of the page.
        mult       -- Factor by which the text fontsize is to be multiplied.
        """

        words = text.rsplit()
        words_in_line = 0
        line = ''
        ax = plt.gca()
        for i in range(len(words)):
            temp = line + words[i] + ' '
            words_in_line += 1
            if len(temp) > maxchars:
                if words_in_line == 1:
                    ax.text(xoff, yoff, temp, va='center', fontsize=mult*8,
                            transform=ax.transAxes, clip_on=False)
                    yoff -= 0.03 * ny_subplot * mult
                    words_in_line = 0
                else:
                    ax.text(xoff, yoff, line, va='center', fontsize=mult*8,
                            transform=ax.transAxes, clip_on=False)
                    yoff -= 0.03 * ny_subplot * mult
                    line = words[i] + ' '
                    words_in_line = 1
            else:
                line = temp
        if len(line) > 0:
            ax.text(xoff, yoff, line, va='center', fontsize=mult*8,
                    transform=ax.transAxes, clip_on=False)
            yoff -= 0.03 * ny_subplot * mult
        yoff -= 0.01 * ny_subplot * mult
        return yoff
