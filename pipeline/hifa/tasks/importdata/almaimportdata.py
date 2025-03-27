# Do not evaluate type annotations at definition time.
from __future__ import annotations

import ssl
import urllib
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Union

import certifi

from pipeline import infrastructure
from pipeline.h.tasks.importdata import fluxes, importdata
from pipeline.hifa.tasks.importdata import dbfluxes
from pipeline.infrastructure import sessionutils, vdp, task_registry

if TYPE_CHECKING:
    from pipeline.domain import MeasurementSet, ObservingRun
    from pipeline.infrastructure.launcher import Context
    from pipeline.h.tasks.common.commonfluxresults import FluxCalibrationResults

__all__ = [
    'ALMAImportData',
    'SerialALMAImportData',
    'ALMAImportDataInputs',
    'ALMAImportDataResults'
]

LOG = infrastructure.logging.get_logger(__name__)


class ALMAImportDataInputs(importdata.ImportDataInputs):
    # PIPE-2067: Added Pointing to retrieve ASDM_POINTING table for offset information
    asis = vdp.VisDependentProperty(
        default='Annotation Antenna CalAtmosphere CalPointing CalWVR ExecBlock Receiver Pointing SBSummary Source Station'
        )
    dbservice = vdp.VisDependentProperty(default=False)
    createmms = vdp.VisDependentProperty(default='false')
    # sets threshold for polcal parallactic angle coverage. See PIPE-597
    minparang = vdp.VisDependentProperty(default=0.0)
    parallel = sessionutils.parallel_inputs_impl(default=False)

    # docstring and type hints: supplements hifa_importdata
    def __init__(
            self, context: Context, vis: Optional[List[str]] = None, output_dir: Optional[str] = None,
            asis: Optional[str] = None, process_caldevice: Optional[bool] = None, session: Optional[str] = None,
            overwrite: Optional[bool] = None, nocopy: Optional[bool] = None, bdfflags: Optional[bool] = None,
            lazy: Optional[bool] = None, save_flagonline: Optional[bool] = None, dbservice: Optional[bool] = None,
            createmms: Optional[str] = None, ocorr_mode: Optional[str] = None, datacolumns: Optional[Dict[str, str]] = None,
            minparang: Optional[float] = None, parallel: Optional[bool] = None
            ):
        """Initialize Inputs.

        Args:
            context: Pipeline context.

            vis: List of visibility data files. These may be ASDMs, tar
                files of ASDMs, MSes, or tar files of MSes. If ASDM files
                are specified, they will be converted to MS format.

                Example: vis=['X227.ms', 'asdms.tar.gz']

            output_dir: Output directory.
                Defaults to None, which corresponds to the current working directory.

            asis: Creates verbatim copies of the ASDM tables in the output MS.
                The value given to this option must be a list of table names
                separated by space characters.

            process_caldevice: Import the caldevice table from the ASDM.

            session: List of session names, one for each visibility dataset,
                used to group the MSes into sessions.

                Example: session=['session_1', 'session_2']

            overwrite: Overwrite existing files on import; defaults to False.
                When converting ASDM to MS, if overwrite=False and the MS
                already exists in the output directory, then this existing
                MS dataset will be used instead.

                Example: overwrite=True

            nocopy: Disable copying of MS to working directory; defaults to
                False.

                Example: nocopy=True

            bdfflags: Apply BDF flags on import.

            lazy: Use the lazy filler import.

            save_flagonline:

            dbservice: Use the online flux catalog.

            createmms: Create an MMS.

            ocorr_mode: ALMA default set to ca.

            datacolumns: Dictionary defining the data types of existing columns.
                The format is:

                {'data': 'data type 1'}

                or

                {'data': 'data type 1', 'corrected': 'data type 2'}.

                For ASDMs the data type can only be RAW and one
                can only specify it for the data column.
                For MSes one can define two different data types
                for the DATA and CORRECTED_DATA columns and they
                can be any of the known data types (RAW,
                REGCAL_CONTLINE_ALL, REGCAL_CONTLINE_SCIENCE,
                SELFCAL_CONTLINE_SCIENCE, REGCAL_LINE_SCIENCE,
                SELFCAL_LINE_SCIENCE, BASELINED, ATMCORR). The
                intent selection strings _ALL or _SCIENCE can be
                skipped. In that case the task determines this
                automatically by inspecting the existing intents
                in the dataset.
                Usually, a single datacolumns dictionary is used
                for all datasets. If necessary, one can define a
                list of dictionaries, one for each EB, with
                different setups per EB.
                If no types are specified,
                {'data':'raw','corrected':'regcal_contline'}
                or {'data':'raw'} will be assumed, depending on
                whether the corrected column exists or not.

            minparang: Minimum required parallactic angle range for polarisation
                calibrator, in degrees. The default of 0.0 is used for
                non-polarisation processing.

            parallel: Execute using CASA HPC functionality, if available.

        """
        super().__init__(context, vis=vis, output_dir=output_dir, asis=asis,
                         process_caldevice=process_caldevice, session=session,
                         overwrite=overwrite, nocopy=nocopy, bdfflags=bdfflags, lazy=lazy,
                         save_flagonline=save_flagonline, createmms=createmms,
                         ocorr_mode=ocorr_mode, datacolumns=datacolumns)
        self.dbservice = dbservice
        self.minparang = minparang
        self.parallel = parallel


class ALMAImportDataResults(importdata.ImportDataResults):
    def __init__(
            self,
            mses: Optional[List[MeasurementSet]] = None,
            setjy_results: Optional[List[FluxCalibrationResults]] = None
            ):
        super().__init__(mses=mses, setjy_results=setjy_results)
        self.parang_ranges = {}

    def __repr__(self) -> str:
        return 'ALMAImportDataResults:\n\t{0}'.format(
            '\n\t'.join([ms.name for ms in self.mses]))


class SerialALMAImportData(importdata.ImportData):
    Inputs = ALMAImportDataInputs
    Results = ALMAImportDataResults

    def _get_fluxes(
            self, context: Context, observing_run: ObservingRun
            ) -> Tuple[str, List[FluxCalibrationResults], Union[List[Dict[str, Union[str, None]]], None]]:
        # get the flux measurements from Source.xml for each MS

        if self.inputs.dbservice:
            testquery = '?DATE=27-March-2013&FREQUENCY=86837309056.169219970703125&WEIGHTED=true&RESULT=1&NAME=J1427-4206&VERBOSE=1'
            # Test for service response
            flux_url, backup_flux_url = dbfluxes.get_flux_urls()
            url = flux_url + testquery

            try:
                ssl_context = ssl.create_default_context(cafile=certifi.where())
                LOG.info('Attempting test query at: %s', url)
                urllib.request.urlopen(url, context=ssl_context, timeout=60.0)
                xml_results, qastatus = dbfluxes.get_setjy_results(observing_run.measurement_sets)
                fluxservice = 'FIRSTURL'
            except Exception as e:
                try:
                    LOG.warning('Unable to execute initial test query with primary flux service.')
                    ssl_context = ssl.create_default_context(cafile=certifi.where())
                    url = backup_flux_url + testquery
                    LOG.info('Attempting test query at backup: %s', url)
                    urllib.request.urlopen(url, context=ssl_context, timeout=60.0)
                    xml_results, qastatus = dbfluxes.get_setjy_results(observing_run.measurement_sets)
                    fluxservice='BACKUPURL'
                except Exception as e2:
                    LOG.warning(('Unable to execute backup test query with flux service.\n'
                                 'Proceeding without using the online flux catalog service.'))
                    xml_results = fluxes.get_setjy_results(observing_run.measurement_sets)
                    fluxservice = 'FAIL'
                    qastatus = None
        else:
            xml_results = fluxes.get_setjy_results(observing_run.measurement_sets)
            fluxservice = None
            qastatus = None
        # write/append them to flux.csv

        # Cycle 1 hack for exporting the field intents to the CSV file:
        # export_flux_from_result queries the context, so we pseudo-register
        # the mses with the context by replacing the original observing run
        orig_observing_run = context.observing_run
        context.observing_run = observing_run
        try:
            fluxes.export_flux_from_result(xml_results, context)
        finally:
            context.observing_run = orig_observing_run

        # re-read from flux.csv, which will include any user-coded values
        combined_results = fluxes.import_flux(context.output_dir, observing_run)

        return fluxservice, combined_results, qastatus


@task_registry.set_equivalent_casa_task('hifa_importdata')
@task_registry.set_casa_commands_comment('If required, ASDMs are converted to MeasurementSets.')
class ALMAImportData(sessionutils.ParallelTemplate):
    """ALMAImportData class for parallelization."""

    Inputs = ALMAImportDataInputs
    Task = SerialALMAImportData
