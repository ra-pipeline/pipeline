<%!
import operator
import pipeline.infrastructure.renderer.htmlrenderer as hr
import pipeline.infrastructure.renderer.rendererutils as rendererutils

navbar_active='By Topic'

tablerow_css_classes = {'Error'      : 'error',
			'Warning'    : 'warning'}

def get_tablerow_class(row):
	return tablerow_css_classes.get(row.type, '')

def results_by_stage_number(d):
    all_results = []
    for v in d.values():
        all_results.extend(v)
    return sorted(all_results, key=operator.attrgetter('stage_number'))

%>
<%inherit file="base.mako"/>

<div class="page-header">
	<h1>${next.title()}<%block name="backbutton"><button class="btn btn-default pull-right" onClick="javascript:window.history.back();">Back</button></%block></h1>
</div>

% if run_status_alert is not None:
<div class="${run_status_alert['alert_class']}">
	<h4>${run_status_alert['title']}</h4>
	<p>${run_status_alert['message']}</p>
	% if run_status_alert.get('reason_code'):
	<p><strong>Reason code:</strong> ${run_status_alert['reason_code']}</p>
	% endif
</div>
% endif

% if active_conditions:
<h3>Active Conditions</h3>
<table class="table table-bordered table-striped table-condensed" summary="Active pipeline conditions for this run">
	<thead>
		<tr>
			<th>Code</th>
			<th>Severity</th>
			<th>Scope</th>
			<th>Message</th>
		</tr>
	</thead>
	<tbody>
	% for condition in active_conditions:
		<tr>
			<td>${condition.get('code', '')}</td>
			<td>${condition.get('severity', '')}</td>
			<td>${condition.get('scope', '')}</td>
			<td>${condition.get('message', '') or ''}</td>
		</tr>
	% endfor
	</tbody>
</table>
% endif

% if topic.results_by_type:
<table class="table">
	<thead>
		<tr>
			<th class="span9">Task</th>
			<th class="span2">QA Score</th>
			<th class="span1"></th>
		</tr>
	</thead>
	<tbody>
	% for results in results_by_stage_number(topic.results_by_type):
		<tr>
			<td><a href="t2-4m.html?sidebar=sidebar_stage${results.stage_number}">${hr.get_task_description(results, pcontext)}</a><span class="pull-right">${scores[results.stage_number].shortmsg}</span></td>
			<td><div class="progress" style="margin-bottom:0px;"><div class="progress-bar${rendererutils.get_bar_class(scores[results.stage_number])}" role="progressbar" style="width:${rendererutils.get_bar_width(scores[results.stage_number])}%;"><span class="text-center"></span></div></div></td>
			<td><span class="badge${rendererutils.get_badge_class(scores[results.stage_number])}">${rendererutils.format_score(scores[results.stage_number])}</span></td>
		</tr>
	% endfor
	</tbody>
</table>
% else:
<p>No tasks belong to this topic.</p>
% endif

<h3>Warnings and errors</h3>
% if tablerows:
<table class="table table-bordered table-striped table-condensed"
	   summary="Messages from tasks for this topic">
	<thead>
		<tr>
			<th>Stage</th>
			<th>Task</th>
			<th>Type</th>
			<th>Message</th>
		</tr>
	</thead>
	<tbody>
	% for row in tablerows:
		<tr class="${get_tablerow_class(row)}">
			<td><a href="t2-4m.html?sidebar=sidebar_stage${row.stage}${row.target}">${row.stage}</a></td>
			<td><a href="t2-4m.html?sidebar=sidebar_stage${row.stage}${row.target}">${row.task}</a></td>
			<td>${row.type}</td>
			<td>${row.message}</td>
		</tr>
	% endfor		
	</tbody>
</table>
% else:
<p>No warnings or errors were emitted for this topic.</p>
% endif

${next.body()}
