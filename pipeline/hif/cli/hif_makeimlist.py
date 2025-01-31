import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.makeimlist.makeimlist.MakeImListInputs.__init__
@utils.cli_wrapper
def hif_makeimlist(vis=None, imagename=None, intent=None, field=None,
                   spw=None, contfile=None, linesfile=None, uvrange=None,
                   specmode=None, outframe=None, hm_imsize=None, hm_cell=None,
                   calmaxpix=None, phasecenter=None,
                   nchan=None, start=None, width=None, nbins=None,
                   robust=None, uvtaper=None, clearlist=None, per_eb=None,
                   per_session=None, calcsb=None, datatype=None, datacolumn=None,
                   parallel=None):

    """Compute list of clean images to be produced

    Generate a list of images to be cleaned. By default, the list will include
    one image per science target per spw. Calibrator targets can be selected
    by setting appropriate values for ``intent``.

    By default, the output image cell size is set to the minimum cell size
    consistent with the UV coverage.

    By default, the image size in pixels is set to values determined by the
    cell size and the primary beam size. If a calibrator is being
    imaged (intents 'PHASE', 'BANDPASS', 'FLUX' or 'AMPLITUDE') then the
    image dimensions are limited to 'calmaxpix' pixels.

    By default, science target images are cubes and calibrator target images
    are mfs. Science target images may be mosaics or single fields.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Make a list of science target images to be cleaned, one image per science
        spw.

        >>> hif_makeimlist()

        2. Make a list of PHASE and BANDPASS calibrator targets to be imaged,
        one image per science spw.

        >>> hif_makeimlist(intent='PHASE,BANDPASS')

        3. Make a list of PHASE calibrator images observed in spw 1, images limited to
        50 pixels on a side.

        >>> hif_makeimlist(intent='PHASE',spw='1',calmaxpix=50)

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
