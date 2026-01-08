"""
recipe_conversion.py - convertor script from procedure xml file to Python code.

Please run the script with -h option to see complete usage.

Usage:

    python3 /path/to/recipe_converter.py [-a] [recipe] [script]

    or

    casa -c /path/to/recipe_converter.py [-a] [recipe] [script]

"""
import argparse
import functools
import glob
import logging
import os
import re
import string
import sys
import xml.dom.minidom as minidom


# logger
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
LOG = logging.getLogger(os.path.basename(__file__))

# type alias
DOM = minidom.Document | minidom.Element

# output directory
RECIPE_OUTPUT_DIR = 'python_recipes'

# special strings for recipe conversion
INDENT = '        '
TEMPLATE_TEXT = '''# General imports
import traceback

# Pipeline imports
import pipeline
from pipeline.infrastructure import casa_tools

# Make pipeline tasks available in local name space
pipeline.initcli(locals())

IMPORT_ONLY = 'Import only'


# Run the procedure
def ${func_name}(vislist, importonly=False, interactive=True):
    echo_to_screen = interactive
    casa_tools.post_to_log("Beginning pipeline run ...")

    try:
        # Initialize the pipeline
        h_init(${init_args})

${procedure}

    except Exception as e:
        if str(e) == IMPORT_ONLY:
            casa_tools.post_to_log("Exiting after import step ...", echo_to_screen=echo_to_screen)
        else:
            casa_tools.post_to_log("Error in procedure execution ...", echo_to_screen=echo_to_screen)
            errstr = traceback.format_exc()
            casa_tools.post_to_log(errstr, echo_to_screen=echo_to_screen)

    finally:
        # Save the results to the context
        h_save()

        casa_tools.post_to_log("Terminating procedure execution ...", echo_to_screen=echo_to_screen)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Process given set of data with ${func_name} recipe.')
    parser.add_argument('-i', '--import-only', action='store_true', dest='import_only', help='Exit after data import stage.')
    parser.add_argument('-q', '--quiet', action='store_true', dest='quiet', help='Do not output log to screen.')
    parser.add_argument('asdmlist', type=str, nargs='+', default=None, metavar='ASDM',
                        help='Input ASDM. Can provide multiple ASDMs separated by space.')
    args = parser.parse_args()
    asdmlist = [x.rstrip("/") for x in args.asdmlist]
    import_only = args.import_only
    interactive = not args.quiet

    ${func_name}(asdmlist, importonly=import_only, interactive=interactive)
'''


def get_recipe_dir() -> str:
    """Return absolute path to recipe directory.

    Basically, this returns the directory where this file is located.

    Returns:
        Absolute path to recipe directory.
    """
    recipe_dir, _ = os.path.split(__file__)
    recipe_dir = os.path.abspath(recipe_dir)
    LOG.debug(f'recipe directory is {recipe_dir}')
    return recipe_dir


def insert_pipeline_path(f):
    """Decorator to insert pipeline source directory to sys.path temporarily."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        pipeline_src = f'{get_recipe_dir()}/../../'
        sys.path.insert(0, pipeline_src)
        try:
            return f(*args, **kwargs)
        finally:
            sys.path.pop(0)
    return wrapper


def get_cli_dir(category: str) -> str:
    """Return path to cli directory for given category.

    Note that this function does not check the existence of
    cli directory.

    Args:
        category: Category name (h, hif, hifa, hifv, hsd, hsdn, etc.)

    Returns:
        Path to cli directory.
    """
    recipe_dir = get_recipe_dir().rstrip('/')
    pipeline_root_dir, _ = os.path.split(recipe_dir)
    cli_dir = os.path.join(pipeline_root_dir, f'{category}/cli')
    LOG.debug(f'cli directory is {cli_dir}')
    return cli_dir


def get_element(node: DOM, tag_name: str, expect_unique: bool = False) -> DOM | list[DOM]:
    """Get (list of) DOM object whose name matches tag_name.

    Args:
        node: Parent DOM object.
        tag_name: Tag name.
        expect_unique: Return single DOM object if True.
                       Defaults to False.

    Returns:
        List of DOM objects whose name is tag_name, or the first DOM object
        in the list if expect_unique is True.
    """
    elements = node.getElementsByTagName(tag_name)

    if expect_unique:
        assert len(elements) == 1
        return_value = elements[0]
    else:
        return_value = elements

    return return_value


def get_data(node: minidom.Element) -> str:
    """Extract data from DOM object.

    Return string 'data' if node represents <tag>data</tag>.

    Args:
        node: DOM object

    Returns:
        Data string.
    """
    return node.firstChild.data


def parse_parameter(node: DOM) -> tuple[str, str]:
    """Parse DOM object corresponding to Parameter tag in procedure xml file.

    Args:
        node: DOM object corresponding to Parameter tag

    Returns:
        Parameter name and its value.
    """
    key_element = get_element(node, 'Keyword', expect_unique=True)
    value_element = get_element(node, 'Value', expect_unique=True)
    return get_data(key_element), get_data(value_element)


@insert_pipeline_path
def parse_command(node: DOM) -> dict:
    """Parse DOM object into dictionary.

    The node parameter must be the object corresponding to
    ProcessingCommand tag in the procedure xml file

    Args:
        node: DOM object to be parsed.

    Returns:
        Dictionary representation of DOM object.

        Return value has the following structure:

            {task_name: {
                'comment': str,
                'parameter': dict
            }}

        where comment is a string taken from the first line of the
        docstring of pipeline task, parameter is a dictionary of
        the pair of parameter name and value specified in procedure
        xml file.

    """
    command_element = get_element(node, 'Command', expect_unique=True)
    command = get_data(command_element)

    parameter_set_element = get_element(node, 'ParameterSet', expect_unique=True)
    parameter_elements = get_element(parameter_set_element, 'Parameter')
    parameters = dict(parse_parameter(p) for p in parameter_elements)
    LOG.debug(f'command is {command}')
    task_property = {}
    LOG.debug(f'parameters are {parameters}')
    task_property['parameter'] = parameters

    import pipeline.cli as cli

    try:
        docstring = cli.get_pipeline_task_with_name(command).__doc__
    except Exception:
        docstring = ''

    comment = docstring.split('\n')[0]
    task_property['comment'] = comment

    return {command: task_property}


def parse(procedure_abs_path: str) -> tuple[str, list[dict]]:
    """Parse procedure xml file.

    Args:
        procedure_abs_path: Absolute path to the procedure xml file.

    Returns:
        Pipeline recipe name with the list of commands.
    """
    root_element = minidom.parse(procedure_abs_path)

    # ProcessingProcedure
    procedure_element = get_element(root_element, 'ProcessingProcedure', expect_unique=True)

    # ProcedureTitle - will be function name
    title_element = get_element(procedure_element, 'ProcedureTitle', expect_unique=True)
    recipe_name = get_data(title_element)

    LOG.debug(f'function name is {recipe_name}')

    # ProcessingCommand
    command_elements = get_element(procedure_element, 'ProcessingCommand')
    commands = [parse_command(e) for e in command_elements]
    LOG.debug(f'command list is:')
    for command in commands:
        LOG.debug(f'{command}')

    return recipe_name, commands


def get_comment(task_name: str, config: dict) -> str:
    """Generate comment for given task from the configuration.

    The function refers comment field of config. Multi-line comment
    is properly handled.

    Args:
        task_name: Pipeline task name.
        config: Pipeline task configuration.

    Returns:
        Comment for pipeline task. If task_name is 'breakpoint',
        the comment indicating breakpoint will be returned.
    """
    comment = config.get('comment', '')
    prefix = f'{INDENT}# '
    if task_name == 'breakpoint':
        comment = prefix + f' ---- {task_name} ----'
    elif comment:
        comment = comment.strip('\n')
        # handle multi-line comment
        comment = re.sub('\n *', f'\n{prefix}', comment)
        comment = prefix + comment + '\n'

    return comment


@insert_pipeline_path
def get_execution_command(task_name: str, config: dict) -> str:
    """Generate execution command from given task name and configuration.

    The config parameter should have at least two fields: parameter and
    parameter_types. The parameter field should be the dictionary with
    (param_name_str, param_value_str) pair while the parameter_types field
    should be the dictionary with (param_name_str, param_type_tuple) pair
    where param_type_tuple is (primary_type, subtypes) pair .

    Args:
        task_name: Pipeline task name.
        config: Pipeline task configuration.

    Returns:
        Task execution command string. If task_name is 'breakpoint',
        empty string will be returned.
    """
    parameter = config.get('parameter', '')

    # breakpoint
    if task_name == 'breakpoint':
        return ''

    args = ''
    if parameter:
        import pipeline.extern.XmlObjectifier as XmlObjectifier

        def construct_arg(key, value):
            cast_value = XmlObjectifier.castType(value)

            if isinstance(cast_value, str):
                arg = f'{key}=\'{value}\''
            else:
                arg = f'{key}={value}'
            return arg

        args += ', '.join([construct_arg(k, v) for k, v in parameter.items()])

    # special handling for importdata task
    is_importdata = 'importdata' in task_name
    if is_importdata:
        args = 'vis=vislist' + (f', {args}' if args else '')

    # construct function call
    command = f'{INDENT}{task_name}({args})'

    if is_importdata:
        command += '''

        if importonly:
            raise Exception(IMPORT_ONLY)'''

    return command


def c2p(command: dict) -> str:
    """Convert pipeline command dictionary into string.

    The command parameter should be the dictionary returned by
    parse_command.

    Args:
        command: Pipeline task and its custom parameters.

    Returns:
        Python code snippet invoking given pipeline task.
        The string will look like the following:

            # task shortdescription taken from the docstring of pipeline task
            taskname()

        or, if parameters are customized in the procedure xml file,

            # task shortdescription taken from the docstring of pipeline task
            taskname(custom_param=custom_value)

        Note that there will be some additional code for importdata stage.
    """
    LOG.debug(f'c2p: command is {list(command.keys())[0]}')
    assert len(command) == 1
    task_name, config = list(command.items())[0]
    procedure = get_comment(task_name, config)

    command = get_execution_command(task_name, config)
    procedure += command

    return procedure


def to_procedure(commands: list[dict]) -> str:
    """Convert list of commands to string that represents Python code snippet.

    Args:
        commands: List of pipeline tasks and their custom parameters.

    Returns:
        Python code snippet that executes pipeline tasks sequentially.
    """
    return '\n\n'.join([c2p(command) for command in commands])


@insert_pipeline_path
def export(recipe_name: str, commands: list[dict], script_name: str, plotlevel_summary: bool = False) -> None:
    """Export parsed information as a Python script.

    Args:
        recipe_name: Name of the function defined in the Python script.
        commands: List of pipeline tasks and their custom parameters.
        script_name: Output script name.
        plotlevel_summary: Set True to initialize pipeline with "summary" plotlevel.
    """
    template = string.Template(TEMPLATE_TEXT)
    procedure = to_procedure(commands)
    init_args = "plotlevel='summary'" if plotlevel_summary else ''

    from pipeline.infrastructure.executeppr import KNOWN_PROCESSING_INTENTS
    processing_intents = dict(
        (k, True) for k, v in KNOWN_PROCESSING_INTENTS.items()
        if recipe_name in v
    )
    if processing_intents:
        init_args = ', '.join([init_args, f'processing_intents={processing_intents}']).strip(', ')

    python_recipes_dir = 'python_recipes'
    os.makedirs(python_recipes_dir, exist_ok=True)

    with open(os.path.join(python_recipes_dir, script_name), 'w') as f:
        f.write(template.safe_substitute(
            func_name=recipe_name,
            procedure=procedure,
            init_args=init_args
        ))


def main(recipe_name: str, script_name: str, plotlevel_summary: bool = False) -> None:
    """Generate Python script from procedure xml file.

    Args:
        recipe_name: Recipe name. Will be translated into xml file name,
                           procedure_<recipe_name>.xml.
        script_name: Output script name.
        plotlevel_summary: Set True to initialize pipeline with "summary" plotlevel.

    Raises:
        FileNotFoundError: Procedure xml file does not exist.
    """
    procedure = f'procedure_{recipe_name}.xml'

    LOG.debug(f'__file__ is {__file__}')
    LOG.info(f'recipe is {recipe_name}')
    LOG.info(f'procedure is {procedure}')

    recipe_dir = get_recipe_dir()

    procedure_abs_path = os.path.join(recipe_dir, procedure)
    if not os.path.exists(procedure_abs_path):
        raise FileNotFoundError(f'Procedure "{procedure}" not found.')

    # parse procedure xml file
    func_name, commands = parse(procedure_abs_path)

    # export commands as Python script
    export(func_name, commands, script_name, plotlevel_summary)


def generate_all() -> None:
    """Generate recipe scripts from all procedure files in the recipe directory.

    Pipeline is initialized with plotlevel='summary' for the recipes listed in
    summary_plotlevel_recipes.
    """
    recipe_dir = get_recipe_dir()

    recipe_xml_files = glob.glob(f'{recipe_dir}/procedure_*.xml')
    summary_plotlevel_recipes = [
        'hifvcalvlass_compression',
        'hifvcalvlass',
        'hifv',
        'hifv_calimage_cont',
        'hifv_contimage',
        'vlassQLIP'
    ]

    for r in recipe_xml_files:
        xml_file = os.path.basename(r)
        LOG.debug(xml_file)
        recipe_name = re.sub(r'procedure_(.*).xml', r'\1', xml_file)
        script_name = f'{recipe_name}.py'
        LOG.info(f'Processing {recipe_name}...')
        plotlevel_summary = recipe_name in summary_plotlevel_recipes
        main(recipe_name, script_name, plotlevel_summary)
        LOG.info(f'Finished processing {recipe_name}.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Convert procedure xml file into Python script')
    parser.add_argument('-a', '--all', action='store_true', dest='generate_all', help='process all procedure files in the recipes directory. user-supplied recipe and script names will be omitted.')
    parser.add_argument('-d', '--debug', action='store_true', dest='debug', help='debug mode')
    parser.add_argument('-s', '--plotlevel-summary', action='store_true', dest='summary', help='set plotlevel summary')
    parser.add_argument('recipe', type=str, nargs='?', default='hsd_calimage',
                        help='recipe type. will be translated to xml file name, "procedure_<recipe>.xml"')
    parser.add_argument('script', type=str, nargs='?', default=None,
                        help='output script name. defaults to <recipe>.py')
    args = parser.parse_args()

    recipe_name = args.recipe
    script_name = args.script
    flag_generate_all = args.generate_all
    flag_debug = args.debug
    flag_summary = args.summary

    if flag_debug:
        LOG.info('running in debug mode...')
        LOG.setLevel(logging.DEBUG)

    LOG.debug(f'generate_all={flag_generate_all}')

    LOG.info(f"Scripts will be generated in '{RECIPE_OUTPUT_DIR}' directory.")

    if flag_generate_all:
        LOG.info('Generating recipe scripts for all procedure files.')
        generate_all()
    else:
        if script_name is None:
            script_name = f'{recipe_name}.py'

        main(recipe_name, script_name, flag_summary)
