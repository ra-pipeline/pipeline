<%!
rsc_path = ""
%>

<%inherit file="t2-4m_details-base.mako"/>

<%block name="title">Transform Measurement Set</%block>

<h2>Results</h2>

% if not table_rows:
    <p>No transformed measurement sets were created.</p>
% else:
    <h4>Transformed Measurement Sets</h4>

    <p>The following transformed measurement sets were created</p>

    <table class="table table-bordered table-striped" summary="Transformed measurement sets">
        <caption>Transformed measurement sets</caption>
        <thead>
           <tr>
            <th scope="col">Original Measurement Set</th>
            <th scope="col">Transformed Measurement Set</th>
          </tr>
        </thead>
        <tbody>
        % for tr in table_rows:
        <tr>
            % for td in tr:
                ${td}
            % endfor
        </tr>
        % endfor
        </tbody>
    </table>
% endif
