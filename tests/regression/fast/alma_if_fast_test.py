import shutil

import pytest

from pipeline.infrastructure import casa_tools
from tests.testing_utils import PipelineTester


# 7m tests
@pytest.mark.seven
def test_uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small__PPR__regression():
    """Run ALMA cal+image regression on a small test dataset with a PPR file.

    PPR:                        pl-regressiontest/uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small/PPR.xml
    Dataset:                    uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms
    """
    ref_directory = 'pl-regressiontest/uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small'

    pt = PipelineTester(
        visname=['uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms'],
        ppr=f'{ref_directory}/PPR.xml',
        input_dir='pl-unittest',
        expectedoutput_dir=ref_directory,
        )

    pt.run()


@pytest.mark.seven
def test_uid___A002_Xef72bb_X9d29__renorm_restore_procedure_hifa_image__regression():
    """Restore renorm from Cycle 8 (with current pipeline)

    Recipe name:                procedure_hifa_image
    Dataset:                    uid___A002_Xef72bb_X9d29
    """
    ref_directory = 'pl-regressiontest/uid___A002_Xef72bb_X9d29'

    pt = PipelineTester(
        visname=['uid___A002_Xef72bb_X9d29'],
        recipe='procedure_hifa_image.xml',
        input_dir=ref_directory,
        expectedoutput_dir=ref_directory,
        )

    # copy files into products folder for restore
    if not pt.compare_only:
        input_products = casa_tools.utils.resolve(f'{ref_directory}/products')
        shutil.copytree(input_products, f'{pt.output_dir}/rawdata')

    pt.run()


@pytest.mark.seven
def test_uid___A002_Xc845c0_X7366__cycle5_restore_procedure_hifa_image__regression():
    """
    Restore from Cycle 5 (with current pipeline)

    Recipe name:                procedure_hifa_image
    Dataset:                    uid___A002_Xc845c0_X7366
    """
    ref_directory = 'pl-regressiontest/uid___A002_Xc845c0_X7366'

    pt = PipelineTester(
        visname=['uid___A002_Xc845c0_X7366'],
        recipe='procedure_hifa_image.xml',
        input_dir=ref_directory,
        expectedoutput_dir=ref_directory,
        )

    # copy files for the restore into products folder
    if not pt.compare_only:
        input_products = casa_tools.utils.resolve(f'{ref_directory}/products')
        shutil.copytree(input_products, f'{pt.output_dir}/rawdata')

    pt.run()


@pytest.mark.seven
def test_uid___A002_Xc46ab2_X15ae__selfcal_restore_procedure_hifa_image__regression():
    """Restore selfcal from Cycle 10 (with current pipeline)

    Recipe name:                procedure_hifa_image
    Dataset:                    uid___A002_Xc46ab2_X15ae
    """
    ref_directory = 'pl-regressiontest/uid___A002_Xc46ab2_X15ae_selfcal_restore'

    pt = PipelineTester(
        visname=['uid___A002_Xc46ab2_X15ae'],
        recipe='procedure_hifa_image.xml',
        input_dir=ref_directory,
        expectedoutput_dir=ref_directory,
        )

    # copy files into products folder for restore
    if not pt.compare_only:
        input_products = casa_tools.utils.resolve(f'{ref_directory}/products')
        shutil.copytree(input_products, f'{pt.output_dir}/rawdata')

    pt.run()


@pytest.mark.skip(reason="Dataset not available")
@pytest.mark.seven
def test_E2E9_1_00084_S__uid___A001_X2df7_X1ec__PPR__regression():
    """Run ALMA polcal+image regression on a multi-EB 7m test dataset with a PPR file.

    PPR:                        pl-regressiontest/E2E9.1.00084.S/PPR.xml
    Project:                    E2E9.1.00084.S
    MOUS:                       uid___A001_X2df7_X1ec
    EBs:                        uid___A002_Xfd80cd_X128a
                                uid___A002_Xfd80cd_X1531
                                uid___A002_Xfd80cd_X1748
    """
    ref_directory = 'pl-regressiontest/E2E9.1.00084.S'

    pt = PipelineTester(
        visname=['uid___A002_Xfd80cd_X128a',
                 'uid___A002_Xfd80cd_X1531',
                 'uid___A002_Xfd80cd_X1748'],
        ppr=f"{ref_directory}/PPR.xml",
        input_dir=ref_directory,
        expectedoutput_dir=ref_directory,
        )

    pt.run()


@pytest.mark.skip(reason="Dataset not available")
@pytest.mark.seven
def test_2023_1_00228_S__uid___A002_X1199f9e_X7c24__procedure_hifa_calimage_diffgain__regression():
    """Run ALMA cal+image regression on a 7m B2B dataset with differential gain calibration.

    Recipe name:                procedure_hifa_calimage_diffgain
    Dataset:                    2023.1.00228.S: uid___A002_X1199f9e_X7c24
    """
    ref_directory = 'pl-regressiontest/2023.1.00228.S'

    pt = PipelineTester(
        visname=['uid___A002_X1199f9e_X7c24'],
        recipe='procedure_hifa_calimage_diffgain.xml',
        input_dir=ref_directory,
        expectedoutput_dir=ref_directory,
        )

    pt.run()


# 12m tests
@pytest.mark.twelve
def test_E2E6_1_00010_S__uid___A002_Xd0a588_X2239__procedure_hifa_image__regression():
    """Run ALMA cal+image regression on a 12m moderate-size test dataset in ASDM.

    Recipe name:                procedure_hifa_calimage
    Dataset:                    E2E6.1.00010.S: uid___A002_Xd0a588_X2239
    """
    ref_directory = 'pl-regressiontest/E2E6.1.00010.S'

    pt = PipelineTester(
        visname=['uid___A002_Xd0a588_X2239'],
        recipe='procedure_hifa_calimage.xml',
        input_dir=ref_directory,
        expectedoutput_dir=ref_directory,
        )

    pt.run()


@pytest.mark.twelve
def test_csv_3899_eb2_small__procedure_hifa_calimage__regression():
    """PIPE-2245: Run small ALMA cal+image regression to cover various heuristics

    Recipe name:                procedure_hifa_calimage
    Dataset:                    CSV-3899-EB2-small
    """
    ref_directory = 'pl-regressiontest/CSV-3899-EB2-small'

    pt = PipelineTester(
        visname=['uid___A002_X1181695_X1c6a4_8ant.ms'],
        recipe='procedure_hifa_calimage.xml',
        input_dir=ref_directory,
        output_dir='csv_3899_eb2_small',
        expectedoutput_dir=ref_directory,
        )

    pt.run(omp_num_threads=1)


@pytest.mark.twelve
def test_uid___A002_Xee1eb6_Xc58d__procedure_hifa_calsurvey__regression():
    """Run ALMA cal+survey regression on a calibration survey test dataset.

    Recipe name:                procedure_hifa_calsurvey
    Dataset:                    uid___A002_Xee1eb6_Xc58d
    """
    ref_directory = 'pl-regressiontest/uid___A002_Xee1eb6_Xc58d_calsurvey'

    pt = PipelineTester(
        visname=['uid___A002_Xee1eb6_Xc58d'],
        recipe='procedure_hifa_calsurvey.xml',
        input_dir=ref_directory,
        output_dir='uid___A002_Xee1eb6_Xc58d_calsurvey_output',
        expectedoutput_dir=ref_directory,
        )

    pt.run()
