"""
T2_4MDetailsSDApplycalRenderer class.

Created on 24 Oct 2014

@author: sjw
"""
from __future__ import annotations

import collections
import os
import re
from typing import TYPE_CHECKING

import pipeline.domain.measures as measures
import pipeline.h.tasks.applycal.renderer as super_renderer
import pipeline.infrastructure
import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.filenamer as filenamer
import pipeline.infrastructure.renderer.basetemplates as basetemplates
import pipeline.infrastructure.utils as utils
from pipeline.h.tasks.common import flagging_renderer_utils as flagutils
from pipeline.h.tasks.common.displays import applycal as applycal
from pipeline.infrastructure import casa_tools
from pipeline.infrastructure.renderer.logger import Plot

if TYPE_CHECKING:
    from pipeline.domain.source import Source
    from pipeline.domain import MeasurementSet
    from pipeline.h.tasks.applycal.applycal import ApplycalResults
    from pipeline.infrastructure.basetask import ResultsList
    from pipeline.infrastructure.launcher import Context

LOG = logging.get_logger(__name__)


class T2_4MDetailsSDApplycalRenderer(super_renderer.T2_4MDetailsApplycalRenderer):
    """SDApplyCal Renderer class for t2_4m."""

    def __init__(self, uri: str = 'hsd_applycal.mako',
                 description: str = 'Apply calibrations from context',
                 always_rerender: bool = False):
        """Initialise the class.

        Args:
            uri: template file name. default:'hsd_applycal.mako'
            description : description of the class, default:'Apply calibrations from context'
            always_rerender : rerendering execution flag, default: False
        """
        super().__init__(
            uri=uri, description=description, always_rerender=always_rerender)

    def update_mako_context(self, ctx: dict, context: Context, result: ResultsList):
        """Update mako context dict to render.

        Args:
            ctx: mako context dict
            context: pipeline context
            result: list of ApplycalResults
        """
        weblog_dir = os.path.join(context.report_dir,
                                  'stage%s' % result.stage_number)

        # calculate which intents to display in the flagging statistics table
        intents_to_summarise = ['TARGET']  # flagutils.intents_to_summarise(context)
        flag_table_intents = ['TOTAL', 'SCIENCE SPWS']
        flag_table_intents.extend(intents_to_summarise)

        flag_totals = {}
        for r in result:
            if r.inputs['flagsum'] is True:
                flag_totals = utils.dict_merge(flag_totals,
                                               flagutils.flags_for_result(r, context, intents_to_summarise=intents_to_summarise))

        calapps = {}
        for r in result:
            calapps = utils.dict_merge(calapps,
                                       self.calapps_for_result(r))

        caltypes = {}
        for r in result:
            caltypes = utils.dict_merge(caltypes,
                                        self.caltypes_for_result(r))

        filesizes = {}
        for r in result:
            vis = r.inputs['vis']
            ms = context.observing_run.get_ms(vis)
            filesizes[ms.basename] = ms._calc_filesize()

        # return all agents so we get ticks and crosses against each one
        agents = ['before', 'applycal']

        # PIPE-615: Add links to the hif_applycal weblog for viewing each
        # callibrary table (and store all callibrary tables in the weblog
        # directory)
        callib_map = super_renderer.copy_callibrary(result, context.report_dir)

        ctx.update({
            'flags': flag_totals,
            'calapps': calapps,
            'caltypes': caltypes,
            'agents': agents,
            'dirname': weblog_dir,
            'filesizes': filesizes,
            'callib_map': callib_map,
            'flag_table_intents': flag_table_intents
        })

        # CAS-5970: add science target plots to the applycal page
        (science_amp_vs_freq_summary_plots, science_amp_vs_freq_subpages, uv_max) = self.create_single_dish_science_plots(context, result)

        ctx.update({
            'science_amp_vs_freq_plots': science_amp_vs_freq_summary_plots,
            'science_amp_vs_freq_subpages': science_amp_vs_freq_subpages,
            'uv_max': uv_max,
        })

        # PIPE-2168: calibrated amplitude vs time plots
        amp_vs_time_summary_plots = collections.defaultdict(dict)
        amp_vs_time_summary_plots['__hsd_applycal__'] = []
        amp_vs_time_detail_plots = {}
        amp_vs_time_subpages = {}
        for r in result:
            vis = r.inputs['vis']
            amp_vs_time_summary_plots[vis] = []
            amp_vs_time_detail_plots[vis] = []

            if r.amp_vs_time_summary_plots:
                summary_plots = r.amp_vs_time_summary_plots
                amp_vs_time_summary_plots[vis].append(["", summary_plots])

            if r.amp_vs_time_detail_plots:
                detail_plots = r.amp_vs_time_detail_plots
                amp_vs_time_detail_plots[vis].extend(detail_plots)

        if len(amp_vs_time_detail_plots) > 0:
            amp_vs_time_subpages = self.create_amp_vs_time_href(context, result, amp_vs_time_detail_plots)

        # PIPE-2450: XY-deviation plots
        xy_deviation_plots, xy_deviation_subpages = self.create_xy_deviation_plots(context, result)
        if len(xy_deviation_plots) > 0:
            # set to determine that this dict is for hsd_applycal.
            # it should be removed in template before rendering
            xy_deviation_plots['__hsd_applycal__'] = []

        ctx.update({
            'xy_deviation_plots': xy_deviation_plots,
            'xy_deviation_plot_subpages': xy_deviation_subpages
        })

        # members for parent template applycal.mako
        ctx.update({
            'amp_vs_freq_plots': [],
            'phase_vs_freq_plots': [],
            'sd_amp_vs_time_plots': amp_vs_time_summary_plots,
            'amp_vs_uv_plots': [],
            'phase_vs_time_plots': [],
            'corrected_to_antenna1_plots': [],
            'corrected_to_model_vs_uvdist_plots': [],
            'science_amp_vs_uv_plots': [],
            'uv_plots': [],
            'amp_vs_freq_subpages': [],
            'phase_vs_freq_subpages': [],
            'amp_vs_time_subpages': amp_vs_time_subpages,
            'amp_vs_uv_subpages': [],
            'phase_vs_time_subpages': [],
            'outliers_path_link': ''
        })

    def create_single_dish_science_plots(self, context: Context, results: ResultsList) \
            -> tuple[dict[str, list[list[str | list[Plot]]]], dict[str, str], dict[str, measures.Distance]]:
        """
        Create plots for the science targets.

        MODIFIED for single dish

        Args:
            context: pipeline context
            results: ResultsList instance containing Applycal Results

        Returns:
            Three dictionaries of plot objects, subpage paths, and
            max UV distances for each vis.
        """
        amp_vs_freq_summary_plots = collections.defaultdict(dict)
        max_uvs = collections.defaultdict(dict)

        amp_vs_freq_detail_plots = {}

        # set to determine that this dict is for hsd_applycal.
        # it should be removed in template before rendering
        amp_vs_freq_summary_plots['__hsd_applycal__'] = []

        for result in results:
            vis = os.path.basename(result.inputs['vis'])
            ms = context.observing_run.get_ms(vis)
            max_uvs[vis] = measures.Distance(value=0.0, units=measures.DistanceUnits.METRE)

            amp_vs_freq_summary_plots[vis] = []

            for source in filter(lambda source: 'TARGET' in source.intents, ms.sources):
                if len(source.fields) > 0:
                    source_name = source.fields[0].name
                    plots = self._plot_source(context, result, ms, source)
                    amp_vs_freq_summary_plots[vis].append([source_name, plots])

            if pipeline.infrastructure.generate_detail_plots(result):
                fields = set()
                with casa_tools.MSMDReader(result.inputs['vis']) as msmd:
                    fields.update(list(msmd.fieldsforintent("OBSERVE_TARGET#ON_SOURCE")))

                # Science target detail plots. Note that summary plots go onto the
                # detail pages
                plots = self.science_plots_for_result(context,
                                                      result,
                                                      applycal.RealVsFrequencyDetailChart,
                                                      fields, None,
                                                      preserve_coloraxis=True)
                amp_vs_freq_detail_plots[vis] = plots

        # create detail pages
        amp_vs_freq_subpage = None
        for d, plotter_cls in (
                (amp_vs_freq_detail_plots, super_renderer.ApplycalAmpVsFreqPerAntSciencePlotRenderer),):
            if d:
                all_plots = list(utils.flatten([v for v in d.values()]))
                renderer = plotter_cls(context, results, all_plots)
                with renderer.get_file() as fileobj:
                    fileobj.write(renderer.render())
                amp_vs_freq_subpage = renderer.path
        amp_vs_freq_subpages = dict((vis, amp_vs_freq_subpage) for vis in amp_vs_freq_detail_plots.keys())

        return amp_vs_freq_summary_plots, amp_vs_freq_subpages, max_uvs

    def _plot_source(self, context: Context, result: ApplycalResults, ms: MeasurementSet, source: Source) \
            -> list[Plot]:
        """Plot science plots for result.

        Args:
            context : pipeline context
            result : applycal result object
            ms : Measurement Set
            source : target source

        Returns:
            List of Plot objects
        """
        brightest_field = super_renderer.get_brightest_field(ms, source)
        plots = self.science_plots_for_result(context,
                                              result,
                                              applycal.RealVsFrequencySummaryChart,
                                              [brightest_field.id], None,
                                              preserve_coloraxis=True)
        for plot in plots:
            plot.parameters['source'] = source

        return plots

    def create_amp_vs_time_href(self, context: Context, result: ResultsList, plots: dict[str, list[Plot]]) -> dict[str, str]:
        """Create detail page.

        Args:
            context : Pipeline context
            result : List of applycal result objects
            plots : Dictionary which contains 'vis' and list of Plot objects

        Returns:
            amp_vs_time_subpages: Dictionary which contains 'vis' and filepath of detail page
        """
        amp_vs_time_subpage = None
        if plots:
            all_plots = list(utils.flatten([v for v in plots.values()]))
            renderer = super_renderer.ApplycalAmpVsTimePlotRenderer(context, result, all_plots)
            with renderer.get_file() as fileobj:
                fileobj.write(renderer.render())
            amp_vs_time_subpage = renderer.path
        amp_vs_time_subpages = dict((vis, amp_vs_time_subpage) for vis in plots.keys())

        return amp_vs_time_subpages

    def create_xy_deviation_plots(
            self,
            ctx: Context,
            results: ResultsList
    ) -> tuple[dict[str, list[tuple[str, list[Plot]]]], dict[str, str]]:
        """Process the XY-deviation plots for hsd_applycal summary page.

        This function generates Plot objects for XY-deviation plots registered
        to the results objects. Generated Plot objects are classified with the
        metadata, and put to the detail page craeted by this function.
        Summary plots are selected for each field and spectral window
        combination based on the associated QA score.

        Args:
            ctx: Pipeline context.
            results: List of ApplycalResults objects.

        Returns:
            Two tuple containing:
            - A dictionary with keys as MS names and values as lists of tuples
              containing lists of Plot objects for XY-deviation plots
              per field. Each list contains summary plots for all science spws.
            - A dictionary with MS names as keys and paths to the XY-deviation
              detail subpages as values.
        """
        xy_deviation_summary_plots = {}
        xy_deviation_subpages = {}
        xy_deviation_plots_all = []

        for r in results:
            vis = os.path.basename(r.inputs['vis'])

            xy_deviation_qa = [
                x for x in r.qa.pool
                if x.origin.metric_name == 'XX-YY.deviation'
            ]

            # exclude QA scores for heavily flagged data,
            # i.e., all data are flagged or data for either
            # of the polarizations are fully flagged
            xy_deviation_qa_exclude_flagged_cases = [
                x for x in xy_deviation_qa
                if "All data flagged" not in x.longmsg
                   and "Data flagged for one polarization" not in x.longmsg
            ]

            # get the xy-deviation plots
            xy_deviation_plots = [
                generate_plot_object_from_name(ctx, plot_name)
                for plot_name in r.xy_deviation_plots
            ]

            if len(xy_deviation_plots) == 0:
                continue

            # create detail pages
            if xy_deviation_plots:
                xy_deviation_plots_all.extend(xy_deviation_plots)
                summaries = xy_deviation_summary_plots.setdefault(vis, [])
                ms = ctx.observing_run.get_ms(vis)
                target_fields = ms.get_fields(intent="TARGET")
                science_spws = ms.get_spectral_windows(science_windows_only=True)
                for field in target_fields:
                    field_name = field.name.strip('"')
                    plots_per_spw = []
                    for spw in science_spws:
                        # take the plot corresponding to worst QA score
                        # as a summary plot
                        spw_id = spw.id
                        qa_for_field_spw = sorted(
                            filter(
                                lambda x: spw_id in x.applies_to.spw and field_name in x.applies_to.field,
                                xy_deviation_qa_exclude_flagged_cases
                            ),
                            key=lambda x: x.score
                        )
                        if len(qa_for_field_spw) == 0:
                            # no useful QA/plots for this field and spw
                            continue

                        worst_score = qa_for_field_spw[0]
                        antenna = worst_score.applies_to.ant.pop()
                        LOG.debug(
                            "vis %s, field %s, spw %s, antenna %s, worst score %s",
                            vis, field_name, spw, antenna, worst_score.score
                        )
                        plot_name = filenamer.sanitize(
                            f"{vis}_{field_name}_{antenna}_Spw{spw_id}_XX-YY_excess.png"
                        )
                        plot = next(filter(
                            lambda x: x.basename == plot_name,
                            xy_deviation_plots
                        ))
                        plots_per_spw.append(plot)
                    summaries.append([field_name, plots_per_spw])

        if xy_deviation_plots_all:
            detail_page_title = f'Amplitude difference vs frequency'
            detail_renderer = basetemplates.JsonPlotRenderer(
                'generic_x_vs_y_field_spw_ant_detail_plots.mako',
                ctx,
                results,
                xy_deviation_plots_all,
                detail_page_title,
                filenamer.sanitize(f'{detail_page_title.lower()}.html')
            )
            with detail_renderer.get_file() as fileobj:
                fileobj.write(detail_renderer.render())
            xy_deviation_subpage = detail_renderer.path
            for r in results:
                vis = os.path.basename(r.inputs['vis'])
                xy_deviation_subpages[vis] = xy_deviation_subpage

        return xy_deviation_summary_plots, xy_deviation_subpages


def generate_plot_object_from_name(ctx: Context, plot_name: str) -> Plot:
    """Generate a Plot object from the name of the plot.

    This function assumes that the plot name holds some metadata about the
    plot. Expected format of plot_name is::

        <vis>_<field name>_<antenna name>_Spw<spw id>_XX-YY_excess.png

    Args:
        ctx: Pipeline context.
        plot_name: Name of the plot file.

    Returns:
        Plot object with extracted metadata. If the plot name does not match
        the expected format, a Plot object with just the name is returned.
    """
    # pattern should match the name with the following format,
    #
    # <vis>_<field name>_<antenna name>_Spw<spw id>_XX-YY_excess.png
    #
    #   - vis should end with ".ms"
    #   - field can contain any characters
    #   - antenna should not contain "_"
    #   - spw should be a number with 1 to 3 digits
    #
    pattern = re.compile(
        r'(?P<vis>.+\.ms)_(?P<field>.+)_(?P<ant>[^_]+)_Spw(?P<spw>\d{1,3})'
        r'_XX-YY_excess.png'
    )
    m = pattern.match(os.path.basename(plot_name))
    if m:
        vis = m.group('vis')
        field = m.group('field')
        antenna = m.group('ant')
        spw = m.group('spw')
        spw_id = int(spw)
        ms = ctx.observing_run.get_ms(vis)
        spw_object = ms.get_spectral_window(spw_id)
        receiver = spw_object.band
        field_objects = (f for f in ms.fields if f.name.strip('"') == field or f.clean_name == field)
        field_object = next(field_objects, None)
        assert field_object is not None
        field_name = field_object.name
        source = field_object.source
        plot = Plot(
            plot_name,
            x_axis="freq",
            y_axis="amp_diff",
            field=field_name,
            parameters={
                'vis': vis,
                'spw': spw,
                'ant': antenna,
                'source': source,
                'receiver': [receiver]
            }
        )
    else:
        plot = Plot(plot_name)

    return plot
