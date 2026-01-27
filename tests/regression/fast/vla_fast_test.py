import shutil

import pytest

from pipeline.infrastructure import casa_tools
from tests.testing_utils import PipelineTester


def test_13A_537__procedure_hifv__regression():
    """Run VLA calibration regression for standard procedure_hifv.xml recipe.

    Recipe name:                procedure_hifv
    Dataset:                    13A-537/13A-537.sb24066356.eb24324502.56514.05971091435
    """
    ref_directory = 'pl-regressiontest/13A-537'

    pt = PipelineTester(
        visname=['13A-537.sb24066356.eb24324502.56514.05971091435'],
        recipe='procedure_hifv.xml',
        input_dir=ref_directory,
        output_dir='13A_537__procedure_hifv__regression',
        expectedoutput_dir=ref_directory,
        )

    pt.run(telescope='vla', omp_num_threads=1)


def test_13A_537__calibration__PPR__regression():
    """Run VLA calibration regression with a PPR file.

    PPR name:                   PPR_13A-537.xml
    Dataset:                    13A-537/13A-537.sb24066356.eb24324502.56514.05971091435
    """
    ref_directory = 'pl-regressiontest/13A-537'

    pt = PipelineTester(
        visname=['13A-537.sb24066356.eb24324502.56514.05971091435'],
        ppr=f'{ref_directory}/PPR_13A-537.xml',
        input_dir=ref_directory,
        output_dir='13A_537__calibration__PPR__regression',
        expectedoutput_dir=ref_directory,
        )

    pt.run(telescope='vla', omp_num_threads=1)


def test_13A_537__restore__PPR__regression():
    """Run VLA calibration restoredata regression with a PPR file
    NOTE: results file frozen to CASA/Pipeline version below since products were created
    with that Pipeline version

    PPR name:                   PPR_13A-537_restore.xml
    Dataset:                    13A-537/13A-537.sb24066356.eb24324502.56514.05971091435
    Expected results version:   casa-6.2.1.7-pipeline-2021.2.0.128
    """
    ref_directory = 'pl-regressiontest/13A-537'

    pt = PipelineTester(
        visname=['13A-537.sb24066356.eb24324502.56514.05971091435'],
        ppr=f'{ref_directory}/PPR_13A-537_restore.xml',
        input_dir=ref_directory,
        output_dir='13A_537__restore__PPR__regression',
        expectedoutput_file=f'{ref_directory}/restore/' +
                             '13A-537.casa-6.2.1.7-pipeline-2021.2.0.128.restore.results.txt',
        )

    # copy files use restore task into products folder
    if not pt.compare_only:
        input_products = casa_tools.utils.resolve(f'{ref_directory}/products')
        shutil.copytree(input_products, f'{pt.output_dir}/products')

    pt.run(telescope='vla')


def test_13A_537__restore__post1553__PPR__regression():
    """Run VLA calibration restoredata regression with a PPR file

    PPR name:                   PPR_13A-537_restore.xml
    Dataset:                    13A-537/13A-537.sb24066356.eb24324502.56514.05971091435
    """
    ref_directory = 'pl-regressiontest/13A-537'

    pt = PipelineTester(
        visname=['13A-537.sb24066356.eb24324502.56514.05971091435'],
        ppr=f'{ref_directory}/PPR_13A-537_restore.xml',
        input_dir=ref_directory,
        output_dir='13A_537__restore__post1553__PPR__regression',
        expectedoutput_dir=f'{ref_directory}/restore/',
        )

    # copy files use restore task into products folder
    if not pt.compare_only:
        input_products = casa_tools.utils.resolve(f'{ref_directory}/post1553_products')
        shutil.copytree(input_products, f'{pt.output_dir}/products')

    pt.run(telescope='vla')


@pytest.mark.skip(reason="PPR xml not available")
def test_13A_537__restore__cont_cube_selfcal__regression():
    """Run VLA calibration restoredata, then continuum and cube imaging with selfcal regression with a PPR file

    PPR name:                   PPR_13A-537_restore__cont_cube_selfcal.xml
    Dataset:                    13A-537/13A-537.sb24066356.eb24324502.56514.05971091435
    """
    ref_directory = 'pl-regressiontest/13A-537'

    pt = PipelineTester(
        visname=['13A-537.sb24066356.eb24324502.56514.05971091435'],
        ppr=f'{ref_directory}/PPR_13A-537_restore__cont_cube_selfcal.xml',
        input_dir=ref_directory,
        output_dir='13A_537__restore__cont_cube_selfcal__regression',
        expectedoutput_dir=f'{ref_directory}/restore_cont_cube_selfcal/',
        )

    # copy files use restore task into products folder
    if not pt.compare_only:
        input_products = casa_tools.utils.resolve(f'{ref_directory}/post1553_products')
        shutil.copytree(input_products, f'{pt.output_dir}/products')

    pt.run(telescope='vla')
