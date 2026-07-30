import collections
import os
import shutil

import pipeline.infrastructure.renderer.basetemplates as basetemplates
import pipeline.infrastructure.renderer.logger as logger


SummaryRow = collections.namedtuple('SummaryRow', 'metric value')
ArtifactLink = collections.namedtuple('ArtifactLink', 'label href')
PlotLink = collections.namedtuple('PlotLink', 'source href thumbnail')


class T2_4MDetailsFindROIRenderer(basetemplates.T2_4MDetailsDefaultRenderer):
    def __init__(self, uri='findroi.mako', description='Detect spectral-line regions of interest',
                 always_rerender=False):
        super().__init__(uri=uri, description=description, always_rerender=always_rerender)

    def update_mako_context(self, mako_context, pipeline_context, results):
        result = results[0]
        weblog_dir = os.path.join(pipeline_context.report_dir, f'stage{result.stage_number}')
        os.makedirs(weblog_dir, exist_ok=True)

        summary_rows = [
            SummaryRow('Sources', result.summary.get('n_sources', 0)),
            SummaryRow('Selected science SPWs', result.summary.get('n_selected_spws', result.summary.get('n_spws', 0))),
            SummaryRow('Successful science SPWs', result.summary.get('n_successful_spws', result.summary.get('n_spws', 0))),
            SummaryRow('Failed science SPWs', result.summary.get('n_failed_spws', 0)),
            SummaryRow('Source/SPW products', result.summary.get('n_source_spws', 0)),
            SummaryRow('Products with line ROI', result.summary.get('n_roi_with_lines', 0)),
            SummaryRow('Products with continuum ranges', result.summary.get('n_roi_with_continuum', 0)),
            SummaryRow('Total runtime (s)', result.summary.get('total_run_s', '')),
        ]

        artifact_links = []
        for label, key in (
            ('Full stage product pickle', 'results_pickle'),
            ('FindROI products tar', 'findroi_products_tar'),
            ('ROI.dat', 'roi_dat'),
            ('ROIcont.dat', 'roi_cont_dat'),
        ):
            href = self._copy_artifact(result.artifacts.get(key), weblog_dir, pipeline_context.report_dir)
            if href:
                artifact_links.append(ArtifactLink(label, href))

        plot_links = []
        summary_plots = result.artifacts.get('summary_plots') or {}
        for source, paths in sorted(summary_plots.items()):
            # Keep all generated plots in the stage output, but only expose the
            # evidence spectrum in the main weblog view.
            for path in (
                paths.get('spectra_png'),
                paths.get('moment0_png'),
            ):
                self._copy_artifact(path, weblog_dir, pipeline_context.report_dir)

            evidence = self._copy_plot(
                paths.get('evidence_png'), weblog_dir, pipeline_context.report_dir
            )
            if evidence:
                href, thumbnail = evidence
                plot_links.append(PlotLink(source, href, thumbnail))

        no_valid_source_spw = (
            not plot_links
            and (
                not int(result.summary.get('n_source_spws', 0))
                or any(
                    paths.get('evidence_status') == 'no_valid_source_spw'
                    for paths in summary_plots.values()
                )
            )
        )
        plot_message = (
            'No valid source/SPW combinations were available for plotting.'
            if no_valid_source_spw else None
        )

        mako_context.update({
            'summary_rows': summary_rows,
            'artifact_links': artifact_links,
            'plot_links': plot_links,
            'plot_message': plot_message,
            'errors': result.errors,
        })

    @staticmethod
    def _copy_artifact(path, weblog_dir, report_dir):
        if not path or not os.path.exists(path):
            return None
        dest = os.path.join(weblog_dir, os.path.basename(path))
        if os.path.abspath(path) != os.path.abspath(dest):
            shutil.copy2(path, dest)
        return os.path.relpath(dest, report_dir)

    @staticmethod
    def _copy_plot(path, weblog_dir, report_dir):
        href = T2_4MDetailsFindROIRenderer._copy_artifact(path, weblog_dir, report_dir)
        if href is None:
            return None

        full_path = os.path.join(report_dir, href)
        thumbnail_path = logger.Plot.create_thumbnail(full_path)
        thumbnail = os.path.relpath(thumbnail_path, report_dir)
        return href, thumbnail
