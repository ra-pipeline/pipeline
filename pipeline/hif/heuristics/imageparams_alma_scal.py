from .imageparams_alma import ImageParamsHeuristicsALMA


class ImageParamsHeuristicsALMAScal(ImageParamsHeuristicsALMA):

    def __init__(self, vislist, spw, observing_run, imagename_prefix='', proj_params=None, contfile=None, linesfile=None, imaging_params={}):
        super().__init__(vislist, spw, observing_run, imagename_prefix, proj_params, contfile, linesfile, imaging_params)
        self.imaging_mode = 'ALMA-SCAL'
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

    def is_selfcal_iteration(self, iteration):
        """"Determine if we need to start the selfcal-solint inner-iteration sequence.

        In the selfcal imaging sequence.
        iter1: initial image: unselfcal imageing
        iter2: i.e. the selfcal lopp
            *solin_prior*iter2.image: imaging for creating selfcal/solint model
            *solin_post*iter2.image: imaging for selfcal/solint QA
        iter3: final image: imaging after selfcal apply
        """
        if iteration == 2:
            return True
        else:
            return False

    # def copy_from_last(self,iteration):
    #     """Copy the last iteration's products at the beginning of the current iteration."""
    #     if iteration >=2 and
    #     return False
