<%!
rsc_path = ""
import os
import pipeline.infrastructure.renderer.htmlrenderer as hr
%>

<%namespace name="base" file="t2-4m_details-base.mako"/>

<script>
    lazyload();
</script>

<style type="text/css">

.table {
  font-family: Arial, Helvetica, sans-serif;
  border-collapse: collapse;
  vertical-align: middle;
  text-align: center;
  float: left;
  margin: 0px 10px;
  width: auto;
}

.table td {
  vertical-align: middle;
  text-align: center;
  background-clip: padding-box;    
  min-width: 60px;     
}

.table th {
  font-weight: bold;
  vertical-align: middle;
  text-align: center;  
}

.table td:first-child {
  vertical-align: middle;
  text-align: center;       
}

.anchor { padding-top: 90px; }

img {
    height: auto;
    display: block;
    margin-left: auto;
    margin-right: auto;
}

</style>


<%
import numpy as np

def fm_band(band):
    return band.replace('_',' ')

def fm_target(target):
    return target.replace('_',' ') 

def fm_sc_success(success):
    if success:
        return '<a style="color:blue">Yes</a>'
    else:
        return '<a style="color:red">No</a>'

def fm_reason(slib):
    rkey='Stop_Reason'
    if rkey not in slib:
        return 'Estimated Selfcal S/N too low for solint'
    else:
        return slib[rkey]

vislist=slib['vislist']
%>

<h3>${fm_target(target)} ${fm_band(band)}</h3>

<h4>
  Passed: ${fm_sc_success(slib[vislist[-1]][solint]['Pass'])}
</h4>


<div class="table-responsive">
<table class="table table-bordered">
  <caption>Prior/Post Image Comparisons</caption>
  <tbody>
  % for tr in summary_tab:
    <tr>
    % for td in tr:
      ${td}
    % endfor
    </tr>
  %endfor
  </tbody>
</table>      
</div>    

<div class="table-responsive">
<table class="table table-bordered">
  <caption>Sol. Summary</caption>
  <tbody>
  % for tr in nsol_tab:
    <tr>
    % for td in tr:
      ${td}
    % endfor
    </tr>
  %endfor
  </tbody>
</table>      
</div>    


<%base:plot_group plot_dict="${phasefreq_plots}"
                                  url_fn="${lambda ms: 'noop'}">

        <%def name="title()">
        </%def>

        <%def name="preamble()">
        </%def>

        <%def name="mouseover(plot)">${plot.basename}</%def>

        <%def name="fancybox_caption(plot)">
          ${plot.y_axis} vs. ${plot.x_axis}
        </%def>

        <%def name="caption_title(plot)">
           ${plot.y_axis} vs. ${plot.x_axis}
        </%def>

</%base:plot_group>

<div class="row"></div>