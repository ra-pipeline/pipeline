import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.editimlist.editimlist.EditimlistInputs.__init__
@utils.cli_wrapper
def hif_editimlist(imagename=None,
                   search_radius_arcsec=None,
                   cell=None,
                   cfcache=None,
                   conjbeams=None,
                   cyclefactor=None,
                   cycleniter=None,
                   nmajor=None,
                   datatype=None,
                   datacolumn=None,
                   deconvolver=None,
                   editmode=None,
                   field=None,
                   imaging_mode=None,
                   imsize=None,
                   intent=None,
                   gridder=None,
                   mask=None,
                   pbmask=None,
                   nbin=None,
                   nchan=None,
                   niter=None,
                   nterms=None,
                   parameter_file=None,
                   pblimit=None,
                   phasecenter=None,
                   reffreq=None,
                   restfreq=None,
                   robust=None,
                   scales=None,
                   specmode=None,
                   spw=None,
                   start=None,
                   stokes=None,
                   sensitivity=None,
                   threshold=None,
                   nsigma=None,
                   uvtaper=None,
                   uvrange=None,
                   width=None,
                   vlass_plane_reject_ms=None):
    """Add to a list of images to be produced with hif_makeimages()

    Add to a list of images to be produced with hif_makeimages(), which uses hif_tclean() to invoke CASA tclean.
    Many of the hif_editimlist() inputs map directly to tclean parameters.

    The results object for the pipeline task is returned.

    Returns:
        The results object for the pipeline task is returned.

    Examples:


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
