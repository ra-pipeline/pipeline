# Logging

## Log files for individual tasks

The `casapy.log` that gets linked from the task page is generated upon pickling a
task result after execution. The contents of this log file are taken from the
temporary `result.casalog` property that is populated by the `capture_log`
decorator. This temporary property is deleted as soon as the stage log is written
to disk, to reduce the size of the final result pickle that is serialized to disk.

The `capture_log` decorator is only appropriate for (and used around) the
`infrastructure.basetask.StandardTaskTemplate.execute` method, and so it currently
can only ever capture what happens during execution of the main task heuristics
(primarily its `prepare` and `analyse` methods) but not what occurs during QA or
weblog generation.

At present, the QA heuristic evaluation and weblog generation are kicked off as part
of accepting a task result (from a task that finished execution) into the Pipeline
context, in `infrastructure.basetask.Result.accept` that is invoked by
`infrastructure.basetask.Executor.execute`.

The `capture_log` decorator operates directly on the CASA log file (and CASA's `casalog`),
bypassing the `pipeline.infrastructure.logging` that is used throughout pipeline
to handle logging.

## Log handling for attention, warning, and error notifications in weblog

Separate from `result.casalog`, there also exists a `result.logrecords` property.
This is initially populated by `basetask.StandardTaskTemplate.execute` itself
(rather than a decorator for `result.casalog`) and later further appended to by
`pipelineqa.QARegistry.do_qa`.

Both at the init and append steps, the logging handlers only intend to capture
errors, warnings, and attention level messages, as `result.logrecords` is only
ever used by the weblog renderer, for the purpose of generating
warning/error/attention notifications and corresponding badges.

Over the years, a couple of exceptional cases were introduced with the aim of
capturing these kinds of notifications when they occur during weblog generation.
To this end, in the weblog renderer module of a couple of tasks, a logging
handler has been wrapped around a particular rendering step (e.g. creating some
plot) to capture any error/warning/attention messages from there, and add those
to `result.logrecords` as well. Since these are still messages that occur
during weblog generation, added to `result.logrecords`, these messages will only
show up as notifications in the weblog (banner at top of page), but not in the
task-specific `casapy.log`.

## Restricting log output per tool

Lowering the log level to TRACE will log all tool calls — including tools such
as CASA quanta and measures. Records from these tools may be considered noise;
you may prefer to leave the log level at DEBUG and selectively enable output
for certain tools by editing `pipeline/infrastructure/casa_tools.py`. For
example, to enable logging of calls to the imager tool alone, edit `casa_tools.py`
and change the private class definition from:

```python
_logging_imager_cls = create_logging_class(casatools.imager,
                                           level=logging.INFO, to_log=(...))
```

to log all method calls at DEBUG level:

```python
_logging_imager_cls = create_logging_class(casatools.imager, level=logging.DEBUG)
```

To omit log records entirely for a tool, assign the unwrapped CASA tool class directly:

```python
imager = casatools.imager()
```
