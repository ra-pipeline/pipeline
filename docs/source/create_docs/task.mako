${taskname}
==========================================

*${shortdescription}*

Parameters
----------

% for pp in pdict:
${pp.name} (${pp.type})
    ${pp.description}
    
    default: ${pp.defaultval}

% endfor

Examples
--------

${example}
