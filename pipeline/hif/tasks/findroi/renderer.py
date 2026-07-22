import collections
import os
import shutil

import pipeline.infrastructure.renderer.basetemplates as basetemplates


SummaryRow = collections.namedtuple('SummaryRow', 'metric value')
ArtifactLink = collections.namedtuple('ArtifactLink', 'label href')
PlotLink = collections.namedtuple('PlotLink', 'source label href')


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
        for source, paths in sorted((result.artifacts.get('summary_plots') or {}).items()):
            for label, path in (
                ('Spectra', paths.get('spectra_png')),
                ('Moment 0', paths.get('moment0_png')),
                ('Evidence', paths.get('evidence_png')),
            ):
                href = self._copy_artifact(path, weblog_dir, pipeline_context.report_dir)
                if href:
                    plot_links.append(PlotLink(source, label, href))

        mako_context.update({
            'summary_rows': summary_rows,
            'artifact_links': artifact_links,
            'plot_links': plot_links,
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
