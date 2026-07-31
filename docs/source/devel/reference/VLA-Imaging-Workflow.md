# VLA interferometry imaging workflow

List of differences compared to the ALMA interferometry imaging workflow (ALMA-Imaging-Workflow.md)

Related recipes and template: procedure_hifv_contimage, procedure_hifv_calimage, template_hifv_contimage
Related tickets: PIPE-673

- hif_checkproductsize

  - task parameter
    - maximize (defaults to -1 for backward compatibility, set to 16384 for VLA) 
      Mitigate continuum image size by changing pixel per beam (min. 4). If `imsize` still larger than limit, 
      then truncate image. Mitigation parameters for different targets and bands are independent.

- hif_makeimlist

  - minimum task parameters:
    - intent (default to 'TARGET')
    - spw (defaults to science spws per band)
    - specmode (defaults to 'cont', no cube imaging at the moment)

  - create list of imaging targets with these parameters per target set:
    - heuristics instance
    - field
    - spw (for specmode='cont' remove spws without data )
    - cell (determine it independently for targets and bands)
    - imsize (determine it independently for targets and bands, PB response of 0.294 for K-band and higher frequencies, 0.016 for Ku band and  lower)
    - specmode ('cont')
    - nbin (not used)
    - gridder ('standard')
    - uvrange (per target and band, omit first 5% of baselines if emission is extended)


- hif_makeimages

  - set additional parameters via task interface:
    - hm_masking ('none')
    - hm_cyclefactor (3)

  - run hif_tclean per imaging target and band

- hif_tclean

  - pblimit=-0.1 to not clip images
  - determine deconvolver ('mtmfs' for 'cont')
  - determine nterms (2 if fractional bandwidth > 10% else 1)
  - default to robust = 0.5
  - calculate sensitivity
    - sensitivity calculations is optimized for ALMA, may not be precise for VLA continumm images
  - clean down to nsigma=5.0, threshold is set to 0.0mJy (only nsigma threshold is used)
  - make dirty image
  - calculate dirty cube statistics using annuli (pb range 0.2/0.3)
  - caclulate niter using beam / mask size heuristics and threshold=nsigma*residual_robust_rms, limit values to the [10000,10000000] range
  - calculate clean continuum image statistics using annuli (pb range 0.2/0.3)
