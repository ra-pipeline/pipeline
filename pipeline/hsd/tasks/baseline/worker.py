"""Worker task for baseline subtraction."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import numpy as np

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.sessionutils as sessionutils
import pipeline.infrastructure.vdp as vdp
from pipeline.infrastructure.utils import relative_path
from pipeline.domain import DataTable, DataType
from pipeline.h.heuristics import caltable as caltable_heuristic
from pipeline.hsd.heuristics import BaselineFitParamConfig
from pipeline.hsd.tasks.common import utils as sdutils
from pipeline.infrastructure import casa_tasks
from pipeline.infrastructure import casa_tools
from . import plotter
from .. import common
from ..common import utils
from .typing import FitFunc, FitOrder

if TYPE_CHECKING:
    from numpy import floating
    from numpy.typing import NDArray

    from pipeline.domain import MeasurementSet
    from pipeline.hsd.tasks.common.utils import RGAccumulator
    from pipeline.infrastructure.launcher import Context

LOG = infrastructure.logging.get_logger(__name__)


class BaselineSubtractionWorkerInputs(vdp.StandardInputs):
    """Inputs class for baseline subtraction tasks."""

    DATACOLUMN = {'CORRECTED_DATA': 'corrected',
                  'DATA': 'data',
                  'FLOAT_DATA': 'float_data'}

    # Search order of input vis
    processing_data_type = [DataType.ATMCORR, DataType.REGCAL_CONTLINE_ALL, DataType.RAW]

    parallel = sessionutils.parallel_inputs_impl()

    vis = vdp.VisDependentProperty(default='', null_input=['', None, [], ['']])
    plan = vdp.VisDependentProperty(default=None)
    fit_func = vdp.VisDependentProperty(default='cspline')
    wave_number = vdp.VisDependentProperty(default=None)
    fit_order = vdp.VisDependentProperty(default='automatic')
    switchpoly = vdp.VisDependentProperty(default=True)
    edge = vdp.VisDependentProperty(default=(0, 0))
    deviationmask = vdp.VisDependentProperty(default={})
    bloutput = vdp.VisDependentProperty(default=None)
    org_directions_dict = vdp.VisDependentProperty(default=None)

    @vdp.VisDependentProperty
    def prefix(self) -> str:
        """Return the prefix for several output files of sdbaseline.

        Prefix is the basename of the MS.

        Returns:
            Prefix string
        """
        return os.path.basename(self.vis.rstrip('/'))

    @vdp.VisDependentProperty
    def blparam(self) -> str:
        """Return blparam file name.

        Name is constructed from input MS name.

        Returns:
            The blparam file name
        """
        return self.prefix + '_blparam.txt'

    @vdp.VisDependentProperty(readonly=True)
    def field(self) -> list[int]:
        """Return list of field ids to process.

        Returned list should conform with the list of MS and
        each field id is translated into the one for corresponding
        MS in the list.

        Returns:
            List of field ids to process
        """
        return self.plan.get_field_id_list()

    @vdp.VisDependentProperty(readonly=True)
    def antenna(self) -> list[int]:
        """Return list of antenna ids to process.

        Returned list should conform with the list of MS and
        each antenna id is translated into the one for corresponding
        MS in the list.

        Returns:
            List of antenna ids to process
        """
        return self.plan.get_antenna_id_list()

    @vdp.VisDependentProperty(readonly=True)
    def spw(self) -> list[int]:
        """Return list of spectral window (spw) ids to process.

        Returned list should conform with the list of MS and
        each spw id is translated into the one for corresponding
        MS in the list.

        Returns:
            List of spw ids to process
        """
        return self.plan.get_spw_id_list()

    @vdp.VisDependentProperty(readonly=True)
    def grid_table(self) -> list[int | float | NDArray[floating]]:
        """Return list of grid tables to process.

        Returned list should conform with the list of MS and
        each grid table is supposed to be processed together
        with corresponding MS in the list.

        Returns:
            List of grid tables to process
        """
        return self.plan.get_grid_table_list()

    @vdp.VisDependentProperty(readonly=True)
    def channelmap_range(self) -> list[list[list[int | bool]]]:
        """Return list of line ranges to process.

        Returned list should conform with the list of MS and
        each channelmap range is supposed to be processed together
        with corresponding MS in the list.

        Returns:
            List of channelmap ranges to process
        """
        return self.plan.get_channelmap_range_list()

    @vdp.VisDependentProperty
    def colname(self) -> str:
        """Return name of existing data column in MS.

        Scan through the column names in the MS, and return the most
        'significant' one found from the following list.

            - CORRECTED_DATA
            - DATA
            - FLOAT_DATA

        For example, if MS has CORRECTED_DATA and DATA columns,
        CORRECTED_DATA will be returned.

        Returns a null string if none of them exist.

        Returns:
            Data column name
        """
        colname = ''
        if isinstance(self.vis, str):
            with casa_tools.TableReader(self.vis) as tb:
                candidate_names = ['CORRECTED_DATA',
                                   'DATA',
                                   'FLOAT_DATA']
                for name in candidate_names:
                    if name in tb.colnames():
                        colname = name
                        break
        return colname

    def __init__(
        self,
        context: Context,
        vis: str | list[str] | None = None,
        plan: RGAccumulator | list[RGAccumulator] | None = None,
        fit_func: FitFunc | None = None,
        fit_order: FitOrder | None = None,
        wave_number: list[int] |  None = None,
        switchpoly: bool | None = None,
        edge: list[int] | None = None,
        deviationmask: dict | list[dict] | None = None,
        blparam: str | list[str] | None = None,
        bloutput: str | list[str] | None = None,
        org_directions_dict: dict | None = None,
        parallel: bool | str | None = None
    ) -> None:
        """Construct BaselineSubtractionWorkerInputs instance.

        Args:
            context: Pipeline context
            vis: Name of the MS or list of MSs. Defaults to None,
                 which is to process all MSs registered to the context.
            plan: Set of metadata for baseline subtraction, or List of
                  the them. Defaults to None. The task may fail if None
                  is given.
            fit_func: Fitting function for baseline subtraction. Accepts either 
                      a single string or a dictionary mapping SPW IDs (int or str) 
                      to a fitting function. Valid function options: cubic spline 
                      ('spline' or 'cspline') or polynomial ('poly' or 'polynomial'). 
                      Default is 'cspline'. If a string is given, it applies to all 
                      spectral windows (SPWs). If a dictionary is given, each SPW 
                      can have a different fitting function, with 'cspline' as the 
                      default for missing SPWs.
            fit_order: Fitting order for polynomial. Accepts either a single integer or a dictionary 
                       mapping SPW IDs (int or str) to an integer. For cubic spline, it is used 
                       to determine how much the spectrum is segmented into. Default (None, 'automatic' 
                       or `-1`) triggers automatic order selection (heuristics); `0` or any positive 
                       integer uses the specified order. If a dictionary is provided, each SPW can have 
                       a different order, with `-1` as the default for missing SPWs.
            wave_number: List of wave numbers for sinusoidal fitting. Defaults to None. This is required
                         only when fit_func is set to 'sinusoid'.
            switchpoly: Whether to fall back the fits from cubic spline to 1st or
                        2nd order polynomial when large masks exist at the edges
                        of the spw. Condition for switching is as follows:
                            if nmask > nchan/2      => 1st order polynomial
                            else if nmask > nchan/4 => 2nd order polynomial
                            else                    => use fitfunc and fitorder
                        where nmask is a number of channels for mask at edge while
                        nchan is a number of channels of entire spectral window.
                        Defaults to True if None is given.
            edge: Edge channels to exclude. Defaults to None, which means
                  that all channels are processed.
            deviationmask: List of deviation masks. Defaults to empty list
                           if None is given.
            blparam: Name of the blparam file name. Defaults to
                     '{name_of_ms}_blparam.txt' if None is given.
            bloutput: Name of the bloutput name. Defaults to the name
                      following pipeline product naming convention
                      (see to_casa_args method) if None is given.
            org_directions_dict: Original source direction for ephemeris
                                 correction. Defaults to None. This is
                                 required only when target source is
                                 ephemeris object.
            parallel: Execute using CASA HPC functionality, if available.
                      Default is None, which intends to turn on parallel
                      processing if possible.
        """
        super().__init__()

        self.context = context
        self.vis = vis
        self.plan = plan
        self.fit_order = fit_order
        self.fit_func = fit_func
        self.wave_number = wave_number
        self.switchpoly = switchpoly
        self.edge = edge
        self.deviationmask = deviationmask
        self.blparam = blparam
        self.bloutput = bloutput
        self.org_directions_dict = org_directions_dict
        self.parallel = parallel

    def to_casa_args(self) -> dict:
        """Convert Inputs instance to the list of keyword arguments for sdbaseline.

        Note that core parameters such as blfunc will be set dynamically through
        the heuristics or inside task.

        Returns:
            Keyword arguments for sdbaseline
        """
        args = super().to_casa_args()  # {'vis': self.vis}
        prefix = os.path.basename(self.vis.rstrip('/'))

        # blparam
        if self.blparam is None or len(self.blparam) == 0:
            args['blparam'] = relative_path(os.path.join(self.output_dir, prefix + '_blparam.txt'))
        else:
            args['blparam'] = self.blparam

        # baseline caltable filename
        if self.bloutput is None or len(self.bloutput) == 0:
            namer = caltable_heuristic.SDBaselinetable()
            bloutput = relative_path(namer.calculate(output_dir=self.output_dir,
                                                            stage=self.context.stage,
                                                            **args))
            args['bloutput'] = bloutput
        else:
            args['bloutput'] = self.bloutput

        # outfile
        if ('outfile' not in args or
                args['outfile'] is None or
                len(args['outfile']) == 0):
            args['outfile'] = relative_path(os.path.join(self.output_dir, prefix + '_bl'))

        args['datacolumn'] = self.DATACOLUMN[self.colname]

        return args

 
class BaselineSubtractionResults(common.SingleDishResults):
    """Results class to hold the result of baseline subtraction."""

    def __init__(self,
                 task: type[basetask.StandardTaskTemplate] | None = None,
                 success: bool | None = None,
                 outcome: Any = None) -> None:
        """Construct BaselineSubtractionResults instance.

        Args:
            task: Task class that produced the result.
            success: Whether task execution is successful or not.
            outcome: Outcome of the task execution.
        """
        super().__init__(task, success, outcome)

    def merge_with_context(self, context: Context) -> None:
        """Merge result instance into context.

        No specific merge operation is done.

        Args:
            context: Pipeline context object containing state information.
        """
        super().merge_with_context(context)

    def _outcome_name(self) -> str:
        """Return string representation of outcome.

        Returns:
            Name of the blparam file with its format
        """
        # outcome should be a name of blparam text file
        return 'blparam: "%s" bloutput: "%s"' % (self.outcome['blparam'], self.outcome['bloutput'])


class SerialBaselineSubtractionWorker(basetask.StandardTaskTemplate):
    """Abstract worker class for baseline subtraction."""

    Inputs = BaselineSubtractionWorkerInputs

    is_multi_vis_task = False

    def __init__(self, inputs: BaselineSubtractionWorkerInputs):
        """Construct BaselineSubtractionWorker instance.

        Args:
            inputs: BaselineSubtractionWorkerInputs instance
        """
        super().__init__(inputs)

        # initialize plotter
        self.datatable = DataTable(sdutils.get_data_table_path(self.inputs.context,
                                                               self.inputs.ms))

    def prepare(self) -> BaselineSubtractionResults:
        """Perform baseline subtraction.

        Call sdbaseline task with optimized parameters. Parameter values such
        as function type, fitting order, etc. are optimized by the heuristics
        class defined in Heuristics attribute.

        Returns:
            BaselineSubtractionResults instance
        """
        vis = self.inputs.vis
        ms = self.inputs.ms
        origin_ms = self.inputs.context.observing_run.get_ms(ms.origin_ms)
        rowmap = sdutils.make_row_map_between_ms(origin_ms, vis)
        fit_order = self.inputs.fit_order
        fit_func = self.inputs.fit_func
        edge = self.inputs.edge
        args = self.inputs.to_casa_args()
        blparam = args['blparam']
        bloutput = args['bloutput']
        outfile = args['outfile']
        datacolumn = args['datacolumn']
        wave_number = self.inputs.wave_number
        process_list = self.inputs.plan
        deviationmask_list = self.inputs.deviationmask
        LOG.info('deviationmask_list={}'.format(deviationmask_list))

        field_id_list = self.inputs.field
        antenna_id_list = self.inputs.antenna
        spw_id_list = self.inputs.spw
        LOG.debug('subgroup member for %s:\n\tfield: %s\n\tantenna: %s\n\tspw: %s',
                  ms.basename,
                  field_id_list,
                  antenna_id_list,
                  spw_id_list)
        
        unique_spws = set(spw_id_list)
        
        # Convert the fitting parameters into dictionaries mapping each SPW.
        fit_order_dict = SerialBaselineSubtractionWorker.get_fit_order_dict(
            fit_order, unique_spws, ms, self.inputs.context)

        # This function will handle the per spw fitting functions and build a dictionary
        # of instance BaselineParamConfig() fitting class for each spw.
        spw_funcs_dict = SerialBaselineSubtractionWorker.build_fitting_configuration(
            spw_id_list=unique_spws,
            fit_function=fit_func,
            ms=ms,
            context=self.inputs.context,
            switchpoly=self.inputs.switchpoly
        )

        # Configures wave numbers according to the per spw inputs by users or distributes
        # a single wave number list across each spw that uses `sinusoid` as a fit function.
        #
        # In this way the wave number is required to get a sinusoidal fit. Even if the
        # function is set to `sinusoid`, the wave_number function will fail with an unknown
        # wave number type if it isn't set.
        if wave_number is not None:
            SerialBaselineSubtractionWorker.configure_wave_number(parameter_config=spw_funcs_dict, wave_number=wave_number)

        # initialization of blparam file.
        # blparam file needs to be removed before starting iteration through
        # reduction group
        if os.path.exists(blparam):
            LOG.debug('Cleaning up blparam file for %s', vis)
            os.remove(blparam)

        for (field_id, antenna_id, spw_id) in process_list.iterate_id():
            if (field_id, antenna_id, spw_id) in deviationmask_list:
                deviationmask = deviationmask_list[(field_id, antenna_id, spw_id)]

            else:
                deviationmask = None

            formatted_edge = list(common.parseEdge(edge))
            heuristic = spw_funcs_dict[spw_id]

            current_fit_order = fit_order_dict.get(spw_id, 'automatic')

            out_blparam = heuristic(
                self.datatable, ms, rowmap,
                antenna_id, field_id, spw_id,
                current_fit_order, formatted_edge,
                deviationmask, blparam
            )
            assert out_blparam == blparam

        # execute sdbaseline
        job = casa_tasks.sdbaseline(infile=vis, datacolumn=datacolumn, blmode='fit', dosubtract=True,
                                    blformat='table', bloutput=bloutput,
                                    blfunc='variable', blparam=blparam,
                                    updateweight=True,
                                    outfile=outfile, overwrite=True)
        self._executor.execute(job)

        outcome = {'infile': vis,
                   'blparam': blparam,
                   'bloutput': bloutput,
                   'outfile': outfile}
        results = BaselineSubtractionResults(success=True, outcome=outcome)
        return results

    def analyse(self, results: BaselineSubtractionResults) -> BaselineSubtractionResults:
        """Generate plots from baseline subtraction results.

        Args:
            results: BaselineSubtractionResults instance

        Raises:
            RuntimeError: Source name is invalid or not found in the domain object

        Returns:
            BaselineSubtractionResults instance
        """
        # plot png files of weblog and calculate QA score
        # initialize plot manager
        ms = self.inputs.ms
        outfile = results.outcome['outfile']
        origin_ms = self.inputs.context.observing_run.get_ms(ms.origin_ms)
        origin_ms_id = self.inputs.context.observing_run.measurement_sets.index(origin_ms)
        quality_manager = plotter.BaselineSubtractionQualityManager(ms, outfile, self.inputs.context, self.datatable)
        plot_manager = plotter.BaselineSubtractionPlotManager(ms, outfile, self.inputs.context, self.datatable)
        org_directions_dict = self.inputs.org_directions_dict
        accum = self.inputs.plan
        deviationmask_list = self.inputs.deviationmask
        formatted_edge = list(common.parseEdge(self.inputs.edge))
        out_rowmap = utils.make_row_map(origin_ms, outfile)
        in_rowmap = None if ms.name == ms.origin_ms else utils.make_row_map(origin_ms, ms.name)
        plot_list = []
        stats = []

        for (field_id, antenna_id, spw_id, grid_table, channelmap_range) in accum.iterate_all():
            virtual_spwid = self.inputs.context.observing_run.real2virtual_spw_id(spw_id, ms)
            data_desc = ms.get_data_description(spw=spw_id)
            num_pol = data_desc.num_polarizations
            polids = np.arange(num_pol, dtype=int)
            LOG.info('field %s antenna %s spw %s', field_id, antenna_id, spw_id)
            if (field_id, antenna_id, spw_id) in deviationmask_list:
                deviationmask = deviationmask_list[(field_id, antenna_id, spw_id)]
            else:
                deviationmask = None

            fields = ms.get_fields(field_id=field_id)
            source_name = fields[0].source.name
            if source_name not in org_directions_dict:
                raise RuntimeError("source_name {} not found in org_directions_dict (sources found are {})"
                                   "".format(source_name, list(org_directions_dict.keys())))
            org_direction = org_directions_dict[source_name]
            data_manager = plotter.BaselineSubtractionDataManager(ms, outfile,
                                                                  self.inputs.context,
                                                                  self.datatable)
            num_ra, num_dec, num_plane, rowlist = data_manager.analyze_plot_table(origin_ms_id,
                                                                                  antenna_id,
                                                                                  virtual_spwid,
                                                                                  polids,
                                                                                  grid_table,
                                                                                  org_direction)
            spw = ms.spectral_windows[spw_id]
            nchan = spw.num_channels
            data_desc = ms.get_data_description(spw=spw)
            npol = data_desc.num_polarizations
            data_manager.resize_storage(num_ra, num_dec, npol, nchan)
            frequency = np.fromiter((spw.channels.chan_freqs[i] * 1.0e-9 for i in range(nchan)),
                                    dtype=np.float64)  # unit in GHz
            data = data_manager.store_result_get_data(num_ra, num_dec, rowlist, npol, nchan,
                                                      out_rowmap=out_rowmap, in_rowmap=in_rowmap)
            postfit_integrated_data = data[0]
            postfit_map_data = data[1]
            prefit_integrated_data = data[2]
            prefit_map_data = data[3]
            prefit_averaged_data = data[4]
            stats.extend(quality_manager.calculate_baseline_quality_stat(field_id, antenna_id, spw_id,
                                                                         postfit_integrated_data,
                                                                         npol, frequency,
                                                                         deviationmask,
                                                                         channelmap_range,
                                                                         formatted_edge))
            plot_list.extend(plot_manager.plot_spectra_with_fit(field_id, antenna_id, spw_id,
                                                                postfit_integrated_data,
                                                                postfit_map_data,
                                                                prefit_integrated_data,
                                                                prefit_map_data,
                                                                prefit_averaged_data,
                                                                num_ra, num_dec,
                                                                rowlist, npol, frequency,
                                                                grid_table, deviationmask,
                                                                channelmap_range, formatted_edge,
                                                                in_rowmap=in_rowmap))
        plot_manager.finalize()

        results.outcome['plot_list'] = plot_list
        results.outcome['baseline_quality_stat'] = stats
        return results
    

    def get_fit_order_dict(fit_order: int | dict[int | str, int | None],
                    spw_id_list: list[int], ms: MeasurementSet = None, context: Context = None) -> dict[int, int | str]:
        """
        Convert the fit_order parameter into a dictionary mapping each SPW ID to its fit order.
        
        If fit_order is None or falsy, every SPW is assigned 'automatic' (triggering heuristics).
        If a single integer (or string) is provided, it is applied to all SPWs.
        If a dictionary is provided, keys are normalized to integers; missing SPWs default to 'automatic'.
        
        Args:
            fit_order: The fit order parameter (int, dict, or None).
            spw_id_list: List of spectral window IDs to process.
        
        Raises:
            ValueError: fit_order of string type has unsupported value.
            TypeError: Value of fit_order has unsupported data type.
            
        Returns:
            A dictionary mapping each SPW ID (int) to its fit order (int or 'automatic').
        """
        if not fit_order:
            return {spw_id: 'automatic' for spw_id in spw_id_list}

        elif isinstance(fit_order, (int, str)):
            if isinstance(fit_order, str):
                if fit_order != 'automatic':
                    raise ValueError(f"Unsupported fit_order string: {fit_order}")
                value = fit_order
            elif isinstance(fit_order, int) and fit_order < 0:
                value = 'automatic'
            else:
                value = fit_order
            return {spw_id: value for spw_id in spw_id_list}

        elif isinstance(fit_order, dict):
            fit_order_dict = {}
            for k, v in fit_order.items():
                key = str(context.observing_run.virtual2real_spw_id(k, ms)) if context and ms else str(k) # for unit tests
                if isinstance(v, int) and v < 0:
                    fit_order_dict[key] = 'automatic'
                else:
                    fit_order_dict[key] = v
            return {spw_id: fit_order_dict.get(str(spw_id), 'automatic')
                    for spw_id in spw_id_list}

        else:
            raise TypeError(f"Value of fit_order has wrong data type: {type(fit_order)}")


    @staticmethod
    def build_fitting_configuration(
            spw_id_list: list[int] | set[Any],
            fit_function: str | list[int | str, str] | None = "cspline",
            ms: MeasurementSet = None,
            context: Context = None,
            switchpoly=True
    ) -> dict[int, BaselineFitParamConfig]:
        """
        Convert the fit_function parameter into a dictionary mapping each SPW ID to its BaselineFitParamConfig.

        If fit_function is None, the default 'cspline' is used.
        If a single string is provided, one BaselineFitParamConfig instance is created and applied to all SPWs.
        If a dictionary is provided, keys are normalized to integers; SPWs not specified default to 'cspline'.

        Args:
            switchpoly: Whether to fall back the fits from cubic spline to 1st or
                        2nd order polynomial when large masks exist at the edges
                        of the spw.
            context: Pipeline context
            ms: MeasurementSet
            fit_function: The fit function parameter (str, dict, or None).
            spw_id_list: list of spectral window IDs to process.

        Raises:
            ValueError: fit_function has unsupported value.

        Returns:
            A dictionary mapping each SPW ID (int) to a BaselineFitParamConfig instance.

        """

        valid_functions = {'spline', 'cspline', 'poly', 'polynomial', 'sinusoid'}

        if fit_function is None:
            fit_function = 'cspline'

        if isinstance(fit_function, str):
            if fit_function not in valid_functions:
                raise ValueError(f"Unsupported fitting function value: {fit_function}")

            _spw_id_list = [context.observing_run.virtual2real_spw_id(key, ms) if
                            context is not None else key for key in spw_id_list]

            heuristics_out = {
                spw_id: BaselineFitParamConfig(
                    fitfunc=fit_function,
                    switchpoly=switchpoly
                ) for spw_id in _spw_id_list
            }

            return heuristics_out

        if isinstance(fit_function, dict):

            spw_function_map = dict.fromkeys(spw_id_list, "cspline")
            spw_function_map.update(fit_function)
            heuristics_out = {}

            # Need to fill in the input fit functions. We could make this cleaner without
            # the virtual2real section, but I'm not sure if the keys will match.
            for key, value in spw_function_map.items():
                # Check that all the functions are supported.
                if not value in valid_functions:
                    raise ValueError(f"Unsupported fitting function value: {value}")

                _key = context.observing_run.virtual2real_spw_id(key, ms) if context else key

                heuristics_out[_key] = BaselineFitParamConfig(
                        fitfunc=spw_function_map[key],
                        switchpoly=switchpoly
                    )

            return heuristics_out

        else:
            raise ValueError(f"Unsupported fitting function type: {type(fit_function)}")

    @staticmethod
    def _process_list(
            parameter_config: dict[int, BaselineFitParamConfig],
            wave_number: list[int] = None
    ):
        for config in parameter_config.values():
            # We only need to set this if the fit function is sinusoid. Otherwise,
            # it should already be set to None in the case of polynomials and cspline
            if config.fitfunc.blfunc == "sinusoid":
                config.wave_number = wave_number

        return parameter_config

    @staticmethod
    def _process_dictionary(
            parameter_config: dict[int, BaselineFitParamConfig],
            wave_number: dict[int, list] = None
    )->dict[int, BaselineFitParamConfig]:

        for key, value in parameter_config.items():
            if key in wave_number.keys() and value.fitfunc.blfunc == "sinusoid":
                parameter_config[key].wave_number = wave_number[key]

        return parameter_config

    @staticmethod
    def configure_wave_number(
            parameter_config: dict[int, BaselineFitParamConfig],
            wave_number: list | dict = None,
    )->None:
        # Possible inputs, wave_number: list, dict[int: list[int]]
        # Check that wave number is a list or a dictionary
        if isinstance(wave_number, list):
            SerialBaselineSubtractionWorker._process_list(
                parameter_config,
                wave_number
            )

            return

        elif isinstance(wave_number, dict):
            SerialBaselineSubtractionWorker._process_dictionary(
                parameter_config,
                wave_number
            )

            return

        else:
            LOG.error("Couldn't determine wave_number data type. Choices are: list, dict{int, string}")
            raise TypeError
        
class BaselineSubtractionWorker(sessionutils.ParallelTemplate):
    """Template class for parallel baseline subtraction task.

    This class is a template for parallel processing that executes
    the task specified by Task property. Parallel processing is
    enabled when parallel attribute of Inputs instance is True and
    pipeline runs on mpicasa environment.

    Note that this is abstract class. Task property must be implemented
    in each subclass.
    """
    Inputs = BaselineSubtractionWorkerInputs
    Task = SerialBaselineSubtractionWorker
