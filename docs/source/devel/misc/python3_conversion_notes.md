# Python 3 conversion notes

This document provides notes on the conversion of the Pipeline code to become
Python 3 compatible.

Python 3 conversion is tracked in
[PIPE-10](https://open-jira.nrao.edu/browse/PIPE-10) and its sub-task tickets.

## Updating code with '2to3' tool

The '2to3' tool has a series of rules to evaluate and convert code to Python 3. 
Below is a summary of which rules have been applied, and which still need to be done.

Rules that do not require changes in PL code nor in external modules (guard
against regression):

```
apply, asserts, exitfunc, getcwdu, imports2, input, intern, itertools_imports,
nonzero, operator, paren, renames, sys_exc, throw, xreadlines
```

Rules that have been applied (guard against regression):

```
basestring, buffer, dict, except, exec, execfile, filter, funcattrs, future,
has_key, idioms, import, imports, isinstance, itertools, long, map, metaclass,
methodattrs, ne, next, numliterals, print, raise, raw_input, reduce, repr,
set_literal (optional), standarderror, tuple_params, types (after idioms),
unicode, urllib, ws_comma (optional), xrange, zip
```

## Examples best coding practices
Included below are a series of examples of best coding practices to use, to
ensure that the Pipeline stays Python 3 compatible.


### Print statements
Before:
```
print “bit of text”
```
After:
```
print(“bit of text”)
```

### 'has_key' method in dictionaries
Before:
```
if mydict.has_key(mykey):
```
After:
```
if mykey in mydict:
```

### Raising exceptions
Before:
```
raise Exception “Oh no!”
```
After:
```
raise Exception(“Oh no!”)
```

### Catching exceptions
Before:
```
except Exception, e:
```
After:
```
except Exception as e:
```

### Checking for type

Before:
```
if type(vis) is types.ListType:
```
After:
```
if isinstance(vis, list):
```

### Relative imports within package
Before:
```
import display
```
After:
```
from . import display
```

### Formatted strings
The following change is not necessary for Python 3 compatibility, 
but the "before" has been marked as deprecated in Python 3 and 
may be removed in the future.

Before:
```
“bit of %s” % “text”
```
After:
```
“bit of {}”.format(“text”)
```

### "reduce" builtin is deprecated
The built-in "reduce" is going away, but is available as part of the
functools in standard library in both Python 2 and 3.

Before:
```
num_mses = reduce(operator.add, [len(r.mses) for r in result])
```
After:
```
import functools
num_mses = functools.reduce(operator.add, [len(r.mses) for r in result])
```

### <> is deprecated, use !=
Before:
```
if a <> 1:
```
After:
```
if a != 1:
```

### Implicit tuple parameter unpacking is no longer supported
Before:
```
lambda (x, y): y - x
```
After:
```
lambda x_y: x_y[1] - x_y[0]
```

### map, filter, zip now return an iterable object, instead of a list
If the result from a call to map, filter, or zip is expected to be a list, then wrap the call in an explicit list
statement.

Before:
```
spwids = map(int, inputs['spw'].split(','))
return spwids[0]
```
After:
```
spwids = list(map(int, inputs['spw'].split(',')))
return spwids[0]
```
or
```
spwids = [int(x) for x in inputs['spw'].split(',')]
```


As a side-effect of this change, one can no longer use a call to 'map' (with/without assigning result to variable)
to run an implicit for loop. The loop has to be made explicit.

Before:
```
map(intent_intervaltree.remove, to_remove)
```
After:
```
for interval in to_remove:
    intent_intervaltree.remove(interval)
```
