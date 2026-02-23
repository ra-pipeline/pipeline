import shutil

from pipeline.infrastructure import casa_tools
from tests.testing_utils import PipelineTester


def test_mg2_20170525142607_180419__procedure_hsdn_calimage__regression():
    """Run ALMA single-dish cal+image regression for standard nobeyama recipe.

    Recipe name:                procedure_hsdn_calimage
    Dataset:                    mg2-20170525142607-180419
    """
    ref_directory = 'pl-regressiontest/mg2-20170525142607-180419'

    pt = PipelineTester(
        visname=['mg2-20170525142607-180419.ms'],
        recipe='procedure_hsdn_calimage.xml',
        input_dir=ref_directory,
        expectedoutput_dir=ref_directory,
        )
    pt.run()


def test_mg2_20170525142607_180419__PPR__regression():
    """Run ALMA single-dish cal+image regression for restore nobeyama recipe.

    PPR:                        pl-regressiontest/mg2-20170525142607-180419_PPR/PPR.xml
    Dataset:                    mg2-20170525142607-180419_PPR
    """
    ref_directory = 'pl-regressiontest/mg2-20170525142607-180419_PPR'

    pt = PipelineTester(
        visname=['mg2-20170525142607-180419.ms'],
        ppr=f'{ref_directory}/PPR.xml',
        input_dir=ref_directory,
        output_dir='mg2-20170525142607-180419_PPR',
        expectedoutput_dir=ref_directory,
        )

    # copy files use restore task into products folder
    if not pt.compare_only:
        input_products = casa_tools.utils.resolve(f'{ref_directory}/products')
        shutil.copytree(input_products, f'{pt.output_dir}/products')

    pt.run()
