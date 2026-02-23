import shutil

from pipeline.infrastructure import casa_tools
from tests.testing_utils import PipelineTester, ensure_working_dir


def test_TSKY0001__vlass_quicklook_regression():
    """Run VLASS quicklook regression

    Recipe name:                procedure_vlassQLIP.xml
    Dataset:                    TSKY0001.sb32295801.eb32296475.57549.31722762731_split_withcorrectdata.ms
    """
    ref_directory = 'pl-regressiontest/vlass_quicklook'

    pt = PipelineTester(
        visname=['TSKY0001.sb32295801.eb32296475.57549.31722762731_split_withcorrectdata.ms'],
        recipe='procedure_vlassQLIP.xml',
        input_dir=ref_directory,
        expectedoutput_dir=ref_directory,
        )

    ensure_working_dir(pt)
    if not pt.compare_only:
        parameter_list_file = casa_tools.utils.resolve(
            f'{ref_directory}/TSKY0001.sb32295801.eb32296475.57549.31722762731_split_QLIP_parameter.list')
        shutil.copyfile(parameter_list_file, casa_tools.utils.resolve(f'{pt.output_dir}/working/QLIP_parameter.list'))
    pt.run(telescope='vla')
