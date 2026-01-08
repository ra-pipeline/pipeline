from __future__ import annotations

import os
from typing import TYPE_CHECKING
import numpy

import pipeline.extern.sd_applycal_qa.sd_applycal_qa as sd_applycal_qa
import pipeline.extern.sd_applycal_qa.sd_qa_reports as sd_qa_reports
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.renderer.logger as logger
import pipeline.infrastructure.vdp as vdp
import pipeline.infrastructure.sessionutils as sessionutils
from pipeline.domain.datatable import DataTableImpl as DataTable
from pipeline.domain import DataType
from pipeline.h.tasks.applycal.applycal import SerialApplycal, ApplycalInputs, ApplycalResults
from pipeline.hsd.tasks.applycal.display import ApplyCalSingleDishPlotmsSpwComposite, ApplyCalSingleDishPlotmsAntSpwComposite
import pipeline.hsd.tasks.applycal.display as display
from pipeline.infrastructure import casa_tools
from pipeline.infrastructure import task_registry

if TYPE_CHECKING:
    from pipeline.domain import MeasurementSet
    from pipeline.infrastructure import CalApplication
    from pipeline.infrastructure.launcher import Context

LOG = infrastructure.get_logger(__name__)


class SDApplycalInputs(ApplycalInputs):
    """
    ApplycalInputs defines the inputs for the Applycal pipeline task.
    """
    # use common implementation for parallel inputs argument
    parallel = sessionutils.parallel_inputs_impl()

    flagdetailedsum = vdp.VisDependentProperty(default=True)
    intent = vdp.VisDependentProperty(default='TARGET')

    # docstring and type hints: supplements hsd_applycal
    def __init__(self,
                 context: Context,
                 output_dir: str | None = None,
                 vis: str | list[str] | None = None,
                 field: str | list[str] | None = None,
                 spw: str | list[str] | None = None,
                 antenna: str | list[str] | None = None,
                 intent: str | list[str] | None = None,
                 parang: bool | None = None,
                 applymode: str | None = None,
                 flagbackup: bool | None = None,
                 flagsum: bool | None = None,
                 flagdetailedsum: bool | None = None,
                 parallel: bool | str | None = None):
        """Inputs for SDApplycal task.

        Args:
            context: Pipeline context object containing state information.

            output_dir: Output directory.

            vis: The list of input MeasurementSets. Defaults to the list of MeasurementSets in the pipeline context.

                Example: ['X227.ms']

            field: A string containing the list of field names or field ids to which the calibration will be applied.
                Defaults to all fields in the pipeline context.

                Example: '3C279', '3C279, M82'

            spw: The list of spectral windows and channels to which the calibration will be applied.
                Defaults to all science windows in the pipeline context.

                Example: '17', '11, 15'

            antenna: The selection of antennas to which the calibration will be applied.
                Defaults to all antennas. Not currently supported.

            intent: A string containing the list of intents against which the selected fields will be matched.
                Defaults to all supported intents in the pipeline context.

                Example: `'*TARGET*'`

            parang: Apply parallactic angle correction. Not used.

            applymode: Calibration apply mode.

                - 'calflag': calibrate data and apply flags from solutions.
                - 'calflagstrict': same as above except flag spws for which calibration is
                  unavailable in one or more tables (instead of allowing them to pass
                  uncalibrated and unflagged). This is the default applymode.
                - 'trial': report on flags from solutions, dataset entirely unchanged.
                - 'flagonly': apply flags from solutions only, data not calibrated.
                - 'flagonlystrict': same as above except flag spws for which calibration is
                  unavailable in one or more tables.
                - 'calonly': calibrate data only, flags from solutions NOT applied.

            flagbackup: Backup the flags before the apply.

                Default: None (equivalent to True)

            flagsum: Run flagdata task for flagging summary.

                Default: None (equivalent to True)

            flagdetailedsum: Generate detailed flagging summary.

                Default: None (equivalent to False)

            parallel: Execute using CASA HPC functionality, if available.
                Default is None, which is equivalent to 'automatic' that intends to
                turn on parallel processing if possible.

                Options: 'automatic', 'true', 'false', True, False
        """
        super().__init__(
            context, output_dir=output_dir, vis=vis,
            field=field, spw=spw, antenna=antenna, intent=intent,
            parang=parang, applymode=applymode, flagbackup=flagbackup,
            flagsum=flagsum, flagdetailedsum=flagdetailedsum,
            parallel=parallel
        )


class SDApplycalResults(ApplycalResults):
    """
    ApplycalResults generated by SDApplycal task.
    Please see parent task's docstring for detail.
    """
    def __init__(self,
                 applied: list[CalApplication] | None = None,
                 data_type: DataType | None = None):
        """Construct SDApplycalResults instance.
        Please see parent task's docstring for detail.

        Args:
            applied: caltables applied by this task.
            data_type: data type enum.
        """
        super().__init__(applied, data_type=data_type)
        self.xy_deviation_score = []
        self.xy_deviation_plots = []


class SerialSDApplycal(SerialApplycal):
    """
    Applycal executes CASA applycal tasks for the current context state,
    applying calibrations registered with the pipeline context to the target
    measurement set.

    Applying the results from this task to the context marks the referred
    tables as applied. As a result, they will not be included in future
    on-the-fly calibration arguments.
    """
    Inputs = SDApplycalInputs

    def modify_task_args(self, task_args: dict) -> dict:
        """Override template arguments for applycal execution.

        This method receives template task_args created by the parent task,
        and override it with our SD-specific antenna selection arguments.

        Args:
            task_args: Template arguments for applycal execution.

        Returns:
            Updated task arguments.
        """
        task_args['antenna'] = '*&&&'
        return task_args

    def _get_flagsum_arg(self, args: dict) -> dict:
        """Update arguments for flag summary.

        According to the requirement in CAS-8813, flag fraction should be
        based on target instead of total.

        Args:
            args: Template arguments for flag summary.

        Returns:
            Updated task arguments.
        """
        task_args = super()._get_flagsum_arg(args)
        task_args['intent'] = 'OBSERVE_TARGET#ON_SOURCE'
        return task_args

    def _tweak_flagkwargs(self, template: list[str]) -> list[str]:
        """Override flagging commands.

        According to the requirement in CAS-8813, flag fraction should be
        based on target instead of total.

        Args:
            template: List of flagging commands.

        Returns:
            Updated flagging commands.
        """
        # use of ' rather than " is required to prevent escaping of flagcmds
        return [row + " intent='OBSERVE_TARGET#ON_SOURCE'" for row in template]

    def prepare(self):
        # execute Applycal
        results = super().prepare()

        # Update Tsys in datatable
        context = self.inputs.context

        # this task uses _handle_multiple_vis framework
        msobj = self.inputs.ms
        origin_basename = os.path.basename(msobj.origin_ms)
        datatable_name = os.path.join(context.observing_run.ms_datatable_name, origin_basename)
        datatable = DataTable()
        datatable.importdata(name=datatable_name, readonly=False)
        datatable._update_flag(msobj.name)
        for calapp in results.applied:
            filename = os.path.join(context.output_dir, calapp.vis)
            fieldids = [fieldobj.id for fieldobj in msobj.get_fields(calapp.field)]
            for _calfrom in calapp.calfrom:
                if _calfrom.caltype == 'tsys':
                    LOG.info('Updating Tsys for {0}'.format(os.path.join(calapp.vis)))
                    tsystable = _calfrom.gaintable
                    spwmap = _calfrom.spwmap
                    gainfield = _calfrom.gainfield
                    datatable._update_tsys(context, filename, tsystable, spwmap, fieldids, gainfield)

        # here, full export is necessary
        datatable.exportdata(minimal=False)

        sdresults = SDApplycalResults(applied=results.applied, data_type=self.applied_data_type)
        sdresults.summaries = results.summaries
        if hasattr(results, 'flagsummary'):
            sdresults.flagsummary = results.flagsummary

        # set unit according to applied calibration
        set_unit(msobj, results.applied)
        return sdresults

    def analyse(self, results: SDApplycalResults) -> SDApplycalResults:
        """Analyse the results of the task.

        This method assesses the quality of the calibration applied in
        this stage. The analysis focuses on the deviation of calibrated
        data between XX and YY polarizations, and also the generation of
        calibrated amplitude vs time plots.

        Returns:
            SDApplycalResults: The results of the task.
        """
        results = super().analyse(results)
        context = self.inputs.context
        msobj = self.inputs.ms

        # perform XX-YY deviation QA
        ms_name = self.inputs.ms.name
        if self.inputs.ms.antenna_array.name == 'ALMA':
            applycal_qa_dir = './sd_applycal_output'
            os.makedirs(applycal_qa_dir, exist_ok=True)

            stage_dir = os.path.join(
                self.inputs.context.report_dir,
                f'stage{self.inputs.context.task_counter}'
            )
            if basetask.DISABLE_WEBLOG:
                # Since weblog is disabled, all the plots will be saved
                # in applycal_qa_dir
                weblog_output_dir = applycal_qa_dir
            else:
                os.makedirs(stage_dir, exist_ok=True)
                weblog_output_dir = stage_dir

            qa_result = sd_applycal_qa.get_ms_applycal_qascores(
                msNames=[ms_name],
                plot_output_path=applycal_qa_dir,
                weblog_output_path=weblog_output_dir,
            )
            qascore_list, plots_fnames, qascore_per_scan_list = qa_result
            sd_qa_reports.makeSummaryTable(
                qascore_list,
                '',
                plfolder=applycal_qa_dir,
                output_file=os.path.join(applycal_qa_dir, f'qascore_summary_{self.inputs.ms.basename}.csv')
            )
            sd_qa_reports.makeQAmsgTable(
                qascore_list,
                plfolder=applycal_qa_dir,
                output_file=os.path.join(applycal_qa_dir, f'qascores_details_{self.inputs.ms.basename}.csv')
            )
            valid_plots_fnames = [x for x in plots_fnames if x != "N/A"]
            results.xy_deviation_score.extend(qascore_list)
            results.xy_deviation_plots.extend(valid_plots_fnames)

        # Generating calibrated amplitude vs time plots
        results.amp_vs_time_summary_plots = None
        results.amp_vs_time_detail_plots = None
        if not basetask.DISABLE_WEBLOG:
            # mkdir stage_dir if it doesn't exist
            stage_dir = os.path.join(context.report_dir, 'stage%s' % context.task_counter)
            os.makedirs(stage_dir, exist_ok=True)

            fields = [x.name for x in msobj.get_fields(intent='TARGET')]
            if len(fields) > 0:
                # For summary plots
                amp_vs_time_summary_plots = self.sd_plots_for_result(
                    context,
                    results,
                    display.ApplyCalSingleDishPlotmsSpwComposite
                )

                # For detail plots
                amp_vs_time_detail_plots = self.sd_plots_for_result(
                    context,
                    results,
                    display.ApplyCalSingleDishPlotmsAntSpwComposite
                )
                results.amp_vs_time_summary_plots = amp_vs_time_summary_plots
                results.amp_vs_time_detail_plots = amp_vs_time_detail_plots

        return results

    def sd_plots_for_result(self, context: Context, results: SDApplycalResults, plotter_cls: ApplyCalSingleDishPlotmsSpwComposite | ApplyCalSingleDishPlotmsAntSpwComposite, **kwargs) -> list[logger.Plot]:
        """Generate amplitude vs. time plots from results instance.

        Args:
            context: Pipeline context object containing state information.
            results: Results instance.
            plotter_cls: Plotter class to generate plot objects of amplitude vs. time.

        Returns:
            plots: List of plot objects of amplitude vs. time.
        """
        xaxis = 'time'
        yaxis = 'real'
        msobj = context.observing_run.get_ms(self.inputs.vis)
        plotter = plotter_cls(context, results, msobj, xaxis, yaxis, **kwargs)
        plots = plotter.plot()

        return plots


def set_unit(ms: MeasurementSet, calapp: list[CalApplication]):
    """Set unit to MS data column according to applied calibrations.

    Args:
        ms: MeasurementSet domain object.
        calapp: List of CalApplication objects.
    """
    target_fields = ms.get_fields(intent='TARGET')
    data_units = dict((f.id, '') for f in target_fields)
    for a in calapp:
        calto = a.calto
        field_name = calto.field
        if len(field_name) == 0:
            field = ms.get_fields(intent='TARGET')
        else:
            field = [f for f in ms.get_fields(name=field_name) if 'TARGET' in f.intents]
        if len(field) == 0:
            continue

        assert len(field) == 1
        field_id = field[0].id
        caltypes = [cf.caltype for cf in a.calfrom]
        if ('ps' in caltypes) and ('tsys' in caltypes):
            data_units[field_id] = 'K'
        else:
            LOG.warning('Calibration of {} (field {}) is not correct. Missing pscal and/or tsyscal.'.format(ms.basename, field_name))
        if 'amp' in caltypes or 'gaincal' in caltypes:
            if data_units[field_id] == 'K':
                data_units[field_id] = 'Jy'

    unit_list = numpy.asarray(list(data_units.values()))
    if numpy.all(unit_list == 'K'):
        data_unit = 'K'
    elif numpy.all(unit_list == 'Jy'):
        data_unit = 'Jy'
    elif numpy.any(unit_list == 'Jy'):
        LOG.warning(
            'Calibration of {} is not correct. Some of calibrations (pscal, tsyscal, ampcal) are missing.'.fomrat(ms.basename))
        data_unit = ''
    else:
        data_unit = ''

    if data_unit != '':
        with casa_tools.TableReader(ms.name, nomodify=False) as tb:
            colnames = tb.colnames()
            target_columns = set(colnames) & set(['DATA', 'FLOAT_DATA', 'CORRECTED_DATA'])
            for col in target_columns:
                tb.putcolkeyword(col, 'UNIT', data_unit)


# Tier-0 parallelization
@task_registry.set_equivalent_casa_task('hsd_applycal')
@task_registry.set_casa_commands_comment('Calibrations are applied to the data. Final flagging summaries are computed')
class SDApplycal(sessionutils.ParallelTemplate):
    Inputs = SDApplycalInputs
    Task = SerialSDApplycal
