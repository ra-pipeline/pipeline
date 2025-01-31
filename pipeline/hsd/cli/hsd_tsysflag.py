import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsd.tasks.tsysflag.tsysflag.TsysflagInputs.__init__
@utils.cli_wrapper
def hsd_tsysflag(vis=None, caltable=None,
                 flag_nmedian=None, fnm_limit=None, fnm_byfield=None,
                 flag_derivative=None, fd_max_limit=None,
                 flag_edgechans=None, fe_edge_limit=None,
                 flag_fieldshape=None, ff_refintent=None, ff_max_limit=None,
                 flag_birdies=None, fb_sharps_limit=None,
                 flag_toomany=None, tmf1_limit=None, tmef1_limit=None,
                 metric_order=None, normalize_tsys=None, filetemplate=None):

    """Flag deviant system temperature measurements.

    Flag deviant system temperature measurements for single dish measurements. This is done by running a
    sequence of flagging sub-tasks (tests), each looking for a different type of possible error.

    If a file with manual Tsys flags is provided with the 'filetemplate'
    parameter, then these flags are applied prior to the evaluation of the
    flagging heuristics listed below.

    The tests are:

      1. Flag Tsys spectra with high median values

      2. Flag Tsys spectra with high median derivatives. This is meant to spot
        spectra that are 'ringing'.

      3. Flag the edge channels of the Tsys spectra in each SpW.

      4. Flag Tsys spectra whose shape is different from that associated with
        the BANDPASS intent.

      5. Flag 'birdies'.

      6. Flag the Tsys spectra of all antennas in a timestamp and spw if
        proportion of antennas already flagged in this timestamp and spw exceeds
        a threshold, and flag Tsys spectra for all antennas and all timestamps
        in a spw, if proportion of antennas that are already entirely flagged
        in all timestamps exceeds a threshold.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Flag Tsys measurements using currently recommended tests:

        >>> hsd_tsysflag()

        2. Flag Tsys measurements using all recommended tests apart from that
        using the 'fieldshape' metric:

        >>> hsd_tsysflag(flag_fieldshape=False)

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
