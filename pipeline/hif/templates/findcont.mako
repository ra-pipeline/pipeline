<%inherit file="t2-4m_details-base.mako"/>
<%block name="header" />

<%block name="title">Find Continuum</%block>

<p>For each target and spectral window without a pre-existing continuum selection, this stage creates a dirty cube to search for spectral-line emission or absorption and identify channel ranges least likely to be contaminated. In the default path, the cube uses Briggs weighting with robust=1.0. Joint spatial masks are formed from moment images and refined using moment-difference contamination checks; spectra extracted from those masks are then analyzed for line features. Starting with the 2026 release, the target-imaging setup formerly produced by <code>hif_makeimlist</code> is generated internally by <code>hif_findcont</code>. Custom target-imaging setups can be supplied via the <code>target_list</code> parameter. Additionally, starting in the 2026 release, the default <code>hm_mode='coarse'</code> uses reduced pixels-per-beam sampling to optimize processing speed; use <code>hm_mode='normal'</code> to preserve the previous-cycle imaging behavior. The effective imaging parameters, including pixels per beam, are shown below.</p>

%if findcont_mode is None:
    <div class="alert alert-info">
        hif_findcont imaging mode: NOT AVAILABLE. The imaging mode is not recorded in this result.
    </div>
%elif not imaging_performed:
    <div class="alert alert-info">
        hif_findcont imaging mode: ${findcont_mode.upper()} (hm_mode='${findcont_mode}'). ${imaging_skip_reason}
    </div>
%elif findcont_mode == 'normal':
    <div class="alert alert-info">
        hif_findcont imaging mode: NORMAL (hm_mode='normal')
    </div>
%else:
    <div class="alert alert-info">
        hif_findcont imaging mode: COARSE (hm_mode='coarse')
    </div>
%endif

%if imaging_summary:
    <div class="table-responsive">
    <table class="table table-bordered table-striped table-condensed">
        <thead>
            <tr>
                <th>Field</th>
                <th>Spw</th>
                <th>Data type</th>
                <th>Phase center</th>
                <th>Pixels per beam</th>
                <th>Cell</th>
                <th>Image size</th>
                <th>Weighting</th>
                <th>Robust</th>
                <th>UV taper</th>
                <th>mosweight</th>
                <th>perchanweightdensity</th>
                <th>nbins</th>
            </tr>
        </thead>
        <tbody>
        %for row in imaging_summary:
            <tr>
                <td>${row.field}</td>
                <td>${row.spw}</td>
                <td>${row.datatype}</td>
                <td>${row.phasecenter}</td>
                <td>${row.ppb}</td>
                <td>${row.cell}</td>
                <td>${row.imsize}</td>
                <td>${row.weighting}</td>
                <td>${row.robust}</td>
                <td>${row.uvtaper}</td>
                <td>${row.mosweight}</td>
                <td>${row.perchanweightdensity}</td>
                <td>${row.nbins}</td>
            </tr>
        %endfor
        </tbody>
    </table>
    </div>
%endif

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
