import pytest

from tests.testing_utils import PipelineTester, setup_flux_antennapos


# 7m tests
@pytest.mark.seven
def test_2019_1_00847_S__uid___A001_X1467_X264_regression(data_directory):
    """Run longer regression test on this ALMA IF 7m dataset

    PPR:                        pl-regressiontest/2019.1.00847.S/PPR.xml
    Project:                    2019.1.00847.S
    MOUS:                       uid___A001_X1467_X264
    EBs:                        uid___A002_Xe1f219_X1457
                                uid___A002_Xe1f219_X9dbf
                                uid___A002_Xe27761_X74f8
    """
    test_directory = f'{data_directory}/alma_if/2019.1.00847.S/'
    ref_directory = 'pl-regressiontest/2019.1.00847.S/'

    pt = PipelineTester(
        visname=[
            'uid___A002_Xe1f219_X1457',
            'uid___A002_Xe1f219_X9dbf',
            'uid___A002_Xe27761_X74f8'
        ],
        ppr=(test_directory + 'PPR.xml'),
        project_id="2019_1_00847_S",
        input_dir=test_directory,
        expectedoutput_dir=ref_directory,
        )

    setup_flux_antennapos(test_directory, pt.output_dir)
    pt.run()


@pytest.mark.seven
def test_2019_1_00994_S__uid___A001_X1467_X29e__PPR__regression(data_directory):
    """Run longer regression test on this ALMA IF 7m dataset

    PPR:                        pl-regressiontest/2019.1.00994.S/PPR.xml
    Project:                    2019.1.00994.S
    MOUS:                       uid___A001_X1467_X29e
    EBs:                        uid___A002_Xe44309_X7d94
                                uid___A002_Xe45e29_X59ee
                                uid___A002_Xe45e29_X6666
                                uid___A002_Xe48598_X8697
    """
    test_directory = f'{data_directory}/alma_if/2019.1.00994.S/'
    ref_directory = 'pl-regressiontest/2019.1.00994.S/'

    pt = PipelineTester(
        visname=[
            'uid___A002_Xe44309_X7d94',
            'uid___A002_Xe45e29_X59ee',
            'uid___A002_Xe45e29_X6666',
            'uid___A002_Xe48598_X8697'
        ],
        ppr=(test_directory + 'PPR.xml'),
        project_id="2019_1_00994_S",
        input_dir=test_directory,
        expectedoutput_dir=ref_directory,
        )

    setup_flux_antennapos(test_directory, pt.output_dir)
    pt.run()


@pytest.mark.seven
def test_2019_1_01056_S__uid___A001_X1465_X1b3c__PPR__regression(data_directory):
    """Run longer regression test on this ALMA IF 7m dataset

    PPR:                        pl-regressiontest/2019.1.01056.S/PPR.xml
    Project:                    2019.1.01056.S
    MOUS:                       uid___A001_X1465_X1b3c
    EBs:                        uid___A002_Xe1f219_X6d0b
                                uid___A002_Xe1f219_X7ee8
    """
    test_directory = f'{data_directory}/alma_if/2019.1.01056.S/'
    ref_directory = 'pl-regressiontest/2019.1.01056.S/'

    pt = PipelineTester(
        visname=['uid___A002_Xe1f219_X6d0b', 'uid___A002_Xe1f219_X7ee8'],
        ppr=(test_directory + 'PPR.xml'),
        project_id="2019_1_01056_S",
        input_dir=test_directory,
        expectedoutput_dir=f'{ref_directory}',
        )

    setup_flux_antennapos(test_directory, pt.output_dir)
    pt.run()


# 12m tests
@pytest.mark.twelve
def test_2019_1_01094_S__uid___A001_X1528_X2a8__PPR__regression(data_directory):
    """Run longer regression test on this ALMA IF 12m dataset

    PPR:                        pl-regressiontest/2019.1.01094.S/PPR.xml
    Project:                    2019.1.01094.S
    MOUS:                       uid___A001_X1528_X2a8
    EBs:                        uid___A002_Xecbc07_X6b0e
                                uid___A002_Xecf7c7_X1d83
    """
    test_directory = f'{data_directory}/alma_if/2019.1.01094.S/'
    ref_directory = 'pl-regressiontest/2019.1.01094.S/'

    pt = PipelineTester(
        visname=['uid___A002_Xecbc07_X6b0e', 'uid___A002_Xecf7c7_X1d83'],
        ppr=(test_directory + 'PPR.xml'),
        project_id="2019_1_01094_S",
        input_dir=test_directory,
        expectedoutput_dir=ref_directory,
        )

    setup_flux_antennapos(test_directory, pt.output_dir)

    pt.run()


@pytest.mark.twelve
def test_E2E9_1_00061_S__uid___A001_X2df8_X5c__regression(data_directory):
    """Run longer regression test on this ALMA IF 12m dataset

    PPR:                        pl-regressiontest/E2E9.1.00061.S/PPR.xml
    Project:                    E2E9.1.00061.S
    MOUS:                       uid___A001_X2df8_X5c
    EBs:                        uid___A002_Xfd764e_X5843
                                uid___A002_Xfd764e_X60e2
    """
    test_directory = f'{data_directory}/alma_if/E2E9.1.00061.S/'
    ref_directory = 'pl-regressiontest/E2E9.1.00061.S/'

    pt = PipelineTester(
        visname=['uid___A002_Xfd764e_X5843', 'uid___A002_Xfd764e_X60e2'],
        ppr=(test_directory + 'PPR.xml'),
        project_id="E2E9_1_00061_S",
        input_dir=test_directory,
        expectedoutput_dir=ref_directory,
        )

    setup_flux_antennapos(test_directory, pt.output_dir)

    pt.run()


@pytest.mark.twelve
def test_2018_1_01255_S__uid___A001_X135e_X67__regression(data_directory):
    """Run longer regression test on this ALMA IF 12m dataset

    PPR:                        pl-regressiontest/2018.1.01255.S/PPR.xml
    Project:                    2018.1.01255.S
    MOUS:                       uid___A001_X135e_X67
    EBs:                        uid___A002_Xe0e4ca_Xb18
                                uid___A002_Xeb9695_X2fe5
    """
    test_directory = f'{data_directory}/alma_if/2018.1.01255.S/'
    ref_directory = 'pl-regressiontest/2018.1.01255.S/'

    pt = PipelineTester(
        visname=['uid___A002_Xe0e4ca_Xb18', 'uid___A002_Xeb9695_X2fe5'],
        ppr=(test_directory + 'PPR.xml'),
        project_id="2018_1_01255_S",
        input_dir=test_directory,
        expectedoutput_dir=ref_directory,
        )

    setup_flux_antennapos(test_directory, pt.output_dir)

    pt.run()


@pytest.mark.twelve
def test_2017_1_00912_S__uid___A002_Xc74b5b_X316a__regression(data_directory):
    """Run longer regression test on this ALMA IF 12m dataset

    PPR:                        pl-regressiontest/2017.1.00912.S/PPR.xml
    Project:                    2017.1.00912.S
    MOUS:                       uid___A001_X1284_X322
    EBs:                        uid___A002_Xc74b5b_X316a
    """
    test_directory = f'{data_directory}/alma_if/2017.1.00912.S/'
    ref_directory = 'pl-regressiontest/2017.1.00912.S/'

    pt = PipelineTester(
        visname=['uid___A002_Xc74b5b_X316a'],
        ppr=(test_directory + 'PPR.xml'),
        project_id="2017_1_00912_S",
        input_dir=test_directory,
        expectedoutput_dir=ref_directory,
        )

    setup_flux_antennapos(test_directory, pt.output_dir)
    pt.run()


@pytest.mark.twelve
def test_2019_1_01184_S__uid___A001_X1465_X1635__regression(data_directory):
    """Run longer regression test on this ALMA IF 12m dataset

    PPR:                        pl-regressiontest/2019.1.01184.S/PPR.xml
    Project:                    2019_1_01184_S
    MOUS:                       uid___A001_X1465_X1635
    EBs:                        uid___A002_Xe1d2cb_X12782
                                uid___A002_Xe850fb_X4efc
    """
    test_directory = f'{data_directory}/alma_if/2019.1.01184.S/'
    ref_directory = 'pl-regressiontest/2019.1.01184.S/'

    pt = PipelineTester(
        visname=['uid___A002_Xe1d2cb_X12782', 'uid___A002_Xe850fb_X4efc'],
        ppr=(test_directory + 'PPR.xml'),
        project_id="2019_1_01184_S",
        input_dir=test_directory,
        expectedoutput_dir=ref_directory,
        )

    setup_flux_antennapos(test_directory, pt.output_dir)
    pt.run()


@pytest.mark.twelve
def test_2019_1_00678_S__uid___A002_Xe6a684_X7c41__PPR__regression(data_directory):
    """Run longer regression test on this ALMA IF 12m dataset

    PPR:                        pl-regressiontest/2019.1.00678.S/PPR.xml
    Project:                    2019.1.00678.S
    MOUS:                       uid___A001_X14d8_X3eb
    EBs:                        uid___A002_Xe6a684_X7c41
    """
    test_directory = f'{data_directory}/alma_if/2019.1.00678.S/'
    ref_directory =  'pl-regressiontest/2019.1.00678.S/'

    pt = PipelineTester(
        visname=['uid___A002_Xe6a684_X7c41'],
        ppr=(test_directory + 'PPR.xml'),
        project_id="2019_1_00678_S",
        input_dir=test_directory,
        expectedoutput_dir=ref_directory,
        )

    setup_flux_antennapos(test_directory, pt.output_dir)
    pt.run()


@pytest.mark.twelve
def test_2017_1_00670_S__uid___A002_Xca8fbf_X5733__PPR__regression(data_directory):
    """Run longer regression test on this ALMA IF 12m dataset

    PPR:                        pl-regressiontest/2017.1.00670.S/PPR.xml
    Project:                    2017.1.00670.S
    MOUS:                       uid___A001_X1284_X20e0
    EBs:                        uid___A002_Xca8fbf_X5733
    """
    test_directory = f'{data_directory}/alma_if/2017.1.00670.S/'
    ref_directory =  'pl-regressiontest/2017.1.00670.S/'

    pt = PipelineTester(
        visname=['uid___A002_Xca8fbf_X5733'],
        ppr=(test_directory + 'PPR.xml'),
        project_id='2017_1_00670_S',
        input_dir = test_directory,
        expectedoutput_dir=ref_directory,
        )

    setup_flux_antennapos(test_directory, pt.output_dir)
    pt.run()
