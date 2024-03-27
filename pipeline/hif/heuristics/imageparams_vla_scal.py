from .imageparams_vla import ImageParamsHeuristicsVLA


class ImageParamsHeuristicsVLAScal(ImageParamsHeuristicsVLA):

    def __init__(self, vislist, spw, observing_run, imagename_prefix='', proj_params=None, contfile=None,
                 linesfile=None, imaging_params={}):
        super().__init__(vislist, spw, observing_run, imagename_prefix, proj_params, contfile, linesfile, imaging_params)
        self.image_mode = 'VLA-SCAL'
        self.selfcal = True

    def keep_iterating(
            self, iteration, hm_masking, tclean_stopcode, dirty_dynamic_range, residual_max, residual_robust_rms, field, intent, spw,
            specmode):
        """Determine if another tclean iteration is necessary."""
        if iteration in [0, 1, 2]:
            return True, hm_masking
        else:
            return False, hm_masking

    def threshold(self, iteration, threshold, hm_masking):
        if iteration == 0:
            return '0.0mJy'
        else:
            return threshold

    def get_autobox_params(self, iteration, intent, specmode, robust):
        """Default auto-boxing parameters."""

        sidelobethreshold = None
        noisethreshold = None
        lownoisethreshold = None
        negativethreshold = None
        minbeamfrac = None
        growiterations = None
        dogrowprune = None
        minpercentchange = None
        fastnoise = None

        return (sidelobethreshold, noisethreshold, lownoisethreshold, negativethreshold, minbeamfrac, growiterations,
                dogrowprune, minpercentchange, fastnoise)
