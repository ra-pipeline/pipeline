"""
The hsd_importdata task.

This task loads the specified visibility data into the pipeline
context unpacking and / or converting it as necessary.
"""

import os
from typing import Any, Dict, List, Optional, Union

import pipeline.h.tasks.importdata.importdata as importdata
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.sessionutils as sessionutils
import pipeline.infrastructure.vdp as vdp
from pipeline.h.tasks.common.commonfluxresults import FluxCalibrationResults
from pipeline.domain.measurementset import MeasurementSet
from pipeline.domain.observingrun import ObservingRun
from pipeline.domain.singledish import MSReductionGroupDesc
from pipeline.hsd.tasks.common.inspection_util import merge_reduction_group
from pipeline.infrastructure import task_registry
from pipeline.infrastructure.launcher import Context
from pipeline.infrastructure.utils import relative_path

from . import inspection

LOG = infrastructure.get_logger(__name__)


class SDImportDataInputs(importdata.ImportDataInputs):
    """Class of inputs of SDImportData.

    This class extends importdata.ImportDataInputs.
    """

    asis = vdp.VisDependentProperty(default='SBSummary ExecBlock Annotation Antenna Station Receiver Source CalAtmosphere CalWVR SpectralWindow')
    ocorr_mode = vdp.VisDependentProperty(default='ao')
    with_pointing_correction = vdp.VisDependentProperty(default=True)
    createmms = vdp.VisDependentProperty(default='false')
    hm_rasterscan = vdp.VisDependentProperty(default='time')

    parallel = sessionutils.parallel_inputs_impl()

    # docstring and type hints: supplements hsd_importdata
    def __init__(self,
                 context: Context,
                 vis: Optional[List[str]] = None,
                 output_dir: Optional[str] = None,
                 asis: Optional[str] = None,
                 process_caldevice: Optional[bool] = None,
                 session: Optional[List[str]] = None,
                 overwrite: Optional[bool] = None,
                 nocopy: Optional[bool] = None,
                 bdfflags: Optional[bool] = None,
                 datacolumns: Optional[Dict] = None,
                 save_flagonline: Optional[bool] = None,
                 lazy: Optional[bool] = None,
                 with_pointing_correction: Optional[bool] = None,
                 createmms: Optional[str] = None,
                 ocorr_mode: Optional[str] = None,
                 hm_rasterscan: Optional[str] = None,
                 parallel: Optional[Union[str, bool]] = None):
        """Initialise SDImportDataInputs class.

        Args:
            context: pipeline context

            vis: List of visibility data files. These may be ASDMs, tar files of ASDMs,
                MSes, or tar files of MSes, If ASDM files are specified, they will be
                converted to MS format.

                Example: vis=['X227.ms', 'asdms.tar.gz']

            output_dir: path of output directory

            asis: Creates verbatim copies of the ASDM tables in the output MS.
                The value given to this option must be a list of table names
                separated by space characters. Default value, None, is
                equivalent to the following list.

                    'SBSummary ExecBlock Annotation Antenna Station Receiver Source CalAtmosphere CalWVR SpectralWindow'

                Example: 'Receiver', ''

            process_caldevice: Import the ASDM caldevice table.

                Example: True

                Default: None (equivalent to True)

            session: List of sessions to which the visibility files belong.
                Defaults to a single session containing all the visibility files,
                otherwise a session must be assigned to each vis file.

                Example: session=['Session_1', 'Sessions_2']

            overwrite: Overwrite existing files on import. When converting
                ASDM to MS, if overwrite=False and the MS already exists in
                output directory, then this existing MS dataset will be used
                instead.

                Default: None (equivalent to False)

            nocopy: Disable copying of MS to working directory

            bdfflags: Apply BDF flags on import.

            datacolumns: Dictionary defining the data types of existing columns.
                The format is:

                    {'data': 'data type 1'}

                or

                    {'data': 'data type 1', 'corrected': 'data type 2'}

                For ASDMs the data type can only be RAW and one can only specify
                it for the data column.
                For MSes one can define two different data types for the DATA and
                CORRECTED_DATA columns and they can be any of the known data types
                (RAW, REGCAL_CONTLINE_ALL, REGCAL_CONTLINE_SCIENCE,
                SELFCAL_CONTLINE_SCIENCE, REGCAL_LINE_SCIENCE,
                SELFCAL_LINE_SCIENCE, BASELINED, ATMCORR).
                The intent selection strings _ALL or _SCIENCE can be skipped.
                In that case the task determines this automatically by inspecting
                the existing intents in the dataset.
                Usually, a single datacolumns dictionary is used for all datasets.
                If necessary, one can define a list of dictionaries, one for each EB,
                with different setups per EB. If no type is specified, {'data':'raw'}
                will be assumed.

            save_flagonline: Save flag commands, flagging template, imaging targets, to text files。

                Default: None (equivalent to True)

            lazy: Use the lazy filter import.

                Default: None (equivalent to False)

            with_pointing_correction: Apply pointing correction to DIRECTION.
                Add (ASDM::Pointing::encoder - ASDM::Pointing::pointingDirection)
                to the value to be written in MS::Pointing::direction.

                Default: None (equivalent to True)

            createmms: Create an MMS.

                Default: None (equivalent to False)

            ocorr_mode: Selection of baseline correlation to import.
                Valid only if input visibility is ASDM. See a document of CASA,
                casatasks::importasdm, for available options.

                Default: None (equivalent to 'ao')

            hm_rasterscan: Heuristics method for raster scan analysis.
                Two analysis modes, time-domain analysis ('time') and
                direction analysis ('direction'), are available.

                Default: None (equivalent to 'time')

            parallel: Execute using CASA HPC functionality, if available.

                Options: 'automatic', 'true', 'false', True, False

                Default: None (equivalent to 'automatic')
        """
        super().__init__(context, vis=vis, output_dir=output_dir, asis=asis,
                         process_caldevice=process_caldevice, session=session,
                         overwrite=overwrite, nocopy=nocopy, bdfflags=bdfflags, lazy=lazy,
                         save_flagonline=save_flagonline, createmms=createmms,
                         ocorr_mode=ocorr_mode, datacolumns=datacolumns)
        self.with_pointing_correction = with_pointing_correction
        self.hm_rasterscan = hm_rasterscan
        self.parallel = parallel


class SDImportDataResults(basetask.Results):
    """SDImportDataResults is an equivalent class with ImportDataResults.

    Purpose of SDImportDataResults is to replace QA scoring associated
    with ImportDataResults with single dish specific QA scoring, which
    is associated with this class.

    ImportDataResults holds the results of the ImportData task. It contains
    the resulting MeasurementSet domain objects and optionally the additional
    SetJy results generated from flux entries in Source.xml.
    """

    def __init__(self,
                 mses: Optional[List[MeasurementSet]] = None,
                 reduction_group_list: Optional[List[Dict[int, MSReductionGroupDesc]]] = None,
                 datatable_prefix: Optional[str] = None,
                 setjy_results: Optional[List[FluxCalibrationResults]] = None,
                 org_directions: Optional[Dict[str, Union[str, Dict[str, Union[str, float]]]]] = None):
        """Initialise SDImportDataResults class.

        Args:
            mses: list of MeasurementSet domain objects
            reduction_group_list: list of dictionaries that consist of reduction group IDs (key) and MSReductionGroupDesc (value)
            datatable_prefix: path to directory that stores DataTable of each MeasurementSet
            setjy_results: the flux results generated from Source.xml
            org_directions: dict of Direction objects of the origin
        """
        super(SDImportDataResults, self).__init__()
        self.mses = [] if mses is None else mses
        self.reduction_group_list = reduction_group_list
        self.datatable_prefix = datatable_prefix
        self.setjy_results = setjy_results
        self.org_directions = org_directions
        self.origin = {}
        self.rasterscan_heuristics_results_direction = {}
        self.rasterscan_heuristics_results_time = {}
        self.results = importdata.ImportDataResults(mses=mses, setjy_results=setjy_results)

    def merge_with_context(self, context: Context):
        """Override method of basetask.Results.merge_with_context.

        Args:
            context: pipeline context
        """
        self.results.merge_with_context(context)
        self.__merge_reduction_group(context.observing_run, self.reduction_group_list)
        context.observing_run.ms_datatable_name = self.datatable_prefix
        context.observing_run.org_directions = self.org_directions

    def __merge_reduction_group(self, observing_run: ObservingRun, reduction_group_list: List[Dict[int, MSReductionGroupDesc]]):
        """Call merge_reduction_group.

        Args:
            observing_run: pipeline.domain.observingrun.ObservingRun object
            reduction_group_list: list of dictionaries that consist of reduction group IDs (key) and MSReductionGroupDesc (value)
        """
        for reduction_group in reduction_group_list:
            merge_reduction_group(observing_run, reduction_group)

    def __repr__(self) -> str:
        """Override of __repr__.

        Returns:
            str: repr string
        """
        return 'SDImportDataResults:\n\t{0}'.format('\n\t'.join([ms.name for ms in self.mses]))


class SerialSDImportData(importdata.ImportData):
    """Data import execution task of SingleDish.

    This class extends importdata.ImportData class, and methods execute main logics depends on it.
    """

    Inputs = SDImportDataInputs

    def prepare(self, **parameters: Dict[str, Any]) -> SDImportDataResults:
        """Prepare job requests for execution.

        Args:
            parameters: the parameters to pass through from the superclass.
        Returns:
            SDImportDataResults : result object
        """
        # get results object by running super.prepare()
        results = super(SerialSDImportData, self).prepare()

        # per MS inspection
        table_prefix = relative_path(os.path.join(self.inputs.context.name, 'MSDataTable.tbl'),
                                     self.inputs.output_dir)
        reduction_group_list = []
        direction_rsh_result_list = []
        time_rsh_result_list = []
        org_directions_dict = {}
        for ms in results.mses:
            LOG.debug('Start inspection for %s' % ms.basename)
            table_name = os.path.join(table_prefix, ms.basename)
            inspector = inspection.SDInspection(self.inputs.context, table_name, ms=ms, hm_rasterscan=self.inputs.hm_rasterscan)
            reduction_group, org_directions, msglist, direction_rsh_result, time_rsh_result = self._executor.execute(inspector, merge=False)
            reduction_group_list.append(reduction_group)
            direction_rsh_result_list.append(direction_rsh_result)
            time_rsh_result_list.append(time_rsh_result)

            # update org_directions_dict for only new keys in org_directions
            for key in org_directions:
                org_directions_dict.setdefault(key, org_directions[key])

        # create results object
        myresults = SDImportDataResults(mses=results.mses,
                                        reduction_group_list=reduction_group_list,
                                        datatable_prefix=table_prefix,
                                        setjy_results=results.setjy_results,
                                        org_directions=org_directions_dict)

        myresults.origin = results.origin
        myresults.msglist = msglist
        for rsh in direction_rsh_result_list:
            myresults.rasterscan_heuristics_results_direction.setdefault(rsh.ms.origin_ms, []).append(rsh)
        for rsh in time_rsh_result_list:
            myresults.rasterscan_heuristics_results_time.setdefault(rsh.ms.origin_ms, []).append(rsh)
        return myresults

    def _get_fluxes(self, context, observing_run):
        # override _get_fluxes not to create flux.csv (PIPE-1846)
        # do nothing, return empty results
        return None, [], None


# Tier-0 parallelization
@task_registry.set_equivalent_casa_task('hsd_importdata')
@task_registry.set_casa_commands_comment('If required, ASDMs are converted to MeasurementSets.')
class SDImportData(sessionutils.ParallelTemplate):
    """SDImportData class for parallelization."""

    Inputs = SDImportDataInputs
    Task = SerialSDImportData
