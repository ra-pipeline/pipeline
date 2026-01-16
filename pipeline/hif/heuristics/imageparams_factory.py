from .imageparams_alma import ImageParamsHeuristicsALMA
from .imageparams_alma_scal import ImageParamsHeuristicsALMAScal
from .imageparams_alma_srdp import ImageParamsHeuristicsALMASrdp
from .imageparams_vla import ImageParamsHeuristicsVLA
from .imageparams_vla_scal import ImageParamsHeuristicsVLAScal
from .imageparams_vlass_quick_look import ImageParamsHeuristicsVlassQl
from .imageparams_vlass_single_epoch_continuum import (
    ImageParamsHeuristicsVlassSeCont,
    ImageParamsHeuristicsVlassSeContAWPP001,
    ImageParamsHeuristicsVlassSeContAWP2,
    ImageParamsHeuristicsVlassSeContAWP2P001,
    ImageParamsHeuristicsVlassSeContAWPHPG,
    ImageParamsHeuristicsVlassSeContAWPHPGP001,
    ImageParamsHeuristicsVlassSeContMosaic,
)
from .imageparams_vlass_single_epoch_cube import ImageParamsHeuristicsVlassSeCube
from .imageparams_vlass_single_epoch_taper import ImageParamsHeuristicsVlassSeTaper


class ImageParamsHeuristicsFactory(object):
    """Imaging heuristics factory class."""

    @staticmethod
    def getHeuristics(vislist, spw, observing_run, imagename_prefix='', proj_params=None, contfile=None, linesfile=None, imaging_params={}, processing_intents={}, imaging_mode='ALMA'):
        if imaging_mode == 'ALMA':
            # ALMA standard
            return ImageParamsHeuristicsALMA(vislist, spw, observing_run, imagename_prefix, proj_params, contfile, linesfile, imaging_params, processing_intents)
        if imaging_mode == 'ALMA-SCAL':
            # ALMA self-calibration
            return ImageParamsHeuristicsALMAScal(vislist, spw, observing_run, imagename_prefix, proj_params, contfile, linesfile, imaging_params, processing_intents)
        if imaging_mode == 'ALMA-SRDP':
            # ALMA SRDP/AUDI
            return ImageParamsHeuristicsALMASrdp(vislist, spw, observing_run, imagename_prefix, proj_params, contfile, linesfile, imaging_params, processing_intents)
        if imaging_mode in ['VLA', 'JVLA', 'EVLA']:  # VLA but not VLASS
            # VLA-PI standard
            return ImageParamsHeuristicsVLA(vislist, spw, observing_run, imagename_prefix, proj_params, contfile, linesfile, imaging_params, processing_intents)
        if imaging_mode in ['VLA-SCAL', 'JVLA-SCAL', 'EVLA-SCAL']:
            # VLA-PI self-calibration
            return ImageParamsHeuristicsVLAScal(vislist, spw, observing_run, imagename_prefix, proj_params, contfile, linesfile, imaging_params, processing_intents)
        if imaging_mode == 'VLASS-QL':  # quick look
            # VLASS QuickLook
            return ImageParamsHeuristicsVlassQl(vislist, spw, observing_run, imagename_prefix, proj_params, contfile, linesfile, imaging_params, processing_intents)
        if imaging_mode in ['VLASS-SE-CONT', 'VLASS-SE-CONT-AWP', 'VLASS-SE-CONT-AWP-P032']:
            # VLASS single epoch continuum, gridder='awp', default to wprojplanes=32
            return ImageParamsHeuristicsVlassSeCont(vislist, spw, observing_run, imagename_prefix, proj_params, contfile, linesfile, imaging_params, processing_intents)
        if imaging_mode == 'VLASS-SE-CONT-AWP-P001':
            # VLASS single epoch continuum, gridder='awp', wprojplanes=1
            return ImageParamsHeuristicsVlassSeContAWPP001(vislist, spw, observing_run, imagename_prefix, proj_params, contfile, linesfile, imaging_params, processing_intents)
        if imaging_mode in ['VLASS-SE-CONT-AWP2', 'VLASS-SE-CONT-AWP2-P032']:
            # VLASS single epoch continuum, gridder='awp2', default to wprojplanes=32
            return ImageParamsHeuristicsVlassSeContAWP2(vislist, spw, observing_run, imagename_prefix, proj_params, contfile, linesfile, imaging_params, processing_intents)
        if imaging_mode == 'VLASS-SE-CONT-AWP2-P001':
            # VLASS single epoch continuum, gridder='awp2', wprojplanes=1
            return ImageParamsHeuristicsVlassSeContAWP2P001(vislist, spw, observing_run, imagename_prefix, proj_params, contfile, linesfile, imaging_params, processing_intents)
        if imaging_mode in ['VLASS-SE-CONT-AWPHPG', 'VLASS-SE-CONT-AWPHPG-P032']:
            # VLASS single epoch continuum, gridder='awphpg', default to wprojplanes=32
            return ImageParamsHeuristicsVlassSeContAWPHPG(vislist, spw, observing_run, imagename_prefix, proj_params, contfile, linesfile, imaging_params, processing_intents)
        if imaging_mode == 'VLASS-SE-CONT-AWPHPG-P001':
            # VLASS single epoch continuum, gridder='awphpg', wprojplanes=1
            return ImageParamsHeuristicsVlassSeContAWPHPGP001(vislist, spw, observing_run, imagename_prefix, proj_params, contfile, linesfile, imaging_params, processing_intents)
        if imaging_mode == 'VLASS-SE-CONT-MOSAIC':
            # VLASS single epoch continuum, gridder='mosaic'
            return ImageParamsHeuristicsVlassSeContMosaic(vislist, spw, observing_run, imagename_prefix, proj_params, contfile, linesfile, imaging_params, processing_intents)
        if imaging_mode == 'VLASS-SE-CUBE':  # single epoch cube
            # VLASS single epoch continuum, gridder='mosaic'
            return ImageParamsHeuristicsVlassSeCube(vislist, spw, observing_run, imagename_prefix, proj_params, contfile, linesfile, imaging_params, processing_intents)
        if imaging_mode == 'VLASS-SE-TAPER':
            # VLASS single epoch taper, **NOT** tested/used
            return ImageParamsHeuristicsVlassSeTaper(vislist, spw, observing_run, imagename_prefix, proj_params, contfile, linesfile, imaging_params, processing_intents)

        raise Exception(f'Unknown imaging mode: {imaging_mode}')
