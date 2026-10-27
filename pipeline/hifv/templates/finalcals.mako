<%!
rsc_path = ""
import os
import pipeline.infrastructure.renderer.htmlrenderer as hr
from pipeline.infrastructure.renderer import rendererutils
%>
<%inherit file="t2-4m_details-base.mako"/>

<%block name="title">Final calibration tables</%block>

<p>Make the final calibration tables. The bandpass and amplitude gain calibration solutions are produced using the CASA tasks <b>bandpass</b> and <b>gaincal</b>.
% if use_flux_cal:
    The standard pipeline processing applies solution normalization disabled, relying on a standard flux density calibrator to set the flux density scale.
% else:
    <b>Note:</b> Solution normalization has been applied to the amplitude gain calibration solutions (solnorm=True, normtype='median'). This mode is used for observations lacking a standard flux density calibrator. <b>When used in conjunction with proper prior calibrations (gain curves and switched power/requantizer gains),</b> this results in visibility data scaled to approximate Janskys without requiring a flux calibrator reference.
% endif
</p>

% for ms in summary_plots:
    <h4>Plots: <br> <a class="replace"
           href="${rendererutils.get_relative_url(pcontext.report_dir, dirname, delay_subpages[ms])}">Final delay plots </a> |
        <a class="replace"
           href="${rendererutils.get_relative_url(pcontext.report_dir, dirname, phasegain_subpages[ms])}">BP initial gain phase </a> |
        <a class="replace"
           href="${rendererutils.get_relative_url(pcontext.report_dir, dirname, bpsolamp_subpages[ms])}">BP Amp solution </a> |
        <a class="replace"
           href="${rendererutils.get_relative_url(pcontext.report_dir, dirname, bpsolphase_subpages[ms])}">BP Phase solution </a> |
        <a class="replace"
           href="${rendererutils.get_relative_url(pcontext.report_dir, dirname, bpsolphaseshort_subpages[ms])}">Phase (short) gain solution</a> |
        <a class="replace"
           href="${rendererutils.get_relative_url(pcontext.report_dir, dirname, finalamptimecal_subpages[ms])}">Final amp time cal </a> |
        <a class="replace"
           href="${rendererutils.get_relative_url(pcontext.report_dir, dirname, finalampfreqcal_subpages[ms])}">Final amp freq cal </a> |
        <a class="replace"
           href="${rendererutils.get_relative_url(pcontext.report_dir, dirname, finalphasegaincal_subpages[ms])}">Final phase gain cal </a>
    </h4>
%endfor
