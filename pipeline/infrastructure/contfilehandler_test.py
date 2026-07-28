from unittest.mock import Mock
import pytest

from .. import domain
from . import casa_tools
from . import contfilehandler

cont_ranges_test_params = ({'fields': {'helms30': {'0': {'spwname': 'X339408637#ALMA_RB_06#BB_1#SW-01#FULL_RES', 'flags': ['ALLCONT'], 'ranges': [{'range': (214.4892469235, 216.2235771905),
'refer': 'LSRK'}]}}}, 'version': 3},)

class mock_spw:
    def __init__(self, frame):
        self.frame = frame

class mock_ms:
    def __init__(self, name):
        self.name = name
        self.spw_topo = mock_spw('TOPO')
    def get_spectral_windows(self):
        return [self.spw_topo]


to_ms_frame_test_params = (
    ('214.5.0~215.5GHz;215.6~216.1GHz LSRK',
     [casa_tools.utils.resolve('pl-unittest/uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms')],
     ['3'], '0', Mock(spec=domain.ObservingRun, **{'virtual2real_spw_id.return_value': 0, 'get_ms.return_value': mock_ms('uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms')}),
     (['214.4948696490~215.5104946490GHz;215.6042446490~216.1198696490GHz TOPO'],
      ['55~119;16~48'],
      {'unit': 'GHz', 'value': 1.5}, 'TOPO')),
    ('230.4~230.7GHz;231.5~231.6GHz;232.3~232.4GHz SOURCE',
     [casa_tools.utils.resolve('pl-unittest/uid___A002_Xcfc232_X2eda_test.ms')],
     ['3'], 18, Mock(spec=domain.ObservingRun, **{'virtual2real_spw_id.return_value': 18, 'get_ms.return_value': mock_ms('uid___A002_Xcfc232_X2eda_test.ms')}),
     (['230.4733757345~230.7038444845GHz;231.5026726095~231.6042351095GHz;232.3024772970~232.4040397970GHz TOPO'],
      ['0~235;1054~1157;1873~1976'],
      {'unit': 'GHz', 'value': 0.5}, 'TOPO'))
    )

@pytest.mark.parametrize("result", cont_ranges_test_params)
def test_cont_ranges(result):
    """
    Test ContFileHandler::cont_ranges
    """

    cfh = contfilehandler.ContFileHandler(casa_tools.utils.resolve('pl-unittest/cont.dat'))
    assert cfh.cont_ranges == result

@pytest.mark.parametrize("selection, msnames, fields, spw_id, observing_run, result", to_ms_frame_test_params)
def test_to_ms_frame(selection, msnames, fields, spw_id, observing_run, result):
    """
    Test ContFileHandler::to_ms_frame()
    """

    cfh = contfilehandler.ContFileHandler(casa_tools.utils.resolve('pl-unittest/cont.dat'))
    assert cfh.to_ms_frame(selection, msnames, fields, spw_id, observing_run) == result



