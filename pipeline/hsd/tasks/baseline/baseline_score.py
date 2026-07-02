import datetime
import pathlib
import time

from casatools import version_string as cversion

import pipeline.extern.sd_baseline_qa.sd_baseline_qa as sd_baseline_qa
import pipeline.extern.sd_baseline_qa.sd_qa_reports as sd_qa_reports

import pipeline.infrastructure as infrastructure

from pipeline.extern.sd_baseline_qa.sd_qa_utils import FailedAnalysisException

LOG = infrastructure.get_logger(__name__)

def _science_lines(context, results)->list:
    """
    Parse context and results to extract relevant science lines.
    Args:
        context: single-dish pipeline context
        results: a list of results data related to the current baseline pass

    Returns: science lines list

    """
    reduction_group = context.observing_run.ms_reduction_group

    outcome_data = [lines["channelmap_range"] for lines in results.outcome["baselined"]]
    lines  = [
        (sub_list.field_name, sub_reduction_group.spw_id, lines) for lines, sub_list in zip(outcome_data, reduction_group.values()) for sub_reduction_group in sub_list
    ]

    return lines


def baseline_score(
        results,
        context,
        file_info
)-> None | dict[str, list]:
    """

    Args:
        results: SDBaselineResults
        context: Data structure containing pertinent run and results information.
        file_info: This is the baseline ms file that is used for analysis adn the original ms name as a tuple.

    Returns: None | Dict

    """

    start_time = time.time()
    casa_version = cversion()

    #  You can get the MeasurementSet name from `context.observing_run.measurement_sets(list).basename` which is a list or
    #  infile = result.outcome.outfile    gives the equivalent _bl file that tht qa code seems to accept.
    #  output directory = context.out_dir
    #  products directory = context.product_dir
    #  html/report directory = context.report_dir

    basename, baseline_file = file_info
    line_data = _science_lines(context, results)

    if line_data is None:
        LOG.error("Science line data not found; Baseline QA heuristic for XX-YY profiles canceled")
        return None

    # Generally, pipeline operates in the current working directory, so we will use that as the working path.
    working_path = pathlib.Path.cwd().resolve()
    LOG.debug(f"Current working directory: %s", working_path)

    date_time = datetime.datetime.now(datetime.UTC).strftime("%Y%d%mT%H%M%SD%f")

    plot_path = pathlib.Path(context.report_dir).joinpath(f"stage{context.task_counter}").joinpath(f"baseline_qa_plots_{date_time}")

    # This should always exist but incase
    plot_path.mkdir(parents=True, exist_ok=True)
    weblog_path = context.report_dir

    try:
        qa_score, antenna_names, plots_function_names = sd_baseline_qa.get_ms_baseline_qascores(
            ms_name = baseline_file,
            sci_line_data=line_data,
            plot_output_path=str(plot_path),
            weblog_output_path=str(weblog_path),
            buffer_data=False,
            basename = basename
        )

        elapsed_time = (time.time() - start_time) / 60.0

        sd_qa_reports.addFLSLentry_bl(
            qascore_list=qa_score,
            output_file=working_path.joinpath(".prototype_qa_score.csv"),
            dtime_min=elapsed_time
        )

        sd_qa_reports.makeSummaryTable_bl(
            qascore_list=qa_score,
            antnames_for=antenna_names,
            plots_fnames=plots_function_names,
            plfolder=str(working_path),
            plot_folder=str(plot_path),
            output_file=str(working_path.joinpath(f"qa_score_summary_{date_time}.csv")),
            writemode="w",
            weblog_adress=""
        )
    except FailedAnalysisException:
        plot_path.rmdir()
        return None

    # except Exception as error:
    #     LOG.error(f"There was an unknown critical error in baseline_score: {error}")
    #     plot_path.rmdir()
    #     return None

    return {"score": qa_score, "plot_names" :plots_function_names}
