# Low signal-to-noise workflow

When users propose to use ALMA via the [Observing Tool](https://almascience.eso.org/proposing/observing-tool), the default will be to use "observatory calibration".
In such a case, the observatory is responsible for selecting and observing appropriate calibrators
(BANDPASS, AMPLITUDE and PHASE intents for standard interferometric observations).
As part of ongoing observatory tasks, fluxes of quasars are monitored and stored in a
([ALMA source catalogue](https://almascience.eso.org/sc/)).
When running a project at the telescope the control software will assess the
project and will select the calibrators for the observation. This is the point
where a low signal-to-noise (SNR) workflow can begin, and one which the ({doc}`ALMA Pipeline <../overview>`)
is designed to handle.


## What are low SNR calibrators

For a given ALMA observation the integration and scan durations for calibrators are preset as are the
initially required signal-to-noise values such that calibration will be successful. Calibrator sources are
selected as to be strong enough as to provide sufficient signal for antenna based calibration solves. 
For targets in some parts of the sky, there may not be a bright enough quasar close enough to the target to achieve the necessary signal-to-noise in each individual spectral window.
The control software will then instead search for appropriate quasars assuming that the spectral windows can be combined in calibration by the ALMA Pipeline low SNR calibration workflow.

Despite the calibrator monitoring employed at ALMA, given that the thousands of calibrators are quasars and can
vary, it is possible that the fluxes are lower than was assumed at runtime when selected.
Thus, calibrators can fall into a low SNR category even if they were not initially expected to.
In some cases already low SNR calibrators can become even weaker, i.e. 'very' low SNR and the ALMA Pipeline will employ
specific low SNR workflow heuristics as to calibrate, as best as feasibly possible, the observations.


## Typical low SNR observations
A large percentage of all ALMA observations have bright calibrators and do not invoke any low SNR workflow.
Those that do typically fall into the following categories:

- High frequency (Band 9 and 10) observations on the 12 m array.
- Higher frequency observations (>Band 7) with the ACA.
  - At Bands 9 and 10 ACA observations are often 'very' low SNR.
- Observations with specifically very narrow bandwidths.
  - The effect is exaggerated if at higher frequencies (>Band 8).
- Observations with spectral windows in low atmospheric transmission regions.

The situation is specifically worse for higher frequency bands because the quasars used for calibration
naturally have a decreasing flux with increasing frequency. There are fewer and fewer
strong calibrators distributed over the entire sky, and thus finding calibrators that
have high SNR for any given science target is not feasible.

## Pipeline low SNR workflow

The ALMA Pipeline low SNR workflow heuristics are, since PL2026, embedded throughout all calibration
tasks as to make the best judgement in performing phase based solves, as detailed below in stage running order:

- {func}`~pipeline.hifa.cli.hifa_wvrgcalflag`: In order to establish the improvement factor after
  WVR application, phase solutions are generated with and without WVR for both the BANDPASS and PHASE
  intents and subsequently compared. However, prior to these, the data must have a bandpass calibration
  pre-applied, and in order to solve the bandpass, the BANDPASS intent phaseup must first be performed.
  The phaseup process used is that encoded for {func}`~pipeline.hifa.cli.hifa_bandpass` (`almaphcorbandpass.py`), but with a
  ``phaseupsnr=5``. The lower SNR limit, compared with {func}`~pipeline.hifa.cli.hifa_bandpass` is to
  use ``combine='spw'`` where absolutely required, but avoid unnecessary time averaging through use of longer ``solint``.
  If the WVR application improves the data, this task registers only the WVR solutions into the Pipeline context (the temporary phase and bandpass tables are discarded because better ones will be created later).

- {func}`~pipeline.hif.cli.hif_lowgainflag`: In order to flag the low amplitude gain solutions, phaseup on the BANDPASS intent is required as a pre-apply.
  Again, this necessitates a pre-bandpass phaseup and a bandpass temporary solution. The phaseup process used is that encoded for
  {func}`~pipeline.hifa.cli.hifa_bandpass` (`almaphcorbandpass.py`) using ``phaseupsnr=5``. 

- {func}`~pipeline.hifa.cli.hifa_bandpassflag`: Prior to investigating amplitude based flags, the bandpass must be solved for,
  that also requires the pre-apply of the phaseup for the BANDPASS intent. {func}`~pipeline.hifa.cli.hifa_bandpassflag`
  directly calls the {func}`~pipeline.hifa.cli.hifa_bandpass`
  task for this process and then makes the flagging assessment on the results.

- {func}`~pipeline.hifa.cli.hifa_bandpass` : The main process is encoded in the ``hifa/tasks/bandpass/almaphcorbandpass.py`` function.
  The bandpass must be solved with sufficient SNR such that when
  the solution is applied to a science target(s) additional noise is not imparted, and therefore does not prohibit
  the detection of weak spectral features. {func}`~pipeline.hifa.cli.hifa_bandpass` uses a default ``bpsnr=50``
  which is the required SNR per solved channel, if this is not met then channel binning for the bandpass solution
  is undertaken (see {func}`~pipeline.hifa.cli.hifa_bandpass` for more details).
  - Before the bandpass is solved,
    the BANDPASS intent phaseup must be made - also with sufficiently high SNR as to not adversely effect the bandpass
    solve. In this case ``phaseupsnr=20``. To provide the best phaseup, if any individual spectral-window has low
    SNR, then ``combine='spw'`` is triggered, and hence the phaseup is driven by the aggregate bandwidth (dominated
    by the wider spectral-windows). In the case ``combine='spw'`` does not yield a high enough SNR, ``solint`` can
    be increased in units of integration time up to ``phaseupmaxsolint`` (default = 60 s). Only the bandpass
    solution is registered into the Pipeline context.

- {func}`~pipeline.hifa.cli.hifa_spwphaseup`: This low SNR heuristic process is to establish, based on SNRs
  extracted after temporary gain solutions, whether spectral windows need to be mapped or combined, and if
  ``solint`` or ``gaintype`` need to be changed from the respective 'int' and 'G' defaults for all subsequent
  phaseup solves in later Pipeline stages. If present in the data the BANDPASS, AMPLITUDE, PHASE, CHECK,
  and DIFFGAIN are assessed - see {func}`~pipeline.hifa.cli.hifa_spwphaseup` for specific workflow details.
  - In overview, the SNR is compared with ``phasesnr`` = 32 (default) for PHASE and CHECK intents when solved
    using ``solint='inf'``, and ``intphasesnr`` = 5 (default) for all other intents using ``solint='int'``.
    For all intents, the ideal case is that ``solint=='int'`` can be used for phaseup, including for PHASE
    and CHECK intents (PHASE and CHECK intents have a SNR threshold referenced to a ``solint='inf'`` as to
    avoid gaincal failures for very low SNR data where ``solint='int'`` is not possible when computing the SNR
    in the first instance). For any intent, if the SNR of any spw is below the threshold, that will be mapped to
    another spw with an SNR above the threshold. If there are none above the threshold then ``combine='spw' is
    invoked. Thereafter, ``gaintype='T'`` can be used to further boost SNR, and ultimately longer ``solint`` (>'int')
    can be used - up to predefined limits - half the scan length ('inf'/2) for PHASE and CHECK intents, or 60 s for
    other intents.

- {func}`~pipeline.hifa.cli.hifa_gfluxscaleflag`: To perform amplitude flagging on all intents other than BANDAPASS (conducted in
  {func}`~pipeline.hifa.cli.hifa_bandpassflag`) a phaseup of the respective intents are required. The mapping/combine parameters established in
  {func}`~pipeline.hifa.cli.hifa_spwphaseup` are used here, but the phaseup uses ``solint='int'`` and ``gaintype='G'`` always.
  This is to avoid over time averaging and 'baking-in' any amplitude offsets caused by baseline dependent phase decoherence.

- {func}`~pipeline.hifa.cli.hifa_gfluxscale`: To derive flux densities for transfer calibrators using flux models
  for reference calibrators the amplitude gains need to be solved for all calibrators - these require phaseup solutions to be pre-applied.
  The phaseup for each independent field of the BANDPASS, AMPLITUDE, PHASE, DIFFGAIN, POLARIZATION and CHECK intents (where present)
  use the mapping/combine modes, ``solint`` and ``gaintype`` as established in {func}`~pipeline.hifa.cli.hifa_spwphaseup`.
  - For very low SNR, if long ``solint`` are used in the phase-up, and on comparable timescales noticeable decoherence can
  occur on certain baseline in the array due to variable atmospheric conditions - then decoherence can be 'baked-in'. Thus,
  because the phaseup did not correct the phases, any amplitudes gains are biased upwards on the decoherent baselines.

- {func}`~pipeline.hifa.cli.hifa_diffgaincal`: Only for band-to-band data, the low SNR process is explained in the {ref}` band-to-band <sec-diffgain>` section.

- {func}`~pipeline.hifa.cli.hifa_timegaincal`: The final phaseup solutions are created at this stage. For all intents assessed
  in {func}`~pipeline.hifa.cli.hifa_spwphaseup` the mapping or combine modes are used, along with parameters of ``solint`` and ``gaintype``.
  For these intents the phaseup are always pre-applied before determining the final amplitude gains, and in all except the PHASE and CHECK intents
  the phaseup solves are applied to each intent themselves (i.e. self calibrated). 

## Band-to-Band
(sec-diffgain)=
Since Cycle 11, the band-to-band mode can be used as the calibration technique for both the ACA and all 12 m arrays (see B2B link).
This mode alliviates some low SNR issues, because the PHASE calibrator can be observated at a lower frequency band.

A necessary part of band-to-band calibration is to correct the phases-offsets between Bands, using the DIFFGAIN in {func}`~pipeline.hifa.cli.hifa_diffgaincal`.
The DIFFGAIN is also a bright quasar that is observed at both a low and high frequency band. In some cases, despite being a respectively strong
calibrator, as required by the observing scheme the scan times used are between 12 and 30 s. {func}`~pipeline.hifa.cli.hifa_diffgaincal`
details the calibration sequence in detail, below highlights the low SNR scenario:

- For the "reference" solution, solving each low frequency band spw with ``solint='inf'``, per short-time scan,
  any (excessive) flagging or narrow bandwidth spectral-windows can require ``combine='spw'``. ``solint`` cannot be increased.

- For the band "phase-offset", per spectral-window using the high frequency band, with ``solint='inf'`` and ``combine='scan'``
  *where* solves are undertaken for the "start" and "end" scan groups respectively (e.g. scans ``5,7,9,11,13`` and ``56,58,60,62,64``
  are solved in separate groupings) the SNR can be too low in one or more spw. Specifically for ACA data in band 9 or 10, and
  where there is a narrow (<512 MHz) spectral-window. In this case ``combine='spw,scan'`` is used.

- In the "residual" phase solutions also generated for the high frequency band per scan, with ``solint='inf'``. It is
  most likely that the SNR threshold is not met for the short scan times per spectral window. In such cases ``combine='spw'`` is used.

Note in all solves the SNR threshold is adopted from that used in {func}`~pipeline.hifa.cli.hifa_spwphaseup` for
the DIFFGAIN intent (default = 5), although in {func}`~pipeline.hifa.cli.hifa_diffgaincal` this SNR only needs to
be achieved for the combination of ``solint`` and ``combine`` used in the three steps.

- An added clause to avoid low SNR solves is to confirm (via a temporary gaintable) that the fraction of flagged data
  does not exceed 0.5, while the fraction of missing scans cannot exceed 0.7. If so ``combine='spw'`` is automatically used.


## Situations that could crash the ALMA Pipeline

Fail modes are extremely rare:

- One type of case, noted in the {doc}`known issues <known_issues>` is specifically
  related to the use of ``combine='spw'`` when the lowest index science spectral-window is fully flagged. In this case
  gaintables cannot be made. A trigger cause could be the exceptionally rare case of instrumental problems, or alternatively
  if that spectral-window is in a low atmospheric transmission zone and has no signal.

- For truely very low SNR calibrators, through no fault of the ALMA control system, nor the ALMA Pipeline, a calibrator may
  simply have reduced in flux beyond even the full extent of the low SNR heuristics. When the ``minsnr`` is lower than 3,
  {func}`~casatasks.calibration.gaincal` will flag solutions. If a calibrator, after using ``combine='spw'`` and
  an increased ``solint``, fails in {func}`~casatasks.calibration.gaincal` the ALMA Pipeline will crash, but the
  such a very weak calibrator is simply not suitable for the task and the data cannot be calibrated. 


## Principle of phaseup

It is useful to recall that the principle of making phaseup solutions, solved using short time
intervals (ideally ``solint='int'``), is to correct for the variable atmospheric variations. To tie with low SNR calibrators,
if ``solint`` timescales become too long, the phaseup is compromised and will not *fully* correct the phase variations, and
the magnitude of the variations are dependent upon baseline length. ALMA observations are conducted also incorporating a
feedback loop to ensure the atmospheric variations are sufficiently stable (see the Phase Decoherence section in
{func}`~pipeline.hifa.cli.hifa_spwphaseup`) and therefore some *longer* ``solint`` can be tolerated, which is why
the ALMA Piepline employ such heuristics before failing to calibrate data.
