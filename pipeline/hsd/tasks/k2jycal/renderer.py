"""Renderer for k2jycal task."""
from __future__ import annotations

import collections
import os
import re
import shutil
from typing import TYPE_CHECKING, Any
import urllib.parse

from numpy import percentile

import pipeline.infrastructure.renderer.basetemplates as basetemplates
import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.utils as utils
from pipeline.hsd.tasks.common import qautils
from pipeline.hsd.tasks.common import utils as sdutils
from . import display as display

if TYPE_CHECKING:
    from pipeline.infrastructure.launcher import Context
    from pipeline.infrastructure.basetask import ResultsList
    from pipeline.hsd.tasks.k2jycal.k2jycal import SDK2JyCalResults

LOG = logging.get_logger(__name__)

JyperKTRV = collections.namedtuple('JyperKTRV', 'virtualspw msname realspw antenna pol factor')
JyperKTR  = collections.namedtuple('JyperKTR',  'spw msname antenna pol factor')


class T2_4MDetailsSingleDishK2JyCalRenderer(basetemplates.T2_4MDetailsDefaultRenderer):
    """Weblog renderer class for k2jycal task."""

    def __init__(self, uri: str = 'hsd_k2jycal.mako',
                 description: str = 'Generate Kelvin to Jy calibration table.',
                 always_rerender: bool = False) -> None:
        """Initialize T2_4MDetailsSingleDishK2JyCalRenderer instance.

        Args:
            template: Name of Mako template file. Defaults to 'hsd_k2jycal.mako'.
            description: Description of the task. This is embedded into the task detail page.
                         Defaults to 'Generate Kelvin to Jy calibration table.'.
            always_rerender: Always rerender the page if True. Defaults to False.
        """
        super().__init__(
            uri=uri, description=description, always_rerender=always_rerender)

    @qautils.sort_qascores
    def render(self, context: Context, result: SDK2JyCalResults) -> str:
        """
        Custom renderer for hsd_k2jycal()

        This method sorts the QAScores with their scores, and renders the weblog,

        Args:
            context: Pipeline context
            result:  SDK2JyCalResults object
        Returns:
            Rendered html document
        """
        # This method modifies the result object,
        # but the changes do not propergate to the original result or context,
        # since they are local in render() thanks to the mechanism of PL infrastructure.
        # Therefore there is no need to bracket the aggregation process
        # with stashing and recovering the original result.qa.pool here.

        return super().render(context, result)

    def update_mako_context(self, ctx: dict[str, Any], context: Context, results: ResultsList) -> None:
        """Update context for weblog rendering.

        Args:
            ctx: Context for weblog rendering
            context: Pipeline context
            results: ResultsList instance. Should hold a list of SDK2JyCalResults instance.
        """
        spw_data = {}
        ms_list = []
        reffile_list = []
        spw_tr = collections.defaultdict(list)

        dovirtual = sdutils.require_virtual_spw_id_handling(context.observing_run)
        trfunc_r = lambda vsp, vis, rsp, ant, pol, factor: JyperKTR(rsp, vis, ant, pol, factor)
        trfunc_v = lambda vsp, vis, rsp, ant, pol, factor: JyperKTRV(vsp, vis, rsp, ant, pol, factor)
        trfunc = trfunc_v if dovirtual else trfunc_r

        # Process each calibration result.
        for r in results:
            ms = context.observing_run.get_ms(name=r.vis)
            ms_label = ms.basename
            ms_list.append(ms_label)
            spw_list = list(ms.get_spectral_windows(science_windows_only=True))
            antennas = list(ms.get_antenna())
            factors_data = r.factors

            for spw in spw_list:
                spwid = spw.id
                vspwid = context.observing_run.real2virtual_spw_id(spwid, ms)
                # Initialize spw_data entry if needed.
                if vspwid not in spw_data:
                    spw_data[vspwid] = {
                        "spw_obj": spw,
                        "all_factors": [],
                        "ms_dict": collections.defaultdict(list),
                        "outliers": []
                    }
                ddid = ms.get_data_description(spw=spwid)
                # Get polarization labels.
                corrs = [ddid.get_polarization_label(i) for i in range(ddid.num_polarizations)]
                for ant in antennas:
                    ant_name = ant.name
                    for corr in corrs:
                        factor = self.__get_factor(factors_data, ms_label, spwid, ant_name, corr)
                        if factor is not None:
                            spw_data[vspwid]["ms_dict"][ms_label].append((factor, corr, ant_name))
                            spw_data[vspwid]["all_factors"].append(factor)
                        # Always record the transformation, using a default if factor is None.
                        jyperk = '{:.3f}'.format(round(factor, 3)) if factor is not None else 'N/A (1.0)'
                        spw_tr[vspwid].append(trfunc(vspwid, ms_label, spwid, ant_name, corr, jyperk))
            reffile_list.append(r.reffile)
        reffile_list = list(dict.fromkeys(reffile_list))

        # Compute stats and flag outliers for each SPW.
        for spw_id, spw_info in spw_data.items():
            if not spw_info["all_factors"]:
                continue
            stats = self.__calculate_stats(spw_info["all_factors"])
            upper, lower = stats["upper_limit"], stats["lower_limit"]
            for ms_label, factor_list in spw_info["ms_dict"].items():
                for factor, corr, ant in factor_list:
                    if factor < lower or factor > upper:
                        spw_info["outliers"].append((ms_label, factor))

        stage_dir = os.path.join(context.report_dir, f'stage{results.stage_number}')
        reffile_copied_list = []
        for reffile in reffile_list:
            if reffile is not None and os.path.exists(reffile):
                LOG.debug('copying %s to %s', reffile, stage_dir)
                shutil.copy2(reffile, stage_dir)
                reffile_copied_list.append(os.path.join(stage_dir, os.path.basename(reffile)))
        reffile_copied = None if not reffile_copied_list else reffile_copied_list
        plots = []
        if any(len(info["ms_dict"]) > 0 for info in spw_data.values()):
            task = display.K2JyBoxScatterDisplay(stage_dir, spw_data, ms_list)
            plots.extend(task.plot())

        # Merge transformation rows for display.
        row_values = []
        for factor_list in spw_tr.values():
            row_values.extend(factor_list)

        # analyse getjyperkalma log and emit warnings if needed
        extra_logrecords_handler = logging.CapturingHandler(logging.WARNING)
        logging.add_handler(extra_logrecords_handler)
        try:
            casalog_path = os.path.join(stage_dir, "casapy.log")
            if casalog_path and os.path.exists(casalog_path):
                with open(casalog_path, 'r') as f:
                    db_error_message_key = "Failed to load URL: https://"
                    msgs = filter(lambda line: db_error_message_key in line, f)
                    db_error_urls = map(
                        lambda line: re.search(
                            "Failed to load URL: (https://[^ ]+)", line
                        ).group(1),
                        map(lambda line: line.rstrip(), msgs)
                    )
                    # extract unique URLs while preserving the original order
                    for url in dict.fromkeys(db_error_urls).keys():
                        asdm_uid = re.search(
                            "uid://[^ ]+",
                            urllib.parse.unquote(url)
                        )
                        if asdm_uid:
                            asdm_uid = asdm_uid.group(0)
                            endpoint_url = url.split("?")[0]
                            LOG.warning(
                                f"Jy/K DB access failed for EB {asdm_uid}, "
                                f"endpoint URL {endpoint_url}"
                            )
        except Exception as e:
            LOG.warning(
                "Error occurred while analyzing casapy.log "
                f"for Jy/K DB access errors: {e}"
            )
        finally:
            logging.remove_handler(extra_logrecords_handler)
            extra_logrecords = extra_logrecords_handler.buffer
            # Since Mako template reverses the order of log records,
            # order of the log records is reversed here to make them
            # appear in the original order in the rendered page.
            extra_logrecords.reverse()

        # Update the context with tables, plots, and additional info.
        ctx.update({
            'jyperk_rows': utils.merge_td_columns(row_values),
            'reffile_list': reffile_copied,
            'jyperk_plot': plots,
            'dovirtual': dovirtual,
            'extra_logrecords': extra_logrecords,
        })

    @staticmethod
    def __calculate_stats(values: list = [], whis: float = 1.5) -> dict[str, float]:
        """ Helper to compute statistical metrics for a given list of factors.

        Args:
            values: A list of numeric factor values.
            whis:  The position of the whiskers.
                   The lower whisker is at the lowest datum above Q1 - whis*(Q3-Q1),
                   and the upper whisker at the highest datum below Q3 + whis*(Q3-Q1),
                   where Q1 and Q3 are the first and third quartiles.
                   Defaults to 1.5

        Returns:
            A dictionary containing:
                - "upper_limit" (float): The upper fence of the values = Q3 + (1.5 * IQR)
                - "lower_limit" (float): The lower fence of the values = Q1 – (1.5 * IQR)
        """
        q1 = percentile(values, 25)
        q3 = percentile(values, 75)
        iqr = q3 - q1
        low = q1 - whis * iqr
        up = q3 + whis * iqr
        return {
            "upper_limit": up,
            "lower_limit": low
        }

    @staticmethod
    def __get_factor(
        factor_dict: dict[str, dict[int, dict[str, dict[str, float]]]],
        vis: str, spwid: int, ant_name: str, pol_name: str
    ) -> float | None:
        """Return Jy/K conversion factor for given meta data.

        Returns a factor corresponding to vis, spwid, ant_name, and pol_name from
        a factor_dict[vis][spwid][ant_name][pol_name] = factor
        If factor_dict lack corresponding factor, the method returns None.

        Args:
            factor_dict: Jy/K factors with meta data
            vis: Name of MS
            spwid: Spectral window id
            ant_name: Name of antenna
            pol_name: Polarization type

        Returns:
            Conversion factor for given meta data. If no corresponding factor
            exists in factor_dict, None is returned.
        """
        if (vis not in factor_dict or
                spwid not in factor_dict[vis] or
                ant_name not in factor_dict[vis][spwid] or
                pol_name not in factor_dict[vis][spwid][ant_name]):
            return None
        return factor_dict[vis][spwid][ant_name][pol_name]
