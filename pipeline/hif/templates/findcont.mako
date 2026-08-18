<%inherit file="t2-4m_details-base.mako"/>
<%block name="header" />

<%block name="title">Find Continuum</%block>

<p>
For each target and spectral window without a pre-existing continuum selection,
this stage creates a dirty cube to search for spectral-line emission or
absorption and identify channel ranges least likely to be contaminated. In the
default path, the cube uses Briggs weighting with robust=1.0. Joint spatial
masks are formed from moment images and refined using moment-difference
contamination checks; spectra extracted from those masks are then analyzed for
line features. Starting with the 2026 release, the target-imaging setup
formerly produced by <code>hif_makeimlist</code> is generated internally by
<code>hif_findcont</code>. Custom target-imaging setups can be supplied via the
<code>target_list</code> parameter. Additionally, starting in the 2026 release,
a new hm_mode='coarse' option allows use of reduced pixels-per-beam sampling to
optimize processing speed; the default hm_mode='normal' preserves the
previous-cycle imaging behavior. The effective imaging parameters, including
pixels per beam, are shown below.</p>

% if not table_rows:
    <p>There are no continuum finding results.
% else:

    <%
    field_block_indices = []
    field = None
    for i, row in enumerate(raw_rows):
        if row.field != field:
            field_block_indices.append(i)
            field = row.field
    field_block_indices.append(len(raw_rows))
    %>

    %if len(field_block_indices) > 2:
        <h3>
        Fields
        </h3>
        <ul>
            %for i in field_block_indices[:-1]:
                <li>
                <a href="#field_block_${i}">${raw_rows[i].field}</a>
                </li>
            %endfor
        </ul>
    %endif

    <table class="table">
        <thead>
            <tr>
                <th rowspan="2">Field</th>
                <th rowspan="2">Spw</th>
                <th colspan="3">Continuum Frequency Range</th>
                <th rowspan="2">Status</th>
                <th rowspan="2">Mom diff SNR</th>
                <th rowspan="2">Average spectrum</th>
                <th rowspan="2">Joint mask</th>
            </tr>
            <tr>
                <th>Start</th>
                <th>End</th>
                <th>Frame</th>
            </tr>
        </thead>
        <tbody>
            <%
            field_block = 0
            %>
            %for i, tr in enumerate(table_rows):
                <tr>
                    %for j, td in enumerate(tr):
                        %if len(field_block_indices) > 2 and field_block_indices[field_block] == i and j == 0:
                            <%
                            td_jumptarget = td.replace('>', ' id="field_block_{:d}" class="jumptarget">'.format(field_block_indices[field_block]), 1)
                            field_block += 1
                            %>
                            ${td_jumptarget}
                        %else:
                            ${td}
                        %endif
                    %endfor
                </tr>
            %endfor
        </tbody>
    </table>
    <p>${contdat_path_link}
%endif
