"""
Tests for the hifv/tasks/hanning/hanning.py module.
"""
import sys
import os


sys.path.insert(0, os.path.expandvars("$SCIPIPE_HEURISTICS"))
import pipeline
pipeline.initcli()
import pytest

context = pipeline.Pipeline().context
inputs = pipeline.hifv.tasks.hanning.Hanning.Inputs(context)
task = pipeline.hifv.tasks.hanning.Hanning(inputs)
# result = task.execute(dry_run=True)
# result.accept(context)
# context.save()

test_params = [(task.inputs.vis, str), (task.inputs.output_dir, str)]


@pytest.mark.parametrize("result, expected", test_params)
def test_hanning(result, expected):
    """Test hanning pipeline task functionality

    Examine the types of the task inputs.

    """

    assert type(result) == expected
