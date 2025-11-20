"""
Importdata tasks for observation data of Nobeyama.

This task loads the specified visibility data into the pipeline
context unpacking and / or converting it as necessary.

Created on Dec 4, 2017

@author: kana
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import pipeline.hsd.tasks.importdata.importdata as sd_importdata
import pipeline.infrastructure as infrastructure
from pipeline.infrastructure import casa_tools, task_registry

if TYPE_CHECKING:
    from pipeline.domain.fluxmeasurement import FluxMeasurement
    from pipeline.domain.measurementset import MeasurementSet
    from pipeline.domain.singledish import MSReductionGroupDesc
    from pipeline.infrastructure.launcher import Context

LOG = infrastructure.get_logger(__name__)


class NROImportDataInputs(sd_importdata.SDImportDataInputs):
    """Class of inputs of NROImportData.

    This class extends importdata.ImportDataInputs.
    """

    # docstring and type hints: supplements hsdn_importdata
    def __init__(
            self,
            context: Context,
            vis: list[str] | None = None,
            output_dir: str | None = None,
            session: list[str] | None = None,
            datacolumns: dict | None = None,
            overwrite: bool | None = None,
            nocopy: bool | None = None,
            createmms: str | None = None,
            hm_rasterscan: str | None = None,
            ):
        """Initialise NROImportDataInputs class.

        Args:
            context: pipeline context

            vis: List of visibility data files. These may be MSes,
                or tar files of MSes.

                Example: vis=['X227.ms', 'anyms.tar.gz']

            output_dir: path of output directory

            session: List of sessions to which the visibility files belong.
                Defaults to a single session containing all the visibility
                files, otherwise a session must be assigned to each vis file.

                Example: session=['Session_1', 'Sessions_2']

            datacolumns: Dictionary defining the data types of existing columns.
                The format is:

                    {'data': 'data type 1'}

                or

                    {'data': 'data type 1', 'corrected': 'data type 2'}

                For MSes one can define two different data types for the DATA and
                CORRECTED_DATA columns and they can be any of the known data types
                (RAW, REGCAL_CONTLINE_ALL, REGCAL_CONTLINE_SCIENCE,
                SELFCAL_CONTLINE_SCIENCE, REGCAL_LINE_SCIENCE,
                SELFCAL_LINE_SCIENCE, BASELINED, ATMCORR).
                The intent selection strings _ALL or _SCIENCE can be skipped.
                In that case the task determines this automatically by inspecting
                the existing intents in the dataset.
                Usually, a single datacolumns dictionary is used for all datasets.
                If necessary, one can define a list of dictionaries, one for each MS,
                with different setups per MS.
                If no type is specified, {'data':'raw'} will be assumed.

            overwrite: Overwrite existing files on import.
                If overwrite=False and the MS already exists in output directory,
                then this existing MS dataset will be used instead.

            nocopy: Disable copying of MS to working directory.

            createmms: Create an MMS

            hm_rasterscan: Heuristics method for raster scan analysis.
                Two analysis modes, time-domain analysis ('time') and
                direction analysis ('direction'), are available.

                Default: None (equivalent to 'time')
        """
        # no-op parameters for MS
        asis = ''
        process_caldevice = False
        bdfflags = False
        lazy = False
        ocorr_mode = 'ao'
        save_flagonline = False

        super().__init__(context, vis=vis, output_dir=output_dir, asis=asis, process_caldevice=process_caldevice,
                         session=session, overwrite=overwrite, nocopy=nocopy, save_flagonline=save_flagonline,
                         bdfflags=bdfflags, lazy=lazy, createmms=createmms, ocorr_mode=ocorr_mode,
                         datacolumns=datacolumns, hm_rasterscan=hm_rasterscan)


class NROImportDataResults(sd_importdata.SDImportDataResults):
    """NROImportDataResults is an equivalent class with ImportDataResults.

    Purpose of NROImportDataResults is to replace QA scoring associated
    with ImportDataResults with single dish specific QA scoring, which
    is associated with this class.

    ImportDataResults holds the results of the ImportData task. It contains
    the resulting MeasurementSet domain objects and optionally the additional
    SetJy results generated from flux entries in Source.xml.
    """

    def __init__(
            self,
            mses: list[MeasurementSet] | None = None,
            reduction_group_list: list[dict[int, MSReductionGroupDesc]] | None = None,
            datatable_prefix: str | None = None,
            setjy_results: list[FluxMeasurement] | None = None,
            ):
        """Initialise NROImportDataResults class.

        Args:
            mses: list of MeasurementSet domain objects
            reduction_group_list: list of dictionaries that consist of reduction group IDs (key) and MSReductionGroupDesc (value)
            datatable_prefix: table name prefix of MeasurementSet
            setjy_results: the flux results generated from Source.xml
        """
        super().__init__(mses=mses, reduction_group_list=reduction_group_list, datatable_prefix=datatable_prefix,
                         setjy_results=setjy_results)

    def merge_with_context(self, context: Context) -> None:
        """Override method of basetask.Results.merge_with_context.

        Args:
            context: pipeline context
        """
        super().merge_with_context(context)
        # Set observatory information
        for ms in self.mses:
            if ms.antenna_array.name in ('NRO',):
                ms.array_name = 'TP'
                context.project_summary.telescope = 'NRO'
                context.project_summary.observatory = 'Nobeyama Radio Observatory'
                break


@task_registry.set_equivalent_casa_task('hsdn_importdata')
@task_registry.set_casa_commands_comment('Import Nobeyama MeasurementSets.')
class NROImportData(sd_importdata.SerialSDImportData):
    """NRO Data import execution task.

    This class extends importdata.ImportData class, and methods execute main logics depends on it.
    """

    Inputs = NROImportDataInputs

    def prepare(self, **parameters: dict[str, Any]) -> NROImportDataResults:
        """Prepare job requests for execution.

        Args:
            parameters: the parameters to pass through from the superclass.
        Returns:
            NROImportDataResults : result object
        """
        # the input data should be MSes
        # TODO: check data type
        # get results object by running super.prepare()
        results = super().prepare()
        myresults = NROImportDataResults(mses=results.mses, reduction_group_list=results.reduction_group_list,
                                         datatable_prefix=results.datatable_prefix, setjy_results=results.setjy_results)
        myresults.origin = results.origin
        myresults.msglist = results.msglist
        return myresults

    def analyse(self, result: NROImportDataResults) -> NROImportDataResults:
        """Get version information for merge2 and set it to MS of result.

        Args:
            result: Result object
        Returns:
            NROImportDataResults : result object
        """
        for ms in result.mses:
            with casa_tools.TableReader(os.path.join(ms.name, 'OBSERVATION')) as tb:
                col = 'RELEASE_DATE'
                release_dates = tb.getcol(col)
                unit = tb.getcolkeywords(col)['QuantumUnits'][0]
            if len(release_dates) > 0:
                release_date = release_dates[0]
                qa = casa_tools.quanta
                merge2_version = qa.time(qa.quantity(release_date, unit), form='ymd')
                if isinstance(merge2_version, list):
                    merge2_version = merge2_version[0]
            else:
                merge2_version = 'N/A'
            ms.merge2_version = merge2_version
        return result
