import collections
import itertools
import operator
import os

import pipeline.h.tasks.common.flagging_renderer_utils as flagutils
import pipeline.infrastructure
import pipeline.infrastructure.filenamer as filenamer
import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.renderer.basetemplates as basetemplates
import pipeline.infrastructure.utils as utils
from pipeline.h.tasks.common.displays import applycal
from pipeline.hifv.tasks.common.renderer import renderer as baseRenderer


LOG = logging.get_logger(__name__)


class T2_4MDetailsfinalcalsRenderer(baseRenderer.calsRenderer):
    def __init__(self, uri='finalcals.mako', description='Final Calibration Tables',
                 always_rerender=False):
        super().__init__(uri=uri, description=description,
                         always_rerender=always_rerender, taskname="finalcals")

    def get_display_context(self, context, results):
        ctx = super().get_display_context(context, results)
        return ctx


class T2_4MDetailsVLAApplycalRenderer(basetemplates.T2_4MDetailsDefaultRenderer):
    def __init__(self, uri='applycals.mako',
                 description='Apply calibrations from context',
                 always_rerender=False):
        super(T2_4MDetailsVLAApplycalRenderer, self).__init__(
            uri=uri, description=description, always_rerender=always_rerender)

    def update_mako_context(self, ctx, context, result):
        weblog_dir = os.path.join(context.report_dir,
                                  'stage%s' % result.stage_number)

        flag_totals = {}
        for r in result:
            try:
                flag_totals = utils.dict_merge(flag_totals,
                                               flagutils.flags_for_result(r, context))
            except:
                LOG.info("No flagging summaries.")

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
            filesizes[os.path.basename(vis)] = ms._calc_filesize()

        # return all agents so we get ticks and crosses against each one
        agents = ['before', 'applycal']

        ctx.update({'flags'    : flag_totals,
                    'calapps'  : calapps,
                    'caltypes' : caltypes,
                    'agents'   : agents,
                    'dirname'  : weblog_dir,
                    'filesizes': filesizes})

    def create_science_plots(self, context, results, correlation):
        """
        Create plots for the science targets, returning two dictionaries of
        vis:[Plots].
        """
        amp_vs_freq_summary_plots = collections.defaultdict(dict)
        phase_vs_freq_summary_plots = collections.defaultdict(dict)
        amp_vs_uv_summary_plots = collections.defaultdict(dict)
        max_uvs = collections.defaultdict(dict)

        for result in results:
            # Plot for 1 science field (either 1 science target or for a mosaic 1
            # pointing). The science field that should be chosen is the one with
            # the brightest average amplitude over all spws
            vis = os.path.basename(result.inputs['vis'])
            ms = context.observing_run.get_ms(vis)

            # Ideally, the uvmax of the spectrum (plots 1 and 2)
            # would be set by the appearance of plot 3; that is, if there is
            # no obvious drop in amplitude with uvdist, then use all the data.
            # A simpler compromise would be to use a uvrange that captures the
            # inner half the data.
            max_uvs[vis], uv_range = utils.scale_uv_range(ms)
            LOG.debug('Setting UV range to %s for %s', uv_range, vis)

            brightest_fields = T2_4MDetailsVLAApplycalRenderer.get_brightest_fields(ms)

            # Limit to 30 sources via CAS-8737
            # MAX_PLOTS = 30
            ## Nplots = (len(brightest_fields.items())/30)+1

            m = context.observing_run.measurement_sets[0]
            alltargetfields = m.get_fields(intent='TARGET')
            Nplots = (len(alltargetfields)/30)+1

            targetfields = [field for field in alltargetfields[0:len(alltargetfields):Nplots]]

            plotfields = targetfields

            '''
            for field in plotfields:
                plots = self.science_plots_for_result(context,
                                                      result,
                                                      applycal.AmpVsFrequencyPerBasebandSummaryChart,
                                                      [field.id],
                                                      uv_range, correlation=correlation)
                amp_vs_freq_summary_plots[vis][field.id] = plots


            for field in plotfields:
                plots = self.science_plots_for_result(context,
                                                      result,
                                                      applycal.PhaseVsFrequencySummaryChart,
                                                      [field.id],
                                                      uv_range, correlation=correlation)
                phase_vs_freq_summary_plots[vis][field.id] = plots

                plots = self.science_plots_for_result(context,
                                                      result,
                                                      applycal.AmpVsUVBasebandSummaryChart,
                                                      [field.id], correlation=correlation)
                amp_vs_uv_summary_plots[vis][field.id] = plots
            '''

            '''
            for source_id, brightest_field in brightest_fields.items()[0:len(brightest_fields.items()):Nplots]:
                plots = self.science_plots_for_result(context,
                                                      result,
                                                      applycal.AmpVsFrequencyPerBasebandSummaryChart,
                                                      [brightest_field.id],
                                                      uv_range, correlation=correlation)
                amp_vs_freq_summary_plots[vis][source_id] = plots

            for source_id, brightest_field in brightest_fields.items()[0:len(brightest_fields.items()):Nplots]:
                plots = self.science_plots_for_result(context,
                                                      result,
                                                      applycal.PhaseVsFrequencySummaryChart,
                                                      [brightest_field.id],
                                                      uv_range, correlation=correlation)
                phase_vs_freq_summary_plots[vis][source_id] = plots

                plots = self.science_plots_for_result(context,
                                                      result,
                                                      applycal.AmpVsUVBasebandSummaryChart,
                                                      [brightest_field.id], correlation=correlation)
                amp_vs_uv_summary_plots[vis][source_id] = plots
            '''

            if pipeline.infrastructure.generate_detail_plots(result):
                scans = ms.get_scans(scan_intent='TARGET')
                fields = set()
                for scan in scans:
                    fields.update([field.id for field in scan.fields])

                # Science target detail plots. Note that summary plots go onto the
                # detail pages; we don't create plots per spw or antenna
                self.science_plots_for_result(context,
                                              result,
                                              applycal.AmpVsFrequencyPerBasebandSummaryChart,
                                              fields,
                                              uv_range,
                                              ApplycalAmpVsFreqSciencePlotRenderer, correlation=correlation)

                self.science_plots_for_result(context,
                                              result,
                                              applycal.PhaseVsFrequencySummaryChart,
                                              fields,
                                              uv_range,
                                              ApplycalPhaseVsFreqSciencePlotRenderer, correlation=correlation)

                self.science_plots_for_result(context,
                                              result,
                                              applycal.AmpVsUVBasebandSummaryChart,
                                              fields,
                                              renderer_cls=ApplycalAmpVsUVSciencePlotRenderer, correlation=correlation)

        # sort plots by baseband so that the summary plots appear in baseband order
        '''
        for vis, source_plots in amp_vs_freq_summary_plots.items():
            self.sort_plots_by_baseband(source_plots)
        for vis, source_plots in phase_vs_freq_summary_plots.items():
            self.sort_plots_by_baseband(source_plots)
        for vis, source_plots in amp_vs_uv_summary_plots.items():
            self.sort_plots_by_baseband(source_plots)
        '''

        return (amp_vs_freq_summary_plots,  max_uvs)

    def science_plots_for_result(self, context, result, plotter_cls, fields,
                                 uvrange=None, renderer_cls=None, correlation=''):
        # override field when plotting amp/phase vs frequency, as otherwise
        # the field is resolved to a list of all field IDs
        overrides = {'coloraxis': 'spw',
                     'correlation': correlation}
        if uvrange is not None:
            overrides['uvrange'] = uvrange

        m = context.observing_run.measurement_sets[0]

        plots = []
        for field in fields:
            # override field when plotting amp/phase vs frequency, as otherwise
            # the field is resolved to a list of all field IDs
            overrides['field'] = field

            plotter = plotter_cls(context, result, ['TARGET'], **overrides)
            plots.extend(plotter.plot())

        for plot in plots:
            plot.parameters['intent'] = ['TARGET']

        if renderer_cls is not None:
            renderer = renderer_cls(context, result, plots, **overrides)
            with renderer.get_file() as fileobj:
                fileobj.write(renderer.render())

        return plots

    @staticmethod
    def get_brightest_fields(ms, intent='TARGET'):
        """

        """
        # get IDs for all science spectral windows
        spw_ids = set()
        for scan in ms.get_scans(scan_intent=intent):
            scan_spw_ids = {dd.spw.id for dd in scan.data_descriptions}
            spw_ids.update(scan_spw_ids)

        if intent == 'TARGET':
            science_ids = {spw.id for spw in ms.get_spectral_windows()}
            spw_ids = spw_ids.intersection(science_ids)

        result = collections.OrderedDict()

        by_source_id = lambda field: field.source.id
        fields_by_source_id = sorted(ms.get_fields(intent=intent),
                                     key=by_source_id)
        for source_id, source_fields in itertools.groupby(fields_by_source_id,
                                                          by_source_id):
            fields = list(source_fields)

            # give the sole science target name if there's only one science target
            # in this ms.
            if len(fields) == 1:
                LOG.info('Only one %s target for Source #%s. Bypassing '
                         'brightest target selection.', intent, source_id)
                result[source_id] = fields[0]
                continue

            field = fields[0]
            LOG.warning('Bypassing brightest field selection due to problem '
                        'with visstat. Using Field #%s (%s) for Source #%s'
                        '', field.id, field.name, source_id)
            result[source_id] = field

        return result

    def sort_plots_by_baseband(self, d):
        for vis, plots in d.items():
            plots = sorted(plots, key=lambda plot: plot.parameters['baseband'])
            d[vis] = plots

    def create_plots(self, context, results, plotter_cls, intents, renderer_cls=None, **kwargs):
        """
        Create plots and return a dictionary of vis:[Plots].
        """
        d = {}
        for result in results:
            plots = self.plots_for_result(context, result, plotter_cls, intents, renderer_cls, **kwargs)
            d = utils.dict_merge(d, plots)
        return d

    def plots_for_result(self, context, result, plotter_cls, intents, renderer_cls=None, **kwargs):
        vis = os.path.basename(result.inputs['vis'])

        plotter = plotter_cls(context, result, intents, **kwargs)
        plots = plotter.plot()
        for plot in plots:
            plot.parameters['intent'] = intents

        d = collections.defaultdict(dict)
        d[vis] = plots

        if renderer_cls is not None:
            renderer = renderer_cls(context, result, plots, **kwargs)
            with renderer.get_file() as fileobj:
                fileobj.write(renderer.render())

        return d

    def calapps_for_result(self, result):
        calapps = collections.defaultdict(list)
        for calapp in result.applied:
            vis = os.path.basename(calapp.vis)
            calapps[vis].append(calapp)
        return calapps

    def caltypes_for_result(self, result):
        type_map = {
            'bandpass': 'Bandpass',
            'gaincal': 'Gain',
            'tsys': 'T<sub>sys</sub>',
            'wvr': 'WVR',
        }

        d = {}
        for calapp in result.applied:
            for calfrom in calapp.calfrom:
                caltype = type_map.get(calfrom.caltype, calfrom.caltype)

                if calfrom.caltype == 'gaincal':
                    # try heuristics to detect phase-only and amp-only
                    # solutions
                    caltype += self.get_gain_solution_type(calfrom.gaintable)

                d[calfrom.gaintable] = caltype

        return d

    def get_gain_solution_type(self, gaintable):
        # solve circular import problem by importing at run-time
        from pipeline.infrastructure import casa_tasks

        # get stats on amp solution of gaintable
        calstat_job = casa_tasks.calstat(caltable=gaintable, axis='amp',
                                         datacolumn='CPARAM', useflags=True)
        calstat_result = calstat_job.execute()
        stats = calstat_result['CPARAM']

        # amp solutions of unity imply phase-only was requested
        tol = 1e-3
        no_amp_soln = all([utils.approx_equal(stats['sum'], stats['npts'], tol),
                           utils.approx_equal(stats['min'], 1, tol),
                           utils.approx_equal(stats['max'], 1, tol)])

        # same again for phase solution
        calstat_job = casa_tasks.calstat(caltable=gaintable, axis='phase',
                                         datacolumn='CPARAM', useflags=True)
        calstat_result = calstat_job.execute()
        stats = calstat_result['CPARAM']

        # phase solutions ~ 0 implies amp-only solution
        tol = 1e-5
        no_phase_soln = all([utils.approx_equal(stats['sum'], 0, tol),
                             utils.approx_equal(stats['min'], 0, tol),
                             utils.approx_equal(stats['max'], 0, tol)])

        if no_phase_soln and not no_amp_soln:
            return ' (amplitude only)'
        if no_amp_soln and not no_phase_soln:
            return ' (phase only)'
        return ''


class ApplycalAmpVsFreqPlotRenderer(basetemplates.JsonPlotRenderer):
    def __init__(self, context, result, plots, **overrides):
        vis = os.path.basename(result.inputs['vis'])
        title = 'Calibrated amplitude vs frequency for %s' % vis
        outfile = filenamer.sanitize('amp_vs_freq-%s.html' % vis)

        super(ApplycalAmpVsFreqPlotRenderer, self).__init__(
                'generic_x_vs_y_field_spw_ant_detail_plots.mako', context,
                result, plots, title, outfile, **overrides)


class ApplycalPhaseVsFreqPlotRenderer(basetemplates.JsonPlotRenderer):
    def __init__(self, context, result, plots, **overrides):
        vis = os.path.basename(result.inputs['vis'])
        title = 'Calibrated phase vs frequency for %s' % vis
        outfile = filenamer.sanitize('phase_vs_freq-%s.html' % vis)

        super(ApplycalPhaseVsFreqPlotRenderer, self).__init__(
                'generic_x_vs_y_field_spw_ant_detail_plots.mako', context,
                result, plots, title, outfile, **overrides)


class ApplycalAmpVsFreqSciencePlotRenderer(basetemplates.JsonPlotRenderer):
    def __init__(self, context, result, plots, **overrides):
        vis = os.path.basename(result.inputs['vis'])
        title = 'Calibrated amplitude vs frequency for %s' % vis
        outfile = filenamer.sanitize('science_amp_vs_freq-%s.html' % vis)

        super(ApplycalAmpVsFreqSciencePlotRenderer, self).__init__(
                'generic_x_vs_y_field_baseband_detail_plots.mako', context,
                result, plots, title, outfile, **overrides)


class ApplycalPhaseVsFreqSciencePlotRenderer(basetemplates.JsonPlotRenderer):
    def __init__(self, context, result, plots, **overrides):
        vis = os.path.basename(result.inputs['vis'])
        title = 'Calibrated phase vs frequency for %s' % vis
        outfile = filenamer.sanitize('science_phase_vs_freq-%s.mako' % vis)

        super(ApplycalPhaseVsFreqSciencePlotRenderer, self).__init__(
                'generic_x_vs_y_field_baseband_detail_plots.html', context,
                result, plots, title, outfile, **overrides)


class ApplycalAmpVsUVSciencePlotRenderer(basetemplates.JsonPlotRenderer):
    def __init__(self, context, result, plots, **overrides):
        vis = os.path.basename(result.inputs['vis'])
        title = 'Calibrated amplitude vs UV distance for %s' % vis
        outfile = filenamer.sanitize('science_amp_vs_uv-%s.html' % vis)

        super(ApplycalAmpVsUVSciencePlotRenderer, self).__init__(
                'generic_x_vs_y_field_baseband_detail_plots.mako', context,
                result, plots, title, outfile, **overrides)


class ApplycalAmpVsUVPlotRenderer(basetemplates.JsonPlotRenderer):
    def __init__(self, context, result, plots, **overrides):
        vis = os.path.basename(result.inputs['vis'])
        title = 'Calibrated amplitude vs UV distance for %s' % vis
        outfile = filenamer.sanitize('amp_vs_uv-%s.html' % vis)

        super(ApplycalAmpVsUVPlotRenderer, self).__init__(
                'generic_x_vs_y_spw_ant_plots.mako', context,
                result, plots, title, outfile, **overrides)


class ApplycalPhaseVsUVPlotRenderer(basetemplates.JsonPlotRenderer):
    def __init__(self, context, result, plots, **overrides):
        vis = os.path.basename(result.inputs['vis'])
        title = 'Calibrated phase vs UV distance for %s' % vis
        outfile = filenamer.sanitize('phase_vs_uv-%s.html' % vis)

        super(ApplycalPhaseVsUVPlotRenderer, self).__init__(
                'generic_x_vs_y_spw_ant_plots.mako', context,
                result, plots, title, outfile, **overrides)


class ApplycalAmpVsTimePlotRenderer(basetemplates.JsonPlotRenderer):
    def __init__(self, context, result, plots, **overrides):
        vis = os.path.basename(result.inputs['vis'])
        title = 'Calibrated amplitude vs times for %s' % vis
        outfile = filenamer.sanitize('amp_vs_time-%s.html' % vis)

        super(ApplycalAmpVsTimePlotRenderer, self).__init__(
                'generic_x_vs_y_field_spw_ant_detail_plots.mako', context,
                result, plots, title, outfile, **overrides)


class ApplycalPhaseVsTimePlotRenderer(basetemplates.JsonPlotRenderer):
    def __init__(self, context, result, plots, **overrides):
        vis = os.path.basename(result.inputs['vis'])
        title = 'Calibrated phase vs times for %s' % vis
        outfile = filenamer.sanitize('phase_vs_time-%s.html' % vis)

        super(ApplycalPhaseVsTimePlotRenderer, self).__init__(
                'generic_x_vs_y_field_spw_ant_detail_plots.mako', context,
                result, plots, title, outfile, **overrides)
