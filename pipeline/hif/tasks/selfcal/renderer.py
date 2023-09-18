
import collections
import os
import string

import pipeline.infrastructure.filenamer as filenamer
import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.renderer.basetemplates as basetemplates
import pipeline.infrastructure.utils as utils
from pipeline.infrastructure.utils.weblog import plots_to_html

from . import display

LOG = logging.get_logger(__name__)


class SelfCalQARenderer(basetemplates.CommonRenderer):
    def __init__(self, context, results, cleantarget, solint):
        super().__init__('selfcalqa.mako', context, results)

        slib = cleantarget['sc_lib']
        target, band = cleantarget['field_name'], cleantarget['sc_band']

        stage_dir = os.path.join(context.report_dir, 'stage%s' % results.stage_number)
        r = results[0]
        outfile = f'{target}_{band}_{solint}.html'
        valid_chars = "_.-%s%s" % (string.ascii_letters, string.digits)
        self.path = os.path.join(stage_dir, filenamer.sanitize(outfile, valid_chars))
        self.rel_path = os.path.relpath(self.path, context.report_dir)

        image_plots, antpos_plots, phasefreq_plots = display.SelfcalSummary(context, r, cleantarget).plot_qa(solint)
        summary_tab, nsol_tab = self.make_summary_table(context, r, cleantarget, solint, image_plots, antpos_plots)

        self.extra_data = {
            'summary_tab': summary_tab,
            'nsol_tab': nsol_tab,
            'target': target,
            'band': band,
            'solint': solint,
            'antpos_plots': antpos_plots,
            'phasefreq_plots': phasefreq_plots,
            'slib': slib}

    def update_mako_context(self, mako_context):
        mako_context.update(self.extra_data)

    def make_summary_table(self, context, r, cleantarget, solint, image_plots, antpos_plots):

        slib = cleantarget['sc_lib']

        # the prior vs. post image comparison table

        rows = []
        row_names = ['Data Type', 'Image', 'SNR', 'RMS', 'Beam']
        vislist = slib['vislist']
        slib_solint = slib[vislist[0]][solint]
        for row_name in row_names:
            if row_name == 'Data Type':
                row_values = ['Prior', 'Post']
            if row_name == 'Image':
                row_values = plots_to_html(image_plots, report_dir=context.report_dir, title='Prior/Post Image Comparison')
            if row_name == 'SNR':
                row_values = ['{:0.3f}'.format(slib_solint['SNR_pre']),
                              '{:0.3f}'.format(slib_solint['SNR_post'])]
            if row_name == 'RMS':
                row_values = ['{:0.3f} mJy/bm'.format(slib_solint['RMS_pre']*1e3),
                              '{:0.3f} mJy/bm'.format(slib_solint['RMS_post']*1e3)]
            if row_name == 'Beam':
                row_values = ['{:0.3f}"x{:0.3f}" {:0.3f} deg'.format(
                    slib_solint['Beam_major_pre'],
                    slib_solint['Beam_minor_pre'],
                    slib_solint['Beam_PA_pre']),
                    '{:0.3f}"x{:0.3f}" {:0.3f} deg'.format(
                    slib_solint['Beam_major_post'],
                    slib_solint['Beam_minor_post'],
                    slib_solint['Beam_PA_post'])]
            rows.append([row_name]+row_values)

        # per-vis solution summary table

        nsol_rows = []
        vis_row_names = ['N Sol.', 'N Flagged Sol.', 'Frac. Flagged Sol.', 'Fallback Mode', 'Spwmap']
        vislist = slib['vislist']
        for vis in vislist:
            nsol_stats = antpos_plots[vis].parameters

            antpos_html = plots_to_html([antpos_plots[vis]], report_dir=context.report_dir)[0]

            vis_desc = ('<a class="anchor" id="{0}_summary"></a>'
                        '<a href="#{0}_byant">'
                        '   {0}'
                        '</a>'.format(vis))

            vis_desc = vis_desc+' '+antpos_html

            for row_name in vis_row_names:
                if row_name == 'N Sol.':
                    row_values = [nsol_stats['nsols']]
                if row_name == 'N Flagged Sol.':
                    row_values = [nsol_stats['nflagged_sols']]
                if row_name == 'Frac. Flagged Sol.':
                    row_values = ['{:0.3f} &#37;'.format(nsol_stats['nflagged_sols']/nsol_stats['nsols']*100.)]
                if row_name == 'Fallback Mode':
                    row_value = '-'
                    if solint == 'inf_EB' and 'fallback' in slib[vis][solint]:
                        fallback_mode = slib[vis][solint]['fallback']
                        if fallback_mode == '':
                            row_value = 'None'
                        if fallback_mode == 'combinespw':
                            row_value = 'Combine SPW'
                        if fallback_mode == 'spwmap':
                            row_value = 'SPWMAP'
                    row_values = [row_value]
                if row_name == 'Spwmap':
                    row_values = [slib[vis][solint]['spwmap']]
                nsol_rows.append([vis_desc]+[row_name]+row_values)

        return utils.merge_td_columns(rows, vertical_align=True), utils.merge_td_columns(nsol_rows, vertical_align=True)


class T2_4MDetailsSelfcalRenderer(basetemplates.T2_4MDetailsDefaultRenderer):
    def __init__(self, uri='selfcal.mako',
                 description='Produce rms images',
                 always_rerender=False):
        super().__init__(uri=uri,
                         description=description, always_rerender=always_rerender)

    def make_targets_summary_table(self, r, targets):
        """Make the selfcal targets summary list table."""
        rows = []

        def bool2icon(value):
            if value:
                return '<span class="glyphicon glyphicon-ok"></span>'
            else:
                return '<span class="glyphicon glyphicon-remove"></span>'

        for target in targets:
            row = []
            valid_chars = "%s%s" % (string.ascii_letters, string.digits)
            id_name = filenamer.sanitize(target['field_name']+'_'+target['sc_band'], valid_chars)
            row.append(f' <a href="#{id_name}">{fm_target(target)}</a> ')
            row.append(target['sc_band'].replace('_', ' '))
            row.append(target['spw'])
            row.append(target['phasecenter'])
            row.append(target['cell'])
            row.append(target['imsize'])
            row.append(', '.join(target['sc_solints']))
            row.append(bool2icon(target['sc_lib']['SC_success']))
            row.append(bool2icon(target['sc_lib']['SC_success'] and r.applycal_result_contline is not None))
            row.append(bool2icon(target['sc_lib']['SC_success'] and r.applycal_result_line is not None))
            rows.append(row)

        return utils.merge_td_columns(rows, vertical_align=True)

    def update_mako_context(self, ctx, context, results):

        stage_dir = os.path.join(context.report_dir, 'stage%s' % results.stage_number)
        r = results[0]
        cleantargets = [cleantarget for cleantarget in r.targets if not cleantarget['sc_exception']]
        is_restore = r.is_restore

        if cleantargets:
            targets_summary_table = self.make_targets_summary_table(r, cleantargets)
        else:
            targets_summary_table = None

        summary_tabs = collections.OrderedDict()
        solint_tabs = collections.OrderedDict()
        spw_tabs = collections.OrderedDict()
        spw_tabs_msg = collections.OrderedDict()

        for target in cleantargets:

            if not is_restore:
                # only do this when not restoring from a previous run (selfcal_resourcs avaibility is not warranted)
                key = (target['field_name'], target['sc_band'])
                slib = target['sc_lib']
                summary_tabs[key] = self.make_summary_table(context, r, target)
                solint_tabs[key] = self.make_solint_summary_table(target, context, results)
                spw_tabs[key], spw_tabs_msg[key] = self.make_spw_summary_table(slib)

        ctx.update({'targets_summary_table': targets_summary_table,
                    'is_restore': is_restore,
                    'solint_tabs': solint_tabs,
                    'summary_tabs': summary_tabs,
                    'spw_tabs': spw_tabs,
                    'cleantargets': cleantargets, })

    def make_solint_summary_table(self, cleantarget, context, results):

        solints, target, band = cleantarget['sc_solints'], cleantarget['field_name'], cleantarget['sc_band']
        slib = cleantarget['sc_lib']
        check_solint = False

        rows = []
        vislist = slib['vislist']
        vis_keys = list(slib[vislist[-1]].keys())
        row_names = [
            'Pass', 'intflux_final', 'intflux_improvement', 'SNR_final', 'SNR_Improvement', 'SNR_NF_final',
            'SNR_NF_Improvement', 'RMS_final', 'RMS_Improvement', 'RMS_NF_final', 'RMS_NF_Improvement',
            'Beam_pre', 'Beam_post', 'Beam_Ratio',
            'clean_threshold']
        qa_extra_data = {}

        for row_name in row_names:

            row = []

            if row_name == 'Pass':
                row.append('Result')
            if row_name == 'intflux_final':
                row.append('Integrated Flux')
            if row_name == 'intflux_improvement':
                row.append('Integrated Flux Change')
            if row_name == 'SNR_final':
                row.append('Dynamic Range')
            if row_name == 'SNR_Improvement':
                row.append('DR Improvement')
            if row_name == 'SNR_NF_final':
                row.append('Dynamic Range (N.F.)')
            if row_name == 'SNR_NF_Improvement':
                row.append('DR Improvement (N.F.)')
            if row_name == 'RMS_final':
                row.append('RMS')
            if row_name == 'RMS_Improvement':
                row.append('RMS Improvement')
            if row_name == 'RMS_NF_final':
                row.append('RMS (N.F.)')
            if row_name == 'RMS_NF_Improvement':
                row.append('RMS Improvement (N.F.)')
            if row_name == 'Beam_pre':
                row.append('Beam Pre')
            if row_name == 'Beam_post':
                row.append('Beam post')
            if row_name == 'Beam_Ratio':
                row.append(text_with_tooltip('Ratio of Beam Area', 'The ratio of the beam area before and after self-calibration.'))
            if row_name == 'clean_threshold':
                row.append('Clean Threshold')

            for solint in solints:
                if solint not in vis_keys:
                    row.append('-')
                else:
                    check_solint = True
                    slib_solint = slib[vislist[-1]][solint]
                    vis_solint_keys = slib_solint.keys()
                    if row_name == 'Pass':
                        result_desc = '-'
                        if not slib_solint['Pass']:
                            result_desc = '<font color="red">{}</font> {}'.format('Fail', slib_solint['Fail_Reason'])
                        else:
                            result_desc = '<font color="blue">{}</font>'.format('Pass')

                        qa_renderer = SelfCalQARenderer(context, results, cleantarget, solint)
                        qa_extra_data[solint] = qa_renderer.extra_data
                        with qa_renderer.get_file() as fileobj:
                            fileobj.write(qa_renderer.render())
                        result_desc = f'{result_desc}<br><a class="replace" href="{qa_renderer.rel_path}">QA Plots</a>'
                        row.append(result_desc)
                    if row_name == 'intflux_final':
                        row.append('{:0.3f} &#177 {:0.3f} mJy'.format(
                            slib_solint['intflux_post'] * 1e3,
                            slib_solint['e_intflux_post'] * 1e3))
                    if row_name == 'intflux_improvement':
                        row.append('{:0.3f}'.format(
                            slib_solint['intflux_post'] /
                            slib_solint['intflux_pre']))
                    if row_name == 'SNR_final':
                        row.append('{:0.3f}'.format(slib_solint['SNR_post']))
                    if row_name == 'SNR_Improvement':
                        row.append('{:0.3f}'.format(
                            slib_solint['SNR_post'] /
                            slib_solint['SNR_pre']))
                    if row_name == 'SNR_NF_final':
                        row.append('{:0.3f}'.format(slib_solint['SNR_NF_post']))
                    if row_name == 'SNR_NF_Improvement':
                        row.append('{:0.3f}'.format(
                            slib_solint['SNR_NF_post'] /
                            slib_solint['SNR_NF_pre']))

                    if row_name == 'RMS_final':
                        row.append('{:0.3f} mJy/bm'.format(slib_solint['RMS_post']*1e3))
                    if row_name == 'RMS_Improvement':
                        row.append('{:0.3f}'.format(
                            slib_solint['RMS_pre'] /
                            slib_solint['RMS_post']))
                    if row_name == 'RMS_NF_final':
                        row.append('{:0.3f} mJy/bm'.format(slib_solint['RMS_NF_post']*1e3))
                    if row_name == 'RMS_NF_Improvement':
                        row.append('{:0.3f}'.format(
                            slib_solint['RMS_NF_pre'] /
                            slib_solint['RMS_NF_post']))
                    if row_name == 'Beam_pre':
                        row.append('{:0.3f}"x{:0.3f}" {:0.3f} deg'.format(
                            slib_solint['Beam_major_pre'],
                            slib_solint['Beam_minor_pre'],
                            slib_solint['Beam_PA_pre']))
                    if row_name == 'Beam_post':
                        row.append('{:0.3f}"x{:0.3f}" {:0.3f} deg'.format(
                            slib_solint['Beam_major_post'],
                            slib_solint['Beam_minor_post'],
                            slib_solint['Beam_PA_post']))
                    if row_name == 'Beam_Ratio':
                        row.append('{:0.3f}'.format(
                            (slib_solint['Beam_major_post'] *
                             slib_solint['Beam_minor_post']) /
                            (slib['Beam_major_orig'] *
                             slib['Beam_minor_orig'])))
                    if row_name == 'clean_threshold':
                        if row_name in vis_solint_keys:
                            row.append('{:0.3f} mJy/bm'.format(
                                slib_solint['clean_threshold']*1e3))
                        else:
                            row.append('Not Available')

            rows.append(row)

        for vis in vislist:

            rows.append(['Measurement Set']+[vis]*len(solints))

            for row_name in ['Flagged Frac.<br>by antenna', 'N.Sols', 'N.Sols Flagged', 'Flagged Frac.']:
                row = [row_name]
                for solint in solints:
                    if solint in vis_keys:
                        nsol_stats = qa_extra_data[solint]['antpos_plots'][vis].parameters
                        if row_name == 'N.Sols':
                            row.append(nsol_stats['nsols'])
                        if row_name == 'N.Sols Flagged':
                            row.append(nsol_stats['nflagged_sols'])
                        if row_name == 'Flagged Frac.':
                            row.append('{:0.3f} &#37;'.format(nsol_stats['nflagged_sols']/nsol_stats['nsols']*100.))
                        if row_name == 'Flagged Frac.<br>by antenna':
                            antpos_html = plots_to_html(
                                [qa_extra_data[solint]['antpos_plots'][vis]],
                                report_dir=context.report_dir, title='Frac. Flagged Sol. Per Antenna')[0]
                            row.append(antpos_html)
                    else:
                        row.append('-')
                rows.append(row)

        if check_solint:
            new_rows = utils.merge_td_rows(utils.merge_td_columns(rows, vertical_align=True))
        else:
            new_rows = None

        return new_rows

    def make_spw_summary_table(self, slib):

        spwlist = list(slib['per_spw_stats'].keys())
        check_all_spws = False

        rows = []
        rows.append(['']+spwlist)
        quantities = ['bandwidth', 'effective_bandwidth', 'SNR_orig', 'SNR_final', 'RMS_orig', 'RMS_final']
        for key in quantities:
            row = [key]
            for spw in spwlist:
                spwkeys = slib['per_spw_stats'][spw].keys()
                if 'SNR' in key and key in spwkeys:
                    row.append('{:0.3f}'.format(slib['per_spw_stats'][spw][key]))
                    check_all_spws = True
                    continue
                if 'RMS' in key and key in spwkeys:
                    row.append('{:0.3f} mJy/bm'.format(slib['per_spw_stats'][spw][key]*1e3))
                    check_all_spws = True
                    continue
                if 'bandwidth' in key and key in spwkeys:
                    row.append('{:0.4f} GHz'.format(slib['per_spw_stats'][spw][key]))
                    continue
                row.append('-')
            rows.append(row)
        warning_msg = []
        # for spw in spwlist:
        #     spwkeys = slib['per_spw_stats'][spw].keys()
        #     if 'delta_SNR' in spwkeys or 'delta_RMS' in spwkeys or 'delta_beamarea' in spwkeys:
        #         if slib['per_spw_stats'][spw]['delta_SNR'] < 0.0:
        #             htmlOut.writelines('WARNING SPW '+spw+' HAS LOWER SNR POST SELFCAL')
        #         if slib['per_spw_stats'][spw]['delta_RMS'] > 0.0:
        #             htmlOut.writelines('WARNING SPW '+spw+' HAS HIGHER RMS POST SELFCAL')
        #         if slib['per_spw_stats'][spw]['delta_beamarea'] > 0.05:
        #             htmlOut.writelines('WARNING SPW '+spw+' HAS A >0.05 CHANGE IN BEAM AREA POST SELFCAL')
        if check_all_spws:
            return utils.merge_td_columns(rows, vertical_align=True), warning_msg
        else:
            return None, warning_msg

    def make_summary_table(self, context, r, cleantarget):
        """Make a per-target summary table."""

        slib = cleantarget['sc_lib']
        rows = []
        row_names = ['Data Type', 'Image', 'Integrated Flux', 'SNR', 'SNR (N.F.)', 'RMS', 'RMS (N.F.)', 'Beam']

        def fm_sc_success(success):
            if success:
                return '<a style="color:blue">Yes</a>'
            else:
                return '<a style="color:red">No</a>'

        def fm_reason(slib):
            rkey = 'Stop_Reason'
            if rkey not in slib:
                return 'Estimated Selfcal S/N too low for solint'
            else:
                return slib[rkey]

        def fm_solint(slib):
            if slib['final_solint'] in [None, 'None']:
                return '-'
            else:
                return slib['final_solint']

        def fm_values(row_values, v1, v2):
            if v1 == -99.:
                row_values[0] = '-'
                row_values[2] = '-'
            if v2 == -99.:
                row_values[1] = '-'
                row_values[2] = '-'
            return row_values

        desc_args = {'success': fm_sc_success(slib['SC_success']),
                     'reason': fm_reason(slib),
                     'finalsolint': fm_solint(slib)}
        summary_desc = ('<ul style="list-style-type:none;">'
                        '<li>Selfcal Success: {success}</li>'
                        '<li>Stop Reason: {reason}</li>'
                        '<li>Final Successful solint: {finalsolint}</li>'
                        '</ul>'.format(**desc_args))
        summary_desc = f'<div style="text-align:left">{summary_desc}</div>'

        for row_name in row_names:
            if row_name == 'Data Type':
                row_values = ['Initial', 'Final', 'Brightness Dist. / Ratio']
            if row_name == 'Image':
                summary_plots, noisehist_plot = display.SelfcalSummary(context, r, cleantarget).plot()
                row_values = plots_to_html(
                    summary_plots[0:2] + [noisehist_plot],
                    report_dir=context.report_dir, title='Initial/Final Image Comparison')
            if row_name == 'Integrated Flux':
                row_values = [
                    '{:0.3f} &#177 {:0.3f} mJy'.format(slib['intflux_orig'] * 1e3, slib['e_intflux_orig'] * 1e3),
                    '{:0.3f} &#177 {:0.3f} mJy'.format(slib['intflux_final'] * 1e3, slib['e_intflux_final'] * 1e3)] + \
                    ['{:0.3f}'.format(slib['intflux_final']/slib['intflux_orig'])]
                row_values = fm_values(row_values, slib['intflux_orig'], slib['intflux_final'])

            if row_name == 'SNR':
                row_values = ['{:0.3f}'.format(slib['SNR_orig']),
                              '{:0.3f}'.format(slib['SNR_final'])] +\
                    ['{:0.3f}'.format(slib['SNR_final']/slib['SNR_orig'])]
                row_values = fm_values(row_values, slib['SNR_orig'], slib['SNR_final'])

            if row_name == 'SNR (N.F.)':
                row_values = ['{:0.3f}'.format(slib['SNR_NF_orig']),
                              '{:0.3f}'.format(slib['SNR_NF_final'])] +\
                    ['{:0.3f}'.format(slib['SNR_NF_final']/slib['SNR_NF_orig'])]
                row_values = fm_values(row_values, slib['SNR_NF_orig'], slib['SNR_NF_final'])

            if row_name == 'RMS':
                row_values = ['{:0.3f} mJy/bm'.format(slib['RMS_orig']*1e3),
                              '{:0.3f} mJy/bm'.format(slib['RMS_final']*1e3)] +\
                    ['{:0.3f}'.format(slib['RMS_final']/slib['RMS_orig'])]
                row_values = fm_values(row_values, slib['RMS_orig'], slib['RMS_final'])

            if row_name == 'RMS (N.F.)':
                row_values = ['{:0.3f} mJy/bm'.format(slib['RMS_NF_orig']*1e3),
                              '{:0.3f} mJy/bm'.format(slib['RMS_NF_final']*1e3)] +\
                    ['{:0.3f}'.format(slib['RMS_NF_final']/slib['RMS_NF_orig'])]
                row_values = fm_values(row_values, slib['RMS_NF_orig'], slib['RMS_NF_final'])

            if row_name == 'Beam':
                row_values = ['{:0.3f}"x{:0.3f}" {:0.3f} deg'.format(
                    slib['Beam_major_orig'],
                    slib['Beam_minor_orig'],
                    slib['Beam_PA_orig']),
                    '{:0.3f}"x{:0.3f}" {:0.3f} deg'.format(
                    slib['Beam_major_final'],
                    slib['Beam_minor_final'],
                    slib['Beam_PA_final'])] + ['{:0.3f}'.format(
                        slib['Beam_major_final'] * slib['Beam_minor_final'] / slib['Beam_major_orig'] / slib['Beam_minor_orig'])]

            rows.append([row_name]+row_values)

        rows.append(['Success / Final Solint']+[desc_args['success']+' / '+desc_args['finalsolint']]*3)
        rows.append(['Stop Reason']+[desc_args['reason']]*3)

        return utils.merge_td_rows(utils.merge_td_columns(rows, vertical_align=True))


def text_with_tooltip(text, tooltip):
    return f'<div data-toggle="tooltip" data-placement="bottom" title="{tooltip}">{text}</div>'


def fm_target(target):
    target_str = target['field']
    if target['is_repr_target']:
        target_str += '<br> (rep.source)'
    return target_str
