# Specification Document for the Function I/O Dumper Decorator and Helper Functions

This document will explain for the Decorator pipeline/infrastructure/utils/utils.py::function_io_dumper() and helper methods.

This decorator and helper methods provide a set of function and auxiliary tools for serializing the input and output (arguments and return value) of a function.
The decorator outputs the arguments and return value of a function in pickle and/or JSON format when the user-specified conditions are met.
This allows debugging of individual functions, regression testing, behavior analysis, and even automatic test template generation using actual behavior data.

## 1. Basic Functionality
- **I/O Serialization**:
  - The decorator captures the function’s inputs (arguments and keyword arguments), output (return value).
  - Data is serialized in two supported formats:
    - **Pickle**: Suitable for complete Python object serialization.
    - **JSON**: Provides human-readable output (with options to limit JSON depth to prevent excessively large dumps). It is not possible to serialize all objects into JSON format, so the exact representation is a JSON-like file.

- **Condition**:
  - A user-supplied condition determines whether serialization should work or not.
  - The `condition` parameter can be specified either as a **callable** or as a **dict**:
    - **Callable Condition:**
      If a callable is provided, it is invoked with the positional arguments (`args`) and keyword arguments (`kwargs`) of the function call. The callable must return `True` if serialization should occur, or `False` otherwise.

      **Example:**
        ```python
        def my_condition(args, kwargs) -> bool:
            # Serialize only if the keyword argument 'spw' is 10 or True.
            return kwargs.get("spw") in (10, 20)
        ```
    - **Dictionary Condition:**
      If a dictionary is provided, the decorator checks that for each key in the dictionary, the corresponding keyword argument has a matching value. Serialization occurs only if all key-value pairs in the dictionary match the keyword arguments.

      **Example:**
        ```python
        # This condition will cause serialization only when the keyword argument 'spw' equals 10.
        simple_condition = {'spw': 10}
        ```

## 2. Optional/Additional Functionality
- **Error Handling**:
  - If serialization (or condition evaluation) fails, the decorator logs the error (or warning) but does not affect the primary function execution.

- **JSON Depth Control**:
  - A parameter (`json_max_depth`) allows users to limit the nested levels in the JSON output to prevent huge or recursive dumps.

- **File Naming and Storage**:
  - Unique file names are generated based on the function name and timestamp to avoid overwriting existing files.

## 3. Use Cases

This decorator is designed to address a wide variety of scenarios:

- **Debugging and Issue Reproduction**:
  - Log detailed state information (arguments, outputs, exceptions) when certain conditions are met, aiding in diagnosing problems during development.
  - By using the dumped arguments and return values, the behavior of a particular function is reproduced and verified individually.
  - Help development and debug rapidly. For example, when a debugging of the weblog would normally require regenerating all PNG files per one test run, however, it can be regenerated for a limited number of PNG files by the execution of the individual function which has been debugging, with dumped files.

    ---
    **Practical Example**: regenerating a part of weblog faster

    First, decorate update_mako_context() of a Renderer class. For example, the following code is for imaging of SingleDish (stage 13). When it run, the decorator serializes three files: ctx.pickle, context.pickle, and results.pickle into the directory  'update_mako_context.[TimeStamp]' named as the function name.

    ```python
    class T2_4MDetailsSingleDishImagingRenderer(basetemplates.T2_4MDetailsDefaultRenderer):
        ...
        @function_io_dumper()
        def update_mako_context(self, ctx, context, results):
    ```
    Next, disable the decorator (to avoid creating pickles during the re-run of the decorated step), and copy pickle files from dumped directory to the current, then run the code below in the working directory, then it regenerates PNG images of the stage 13 only:
    ```python
    import os
    import pickle
    from pipeline.hsd.tasks.imaging.renderer import T2_4MDetailsSingleDishImagingRenderer

    pickle_path = '<path_to_pickles>'
    with open(os.path.join(pickle_path, 'ctx.pickle'), 'rb') as f:
        ctx = pickle.load(f)
    with open(os.path.join(pickle_path, 'context.pickle'), 'rb') as f:
          context = pickle.load(f)
    with open(os.path.join(pickle_path, 'results.pickle'), 'rb') as f:
          context = results.load(f)
    render = T2_4MDetailsSingleDishImagingRenderer()
    render.update_mako_context(ctx, context, results)
    ```

- **Use pickles as input data of a unit test**:

  For example, decorate hsd/tasks/importdata/reader.py::merge_flagcmd() and execute hsd_importdata,
  then it will output pickle files of argument objects and returning object into merge_flagcmd* directory in current (working) directory.
  We use the pickle file as expected input/output for a unit test.
  This sample velow uses a pickle file for the input argument, but basically input parameters should be specified and used for unit testing.

  ```python
  import os
  import pickle
  import unittest
  from deepdiff.diff import DeepDiff

  from pipeline.hsd.tasks.importdata.reader import merge_flagcmd

  def load_pickle(file_path):
      fname = '.'.join(os.path.basename(file_path).split(".")[0:-1])
      with open(file_path, "rb") as f:
          return fname, pickle.load(f)

  class TestHsdImportData(unittest.TestCase):

      def test_merge_flagcmd(self):
          basepath = "merge_flagcmd.expected/"

          # load input data and expected result
          _, commands = load_pickle(basepath + 'commands.pickle')
          result = merge_flagcmd(commands)

          # load expected result
          objname, expected = load_pickle(basepath + 'merge_flagcmd.expected.result.pickle')

          # compare results
          diff = DeepDiff(result, expected[objname], ignore_order=True)
          self.assertDictEqual(diff, {}, f"Result is different:\n{result}")

  if __name__ == "__main__":
      unittest.main()
  ```


- **Regression Testing Automation**:
  - Automatically capture function inputs and outputs during execution. Later, these dumps can be used to generate test cases or compare against new code versions.

- **Dynamic Decoration for Temporary Logging**:
  - By helper function, we can apply the decorator at runtime to a function without modifying its source code. This is useful for on-demand logging or debugging sessions.

## 4. Operating Specifications

- **Execution Flow**:
  1. When the decorated function is called, the decorator first evaluates the supplied `condition` using the function’s arguments.
  2. If the condition is met (i.e. returns `True` for a callable or matches the provided dictionary) or it is not specified, the decorator serializes the available arguments and the return value into the specified formats (Pickle and/or JSON).

- **Error Handling**:
  - If the condition evaluation raises an exception (in the case of a callable), a warning is logged and serialization is skipped.
  - Any errors during serialization (e.g., file write failures) are logged without impacting the function’s return value.

## 5. Interface Specifications

### 5.1 Main Decorator: `function_io_dumper`

- **Parameters:**
  - `to_pickle: bool`
    Enable/disable Pickle serialization.
  - `to_json: bool`
    Enable/disable JSON serialization.
  - `json_max_depth: int`
    Limit the depth of JSON serialization (optional, for controlling output size).
  - `condition: Callable[[tuple[Any, ...], dict[str, Any]], bool] | dict[str, Any] | None`
    A condition that determines whether serialization should occur. It can be specified as either:
    - A callable with the signature `Callable[[tuple[Any, ...], dict[str, Any]], bool]`, or
    - A dictionary for simple equality checking (e.g., `{'spw': 10}`).
  - `timestamp: bool`
    When `True`, include a timestamp in the serialized data and file names.

- **Return Value:**
  - Returns a decorated function that retains the original function’s signature.

- **Usage Example:**
  ```python
  # Using a callable condition:
  def my_condition(args, kwargs) -> bool:
      return kwargs.get("spw") in (10, True)

  @function_io_dumper(to_pickle=True, to_json=True, condition=my_condition, timestamp=True)
  def my_function(x: int, spw: bool = False) -> int:
      return x * 2
  ```

  ```python
  # Using a dictionary condition:
  simple_condition = {'spw': 10}

  @function_io_dumper(to_pickle=True, to_json=True, condition=simple_condition, timestamp=True)
  def my_function(x: int, spw: bool = False) -> int:
      return x * 2
  ```

## 6. Helper Function Specifications and Use Cases

### 6.1 Dynamic Decoration Helper: `decorate_io_dumper`

**Purpose:**

The `decorate_io_dumper` function dynamically applies the `function_io_dumper` decorator to methods of a specified class. This enables conditional input/output serialization of selected functions within a class without modifying their source code.

**Parameters:**

- **`cls: object`**
  The class whose methods should be decorated with `function_io_dumper`.
- **`functions: list[str] | None` (optional)**
  A list of function names to be decorated.
  - If specified, only the listed functions will be decorated.
  - If left empty (`[]`), all methods of the class will be decorated.
- **`*args: Any`**, **`**kwargs: Any`**
  - Other parameters corresponding to `function_io_dumper` (e.g., `to_pickle`, `to_json`, `json_max_depth`, `condition`, `timestamp`).

**Usage Example:**

```python
import pipeline.infrastructure.utils.utils as ut

ut.decorate_io_dumper(SDInspection, ['execute'])

...
hsd_importdata()  # -> dump args of SDInspection.execute()
```
