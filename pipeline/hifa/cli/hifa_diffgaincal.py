import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.diffgaincal.diffgaincal.DiffGaincalInputs.__init__
@utils.cli_wrapper
def hifa_diffgaincal(vis=None, flagging_frac_limit=None, hm_spwmapmode=None, missing_scans_frac_limit=None):
    """Derive SpW phase offsets from differential gain calibrator.

    This task creates the spectral window phase offset table used to allow
    calibrating the "on-source" spectral setup with phase gains from a
    "reference" spectral setup. Currently this setup with two different
    SpectralSpecs is used by the band-to-band mode, for a high and low 
    frequency band. 
  
    A bright point source quasar, called the Differential Gain Calibrator 
    (DIFFGAIN) source, is used for this purpose. This DIFFGAIN source is typically 
    observed in groups of interleaved "reference" and "on-source" scans. These
    blocks typically occur once at the start and once at the end of the
    observation. In very long observations, there may be a group of scans
    occurring during the middle. 

    The procedure for the phase calibration process is as follow:

    - ``reference`` calibration uses the "reference" spectral setup, the "low"
      frequency for band-to-band observations. The solint is fixed as 'inf' (i.e.
      solutions are made per scan). Spectral window combination is governed by
      the hm_spwmapmode options described below. In standard pipeline operation
      ``auto`` is used - basing spw combination upon SNR and flagging level.
      These reference phase solutions are later applied on-the-fly while solving 
      the (band-to-band) ``phase offset``. The premise being that the ``reference``
      solutions correct for atmospheric phase variability.

    - ``phase offset`` (i.e. the band-to-band correction) calibration uses the
      "on-source" spectral setup, the "high" frequency for band-to-band observations.
      The above ``reference`` phase corrections are applied on-the-fly using a
      linearPD interpolation - this corrects (scales) the phases according to the 
      different ratio of the frequency bands. The solint = 'inf' and each group of
      scan blocks (typically at the start and end of the observation) are combined
      respectively. The phase offset solution generally comprises of 2 time
      solutions per spw, per polarization. Spectral window combination is governed
      by the hm_spwmapmode options described below. ``auto`` is used - basing spw
      combination upon SNR and flag data. These solutions are stored in the 
      pipeline context for later application to the TARGET and CHECK intent(s).
    
    - ``residual offset`` solutions are produced by applying both ``reference`` and
      band-to-band ``phase offset`` solutions to the 'on-source' DIFFGAIN intent
      on-the-fly, and subsequently solving phases per spw, per scan using
      solint='inf'.  Spectral window combination is governed by the hm_spwmapmode
      options described below. ``auto`` is used - basing spw combination upon SNR
      and flagging level.


    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Derive SpW phase offsets from differential gain calibrator.

        >>> hifa_diffgaincal()

    """
