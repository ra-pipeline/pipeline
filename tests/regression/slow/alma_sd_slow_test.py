from tests.testing_utils import PipelineTester, setup_flux_antennapos


def test_2019_2_00093_S__uid___A001_X14c3_Xc33__regression(data_directory):
    """Run longer regression test on this ALMA SD dataset

    Recipe name:                procedure_hsd_calimage
    Project:                    2019.2.00093.S
    MOUS:                       uid___A001_X14c3_Xc33
    EBs:                        uid___A002_Xe850fb_X2df8
                                uid___A002_Xe850fb_X36e4
                                uid___A002_Xe850fb_X11e13
    """
    test_directory = f'{data_directory}/alma_sd/2019.2.00093.S/'
    ref_directory = 'pl-regressiontest/2019.2.00093.S/'

    pt = PipelineTester(
        visname=['uid___A002_Xe850fb_X2df8', 'uid___A002_Xe850fb_X36e4', 'uid___A002_Xe850fb_X11e13'],
        recipe='procedure_hsd_calimage.xml',
        project_id="2019_2_00093_S",
        input_dir=test_directory,
        expectedoutput_dir=ref_directory,
        )

    pt.run()


def test_2019_1_01056_S__uid___A001_X1465_X1b44__regression(data_directory):
    """Run weekly regression test on this ALMA SD dataset

    Recipe name:                procedure_hsd_calimage
    Project:                    2019.1.01056.S
    MOUS:                       uid___A001_X1465_X1b44
    EBs:                        uid___A002_Xe1d2cb_X110f1
                                uid___A002_Xe1d2cb_X11d0a
                                uid___A002_Xe1f219_X6eeb
    """
    test_directory = f'{data_directory}/alma_sd/2019.1.01056.S/'
    ref_directory = 'pl-regressiontest/2019.1.01056.S/'

    pt = PipelineTester(
        visname=['uid___A002_Xe1d2cb_X110f1', 'uid___A002_Xe1d2cb_X11d0a', 'uid___A002_Xe1f219_X6eeb'], 
        recipe='procedure_hsd_calimage.xml',
        project_id="2019_1_01056_S",
        input_dir=test_directory,
        expectedoutput_dir=f'{ref_directory}',
        )

    setup_flux_antennapos(test_directory, pt.output_dir)
    pt.run()


def test_2016_1_01489_T__uid___A001_X898_Xda__regression(data_directory):
    """Run weekly regression test on this ALMA SD dataset

    Recipe name:                procedure_hsd_calimage
    Project:                    2016.1.01489.T
    MOUS:                       uid___A001_X898_Xda
    EBs:                        uid___A002_Xbadc30_X43ee
                                uid___A002_Xbaedce_X7694
    """
    test_directory = f'{data_directory}/alma_sd/2016.1.01489.T/'
    ref_directory = 'pl-regressiontest/2016.1.01489.T/'

    pt = PipelineTester(
        visname=['uid___A002_Xbadc30_X43ee', 'uid___A002_Xbaedce_X7694'],
        recipe='procedure_hsd_calimage.xml',
        project_id="2016_1_01489_T",
        input_dir=test_directory,
        expectedoutput_dir=ref_directory,
        )

    pt.run()
