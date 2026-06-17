import collections
import math
import numpy as np
import os

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.renderer.logger as logger
import pipeline.infrastructure.casa_tasks as casa_tasks
from pipeline.infrastructure import casa_tools
LOG = infrastructure.get_logger(__name__)


class Chart:
    def plot(self):
        task_plots = {
            "testBPdcals": [self.get_plot_wrapper('BPcal'), self.get_plot_wrapper('delaycal')],
            "semiFinalBPdcals": [self.get_plot_wrapper()],
            "finalcals": [self.get_plot_wrapper()]
        }
        plots = task_plots.get(self.taskname, [])
        return [p for p in plots if p is not None]

    def get_plot_params(self, figfile, taskname=None):
        corrstring = self.ms.get_vla_corrstring()

        plot_params = {
            'xaxis': 'freq', 'yaxis': 'amp', 'plotrange': [], 'title': '', 'xlabel': '', 'ylabel': '',
            'showmajorgrid': False, 'showminorgrid': False, 'plotfile': figfile, 'overwrite': True,
            'clearplots': True, 'showgui': False,
            }
        if taskname == "testBPdcals" or "semiFinalBPdcals":
            plot_params.update({'vis': self.ms.name, 'ydatacolumn': 'corrected', 'selectdata': True, 'averagedata': True,
                                'avgtime': '1e8', 'avgscan': True, 'transform': False, 'extendflag': False, 'iteraxis': '',
                                'coloraxis': 'antenna2', 'correlation': corrstring})
        elif taskname == "finalcals":
            plot_params.update({'vis': self.result.ktypecaltable, 'field': '', 'antenna': '0~2', 'spw': '', 'timerange': '',
                                'coloraxis': 'spw', 'titlefont': 8, 'xaxisfont': 7, 'yaxisfont': 7})
            # 'title': 'K table: finaldelay.tbl   Antenna: {!s}'.format('0~2'),
        return plot_params

    def get_maxphase_maxamp(self, bpcaltablename):
        """
        Calculates the maximum amplitude and phase values from the bandpass calibration table.

        Args:
            bpcaltablename (str): The name of the bandpass calibration table.

        Returns:
            tuple: The maximum amplitude and phase values.
        """
        with casa_tools.TableReader(bpcaltablename) as tb:
            dataVarCol = tb.getvarcol('CPARAM')
            flagVarCol = tb.getvarcol('FLAG')

        rowlist = list(dataVarCol.keys())
        maxmaxamp = 0.0
        maxmaxphase = 0.0
        for rrow in rowlist:
            dataArr = dataVarCol[rrow]
            flagArr = flagVarCol[rrow]
            amps = np.abs(dataArr)
            phases = np.arctan2(np.imag(dataArr), np.real(dataArr))
            good = np.logical_not(flagArr)
            tmparr = amps[good]
            if len(tmparr) > 0:
                maxamp = np.max(amps[good])
                if maxamp > maxmaxamp:
                    maxmaxamp = maxamp
            tmparr = np.abs(phases[good])
            if len(tmparr) > 0:
                maxphase = np.max(np.abs(phases[good])) * 180. / math.pi
                if maxphase > maxmaxphase:
                    maxmaxphase = maxphase
        ampplotmax = maxmaxamp
        phaseplotmax = maxmaxphase
        return phaseplotmax.item(), ampplotmax.item()


class SummaryChart(Chart):
    def __init__(self, context, result, spw='', suffix='', taskname=None):
        self.context = context
        self.result = result
        self.ms = context.observing_run.get_ms(result.inputs['vis'])
        self.spw = str(spw)
        self.suffix = suffix
        self.taskname = taskname

    def create_plot(self, prefix=''):
        figfile = self.get_figfile(prefix)

        bandpass_field_select_string = self.context.evla['msinfo'][self.ms.name].bandpass_field_select_string
        bandpass_scan_select_string = self.context.evla['msinfo'][self.ms.name].bandpass_scan_select_string
        delay_scan_select_string = self.context.evla['msinfo'][self.ms.name].delay_scan_select_string
        calibrator_scan_select_string = self.context.evla['msinfo'][self.ms.name].calibrator_scan_select_string
        plot_params = super().get_plot_params(figfile, self.taskname)
        if self.spw:
            plot_params['spw'] = self.spw
        plot_scan = None
        if self.taskname == "testBPdcals":
            if prefix == 'BPcal':
                plot_scan = self.context.evla['msinfo'][self.ms.name].bandpass_scan_select_string
                if self.spw is not None:
                    plot_params['field'] = bandpass_field_select_string

            if (delay_scan_select_string != bandpass_scan_select_string) and prefix == 'delaycal':
                plot_scan = delay_scan_select_string

        elif self.taskname == "semiFinalBPdcals":
            plot_scan = calibrator_scan_select_string
            plot_params['avgscan'] = False
        elif self.taskname == "finalcals":
            plot_scan = ""

        if plot_scan is not None:
            job = casa_tasks.plotms(**{**plot_params, 'scan': plot_scan})
            job.execute()

    def get_figfile(self, prefix):
        filename = ''
        base_path = os.path.join(self.context.report_dir, 'stage%s' % self.result.stage_number)
        if self.taskname == "testBPdcals":
            if self.spw is not None:
                filename = 'testcalibrated_per_spw_' + self.spw + '_' + prefix
            else:
                filename = 'testcalibrated' + prefix
        elif self.taskname == "semiFinalBPdcals":
            if self.spw is not None:
                filename = 'semifinalcalibrated_per_spw_' + self.spw + '_' + self.suffix
            else:
                filename = 'semifinalcalibrated_' + self.suffix
        elif self.taskname == "finalcals":
            filename = "finalcalsjunk"
        if filename:
            filename = os.path.join(base_path, (filename + '-%s-summary.png' % self.ms.basename))
        return filename

    def get_plot_wrapper(self, prefix=''):
        figfile = self.get_figfile(prefix=prefix)

        bandpass_scan_select_string = self.context.evla['msinfo'][self.ms.name].bandpass_scan_select_string
        delay_scan_select_string = self.context.evla['msinfo'][self.ms.name].delay_scan_select_string
        plot_type = ''
        if self.taskname == "testBPdcals":
            xaxis = "freq"
            yaxis = "amp"
            if prefix == 'BPcal' or ((delay_scan_select_string != bandpass_scan_select_string) and prefix == 'delaycal'):
                plot_type = prefix
        elif self.taskname == "semiFinalBPdcals":
            xaxis = "freq"
            yaxis = "amp"
            if self.spw is not None:
                plot_type = 'semifinalcalibratedcals per spw' + self.suffix
            else:
                plot_type = 'semifinalcalibratedcals' + self.suffix
        elif self.taskname == "finalcals":
            xaxis = "freq"
            yaxis = "delay"
            plot_type = "finalcalsjunk"

        if plot_type:
            params = {'vis': self.ms.basename, 'type': plot_type}
            if self.spw is not None:
                params['spw'] = self.spw
            wrapper = logger.Plot(figfile, x_axis=xaxis, y_axis=yaxis, parameters=params)

        if not os.path.exists(figfile):
            LOG.trace('Summary plot not found. Creating new plot.')
            try:
                self.create_plot(prefix)
            except Exception as ex:
                LOG.error('Could not create plot.')
                LOG.exception(ex)
                return None

        if plot_type:
            return wrapper
        return None


class PerAntennaChart(Chart):
    def __init__(self, context, result, suffix='', taskname=None, plottype=None, perSpwChart=False):
        self.context = context
        self.result = result
        self.ms = context.observing_run.get_ms(result.inputs['vis'])
        self.taskname = taskname
        self.suffix = suffix
        self.plottype = plottype
        self.perSpwChart = perSpwChart
        self.json = {}
        plottext = ""
        if self.plottype == "delay":
            plottext = "testdelays" if self.taskname == "testBPdcals" else "delays" if self.taskname == "semiFinalBPdcals" else 'finaldelays' if self.taskname == "finalcals" else ''
        elif self.plottype == "ampgain":
            plottext = "ampgain" if self.taskname == "testBPdcals" else ''
        elif self.plottype == "phasegain":
            plottext = "phasegain" if self.taskname == "testBPdcals" else "phasegain-" + self.suffix \
                        if self.taskname == "semiFinalBPdcals" else 'finalphasegain' if self.taskname == "finalcals" else ''
        elif self.plottype == "bpsolamp":
            plottext = "bpsolamp" if self.taskname == "testBPdcals" else "bpsolamp-" + self.suffix if self.taskname == "semiFinalBPdcals"\
                else 'finalbpsolamp' if self.taskname == "finalcals" else ''
        elif self.plottype == "bpsolphase":
            plottext = "bpsolphase" if self.taskname == "testBPdcals" else "bpsolphase-" + self.suffix if self.taskname == "semiFinalBPdcals"\
                else 'finalbpsolphase' if self.taskname == "finalcals" else ''
        elif self.plottype == "bpsolamp_perspw":
            plottext = "bpsolamp" if self.taskname == "testBPdcals" else "bpsolamp_perspw-" + self.suffix if self.taskname == "semiFinalBPdcals"\
                else 'finalbpsolamp' if self.taskname == "finalcals" else ''
        elif self.plottype == "bpsolphase_perspw":
            plottext = "bpsolphase" if self.taskname == "testBPdcals" else "bpsolphase_perspw-" + self.suffix if self.taskname == "semiFinalBPdcals"\
                else 'finalbpsolphase' if self.taskname == "finalcals" else ''
        elif self.plottype == "finalbpsolphaseshort":
            plottext = "finalbpsolphaseshort"
        elif self.plottype == "finalamptimecal":
            plottext = "finalamptimecal"
        elif self.plottype == "finalampfreqcal":
            plottext = "finalampfreqcal"
        elif self.plottype == "finalphasegaincal":
            plottext = "finalphasegaincal"

        if plottext:
            self.json_filename = os.path.join(context.report_dir,
                                            f'stage{result.stage_number}',
                                            f'{plottext}-{self.ms}.json')

    def plot(self):
        nplots = len(self.ms.antennas)
        plots = []
        result_table = None
        times = []
        xconnector = ''
        plot_title = ''
        xaxis = ''
        yaxis = ''
        filenametext = ''

        type = None
        plot_params = {
            'vis': '',
            'xaxis': 'time',
            'yaxis': 'phase',
            'field': '',
            'antenna': '',
            'spw': '',
            'timerange': '',
            'coloraxis': '',
            'plotrange': [],
            'symbolshape': 'circle',
            'title': '',
            'titlefont': 8,
            'xaxisfont': 7,
            'yaxisfont': 7,
            'showgui': False,
            'plotfile': '',
            'xconnector': 'line'
        }

        LOG.info("Plotting {!s} {!s}".format(self.taskname, self.plottype))

        if self.plottype == "delay":
            filenametext = "testdelay" if self.taskname == "testBPdcals" else "delay" \
                        if self.taskname == "semiFinalBPdcals" else 'finaldelays' if self.taskname == "finalcals" else ''
            type = "Test Delay" if self.taskname == "testBPdcals" else 'delay' + self.suffix \
                if self.taskname == "semiFinalBPdcals" else 'Final delay' if self.taskname == "finalcals" else None
            result_table = self.result.ktypecaltable
            xconnector = 'step'
            xaxis = 'Frequency'
            yaxis = 'Amp'
        elif self.plottype == "ampgain":
            filenametext = "testBPdinitialgainamp" if self.taskname == "testBPdcals" else ''
            type = "Amp Gain" if self.taskname == "testBPdcals" else None
            result_table = self.result.bpdgain_touse
            xconnector = 'line'
            xaxis = 'Time'
            yaxis = 'Amp'
        elif self.plottype == "phasegain":
            result_table = self.result.bpdgain_touse
            filenametext = "testBPdinitialgainphase" if self.taskname == "testBPdcals" else "BPinitialgainphase" if self.taskname == "semiFinalBPdcals" \
                else 'finalBPinitialgainphase' if self.taskname == "finalcals" else ''
            xconnector = 'line'
            xaxis = 'Time'
            yaxis = 'phase'
            plot_params['symbolshape'] = 'circle'
            type = "Phase Gain" if self.taskname == "testBPdcals" else 'phasegain' + self.suffix if self.taskname == "semiFinalBPdcals"\
                else 'BP initial gain phase' if self.taskname == "finalcals" else None
        elif self.plottype == "bpsolamp":
            result_table = self.result.bpcaltable
            filenametext = "testBPcal_amp" if self.taskname == "testBPdcals" else "BPcal_amp" if self.taskname == "semiFinalBPdcals"\
                else 'finalBPcal_amp' if self.taskname == "finalcals" else ''
            xconnector = 'step'
            xaxis = 'Frequency'
            yaxis = 'Amp'
            plot_params['symbolshape'] = 'circle'
            type = "Bandpass Amp Solution" if self.taskname == "testBPdcals" else 'bpsolamp' + self.suffix if self.taskname == "semiFinalBPdcals"\
                else 'BP Amp solution' if self.taskname == "finalcals" else None
        elif self.plottype == "bpsolphase":
            result_table = self.result.bpcaltable
            filenametext = "testBPcal_phase" if self.taskname == "testBPdcals" else "BPcal_phase" if self.taskname == "semiFinalBPdcals"\
                else 'finalBPcal_phase' if self.taskname == "finalcals" else ''
            xconnector = 'step'
            xaxis = 'Frequency'
            yaxis = 'Phase'
            plot_params['symbolshape'] = 'circle'
            type = "Bandpass Phase Solution" if self.taskname == "testBPdcals" else 'bpsolphase' + self.suffix if self.taskname == "semiFinalBPdcals"\
                else 'BP Phase solution' if self.taskname == "finalcals" else None
        elif self.plottype == "bpsolamp_perspw":
            result_table = self.result.bpcaltable
            filenametext = "testBPcal_amp" if self.taskname == "testBPdcals" else "BPcal_amp" if self.taskname == "semiFinalBPdcals"\
                else 'finalBPcal_amp' if self.taskname == "finalcals" else ''
            xconnector = 'step'
            xaxis = 'Frequency'
            yaxis = 'Amp'
            plot_params['symbolshape'] = 'circle'
            type = "Bandpass Amp Solution" if self.taskname == "testBPdcals" else 'bpsolamp' + self.suffix if self.taskname == "semiFinalBPdcals"\
                else 'BP Amp solution' if self.taskname == "finalcals" else None
        elif self.plottype == "bpsolphase_perspw":
            result_table = self.result.bpcaltable
            filenametext = "testBPcal_phase" if self.taskname == "testBPdcals" else "BPcal_phase" if self.taskname == "semiFinalBPdcals"\
                else 'finalBPcal_phase' if self.taskname == "finalcals" else ''
            xconnector = 'step'
            xaxis = 'Frequency'
            yaxis = 'Phase'
            plot_params['symbolshape'] = 'circle'
            type = "Bandpass Phase Solution" if self.taskname == "testBPdcals" else 'bpsolphase' + self.suffix if self.taskname == "semiFinalBPdcals"\
                else 'BP Phase solution' if self.taskname == "finalcals" else None
        elif self.plottype == "finalbpsolphaseshort":
            result_table = self.result.phaseshortgaincaltable
            filenametext = "phaseshortgaincal"
            xconnector = 'line'
            xaxis = 'Time'
            yaxis = 'Phase'
            plot_params['symbolshape'] = 'circle'
            type = "Phase (short) gain solution"
        elif self.plottype == "finalamptimecal":
            result_table = self.result.finalampgaincaltable
            filenametext = "finalamptimecal"
            xconnector = 'line'
            xaxis = 'Time'
            yaxis = 'Amp'
            plot_params['symbolshape'] = 'circle'
            type = "Final amp time cal"
        elif self.plottype == "finalampfreqcal":
            result_table = self.result.finalampgaincaltable
            filenametext = "finalampfreqcal"
            xconnector = 'step'
            xaxis = 'freq'
            yaxis = 'Amp'
            plot_params['symbolshape'] = 'circle'
            type = "Final amp freq cal"
        elif self.plottype == "finalphasegaincal":
            result_table = self.result.finalphasegaincaltable
            filenametext = "finalphasegaincal"
            xconnector = 'line'
            xaxis = 'time'
            yaxis = 'phase'
            plot_params['symbolshape'] = 'circle'
            type = "Final phase gain cal"

        plot_params['xaxis'] = xaxis
        plot_params['yaxis'] = yaxis
        plot_params['xconnector'] = xconnector

        plotrange = []
        spws = []
        spw2band = self.ms.get_vla_spw2band()

        if self.perSpwChart:
            spws = self.ms.get_spectral_windows(science_windows_only=True)
        else:
            # adding a place holder if perSpwChart is false
            # This is just to ensure that loop executes atleast once if
            # perSpwChart is false
            spws.append(-1)
        if self.taskname == "finalcals":
            if self.perSpwChart:
                spws = self.ms.get_spectral_windows(science_windows_only=True)
            else:
                spwlist = [spw.id for spw in self.ms.get_spectral_windows(science_windows_only=True)]
                band2spw = collections.defaultdict(list)
                for spw, band in spw2band.items():
                    if spw in spwlist:
                        band2spw[band].append(str(spw))

            result_table = {band: result_table for band in {band for spw, band in spw2band.items()}}

        for bandname, tabitem in result_table.items():
            # PIPE-1729: check gaintable is present
            if not os.path.exists(tabitem):
                LOG.warning("{!s} not found".format(tabitem))
                continue
            with casa_tools.TableReader(tabitem) as tb:
                times.extend(tb.getcol('TIME'))

        if len(times) == 0:
            return []
        mintime = np.min(times)
        maxtime = np.max(times)
        for spw in spws:
            if not self.perSpwChart or spw.specline_window:
                for bandname, tabitem in result_table.items():
                    # PIPE-1729: check gaintable is present
                    if not os.path.exists(tabitem):
                        LOG.warning("{!s} not found".format(tabitem))
                        continue
                    if self.perSpwChart and spw2band[spw.id] != bandname:
                        continue
                    if self.plottype == "bpsolamp" or self.plottype == "bpsolphase" or self.plottype == "bpsolamp_perspw" or self.plottype == "bpsolphase_perspw":
                        maxmaxphase, maxmaxamp = self.get_maxphase_maxamp(tabitem)
                        ampplotmax = maxmaxamp
                        plotmax = maxmaxphase
                    if self.plottype == "finalamptimecal" or self.plottype == "finalampfreqcal" or self.plottype == "ampgain":
                        with casa_tools.TableReader(tabitem) as tb:
                            cpar = tb.getcol('CPARAM')
                            flgs = tb.getcol('FLAG')
                        amps = np.abs(cpar)
                        good = np.logical_not(flgs)
                        maxamp = np.max(amps[good])
                        plotmax = max(2.0, maxamp)

                    if self.plottype == "delay":
                        plot_title_prefix = 'K table: {!s}  '.format(tabitem if self.taskname == "testBPdcals"
                                                                     else "delay.tbl" if self.taskname == "semiFinalBPdcals"
                                                                     else "finaldelay.tbl" if self.taskname == "finalcals" else "")

                    elif self.plottype == "ampgain":
                        plotrange = [mintime, maxtime, 0.0, plotmax]
                        plot_title_prefix = 'G table: {!s}'.format(tabitem)
                    elif self.plottype == "phasegain":
                        plotrange = [mintime, maxtime, -180, 180]
                        plot_title_prefix = 'G table: {!s}  '.format(tabitem if self.taskname == "testBPdcals"
                                                                     else tabitem if self.taskname == "semiFinalBPdcals"
                                                                     else "finalBPinitialgain.tbl" if self.taskname == "finalcals" else "")
                    elif self.plottype == "bpsolamp":
                        plotrange = [0, 0, 0, ampplotmax]
                        plot_title_prefix = 'B table: {!s}  '.format(tabitem if self.taskname == "testBPdcals"
                                                                     else "BPcal.b" if self.taskname == "semiFinalBPdcals"
                                                                     else "finalBPcal.tbl" if self.taskname == "finalcals" else "")
                    elif self.plottype == "bpsolphase":
                        plotrange = [0, 0, -plotmax, plotmax]
                        plot_title_prefix = 'B table: {!s}  '.format(tabitem if self.taskname == "testBPdcals"
                                                                     else "BPcal.tbl" if self.taskname == "semiFinalBPdcals"
                                                                     else "finalBPcal.tbl" if self.taskname == "finalcals" else "")
                    elif self.plottype == "bpsolamp_perspw":
                        plot_title_prefix = 'B table: {!s}  '.format(tabitem if self.taskname == "testBPdcals"
                                                                     else "BPcal.b" if self.taskname == "semiFinalBPdcals"
                                                                     else "finalBPcal.tbl" if self.taskname == "finalcals" else "")
                        plotrange = [0, 0, 0, ampplotmax]
                    elif self.plottype == "bpsolphase_perspw":
                        plot_title_prefix = 'B table: {!s}  '.format(tabitem if self.taskname == "testBPdcals"
                                                                     else "BPcal.tbl" if self.taskname == "semiFinalBPdcals"
                                                                     else "finalBPcal.tbl" if self.taskname == "finalcals" else "")
                        plotrange = [0, 0, -plotmax, plotmax]
                    elif self.plottype == "finalbpsolphaseshort":
                        plot_title_prefix = 'G table: phaseshortgaincal.tbl  '
                        plotrange = [mintime, maxtime, -180, 180]
                    elif self.plottype == "finalamptimecal":
                        plot_title_prefix = 'G table: finalampgaincal.tbl  '
                        plotrange = [mintime, maxtime, 0, plotmax]
                    elif self.plottype == "finalampfreqcal":
                        plot_title_prefix = 'G table: finalampgaincal.tbl  '
                        plotrange = [0, 0, 0, plotmax]
                    elif self.plottype == "finalphasegaincal":
                        plot_title_prefix = 'G table: finalphasegaincal.tbl  '
                        plotrange = [mintime, maxtime, -180, 180]

                    plot_params['plotrange'] = plotrange

                    for ii in range(nplots):
                        if self.taskname == "testBPdcals" or self.taskname == "finalcals":
                            filename = filenametext + str(ii) + '_' + bandname
                        elif self.taskname == "semiFinalBPdcals":
                            filename = filenametext + str(ii) + '_' + self.suffix + '_' + bandname

                        if self.taskname == "finalcals" and not self.perSpwChart:
                            plot_params['spw'] = ",".join(band2spw[bandname])

                        if self.perSpwChart:
                            filename = "{!s}_{!s}.png".format(filename, str(spw.id))
                            plot_params['spw'] = str(spw.id)
                        else:
                            filename = "{!s}.png".format(filename)

                        antPlot = str(ii)
                        # Get antenna name
                        domain_antennas = self.ms.get_antenna(antPlot)
                        idents = [a.name if a.name else a.id for a in domain_antennas]
                        antName = ','.join(idents)

                        stage = 'stage%s' % self.result.stage_number
                        stage_dir = os.path.join(self.context.report_dir, stage)
                        # construct the relative filename, eg. 'stageX/testdelay0.png'

                        figfile = os.path.join(stage_dir, filename)
                        plot_failed = False
                        if not os.path.exists(figfile):
                            try:
                                LOG.debug("Plotting {!s} {!s} {!s}".format(self.taskname, self.plottype, antName))
                                if not self.perSpwChart:
                                    plot_title = "{!s} Antenna: {!s}  Band: {!s}".format(plot_title_prefix, antName, bandname)
                                else:
                                    plot_title = "{!s} Antenna: {!s}  Band: {!s} Spw: {!s}".format(plot_title_prefix, antName, bandname, str(spw.id))

                                plot_params['vis'] = tabitem
                                plot_params['antenna'] = antPlot
                                plot_params['title'] = plot_title
                                plot_params['plotfile'] = figfile

                                job = casa_tasks.plotms(**plot_params)

                                job.execute()
                            except Exception as ex:
                                plot_failed = True
                                LOG.warning("Unable to plot " + filename)
                        else:
                            LOG.debug('Using existing ' + filename + ' plot.')
                        if not plot_failed:
                            try:
                                plot = logger.Plot(figfile, x_axis=xaxis, y_axis=yaxis, field='',
                                                parameters={'spw': plot_params['spw'],
                                                            'pol': '',
                                                            'ant': antName,
                                                            'bandname': bandname,
                                                            'type': type,
                                                            'file': os.path.basename(figfile)})
                                plots.append(plot)
                            except Exception as ex:
                                LOG.warning("Unable to add plot to stack ", ex)
                                plots.append(None)

        return [p for p in plots if p is not None]
