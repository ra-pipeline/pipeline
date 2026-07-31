import collections
import os
import shutil

import pipeline.infrastructure.renderer.basetemplates as basetemplates
import pipeline.infrastructure.renderer.logger as logger


SourceSummaryRow = collections.namedtuple('SourceSummaryRow', 'source spw_summary roi_summary')
ArtifactLink = collections.namedtuple('ArtifactLink', 'label href')
PlotLink = collections.namedtuple(
    'PlotLink', 'field spw href thumbnail positive_roi_ranges evidence_status'
)
PlotGroup = collections.namedtuple('PlotGroup', 'field plots')

FINDROI_THUMBNAIL_SIZE = '500x376'


class T2_4MDetailsFindROIRenderer(basetemplates.T2_4MDetailsDefaultRenderer):
    def __init__(self, uri='findroi.mako', description='Detect spectral-line regions of interest',
                 always_rerender=False):
        super().__init__(uri=uri, description=description, always_rerender=always_rerender)

    def update_mako_context(self, mako_context, pipeline_context, results):
        result = results[0]
        weblog_dir = os.path.join(pipeline_context.report_dir, f'stage{result.stage_number}')
        os.makedirs(weblog_dir, exist_ok=True)

        selected_spws = result.summary.get('n_selected_spws', result.summary.get('n_spws', 0))
        successful_spws = result.summary.get('n_successful_spws', result.summary.get('n_spws', 0))
        failed_spws = result.summary.get('n_failed_spws', 0)
        spw_summary = f'{selected_spws}/{successful_spws}/{failed_spws}'
        summary_rows = [
            SourceSummaryRow(
                row.get('source', ''),
                spw_summary,
                f"{row.get('n_roi_with_lines', 0)}/{row.get('n_roi_with_continuum', 0)}",
            )
            for row in result.summary.get('source_summaries', [])
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
        roi_dat_ranges = self._read_roi_dat_ranges(result.artifacts.get('roi_dat'))
        for field, spw_plots in sorted(summary_plots.items()):
            for spw_key, paths in sorted(spw_plots.items(), key=lambda item: int(item[0])):
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
                else:
                    href, thumbnail = None, None
                spw = str(paths.get('spw_id', spw_key))
                plot_links.append(
                    PlotLink(
                        field,
                        spw,
                        href,
                        thumbnail,
                        roi_dat_ranges.get((field, spw), []),
                        paths.get('evidence_status'),
                    )
                )

        plot_groups = []
        for plot in plot_links:
            if not plot_groups or plot_groups[-1].field != plot.field:
                plot_groups.append(PlotGroup(plot.field, []))
            plot_groups[-1].plots.append(plot)

        all_no_valid_source_spw = bool(plot_links) and all(
            plot.evidence_status == 'no_valid_source_spw' for plot in plot_links
        )
        no_valid_source_spw = (
            not any(plot.href for plot in plot_links)
            and (
                not int(result.summary.get('n_source_spws', 0))
                or all_no_valid_source_spw
            )
        )
        plot_message = (
            'No valid field/SPW combinations were available for plotting.'
            if no_valid_source_spw else None
        )

        mako_context.update({
            'summary_rows': summary_rows,
            'artifact_links': artifact_links,
            'plot_links': plot_links,
            'plot_groups': plot_groups,
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
        thumbnail_path = logger.Plot.create_thumbnail(full_path, thumbnail_size=FINDROI_THUMBNAIL_SIZE)
        thumbnail = os.path.relpath(thumbnail_path, report_dir)
        return href, thumbnail

    @staticmethod
    def _read_roi_dat_ranges(path):
        if not path or not os.path.exists(path):
            return {}

        ranges = {}
        field = None
        spw = None
        with open(path, encoding='ascii') as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith('Field: '):
                    field = line[len('Field: '):]
                    spw = None
                elif line.startswith('SpectralWindow: '):
                    spw = line[len('SpectralWindow: '):]
                    ranges[(field, spw)] = []
                elif field is not None and spw is not None:
                    ranges[(field, spw)].append(T2_4MDetailsFindROIRenderer._format_roi_dat_range(line))
        return ranges

    @staticmethod
    def _format_roi_dat_range(line):
        """Shorten displayed ROI frequency bounds without changing ROI.dat."""
        if line == 'NONE':
            return line

        frequency, separator, suffix = line.partition('GHz')
        if not separator or '~' not in frequency:
            return line

        lower, _, upper = frequency.partition('~')

        def truncate(value):
            whole, decimal, fraction = value.partition('.')
            return f'{whole}{decimal}{fraction[:5]}' if decimal else value

        return f'{truncate(lower)} ~ {truncate(upper)} GHz{suffix}'
