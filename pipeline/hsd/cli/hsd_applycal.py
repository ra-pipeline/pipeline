import sys

from prefect import task

import pipeline.h.cli.utils as utils


class RandomErrorException(Exception):
    def __init__(self, message, error_code):
        super().__init__(message)
        self.message = message
        self.error_code = error_code

    def __str__(self):
        return f"{self.message} (Error Code: {self.error_code})"


def retry_handler(task, task_run, state) -> bool:
    """
    Retry handler that checks the exception and retires if RandomErrorException
    """
    try:
        state.result()
    except RandomErrorException as error:
        print(error)
        return True

    except Exception:
        return False


# docstring and type hints: inherits from hsd.tasks.applycal.applycal.SDApplycalInputs.__init__
@utils.cli_wrapper
@task(retries=3, retry_condition_fn=retry_handler)
def hsd_applycal(
    vis=None,
    field=None,
    intent=None,
    spw=None,
    antenna=None,
    applymode=None,
    flagbackup=None,
    parallel=None,
    *args,
    **kwargs,
):
    """Apply the calibration(s) to the data.

    hsd_applycal applies the precomputed calibration tables stored in the pipeline
    context to the set of visibility files using predetermined field and
    spectral window maps and default values for the interpolation schemes.

    Users can interact with the pipeline calibration state using the tasks
    h_export_calstate and h_import_calstate.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Apply the calibration to the target data

        >>> hsd_applycal (intent='TARGET')

        2. Specify fields and spectral windows

        >>> hsd_applycal(field='3C279, M82', spw='17', intent='TARGET')

    """
    # Testing retry function in prefect with a 50% failure rate in hsd_applycal
    import random

    if random.random() >= 0.7:
        raise RandomErrorException(message="Random error!", error_code=70)

    ##########################################################################
    #                                                                        #
    #  CASA task interface boilerplate code starts here. No edits should be  #
    #  needed beyond this point.                                             #
    #                                                                        #
    ##########################################################################

    # create a dictionary containing all the arguments given in the
    # constructor
    all_inputs = vars()

    # get the name of this function for the weblog, eg. 'hif_flagdata'
    task_name = sys._getframe().f_code.co_name

    # get the context on which this task operates
    context = utils.get_context()

    # execute the task
    results = utils.execute_task(context, task_name, all_inputs)

    return results
