"""Test for recipe_converter.py"""
import os
import pytest
import string
import tempfile
import xml.dom.minidom as minidom

from . import recipe_converter


def helper_get_document(xml_string):
    return minidom.parseString(xml_string)


def helper_get_root_element(xml_string, root_tag_name):
    return helper_get_document(xml_string).getElementsByTagName(root_tag_name)[0]


def helper_generate_document_and_element(xml_string, root_tag_name):
    yield helper_get_document(xml_string)
    yield helper_get_root_element(xml_string, root_tag_name)


def test_get_recipe_dir():
    """Test get_recipe_dir."""
    path = recipe_converter.get_recipe_dir()
    assert path == os.path.split(__file__)[0]


@pytest.mark.parametrize('submodule', ['hsd', 'hif', 'blah'])
def test_get_cli_dir(submodule):
    """Test get_cli_dir."""
    path = recipe_converter.get_cli_dir(submodule)
    recipe_dir, _ = os.path.split(__file__)
    pipeline_dir, _ = os.path.split(recipe_dir)
    assert path == os.path.join(pipeline_dir, submodule, 'cli')


@pytest.mark.parametrize(
    'xml_string, tag_name, expected',
    [
        ('<root><a><b>data</b></a></root>', 'b', 1),
        ('<root><a><b>data</b></a></root>', 'a', 1),
        ('<root><a><b>data</b></a></root>', 'c', 0),
        ('<root><a><b>data</b><b>data</b></a></root>', 'b', 2),
    ]
)
def test_get_element(xml_string, tag_name, expected):
    """Test get_element."""
    for dom_node in helper_generate_document_and_element(xml_string, 'root'):
        elements = recipe_converter.get_element(dom_node, tag_name)

        assert len(elements) == expected

        if expected > 0:
            assert all([x.tagName == tag_name for x in elements])

        if expected == 1:
            elements = recipe_converter.get_element(dom_node, tag_name, expect_unique=True)
            assert elements.tagName == tag_name


@pytest.mark.parametrize(
    'xml_string, expected',
    [
        ('<a>data</a>', 'data'),
        ('<a><b>data</b></a>', AttributeError),
    ]
)
def test_get_data(xml_string, expected):
    """Test get_data."""
    # Element
    dom_node = helper_get_root_element(xml_string, 'a')

    if isinstance(expected, type) and issubclass(expected, Exception):
        with pytest.raises(expected):
            data = recipe_converter.get_data(dom_node)
    elif isinstance(expected, str):
        data = recipe_converter.get_data(dom_node)
        assert isinstance(data, str)
        assert data == expected
    else:
        pytest.fail('Should not reach here')

    # Document (always raise AttributeError)
    dom_node = helper_get_document(xml_string)
    with pytest.raises(AttributeError):
        data = recipe_converter.get_data(dom_node)


@pytest.mark.parametrize(
    'xml_string, expected',
    [
        ('<root><Keyword>spw</Keyword><Value>0</Value></root>', ('spw', '0')),
    ]
)
def test_parse_parameter(xml_string, expected):
    """Test parse_parameter."""
    for dom_node in helper_generate_document_and_element(xml_string, 'root'):
        key, val = recipe_converter.parse_parameter(dom_node)
        assert isinstance(key, str)
        assert isinstance(val, str)
        assert key == expected[0]
        assert val == expected[1]


@pytest.mark.parametrize(
    'xml_string, expected',
    [
        # valid Command with default parameters
        (
            '<ProcessingCommand>' \
            '<Command>h_save</Command>' \
            '<ParameterSet></ParameterSet>' \
            '</ProcessingCommand>',
            {'h_save': {'comment': 'not_tested', 'parameter': {}}}
        ),
        # valid Command with custom parameters
        (
            '<ProcessingCommand>' \
            '<Command>h_save</Command>' \
            '<ParameterSet>' \
            '<Parameter><Keyword>filename</Keyword><Value>output.context</Value></Parameter>' \
            '</ParameterSet>' \
            '</ProcessingCommand>',
            {'h_save': {'comment': 'not_tested', 'parameter': {'filename': 'output.context'}}}
        ),
        # breakpoint
        (
            '<ProcessingCommand>' \
            '<Command>breakpoint</Command>' \
            '<ParameterSet></ParameterSet>' \
            '</ProcessingCommand>',
            {'breakpoint': {'parameter': {}}}
        ),
        # ERROR: not a Command
        ('<ProcessingCommand><task><shortdescription>do something</shortdescription></task></ProcessingCommand>', AssertionError),
        # ERROR: multiple Commands
        (
            '<ProcessingCommand>' \
            '<Command>h_init</Command><ParameterSet></ParameterSet>' \
            '<Command>h_save</Command><ParameterSet></ParameterSet>' \
            '</ProcessingCommand>',
            AssertionError
        ),
        # ERROR: unexpected Command structure (missing ParameterSet)
        (
            '<ProcessingCommand><Command>h_save</Command></ProcessingCommand>',
            AssertionError
        ),
    ]
)
def test_parse_command(xml_string, expected):
    """Test parse_command."""
    for dom_node in helper_generate_document_and_element(xml_string, 'ProcessingCommand'):
        if isinstance(expected, type) and issubclass(expected, Exception):
            with pytest.raises(expected):
                cmd = recipe_converter.parse_command(dom_node)
        elif isinstance(expected, dict):
            cmd = recipe_converter.parse_command(dom_node)
            print(cmd)
            assert isinstance(cmd, dict)
            assert len(cmd) == 1
            task_name, expected_prop = list(expected.items())[0]
            assert task_name in cmd
            prop = cmd[task_name]
            print(prop)
            assert isinstance(prop, dict)
            for key in expected_prop.keys():
                assert key in prop
            assert prop['parameter'] == expected_prop['parameter']
        else:
            pytest.fail('Should not reach here')


@pytest.mark.parametrize(
    'xml_string, expected',
    [
        # ERROR: invalid structure
        ('<ProcessingProcedure></ProcessingProcedure>', AssertionError),
        # valid structure
        (
            '<ProcessingProcedure>' \
            '<ProcedureTitle>h_test</ProcedureTitle>' \
            '<ProcessingCommand><Command>h_save</Command><ParameterSet></ParameterSet></ProcessingCommand>' \
            '</ProcessingProcedure>',
            ('h_test', [{'h_save': {'comment': 'not_tested', 'parameter': {}}}])
        )
    ]
)
def test_parse(xml_string, expected):
    """Test parse."""
    with tempfile.NamedTemporaryFile('w+') as f:
        name = f.name
        f.write(xml_string)
        f.flush()
        if isinstance(expected, type) and issubclass(expected, Exception):
            with pytest.raises(expected):
                _ = recipe_converter.parse(name)
        elif isinstance(expected, tuple):
            procedure_name, commands = recipe_converter.parse(name)
            assert procedure_name == expected[0]
            expected_commands = expected[1]
            assert len(commands) == len(expected_commands)
            for cmd, ref in zip(commands, expected_commands):
                command_name = list(ref.keys())[0]
                assert len(cmd) == 1
                assert command_name in cmd
                ref_prop = ref[command_name]
                prop = cmd[command_name]
                for key in ref_prop.keys():
                    assert key in prop
                assert prop['parameter'] == ref_prop['parameter']
        else:
            pytest.fail('Should not reach here')


@pytest.mark.parametrize(
    'task_name, config, expected',
    [
        ('breakpoint', {}, '        #  ---- breakpoint ----'),
        ('breakpoint', {'comment': 'This is comment'}, '        #  ---- breakpoint ----'),
        ('hsd_baseline', {}, ''),
        ('hsd_baseline', {'comment': 'This is comment'}, '        # This is comment\n'),
        ('hsd_baseline', {'comment': 'This is comment\n'}, '        # This is comment\n'),
        (
            'hsd_baseline',
            {'comment': 'This is \nmulti-line comment'},
            '        # This is \n' \
            '        # multi-line comment\n'
        ),
        (
            'hsd_baseline',
            {'comment': 'This is \nmulti-line comment\n'},
            '        # This is \n' \
            '        # multi-line comment\n'
        ),
    ]
)
def test_get_comment(task_name, config, expected):
    """Test get_comment."""
    result = recipe_converter.get_comment(task_name, config)
    assert result == expected


@pytest.mark.parametrize(
    'task_name, config, expected',
    [
        # breakpoint
        ('breakpoint', {}, ''),
        # default parameter
        (
            'hsd_baseline',
            {'parameter_types': {}},
            '        hsd_baseline()'
        ),
        # custom parameters: any type parameter value is always interpreted as string
        (
            'hsd_baseline',
            {
                'parameter': {'pstr': 'strval', 'pint': '3'}
            },
            '        hsd_baseline(pstr=\'strval\', pint=3)'
        ),
        # importdata tasks
        (
            'hsd_importdata',
            {'parameter_types': {}},
            '        hsd_importdata(vis=vislist)\n' \
            '\n' \
            '        if importonly:\n' \
            '            raise Exception(IMPORT_ONLY)'
        ),
    ]
)
def test_get_execution_command(task_name, config, expected):
    """Test get_execution_command."""
    if isinstance(expected, type) and issubclass(expected, Exception):
        with pytest.raises(expected):
            _ = recipe_converter.get_execution_command(task_name, config)
    elif isinstance(expected, str):
        result = recipe_converter.get_execution_command(task_name, config)
        assert result == expected
    else:
        pytest.fail('Should not reach here')


def test_c2p():
    """Test c2p."""
    # perform only simple test as c2p is consisting of get_comment and get_execution_command
    # which are well tested right above
    task_property = {'h_applycal': {
        'comment': 'This is comment',
        'parameter': {'spw': '17,19,21,23'},
        'parameter_types': {'spw': ('string', [])}
    }}
    expected = '        # This is comment\n' \
               '        h_applycal(spw=\'17,19,21,23\')'
    result = recipe_converter.c2p(task_property)
    assert result == expected


def test_to_procedure():
    """Test to_procedure."""
    # perform only simple test as to_procedure is just a sequential call of c2p
    task_property_list = [
        {'h_applycal': {
            'comment': 'This is comment',
            'parameter': {'spw': '17,19,21,23'},
            'parameter_types': {'spw': ('string', [])}
        }},
        {'h_makeimlist': {
            'comment': 'This is another comment',
            'parameter': {},
            'parameter_types': {}
        }}
    ]
    expected = '        # This is comment\n' \
               '        h_applycal(spw=\'17,19,21,23\')\n' \
               '\n' \
               '        # This is another comment\n' \
               '        h_makeimlist()'
    result = recipe_converter.to_procedure(task_property_list)
    assert result == expected


@pytest.mark.parametrize(
    'plotlevel_summary, init_args',
    [
        (False, ''),
        (True, 'plotlevel=\'summary\'')
    ]
)
def test_export(plotlevel_summary, init_args):
    """Test export."""
    script_template = string.Template(recipe_converter.TEMPLATE_TEXT)
    task_property_list = [
        {'h_applycal': {
            'comment': 'This is comment',
            'parameter': {'spw': '17,19,21,23'},
            'parameter_types': {'spw': ('string', [])}
        }},
        {'h_makeimlist': {
            'comment': 'This is another comment',
            'parameter': {},
            'parameter_types': {}
        }}
    ]
    func_name = 'h_test'
    procedure = '        # This is comment\n' \
                '        h_applycal(spw=\'17,19,21,23\')\n' \
                '\n' \
                '        # This is another comment\n' \
                '        h_makeimlist()'
    expected = script_template.safe_substitute(
        func_name=func_name,
        procedure=procedure,
        init_args=init_args
    )
    with tempfile.NamedTemporaryFile('w+') as f:
        outfile = f.name
        recipe_converter.export(
            recipe_name=func_name,
            commands=task_property_list,
            script_name=outfile,
            plotlevel_summary=plotlevel_summary
        )
        f.seek(0, os.SEEK_SET)
        result = f.read()
    assert result == expected


def test_main():
    """Test main."""
    pytest.skip('Skip testing main. Its output must be carefully examined by developer.')


def test_generate_all():
    """Test generate_all."""
    pytest.skip('Skip testing generate_all. Its output must be carefully examined by developer.')
