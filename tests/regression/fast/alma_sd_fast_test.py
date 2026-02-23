import shutil

from pipeline.infrastructure import casa_tools
from tests.testing_utils import PipelineTester


def test_uid___A002_X85c183_X36f__procedure_hsd_calimage__regression():
    """Run ALMA single-dish cal+image regression on the observation data of M100.

    Recipe name:                procedure_hsd_calimage
    Dataset:                    uid___A002_X85c183_X36f
    """
    ref_directory = 'pl-regressiontest/uid___A002_X85c183_X36f'

    pt = PipelineTester(
        visname=['uid___A002_X85c183_X36f'],
        recipe='procedure_hsd_calimage.xml',
        input_dir=ref_directory,
        expectedoutput_dir=ref_directory,
        )

    pt.run()


def test_uid___A002_X85c183_X36f_SPW15_23__PPR__regression():
    """Run ALMA single-dish restoredata regression on the observation data of M100.

    PPR: PPR.xml                pl-regressiontest/uid___A002_X85c183_X36f_SPW15_23/PPR.xml
    Dataset:                    uid___A002_X85c183_X36f_SPW15_23
    """
    ref_directory = 'pl-regressiontest/uid___A002_X85c183_X36f_SPW15_23'

    pt = PipelineTester(
        visname=['uid___A002_X85c183_X36f_SPW15_23.ms'],
        ppr=f'{ref_directory}/PPR.xml',
        input_dir=ref_directory,
        expectedoutput_dir=ref_directory,
        )

    # copy files use restore task into products folder
    if not pt.compare_only:
        input_products = casa_tools.utils.resolve(f'{ref_directory}/products')
        shutil.copytree(input_products, f'{pt.output_dir}/products')

    pt.run()
