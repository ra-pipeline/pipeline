import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsd.tasks.importdata.importdata.SDImportDataInputs.__init__
@utils.cli_wrapper
def hsd_importdata(vis=None, session=None, hm_rasterscan=None, parallel=None, asis=None, process_caldevice=None, overwrite=None,
                   nocopy=None, bdfflags=None, datacolumns=None, lazy=None, with_pointing_correction=None, createmms=None):
    """Import ASDM/MS data into the single-dish pipeline context.

    Loads the specified visibility data into the pipeline context, unpacking and/or converting it
    as necessary. The WebLog shows the summary of imported MSs, grouping of spws to be reduced
    together, and spw matching between Tsys and science spws.

    Telescope pointing plots are generated and available from the MS Summary page (Home -- MS name
    -- ``Telescope Pointing``). Two plot types are shown:

    - On-source positions only.
    - All positions including OFF positions.

    In these plots: the red circle indicates the beam size at the starting position of the raster
    scan; the red dot marks the last scan position; the green line represents antenna slewing
    motion; gray dots indicate flagged data. For moving objects (e.g. solar system bodies), an
    additional set of pointing plots with ephemeris correction is produced.

    .. figure:: /figures/guide-img034.png
       :scale: 60%
       :alt: Telescope Pointing detail page

       The detailed page of Telescope Pointing on the MS summary page.

    If ``overwrite=False`` and the task is asked to
    convert an input ASDM input to an MS, then when the output MS already exists in
    the output directory, the ``importasdm`` conversion step is skipped, and the
    existing MS will be imported instead.

    Notes:
        QA scoring:

        - 1.0 if ATMOSPHERE intents are present.
        - 1.0 if a single continuous observing session is present.
        - 1.0 if all source coordinates are available.
        - -0.5 if existing processing history is detected.
        - -0.5 if existing model data is detected.

    Examples:
        1. Load ASDMs from the ``../rawdata`` directory into the context:

        >>> hsd_importdata(vis=['../rawdata/uid___A002_X30a93d_X43e', '../rawdata/uid_A002_x30a93d_X44e'])

        2. Load an MS in the current directory:

        >>> hsd_importdata(vis=['uid___A002_X30a93d_X43e.ms'])

        3. Load a tarred ASDM:

        >>> hsd_importdata(vis=['../rawdata/uid___A002_X30a93d_X43e.tar.gz'])

        4. Import a list of MeasurementSets:

        >>> hsd_importdata(vis=['uid___A002_X30a93d_X43e.ms', 'uid_A002_x30a93d_X44e.ms'])

    """
