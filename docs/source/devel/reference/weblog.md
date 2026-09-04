# Weblog Rendering
The pipeline weblog generator is implemented in `infrastructure.renderer.htmlrenderer.WebLogGenerator`.

The weblog rendering is always executed on the "pipeline context", not on an
individual task result. As such, the weblog generator cannot render results that
have not (yet) been accepted into the context.

During a pipeline run, weblog rendering is triggered as a step after execution of
the main task heuristics, during the step where the task `Results` are accepted
into the Pipeline context, as implemented in `infrastructure.basetask.Results.accept`.

Weblog generation can be disabled with the module-level variable
`infrastructure.basetask.DISABLE_WEBLOG`, e.g.:

```python
import pipeline.infrastructure.basetask as basetask
basetask.DISABLE_WEBLOG = True
# continue with execution of Pipeline stages, recipereducer, or executeppr...
```
or at time of Pipeline initialisation with:
```python
h_init(weblog=False)
```

Weblog generation can also be triggered after a Pipeline run has completed, with:
```python
import pipeline.infrastructure.renderer.htmlrenderer as htmlrenderer
context = h_resume(filename='last')
htmlrenderer.WebLogGenerator.render(context)
```

However, at present, there are various pipeline stages where the weblog rendering
will include steps that create statistics (e.g. flagging summary) or plots based on the
state that the Measurement Set is left in at the end of the pipeline stage.
As such, decoupling weblog rendering from task execution is possible, but running
weblog generation for the first time at the end of the pipeline run would currently
lead to the weblog of several stages looking different, because the measurement set
will have been changed in subsequent stages (typically updates to flagging,
corrected amplitude, and/or model data columns).

There are already a couple of tasks that need to create plots during execution of
the task heuristics, because those plots need to reflect the temporary state of the
measurement set during the task. Examples include: `hifa_bandpassflag`,
`hifa_gfluxscaleflag`, `hifa_targetflag`, `hifa_polcalflag`, which all use a mid-task
temporary applycal. 


