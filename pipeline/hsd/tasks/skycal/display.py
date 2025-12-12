"""Display module for skycal task."""
from __future__ import annotations

import glob
import os
from matplotlib.figure import Figure
from matplotlib.ticker import NullFormatter
import numpy as np
import traceback

import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.renderer.logger as logger
from pipeline.h.tasks.common.displays import common as common
from pipeline.h.tasks.common.displays import bandpass as bandpass
from ..common import display as sd_display
from pipeline.infrastructure import casa_tasks
from pipeline.infrastructure import casa_tools
from pipeline.infrastructure.displays.plotstyle import casa5style_plot
from typing import TYPE_CHECKING, Any, NoReturn

if TYPE_CHECKING:
    from collections.abc import Sequence
    from matplotlib.axes import Axes
    from pipeline.domain import Field, MeasurementSet, Scan
    from pipeline.hsd.tasks.skycal.skycal import SDSkyCalResults
    from pipeline.infrastructure.callibrary import CalApplication
    from pipeline.infrastructure.launcher import Context
    from pipeline.infrastructure.jobrequest import JobRequest


LOG = logging.get_logger(__name__)


def get_field_from_ms(ms: MeasurementSet, field: str) -> list[Field]:
    """Return list of fields that matches field selection.

    Matching with field id takes priority over
    the matching with field name.

    Args:
        ms: MeasurementSet domain object
        field: Field selection string

    Returns:
        List of field domain objects
    """
    field_list = []
    if field.isdigit():
        # regard field as FIELD_ID
        field_list = ms.get_fields(field_id=int(field))

    if len(field_list) == 0:
        # regard field as FIELD_NAME
        field_list = ms.get_fields(name=field)

    return field_list


class SingleDishSkyCalDisplayBase(object):
    """Base display class for skycal stage."""

    def init_with_field(self, context: Context, result: SDSkyCalResults, field: str) -> None:
        """Initialize attributes using field information.

        Args:
            context: Pipeline context
            result: SDSkyCalResults instance
            field: Field string. Either field id or field name.
                   Matching with field id takes priority over
                   the matching with field name.

        Raises:
            RuntimeError: Invalid field selection
        """
        vis = self._vis
        ms = context.observing_run.get_ms(vis)
        fields = get_field_from_ms(ms, field)
        if len(fields) == 0:
            # failed to find field domain object with field
            raise RuntimeError(f'No match found for field "{field}".')

        self.field_id = fields[0].id
        self.field_name = fields[0].clean_name

        LOG.debug('field: ID %s Name \'%s\'' % (self.field_id, self.field_name))
        old_prefix = self._figroot.replace('.png', '')
        self._figroot = self._figroot.replace('.png', '-%s.png' % (self.field_name))
        new_prefix = self._figroot.replace('.png', '')

        self._update_figfile(old_prefix, new_prefix)

        if 'field' not in self._kwargs:
            self._kwargs['field'] = self.field_id

    def add_field_identifier(self, plots: list[logger.Plot]) -> None:
        """Add field identifier.

        Args:
            plots: List of plot object.
        """
        for plot in plots:
            if 'field' not in plot.parameters:
                plot.parameters['field'] = self.field_name

    def _update_figfile(self) -> NoReturn:
        """Update the name of figure file.

        Raise:
             NotImplementedError
        """
        raise NotImplementedError()


class SingleDishSkyCalAmpVsFreqSummaryChart(common.PlotbandpassDetailBase, SingleDishSkyCalDisplayBase):
    """Class for plotting Amplitude vs. Frequency summary chart.

    The summary charts are displayed in the main page of hsd_skycal in the weblog.
    The chart is plotted for each Measurement Set, Field and Spectral Window.
    """

    def __init__(self, context: Context, result: SDSkyCalResults, field: str) -> None:
        """Initialize the class.

        Args:
            context: Pipeline context
            result: SDSkyCalResults instance
            field: Field string. Either field id or field name.
        """
        super(SingleDishSkyCalAmpVsFreqSummaryChart, self).__init__(context, result,
                                                                    'freq', 'amp',
                                                                    showatm=True,
                                                                    overlay='antenna',
                                                                    solutionTimeThresholdSeconds=3600.)

        self.context = context
        # self._figfile structure: {spw_id: {antenna_id: filename}}
        self.spw_ids = list(self._figfile.keys())
        # take any value from the dictionary
        self._figfile = dict((spw_id, list(self._figfile[spw_id].values())[0]) for spw_id in self.spw_ids)
        self.init_with_field(context, result, field)

    def plot(self) -> list[logger.Plot]:
        """Plot the Amplitude vs. Frequency summary chart.

        Return:
            List of plot object.
        """
        commands = {}
        missing = [spw_id
                   for spw_id in self.spw_ids
                   if not os.path.exists(self._figfile[spw_id])]
        if missing:
            LOG.trace('Executing new plotbandpass job for missing figures')
            for spw_id in missing:
                # PIPE-110: show image sideband for DSB receivers.
                showimage = self._rxmap.get(spw_id, "") == "DSB"
                try:
                    task = self.create_task(spw_id, '', showimage=showimage)
                    commands[spw_id] = str(task)
                    task.execute()
                except Exception as ex:
                    LOG.error('Could not create plotbandpass summary plots')
                    LOG.exception(ex)

        # workaround for CAS-13863
        # So far, missing plots issue happens only for TP Spectral Scan data
        missing = [spw_id
                   for spw_id in self.spw_ids
                   if not os.path.exists(self._figfile[spw_id])]
        if missing:
            LOG.info('Executing plotbandpass again for missing figures')
            for spw_id in missing:
                # PIPE-110: show image sideband for DSB receivers.
                showimage = self._rxmap.get(spw_id, "") == "DSB"
                try:
                    task = self.create_task_for_tp_spectral_scan(spw_id, '', showimage=showimage)
                    commands[spw_id] = str(task)
                    task.execute()
                    self.rename_and_clear_figure(spw_id)
                except Exception as ex:
                    LOG.error('Could not create plotbandpass summary plots')
                    LOG.exception(ex)

        wrappers = []
        for spw_id, figfile in self._figfile.items():
            # PIPE-110: show image sideband for DSB receivers.
            showimage = self._rxmap.get(spw_id, "") == "DSB"
            if os.path.exists(figfile):
                task = self.create_task(spw_id, '', showimage=showimage)
                command = commands.get(spw_id, str(task))
                wrapper = logger.Plot(figfile,
                                      x_axis=self._xaxis,
                                      y_axis=self._yaxis,
                                      parameters={'vis': self._vis_basename,
                                                  'spw': spw_id,
                                                  'field': self.field_name},
                                      command=command)
                wrappers.append(wrapper)
            else:
                LOG.trace('No plotbandpass summary plot found for spw '
                          '%s' % spw_id)

        return wrappers

    def _update_figfile(self, old_prefix: str, new_prefix: str) -> None:
        """Update the name of figure file.

        Args:
            old_prefix: Prefix before updating the name of figure file.
            new_prefix: Prefix after updating the name of figure file.
        """
        for spw_id, figfile in self._figfile.items():
            self._figfile[spw_id] = figfile.replace(old_prefix, new_prefix)
            spw_indicator = 'spw{}'.format(spw_id)
            pieces = self._figfile[spw_id].split('.')
            try:
                spw_index = pieces.index(spw_indicator)
            except:
                spw_index = -3
            # remove antenna name from the filename
            pieces.pop(spw_index - 1)
            self._figfile[spw_id] = '.'.join(pieces)

    def create_task_for_tp_spectral_scan(self, spw_arg: int, antenna_arg: str,
                                         showimage: bool = False) -> JobRequest:
        """
        Return plotbandpass task job with a tweaked parameter value.

        A job of plotbandpass is created with
            solutionTimeThresholdSeconds = a half of exposure time of a scan.

        Args:
            spw_arg: spw ID
            antenna_arg: antenna selection string
            showimage: If True, show the atmospheric curve for the image
                sideband, too.
        Returns:
            A job of plotbandpass task.
        """
        kwargs_org = self._kwargs.copy()
        try:
            ms = self.context.observing_run.get_ms(self._vis)
            def __get_sorted_reference_scans(msobj: MeasurementSet,
                                             spw: int | str | Sequence | None = None) -> list[Scan]:
                """
                Return a list of REFERENCE Scan objects sorted by scan IDs.
                Args:
                    msobj: MeasuremetSet object
                    spw: Spw selection
                Returns: a list of REFERENCE scan objects sorted by scan ID.
                """
                scans = msobj.get_scans(scan_intent='REFERENCE', spw=spw)
                return sorted(scans, key=lambda s: s.id)

            # The solutionTimeThresholdSeconds should be equal to or smaller than
            # the time gap between the previous reference scan and a selected scan.
            myqa = casa_tools.quanta
            scans_all = __get_sorted_reference_scans(ms)
            # The first scan of the selected spw
            scan_spw = __get_sorted_reference_scans(ms, spw=spw_arg)[0]
            idx_scan_spw = [s.id for s in scans_all].index(scan_spw.id)
            if idx_scan_spw > 0:
                start_time_scan_spw = myqa.convert(scan_spw.start_time['m0'], 's')['value']
                end_time_previous_scan = myqa.convert(scans_all[idx_scan_spw - 1].end_time['m0'], 's')['value']
                self._kwargs['solutionTimeThresholdSeconds'] = start_time_scan_spw - end_time_previous_scan
            else:  # I don't think this should happen but defining a reasonable value to avoid failure.
                self._kwargs['solutionTimeThresholdSeconds'] = scan_spw.exposure_time(spw_arg).seconds / 2
            self._kwargs['scans'] = scan_spw.id
            task = super().create_task(spw_arg, antenna_arg, showimage)
        finally:
            self._kwargs = kwargs_org
        return task

    def rename_and_clear_figure(self, spw_id: int) -> None:
        """
        Select one figure per spw and rename the figure.

        Args:
            spw_id: Spw ID
        """
        figfile = self._figfile[spw_id]
        if os.path.exists(figfile):
            return

        prefix, extension = os.path.splitext(self._figroot)
        pattern = f'{prefix}.spw{spw_id}.t*{extension}'
        figures = sorted(glob.glob(pattern))
        if len(figures) == 0:
            return
        os.rename(figures[0], figfile)
        for fig in figures[1:]:
            os.remove(fig)


class SingleDishSkyCalAmpVsFreqDetailChart(bandpass.BandpassDetailChart, SingleDishSkyCalDisplayBase):
    """Class for plotting Amplitude vs. Frequency detail chart.

    The detail charts are displayed in the sub page (sky_level_vs_frequency.html) of hsd_skycal
    in the weblog.
    The chart is plotted for each Measurement Set, Antenna, Field and Spectral Window.
    """

    @staticmethod
    def get_caltable_from_result(result: SDSkyCalResults) -> str:
        """Extract caltable name from the results object.

        This method assumes result.final contains only one CalApplication
        object. Results with multiple CalApplication objects is not supported.
        Empty result will cause an error, too.

        Args:
            result: Results object generated by hsd_skycal

        Returns:
            Name of the caltable
        """
        assert len(result.final) == 1
        calapp = result.final[0]
        caltable = calapp.gaintable.rstrip('/')
        return caltable

    @staticmethod
    def get_solution_interval(caltable: str) -> float | None:
        """Compute appropriate solution interval for caltable.

        The value should be given to solutionTimeThresholdSeconds
        parameter when calling plotbandpass.

        Returned value is usually a minimum interval which is
        stored in the INTERVAL column. In case if minimum time
        difference, which is a difference of time stamp taken
        from the TIME column, is shorter than minimum interval,
        returned value will be based on the time difference
        rather than interval.

        Args:
            caltable: Name of the caltable

        Returns:
            Solution interval in seconds. Return value will be None
            if no valid caltable rows exist.
        """
        with casa_tools.TableReader(caltable) as tb:
            unique_timestamps_per_antenna = []
            antennas = np.unique(tb.getcol('ANTENNA1'))
            valid_rows = tb.query('not all(FLAG)')
            intervalcol = valid_rows.getcol('INTERVAL')
            timecol = valid_rows.getcol('TIME')
            antenna1col = valid_rows.getcol('ANTENNA1')
            for a in antennas:
                unique_timestamps_per_antenna.append(
                    np.unique(timecol[antenna1col == a])
                )
            valid_rows.close()

        if len(intervalcol) == 0:
            # return None if no valid caltable rows exist
            return None

        max_interval = int(np.ceil(intervalcol.max()))

        # check if number of unique timestamps is less than 2
        if np.any([len(x) < 2 for x in unique_timestamps_per_antenna]):
            # if True, skip evaluating min_time_diff since
            # time difference cannot be calculated
            min_time_diff = None
        else:
            # if False, evaluate min_time_diff as a minimum
            # time difference between adjacent timestamps
            min_time_diff_per_antenna = map(
                lambda x: np.diff(x).min(),
                unique_timestamps_per_antenna
            )
            min_time_diff = int(np.floor(min(min_time_diff_per_antenna)))

        LOG.info(f'max_interval is {max_interval}, min_time_diff is {min_time_diff}')

        if min_time_diff is None or max_interval < min_time_diff:
            solution_interval = max_interval
        else:
            # The solution_interval should be shorter than min_time_diff.
            # Multiply by 0.5 to show this relation explicitly.
            # You can change numerical factor (0.5) if you want, but
            # keep in mind that the factor should be positive and should
            # not exceed 1.0.
            solution_interval = min_time_diff * 0.5

        LOG.info(f'caltable "{os.path.basename(caltable)}": '
                 f'solution interval is {solution_interval} sec.')

        return solution_interval

    def __init__(self, context: Context, result: SDSkyCalResults, field: str) -> None:
        """Initialize the class.

        Args:
            context: Pipeline context object containing state information.
            result: Pipeline task execution result.
            field: Field string. Either field id or field name.
        """
        caltable = self.get_caltable_from_result(result)
        solution_interval = self.get_solution_interval(caltable)
        extra_options = {}
        if solution_interval is not None:
            extra_options['solutionTimeThresholdSeconds'] = solution_interval

        super(SingleDishSkyCalAmpVsFreqDetailChart, self).__init__(
            context, result, xaxis='freq', yaxis='amp',
            showatm=True, overlay='time',
            **extra_options)

        self.init_with_field(context, result, field)

    def plot(self) -> list[logger.Plot]:
        """Create Amplitude vs. Frequency detail plot.

        Return:
            List of plot object.
        """
        wrappers = super(SingleDishSkyCalAmpVsFreqDetailChart, self).plot()

        self.add_field_identifier(wrappers)

        return wrappers

    def _update_figfile(self, old_prefix: str, new_prefix: str) -> None:
        """Update the name of figure file.

        Args:
            old_prefix: Prefix before updating the name of figure file.
            new_prefix: Prefix after updating the name of figure file.
        """
        for spw_id in self._figfile:
            for antenna_id, figfile in self._figfile[spw_id].items():
                new_figfile = figfile.replace(old_prefix, new_prefix)
                self._figfile[spw_id][antenna_id] = new_figfile


class SingleDishPlotmsLeaf(object):
    """Class to execute plotms and return a plot wrapper.

    Task arguments for plotms are customized for single dish usecase.
    """

    def __init__(
        self,
        context: Context,
        result: SDSkyCalResults,
        calapp: CalApplication,
        xaxis: str,
        yaxis: str,
        spw: str = '',
        ant: str = '',
        coloraxis: str = '',
        plotindex: int = 0,
        flush_plot: bool = False,
        **kwargs: Any
    ) -> None:
        """Construct SingleDishPlotmsLeaf instance.

        The constructor has an API that accepts additional parameters
        to customize plotms but currently those parameters are ignored.

        Args:
            context: Pipeline context object containing state information.
            result: SDSkyCalResults instance.
            calapp: CalApplication instance.
            xaxis: The content of X-axis of the plot.
            yaxis: The content of Y-axis of the plot.
            spw: Spectral window selection. Defaults to '' (all spw).
            ant: Antenna selection. Defaults to '' (all antenna).
            coloraxis: Color axis type. Defaults to ''.
            plotindex: Index of plot to show the field (actually calapp).
            flush_plot: Flag to flush plot.
        Raises:
            RuntimeError: Invalid field selection in calapp
        """
        LOG.debug('__init__(caltable={caltable}, spw={spw}, ant={ant})'.format(caltable=calapp.gaintable, spw=spw,
                                                                               ant=ant))
        self.xaxis = xaxis
        self.yaxis = yaxis
        self.caltable = calapp.gaintable
        self.vis = calapp.vis
        self.spw = str(spw)
        self.antenna = str(ant)
        self.coloraxis = coloraxis
        self.plotindex = plotindex
        self.flush_plot = flush_plot
        self.field = calapp.gainfield

        ms = context.observing_run.get_ms(self.vis)
        fields = get_field_from_ms(ms, self.field)
        if len(fields) == 0:
            # failed to find field domain object with field
            raise RuntimeError(f'No match found for field "{self.field}".')

        self.antmap = dict((a.id, a.name) for a in ms.antennas)
        if len(self.antenna) == 0:
            self.antenna_selection = 'all'
        else:
            self.antenna_selection = list(self.antmap.values())[int(self.antenna)]
        LOG.info('antenna: ID %s Name \'%s\'' % (self.antenna, self.antenna_selection))

        self._figroot = os.path.join(context.report_dir,
                                     'stage%s' % result.stage_number)

    def plot(self) -> list[logger.Plot]:
        """Generate a sky calibration plot.

        Return:
            List of plot object.
        """
        prefix = '{ms}-{y}_vs_{x}-{ant}-spw{spw}'.format(
            ms=os.path.basename(self.vis), y=self.yaxis, x=self.xaxis,
            ant=self.antenna_selection, spw=self.spw)

        title = 'Sky level vs time\nAntenna {ant} Spw {spw} \ncoloraxis={coloraxis}'.format(
            ant=self.antenna_selection, spw=self.spw, coloraxis=self.coloraxis)
        figfile = os.path.join(self._figroot, '{prefix}.png'.format(prefix=prefix))
        task = self._create_task(title, figfile)

        if os.path.exists(figfile):
            LOG.debug('Returning existing plot')
        else:
            try:
                task.execute()
            except Exception as e:
                LOG.error(str(e))
                LOG.debug(traceback.format_exc())
                if self.flush_plot:
                    LOG.error('Failed to generate plot "{}"'.format(figfile))
                else:
                    LOG.error('Failed to generate plot for field "{}"'.format(self.field))
                return []

        if self.flush_plot:
            return [self._get_plot_object(figfile, task)]
        else:
            return []

    def _create_task(self, title: str, figfile: str) -> JobRequest:
        """Create task of CASA plotms.

        Args:
            title: Title of figure
            figfile: Name of figure file
        Return:
            Instance of JobRequest.
        """
        clearplots = True if self.plotindex == 0 else False
        if not self.flush_plot:
            figfile = ""
        task_args = {'vis': self.caltable,
                     'xaxis': self.xaxis,
                     'yaxis': self.yaxis,
                     'coloraxis': self.coloraxis,
                     'showgui': False,
                     'spw': self.spw,
                     'antenna': self.antenna,
                     'title': title,
                     'showlegend': True,
                     'legendposition': 'exteriorRight',
                     'averagedata': True,
                     'avgchannel': '1e8',
                     'plotindex': self.plotindex,
                     'clearplots': clearplots,
                     'plotfile': figfile
                     }

        return casa_tasks.plotms(**task_args)

    def _get_plot_object(self, figfile: str, task: JobRequest) -> logger.Plot:
        """Generate parameters and return logger.Plot.

        Args:
            figfile: Name of figure file.
            task: JobRequest object.

        Return:
            logger.Plot
        """
        parameters = {'vis': os.path.basename(self.vis),
                      'ant': self.antenna_selection,
                      'spw': self.spw}

        return logger.Plot(figfile,
                           x_axis='Time',
                           y_axis='Amplitude',
                           parameters=parameters,
                           command=str(task))


class SingleDishPlotmsSpwComposite(common.LeafComposite):
    """
    Create a PlotLeaf for each spw in the caltable or caltables.
    """
    # reference to the PlotLeaf class to call
    leaf_class = SingleDishPlotmsLeaf

    def __init__(self, context, result, calapp: list[CalApplication],
                 xaxis, yaxis, ant='', pol='', **kwargs):

        # Create a dictionary to keep track of which caltable has which spws.
        dict_calapp_spws = self._create_calapp_contents_dict(calapp, 'SPECTRAL_WINDOW_ID')
        table_spws = sorted(dict_calapp_spws.keys())
        children = []
        for spw in table_spws:
            children_field = []
            for plotindex, cal in enumerate(calapp):
                final_field = plotindex == len(calapp)-1
                item = self.leaf_class(context, result, cal, xaxis, yaxis, spw=int(spw), ant=ant, pol=pol, plotindex=plotindex, flush_plot=final_field, **kwargs)
                children_field.append(item)
            children.extend(children_field)

        super().__init__(children)


class SingleDishPlotmsAntSpwComposite(common.LeafComposite):
    """Class to create a PlotLeaf for each antenna and spw."""

    leaf_class = SingleDishPlotmsSpwComposite

    def __init__(self, context, result, calapp: list[CalApplication], xaxis, yaxis, pol='', **kwargs):

        dict_calapp_ants = self._create_calapp_contents_dict(calapp, 'ANTENNA1')
        table_ants = sorted(dict_calapp_ants.keys())

        children = [self.leaf_class(context, result, dict_calapp_ants[ant], xaxis, yaxis,
                    ant=int(ant), pol=pol, **kwargs)
                    for ant in table_ants]
        super(SingleDishPlotmsAntSpwComposite, self).__init__(children)


class SingleDishPlotmsAntComposite(common.AntComposite):
    """Class to create a PlotLeaf for each antenna."""

    leaf_class = SingleDishPlotmsLeaf


class SingleDishSkyCalAmpVsTimeSummaryChart(SingleDishPlotmsSpwComposite):
    """Class for plotting Amplitude vs. Time summary chart.

    The summary charts are displayed in the main page of hsd_skycal in the weblog.
    The chart is plotted for each Measurement Set, Field and Spectral Window.
    """

    def __init__(self, context: Context, result: SDSkyCalResults, calapp: list[CalApplication]) -> None:
        """Initialize the class.

        Args:
            context: Pipeline context object containing state information.
            result: SDSkyCalResults instance.
            calapp: List of CalApplication instances.
        """
        super(SingleDishSkyCalAmpVsTimeSummaryChart, self).__init__(context, result, calapp,
                                                                    xaxis='time', yaxis='amp',
                                                                    coloraxis='field')


class SingleDishSkyCalAmpVsTimeDetailChart(SingleDishPlotmsAntSpwComposite):
    """Class for plotting Amplitude vs. Time detail chart.

    The detail charts are displayed in the sub page (sky_level_vs_time.html) of hsd_skycal
    in the weblog.
    The chart is plotted for each Measurement Set, Antenna, Field and Spectral Window.
    """

    def __init__(self, context: Context, result: SDSkyCalResults, calapp: list[CalApplication]) -> None:
        """Initialize the class.

        Args:
            context: Pipeline context object containing state information.
            result: SDSkyCalResults instance.
            calapp: List of CalApplication instances.
        """
        super(SingleDishSkyCalAmpVsTimeDetailChart, self).__init__(context, result, calapp,
                                                                   xaxis='time', yaxis='amp',
                                                                   coloraxis='field')


@casa5style_plot
def plot_elevation_difference(
        context: Context,
        result: SDSkyCalResults,
        eldiff: dict[str, np.ndarray],
        threshold: float = 3.0
        ) -> list[logger.Plot]:
    """Generate plot of elevation difference.

    Args:
        context: Pipeline context object containing state information.
        result: SDSkyCalResults instance.
        eldiff: -- dictionary whose value is ElevationDifference named tuple instance that holds
                      'timeon': timestamp for ON-SOURCE pointings
                      'elon': ON-SOURCE elevation
                      'flagon': flag for ON-SOURCE pointings (True if flagged, False otherwise)
                      'timecal': timestamp for OFF-SOURCE pointings
                      'elcal': OFF-SOURCE elevation
                      'time0': timestamp for preceding OFF-SOURCE pointings
                      'eldiff0': elevation difference between ON-SOURCE and preceding OFF-SOURCE
                      'time1': timestamp for subsequent OFF-SOURCE pointings
                      'eldiff1': elevation difference between ON-SOURCE and subsequent OFF-SOURCE
                eldiff is a nested dictionary whose first key is FIELD_ID for target, the second one
                is ANTENNA_ID, and the third one is SPW_ID.
        threhshold -- Elevation threshold for QA (default 3deg)
    Return:
        List of plot object.
    """
    calapp = result.final[0]
    vis = calapp.calto.vis
    ms = context.observing_run.get_ms(vis)

    figroot = os.path.join(context.report_dir,
                           'stage%s' % result.stage_number)

    start_time = np.min([np.min(x.timeon) for z in eldiff.values() for y in z.values()
                            for x in y.values() if len(x.timeon) > 0])
    end_time = np.max([np.max(x.timeon) for z in eldiff.values() for y in z.values()
                          for x in y.values() if len(x.timeon) > 0])

    def init_figure(figure: Figure) -> tuple[Axes, Axes]:
        """Initialize the figure.

        Args:
            figure_id: ID of figure.
        Return:
            Tuple (a0, a1); both a0 and a1 are Axes instance of plot.
        """
        figure.clear()
        a0 = figure.add_axes((0.125, 0.51, 0.775, 0.39))
        a0.xaxis.set_major_locator(sd_display.utc_locator(start_time=start_time, end_time=end_time))
        a0.xaxis.set_major_formatter(NullFormatter())
        a0.tick_params(axis='both', labelsize=10)
        a0.set_ylabel('Elevation [deg]', fontsize=10)

        a1 = figure.add_axes((0.125, 0.11, 0.775, 0.39))
        a1.xaxis.set_major_locator(sd_display.utc_locator(start_time=start_time, end_time=end_time))
        a1.xaxis.set_major_formatter(sd_display.utc_formatter())
        a1.tick_params(axis='both', labelsize=10)
        a1.set_ylabel('Elevation Difference [deg]', fontsize=10)
        a1.set_xlabel('UTC', fontsize=10)
        return a0, a1

    def finalize_figure(figure: Figure, vis: str, field_name: str, antenna_name: str, xmin: float, xmax: float) -> None:
        """Set axes, label, legend and title for the elevation difference figure.

        Args:
            figure_id: ID of figure.
            vis: Name of Measurement Set.
            field_name: Name of field.
            antenna_name: Name of antenna.
        """
        axes = figure.axes
        assert len(axes) == 2, f"length of axes should be 2, but got {len(axes)}"
        a0 = axes[0]
        a1 = axes[1]
        ymin, ymax = a1.get_ylim()
        dy = ymax - ymin
        a1.set_ylim(0, max(ymax + 0.1 * dy, threshold + 0.1))

        a1.axhline(threshold, color='red')
        dx = xmax - xmin
        xmin_new = xmin - 0.05 * dx
        xmax_new = xmax + 0.05 * dx
        dx_new = xmax_new - xmin_new
        a1.set_xlim(xmin_new, xmax_new)
        x = xmax_new - 0.01 * dx_new
        y = threshold - 0.05
        a1.text(x, y, 'QA threshold', ha='right', va='top', color='red', size='small')

        a0.set_xlim(xmin_new, xmax_new)
        labelon = False
        labeloff = False
        for l in a0.lines:
            if (labelon is False) and (l.get_color() == 'black'):
                l.set_label('ON')
                labelon = True
            if (labeloff is False) and (l.get_color() == 'blue'):
                l.set_label('OFF')
                labeloff = True
            if labelon and labeloff:
                break
        a0.legend(loc='best', numpoints=1, prop={'size': 'small'})
        a0.set_title(
            f'Elevation Difference between ON and OFF\n{vis} Field {field_name} Antenna {antenna_name}',
            fontsize=12
        )

    def generate_plot(figure: Figure, vis: str, field_name: str, antenna_name: str) -> logger.Plot:
        """Generate the file of elevation figure.

        Args:
            figure_id: ID of figure
            vis: Name of Measurement Set
            field_name: Name of field
            antenna_name: Name of antenna
        Return:
            logger.Plot
        """
        vis_prefix = '.'.join(vis.split('.')[:-1])
        figfile = 'elevation_difference_{}_{}_{}.png'.format(vis_prefix, field_name, antenna_name)
        figpath = os.path.join(figroot, figfile)
        figure.savefig(figpath)
        plot = None
        if os.path.exists(figpath):
            parameters = {'intent': 'TARGET',
                          'spw': '',
                          'pol': '',
                          'ant': antenna_name,
                          'vis': vis,
                          'type': 'Elevation Difference vs. Time',
                          'file': vis}
            plot = logger.Plot(figpath,
                               x_axis='Time',
                               y_axis='Elevation Difference',
                               field=field_name,
                               parameters=parameters)
        return plot

    plots = []
    figure0 = Figure()
    figure1 = Figure()
    for field_id, eldiff_field in eldiff.items():
        # figure for summary plot
        a2, a3 = init_figure(figure1)

        field = ms.fields[field_id]
        field_name = field.clean_name

        plots_per_field = []

        global_xmin = None
        global_xmax = None
        for antenna_id, eldant in eldiff_field.items():
            # figure for per-antenna plots
            a0, a1 = init_figure(figure0)

            antenna_name = ms.antennas[antenna_id].name

            xmin, xmax = None, None
            for spw_id, eld in eldant.items():
                if len(eld.timeon) == 0 or len(eld.timecal) == 0:
                    continue

                # Elevation vs. Time
                # PIPE-1752 plot valid data points only
                # mask: True for valid, False otherwise
                mask = np.logical_not(eld.flagon)
                xon = sd_display.mjd_to_plotval(eld.timeon)
                xmin = xon.min()
                global_xmin = xmin if global_xmin is None else min(global_xmin, xmin)
                xmax = xon.max()
                global_xmax = xmax if global_xmax is None else max(global_xmax, xmax)
                xoff = sd_display.mjd_to_plotval(eld.timecal)
                for a in [a0, a2]:
                    a.plot(xon[mask], eld.elon[mask], '.', color='black', mew=0)
                    a.plot(xoff, eld.elcal, '.', color='blue', mew=0)

                # Elevation Difference vs. Time
                time0 = eld.time0
                eldiff0 = eld.eldiff0
                time1 = eld.time1
                eldiff1 = eld.eldiff1
                io0 = np.where(np.abs(eldiff0) < threshold)[0]
                ix0 = np.where(np.abs(eldiff0) >= threshold)[0]
                io1 = np.where(np.abs(eldiff1) < threshold)[0]
                ix1 = np.where(np.abs(eldiff1) >= threshold)[0]
                index_list = [io0, io1, ix0, ix1]
                time_list = [time0, time1, time0, time1]
                eldiff_list = [eldiff0, eldiff1, eldiff0, eldiff1]
                style_list = ['g.', 'g.', 'rs', 'rs']
                for idx, t, ed, ls in zip(index_list, time_list, eldiff_list, style_list):
                    if len(idx) > 0:
                        x = sd_display.mjd_to_plotval(t[idx])
                        y = np.abs(ed[idx])
                        for a in [a1, a3]:
                            a.plot(x, y, ls, mew=0)

            # skip per-antenna plots if there are no data to plot
            if xmin and xmax:
                # finalize figure for per-antenna plot
                finalize_figure(figure0, ms.basename, field_name, antenna_name, xmin, xmax)

                # generate plot object
                plot = generate_plot(figure0, ms.basename, field_name, antenna_name)
                figure0.clear()
                if plot is not None:
                    plots_per_field.append(plot)

        # skip summary if there are no data to plot
        if global_xmin and global_xmax:
            # finalize figure for summary plot
            finalize_figure(figure1, ms.basename, field_name, 'ALL', global_xmin, global_xmax)

            # generate plot object
            plot = generate_plot(figure1, ms.basename, field_name, '')
            figure1.clear()
            if plot is not None:
                plots_per_field.append(plot)

        plots.extend(plots_per_field)

    return plots
