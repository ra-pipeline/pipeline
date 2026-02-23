import os

import pytest

from pipeline.infrastructure import casa_tools
from tests.testing_utils import PipelineTester


@pytest.mark.skip(reason="Dataset not available")
@pytest.mark.importdata
def test_uid___A002_X1181695_X1c6a4_8ant__chan_flagged_import__component():
    """Run test of importdata on small dataset with channels flagged.

    Dataset(s):                 uid___A002_X1181695_X1c6a4_8ant_chans_flagged.ms
    Task(s):                    hifa_importdata
    """
    ref_directory = 'pl-componenttest/chan_flagged_import'
    visname = 'uid___A002_X1181695_X1c6a4_8ant_chans_flagged.ms'
    tasks = [
        ('hifa_importdata', {'vis': casa_tools.utils.resolve(os.path.join(ref_directory, visname))}),
    ]

    pt = PipelineTester(
        visname=[visname],
        mode='component',
        tasks=tasks,
        output_dir='chan_flagged_import',
        expectedoutput_dir=ref_directory,
        )

    pt.run()


@pytest.mark.importdata
@pytest.mark.selfcal
def test_uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small_target__selfcal_and_selfcal_restore__component():
    """Run test selfcal and selfcal restoration capabilities.

    Dataset(s):                 uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small_target.ms
    Task(s):                    hifa_importdata, hif_selfcal
    """
    data_dir = 'pl-unittest'
    visname = 'uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small_target.ms'
    tasks = [
        ('hifa_importdata', {'vis': casa_tools.utils.resolve(os.path.join(data_dir, visname)),
                             'datacolumns': {'data': 'regcal_contline'}}),
        ('hif_selfcal', {}),
        ('hif_selfcal', {'restore_only': True}),
    ]

    pt = PipelineTester(
        visname=['uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small_target.ms'],
        mode='component',
        tasks=tasks,
        output_dir='selfcal_and_selfcal_restore',
        expectedoutput_dir='pl-componenttest/selfcal_and_selfcal_restore',
        )

    pt.run()


@pytest.mark.skip(reason="Dataset not available")
@pytest.mark.importdata
@pytest.mark.selfcal
@pytest.mark.makeimages
def test_uid___A001_X375e_X7a__spw_mapping_missing_spws__component():
    """Run test of spw mapping with missing spws.

    MOUS:                       uid://A001/X375e/X7a
    Dataset(s):                 uid___A002_X11a51f7_Xcf3_spws_24_26_28.ms
                                uid___A002_X1290676_X2b8_spws_24_26_30.ms
                                uid___A002_X1290676_X665_spws_24_28_30.ms
    Task(s):                    hifa_importdata, hif_selfcal, hif_makeimlist, hif_makeimages
    """
    ref_directory = 'pl-componenttest/spw_mapping_missing_spws'
    visnames = ['uid___A002_X11a51f7_Xcf3_spws_24_26_28.ms',
                'uid___A002_X1290676_X2b8_spws_24_26_30.ms',
                'uid___A002_X1290676_X665_spws_24_28_30.ms']
    tasks = [
        ('hifa_importdata', {'vis': [casa_tools.utils.resolve(os.path.join(ref_directory, visname)) for visname in visnames]}),
        ('hif_selfcal', {}),
        ('hif_makeimlist', {'specmode': 'cont'}),
        ('hif_makeimages', {})
    ]

    pt = PipelineTester(
        visname=visnames,
        mode='component',
        tasks=tasks,
        output_dir='spw_mapping_missing_spws',
        expectedoutput_dir=ref_directory,
        )

    pt.run()
