import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.importdata.importdata.VLAImportDataInputs.__init__
@utils.cli_wrapper
def hifv_importdata(vis=None, session=None, asis=None, overwrite=None, nocopy=None, createmms=None,
                    ocorr_mode=None, datacolumns=None, specline_spws=None, parallel=None):
    """Imports data into the VLA pipeline.

    The ``hifv_importdata`` task loads the specified visibility data into the pipeline
    context unpacking and / or converting it as necessary.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Load an ASDM list in the ../rawdata subdirectory into the context:

        >>> hifv_importdata (vis=['../rawdata/uid___A002_X30a93d_X43e', '../rawdata/uid_A002_x30a93d_X44e'])

        2. Load an MS in the current directory into the context:

        >>> hifv_importdata (vis=['uid___A002_X30a93d_X43e.ms'])

        3. Load a tarred ASDM in ../rawdata into the context:

        >>> hifv_importdata (vis=['../rawdata/uid___A002_X30a93d_X43e.tar.gz'])

        4. Check the hifv_importdata inputs, then import the data:

        >>> myvislist = ['uid___A002_X30a93d_X43e.ms', 'uid_A002_x30a93d_X44e.ms']
        >>> hifv_importdata(vis=myvislist)

        5. Run with explicit setting of data column types:

        >>> hifv_importdata(vis=['uid___A002_X30a93d_X43e_targets.ms'], datacolumns={'data': 'regcal_contline'})
        >>> hifv_importdata(vis=['uid___A002_X30a93d_X43e_targets_line.ms'], datacolumns={'data': 'regcal_line', 'corrected': 'selfcal_line'})

    """
