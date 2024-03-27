# Started from jmaster's create_docs.py.
# Modified by kberry to work post-removal of the task interface.

import argparse
import inspect
import os
import sys
from collections import namedtuple
from typing import Dict, Tuple

from mako.template import Template

Task = namedtuple('Task', 'name short description parameters examples')

# Task groups and their names
task_groups = {"h": "Generic",
               "hif": "Interferometry Generic",
               "hifa": "Interferometry ALMA",
               "hifas": "Interferometry ALMA SRDP",
               "hifv": "Interferometry VLA",
               "hsd": "Single Dish",
               "hsdn": "Nobeyama"}


def check_dirs(filename: str):
    """Pre-check/create the ancestry directories of a given file path."""
    filedir = os.path.dirname(filename)
    if not os.path.exists(filedir):
        os.makedirs(filedir)


def write_landing_page(pdict, rst_file="taskdocs.rst",
                       mako_template="pipeline_tasks.mako", outdir=None):
    """Creates reST file for the "landing page" for the tasks."""
    script_path = os.path.dirname(os.path.realpath(__file__))
    task_template = Template(filename=os.path.join(script_path, mako_template))

    # Write the information into a rst file that can be rendered by sphinx as html/pdf/etc.

    output_dir = script_path if outdir is None else outdir
    rst_file_full_path = os.path.join(output_dir, rst_file)
    check_dirs(rst_file_full_path)
    with open(rst_file_full_path, 'w') as fd:
        rst_text = task_template.render(plversion=2023, pdict=pdict, task_groups=task_groups)
        fd.writelines(rst_text)


def write_task_pages(pdict, outdir=None):
    """Creates reST files for each task.
    """
    script_path = os.path.dirname(os.path.realpath(__file__))
    task_template = Template(filename=os.path.join(script_path, 'individual_task.mako'))

    output_dir = script_path if outdir is None else outdir
    for entry in pdict:
        for task in pdict[entry]:
            rst_file = "{}/{}_task.rst".format(entry, task.name)
            rst_file_full_path = os.path.join(output_dir, rst_file)
            check_dirs(rst_file_full_path)
            with open(rst_file_full_path, 'w') as fd:
                rst_text = task_template.render(category=entry, name=task.name, description=task.description,
                                                parameters=task.parameters, examples=task.examples)
                fd.writelines(rst_text)


def _parse_description(description_section: str) -> Tuple[str, str]:
    """ Parse the short and long descriptions from the docstring """
    short_description = ""
    long_description = ""

    index = 0
    lines = description_section.split("\n")
    if len(lines) > 1:
        short_description = lines[1].split("----")
        if len(short_description) > 1:
            if short_description[1] != '':
                short_description = short_description[1]
                index = 2
            else:
                # hifa_wvrgcal and hifa_wvrgcal flag have longer short
                # descriptions that extend onto the next line
                short_description = lines[2].strip() + "\n" + lines[3].strip()
                index = 4

    long_description = description_section

    # Better format long description:
    long_split = long_description.split('\n')[index:]
    long_split_stripped = [line[4:] for line in long_split]
    long_description = "\n".join(long_split_stripped).strip("\n")

    return short_description, long_description


def _parse_parameters(parameters_section: str) -> Dict[str, str]:
    """
    Parse the parameters section of the docstring and return a
    dict of {'parameter': 'description'}.
    """
    parms_split = parameters_section.split("\n")

    parameters_dict = {}  # format is {'parameter': 'description'}
    current_parm_desc = None
    parameter_name = ""
    for line in parms_split:
        if len(line) > 4:
            if not line[4].isspace():
                if current_parm_desc is not None:
                    parameters_dict[parameter_name] = current_parm_desc
                parameter_name = line.split()[0]
                index = line.find(parameter_name)
                description_line_one = line[index+len(parameter_name):].strip()
                current_parm_desc = description_line_one
            else:
                if current_parm_desc is not None:
                    new_line = line.strip()
                    # Don't add totally empty lines:
                    if not new_line.isspace():
                        current_parm_desc = current_parm_desc + " " + new_line + "\n"

    # Add the information for the last parameter
    if parameter_name != "" and current_parm_desc is not None:
        parameters_dict[parameter_name] = current_parm_desc

    return parameters_dict


def _parse_examples(examples_section: str) -> str:
    """ Parse examples section from the docstring """
    examples = examples_section.strip("\n")

    # There are 4 spaces before the text on each line begins for the
    # examples and there can be leading and trailing lines with only
    # newlines, which are stripped out.
    examples = "\n".join([line[4:] for line in examples.split("\n")]).strip("\n")
    return examples


def docstring_parse(docstring: str) -> Tuple[str, str, str, dict]:
    """ Parses the docstring for each pipeline task.

        This will parse the non-standard docstring format currently used
        for pipeline tasks and return the short description, the long
        description, the examples, and a dictionary of
        {'parameter name' : 'parameter description'}

        If parsing something fails, it will continue and a warning message will
        be printed to stdout.

        Example of the non-standard docstring-format that this will parse:

            h_example_task ---- An example task short description

            h_example task is an example task that serves as an example of
            the non-standard docstring format parsed by this script, and this
            is the long description.

            --------- parameter descriptions ---------------------------------------------

            filename            A filename that could be set as input if this were a real
                                task.
                                example: filename='filename.txt'
            optional            An optional parameter that can be set. This does nothing.
                                example: optional=True

            --------- examples -----------------------------------------------------------

            1. Run the example task

            >>> h_example_task()

            2. Run the example task with the ``optional`` parameter set

            >>> h_example_task(optional=True)

            --------- issues -----------------------------------------------------------

            This is an example task, but if it had any known issues, they would be here.
    """
    # Strings that delimit the different sections of the pipeline task docstrings:
    parameter_delimiter = "--------- parameter descriptions ---------------------------------------------"
    examples_delimiter = "--------- examples -----------------------------------------------------------"
    issues_delimiter = "--------- issues -----------------------------------------------------------"

    try:
        description_section, rest_of_docstring = docstring.split(parameter_delimiter)

        short_description, long_description = _parse_description(description_section)

        parameters_section, examples_section = rest_of_docstring.split(examples_delimiter)

        parameters_dict = _parse_parameters(parameters_section)

        # The "issues" section is excluded from the output docs and is not
        # always present. If present, it will always be the last
        # section.
        if issues_delimiter in examples_section:
            temp_split = examples_section.split(issues_delimiter)
            examples_section = temp_split[0]

        examples = _parse_examples(examples_section)

    except Exception as e:
        print("Failed to parse docstring. Error: {}".format(e))
        print("Failing docstring: {}".format(docstring))

    return short_description, long_description, examples, parameters_dict


def create_docs(outdir=None, srcdir=None, missing_report=False, tasks_to_exclude=None):
    """
    Walks through the pipeline and creates reST documentation for each pipeline task, including an
    overall landing page.

    Optionally generates and outputs lists of tasks with missing examples, parameters, and
    longer descriptions.
    """
    if srcdir is not None and os.path.exists(srcdir):
        sys.path.insert(0, srcdir)
    try:
        import pipeline.cli
    except ImportError:
        raise ImportError("Can not import the Pipeline package to inspect the task docs.")

    # Dict which stores { 'task group' : [list of Tasks in that group]}
    tasks_by_group = {"h": [],
                      "hif": [],
                      "hifa": [],
                      "hifas": [],
                      "hifv": [],
                      "hsd": [],
                      "hsdn": []}

    if not tasks_to_exclude:
        # Tasks to exclude from the reference manual
        # hifv tasks confirmed by John Tobin via email 20230911
        # h tasks requested by Remy via email 20230921
        tasks_to_exclude = ['h_applycal',
                            'h_export_calstate',
                            'h_exportdata',
                            'h_import_calstate',
                            'h_importdata',
                            'h_mssplit',
                            'h_restoredata',
                            'h_show_calstate',
                            'hifv_targetflag',
                            'hifv_gaincurves',
                            'hifv_opcal',
                            'hifv_rqcal',
                            'hifv_swpowcal',
                            'hifv_tecmaps']

    # Lists of cli PL tasks that are missing various pieces:
    missing_example = []
    missing_description = []
    missing_parameters = []

    # Walk through the whole pipeline and generate documentation for cli pipeline tasks
    for group_name, obj in inspect.getmembers(pipeline):
        if group_name in task_groups.keys():
            for folder_name, sub_obj in inspect.getmembers(obj):
                if 'cli' in folder_name:
                    for task_name, task_func in inspect.getmembers(sub_obj):
                        if '__' not in task_name and task_name is not None and task_name[0] == 'h':
                            docstring = task_func.__doc__
                            short_description, long_description, examples, parameters = docstring_parse(docstring)

                            if missing_report:
                                if not examples:
                                    missing_example.append(task_name)
                                if not long_description:
                                    missing_description.append(task_name)
                                if not parameters:
                                    missing_parameters.append(task_name)

                            if task_name not in tasks_to_exclude:
                                tasks_by_group[group_name].append(
                                    Task(task_name, short_description, long_description, parameters, examples))
                            else:
                                print("Excluding task: {}".format(task_name))

    if missing_report:
        print("The following tasks are missing examples:")
        for name in missing_example:
            print(name)
        print("\n")

        print("The following tasks are missing descriptons:")
        for name in missing_description:
            print(name)
        print("\n")

        print("The following tasks are missing parameters:")
        for name in missing_parameters:
            print(name)
        print("\n")

    # Write out "landing page"
    write_landing_page(tasks_by_group, outdir=outdir)

    # Write individual task pages
    write_task_pages(tasks_by_group, outdir=outdir)


def cli_command():
    """CLI interface of create_docs.py.

    try `python create_docs.py --help`
    """

    parser = argparse.ArgumentParser(description='Generate Pipeline task .RST files')
    parser.add_argument('--outdir', '-o', type=str, default=None, help='Output path of the RST files/subdirectories')
    parser.add_argument('--srcdir', '-s', type=str, default=None, help='Path of the Pipeline source code')

    args = parser.parse_args()
    srcdir = args.srcdir

    # the primary fallback default of the pipeline source directory.
    env_pipeline_src = os.getenv('pipeline_src')
    if srcdir is None and env_pipeline_src:
        # use the env variable "pipeline_src" for the Pipeline source code path.
        srcdir = os.path.abspath(env_pipeline_src)

    # the secondary fallback default of the Pipeline source directory.
    if srcdir is None:
        # use the ancestry path if "pipeline_dir" is not set.
        srcdir = os.path.abspath('../../pipeline')

    create_docs(outdir=args.outdir, srcdir=srcdir, missing_report=True)


if __name__ == "__main__":
    cli_command()
