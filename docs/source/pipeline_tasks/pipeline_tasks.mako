List of Heuristics Tasks (Pipeline ${plversion})
=================================================

% for category in pdict:
    
${task_groups[category]}
${"-"*len(task_groups[category])}
${len(pdict[category])} tasks available. 

.. list-table::
    :widths: 25 50
    :header-rows: 1

    * - task name
      - description
% for task in pdict[category]:
    * - :ref:`${task[0]}`
% if len(task[1].split("\n")) > 1:
      - | ${task[1].split("\n")[0].strip()}
    % for line in task[1].split("\n")[1:]:
      % if line:
        | ${line.strip()}
      % endif
    % endfor
% else: 
      - ${task[1]}
% endif 
% endfor 

.. toctree::
   :maxdepth: 1
   :glob:

   ${category}/*

% endfor 


