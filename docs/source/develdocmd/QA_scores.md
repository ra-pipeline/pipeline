# Pipeline QA score class design

Pipeline QA scores are represented by the
pipeline/infrastructure/pipelineqa.py::QAScore class. The basic setup features
a normalized numerical score ("score") between 0.0 and 1.0 with the following
numerical ranges, meanings and colors:

0.00 <= score <= 0.33 -> error, red
0.33 <  score <= 0.66 -> warning, yellow
0.66 <  score <= 0.90 -> suboptimal, blue
0.90 <  score <= 1.00 -> optimal, green

Optionally, "score" can be set to -0.1 in case the score calculation encounters
any errors that can not be handled. -0.1 is considered an error score.

A long message ("longmsg") describes the reason for the given score in detail.
It is rendered in weblog QA score tables. A short message ("shortmsg") gives
a concise summary for the "By Task" weblog page. It is shown next to the task
name and should thus be short to render well.

The scores are usually calculated from unnormalized metrics using the actual
data. The metric is coded via the "QAOrigin" entity class defined in
"pipelineqa.py". It has "metric_name", "metric_score" (which is really the
metric value and *not* any normalized quantity) and "metric_units". In the
QA score objects the metrics are stored as the "origin" attribute.

Furthermore there is a data selection object stored as "applies_to" attribute
in the main QA score object. The data selection is coded in the
"TargetDataSelection" via the sessions, vis list, scans, spws, fields, intents,
antennas and polarizations that were used to compute the particular metric.

The last attribute is the "weblog_location" which is an enum with possible
values "BANNER", "ACCORDION", "HIDDEN" and "UNSET". "BANNER" is the top of a
weblog page, "ACCORDION" used to be the QA score table at the bottom of the
page. PIPE-1481 requested moving this up to the banner area. Previously, the
banner scores were supposed to highlight the main QA findings, in particular
error and warning scores. This will be replaced with display of the task
score and link to all subscores to be shown in the weblog (all except "HIDDEN").
The difference between "BANNER" and "ACCORDION" will probably no longer be
needed. "UNSET" is for legacy scores from the time before introducing the
banner concept. They were handled like "BANNER" scores.

Every task result has a QA object called "qa" with a "pool" attribute listing
all subscores. The task score is defined by the "representative_score"
attribute. It is often the minimum of all subscores, but it could also be
computed differently, e.g. as mean of subscores. In case "representative_score"
is unset, the pipeline assumes the minimum of the pool scores.
