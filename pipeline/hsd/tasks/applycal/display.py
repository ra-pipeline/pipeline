from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.renderer.logger as logger
from pipeline.h.tasks.common.displays import common as common
from pipeline.infrastructure import casa_tasks

if TYPE_CHECKING:
    from pipeline.domain import MeasurementSet
    from pipeline.infrastructure.jobrequest import JobRequest
    from pipeline.infrastructure.launcher import Context
    from pipeline.hsd.tasks.applycal.applycal import SDApplycalResults

LOG = infrastructure.get_logger(__name__)


class ApplyCalSingleDishPlotmsLeaf(object):
    """Class to execute plotms and return a plot wrapper.

    Task arguments for plotms are customized for single dish usecase.
    """

    def __init__(
        self,
        context: Context,
        result: SDApplycalResults,
        ms: MeasurementSet,
        xaxis: str,
        yaxis: str,
        spw: str = '',
        ant: str = '',
        **kwargs: Any
    ) -> None:
        """Construct SingleDishPlotmsLeaf instance.

        The constructor has an API that accepts additional parameters
        to customize plotms but currently those parameters are ignored.

        Args:
            context: Pipeline context object containing state information.
            result: SDApplycalResults instance.
            ms: Measurement Set.
            xaxis: The content of X-axis of the plot.
            yaxis: The content of Y-axis of the plot.
            spw: Spectral window selection. Defaults to '' (all spw).
            ant: Antenna selection. Defaults to '' (all antenna).
        Raises:
            RuntimeError: Invalid field selection in calapp
        """
        self.xaxis = xaxis
        self.yaxis = yaxis
        self.vis = ms.basename
        self.spw = str(spw)
        self.antenna = str(ant)
        self.field = [i.name for i in ms.get_fields(intent='TARGET')]

        if len(self.field) == 0:
            # failed to find field domain object with field
            raise RuntimeError(f'No match found for field "{self.field}".')

        self.antmap = dict((a.id, a.name) for a in ms.antennas)
        if len(self.antenna) == 0:
            self.antenna_selection = 'all'
        else:
            self.antenna_selection = list(self.antmap.values())[int(self.antenna)]
        LOG.info('antenna: ID %s Name \'%s\'' % (self.antenna, self.antenna_selection))

        self.stage_dir = os.path.join(context.report_dir, 'stage%s' % context.task_counter)

    def plot(self) -> list[logger.Plot]:
        """Generate calibrated amplitude vs. time plots.

        Return:
            List of plot objects.
        """

        filename = f'{self.vis}-real_vs_time-{self.antenna_selection}-spw{self.spw}.png'
        title = f'Science target: calibrated amplitude vs time\nAntenna {self.antenna_selection} Spw {self.spw} \ncoloraxis="field"'
        figfile = os.path.join(self.stage_dir, filename)

        if os.path.exists(figfile):
            LOG.debug('Returning existing plot')
        else:
            try:
                task = self._create_task(title, figfile)
                task.execute()
                return [self._get_plot_object(figfile, task)]
            except Exception:
                LOG.error(f"Failed to create calibrated amplitude vs time plot for EB {self.vis} Spw {self.spw} Antenna {self.antenna_selection}.")
                return []

    def _create_task(self, title: str, figfile: str) -> JobRequest:
        """Create task of CASA plotms.

        Args:
            title: Title of figure
            figfile: Name of figure file
        Return:
            Instance of JobRequest.
        """
        field = ",".join(self.field)
        if len(self.antenna) == 0:
            antenna = self.antenna
        else:
            antenna = self.antenna + '&&&'

        task_args = {'vis': self.vis,
                     'xaxis': self.xaxis,
                     'yaxis': self.yaxis,
                     'ydatacolumn': 'corrected',
                     'coloraxis': 'field',
                     'intent': 'OBSERVE_TARGET#ON_SOURCE',
                     'showgui': False,
                     'spw': self.spw,
                     'antenna': antenna,
                     'field': field,
                     'title': title,
                     'showlegend': True,
                     'averagedata': True,
                     'avgchannel': '1e8',
                     'legendposition': 'exteriorRight',
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
        parameters = {'vis': self.vis,
                      'ant': self.antenna_selection,
                      'spw': self.spw}

        return logger.Plot(figfile,
                           x_axis='Time',
                           y_axis='Amplitude',
                           parameters=parameters,
                           command=str(task))


class ApplyCalSingleDishPlotmsSpwComposite(common.LeafComposite):
    """
    Create a PlotLeaf for each spw in the Measurement Set.
    """
    # reference to the PlotLeaf class to call
    leaf_class = ApplyCalSingleDishPlotmsLeaf

    def __init__(self, context: Context, result: SDApplycalResults, ms: MeasurementSet,
                 xaxis: str, yaxis: str, ant: str = '', pol: str = '', **kwargs):
        """Construct ApplyCalSingleDishPlotmsSpwComposite instance.

        Args:
            context: Pipeline context object containing state information.
            result: SDApplycalResults instance.
            ms: Measurement Set.
            xaxis: The content of X-axis of the plot.
            yaxis: The content of Y-axis of the plot.
            ant: Antenna selection. Defaults to '' (all antenna).
            pol: Polarization selection. Defaults to '' (all polarization).

        """
        spwids = [spws.id for spws in ms.get_spectral_windows()]
        children = [self.leaf_class(context, result, ms, xaxis, yaxis,
                    spw=int(spw), ant=ant, pol=pol, **kwargs)
                    for spw in spwids]
        super().__init__(children)


class ApplyCalSingleDishPlotmsAntSpwComposite(common.LeafComposite):
    """Class to create a PlotLeaf for each antenna and spw."""

    leaf_class = ApplyCalSingleDishPlotmsSpwComposite

    def __init__(self, context: Context, result: SDApplycalResults, ms: MeasurementSet,
                 xaxis: str, yaxis: str, pol: str = '', **kwargs):
        """Construct ApplyCalSingleDishPlotmsAntSpwComposite instance.

        Args:
            context: Pipeline context object containing state information.
            result: SDApplycalResults instance.
            ms: Measurement Set.
            xaxis: The content of X-axis of the plot.
            yaxis: The content of Y-axis of the plot.
            pol: Polarization selection. Defaults to '' (all polarization).

        """
        ants = [int(i.id) for i in ms.get_antenna()]
        children = [self.leaf_class(context, result, ms, xaxis, yaxis,
                    ant=ant, pol=pol, **kwargs)
                    for ant in ants]
        super().__init__(children)
