<%!
import pipeline.infrastructure.renderer.htmlrenderer as hr
%>

<%inherit file="t2-4m_details-base.mako"/>

<%block name="title">Stage ${hr.get_stage_number(result)} Task Details</%block>

<h1>Stage ${hr.get_stage_number(result)}: ${hr.get_task_description(result, pcontext)}</h1>

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

<h2>Native findROI Plots</h2>
% if plot_links:
<table class="table table-bordered table-striped">
  <thead>
    <tr>
      <th>Source</th>
      <th>Plot</th>
      <th>Preview</th>
    </tr>
  </thead>
  <tbody>
  % for plot in plot_links:
    <tr>
      <td>${plot.source}</td>
      <td><a href="${plot.href}">${plot.label}</a></td>
      <td><a href="${plot.href}"><img src="${plot.href}" style="max-width: 360px;" alt="${plot.label} for ${plot.source}"></a></td>
    </tr>
  % endfor
  </tbody>
</table>
% else:
<p>No native findROI plots were written.</p>
% endif
