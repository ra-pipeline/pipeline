<%inherit file="importdata.mako"/>

<%block name="title">ALMA Import Data</%block>

<%block name="addendum">

<h3>Intent Separation Angles</h3>
% if sepangle_table:
<p>The following table indicates the separation angles for the TARGET(s), PHASE and CHECK intents. These values are useful in understanding the accuracy of phase transfer and the usefulness of the check source. In an ideal situation the closer a PHASE intent to a TARGET the more optimal the phase transfer, while the CHECK intent is most useful if equidistant to the PHASE intent as the TARGET is, i.e. phase transfer occurs over a similar angular separation on the sky from the PHASE to the CHECK, as it does for the PHASE to the TARGET(s). TARGET to PHASE intent separation angles are shown for all TARGETS(s) if there are <=5, otherwise only the TARGETs with the min and max separation angles to the PHASE intent are shown. For mosaics a central target position is used. CHECK to PHASE intent separation angles are only indicated if the measurement set contains a CHECK intent.</p>
<table class="table table-bordered table-striped" summary="Target, Phase and Check intent separation angles">
        <thead>
	    <tr>
	        <th>Measurement Set</th>
                <th>Field</th>
                <th>Intent</th>
                <th>Field</th>
                <th>Intent</th>
                <th>Separation angle (deg)</th>
		<th>Separation angle plot
            </tr>
	</thead>
	<tbody>
    % for tr in sepangle_table:
        <tr>
        % for td in tr:
            ${td}
        % endfor
        </tr>
    %endfor
	</tbody>
</table>
% else:
    <p>No information available on intent separation angles.
% endif

<h3>Parallactic Angle Ranges</h3>
% if parang_ranges['intents_found']:
<p>The following table and plots show the ranges of parallactic angles of the polarization calibrator(s) per session.</p>
<table class="table table-bordered table-striped table-condensed"
       summary="Parallactic angle information">
    <thead>
        <tr>
            <th>Session</th>
            <th>Parallactic angle range</th>
            <th>Parallactic angle plot</th>
        </tr>
    </thead>
    <tbody>
        % for session_name in parang_ranges['sessions']:
            <tr>
                <td>${session_name}</td>
                <td>
                    ${'%.1f' % (parang_ranges['sessions'][session_name]['min_parang_range'])}&deg;
                    % if parang_ranges['sessions'][session_name]['min_parang_range'] >= minparang:
                        &ge;
                    % else:
                        &lt;
                    % endif
                    min. parallactic angle (${'%.1f' % (minparang)}&deg;)
                </td>
                <td>${parang_plots[session_name]['html']}</td>
            </tr>
        % endfor
    </tbody>
</table>
% else:
<p>No polarization intents found.</p>
% endif
</%block>
