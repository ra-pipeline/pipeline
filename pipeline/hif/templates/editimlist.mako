
<%!
rsc_path = "../"
import os
import pipeline.infrastructure.renderer.htmlrenderer as hr
from pipeline.infrastructure.renderer.rendererutils import get_multiple_line_string

%>
<%inherit file="t2-4m_details-base.mako"/>

<%block name="header" />

<%block name="title">Edit image list</%block>

%if vlass_flagsummary_plots_html is not None:
    <h2>VLASS Flagging Summary</h2>
    ${vlass_flagsummary_plots_html}
%endif

<h2>Image list settings</h2>

<%
r=result[0]
targets=result[0].targets
%>

%if not len(targets):
    <p>There are no clean targets.</p>
%else:
    <%
    # targets only contain 1 element for all existing workflows,  execept vlass-se-cube, 
    # where it can contain multiple elements, one for each plane.
    target = targets[0]
    fields = target['field'] if isinstance(target['field'], list) else [target['field']]
    n_field = sum(len(f.split(',')) for f in fields)    
    %>
    <div class="table-responsive">
    <table class="table table-bordered table-striped table-hover table-condensed">
        <tr>
            <td><strong>Imaging heuristics mode</strong></td>
            <td>${r.img_mode}</td>
        </tr>
        <tr>
            %if r.img_mode == 'VLASS-SE-CUBE':
                <td><strong>Image name (per plane)</strong></td>
                <td>${get_multiple_line_string([target['imagename'] for target in targets])}</td>                
            %else:
                <td><strong>Image name</strong></td>
                <td>${os.path.basename(target['imagename'])}</td>
            %endif
        </tr>
        <tr>
            <td><strong>Phase center</strong></td>
            <td>${target['phasecenter']}</td>
        </tr>
        <tr>
            <td><strong>Cell size</strong></td>
            <td>${target['cell']}</td>
        </tr>
        <tr>
            <td><strong>Image size</strong></td>
            <td>${target['imsize']}</td>
        </tr>
        <tr>
            %if r.img_mode == 'VLASS-SE-CUBE':
                <td><strong>spw (per plane)</strong></td>
                <td>${get_multiple_line_string([target['spw'] for target in targets])}</td>  
            %else:
                <td><strong>spw</strong></td>
                <td>${target['spw']}</td>
            %endif
        </tr>
        <tr>
            %if r.img_mode == 'VLASS-SE-CUBE':
                <td><strong>reffreq (per plane)</strong></td>
                <td>${get_multiple_line_string([target['reffreq'] for target in targets])}</td> 
            %else:
                <td><strong>reffreq</strong></td>
                <td>${target['reffreq']}</td>
            %endif
        </tr>
        <tr>
            %if r.img_mode == 'VLASS-SE-CUBE':
                <td><strong>flagpct (per plane)</strong></td>
                <td>${get_multiple_line_string([target['misc_vlass']['flagpct'] for target in targets], str_format='{:.2%}')}</td>
            %endif
        </tr>        
        <%
        if isinstance(target['mask'], list):
            mask='<br>'.join(target['mask'])
        else:
            mask=target['mask']
        %>
        <tr>
            <td><strong>mask (per iter)</strong></td>
            <td>${mask}</td>
        </tr>            
        <tr>
            <td><strong>Search buffer radius (arcsec)</strong></td>
            <td>${r.buffer_size_arcsec}</td>
        </tr>
        <tr>
            <td><strong>Number of fields</strong></td>
            <td>${n_field}</td>
        </tr>           
        %for key in target.keys():
            %if key in target.keys() and key not in ('imagename', 'spw', 'phasecenter', 'cell', 'imsize', 'field', 'heuristics', 'vis', 'is_per_eb', 'antenna', 'reffreq', 'mask', 'misc_vlass'):
                <tr>
                    <td><strong>${key}</strong></td>
                    <td>${target[key]}</td>
                </tr>
            %endif
        %endfor
    </table>
    </div>
%endif
