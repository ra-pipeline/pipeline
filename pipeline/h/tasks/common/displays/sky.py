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
import shutil
import string
import textwrap
import traceback

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap
from matplotlib.offsetbox import AnnotationBbox, HPacker, TextArea
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
from scipy.ndimage import binary_dilation, binary_erosion, generate_binary_structure

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.renderer.logger as logger
import pipeline.infrastructure.utils as utils
from pipeline.infrastructure import casa_tasks, casa_tools, filenamer
from pipeline.infrastructure.displays.plotstyle import matplotlibrc_formal
from pipeline.infrastructure.utils import get_stokes

LOG = infrastructure.logging.get_logger(__name__)

_valid_chars = "_.%s%s" % (string.ascii_letters, string.digits)


def plotfilename(image, reportdir, collapseFunction=None, stokes=None):
    """Generate a filename for a plot based on image and other parameters.

    Args:
        image (str): Path to the image file.
        reportdir (str): Directory where the report will be saved.
        collapseFunction (str | None): Collapse function used, if any.
        stokes (str | None): Stokes parameter, if specified.

    Returns:
        str: The generated filename for the plot.

    Note:
        The Stokes suffix is only attached when explicitly specified (PIPE-1410).
    """

    name_elements = [os.path.basename(image)]
    name_elements.extend(filter(None, [collapseFunction, stokes, 'sky', 'png']))
    name = os.path.join(reportdir, filenamer.sanitize('.'.join(name_elements), valid_chars=_valid_chars))

    return name


class SkyDisplay:
    """Class to plot sky images."""

    def __init__(self, exclude_desc=False, overwrite=False, figsize=(6.4, 4.8), dpi=None):
        self.exclude_desc = exclude_desc    # exclude the text descriptions from image metadata.
        self.overwrite = overwrite          # decide whether to overwrite existing figures or not.
        self.figsize = figsize              # class instance default figsize value
        self._dpi = dpi                     # class instance default dpi

    def plot_per_stokes(self, *args, stokes_list: list[str] | None = None, **kwargs) -> list:
        """Plot sky images from a CASA image file with multiple Stokes planes.

        Args:
            *args: Positional arguments to be passed to self.plot().
            stokes_list: List of Stokes parameters to plot.
                If None, all available Stokes planes will be plotted.
            **kwargs: Keyword arguments to be passed to self.plot().

        Returns:
            A list of plot objects, one for each Stokes parameter.

        Description:
            This method generates one plot per Stokes parameter for a given image file.
            It uses self.plot() to create each individual plot.

        Note:
            PIPE-1401: A new keyword argument 'stokes' is added to SkyDisplay.plot(),
            SkyDisplay._plot_panel(), etc. By default (stokes=None), the behavior
            before PIPE-1401 is preserved: no additional stokes-related suffix in .png
            or 'stokes' key in the plot wrapper object.
        """
        if stokes_list is None:
            stokes_list = get_stokes(args[1])

        return [self.plot(*args, stokes=stokes, **kwargs) for stokes in stokes_list]

    def _get_default_dpi(self, context):
        """Get the default DPI (dots per inch) for imaging plots.

        Args:
            context: The Pipeline context object.

        Returns:
            float or None: The default DPI value. 400.0 for VLA imaging plots,
            self._dpi if set, or None otherwise.

        Description:
            This method determines the default DPI for imaging plots based on
            the context and instance settings. It prioritizes the instance's
            _dpi attribute if set, otherwise uses context-based logic.

        Note:
            For VLA hif_makeimages sky plots, the default is 400 DPI (PIPE-1083).
        """

        # class instance default takes precedence over the context-based default
        if self._dpi is not None:
            return self._dpi

        last_result = context.results[-1]

        # PIPE-1083: when making VLA/SS hif_makeimages sky plot, we default to 400 dpi
        if last_result.taskname == 'hif_makeimages':
            if last_result.results:
                first_result = last_result.results[0]
                if first_result.imaging_mode in ('VLA', 'EVLA', 'JVLA') or first_result.imaging_mode.startswith('VLASS'):
                    return 400.0

        # PIPE-1083: when making sky plots for the tasks/stages below, we default to 400 dpi.
        #     hif_makermsimages, hif_makecutoutsimages, and hifv_pbcor
        if last_result.taskname in ('hif_makermsimages', 'hif_makecutoutimages', 'hifv_pbcor'):
            return 400.0

        return None

    def _get_vla_band(self, context, miscinfo) -> str | None:
        """Get the VLA band string, only for VLA aggregated cont imaging."""
        last_result = context.results[-1]

        # Check if we should use band notation based on task and imaging mode
        use_band_notation = (
            # hif_makeimage VLA-PI cont imaging sky plots
            (
                last_result.taskname == 'hif_makeimages'
                and last_result.results[0].imaging_mode in {'VLA', 'EVLA', 'JVLA'}
                and miscinfo.get('specmode') == 'cont'
            )
            or
            # hifv_pbcor VLA-PI cont imaging sky plots
            (
                last_result.taskname == 'hifv_pbcor'
                and context.imaging_mode is None
                and miscinfo.get('specmode') == 'cont'
            )
        )

        if not use_band_notation:
            return None

        # Get measurement set and band mapping - VLA has only 1 MS
        ms = context.observing_run.get_measurement_sets()[0]
        spw2band = ms.get_vla_spw2band()
        virtspw_str = miscinfo.get('virtspw', '')
        if not virtspw_str:
            return None

        bands = {spw2band[spw_id] for spw in virtspw_str.split(',') if (spw_id := int(spw)) in spw2band}

        # VLA imaging happens per-band, typically resulting in single-element set
        return ','.join(bands) if bands else None

    def plot(self, context, imagename, reportdir, intent=None, collapseFunction='mean',
             stokes: str | None = None, vmin=None, vmax=None, mom8_fc_peak_snr=None,
             maskname=None, dpi=None, **imshow_args):
        """Plot sky images from a image file."""

        if not imagename:
            return []

        if vmin is not None and vmax is not None:
            imshow_args['norm'] = plt.Normalize(vmin, vmax, clip=True)

        # The dpi input from a method call takes precedence over the class/context-based default.
        if dpi is not None:
            dpi_savefig = dpi
        else:
            dpi_savefig = self._get_default_dpi(context)

        plotfile, coord_names, field, band = self._plot_panel(context, reportdir, imagename, collapseFunction=collapseFunction,
                                                              stokes=stokes,
                                                              mom8_fc_peak_snr=mom8_fc_peak_snr,
                                                              maskname=maskname, dpi=dpi_savefig, **imshow_args)

        # field names may not be unique, which leads to incorrectly merged
        # plots in the weblog output. As a temporary fix, change to field +
        # intent - which is better but again, not guaranteed unique.
        if intent:
            field = f'{field!s} ({intent!s})'

        with casa_tools.ImageReader(imagename) as image:
            miscinfo = image.miscinfo()

        parameters = {k: miscinfo[k] for k in ['virtspw', 'pol', 'field', 'datatype', 'type', 'iter'] if k in miscinfo}
        parameters['ant'] = None
        parameters['band'] = band
        parameters['moment'] = collapseFunction
        if isinstance(stokes, str):
            # PIPE-1401: only save the 'stokes' keyword when it was explicitly requested.
            parameters['stokes'] = stokes
        try:
            parameters['prefix'] = os.path.basename(imagename).split('.')[0]
        except:
            parameters['prefix'] = None

        plot = logger.Plot(plotfile, x_axis=coord_names[0],
                           y_axis=coord_names[1], field=field,
                           parameters=parameters)

        return plot

    def _collapse_image(self, imagename, collapseFunction='mean', stokes: str | None = None, include_mask=False):
        """Collapse an image along the spectral axis."""
        stokes_present = get_stokes(imagename)
        if stokes not in stokes_present:
            stokes_select = stokes_present[0]
        else:
            stokes_select = stokes

        with casa_tools.ImageReader(imagename) as image:
            _, _, npol, nchan = image.shape()
            if nchan == 1 and npol == 1:
                if include_mask:
                    mdata = np.ma.array(
                        image.getchunk(dropdeg=True), mask=np.invert(image.getchunk(getmask=True, dropdeg=True))
                    )
                else:
                    mdata = image.getchunk(dropdeg=True)
            else:
                collapsed = image.collapse(function=collapseFunction, axes=2, stokes=stokes_select)
                if include_mask:
                    mdata = np.ma.array(
                        collapsed.getchunk(dropdeg=True), mask=np.invert(collapsed.getchunk(getmask=True, dropdeg=True))
                    )
                else:
                    mdata = collapsed.getchunk(dropdeg=True)
                collapsed.done()
        return mdata

    @matplotlibrc_formal
    def _plot_panel(self, context, reportdir, imagename, collapseFunction='mean',
                    stokes: str | None = None, mom8_fc_peak_snr=None,
                    maskname=None, dpi=None, **imshow_args):
        """Method to plot a map."""
        plotfile = plotfilename(image=os.path.basename(imagename),
                                reportdir=reportdir, collapseFunction=collapseFunction, stokes=stokes)
        LOG.info('Plotting %s to %s', imagename, plotfile)

        stokes_present = get_stokes(imagename)
        if stokes not in stokes_present:
            stokes_select = stokes_present[0]
            # PIPE-1401: plot mask sky images for different stokes plane even when the mask file has a single Stokes plane.
            # note: the fallback is required for vlass-se-cube because the user input mask is from vlass-se-cont with only Stokes=I.
            if isinstance(stokes, str):
                LOG.warning('Stokes %s is requested, but only Stokes=%s is present.', stokes, stokes_present)
                LOG.warning('We will try to create a plot with a fallback of Stokes=%s.', stokes_present)
            else:
                LOG.info(
                    'No Stokes selection is specified, we will use the first present Stokes plane: Stokes=%s.',
                    stokes_select,
                )
        else:
            stokes_select = stokes
            LOG.info('Stokes=%s is selected.', stokes_select)

        with casa_tools.ImageReader(imagename) as image:
            _, _, npol, nchan = image.shape()

        plot_exists_and_keep = os.path.exists(plotfile) and not self.overwrite
        is_single_plane = (nchan == 1 and npol == 1)

        # Reuse the original image either when we are not allowed to overwrite
        # an existing plot file, or when the image is already a single
        # (channel, polarization) plane and no collapsing is needed.
        if plot_exists_and_keep or is_single_plane:
            collapsed = casa_tools.image
            collapsed.open(imagename)
        else:
            with casa_tools.ImageReader(imagename) as image:
                if nchan == 1:
                    # Use Stokes-axis slicing instead of frequency collapsing
                    rgtool = casa_tools.regionmanager
                    cs = image.coordsys()
                    region = rgtool.frombcs(csys=cs.torecord(), shape=image.shape(),
                                            stokes=stokes_select, stokescontrol='a')
                    cs.done()
                    collapsed = image.subimage(region=region)
                    rgtool.done()
                else:
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
                            tmpfile = f'{os.path.basename(imagename)}_mom0_tmp.img'
                            casa_tasks.immoments(imagename=imagename, moments=[
                                0], outfile=tmpfile, stokes=stokes_select).execute()
                            assert os.path.exists(tmpfile)
                            collapsed = image.newimagefromimage(infile=tmpfile)
                            shutil.rmtree(tmpfile)
                        elif collapseFunction == 'mom8':
                            collapsed = image.collapse(function='max', stokes=stokes_select, axes=3)
                        else:
                            # Note: in case 'max' and non-pbcor image a moment 0 map was written to disk
                            # in the past. With PIPE-558 this is done in hif/tasks/tclean.py tclean._calc_mom0_8()
                            collapsed = image.collapse(function=collapseFunction, stokes=stokes_select, axes=3)
                    except Exception as ex:
                        LOG.info(ex)
                        traceback_msg = traceback.format_exc()
                        LOG.debug(traceback_msg)
                        # All channels flagged or some other error. Make collapsed zero image.
                        collapsed_new = image.newimagefromimage(infile=imagename)
                        collapsed_new.set(pixelmask=True, pixels='0')
                        collapsed = collapsed_new.collapse(function='mean', stokes=stokes_select, axes=3)
                        collapsed_new.done()

        cs = collapsed.coordsys()  # needs to explicitly close later
        coord_names = cs.names()
        miscinfo = collapsed.miscinfo()

        vla_cont_band = self._get_vla_band(context, miscinfo)
        if vla_cont_band is not None:
            # VLA-specmode='cont' only, not triggered for ALMA, VLASS.
            miscinfo['band'] = vla_cont_band
        else:
            # Use the reference-frequencey (in Hz) as the fallback value of the 'band' key
            # This key is only used for VLASS and VLA so will not affect ALMA
            miscinfo['band'] = cs.referencevalue(format='n')['numeric'][3]

        field_name = miscinfo.get('field', None)
        band_name = miscinfo.get('band', None)

        # early abort: don't replot if a file with the required name already exists
        if os.path.exists(plotfile) and not self.overwrite:
            LOG.info('plotfile already exists: %s', plotfile)
            # done with ia/cs tool instances
            collapsed.done()
            cs.done()
            return plotfile, coord_names, field_name, band_name

        cs.setunits(type='direction', value='arcsec arcsec')
        coord_units = cs.units()
        coord_refs = cs.referencevalue(format='s')
        brightness_unit = collapsed.brightnessunit()
        beam_rec = collapsed.restoringbeam()
        if 'major' in beam_rec:
            cqa = casa_tools.quanta
            bpa = cqa.convert(beam_rec['positionangle'], 'deg')['value']
            bmaj = cqa.convert(beam_rec['major'], 'arcsec')['value']
            bmin = cqa.convert(beam_rec['minor'], 'arcsec')['value']
            beam = [bmaj, bmin, bpa]
        else:
            beam = None

        # Otherwise do the plotting

        # remove any incomplete matplotlib plots, if left these can cause weird errors
        plt.close('all')

        # PIPE-2843: disable constrained layout to prevent potential bad interaction with AnnotationBbox
        # Also see: https://github.com/matplotlib/matplotlib/issues/24453
        fig, ax = plt.subplots(figsize=self.figsize, constrained_layout=False)

        LOG.info('Getting data from collapsed image of %s', imagename)

        data = collapsed.getchunk(dropdeg=True)
        mask = np.invert(collapsed.getchunk(getmask=True, dropdeg=True))

        collapsed.done()
        shape = data.shape
        data = data.reshape(shape[0], shape[1])
        mask = mask.reshape(shape[0], shape[1])
        mdata = np.ma.array(data, mask=mask)

        # get tl/tr corner positions in offset
        blc = cs.torel(cs.toworld([-0.5, -0.5, 0, 0]))['numeric']
        trc = cs.torel(cs.toworld([shape[0]-0.5, shape[1]-0.5, 0, 0]))['numeric']

        # plot data
        if 'cmap' not in imshow_args:
            # matplotlib Colormap has its own __copy__ implementation:
            #   https://github.com/matplotlib/matplotlib/blob/v3.3.x/lib/matplotlib/colors.py#L616
            imshow_args['cmap'] = copy.copy(plt.cm.jet)
        imshow_args['cmap'].set_bad('k', 1.0)
        im = ax.imshow(mdata.T, interpolation='nearest', origin='lower', aspect='equal',
                       extent=[blc[0], trc[0], blc[1], trc[1]], **imshow_args)

        if maskname is not None and os.path.exists(maskname):
            LOG.info('Overplotting mask from %s', maskname)
            # Create a boolean mask from the mask image data array
            mask_bool = self._collapse_image(maskname, include_mask=False) > 0.5

            # setup structure: 3x3 square of True to prevent diagonal gaps
            struct = generate_binary_structure(2, 2)

            # Get the initial 1-pixel boundary (in-place)
            # boundary: True only at the edges
            boundary = np.empty_like(mask_bool)
            binary_erosion(mask_bool, structure=struct, output=boundary, border_value=0)
            # XOR gives the difference between the mask and its eroded version
            boundary ^= mask_bool

            # Thicken the line:
            # 2 iterations = ~5 pixels wide
            # 1 iteration = ~3 pixels wide
            binary_dilation(boundary, structure=struct, iterations=2, output=boundary)

            # Convert to a masked array so background is transparent
            # We mask out the 'False' values (background)
            boundary_mask = np.ma.masked_where(~boundary, boundary)
            ax.imshow(boundary_mask.T, interpolation='nearest', origin='lower', aspect='equal',
                      extent=[blc[0], trc[0], blc[1], trc[1]], cmap=ListedColormap(['white']), alpha=0.25)

        ax.axis('image')
        lims = ax.axis()

        # make ticks and labels white
        for line in ax.xaxis.get_ticklines() + ax.yaxis.get_ticklines():
            line.set_color('white')
        for labels in ax.xaxis.get_ticklabels() + ax.yaxis.get_ticklabels():
            labels.set_fontsize(0.5 * labels.get_fontsize())

        # colour bar
        if self.exclude_desc:
            height = '80%'
        else:
            height = '50%'
        cax = inset_axes(
            ax,
            width='4%',
            height=height,
            loc='center left',
            bbox_to_anchor=(1.01, 0.0, 1, 1),
            bbox_transform=ax.transAxes,
        )
        cb = plt.colorbar(im, cax=cax)
        fontsize = 8
        cb.ax.tick_params(labelsize=fontsize)
        cb.set_label(brightness_unit, fontsize=fontsize)
        cb.ax.yaxis.set_offset_position('left')

        # plot beam
        if beam is not None:
            beam_patch = mpatches.Ellipse((lims[0] + 0.1 * (lims[1]-lims[0]), lims[2] + 0.1 * (lims[3]-lims[2])),
                                          width=beam[1], height=beam[0],
                                          linestyle='solid', edgecolor='yellow', fill=False,
                                          angle=-beam[2])
            ax.add_patch(beam_patch)

        # add xy labels
        ax.set_xlabel(f'{coord_names[0]} ({coord_units[0]})')
        ax.set_ylabel(f'{coord_names[1]} ({coord_units[1]})')

        # Add the color text box
        if not self.exclude_desc:
            # image reference pixel
            yoff = -0.15
            xoff = 0.0
            yoff = SkyDisplay.plottext(cb.ax, xoff, yoff, 'Reference Position:', 40)
            for i, k in enumerate(coord_refs['string']):
                # note: the labels present the reference value at individual axes of the collapsed image
                # https://casadocs.readthedocs.io/en/latest/api/tt/casatools.image.html#casatools.image.image.collapse
                name_abbreviations = {
                    'Right Ascension': '  R.A.',
                    'Declination': '  Dec.',
                }
                coord_name = coord_names[i]
                for name, abbr in name_abbreviations.items():
                    coord_name = coord_name.replace(name, abbr)
                yoff = SkyDisplay.plottext(cb.ax, xoff, yoff, f'{coord_name}: {k}', 40, mult=0.8)
            # if peaksnr is available for the mom8_fc image, include it in the plot
            if 'mom8_fc' in imagename and mom8_fc_peak_snr is not None:
                yoff = 1.15
                SkyDisplay.plottext(cb.ax, xoff, yoff, 'Peak SNR: {:.5f}'.format(mom8_fc_peak_snr), 40)

            mode_texts = {
                'mean': 'mean',
                'mom0': 'integ. line int. (mom0)',
                'max': 'peak line int. (mom8)',
                'mom8': 'peak line int. (mom8)',
                'center': 'center slice'
            }

            image_info = {'display': mode_texts[collapseFunction]}
            image_info.update(miscinfo)
            # PIPE-2708: improve the virtspw key formatting
            if image_info.get('virtspw') is not None:
                image_info['virtspw'] = utils.find_ranges(image_info['virtspw'])

            type_mapping = {
                'flux': 'pb',
                'mom0_fc': 'Line-free Moment 0',
                'mom8_fc': 'Line-free Moment 8'
            }

            if 'type' in image_info:
                image_info['type'] = type_mapping.get(image_info['type'], image_info['type'])

            if isinstance(image_info.get('band', None), str):
                # Currently only used for VLA specmode='cont' imaging results
                key_color = [('type', 'k'),
                             ('display', 'r'),
                             ('field', 'k'),
                             ('band', 'k'),
                             ('pol', 'k'),
                             ('iter', 'k')]
            else:
                key_color = [('type', 'k'),
                             ('display', 'r'),
                             ('field', 'k'),
                             ('virtspw', 'k'),
                             ('pol', 'k'),
                             ('iter', 'k')]
            labels = [TextArea('%s:%s' % (key, image_info[key]), textprops=dict(color=color))
                      for key, color in key_color
                      if image_info.get(key) is not None]

            txt = HPacker(children=labels, align="baseline", pad=0, sep=7)
            bbox = AnnotationBbox(txt, xy=(0.5, 1.04),
                                  xycoords='axes fraction',
                                  frameon=True,
                                  box_alignment=(0.5, 0.0),
                                  pad=0.3)
            ax.add_artist(bbox)

        # PIPE-997: plot a 41pix-wide PSF inset if the image is larger than 41*3
        if miscinfo.get('type', None) == 'psf':
            # use the same vmin/vmax as the full-size plot.
            if 'norm' not in imshow_args:
                vmin, vmax = im.get_clim()
                imshow_args['norm'] = plt.Normalize(vmin, vmax, clip=True)
            self._plot_psf_inset(ax, mdata, imshow_args, beam=beam, cs=cs)

        # save the image
        fig.savefig(plotfile, bbox_inches='tight', dpi=dpi, pil_kwargs={'optimize': True})
        plt.close(fig)

        if not os.path.exists(plotfile):
            # PIPE-2022: Generate a warning if the PNG file is missing. The
            # message is caught by a local logging handler for the weblog.
            LOG.warning(f'Plot {plotfile} is missing on disk')

        # done with ia.coordsys()
        cs.done()

        return plotfile, coord_names, field_name, band_name

    def _plot_psf_inset(self, ax, mdata, imshow_args, beam=None, cs=None):
        """Plot the PSF inset panel."""

        npix_inset_half = 20
        maxfrac_inset = 1./3
        npix_inset = npix_inset_half*2.+1
        shape = mdata.shape
        if npix_inset < shape[0]*maxfrac_inset or npix_inset < shape[1]*maxfrac_inset:
            x0 = shape[0]//2-npix_inset_half
            x1 = shape[0]//2+npix_inset_half+1
            y0 = shape[1]//2-npix_inset_half
            y1 = shape[1]//2+npix_inset_half+1
            mdata_sub = mdata[x0:x1, y0:y1]
            axinset = ax.inset_axes(bounds=[0.60, 0.02, 0.38, 0.38])

            if cs is not None:
                blc = cs.torel(cs.toworld([-0.5+x0, -0.5+y0, 0, 0]))['numeric']
                trc = cs.torel(cs.toworld([x1-0.5, y1-0.5, 0, 0]))['numeric']
                extent = [blc[0], trc[0], blc[1], trc[1]]
            else:
                # if cs is not available, use a fiducial data coordinate system.
                # but your beam specification needs to be in pix units to get the plot scale
                # right
                extent = [-npix_inset_half-0.5, npix_inset_half+0.5, -npix_inset_half-0.5, npix_inset_half+0.5]

            axinset.imshow(mdata_sub.T, extent=extent,
                           interpolation='nearest', origin='lower', aspect='equal',
                           **imshow_args)

            for spine in ['bottom', 'top', 'right', 'left']:
                axinset.spines[spine].set_color('white')
            axinset.contour(mdata_sub.T, [0.5], colors='k', linestyles='dotted',
                            extent=extent, origin='lower')
            axinset.set_xticks([])
            axinset.set_yticks([])

            if beam is not None:
                beam_patch = mpatches.Ellipse((0, 0), width=beam[1], height=beam[0],
                                              linestyle='solid', edgecolor='k', fill=False,
                                              angle=-beam[2])
                axinset.add_patch(beam_patch)

    @staticmethod
    def plottext(ax, xoff, yoff, text, maxchars, mult=1.0, line_spacing=0.04):
        """Plots text on a Matplotlib Axes object with automatic line breaks.

        This function is designed to be robust and uses standard library
        tools for text wrapping.

        Args:
            ax (matplotlib.axes.Axes): The Axes object to plot the text on.
            xoff (float): World x-coordinate where text is to start (in axes coordinates, 0-1).
            yoff (float): World y-coordinate where text is to start (in axes coordinates, 0-1).
            text (str): The text string to display.
            maxchars (int): The maximum number of characters before a newline is inserted.
            mult (float, optional): Factor by which the text fontsize is to be multiplied.
                                    Defaults to 1.0.
            line_spacing (float, optional): Vertical spacing between lines in axes coordinates.
                                        Defaults to 0.04.

        Returns:
            float: The final y-coordinate after plotting the text.
        """
        lines = textwrap.wrap(text, width=maxchars)

        current_yoff = yoff

        for line in lines:
            ax.text(
                xoff,
                current_yoff,
                line,
                va='top',
                fontsize=mult * 8,                transform=ax.transAxes,
                clip_on=False,
            )
            current_yoff -= line_spacing * mult

        current_yoff -= line_spacing * mult

        return current_yoff
