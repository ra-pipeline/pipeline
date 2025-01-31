import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.uvcontsub.uvcontsub.UvcontSubInputs.__init__
@utils.cli_wrapper
def hif_uvcontsub(vis=None, field=None, intent=None, spw=None, fitorder=None, parallel=None):
    """Fit and subtract continuum from the data

    hif_uvcontsub fits the continuum for the frequency ranges given in the cont.dat
    file, subtracts that fit from the uv data and generates a new set of MSes
    containing the continuum subtracted (i.e. line) data. The fit is attempted
    for all science targets and spws. If a fit is impossible, the corresponding
    data selection is not written to the output line MS.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Fit and subtract continuum for all science targets and spws

        >>> hif_uvcontsub()

        2. Fit and subtract continuum only for a subsect of fields

        >>> hif_uvcontsub(field='3C279,M82'

        3. Fit and subtract continuum only for a subsect of spws

        >>> hif_uvcontsub(spw='11,13')

        4. Override automatic fit order choice

        >>> hif_uvcontsub(fitorder={'3C279': {'15': 1, '17': 2}, 'M82': {'13': 2}})

    """


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
