from . import CacheHandler
from functools import lru_cache

from pipeline.infrastructure import casa_tools, casa_tasks


class VLA_CacheHandler(CacheHandler):
    """
    Derived cache handler for VLA-specific computations.
    Implements cached properties for expensive methods.
    """
    def __init__(self):
        pass

    @staticmethod
    @lru_cache(maxsize=64)
    def run_flagdata(vis, mode='', field='', spw='', intent='', display='', flagbackup=False, savepars=False):
        task_args = {'vis': vis,
                     'mode': mode,
                     'field': field,
                     'spw': spw,
                     'intent': intent,
                     'display': display,
                     'flagbackup': flagbackup,
                     'savepars': savepars}
        task = casa_tasks.flagdata(**task_args)
        result = task.execute()
        return result

    @staticmethod
    @lru_cache(maxsize=16)
    def compute_refant_output(vis, field, spw, intent, geometry, flagging, refantignore=None):
        """Compute and cache the reference antenna output."""

        # import is done here to avoid importing
        # 'MeasurementSet' from partially initialized module
        import pipeline.hif.heuristics.findrefant as findrefant

        refantobj = findrefant.RefAntHeuristics(
            vis=vis,
            field=field,
            geometry=geometry,
            flagging=flagging,
            intent=intent,
            spw=spw,
            refantignore=refantignore
        )
        return refantobj.calculate()

    @staticmethod
    @lru_cache(maxsize=128)
    def _read_single_column(table_path, column):
        """Read and cache a single column from disk."""
        with casa_tools.TableReader(table_path) as table:
            data = table.getcol(column)
            return data

    @classmethod
    def get_columndata(cls, table_path, columns):
        """
        Return one or more columns.
        Each column is read individually and cached automatically.
        """
        if isinstance(columns, str):
            columns = [columns]

        result = {}
        for col in columns:
            # Each column read will use lru_cache
            result[col] = cls._read_single_column(table_path, col)
        return result
