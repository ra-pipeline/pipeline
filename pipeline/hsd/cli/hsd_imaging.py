import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsd.tasks.imaging.imaging.SDImagingInputs.__init__
@utils.cli_wrapper
def hsd_imaging(mode=None, restfreq=None, infiles=None, field=None, spw=None):

    """Generate single dish images.

    The hsd_imaging task generates single dish images per antenna as
    well as combined image over whole antennas for each field and
    spectral window. Image configuration (grid size, number of pixels,
    etc.) is automatically determined based on meta data such as
    antenna diameter, map extent, etc.

    Note that generated images are always in LSRK frame.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Generate images with default settings and context

        >>> hsd_imaging()

        2. Generate images with amplitude calibrator and specific parameters

        >>> hsd_imaging(mode='ampcal', field='*Sgr*,M100', spw='17,19')

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
