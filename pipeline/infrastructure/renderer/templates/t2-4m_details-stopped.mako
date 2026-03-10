<%!
import pipeline.infrastructure.renderer.htmlrenderer as hr
%>
<%inherit file="t2-4m_details-base.mako"/>
<%block name="header" />

<%block name="title">${hr.get_task_description(result, pcontext, include_stage=False)}</%block>

<p>This task requested a clean stop and pipeline execution ended intentionally.</p>

% if message:
<h2>Stop message:</h2>
<pre>${message}</pre>
% endif

% if reason_code:
<h2>Stop reason code:</h2>
<pre>${reason_code}</pre>
% endif