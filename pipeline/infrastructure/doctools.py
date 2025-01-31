import inspect

from docstring_inheritance import inherit_google_docstring

import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.sessionutils as sessionutils

from typing import Callable


def inherit_type_hints(parent_func: Callable, child_func: Callable):
    """Copy type hints from parent_func to child_func.

    Note:
        This function assumes that parent_func and child_func
        have similar function signatures. Typical usecase is
        that one function wraps the other. Function signature
        is not necessarily be identical. But there must be
        some overlap of parameter names to make this function
        work.

        Note that, if parent_func and child_func use the same
        parameter name but for different purposes, resulting
        type hint may be wrong.

    Args:
        parent_func: Base function from which type hints are copied
        child_func: Function to be annotated
    """
    parent_annotations = parent_func.__annotations__
    child_annotations = child_func.__annotations__
    child_parameters = list(inspect.signature(child_func).parameters)
    for param in child_parameters:
        if param in parent_annotations:
            child_annotations.setdefault(param, parent_annotations[param])


def inherit_annotations(task_class: basetask.StandardTaskTemplate, cli_task: Callable):
    """Inherit function annotations from Task implementation class.

    Type hints for parameters are inherited from task_class.Inputs.__init__.
    On the other hand, type hint for return value refers to either task_class.analyse
    or task_class.execute. In addition, return type can be ResultsList depending
    on the value of task_class.is_multi_vis_task attribute.

    Args:
        task_class: Pipeline Task class
        cli_task: Pipeline CLI function
    """
    # type hints for parameters
    inherit_type_hints(task_class.Inputs.__init__, cli_task)

    # type hint for return value
    if issubclass(task_class, basetask.ModeTask):
        parent_func = task_class.execute
        is_multi_vis = task_class.is_multi_vis_task
    elif issubclass(task_class, sessionutils.ParallelTemplate):
        parent_func = task_class.Task.analyse
        is_multi_vis = task_class.Task.is_multi_vis_task
    else:
        parent_func = task_class.analyse
        is_multi_vis = task_class.is_multi_vis_task

    # use generic Results type if there is no type information on return value
    return_type = parent_func.__annotations__.get('return', basetask.Results)

    # according to the implementation of StandardTaskTemplate, return value
    # will be ResultsList if is_multi_vis_task is False
    if is_multi_vis:
        cli_task.__annotations__['return'] = return_type
    else:
        cli_task.__annotations__['return'] = basetask.ResultsList[return_type]


def inherit_docstring(task_class: basetask.StandardTaskTemplate, cli_task: Callable):
    """Merge docstring of the constructor for Inputs class of task_class into cli_task.

    Typical usecase is to merge Args section of task_class.Inputs.__init__ into
    the docstring of cli_task without modifying generic description.

    Args:
        task_class: Pipeline Task class
        cli_task: Pipeline CLI function
    """
    inputs_class = task_class.Inputs
    # check if cli_task is wrapped with any decorators
    if hasattr(cli_task, '__wrapped__'):
        # if it is wrapped, peel off all wrapper functions
        base_func = cli_task
        while hasattr(base_func, '__wrapped__'):
            base_func = base_func.__wrapped__

        # inherit docstring from Inputs's constructor
        inherit_google_docstring(inputs_class.__init__.__doc__, base_func)

        # copy docstring to outermost wrapper function
        cli_task.__doc__ = base_func.__doc__
    else:
        # if cli_task is not wrapped, simply inherit docstring
        # from Inputs's constructor
        inherit_google_docstring(inputs_class.__init__.__doc__, cli_task)
