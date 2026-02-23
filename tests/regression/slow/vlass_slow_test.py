import shutil

from pipeline.infrastructure import casa_tools
from tests.testing_utils import PipelineTester, ensure_working_dir


def test_VLASS2_2__se_cont_mosaic_procedure_vlassSEIP__regression(data_directory):
    """Run VLASS regression

    Recipe name:                   procedure_vlassSEIP_cv.xml
    Dataset:                       VLASS2.2.sb40889925.eb40967634.59536.14716583333_J232327.4+5024320_split.ms
    """
    test_directory = f'{data_directory}/vlass/se_cont_mosaic/'
    ref_directory = 'pl-regressiontest/vlass_se_cont_mosaic/'

    pt = PipelineTester(
        visname=['VLASS2.2.sb40889925.eb40967634.59536.14716583333_J232327.4+5024320_split.ms'],
        recipe=f'{test_directory}/procedure_vlassSEIP_cv.xml',
        input_dir=test_directory,
        expectedoutput_dir=ref_directory,
        )

    ensure_working_dir(pt)

    # Copy parameter list file into the working directory
    if not pt.compare_only:
        parameter_list_file = casa_tools.utils.resolve(f'{test_directory}/SEIP_parameter.list')
        shutil.copyfile(parameter_list_file, casa_tools.utils.resolve(
            f'{pt.output_dir}/working/SEIP_parameter.list'))

    pt.run(telescope='vla')


def test_VLASS2_2__se_cont_awp32_procedure_vlassSEIP__regression(data_directory):
    """Run VLASS regression

    Recipe name:                   procedure_vlassSEIP_cv.xml
    Dataset:                       VLASS2.2.sb40889925.eb40967634.59536.14716583333_J232327.4+5024320_split.ms
    """
    test_directory = f'{data_directory}/vlass/se_cont_awp32/'
    ref_directory = 'pl-regressiontest/vlass_se_cont_awp32/'

    pt = PipelineTester(
        visname=['VLASS2.2.sb40889925.eb40967634.59536.14716583333_J232327.4+5024320_split.ms'],
        recipe=f'{test_directory}/procedure_vlassSEIP_cv.xml',
        input_dir=test_directory,
        expectedoutput_dir=ref_directory,
        )

    ensure_working_dir(pt)

    # Copy parameter list file into the working directory
    if not pt.compare_only:
        parameter_list_file = casa_tools.utils.resolve(f'{test_directory}/SEIP_parameter_awp32.list')
        shutil.copyfile(parameter_list_file, casa_tools.utils.resolve(
            f'{pt.output_dir}/working/SEIP_parameter.list'))

    pt.run(telescope='vla')


def test_VLASS2_2__se_cube_procedure_vlassCCIP__regression(data_directory):
    """Run VLASS regression

    Recipe name:                procedure_vlassCCIP.xml
    Dataset:                    VLASS2.2.sb40889925.eb40967634.59536.14716583333_J232327.4+5024320_split.ms
    """
    test_directory = f'{data_directory}/vlass/se_cube/'
    ref_directory = 'pl-regressiontest/vlass_se_cube/'

    pt = PipelineTester(
        visname=['VLASS2.2.sb40889925.eb40967634.59536.14716583333_J232327.4+5024320_split.ms'],
        recipe='procedure_vlassCCIP.xml',
        input_dir=test_directory,
        expectedoutput_dir=ref_directory,
        )

    ensure_working_dir(pt)

    # Copy parameter list files and reimaging resources into the working directory
    if not pt.compare_only:
        seip_parameter_list_file = casa_tools.utils.resolve(f'{test_directory}/SEIP_parameter.list')
        shutil.copyfile(seip_parameter_list_file, casa_tools.utils.resolve(
            f'{pt.output_dir}/working/SEIP_parameter.list'))

        ccip_parameter_list_file = casa_tools.utils.resolve(f'{test_directory}/CCIP_parameter_sg16.list')
        shutil.copyfile(ccip_parameter_list_file, casa_tools.utils.resolve(
            f'{pt.output_dir}/working/CCIP_parameter.list'))

        reimaging_resources_file = casa_tools.utils.resolve(f'{test_directory}/reimaging_resources.tgz')
        shutil.copyfile(reimaging_resources_file, casa_tools.utils.resolve(
            f'{pt.output_dir}/working/reimaging_resources.tgz'))

    pt.run(telescope='vla')


def test_VLASS2_1__procedure_hifvcalvlass__regression(data_directory):
    """Run VLASS regression

    Recipe name:            procedure_hifvcalvlass.xml
    Dataset:                VLASS2.1.sb39020033.eb39038648.59173.7629213426
    """
    test_directory = f'{data_directory}/vlass/cal/'
    ref_directory = 'pl-regressiontest/vlass_cal'

    pt = PipelineTester(
        visname=['VLASS2.1.sb39020033.eb39038648.59173.7629213426'],
        recipe='procedure_hifvcalvlass.xml',
        input_dir=test_directory,
        expectedoutput_dir=ref_directory,
        )

    pt.run(telescope='vla')
