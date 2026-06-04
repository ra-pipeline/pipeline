from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from pipeline.domain.datatype import DataType

if TYPE_CHECKING:
    from numpy import ndarray


def get_ms_data_types_from_history(msgs: ndarray) -> tuple[dict, dict]:
    """Retrieve the original datatype lookup dictionaries from MS HISTORY table entries.

    Args:
        msgs: HISTORY table message as numpy array

    Returns:
        datatype per column dictionary
        datatype per source and spw dictionary
    """
    # Define some dictionaries representing the datatypes as strings
    data_type_per_column_strtypes = {}
    found_data_type_per_column = False
    data_types_per_source_and_spw_strtypes = {}
    found_data_types_per_source_and_spw = False

    # Search backwards from latest messages since the datatype information is
    # written multiple times as new history entries throughout the pipeline processing.
    for item in reversed(msgs):
        if not found_data_type_per_column and 'data_type_per_column' in item:
            data_type_per_column_strtypes = ast.literal_eval(item.split(sep='=', maxsplit=1)[1])
            found_data_type_per_column = True
        if not found_data_types_per_source_and_spw and 'data_types_per_source_and_spw' in item:
            data_types_per_source_and_spw_strtypes = ast.literal_eval(item.split(sep='=', maxsplit=1)[1])
            found_data_types_per_source_and_spw = True
        if found_data_type_per_column and found_data_types_per_source_and_spw:
            break

    # Make actual dictionaries with datatype enums
    if data_type_per_column_strtypes != {}:
        data_type_per_column = dict((DataType[k], v) for k, v in data_type_per_column_strtypes.items())
    else:
        data_type_per_column = dict()

    if data_types_per_source_and_spw_strtypes != {}:
        data_types_per_source_and_spw = dict((k, [DataType[item] for item in v])
                                             for k, v in data_types_per_source_and_spw_strtypes.items())
    else:
        data_types_per_source_and_spw = dict()

    return data_type_per_column, data_types_per_source_and_spw
