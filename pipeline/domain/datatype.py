"""Pydantic-friendly DataType enumeration for Phase 5 modernization."""

from __future__ import annotations

from enum import Enum, auto, unique
from operator import attrgetter


@unique
class DataType(Enum):
    """Enumeration of data types used in the pipeline."""

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
        """Return valid datatypes for given intent and specmode."""
        if intent == 'TARGET':
            if specmode == 'mfs':
                specmode_datatypes = [
                    DataType.SELFCAL_CONTLINE_SCIENCE,
                    DataType.REGCAL_CONTLINE_SCIENCE,
                    DataType.REGCAL_CONTLINE_ALL,
                    DataType.RAW,
                ]
            elif specmode == 'cont':
                specmode_datatypes = [
                    DataType.SELFCAL_CONT_SCIENCE,
                    DataType.REGCAL_CONT_SCIENCE,
                    DataType.SELFCAL_CONTLINE_SCIENCE,
                    DataType.REGCAL_CONTLINE_SCIENCE,
                    DataType.REGCAL_CONTLINE_ALL,
                    DataType.RAW,
                ]
            else:
                specmode_datatypes = [
                    DataType.SELFCAL_LINE_SCIENCE,
                    DataType.REGCAL_LINE_SCIENCE,
                    DataType.SELFCAL_CONTLINE_SCIENCE,
                    DataType.REGCAL_CONTLINE_SCIENCE,
                    DataType.REGCAL_CONTLINE_ALL,
                    DataType.RAW,
                ]
        else:
            specmode_datatypes = [DataType.REGCAL_CONTLINE_ALL, DataType.RAW]
        return specmode_datatypes

    @staticmethod
    def get_short_datatype_desc(datatype_str: str) -> str:
        """Return a short summary string for weblog purposes."""
        if datatype_str == 'RAW':
            return '<span style="background-color:lightgray;">RAW</span>'
        if 'REGCAL' in datatype_str:
            return '<span style="background-color:lightblue;">REGCAL</span>'
        if 'SELFCAL' in datatype_str:
            return '<span style="background-color:palegreen;">SELFCAL</span>'
        return 'UNKNOWN'


TYPE_PRIORITY_ORDER = sorted(DataType.__members__.values(), key=attrgetter('value'))
