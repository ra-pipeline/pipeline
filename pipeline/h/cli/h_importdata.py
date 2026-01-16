from . import utils


# docstring and type hints: inherits from h.tasks.importdata.importdata.ImportDataInputs.__init__
@utils.cli_wrapper
def h_importdata(vis=None, session=None, asis=None, process_caldevice=None, overwrite=None,
                 nocopy=None, bdfflags=None, lazy=None, ocorr_mode=None, createmms=None):
    """Imports data into the interferometry pipeline.

    The h_importdata task loads the specified visibility data into the pipeline
    context unpacking and / or converting it as necessary.

    If the ``overwrite`` input parameter is set to False and the task is
    asked to convert an input ASDM input to an MS, then when the output
    MS already exists in the output directory, the importasdm
    conversion step is skipped, and the existing MS will be imported
    instead.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Load an ASDM list in the ../rawdata subdirectory into the context"

        >>> h_importdata(vis=['../rawdata/uid___A002_X30a93d_X43e', '../rawdata/uid_A002_x30a93d_X44e'])

        2. Load an MS in the current directory into the context:

        >>> h_importdata(vis=['uid___A002_X30a93d_X43e.ms'])

        3. Load a tarred ASDM in ../rawdata into the context:

        >>> h_importdata(vis=['../rawdata/uid___A002_X30a93d_X43e.tar.gz'])

        4. Import a list of MeasurementSets:

        >>> myvislist = ['uid___A002_X30a93d_X43e.ms', 'uid_A002_x30a93d_X44e.ms']
        >>> h_importdata(vis=myvislist)

    """
