"""
recipereducer is a utility to reduce data using a standard pipeline procedure.
It parses a XML reduction recipe, converts it to pipeline tasks, and executes
the tasks for the given data. It was written to give pipeline developers
without access to PPRs and/or a PPR generator a way to reduce data using the
latest standard recipe.

Note: multiple input datasets can be specified. Doing so will reduce the data
      as part of the same session.

Example #1: process uid123.tar.gz using the standard recipe.

    import pipeline.recipereducer
    pipeline.recipereducer.reduce(vis=['uid123.tar.gz'])

Example #2: process uid123.tar.gz using a named recipe.

    import pipeline.recipereducer
    pipeline.recipereducer.reduce(vis=['uid123.tar.gz'],
                                  procedure='procedure_hif.xml')

Example #3: process uid123.tar.gz and uid124.tar.gz using the standard recipe.

    import pipeline.recipereducer
    pipeline.recipereducer.reduce(vis=['uid123.tar.gz', 'uid124.tar.gz'])

Example #4: process uid123.tar.gz, naming the context 'testrun', thus
            directing all weblog output to a directory called 'testrun'.

    import pipeline.recipereducer
    pipeline.recipereducer.reduce(vis=['uid123.tar.gz'], name='testrun')

Example #5: process uid123.tar.gz with a log level of TRACE

    import pipeline.recipereducer
    pipeline.recipereducer.reduce(vis=['uid123.tar.gz'], loglevel='trace')

"""
import ast
import collections
import os
import traceback
import xml.etree.ElementTree as ElementTree

import pkg_resources

import pipeline.infrastructure.launcher as launcher
import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.vdp as vdp
from pipeline.infrastructure import exceptions, task_registry, utils

LOG = logging.get_logger(__name__)

RECIPES_DIR = pkg_resources.resource_filename(__name__, 'recipes')

TaskArgs = collections.namedtuple('TaskArgs', 'vis infiles session')


def _create_context(loglevel, plotlevel, name):
    return launcher.Pipeline(loglevel=loglevel, plotlevel=plotlevel,
                             name=name).context


def _get_context_name(procedure):
    root, _ = os.path.splitext(os.path.basename(procedure))
    return 'pipeline-%s' % root


def _get_processing_procedure(procedure: str) -> ElementTree:
    # find the procedure file on disk, then fall back to the standard recipes
    if os.path.exists(procedure):
        procedure_file = os.path.abspath(procedure)
    else:
        procedure_file = os.path.join(RECIPES_DIR, procedure)
    if os.path.exists(procedure_file):
        LOG.info('Using procedure file: %s' % procedure_file)
    else:
        msg = f'Procedure not found:: {procedure}'
        LOG.error(msg)
        raise IOError(msg)

    procedure_xml = ElementTree.parse(procedure_file)
    if not procedure_xml:
        msg = f'Could not parse procedure file at {procedure_file}'
        LOG.error(msg)
        raise IOError(msg)

    return procedure_xml


def _get_procedure_title(procedure):
    procedure_xml = _get_processing_procedure(procedure)
    procedure_title = procedure_xml.findtext('ProcedureTitle', default='Undefined')
    return procedure_title


def _get_tasks(context, args, procedure):
    procedure_xml = _get_processing_procedure(procedure)

    commands_seen = []
    for processingcommand in procedure_xml.findall('ProcessingCommand'):
        cli_command = processingcommand.findtext('Command')
        commands_seen.append(cli_command)

        # ignore breakpoints
        if cli_command == 'breakpoint':
            continue

        # skip exportdata when preceded by a breakpoint
        if len(commands_seen) > 1 and commands_seen[-2] == ['breakpoint'] \
                and cli_command == 'hif_exportdata':
            continue

        task_class = task_registry.get_pipeline_class_for_task(cli_command)

        task_args = {}

        if cli_command in ['hif_importdata',
                           'hifa_importdata',
                           'hifv_importdata',
                           'hif_restoredata',
                           'hifa_restoredata',
                           'hsd_importdata',
                           'hsdn_importdata']:
            task_args['vis'] = args.vis
            # we might override this later with the procedure definition
            task_args['session'] = args.session

        elif cli_command in [ 'hsd_restoredata' ]:
            task_args['infiles'] = args.infiles

        for parameterset in processingcommand.findall('ParameterSet'):
            for parameter in parameterset.findall('Parameter'):
                argname = parameter.findtext('Keyword')
                argval = parameter.findtext('Value')
                task_args[argname] = string_to_val(argval)

        task_inputs = vdp.InputsContainer(task_class, context, **task_args)
        task = task_class(task_inputs)
        task._hif_call = _as_task_call(task_class, task_args)
        # we yield rather than return so that the context can be updated
        # between task executions
        yield task


def string_to_val(s):
    """
    Convert a string to a Python data type.
    """
    try:
        pyobj = ast.literal_eval(s)
        # PIPE-1030: prevent a string like "1,2,3" from being unexpectedly translated into tuple
        if type(pyobj) is tuple and s.strip()[0] != '(':
            pyobj = s
        return pyobj
    except ValueError:
        return s
    except SyntaxError:
        return s


def _format_arg_value(arg_val):
    arg, val = arg_val
    return '%s=%r' % (arg, val)


def _as_task_call(task_class, task_args):
    kw_args = list(map(_format_arg_value, task_args.items()))
    return '%s(%s)' % (task_class.__name__, ', '.join(kw_args))


def reduce(vis=None, infiles=None, procedure='procedure_hifa_calimage.xml',
           context=None, name=None, loglevel='info', plotlevel='default',
           session=None, exitstage=None, startstage=None):
    if vis is None:
        vis = []

    if infiles is None:
        infiles = []

    if context is None:
        name = name if name else _get_context_name(procedure)
        context = _create_context(loglevel, plotlevel, name)
        procedure_title = _get_procedure_title(procedure)
        context.set_state('ProjectStructure', 'recipe_name', procedure_title)

    if session is None:
        session = ['default'] * len(vis)

    if startstage is None:
        startstage = 0

    task_args = TaskArgs(vis, infiles, session)
    task_generator = _get_tasks(context, task_args, procedure)
    try:
        procedure_stage_nr = 0
        while True:
            task = next(task_generator)
            procedure_stage_nr += 1
            if procedure_stage_nr < startstage:
                continue
            LOG.info('Executing pipeline task %s' % task._hif_call)

            try:
                result = task.execute()
                result.accept(context)
            except Exception as ex:
                # Log message if an exception occurred that was not handled by
                # standardtask template (not turned into failed task result).
                LOG.error('Unhandled error in recipereducer while running pipeline task %s.' % task._hif_call)
                traceback.print_exc()
                return context

            tracebacks = utils.get_tracebacks(result)
            if len(tracebacks) > 0:
                previous_tracebacks_as_string = "{}".format("\n".join([tb for tb in tracebacks]))
                raise exceptions.PipelineException(previous_tracebacks_as_string)
            elif result.stage_number is exitstage:
                break

    except StopIteration:
        pass
    finally:
        LOG.info('Saving context...')
        context.save()

    return context
