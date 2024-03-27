${name}
${"="*len(name)}

% if description: 
Task description
-----------------
${description}
% endif

% if parameters: 
Parameter List 
--------------
.. list-table::
    :widths: 25 50
    :header-rows: 1
    :class: longtable

    * - parameter name
      - description
% for parameter in parameters: 
    * - ${parameter.strip()}
      - | ${parameters[parameter].split("\n")[0].strip()}
    % for i, line in enumerate(parameters[parameter].split("\n")[1:]):
      % if i == 35 and line: 
    * - 
      - | ${line.strip()}
      % elif line:
        | ${line.strip()}
      % endif
    % endfor
% endfor 
% endif


% if examples:
Examples 
--------
${examples}
% endif