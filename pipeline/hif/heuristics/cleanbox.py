from __future__ import annotations

import os.path
from typing import TYPE_CHECKING, Any

import numpy as np

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.utils as utils
from pipeline.infrastructure import casa_tools

if TYPE_CHECKING:
    import casatools.image
    from pipeline.infrastructure.casa_tools import _logging_image_cls as LoggingImage


LOG = infrastructure.get_logger(__name__)


def analyse_clean_result(multiterm, model, restored, residual, pb, cleanmask, pblimit_image=0.2,
                         pblimit_cleanmask=0.3, cont_freq_ranges=None):

    qaTool = casa_tools.quanta

    if pb == '':
        pb = None

    if multiterm:
        extension = '.tt0'
    else:
        extension = ''

    # get the sum of the model image to find how much flux has been
    # cleaned
    model_sum = None
    if model is not None:
        with casa_tools.ImageReader(model + extension) as image:
            model_stats = image_statistics_per_stokes(image, robust=False, stokescontrol='f')
            model_sum = model_stats['sum'][0]
            LOG.debug('Sum of model: %s' % model_sum)

    LOG.debug('Fixing coordsys of pb and cleanmask')
    with casa_tools.ImageReader(residual + extension) as image:
        csys = image.coordsys()
    if pb is not None:
        with casa_tools.ImageReader(pb + extension) as image:
            image.setcoordsys(csys.torecord())
    if cleanmask is not None and os.path.exists(cleanmask):
        with casa_tools.ImageReader(cleanmask) as image:
            image.setcoordsys(csys.torecord())
    csys.done()

    with casa_tools.ImageReader(residual + extension) as image:
        # get the rms of the residual image inside the cleaned area
        LOG.todo('Cannot use dirname in mask')
        residual_cleanmask_rms = None

        if cleanmask is not None and os.path.exists(cleanmask):
            # Area inside clean mask
            statsmask = f'"{os.path.basename(cleanmask)}" > 0.1'
            resid_clean_stats = image_statistics_per_stokes(image, mask=statsmask, robust=False, stretch=True)

            try:
                residual_cleanmask_rms = resid_clean_stats['rms'][0]
                LOG.info('Residual rms inside cleaned area: %s' % residual_cleanmask_rms)
            except:
                pass

        # and the rms of the residual image outside the cleaned area
        residual_non_cleanmask_rms = None

        if pb is not None and os.path.exists(pb+extension):
            have_mask = True
            statsmask = '("%s" > %f) && ("%s" < %f)' % (os.path.basename(pb)+extension, pblimit_image,
                                                        os.path.basename(pb)+extension, pblimit_cleanmask)
        elif cleanmask is not None and os.path.exists(cleanmask):
            have_mask = True
            # Area outside clean mask
            statsmask = '"%s" < 0.1' % (os.path.basename(cleanmask))
        else:
            have_mask = False
            statsmask = ''

        residual_stats = image_statistics_per_stokes(
            image, stokescontrol='f', mask=statsmask, robust=False, stretch=True)

        try:
            residual_non_cleanmask_rms = residual_stats['rms'][0]
            if have_mask:
                LOG.info('Residual rms in the annulus: %s' % residual_non_cleanmask_rms)
            else:
                LOG.info('Residual rms across full area: %s' % residual_non_cleanmask_rms)
        except:
            pass

        # get the max, min of the residual image (avoiding the edges
        # where spikes can occur)
        if pb is not None and os.path.exists(pb + extension):
            residual_stats = image_statistics_per_stokes(
                image,
                stokescontrol='f',
                mask=f'"{os.path.basename(pb) + extension}" > {pblimit_image:f}',
                robust=False,
                stretch=True,
            )
        else:
            residual_stats = image_statistics_per_stokes(image, stokescontrol='f', robust=False)

        try:
            # This filters just Stokes I. For the time being (PIPE-2464)
            # this seems sufficient. If other Stokes results are needed
            # later, the downstream code in tclean.py needs to be adjusted.
            residual_max = residual_stats['max'][0]
            residual_min = residual_stats['min'][0]
        except:
            residual_max = None
            residual_min = None

        LOG.info('Residual max: %s min: %s', residual_max, residual_min)
        residual_stats = image_statistics_per_stokes(image, stokescontrol='f', robust=True, excludepix=0.0)
        residual_robust_rms = residual_stats['medabsdevmed'][0] * 1.4826  # see CAS-9631
        LOG.debug('residual scaled MAD: %s', residual_robust_rms)

    pbcor_image_min = None
    pbcor_image_min_iquv = None
    pbcor_image_max = None
    pbcor_image_max_iquv = None
    nonpbcor_imagename = None
    nonpbcor_image_non_cleanmask_rms = None
    nonpbcor_image_non_cleanmask_rms_min = None
    nonpbcor_image_non_cleanmask_rms_max = None
    nonpbcor_image_non_cleanmask_robust_rms = None
    nonpbcor_image_non_cleanmask_robust_rms_iquv = None
    nonpbcor_image_non_cleanmask_freq_ch1 = None
    nonpbcor_image_non_cleanmask_freq_chN = None
    nonpbcor_image_non_cleanmask_freq_frame = None
    nonpbcor_image_non_cleanmask_rms_iquv = None
    nonpbcor_image_non_cleanmask_rms_min_iquv = None
    nonpbcor_image_non_cleanmask_rms_max_iquv = None
    nonpbcor_image_cleanmask_spectrum = None
    nonpbcor_image_cleanmask_spectrum_pblimit = None
    nonpbcor_image_cleanmask_npoints = None
    nonpbcor_image_statsmask = None
    if restored not in [None, '']:
        # get min and max of the pb-corrected cleaned result
        with casa_tools.ImageReader(restored.replace('.image', '.image%s' % extension)) as image:
            if pb is not None and os.path.exists(pb+extension):
                have_mask = True
                # Default is area pb > 0.3
                statsmask = '"%s" > %f' % (os.path.basename(pb)+extension, pblimit_cleanmask)
            elif cleanmask is not None and os.path.exists(cleanmask):
                have_mask = True
                # Area inside clean mask
                statsmask = '"%s" > 0.1' % (os.path.basename(cleanmask))
            else:
                have_mask = False
                statsmask = ''

            if 'TARGET' in image.miscinfo().get('intent', None):
                image_stats = image.statistics(mask=statsmask, stretch=True)
                # For polarization calibrators we need stats for I, Q, U and V, so exclude the
                # Stokes axis from collapsing.
                image_stats_iquv = image_statistics_per_stokes(image, stokescontrol='a', mask=statsmask, stretch=True)
            else:
                # Restrict region to inner 25% x 25% of the image for calibrators to
                # avoid picking up sidelobes (PIPE-611)
                shape = image.shape()
                rgTool = casa_tools.regionmanager
                nPixels = max(shape[0], shape[1])
                region = rgTool.box([nPixels*0.375-1, nPixels*0.375-1, 0, 0], [nPixels*0.625-1, nPixels*0.625-1, shape[2]-1, shape[3]-1])
                image_stats = image.statistics(mask=statsmask, region=region, stretch=True)
                # For polarization calibrators we need stats for I, Q, U and V, so exclude the
                # Stokes axis from collapsing.
                image_stats_iquv = image_statistics_per_stokes(image, stokescontrol='a', mask=statsmask,region=region, stretch=True)
                rgTool.done()

            pbcor_image_min = image_stats['min'][0]
            pbcor_image_min_iquv = image_stats_iquv['min']
            pbcor_image_max = image_stats['max'][0]
            pbcor_image_max_iquv = image_stats_iquv['max']

            if have_mask:
                LOG.debug('Clean pb-corrected image min in cleaned area: %s' % pbcor_image_min)
                LOG.debug('Clean pb-corrected image max in cleaned area: %s' % pbcor_image_max)
            else:
                LOG.debug('Clean pb-corrected image min in full area: %s' % pbcor_image_min)
                LOG.debug('Clean pb-corrected image max in full area: %s' % pbcor_image_max)

        # get RMS in non cleanmask area of non-pb-corrected cleaned result
        if restored.find('.image.pbcor') != -1:
            nonpbcor_imagename = restored.replace('.image.pbcor', '.image%s' % extension)
        else:
            nonpbcor_imagename = restored.replace('.image', '.image%s' % extension)

        # If possible use flattened clean mask for exclusion of areas for all spectral channels
        flattened_mask = None
        if cleanmask is not None and os.path.exists(cleanmask):
            if '.mask' in cleanmask:
                flattened_mask = cleanmask.replace('.mask', '.mask.flattened')
            elif '.cleanmask' in cleanmask:
                flattened_mask = cleanmask.replace('.cleanmask', '.cleanmask.flattened')
            else:
                raise 'Cannot handle clean mask name %s' % (os.path.basename(cleanmask))

            with casa_tools.ImageReader(cleanmask) as image:
                image_shape = image.shape()
                if image_shape[2] == 1 and image_shape[3] == 1:
                    flattened_mask = cleanmask
                    flattened_mask_image = image
                else:
                    flattened_mask_image = image.collapse(
                        function='max', axes=[2, 3], outfile=flattened_mask, overwrite=True)
                try:
                    npoints_mask = flattened_mask_image.statistics(mask='"%s" > 0.1' % (os.path.basename(flattened_mask)), axes=[0, 1, 3], robust=False, stretch=True)['npts'][0]
                    if npoints_mask.shape != (0,):
                        nonpbcor_image_cleanmask_npoints = int(npoints_mask)
                    else:
                        nonpbcor_image_cleanmask_npoints = 0
                except:
                    nonpbcor_image_cleanmask_npoints = 0
                flattened_mask_image.done()

        with casa_tools.ImageReader(nonpbcor_imagename) as image:
            # Get the image frequency axis for later plotting.
            imhead = image.summary(list=False)
            lcs = image.coordsys()
            try:
                csys = image.coordsys()
                freq_axis = csys.findaxisbyname('spectral')
                csys.done()
            except:
                num_axes = image.shape().shape[0]
                if num_axes > 3:
                    LOG.warning("Can't find spectral axis. Assuming it is 3.")
                    freq_axis = 3
                elif num_axes > 2:
                    LOG.warning("Can't find spectral axis. Assuming it is 2.")
                    freq_axis = 2
                elif num_axes == 2:
                    LOG.error("No spectral axis found")
                    freq_axis = -1
            lcs.done()
            nonpbcor_image_non_cleanmask_freq_ch1 = qaTool.quantity(imhead['refval'][freq_axis] - imhead['refpix'][freq_axis] * imhead['incr'][freq_axis], imhead['axisunits'][freq_axis])
            nonpbcor_image_non_cleanmask_freq_chN = qaTool.quantity(imhead['refval'][freq_axis] + (imhead['shape'][freq_axis] - 1 - imhead['refpix'][freq_axis]) * imhead['incr'][freq_axis], imhead['axisunits'][freq_axis])
            # Get the spectral reference. Unfortunately this is coded in text
            # messages rather than a key/value pair. Hence the parsing code.
            try:
                for msg in imhead['messages'][1].split('\n'):
                    msg_l = msg.lower()
                    if 'spectral' in msg_l and 'reference' in msg_l:
                        nonpbcor_image_non_cleanmask_freq_frame = msg.split(':')[1].strip()
            except:
                LOG.warning('Cannot determine spectral reference in %s. Assuming it is LSRK.' % (nonpbcor_imagename))
                nonpbcor_image_non_cleanmask_freq_frame = 'LSRK'

            # define mask outside the cleaned area
            image_stats = None
            image_stats_iquv = None
            if pb is not None and os.path.exists(pb+extension) and cleanmask is not None and os.path.exists(cleanmask):
                pb_name = os.path.basename(pb)+extension
                have_mask = True
                # Annulus without clean mask
                statsmask = '("%s" < 0.1) && ("%s" > %f) && ("%s" < %f)' % \
                            (os.path.basename(flattened_mask), \
                             pb_name, pblimit_image, \
                             pb_name, pblimit_cleanmask)
                # Check for number of points per channel (PIPE-541):
                try:
                    image_stats = image.statistics(mask=statsmask, robust=True, axes=[0, 1, 2], algorithm='chauvenet', maxiter=5, stretch=True)
                    # For IQUV images we need the individual values along the Stokes axis
                    image_stats_iquv = image.statistics(mask=statsmask, robust=True, axes=[0, 1], algorithm='chauvenet', maxiter=5, stretch=True)
                    if image_stats['npts'].shape == (0,) or np.median(image_stats['npts']) < 10.0:
                        # Switch to full annulus to avoid zero noise spectrum due to voluminous mask
                        LOG.warning('Using full annulus for noise spectrum due to voluminous mask "%s".' %
                                    (os.path.basename(cleanmask)))
                        statsmask = '("%s" > %f) && ("%s" < %f)' % (pb_name, pblimit_image,
                                                                    pb_name, pblimit_cleanmask)
                        image_stats = None
                        image_stats_iquv = None
                except Exception as e:
                    # Try full annulus as a fallback
                    LOG.exception('Using full annulus for noise spectrum due to voluminous mask "%s".' % (os.path.basename(cleanmask)), exc_info=e)
                    statsmask = '("%s" > %f) && ("%s" < %f)' % (pb_name, pblimit_image,
                                                                pb_name, pblimit_cleanmask)
                    image_stats = None
                    image_stats_iquv = None
            elif pb is not None and os.path.exists(pb+extension):
                pb_name = os.path.basename(pb)+extension
                have_mask = True
                # Full annulus
                statsmask = '("%s" > %f) && ("%s" < %f)' % (pb_name, pblimit_image,
                                                            pb_name, pblimit_cleanmask)
            elif cleanmask is not None and os.path.exists(cleanmask):
                have_mask = True
                # Area outside clean mask
                statsmask = '"%s" < 0.1' % (os.path.basename(flattened_mask))
            else:
                # Full area
                have_mask = False
                statsmask = ''

            try:
                # Get image RMS for all channels (this is for the weblog)
                # Avoid repeat if the check for npts was done and is OK.
                if image_stats is None:
                    image_stats = image.statistics(mask=statsmask, robust=True, axes=[0, 1, 2], algorithm='chauvenet', maxiter=5, stretch=True)
                    image_stats_iquv = image.statistics(mask=statsmask, robust=True, axes=[0, 1], algorithm='chauvenet', maxiter=5, stretch=True)

                nonpbcor_image_statsmask = statsmask

                # Filter continuum frequency ranges if given
                # TODO: The second condition checks if this is an IQUV cube. This
                # should be done more directly via extra method parameters.
                if cont_freq_ranges not in (None, '', 'NONE', 'ALL', 'ALLCONT'):
                    # TODO: utils.freq_selection_to_channels uses casa_tools.image to get the frequency axis
                    #       and closes the global pipeline image tool. The context manager wrapped tool
                    #       used in this "with" statement is a different instance, so this is OK, but stacked
                    #       use of casa_tools.image might lead to unexpected results.
                    cont_chan_ranges = utils.freq_selection_to_channels(nonpbcor_imagename, cont_freq_ranges)
                    cont_chan_indices = np.hstack([np.arange(start, stop+1) for start, stop in cont_chan_ranges])
                    nonpbcor_image_non_cleanmask_rms_vs_chan = image_stats['rms'][cont_chan_indices]
                    if len(image_stats_iquv['rms'].shape) == 2:
                        nonpbcor_image_non_cleanmask_rms_vs_chan_iquv = image_stats_iquv['rms'][:,cont_chan_indices]
                    else:
                        nonpbcor_image_non_cleanmask_rms_vs_chan_iquv = image_stats_iquv['rms']
                else:
                    nonpbcor_image_non_cleanmask_rms_vs_chan = image_stats['rms']
                    nonpbcor_image_non_cleanmask_rms_vs_chan_iquv = image_stats_iquv['rms']

                nonpbcor_image_non_cleanmask_robust_rms = image_stats['medabsdevmed'] * 1.4826
                nonpbcor_image_non_cleanmask_robust_rms_iquv = image_stats_iquv['medabsdevmed'] * 1.4826

                nonpbcor_image_non_cleanmask_rms_median = np.median(nonpbcor_image_non_cleanmask_rms_vs_chan)
                nonpbcor_image_non_cleanmask_rms_mean = np.mean(nonpbcor_image_non_cleanmask_rms_vs_chan)
                nonpbcor_image_non_cleanmask_rms_min = np.min(nonpbcor_image_non_cleanmask_rms_vs_chan)
                nonpbcor_image_non_cleanmask_rms_max = np.max(nonpbcor_image_non_cleanmask_rms_vs_chan)
                nonpbcor_image_non_cleanmask_rms = nonpbcor_image_non_cleanmask_rms_median

                if len(image_stats_iquv['rms'].shape) == 2:
                    nonpbcor_image_non_cleanmask_rms_median_iquv = np.median(nonpbcor_image_non_cleanmask_rms_vs_chan_iquv, axis=(1,))
                    nonpbcor_image_non_cleanmask_rms_mean_iquv = np.mean(nonpbcor_image_non_cleanmask_rms_vs_chan_iquv, axis=(1,))
                    nonpbcor_image_non_cleanmask_rms_min_iquv = np.min(nonpbcor_image_non_cleanmask_rms_vs_chan_iquv, axis=(1,))
                    nonpbcor_image_non_cleanmask_rms_max_iquv = np.max(nonpbcor_image_non_cleanmask_rms_vs_chan_iquv, axis=(1,))
                else:
                    nonpbcor_image_non_cleanmask_rms_median_iquv = nonpbcor_image_non_cleanmask_rms_vs_chan_iquv
                    nonpbcor_image_non_cleanmask_rms_mean_iquv = nonpbcor_image_non_cleanmask_rms_vs_chan_iquv
                    nonpbcor_image_non_cleanmask_rms_min_iquv = nonpbcor_image_non_cleanmask_rms_vs_chan_iquv
                    nonpbcor_image_non_cleanmask_rms_max_iquv = nonpbcor_image_non_cleanmask_rms_vs_chan_iquv

                nonpbcor_image_non_cleanmask_rms_iquv = nonpbcor_image_non_cleanmask_rms_median_iquv

                if have_mask:
                    area_text = 'annulus'
                else:
                    area_text = 'full image'
                LOG.info('Clean image statistics (%s) for %s: rmsmedian: %s Jy/bm rmsmean: %s Jy/bm rmsmin:'
                         ' %s Jy/bm rmsmax: %s Jy/bm' % \
                    (area_text, os.path.basename(nonpbcor_imagename),
                     nonpbcor_image_non_cleanmask_rms_median,
                     nonpbcor_image_non_cleanmask_rms_mean,
                     nonpbcor_image_non_cleanmask_rms_min,
                     nonpbcor_image_non_cleanmask_rms_max))
            except Exception as e:
                nonpbcor_image_non_cleanmask_rms_median, \
                nonpbcor_image_non_cleanmask_rms_mean, \
                nonpbcor_image_non_cleanmask_rms_min = \
                nonpbcor_image_non_cleanmask_rms_max = \
                nonpbcor_image_non_cleanmask_rms = \
                    -999.0
                nonpbcor_image_non_cleanmask_rms_median_iquv = np.array([-999.0]*4)
                nonpbcor_image_non_cleanmask_rms_mean_iquv = np.array([-999.0]*4)
                nonpbcor_image_non_cleanmask_rms_min_iquv = np.array([-999.0]*4)
                nonpbcor_image_non_cleanmask_rms_max_iquv = np.array([-999.0]*4)
                nonpbcor_image_non_cleanmask_rms_iquv = np.array([-999.0]*4)

                LOG.warning('Exception while determining image RMS for %s: %s' % (nonpbcor_imagename, e))

            # Get the flux density spectrum in the clean mask area if available
            if nonpbcor_image_cleanmask_npoints not in (None, 0):
                # Area in flattened clean mask
                spectrum_mask = '"%s" > 0.1' % (os.path.basename(flattened_mask))
            elif pb is not None:
                # Area of pb > pblimit_cleanmask
                spectrum_mask = '"%s" > %f' % (os.path.basename(pb)+extension, pblimit_cleanmask)
                nonpbcor_image_cleanmask_spectrum_pblimit = pblimit_cleanmask
            else:
                spectrum_mask = None

            # Because image.getprofile(axis=freq_axis) doesn't work on an image/cube with more than
            # one polarization plane (e.g. VLASS fullstokes images), we first create a stokes-I only
            # image with 'spectrum_mask' included, and then run ia.getprofile().
            # note: the stoke-i extraction can also be done with imagepol.stokesi()

            image_csys = image.coordsys()
            rgTool = casa_tools.regionmanager
            region = rgTool.frombcs(csys=image_csys.torecord(), shape=image.shape(), stokes='I', stokescontrol='a')
            image_csys.done()
            rgTool.done()

            image_stokesi = image.subimage(region=region, mask=spectrum_mask, dropdeg=False, stretch=True)
            nonpbcor_image_cleanmask_spectrum = image_stokesi.getprofile(function='flux', axis=freq_axis)['values']
            image_stokesi.done()

    return (residual_cleanmask_rms, residual_non_cleanmask_rms, residual_min, residual_max,
            nonpbcor_image_non_cleanmask_rms_min, nonpbcor_image_non_cleanmask_rms_max,
            nonpbcor_image_non_cleanmask_rms, pbcor_image_min, pbcor_image_max, residual_robust_rms,
            {'nonpbcor_imagename': nonpbcor_imagename,
             'nonpbcor_image_non_cleanmask_freq_ch1': nonpbcor_image_non_cleanmask_freq_ch1,
             'nonpbcor_image_non_cleanmask_freq_chN': nonpbcor_image_non_cleanmask_freq_chN,
             'nonpbcor_image_non_cleanmask_freq_frame': nonpbcor_image_non_cleanmask_freq_frame,
             'nonpbcor_image_non_cleanmask_robust_rms': nonpbcor_image_non_cleanmask_robust_rms,
             'nonpbcor_image_non_cleanmask_robust_rms_iquv': nonpbcor_image_non_cleanmask_robust_rms_iquv,
             'nonpbcor_image_cleanmask_spectrum': nonpbcor_image_cleanmask_spectrum,
             'nonpbcor_image_cleanmask_spectrum_pblimit': nonpbcor_image_cleanmask_spectrum_pblimit,
             'nonpbcor_image_cleanmask_npoints': nonpbcor_image_cleanmask_npoints,
             'cont_freq_ranges': cont_freq_ranges,
             'nonpbcor_image_statsmask': nonpbcor_image_statsmask},
            pbcor_image_min_iquv, pbcor_image_max_iquv, nonpbcor_image_non_cleanmask_rms_min_iquv,
            nonpbcor_image_non_cleanmask_rms_max_iquv, nonpbcor_image_non_cleanmask_rms_iquv)


def image_statistics_per_stokes(
    image: casatools.image.image | LoggingImage,
    stokescontrol: str = 'a',
    region: dict | None = None,
    **kwargs: Any,
) -> dict[str, np.ndarray]:
    """Compute statistics for each Stokes plane of a 4D CASA image cube.

    This function iterates through the Stokes planes (e.g., I, Q, U, V) of a 4D image cube, computes a standard
    set of statistics for each plane, and returns the results in a dictionary. The expected image shape is
    [nx, ny, nstokes, nfreq].

    It is used as a workaround for CAS-14660 when deriving per-Stokes cube statistics.

    Args:
        image: A CASA image object with a .shape() method and .statistics() method.
        stokescontrol: If 'f', only the first Stokes plane (index 0) is processed; otherwise all planes are processed.
        region: Optional region record to constrain the statistics to a specific area.
        **kwargs: Passed directly to the image's .statistics() method (e.g., verbose, stretch).

    Returns:
        A dictionary mapping statistic names (e.g., 'max', 'mean', 'rms') to NumPy arrays.
        Each array contains values for the processed Stokes planes.

    Raises:
        AttributeError: If the image object lacks a .shape() method.
        ValueError: If the image is not 4-dimensional.

    Example:
        >>> stats = image_statistics_per_stokes(my_image, stokescontrol='a', verbose=True)
        >>> print(stats['mean'])  # Mean values for all Stokes planes
        [0.001, 0.002, 0.001, 0.003]
    """
    # Validate input image
    try:
        img_shape = image.shape()
    except AttributeError as e:
        raise AttributeError("The 'image' object must provide a .shape() method.") from e
    if len(img_shape) != 4:
        raise ValueError(f'Expected 4D image, got {len(img_shape)}D with shape {img_shape}.')

    # Avoid CAS-14660 bug by discarding explicit axis specification
    kwargs.pop('axes', None)

    # Initialize statistics containers
    stats_items = [
        'max',
        'mean',
        'medabsdevmed',
        'median',
        'min',
        'npts',
        'q1',
        'q3',
        'rms',
        'sigma',
        'sum',
        'sumsq',
    ]
    stats_per_stokes: dict[str, list[float]] = {key: [] for key in stats_items}

    # Handle region specification
    if isinstance(region, dict) and {'blc', 'trc'} <= region.keys() and region.get('name') == 'LCSlicer':
        # rg.box uses zero-based indices; region records return one-based indices, so convert back
        blc = region['blc'].copy() - 1
        trc = region['trc'].copy() - 1
        if stokescontrol == 'f':
            trc[2] = blc[2]
    else:
        if region:
            LOG.warning('Unsupported region format %r; ignoring.', region)
        blc = [0, 0, 0, 0]
        stokes_last = 0 if stokescontrol == 'f' else img_shape[2] - 1
        trc = [img_shape[0] - 1, img_shape[1] - 1, stokes_last, img_shape[3] - 1]

    rg = casa_tools.regionmanager
    for stokes_idx in range(int(blc[2]), int(trc[2]) + 1):
        blc_stokes, trc_stokes = blc.copy(), trc.copy()
        blc_stokes[2] = trc_stokes[2] = stokes_idx
        region_stokes = rg.box(blc=blc_stokes, trc=trc_stokes)

        stats_current = image.statistics(region=region_stokes, **kwargs)
        for key in stats_per_stokes:
            if key in stats_current and stats_current[key].size:
                stats_per_stokes[key].append(stats_current[key][0])

    return {key: np.array(values) for key, values in stats_per_stokes.items()}
