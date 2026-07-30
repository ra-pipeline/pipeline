<%inherit file="t2-4m_details-base.mako"/>

<%block name="title">Find Regions of Interest</%block>

<h2>Summary</h2>
<table class="table table-bordered table-striped">
  <tbody>
  % for row in summary_rows:
    <tr>
      <th>${row.metric}</th>
      <td>${row.value}</td>
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

<h2>Per-Source Evidence Spectra</h2>
% if plot_message:
<p>${plot_message}</p>
% elif plot_links:
<table class="table table-bordered table-striped">
  <thead>
    <tr>
      <th>Source</th>
      <th>Evidence Spectrum</th>
    </tr>
  </thead>
  <tbody>
  % for plot in plot_links:
    <tr>
      <td>${plot.source}</td>
      <td>
        <a href="${plot.href}"
           data-fancybox="findroi_evidence"
           data-caption="${plot.source} evidence spectrum">
          <img class="lazyload img-responsive"
               data-src="${plot.thumbnail}"
               alt="${plot.source} evidence spectrum">
        </a>
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
