"""Module to define data type.

Classes:
    DataType: An Enum class to define data type.
"""
# Do not evaluate type annotations at definition time.
from __future__ import annotations

from enum import Enum, auto, unique
from operator import attrgetter


@unique
class DataType(Enum):
    """Enumeration of data types used in the pipeline.

    Attributes:
        RAW: Raw, unprocessed data.
        REGCAL_CONTLINE_ALL: Regular calibrated data for all scans.
        BASELINED: Data after spectral baseline subtraction.
        ATMCORR: Data corrected for residual atmospheric effects.
        REGCAL_CONT_SCIENCE: Regular calibrated continuum-only data for target scans.
        SELFCAL_CONT_SCIENCE: Self-calibrated continuum-only data for target scans.
        REGCAL_CONTLINE_SCIENCE: Regular calibrated data for target scans.
        SELFCAL_CONTLINE_SCIENCE: Self-calibrated data for target scans.
        REGCAL_LINE_SCIENCE: Regular calibrated spectral line data.
        SELFCAL_LINE_SCIENCE: Self-calibrated spectral line data.
    """
    RAW = auto()
    REGCAL_CONTLINE_ALL = auto()
    ATMCORR = auto()
    BASELINED = auto()
    REGCAL_CONTLINE_SCIENCE = auto()
    SELFCAL_CONTLINE_SCIENCE = auto()
    REGCAL_CONT_SCIENCE = auto()
    SELFCAL_CONT_SCIENCE = auto()
    REGCAL_LINE_SCIENCE = auto()
    SELFCAL_LINE_SCIENCE = auto()

    @staticmethod
    def get_specmode_datatypes(intent: str, specmode: str) -> list[DataType]:
        """
        Return valid datatypes for given intent and specmode.

        Return the list of valid datatypes depending on the intent and specmode,
        in order of preference for the automatic choice of datatype (if not
        manually overridden).

        Args:
            intent: Intent to select datatypes for.
            specmode: Spectral gridding type to select datatypes for.

        Returns:
            List of valid datatypes for given intent and specmode.
        """
        if intent == 'TARGET':
            if specmode == 'mfs':
                # The preferred data types are SELFCAL_CONTLINE_SCIENCE and REGCAL_CONTLINE_SCIENCE.
                # The remaining fallback values are just there to support experimental usage of
                # the first set of MSes.
                specmode_datatypes = [DataType.SELFCAL_CONTLINE_SCIENCE, DataType.REGCAL_CONTLINE_SCIENCE,
                                      DataType.REGCAL_CONTLINE_ALL, DataType.RAW]
            elif specmode == 'cont':
                # The preferred data types are SELFCAL_CONTLINE_SCIENCE and REGCAL_CONTLINE_SCIENCE.
                # For VLA, also SELFCAL_CONT_SCIENCE and REGCAL_CONT_SCIENCE.
                # The remaining fallback values are just there to support experimental usage of
                # the first set of MSes.
                specmode_datatypes = [DataType.SELFCAL_CONT_SCIENCE, DataType.REGCAL_CONT_SCIENCE,
                                      DataType.SELFCAL_CONTLINE_SCIENCE, DataType.REGCAL_CONTLINE_SCIENCE,
                                      DataType.REGCAL_CONTLINE_ALL, DataType.RAW]
            else:
                # The preferred data types for cube and repBW specmodes are SELFCAL_LINE_SCIENCE and
                # REGCAL_LINE_SCIENCE. The remaining fallback values are just there to support
                # experimental usage of the first and second sets of MSes.
                specmode_datatypes = [DataType.SELFCAL_LINE_SCIENCE, DataType.REGCAL_LINE_SCIENCE,
                                      DataType.SELFCAL_CONTLINE_SCIENCE, DataType.REGCAL_CONTLINE_SCIENCE,
                                      DataType.REGCAL_CONTLINE_ALL, DataType.RAW]
        else:
            # Calibrators are only present in the first set of MSes.
            # Thus listing only their possible data types.
            specmode_datatypes = [DataType.REGCAL_CONTLINE_ALL, DataType.RAW]
        return specmode_datatypes

    @staticmethod
    def get_short_datatype_desc(datatype_str: str) -> str:
        """
        Return a short summary string for weblog purposes.
        """
        if datatype_str == 'RAW':
            return '<span style="background-color:lightgray;">RAW</span>'
        elif 'REGCAL' in datatype_str:
            return '<span style="background-color:lightblue;">REGCAL</span>'
        elif 'SELFCAL' in datatype_str:
            return '<span style="background-color:palegreen;">SELFCAL</span>'
        else:
            return 'UNKNOWN'


TYPE_PRIORITY_ORDER = sorted(DataType.__members__.values(), key=attrgetter('value'))
