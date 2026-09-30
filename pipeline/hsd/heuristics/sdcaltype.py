import os

import numpy

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.api as api
from pipeline.hsd.heuristics import DataTypeHeuristics
from pipeline.infrastructure import casa_tools

LOG = infrastructure.get_logger(__name__)


class CalibrationTypeHeuristics(api.Heuristic):
    """
    """
    def calculate(self, filename):
        h = self._heuristics_factory(filename)
        return h(filename)

    def _heuristics_factory(self, filename):
        h = DataTypeHeuristics()
        datatype = h(filename).lower()
        return getattr(self, '_generate_%s_heuristics' % datatype)()

    def _generate_ms2_heuristics(self):
        return MsCalibrationTypeHeuristics()

    def _generate_asdm_heuristics(self):
        return AsdmCalibrationTypeHeuristics()

    def _generate_fits_heuristics(self):
        return DefaultCalibrationTypeHeuristics()

    def _generate_nro_heuristics(self):
        return DefaultCalibrationTypeHeuristics()

    def _generate_unknown_heuristics(self):
        return DefaultCalibrationTypeHeuristics()


class DefaultCalibrationTypeHeuristics(api.Heuristic):
    """
    Always return calibration mode 'none'.
    """
    def calculate(self, filename):
        """
        Return calibration type. Always return 'none'.
        """
        return 'none'


def _gap_analysis(timestamps, intervals, threshold_factor=3.0):
    separation = timestamps[1:] - timestamps[:-1]
    real_separation = separation.take(separation.nonzero()[0])
    average_interval = numpy.median(intervals)
    threshold = average_interval * threshold_factor
    #threshold = numpy.median(real_separation) * threshold_factor
    LOG.debug('threshold = %s'%(threshold))
    gaplist = numpy.where(separation > threshold)[0]
    return gaplist


def _israster(timestamp, interval, direction):
    # gap analysis
    gap_list = _gap_analysis(timestamp, interval, threshold_factor=5.0)
    LOG.debug('gap_list=%s'%(gap_list))

    # inspect scan direction
    dir0 = direction[:, :(gap_list[0]+1)]
    ddir0 = dir0[:, 1:] - dir0[:, :-1]
    ddir0_nonzero = ddir0[:, ddir0[0].nonzero()[0]]
    slope = ddir0_nonzero[1] / ddir0_nonzero[0]
    LOG.debug('slope=%s'%(slope))
    slope_mean = slope.mean()
    slope_std = slope.std()
    LOG.debug('slope_mean=%s'%(slope_mean))
    LOG.debug('slope_std=%s'%(slope_std))

    # compare extent of one direction segment with total map extent
    dx_total = direction[0].max() - direction[0].min()
    dy_total = direction[1].max() - direction[1].min()
    LOG.debug('dx_total, dy_total = %s, %s'%(dx_total, dy_total))
    dx = dir0[0].max() - dir0[0].min()
    dy = dir0[1].max() - dir0[1].min()
    LOG.debug('dx, dy = %s, %s'%(dx, dy))
    dx_fraction = dx / dx_total
    dy_fraction = dy / dy_total
    LOG.debug('fraction = %s, %s'%(dx_fraction, dy_fraction))

    # Heuristics of observing pattern
    # Here, slope and extent of directions in the first segment 
    # are examined. If slope is almost same in the segment (i.e.,
    # straight line) and extent of the segment is significant
    # with respect to total map extent, the observing pattern
    # is regarded as 'raster'.
    israster = (slope_std / abs(slope_mean) < 0.01) \
               and (max(dx_fraction, dy_fraction) > 0.34)

    return israster


class MsCalibrationTypeHeuristics(api.Heuristic):
    """
    Return appropriate calibration type by examining
    STATE subtable.
    """
    def calculate(self, filename):
        """
        Return calibration type, which is determined
        by examining STATE subtable.
        """
        caltype = 'none'

        with casa_tools.TableReader(filename) as tb:
            statetable = tb.getkeyword('STATE').lstrip('Table: ')
        if os.path.exists(statetable):
            with casa_tools.TableReader(statetable) as tb:
                obsmodes = tb.getcol( 'OBS_MODE' )
                obsmode = obsmodes[0]
            if ( obsmode.find( 'PSWITCH' ) != -1 ):
                caltype = 'ps'
            elif ( obsmode.find( 'FSWITCH' ) != -1 ):
                caltype = 'fs'
            else:
                import re
                regex = '^OBSERVE_TARGET[#,_](ON|OFF)_SOURCE'
                found = False
                for obsmode in obsmodes:
                    if re.match(regex, obsmode) is not None:
                        found = True
                        break
                if found:
                    caltype = 'ps'  # 'otf'

        return caltype


class AsdmCalibrationTypeHeuristics(api.Heuristic):
    """Determine single-dish calibration type by inspecting ASDM Scan table."""

    def calculate(self, filename: str) -> str:
        """Determine calibration type from ASDM Scan table.

        Attempts reading via pyasdm to support both XML and binary MIME tables.
        Falls back to xml.etree.ElementTree if pyasdm parsing fails or is unavailable.

        Args:
            filename: Path to ASDM directory.

        Returns:
            Calibration type ('ps' or 'none').
        """
        caltype = 'none'

        try:
            import pyasdm

            asdm = pyasdm.ASDM()
            scan_table = asdm.getScan()
            try:
                scan_table.setFromFile(filename)
                for row in scan_table.get():
                    intents = [str(x) for x in row.getScanIntent()]
                    if any('OBSERVE_TARGET' in intent for intent in intents):
                        return 'ps'
                return 'none'
            except Exception:
                xml_path = os.path.join(filename, 'Scan.xml')
                if os.path.exists(xml_path):
                    with open(xml_path, 'r', encoding='utf-8') as f:
                        scan_table.fromXML(f.read())
                    for row in scan_table.get():
                        intents = [str(x) for x in row.getScanIntent()]
                        if any('OBSERVE_TARGET' in intent for intent in intents):
                            return 'ps'
                    return 'none'
        except Exception:
            pass

        scan_table_xml = os.path.join(filename, 'Scan.xml')
        if os.path.exists(scan_table_xml):
            try:
                import xml.etree.ElementTree as ElementTree

                tree = ElementTree.parse(scan_table_xml)
                for node in tree.findall('.//scanIntent'):
                    if node.text and 'OBSERVE_TARGET' in node.text:
                        return 'ps'
            except Exception:
                pass

        return caltype

