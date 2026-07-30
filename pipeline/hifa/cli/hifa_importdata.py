import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.importdata.almaimportdata.ALMAImportDataInputs.__init__
@utils.cli_wrapper
def hifa_importdata(vis=None, session=None, asis=None, process_caldevice=None, overwrite=None, nocopy=None,
                    bdfflags=None, datacolumns=None, lazy=None, dbservice=None, ocorr_mode=None, createmms=None,
                    minparang=None, parallel=None):
    """Imports data into the interferometry pipeline.

    The ``hifa_importdata`` task loads the specified visibility data into the pipeline context, unpacking and/or
    converting it as necessary. ASDMs are imported into MeasurementSets, Binary Data Flags are applied, and some
    properties of those MSs are calculated.

    If the ``overwrite`` input parameter is set to False and the task is asked to convert an input ASDM to an MS,
    then when the output MS already exists in the output directory, the importasdm conversion step is skipped, and
    the existing MS will be imported instead.

    The WebLog page shows a summary of imported MSs and flux densities of calibrators. Flux densities are first
    read from the Source.xml table of the ASDM (recorded by the online system from the calibrator catalog), then
    updated by querying the online ALMA calibrator flux service (controlled by ``dbservice=True``), allowing
    post-observation observatory measurements to be used. The flux densities for each calibrator in each science
    spw in each MS are written to the file ``flux.csv`` in the ``calibration/`` subdirectory.

    If a POLARIZATION intent is present, the parallactic angle coverage of each polarization session is shown
    graphically and reported quantitatively.

    Notes:
        **QA Scoring**

        Poor QA scores result from conditions including missing scan intents or calibrator positions, out-of-date
        IERS table, or previously processed data. A QA score of 0.9 is given for high-frequency data (Bands 9 or
        10). For the flux database query, the score is 0.3 if the database value could not be used and the flux
        for any spw is from the ASDM, 0.5 if the query returned a warning or had a value older than 14 days,
        otherwise 1.0. A QA score of 0.60 results if the parallactic angle coverage is less than 60 degrees.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Load an ASDM list in the ../rawdata subdirectory into the context:

        >>> hifa_importdata(vis=['../rawdata/uid___A002_X30a93d_X43e', '../rawdata/uid_A002_x30a93d_X44e'])

        2. Load an MS in the current directory into the context:

        >>> hifa_importdata(vis=['uid___A002_X30a93d_X43e.ms'])

        3. Load a tarred ASDM in ../rawdata into the context:

        >>> hifa_importdata(vis=['../rawdata/uid___A002_X30a93d_X43e.tar.gz'])

        4. Import a list of MeasurementSets:

        >>> myvislist = ['uid___A002_X30a93d_X43e.ms', 'uid_A002_x30a93d_X44e.ms']
        >>> hifa_importdata(vis=myvislist)

        5. Run with explicit setting of data column types:

        >>> hifa_importdata(vis=['uid___A002_X30a93d_X43e_targets.ms'], datacolumns={'data': 'regcal_contline'})
        >>> hifa_importdata(vis=['uid___A002_X30a93d_X43e_targets_line.ms'],
        ...                    datacolumns={'data': 'regcal_line', 'corrected': 'selfcal_line'})

    """
