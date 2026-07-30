<%inherit file="t2-4m_details-base.mako"/>

<%block name="title">Find Regions of Interest</%block>

<p>This task quickly searches the selected science field/SPW combinations for candidate spectral-line regions of interest. For each combination, the data are first imaged using a lightweight, nearest-neighbor-gridded coarse dirty cube. The task then constructs a joint evidence spectrum from multiple independent methods of spectral extraction, estimates the characteristic line width, convolves the evidence spectrum with kernels spanning that width, and applies positive and negative detection thresholds of +5&sigma; and -7&sigma;, respectively. The stage pickle file contains the complete candidate-line dictionary used by this task. Candidate line and continuum frequency ranges are written to <code>ROI.dat</code> and <code>ROIcont.dat</code>; the summary and evidence plots below provide a field/SPW-level view of the results.</p>

<h2>Summary</h2>
<table class="table table-bordered table-striped">
  <thead>
    <tr>
      <th>Field</th>
      <th>Selected / Successful / Failed Science SPWs</th>
      <th>SPWs with Line ROI / Continuum Ranges</th>
    </tr>
  </thead>
  <tbody>
  % for row in summary_rows:
    <tr>
      <td>${row.source}</td>
      <td>${row.spw_summary}</td>
      <td>${row.roi_summary}</td>
    </tr>
  % endfor
  </tbody>
</table>

% if errors:
<div class="alert alert-danger">
  <p>hif_findroi reported errors:</p>
  <ul>
  % for error in errors:
    <li>${error}</li>
  % endfor
  </ul>
</div>
% endif

<h2>Evidence Spectra and Detected ROI</h2>
% if plot_message:
<p>${plot_message}</p>
% elif plot_links:
<table class="table table-bordered table-striped">
  <thead>
    <tr>
      <th>Field</th>
      <th>SPW</th>
      <th>Evidence Spectrum</th>
      <th>Positive ROI Ranges</th>
    </tr>
  </thead>
  <tbody>
  % for group in plot_groups:
    % for row_index, plot in enumerate(group.plots):
      <tr>
      % if row_index == 0:
        <td rowspan="${len(group.plots)}">${group.field}</td>
      % endif
        <td>${plot.spw}</td>
        <td>
        % if plot.href:
          <a href="${plot.href}"
             data-fancybox="findroi_evidence"
             data-caption="${plot.field} SPW ${plot.spw} evidence spectrum">
          <img class="lazyload img-responsive"
               data-src="${plot.thumbnail}"
               alt="${plot.field} SPW ${plot.spw} evidence spectrum">
          </a>
        % elif plot.evidence_status == 'evidence_plot_failed':
          Evidence spectrum plotting failed; spectrum data is available.
        % elif plot.evidence_status == 'no_valid_source_spw':
          No valid field/SPW combination; no spectrum was available to plot.
        % else:
          No evidence spectrum was available for this field/SPW.
        % endif
        </td>
        <td>
        % if plot.positive_roi_ranges:
          % for roi_range in plot.positive_roi_ranges:
            ${roi_range}<br>
          % endfor
        % else:
          No ROI.dat entry
        % endif
        </td>
      </tr>
    % endfor
  % endfor
  </tbody>
</table>
% else:
<p>No evidence spectra were written.</p>
% endif

<h2>Artifacts</h2>
% if artifact_links:
<ul>
% for artifact in artifact_links:
  <li><a href="${artifact.href}">${artifact.label}</a></li>
% endfor
</ul>
% else:
<p>No artifacts were written.</p>
% endif
