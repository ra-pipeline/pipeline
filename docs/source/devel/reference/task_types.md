# Task Types: Single-vis, Multi-vis, and Session-aware

By default, each pipeline task is considered a single-vis task, which means that
if invoked on a list of measurement sets, the task will automatically be executed
separately for each measurement set, with the `Results` object from each execution
aggregated into a `ResultsList` that is returned by the single-vis task. This handling
is implemented in `infrastructure.basetask.StandardTaskTemplate.execute`.

A task can declare itself to be multi-vis with the `is_multi_vis_task` class
property. Examples include the `exportdata` and `restoredata` tasks, and many
tasks in the "imaging" pipeline. A multi-vis task is not necessarily a
session-aware task. Many multi-vis tasks merely process all input measurement sets
at once, without regard of what session each measurement set belongs to.

Session-aware tasks were first foreseen as necessary for the future implementation
of "group processing": processing a group of measurement sets that were observed
as part of a "session", where certain measurement sets no longer contain all required
calibrator intents themselves but instead need to be calibrated using calibration
scans from a different measurement set in the same session.

Initial updates to the pipeline framework to support sessions were introduced in
[CAS-10781](https://open-jira.nrao.edu/browse/CAS-10781) around Fall 2017 for the Cycle 6 release, see commit
[0a23bd5b](https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline/commits/0a23bd5b85154118371d3bfedf9fbc7a50bb4bfc).

As part of CAS-10781, prototype of 2 session-aware tasks were introduced:

- the `session_bandpass` task defined in `hifa.tasks.bandpass.almaphcorbandpass.SessionALMAPhcorBandpass` is a prototype of bandpass task that would process a session of MSes where one or more MSes might miss a bandpass calibrator; for those MSes without a bandpass, it would take a bandpass scan from another MS that is closest in time.
- the `session_gfluxscale` task defined in `hifa.tasks.fluxscale.gcorfluxscale.SessionGcorFluxscale` is a prototype that would process a session of MSes, adopting flux calibrations from one MS to another MS if the latter were to be missing a flux calibrator

Note: as of September 2025, these tasks are still prototypes that are not validated,
have never been used in recipes / production, and are not actively maintained. To
avoid ongoing maintenance, these tasks could be commented out or removed from their module.

A task is session-aware when it acts separately on each session and its corresponding list of MSes.

As of September 2025, the following Pipeline tasks are session aware, as
indicated by their use of `pipeline.infrastructure.sessionutils.group_vislist_into_sessions`:

- hifa_session_refant:
  - used in ALMA IF polarization calibration cal recipes.
  - considers all MSes within a session to assess the best single common reference antenna list.
- hifa_polcal:
  - used in ALMA IF polarization calibration cal recipes.
  - performs polarization calibration separately for each session, combining measurement sets within each session.
- hif_makeimlist:
  - used in numerous ALMA IF and VLA (imaging) recipes
  - if called with `inputs.per_session=True` (default: False), `hif_makeimlist` will create an image target per session.

## Stage numbers in filenames

The pipeline stage number that is used in pipeline products () is composed of two elements:

- the task counter: incremented in StandardTaskTemplate.execute when the task-to-be-executed is the top-level task.
- the sub-task counter: incremented in StandardTaskTemplate.execute when the task-to-be-executed is not the top-level task.

This stage number, e.g. "s17.3", is included in the filenames of intermediate Pipeline products (such as caltables, plots)
that are all stored in the same common 'working' directory, to ensure these products have unique filenames, even if a
task re-runs a gaincal step multiple times (different sub-tasks) or a pipeline task is run multiple times in a recipe.

The stage number is added to a task result as `result.stage_number` by `infrastructure.basetask.result_finaliser`.
