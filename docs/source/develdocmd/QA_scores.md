# Pipeline Quality Assurance (QA) Score Class Design

Pipeline QA scores are represented by the
`pipeline/infrastructure/pipelineqa.py::QAScore` class. The basic setup features
a normalized numerical score ("score") between 0.0 and 1.0 with the following
numerical ranges, meanings and colors:

| score range           | color  | QA level   |
|:----------------------|:-------|:-----------|
| 0.00 <= score <= 0.33 | red    | error      |
| 0.33 < score <= 0.66  | yellow | warning    |
| 0.66 < score <= 0.90  | blue   | suboptimal |
| 0.90 < score <= 1.00  | green  | optimal    |

Optionally, `score` can be set to -0.1 if the score calculation encounters any unhandled errors. A score of -0.1 is considered an error score.

A long message (`longmsg`) describes the reason for the given score in detail.
It is rendered in weblog QA score tables. A short message (`shortmsg`) gives
a concise summary for the "By Task" weblog page. It is shown next to the task
name and should thus be short to render well.

The scores are usually calculated from unnormalized metrics using the actual
data. The metric is coded via the `QAOrigin` entity class defined in
`pipelineqa.py`. It has `metric_name`, `metric_score` (which is really the
metric value and **not** any normalized quantity) and "metric_units". In the
QA score objects the metrics are stored as the `origin` attribute.

Furthermore there is a data selection object stored as `applies_to` attribute
in the main QA score object. The data selection is coded in the
`TargetDataSelection` via the sessions, vis list, scans, spws, fields, intents,
antennas and polarizations that were used to compute the particular metric.

A QA score can be `None`, presented as "N/A". You can assign an "N/A" QA score
with custom messages. If no score is assigned to the task results, a "N/A" QA
score with a “No QA” message will be attached as a fallback.

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

## Pipeline QA "Handler" Class Registration

Pipeline QA "handler" classes rely on the class inheritance relationship from the `QAPlugin` base class to register and load correctly (see the `QARegistry.do_qa` method).

Individual task QA modules need to be imported into the namespace early so their `*QAHandler` and `*ListQAHandler` classes can be defined and registered. For this reason, it is essential to have `import . qa` inside `h*/tasks/*/__init__.py` for any Pipeline task with a `qa.py` module.

To check the currently registered `*QAHandler` classes, you can try:

```python
CASA <2>: from pipeline.infrastructure.pipelineqa import QAPlugin
CASA <3>: QAPlugin.__subclasses__()
Out[3]:
[pipeline.h.tasks.exportdata.qa.ExportDataQAHandler,
 pipeline.h.tasks.exportdata.qa.ExportDataListQAHandler,
 pipeline.h.tasks.applycal.qa.ApplycalQAHandler,
 pipeline.h.tasks.applycal.qa.ApplycalListQAHandler,
 pipeline.h.tasks.importdata.qa.ImportDataQAHandler,
 pipeline.h.tasks.importdata.qa.ImportDataListQAHandler,
 # ...
]
```

## Reference on ALMA Quality Assurance

* [QA2 Data Products](https://almascience.nrao.edu/processing/qa2-data-products)
* [Sec. 7 QA Scores, Hunter et al. 2023 PASP, 135, 074501](https://ui.adsabs.harvard.edu/abs/2023PASP..135g4501H/abstract)
* [Sec. 11 Quality Assurance, ALMA Cycyle 11 Technical Handbook](https://almascience.nrao.edu/documents-and-tools/cycle11/alma-technical-handbook)
* [ALMA quality assurance: concepts, procedures, and tools](https://ui.adsabs.harvard.edu/abs/2016SPIE.9910E..1HC/abstract)
* [Improving ALMA's data processing efficiency using a holistic approach](https://ui.adsabs.harvard.edu/abs/2020SPIE11449E..1TN/abstract)
