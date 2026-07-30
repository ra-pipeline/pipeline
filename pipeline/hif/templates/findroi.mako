<%inherit file="t2-4m_details-base.mako"/>

<%block name="title">Find Regions of Interest</%block>

<h2>Summary</h2>
<table class="table table-bordered table-striped">
  <thead>
    <tr>
      <th>Field</th>
      <th>Selected / Successful / Failed Science SPWs</th>
      <th>Products with Line ROI / Continuum Ranges</th>
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

<h2>Per-Field Evidence Spectra</h2>
% if plot_message:
<p>${plot_message}</p>
% elif plot_links:
<table class="table table-bordered table-striped">
  <thead>
    <tr>
      <th>Field</th>
      <th>SPW</th>
      <th>Evidence Spectrum</th>
    </tr>
  </thead>
  <tbody>
  % for plot in plot_links:
    <tr>
      <td>${plot.field}</td>
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
      % else:
        No evidence spectrum available
      % endif
      </td>
    </tr>
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
