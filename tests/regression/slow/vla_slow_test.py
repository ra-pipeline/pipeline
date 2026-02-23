from tests.testing_utils import PipelineTester


def test_13A_537__procedure_hifv_calimage_cont_cube_selfcal__regression():
    """PIPE-2357: Run VLA calibration regression for standard procedure_hifv_calimage_cont_cube_selfcal.xml recipe.

    Recipe name:                procedure_hifv_calimage_cont_cube_selfcal.xml
    Dataset:                    13A-537/13A-537.sb24066356.eb24324502.56514.05971091435
    """
    ref_directory = 'pl-regressiontest/13A-537'

    pt = PipelineTester(
        visname=['13A-537.sb24066356.eb24324502.56514.05971091435'],
        recipe='procedure_hifv_calimage_cont_cube_selfcal.xml',
        input_dir=ref_directory,
        expectedoutput_dir=ref_directory,
        )

    pt.run(telescope='vla', omp_num_threads=1)


def test_15B_342__procedure_hifv_calimage_cont_selfcal__regression(data_directory):
    """Run VLA calibration regression for standard recipe.

    Recipe name:                procedure_hifv_calimage_cont_selfcal
    Dataset:                    15B-342.sb31041443.eb31041910.57246.076202627315
    """
    test_directory = f'{data_directory}/vla/15B-342/'
    ref_directory = 'pl-regressiontest/15B-342/'

    pt = PipelineTester(
        visname=['15B-342.sb31041443.eb31041910.57246.076202627315'],
        recipe='procedure_hifv_calimage_cont_selfcal.xml',
        input_dir=test_directory,
        expectedoutput_dir=ref_directory,
        )

    pt.run(telescope='vla', omp_num_threads=1)


def test_17B_188__procedure_hifv_calimage_cont_selfcal__regression(data_directory):
    """Run VLA calibration regression for standard recipe.

    Recipe name:                procedure_hifv_calimage_cont_selfcal
    Dataset:                    17B-188.sb35564398.eb35590549.58363.10481791667
    """
    test_directory = f'{data_directory}/vla/17B-188/'
    ref_directory = 'pl-regressiontest/17B-188/'

    pt = PipelineTester(
        visname=['17B-188.sb35564398.eb35590549.58363.10481791667'],
        recipe='procedure_hifv_calimage_cont_selfcal.xml',
        input_dir=test_directory,
        expectedoutput_dir=ref_directory,
        )

    pt.run(telescope='vla', omp_num_threads=1)


def test_18A_228__procedure_hifv_calimage_cont_selfcal__regression(data_directory):
    """Run VLA calibration regression for standard procedure_hifv_calimage_cont.xml recipe.

    Recipe name:                procedure_hifv_calimage_cont_selfcal
    Dataset:                    18A-228.sb35538192.eb35676319.58412.135923414358
    """
    test_directory = f'{data_directory}/vla/18A-228/'
    ref_directory = 'pl-regressiontest/18A-228/'

    pt = PipelineTester(
        visname=['18A-228.sb35538192.eb35676319.58412.13592341435'],
        recipe='procedure_hifv_calimage_cont_selfcal.xml',
        input_dir=test_directory,
        expectedoutput_dir=ref_directory,
        )

    pt.run(telescope='vla', omp_num_threads=1)


def test_18A_426__procedure_hifv_calimage_cont_selfcal__regression(data_directory):
    """Run VLA calibration regression for standard procedure_hifv_calimage_cont.xml recipe.

    Recipe name:                procedure_hifv_calimage_cont_selfcal
    Dataset:                    18A-426.sb35644955.eb35676220.58411.96917952546
    """
    test_directory = f'{data_directory}/vla/18A-426/'
    ref_directory = 'pl-regressiontest/18A-426/'

    pt = PipelineTester(
        visname=['18A-426.sb35644955.eb35676220.58411.96917952546'],
        recipe='procedure_hifv_calimage_cont_selfcal.xml',
        input_dir=test_directory,
        expectedoutput_dir=ref_directory,
        )

    pt.run(telescope='vla', omp_num_threads=1)


def test_21A_423__procedure_hifv_calimage_cont_selfcal__regression(data_directory):
    """Run VLA calibration regression for standard recipe.

    Recipe name:                procedure_hifv_calimage_cont_selfcal
    Dataset:                    21A-423.sb39709588.eb40006153.59420.64362002315
    """
    test_directory = f'{data_directory}/vla/21A-423/'
    ref_directory = 'pl-regressiontest/21A-423/'

    pt = PipelineTester(
        visname=['21A-423.sb39709588.eb40006153.59420.64362002315'],
        recipe='procedure_hifv_calimage_cont_selfcal.xml',
        input_dir=test_directory,
        expectedoutput_dir=ref_directory,
        )

    pt.run(telescope='vla', omp_num_threads=1)
