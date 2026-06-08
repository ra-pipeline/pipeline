import collections
import contextlib
import importlib
import os


import pipeline.infrastructure.filenamer as filenamer
import pipeline.infrastructure.renderer.basetemplates as basetemplates
import pipeline.infrastructure.renderer.weblog as weblog


class VLASubPlotRenderer:
    def __init__(self, context, result, plots, json_path, template, filename_prefix, bandlist, spwlist=None, spw_plots=None, taskname=None):
        self.context = context
        self.result = result
        self.plots = plots
        self.ms = os.path.basename(self.result.inputs['vis'])
        self.template = template
        self.filename_prefix = filename_prefix
        self.bandlist = bandlist
        self.spwlist = spwlist
        self.spw_plots = spw_plots
        self.taskname = taskname
        if self.spwlist is None:
            self.spwlist = []

        if self.spw_plots is None:
            self.spw_plots = []

        self.summary_plots = {}
        self.delay_subpages = {}
        self.ampgain_subpages = {}
        self.phasegain_subpages = {}
        self.bpsolamp_subpages = {}
        self.bpsolphase_subpages = {}
        self.bpsolphaseshort_subpages = {}
        self.finalamptimecal_subpages = {}
        self.finalampfreqcal_subpages = {}
        self.finalphasegaincal_subpages = {}
        delay_filename = {
            "testBPdcals": "testdelays",
            "semiFinalBPdcals": "delays",
            "finalcals": "finaldelays"}.get(self.taskname, '')
        self.delay_subpages[self.ms] = filenamer.sanitize('%s-%s.html' % (delay_filename, self.ms))
        self.phasegain_subpages[self.ms] = filenamer.sanitize('phasegain' + '-%s.html' % self.ms)
        self.bpsolamp_subpages[self.ms] = filenamer.sanitize('bpsolamp' + '-%s.html' % self.ms)
        self.bpsolphase_subpages[self.ms] = filenamer.sanitize('bpsolphase' + '-%s.html' % self.ms)

        if self.taskname == "testBPdcals":
            self.ampgain_subpages[self.ms] = filenamer.sanitize('ampgain' + '-%s.html' % self.ms)
        if self.taskname == "finalcals":
            self.bpsolphaseshort_subpages[self.ms] = filenamer.sanitize('bpsolphaseshort' + '-%s.html' % self.ms)
            self.finalamptimecal_subpages[self.ms] = filenamer.sanitize('finalamptimecal' + '-%s.html' % self.ms)
            self.finalampfreqcal_subpages[self.ms] = filenamer.sanitize('finalampfreqcal' + '-%s.html' % self.ms)
            self.finalphasegaincal_subpages[self.ms] = filenamer.sanitize('finalphasegaincal' + '-%s.html' % self.ms)
        if os.path.exists(json_path):
            with open(json_path, 'r') as json_file:
                self.json = json_file.readlines()[0]
        else:
            self.json = '{}'

    def _get_display_context(self):
        retundict = {'pcontext': self.context,
                     'result': self.result,
                     'plots': self.plots,
                     'spw_plots': self.spw_plots,
                     'dirname': self.dirname,
                     'json': self.json,
                     'delay_subpages': self.delay_subpages,
                     'ampgain_subpages': self.ampgain_subpages,
                     'phasegain_subpages': self.phasegain_subpages,
                     'bpsolamp_subpages': self.bpsolamp_subpages,
                     'bpsolphase_subpages': self.bpsolphase_subpages,
                     'spwlist': self.spwlist,
                     'bandlist': self.bandlist}
        if self.taskname == "finalcals":
            retundict["bpsolphaseshort_subpages"] = self.bpsolphaseshort_subpages
            retundict["finalamptimecal_subpages"] = self.finalamptimecal_subpages
            retundict["finalampfreqcal_subpages"] = self.finalampfreqcal_subpages
            retundict["finalphasegaincal_subpages"] = self.finalphasegaincal_subpages

        return retundict

    @property
    def dirname(self):
        stage = 'stage%s' % self.result.stage_number
        return os.path.join(self.context.report_dir, stage)

    @property
    def filename(self):
        filename = filenamer.sanitize(self.filename_prefix + '-%s.html' % self.ms)
        return filename

    @property
    def path(self):
        return os.path.join(self.dirname, self.filename)

    def get_file(self):
        if not os.path.exists(self.dirname):
            os.makedirs(self.dirname)

        file_obj = open(self.path, 'w')
        return contextlib.closing(file_obj)

    def render(self):
        display_context = self._get_display_context()
        t = weblog.TEMPLATE_LOOKUP.get_template(self.template)
        return t.render(**display_context)


class calsRenderer(basetemplates.T2_4MDetailsDefaultRenderer):
    def __init__(self, uri, description, always_rerender=False, taskname=''):
        super().__init__(uri=uri, description=description, always_rerender=always_rerender)
        self.taskname = taskname

    def load_display(self):

        module_name = {
            "testBPdcals": "pipeline.hifv.tasks.testBPdcals.display",
            "semiFinalBPdcals": "pipeline.hifv.tasks.semiFinalBPdcals.display",
            "finalcals": "pipeline.hifv.tasks.finalcals.display"}.get(self.taskname, '')

        return importlib.import_module(module_name)

    def get_display_context(self, context, results):
        super_cls = super()
        ctx = super_cls.get_display_context(context, results)
        display = self.load_display()
        weblog_dir = os.path.join(context.report_dir,
                                  'stage%s' % results.stage_number)
        # varibales common to
        # cals task
        summary_plots = {}
        summary_plots_per_spw = {}
        delay_subpages = {}
        ampgain_subpages = {}
        phasegain_subpages = {}
        bpsolamp_subpages = {}
        bpsolphase_subpages = {}

        # semiFinalBPdcals variables
        suffix = ''

        # finalcals variables
        bpsolphaseshort_subpages = {}
        finalamptimecal_subpages = {}
        finalampfreqcal_subpages = {}
        finalphasegaincal_subpages = {}

        band2spw = collections.defaultdict(list)

        # based on the task deciding
        # which template to use
        template = {
            "testBPdcals": "testcals_plots.mako",
            "semiFinalBPdcals": "semifinalcals_plots.mako",
            "finalcals": "finalcals_plots.mako"}.get(self.taskname, '')

        for result in results:

            m = context.observing_run.get_ms(result.inputs['vis'])
            spw2band = m.get_vla_spw2band()
            spwobjlist = m.get_spectral_windows(science_windows_only=True)
            listspws = [spw.id for spw in spwobjlist]
            for spw, band in spw2band.items():
                if spw in listspws:  # Science intents only
                    band2spw[band].append(str(spw))
            ms = os.path.basename(result.inputs['vis'])
            if self.taskname == "testBPdcals" or self.taskname == "semiFinalBPdcals":
                plotter = display.SummaryChart(context, result, taskname=self.taskname, suffix=suffix)
                plots = plotter.plot()
                summary_plots[ms] = plots
            else:
                summary_plots[ms] = None

            # generate per-SPW testBPdcals plots for specline windows
            spws = m.get_spectral_windows(science_windows_only=True)
            spwlist = []
            per_spw_plots = []
            for spw in spws:
                if spw.specline_window:
                    if self.taskname == "testBPdcals" or self.taskname == "semiFinalBPdcals":
                        plotter = display.SummaryChart(context, result, spw=spw.id, taskname=self.taskname)
                        plots = plotter.plot()
                        per_spw_plots.extend(plots)
                    spwlist.append(str(spw.id))

            if per_spw_plots:
                summary_plots_per_spw[ms] = []
                summary_plots_per_spw[ms].extend(per_spw_plots)
            filename_prefix = {
                "testBPdcals": "testdelays",
                "semiFinalBPdcals": "delays",
                "finalcals": "finaldelays"}.get(self.taskname, '')
            # generate testdelay plots and JSON file
            plotter = display.AntennaChart(context, result, taskname=self.taskname, plottype="delay", suffix=suffix)
            plots = plotter.plot()
            json_path = plotter.json_filename
            # write the html for each MS to disk
            renderer = VLASubPlotRenderer(context, result, plots, json_path, template, filename_prefix, band2spw, taskname=self.taskname)
            with renderer.get_file() as fileobj:
                fileobj.write(renderer.render())
                delay_subpages[ms] = renderer.filename

            if self.taskname == "testBPdcals":
                # generate amp Gain plots and JSON file
                plotter = display.AntennaChart(context, result, taskname=self.taskname, plottype="ampgain")
                plots = plotter.plot()
                json_path = plotter.json_filename

                # write the html for each MS to disk
                renderer = VLASubPlotRenderer(context, result, plots, json_path, template, 'ampgain', band2spw, taskname=self.taskname)
                with renderer.get_file() as fileobj:
                    fileobj.write(renderer.render())
                    ampgain_subpages[ms] = renderer.filename

            # generate phase Gain plots and JSON file
            plotter = display.AntennaChart(context, result, taskname=self.taskname, plottype="phasegain", suffix=suffix)
            plots = plotter.plot()
            json_path = plotter.json_filename

            # write the html for each MS to disk
            renderer = VLASubPlotRenderer(context, result, plots, json_path, template, 'phasegain', band2spw, taskname=self.taskname)
            with renderer.get_file() as fileobj:
                fileobj.write(renderer.render())
                phasegain_subpages[ms] = renderer.filename

            # generate amp bandpass solution plots and JSON file
            plotter = display.AntennaChart(context, result, taskname=self.taskname, plottype="bpsolamp", suffix=suffix)
            plots = plotter.plot()
            json_path = plotter.json_filename

            # generate amp bandpass solution per-spw plots
            plotter = display.AntennaChart(context, result, taskname=self.taskname, plottype="bpsolamp_perspw", perSpwChart=True, suffix=suffix)
            spw_plots = plotter.plot()

            # write the html for each MS to disk
            renderer = VLASubPlotRenderer(context, result, plots, json_path, template, 'bpsolamp', band2spw, spwlist, spw_plots=spw_plots, taskname=self.taskname)
            with renderer.get_file() as fileobj:
                fileobj.write(renderer.render())
                bpsolamp_subpages[ms] = renderer.filename

            # generate phase bandpass solution plots and JSON file
            plotter = display.AntennaChart(context, result, taskname=self.taskname, plottype="bpsolphase",  suffix=suffix)
            plots = plotter.plot()
            json_path = plotter.json_filename

            # generate phase bandpass per spw solution plots
            plotter = display.AntennaChart(context, result, taskname=self.taskname, plottype="bpsolphase_perspw", perSpwChart=True,  suffix=suffix)
            spw_plots = plotter.plot()

            # write the html for each MS to disk
            renderer = VLASubPlotRenderer(context, result, plots, json_path, template, 'bpsolphase', band2spw, spwlist, spw_plots=spw_plots, taskname=self.taskname)
            with renderer.get_file() as fileobj:
                fileobj.write(renderer.render())
                bpsolphase_subpages[ms] = renderer.filename

            if self.taskname == "finalcals":
                # generate phase short bandpass solution plots and JSON file
                plotter = display.AntennaChart(context, result, taskname=self.taskname, plottype="finalbpsolphaseshort", suffix=suffix)
                plots = plotter.plot()
                json_path = plotter.json_filename

                # write the html for each MS to disk
                renderer = VLASubPlotRenderer(context, result, plots, json_path, template, 'bpsolphaseshort', band2spw, taskname=self.taskname)
                with renderer.get_file() as fileobj:
                    fileobj.write(renderer.render())
                    bpsolphaseshort_subpages[ms] = renderer.filename

                # generate final amp time cal solution plots and JSON file
                plotter = display.AntennaChart(context, result, taskname=self.taskname, plottype="finalamptimecal", suffix=suffix)
                plots = plotter.plot()
                json_path = plotter.json_filename

                plotter = display.AntennaChart(context, result, taskname=self.taskname, plottype='finalamptimecal', perSpwChart=True, suffix=suffix)
                spw_plots = plotter.plot()

                # write the html for each MS to disk
                renderer = VLASubPlotRenderer(context, result, plots, json_path, template, 'finalamptimecal', band2spw, spwlist, spw_plots=spw_plots, taskname=self.taskname)
                with renderer.get_file() as fileobj:
                    fileobj.write(renderer.render())
                    finalamptimecal_subpages[ms] = renderer.filename

                # generate final amp freq cal solution plots and JSON file
                plotter = display.AntennaChart(context, result, taskname=self.taskname, plottype="finalampfreqcal", suffix=suffix)
                plots = plotter.plot()
                json_path = plotter.json_filename

                # write the html for each MS to disk
                renderer = VLASubPlotRenderer(context, result, plots, json_path, template, 'finalampfreqcal', band2spw, taskname=self.taskname)
                with renderer.get_file() as fileobj:
                    fileobj.write(renderer.render())
                    finalampfreqcal_subpages[ms] = renderer.filename

                # generate final phase gain cal solution plots and JSON file
                plotter = display.AntennaChart(context, result, taskname=self.taskname, plottype="finalphasegaincal", suffix=suffix)
                plots = plotter.plot()
                json_path = plotter.json_filename

                plotter = display.AntennaChart(context, result, taskname=self.taskname, plottype="finalphasegaincal", perSpwChart=True, suffix=suffix)
                spw_plots = plotter.plot()

                # write the html for each MS to disk
                renderer = VLASubPlotRenderer(context, result, plots, json_path, template, 'finalphasegaincal', band2spw, spwlist, spw_plots=spw_plots, taskname=self.taskname)
                with renderer.get_file() as fileobj:
                    fileobj.write(renderer.render())
                    finalphasegaincal_subpages[ms] = renderer.filename

        ctx.update({'summary_plots': summary_plots,
                    'summary_plots_per_spw': summary_plots_per_spw,
                    'delay_subpages': delay_subpages,
                    'ampgain_subpages': ampgain_subpages,
                    'phasegain_subpages': phasegain_subpages,
                    'bpsolamp_subpages': bpsolamp_subpages,
                    'bpsolphase_subpages': bpsolphase_subpages,
                    'dirname': weblog_dir})
        if self.taskname == "finalcals":
            ctx.update({'bpsolphaseshort_subpages': bpsolphaseshort_subpages,
                        'finalamptimecal_subpages': finalamptimecal_subpages,
                        'finalampfreqcal_subpages': finalampfreqcal_subpages,
                        'finalphasegaincal_subpages': finalphasegaincal_subpages})
        return ctx
