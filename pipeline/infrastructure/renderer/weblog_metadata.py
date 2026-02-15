"""Weblog metadata helpers for renderer fast paths."""

from __future__ import annotations

import dataclasses
import json
import os
from types import SimpleNamespace
from typing import Any

from pipeline.infrastructure.renderer import logger


@dataclasses.dataclass
class PlotMetadata:
    """Serializable plot metadata."""

    path: str
    x_axis: str
    y_axis: str
    parameters: dict[str, Any]
    thumbnail_check: bool = True

    @classmethod
    def from_plot(cls, plot: logger.Plot, report_dir: str) -> PlotMetadata:
        """Create PlotMetadata from a Plot instance."""
        rel_path = os.path.relpath(plot.abspath, report_dir)
        return cls(
            path=rel_path,
            x_axis=plot.x_axis,
            y_axis=plot.y_axis,
            parameters=dict(plot.parameters),
            thumbnail_check=plot.thumbnail_check,
        )

    def to_plot(self, report_dir: str) -> logger.Plot:
        """Reconstruct a Plot from metadata."""
        abspath = os.path.join(report_dir, self.path)
        return logger.Plot(
            abspath,
            x_axis=self.x_axis,
            y_axis=self.y_axis,
            parameters=self.parameters,
            thumbnail_check=self.thumbnail_check,
        )


@dataclasses.dataclass
class T2_1DetailsMetadata:
    """Serializable metadata for T2_1DetailsRenderer."""

    report_dir: str
    telescope: str
    ms_basename: str
    ms_session: str
    ms_correlator_name: str | None
    science_sources: str
    calibrators: str
    all_bands: str
    science_bands: str
    baseline_min: Any
    baseline_max: Any
    num_antennas: int
    num_baselines: int
    ant_diameters: str
    time_start: str
    time_end: str
    time_on_source: str
    time_on_science: str
    dirname: str
    weather_plot: PlotMetadata | None
    pwv_plot: PlotMetadata | None
    azel_plot: PlotMetadata | None
    el_vs_time_plot: PlotMetadata | None
    intent_vs_time: PlotMetadata | None
    field_vs_time: PlotMetadata | None
    spwid_vs_freq: PlotMetadata | None
    zd_telmjd_plot: PlotMetadata | None
    is_singledish: bool
    pointing_plot: PlotMetadata | None
    el_min: str
    el_max: str
    zd_min: float
    zd_avg: float
    zd_max: float
    telmjd_min: str
    telmjd_avg: str
    telmjd_max: str
    vla_basebands: str

    @classmethod
    def from_display_context(cls, display_context: dict[str, Any]) -> T2_1DetailsMetadata:
        """Build metadata from a display context dict."""
        pcontext = display_context['pcontext']
        ms = display_context['ms']
        report_dir = pcontext.report_dir

        def _plot_meta(plot: logger.Plot | None) -> PlotMetadata | None:
            if plot is None:
                return None
            return PlotMetadata.from_plot(plot, report_dir)

        return cls(
            report_dir=report_dir,
            telescope=pcontext.project_summary.telescope,
            ms_basename=ms.basename,
            ms_session=str(ms.session),
            ms_correlator_name=getattr(ms, 'correlator_name', None),
            science_sources=display_context['science_sources'],
            calibrators=display_context['calibrators'],
            all_bands=display_context['all_bands'],
            science_bands=display_context['science_bands'],
            baseline_min=display_context['baseline_min'],
            baseline_max=display_context['baseline_max'],
            num_antennas=display_context['num_antennas'],
            num_baselines=display_context['num_baselines'],
            ant_diameters=display_context['ant_diameters'],
            time_start=display_context['time_start'],
            time_end=display_context['time_end'],
            time_on_source=display_context['time_on_source'],
            time_on_science=display_context['time_on_science'],
            dirname=display_context['dirname'],
            weather_plot=_plot_meta(display_context['weather_plot']),
            pwv_plot=_plot_meta(display_context['pwv_plot']),
            azel_plot=_plot_meta(display_context['azel_plot']),
            el_vs_time_plot=_plot_meta(display_context['el_vs_time_plot']),
            intent_vs_time=_plot_meta(display_context['intent_vs_time']),
            field_vs_time=_plot_meta(display_context['field_vs_time']),
            spwid_vs_freq=_plot_meta(display_context['spwid_vs_freq']),
            zd_telmjd_plot=_plot_meta(display_context['zd_telmjd_plot']),
            is_singledish=display_context['is_singledish'],
            pointing_plot=_plot_meta(display_context['pointing_plot']),
            el_min=display_context['el_min'],
            el_max=display_context['el_max'],
            zd_min=display_context['zd_min'],
            zd_avg=display_context['zd_avg'],
            zd_max=display_context['zd_max'],
            telmjd_min=display_context['telmjd_min'],
            telmjd_avg=display_context['telmjd_avg'],
            telmjd_max=display_context['telmjd_max'],
            vla_basebands=display_context['vla_basebands'],
        )

    def to_display_context(self) -> dict[str, Any]:
        """Reconstruct display context using lightweight objects."""
        project_summary = SimpleNamespace(telescope=self.telescope)
        pcontext = SimpleNamespace(report_dir=self.report_dir, project_summary=project_summary)
        ms = SimpleNamespace(
            basename=self.ms_basename,
            session=self.ms_session,
            correlator_name=self.ms_correlator_name,
        )

        def _plot(plot_meta: PlotMetadata | None) -> logger.Plot | None:
            if plot_meta is None:
                return None
            return plot_meta.to_plot(self.report_dir)

        return {
            'pcontext': pcontext,
            'ms': ms,
            'science_sources': self.science_sources,
            'calibrators': self.calibrators,
            'all_bands': self.all_bands,
            'science_bands': self.science_bands,
            'baseline_min': self.baseline_min,
            'baseline_max': self.baseline_max,
            'num_antennas': self.num_antennas,
            'ant_diameters': self.ant_diameters,
            'num_baselines': self.num_baselines,
            'time_start': self.time_start,
            'time_end': self.time_end,
            'time_on_source': self.time_on_source,
            'time_on_science': self.time_on_science,
            'intent_vs_time': _plot(self.intent_vs_time),
            'field_vs_time': _plot(self.field_vs_time),
            'spwid_vs_freq': _plot(self.spwid_vs_freq),
            'dirname': self.dirname,
            'weather_plot': _plot(self.weather_plot),
            'pwv_plot': _plot(self.pwv_plot),
            'azel_plot': _plot(self.azel_plot),
            'el_vs_time_plot': _plot(self.el_vs_time_plot),
            'zd_telmjd_plot': _plot(self.zd_telmjd_plot),
            'is_singledish': self.is_singledish,
            'pointing_plot': _plot(self.pointing_plot),
            'el_min': self.el_min,
            'el_max': self.el_max,
            'zd_min': self.zd_min,
            'zd_avg': self.zd_avg,
            'zd_max': self.zd_max,
            'telmjd_min': self.telmjd_min,
            'telmjd_avg': self.telmjd_avg,
            'telmjd_max': self.telmjd_max,
            'vla_basebands': self.vla_basebands,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        data = dataclasses.asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> T2_1DetailsMetadata:
        """Construct from JSON dict."""
        def _plot_data(value: dict[str, Any] | None) -> PlotMetadata | None:
            if value is None:
                return None
            return PlotMetadata(**value)

        data = dict(data)
        data['weather_plot'] = _plot_data(data.get('weather_plot'))
        data['pwv_plot'] = _plot_data(data.get('pwv_plot'))
        data['azel_plot'] = _plot_data(data.get('azel_plot'))
        data['el_vs_time_plot'] = _plot_data(data.get('el_vs_time_plot'))
        data['intent_vs_time'] = _plot_data(data.get('intent_vs_time'))
        data['field_vs_time'] = _plot_data(data.get('field_vs_time'))
        data['spwid_vs_freq'] = _plot_data(data.get('spwid_vs_freq'))
        data['zd_telmjd_plot'] = _plot_data(data.get('zd_telmjd_plot'))
        data['pointing_plot'] = _plot_data(data.get('pointing_plot'))
        return cls(**data)


def _metadata_path(report_dir: str, session: str, ms_basename: str) -> str:
    return os.path.join(report_dir, f'session{session}', ms_basename, 't2-1_details.metadata.json')


def load_t2_1_details_metadata(report_dir: str, session: str, ms_basename: str) -> T2_1DetailsMetadata | None:
    """Load T2_1DetailsRenderer metadata if present."""
    path = _metadata_path(report_dir, session, ms_basename)
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        data = json.load(f)
    return T2_1DetailsMetadata.from_dict(data)


def save_t2_1_details_metadata(metadata: T2_1DetailsMetadata) -> None:
    """Persist T2_1DetailsRenderer metadata to JSON."""
    path = _metadata_path(metadata.report_dir, metadata.ms_session, metadata.ms_basename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(metadata.to_dict(), f, indent=2, default=str)


@dataclasses.dataclass
class T2_2_4Metadata:
    """Serializable metadata for T2_2_4Renderer (Sky Setup)."""

    report_dir: str
    ms_basename: str
    ms_session: str
    dirname: str
    azel_plot: PlotMetadata | None
    suntrack_plot: PlotMetadata | None
    el_vs_time_plot: PlotMetadata | None
    zd_telmjd_plot: PlotMetadata | None
    plot_uv: PlotMetadata | None

    @classmethod
    def from_display_context(cls, display_context: dict[str, Any]) -> T2_2_4Metadata:
        """Build metadata from a display context dict."""
        pcontext = display_context['pcontext']
        ms = display_context['ms']
        report_dir = pcontext.report_dir

        def _plot_meta(plot: logger.Plot | None) -> PlotMetadata | None:
            if plot is None:
                return None
            return PlotMetadata.from_plot(plot, report_dir)

        return cls(
            report_dir=report_dir,
            ms_basename=ms.basename,
            ms_session=str(ms.session),
            dirname=display_context['dirname'],
            azel_plot=_plot_meta(display_context['azel_plot']),
            suntrack_plot=_plot_meta(display_context['suntrack_plot']),
            el_vs_time_plot=_plot_meta(display_context['el_vs_time_plot']),
            zd_telmjd_plot=_plot_meta(display_context['zd_telmjd_plot']),
            plot_uv=_plot_meta(display_context['plot_uv']),
        )

    def to_display_context(self) -> dict[str, Any]:
        """Reconstruct display context using lightweight objects."""
        pcontext = SimpleNamespace(report_dir=self.report_dir)
        ms = SimpleNamespace(basename=self.ms_basename, session=self.ms_session)

        def _plot(plot_meta: PlotMetadata | None) -> logger.Plot | None:
            if plot_meta is None:
                return None
            return plot_meta.to_plot(self.report_dir)

        return {
            'pcontext': pcontext,
            'ms': ms,
            'azel_plot': _plot(self.azel_plot),
            'suntrack_plot': _plot(self.suntrack_plot),
            'el_vs_time_plot': _plot(self.el_vs_time_plot),
            'zd_telmjd_plot': _plot(self.zd_telmjd_plot),
            'plot_uv': _plot(self.plot_uv),
            'dirname': self.dirname,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> T2_2_4Metadata:
        """Construct from JSON dict."""
        def _plot_data(value: dict[str, Any] | None) -> PlotMetadata | None:
            if value is None:
                return None
            return PlotMetadata(**value)

        data = dict(data)
        data['azel_plot'] = _plot_data(data.get('azel_plot'))
        data['suntrack_plot'] = _plot_data(data.get('suntrack_plot'))
        data['el_vs_time_plot'] = _plot_data(data.get('el_vs_time_plot'))
        data['zd_telmjd_plot'] = _plot_data(data.get('zd_telmjd_plot'))
        data['plot_uv'] = _plot_data(data.get('plot_uv'))
        return cls(**data)


@dataclasses.dataclass
class T2_2_6Metadata:
    """Serializable metadata for T2_2_6Renderer (Scans)."""

    report_dir: str
    ms_basename: str
    ms_session: str
    tablerows: list[dict[str, Any]]

    @classmethod
    def from_display_context(cls, display_context: dict[str, Any]) -> T2_2_6Metadata:
        """Build metadata from a display context dict."""
        pcontext = display_context['pcontext']
        ms = display_context['ms']

        rows = []
        for row in display_context['tablerows']:
            rows.append(
                {
                    'id': row.id,
                    'time_start': row.time_start,
                    'time_end': row.time_end,
                    'duration': row.duration,
                    'intents': list(row.intents),
                    'fields': row.fields,
                    'spws': row.spws,
                }
            )

        return cls(
            report_dir=pcontext.report_dir,
            ms_basename=ms.basename,
            ms_session=str(ms.session),
            tablerows=rows,
        )

    def to_display_context(self) -> dict[str, Any]:
        """Reconstruct display context using lightweight objects."""
        pcontext = SimpleNamespace(report_dir=self.report_dir)
        ms = SimpleNamespace(basename=self.ms_basename, session=self.ms_session)
        rows = [SimpleNamespace(**row) for row in self.tablerows]

        return {
            'pcontext': pcontext,
            'ms': ms,
            'tablerows': rows,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> T2_2_6Metadata:
        """Construct from JSON dict."""
        return cls(**data)


def export_t2_1_details_metadata(context: Any) -> None:
    """Export T2_1DetailsRenderer metadata for all measurement sets.

    Args:
        context: Pipeline context object.
    """
    if not hasattr(context, 'observing_run') or context.observing_run is None:
        return

    from pipeline.infrastructure.renderer import htmlrenderer

    for ms in context.observing_run.measurement_sets:
        path = _metadata_path(context.report_dir, str(ms.session), ms.basename)
        if os.path.exists(path):
            continue

        display_context = htmlrenderer.T2_1DetailsRenderer.get_display_context(context, ms)
        metadata = T2_1DetailsMetadata.from_display_context(display_context)
        save_t2_1_details_metadata(metadata)


def _t2_2_4_metadata_path(report_dir: str, session: str, ms_basename: str) -> str:
    return os.path.join(report_dir, f'session{session}', ms_basename, 't2-2-4.metadata.json')


def load_t2_2_4_metadata(report_dir: str, session: str, ms_basename: str) -> T2_2_4Metadata | None:
    """Load T2_2_4Renderer metadata if present."""
    path = _t2_2_4_metadata_path(report_dir, session, ms_basename)
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        data = json.load(f)
    return T2_2_4Metadata.from_dict(data)


def save_t2_2_4_metadata(metadata: T2_2_4Metadata) -> None:
    """Persist T2_2_4Renderer metadata to JSON."""
    path = _t2_2_4_metadata_path(metadata.report_dir, metadata.ms_session, metadata.ms_basename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(metadata.to_dict(), f, indent=2, default=str)


def export_t2_2_4_metadata(context: Any) -> None:
    """Export T2_2_4Renderer metadata for all measurement sets."""
    if not hasattr(context, 'observing_run') or context.observing_run is None:
        return

    from pipeline.infrastructure.renderer import htmlrenderer

    for ms in context.observing_run.measurement_sets:
        path = _t2_2_4_metadata_path(context.report_dir, str(ms.session), ms.basename)
        if os.path.exists(path):
            continue

        display_context = htmlrenderer.T2_2_4Renderer.get_display_context(context, ms)
        metadata = T2_2_4Metadata.from_display_context(display_context)
        save_t2_2_4_metadata(metadata)


def _t2_2_6_metadata_path(report_dir: str, session: str, ms_basename: str) -> str:
    return os.path.join(report_dir, f'session{session}', ms_basename, 't2-2-6.metadata.json')


def load_t2_2_6_metadata(report_dir: str, session: str, ms_basename: str) -> T2_2_6Metadata | None:
    """Load T2_2_6Renderer metadata if present."""
    path = _t2_2_6_metadata_path(report_dir, session, ms_basename)
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        data = json.load(f)
    return T2_2_6Metadata.from_dict(data)


def save_t2_2_6_metadata(metadata: T2_2_6Metadata) -> None:
    """Persist T2_2_6Renderer metadata to JSON."""
    path = _t2_2_6_metadata_path(metadata.report_dir, metadata.ms_session, metadata.ms_basename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(metadata.to_dict(), f, indent=2, default=str)


def export_t2_2_6_metadata(context: Any) -> None:
    """Export T2_2_6Renderer metadata for all measurement sets."""
    if not hasattr(context, 'observing_run') or context.observing_run is None:
        return

    from pipeline.infrastructure.renderer import htmlrenderer

    for ms in context.observing_run.measurement_sets:
        path = _t2_2_6_metadata_path(context.report_dir, str(ms.session), ms.basename)
        if os.path.exists(path):
            continue

        display_context = htmlrenderer.T2_2_6Renderer.get_display_context(context, ms)
        metadata = T2_2_6Metadata.from_display_context(display_context)
        save_t2_2_6_metadata(metadata)


@dataclasses.dataclass
class T2_2_1Metadata:
    """Serializable metadata for T2_2_1Renderer (Spatial Setup)."""

    report_dir: str
    ms_basename: str
    ms_session: str
    pointings: list[dict[str, Any]]

    @classmethod
    def from_display_context(cls, display_context: dict[str, Any]) -> T2_2_1Metadata:
        """Build metadata from a display context dict."""
        pcontext = display_context['pcontext']
        ms = display_context['ms']
        report_dir = pcontext.report_dir

        def _plot_meta(plot: logger.Plot | None) -> PlotMetadata | None:
            if plot is None:
                return None
            return PlotMetadata.from_plot(plot, report_dir)

        pointings_data = []
        for source, plots in display_context['pointings']:
            pointings_data.append({
                'source_id': source.id,
                'source_name': source.name,
                'plots': [_plot_meta(p) for p in plots if p is not None],
            })

        return cls(
            report_dir=report_dir,
            ms_basename=ms.basename,
            ms_session=str(ms.session),
            pointings=pointings_data,
        )

    def to_display_context(self) -> dict[str, Any]:
        """Reconstruct display context using lightweight objects."""
        pcontext = SimpleNamespace(report_dir=self.report_dir)
        ms = SimpleNamespace(basename=self.ms_basename, session=self.ms_session)

        def _plot(plot_meta: PlotMetadata | None) -> logger.Plot | None:
            if plot_meta is None:
                return None
            return plot_meta.to_plot(self.report_dir)

        pointings = []
        for item in self.pointings:
            source = SimpleNamespace(id=item['source_id'], name=item['source_name'])
            plots = [_plot(pm) for pm in item['plots']]
            pointings.append((source, plots))

        return {
            'pcontext': pcontext,
            'ms': ms,
            'pointings': pointings,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> T2_2_1Metadata:
        """Construct from JSON dict."""
        def _plot_data(value: dict[str, Any] | None) -> PlotMetadata | None:
            if value is None:
                return None
            return PlotMetadata(**value)

        data = dict(data)
        for pointing in data.get('pointings', []):
            pointing['plots'] = [_plot_data(p) for p in pointing['plots']]
        return cls(**data)


def _t2_2_1_metadata_path(report_dir: str, session: str, ms_basename: str) -> str:
    return os.path.join(report_dir, f'session{session}', ms_basename, 't2-2-1.metadata.json')


def load_t2_2_1_metadata(report_dir: str, session: str, ms_basename: str) -> T2_2_1Metadata | None:
    """Load T2_2_1Renderer metadata if present."""
    path = _t2_2_1_metadata_path(report_dir, session, ms_basename)
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        data = json.load(f)
    return T2_2_1Metadata.from_dict(data)


def save_t2_2_1_metadata(metadata: T2_2_1Metadata) -> None:
    """Persist T2_2_1Renderer metadata to JSON."""
    path = _t2_2_1_metadata_path(metadata.report_dir, metadata.ms_session, metadata.ms_basename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(metadata.to_dict(), f, indent=2, default=str)


def export_t2_2_1_metadata(context: Any) -> None:
    """Export T2_2_1Renderer metadata for all measurement sets."""
    if not hasattr(context, 'observing_run') or context.observing_run is None:
        return

    from pipeline.infrastructure.renderer import htmlrenderer

    for ms in context.observing_run.measurement_sets:
        path = _t2_2_1_metadata_path(context.report_dir, str(ms.session), ms.basename)
        if os.path.exists(path):
            continue

        display_context = htmlrenderer.T2_2_1Renderer.get_display_context(context, ms)
        metadata = T2_2_1Metadata.from_display_context(display_context)
        save_t2_2_1_metadata(metadata)


@dataclasses.dataclass
class T2_2_3Metadata:
    """Serializable metadata for T2_2_3Renderer (Antenna Setup)."""

    report_dir: str
    ms_basename: str
    ms_session: str
    dirname: str
    plot_ants: PlotMetadata | None
    plot_ants_plog: PlotMetadata | None
    plot_uv: PlotMetadata | None

    @classmethod
    def from_display_context(cls, display_context: dict[str, Any]) -> T2_2_3Metadata:
        """Build metadata from a display context dict."""
        pcontext = display_context['pcontext']
        ms = display_context['ms']
        report_dir = pcontext.report_dir

        def _plot_meta(plot: logger.Plot | None) -> PlotMetadata | None:
            if plot is None:
                return None
            return PlotMetadata.from_plot(plot, report_dir)

        return cls(
            report_dir=report_dir,
            ms_basename=ms.basename,
            ms_session=str(ms.session),
            dirname=display_context['dirname'],
            plot_ants=_plot_meta(display_context.get('plot_ants')),
            plot_ants_plog=_plot_meta(display_context.get('plot_ants_plog')),
            plot_uv=_plot_meta(display_context.get('plot_uv')),
        )

    def to_display_context(self) -> dict[str, Any]:
        """Reconstruct display context using lightweight objects."""
        pcontext = SimpleNamespace(report_dir=self.report_dir)
        ms = SimpleNamespace(basename=self.ms_basename, session=self.ms_session)

        def _plot(plot_meta: PlotMetadata | None) -> logger.Plot | None:
            if plot_meta is None:
                return None
            return plot_meta.to_plot(self.report_dir)

        return {
            'pcontext': pcontext,
            'ms': ms,
            'dirname': self.dirname,
            'plot_ants': _plot(self.plot_ants),
            'plot_ants_plog': _plot(self.plot_ants_plog),
            'plot_uv': _plot(self.plot_uv),
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> T2_2_3Metadata:
        """Construct from JSON dict."""
        def _plot_data(value: dict[str, Any] | None) -> PlotMetadata | None:
            if value is None:
                return None
            return PlotMetadata(**value)

        data = dict(data)
        data['plot_ants'] = _plot_data(data.get('plot_ants'))
        data['plot_ants_plog'] = _plot_data(data.get('plot_ants_plog'))
        data['plot_uv'] = _plot_data(data.get('plot_uv'))
        return cls(**data)


def _t2_2_3_metadata_path(report_dir: str, session: str, ms_basename: str) -> str:
    return os.path.join(report_dir, f'session{session}', ms_basename, 't2-2-3.metadata.json')


def load_t2_2_3_metadata(report_dir: str, session: str, ms_basename: str) -> T2_2_3Metadata | None:
    """Load T2_2_3Renderer metadata if present."""
    path = _t2_2_3_metadata_path(report_dir, session, ms_basename)
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        data = json.load(f)
    return T2_2_3Metadata.from_dict(data)


def save_t2_2_3_metadata(metadata: T2_2_3Metadata) -> None:
    """Persist T2_2_3Renderer metadata to JSON."""
    path = _t2_2_3_metadata_path(metadata.report_dir, metadata.ms_session, metadata.ms_basename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(metadata.to_dict(), f, indent=2, default=str)


def export_t2_2_3_metadata(context: Any) -> None:
    """Export T2_2_3Renderer metadata for all measurement sets."""
    if not hasattr(context, 'observing_run') or context.observing_run is None:
        return

    from pipeline.infrastructure.renderer import htmlrenderer

    for ms in context.observing_run.measurement_sets:
        path = _t2_2_3_metadata_path(context.report_dir, str(ms.session), ms.basename)
        if os.path.exists(path):
            continue

        display_context = htmlrenderer.T2_2_3Renderer.get_display_context(context, ms)
        metadata = T2_2_3Metadata.from_display_context(display_context)
        save_t2_2_3_metadata(metadata)


@dataclasses.dataclass
class T2_2_7Metadata:
    """Serializable metadata for T2_2_7Renderer (Single Dish Pointing)."""

    report_dir: str
    ms_basename: str
    ms_session: str
    dirname: str
    target_pointing: list[PlotMetadata]
    whole_pointing: list[PlotMetadata]
    offset_pointing: list[PlotMetadata]

    @classmethod
    def from_display_context(cls, display_context: dict[str, Any]) -> T2_2_7Metadata:
        """Build metadata from a display context dict."""
        pcontext = display_context['pcontext']
        ms = display_context['ms']
        report_dir = pcontext.report_dir

        def _plot_meta(plot: logger.Plot | None) -> PlotMetadata | None:
            if plot is None:
                return None
            return PlotMetadata.from_plot(plot, report_dir)

        return cls(
            report_dir=report_dir,
            ms_basename=ms.basename,
            ms_session=str(ms.session),
            dirname=display_context['dirname'],
            target_pointing=[_plot_meta(p) for p in display_context['target_pointing'] if p is not None],
            whole_pointing=[_plot_meta(p) for p in display_context['whole_pointing'] if p is not None],
            offset_pointing=[_plot_meta(p) for p in display_context['offset_pointing'] if p is not None],
        )

    def to_display_context(self) -> dict[str, Any]:
        """Reconstruct display context using lightweight objects."""
        pcontext = SimpleNamespace(report_dir=self.report_dir)
        ms = SimpleNamespace(basename=self.ms_basename, session=self.ms_session)

        def _plot(plot_meta: PlotMetadata | None) -> logger.Plot | None:
            if plot_meta is None:
                return None
            return plot_meta.to_plot(self.report_dir)

        return {
            'pcontext': pcontext,
            'ms': ms,
            'dirname': self.dirname,
            'target_pointing': [_plot(pm) for pm in self.target_pointing],
            'whole_pointing': [_plot(pm) for pm in self.whole_pointing],
            'offset_pointing': [_plot(pm) for pm in self.offset_pointing],
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> T2_2_7Metadata:
        """Construct from JSON dict."""
        def _plot_data(value: dict[str, Any] | None) -> PlotMetadata | None:
            if value is None:
                return None
            return PlotMetadata(**value)

        data = dict(data)
        data['target_pointing'] = [_plot_data(p) for p in data['target_pointing']]
        data['whole_pointing'] = [_plot_data(p) for p in data['whole_pointing']]
        data['offset_pointing'] = [_plot_data(p) for p in data['offset_pointing']]
        return cls(**data)


def _t2_2_7_metadata_path(report_dir: str, session: str, ms_basename: str) -> str:
    return os.path.join(report_dir, f'session{session}', ms_basename, 't2-2-7.metadata.json')


def load_t2_2_7_metadata(report_dir: str, session: str, ms_basename: str) -> T2_2_7Metadata | None:
    """Load T2_2_7Renderer metadata if present."""
    path = _t2_2_7_metadata_path(report_dir, session, ms_basename)
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        data = json.load(f)
    return T2_2_7Metadata.from_dict(data)


def save_t2_2_7_metadata(metadata: T2_2_7Metadata) -> None:
    """Persist T2_2_7Renderer metadata to JSON."""
    path = _t2_2_7_metadata_path(metadata.report_dir, metadata.ms_session, metadata.ms_basename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(metadata.to_dict(), f, indent=2, default=str)


def export_t2_2_7_metadata(context: Any) -> None:
    """Export T2_2_7Renderer metadata for all measurement sets."""
    if not hasattr(context, 'observing_run') or context.observing_run is None:
        return

    from pipeline.infrastructure.renderer import htmlrenderer

    for ms in context.observing_run.measurement_sets:
        path = _t2_2_7_metadata_path(context.report_dir, str(ms.session), ms.basename)
        if os.path.exists(path):
            continue

        display_context = htmlrenderer.T2_2_7Renderer.get_display_context(context, ms)
        metadata = T2_2_7Metadata.from_display_context(display_context)
        save_t2_2_7_metadata(metadata)


# =============================================================================
# Metadata classes for data-only renderers (T1 series, T2 navigation)
# =============================================================================

@dataclasses.dataclass
class T1_1RendererMetadata:
    """Metadata for T1_1Renderer (OUS Splash Page) - data only, no plots."""

    report_dir: str
    rendered_at: str

    @classmethod
    def from_display_context(cls, display_context: dict[str, Any]) -> T1_1RendererMetadata:
        """Build metadata from display context."""
        return cls(
            report_dir=display_context['pcontext'].report_dir,
            rendered_at=display_context['pcontext'].timestamp.isoformat()
            if hasattr(display_context['pcontext'], 'timestamp')
            else '',
        )

    def to_display_context(self) -> dict[str, Any]:
        """Reconstruct display context from metadata."""
        return SimpleNamespace(cached=True)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON dict."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> T1_1RendererMetadata:
        """Deserialize from JSON dict."""
        return cls(**data)


@dataclasses.dataclass
class T1_2RendererMetadata:
    """Metadata for T1_2Renderer (Observation Summary) - data only."""

    report_dir: str
    rendered_at: str

    @classmethod
    def from_display_context(cls, display_context: dict[str, Any]) -> T1_2RendererMetadata:
        """Build metadata from display context."""
        return cls(
            report_dir=display_context['pcontext'].report_dir,
            rendered_at=display_context['pcontext'].timestamp.isoformat()
            if hasattr(display_context['pcontext'], 'timestamp')
            else '',
        )

    def to_display_context(self) -> dict[str, Any]:
        """Reconstruct display context from metadata."""
        return SimpleNamespace(cached=True)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON dict."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> T1_2RendererMetadata:
        """Deserialize from JSON dict."""
        return cls(**data)


@dataclasses.dataclass
class T1_3MRendererMetadata:
    """Metadata for T1_3MRenderer (By Topic) - data only."""

    report_dir: str
    rendered_at: str

    @classmethod
    def from_display_context(cls, display_context: dict[str, Any]) -> T1_3MRendererMetadata:
        """Build metadata from display context."""
        return cls(
            report_dir=display_context['pcontext'].report_dir,
            rendered_at=display_context['pcontext'].timestamp.isoformat()
            if hasattr(display_context['pcontext'], 'timestamp')
            else '',
        )

    def to_display_context(self) -> dict[str, Any]:
        """Reconstruct display context from metadata."""
        return SimpleNamespace(cached=True)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON dict."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> T1_3MRendererMetadata:
        """Deserialize from JSON dict."""
        return cls(**data)


@dataclasses.dataclass
class T1_4MRendererMetadata:
    """Metadata for T1_4MRenderer (Task Summary) - data only."""

    report_dir: str
    rendered_at: str

    @classmethod
    def from_display_context(cls, display_context: dict[str, Any]) -> T1_4MRendererMetadata:
        """Build metadata from display context."""
        return cls(
            report_dir=display_context['pcontext'].report_dir,
            rendered_at=display_context['pcontext'].timestamp.isoformat()
            if hasattr(display_context['pcontext'], 'timestamp')
            else '',
        )

    def to_display_context(self) -> dict[str, Any]:
        """Reconstruct display context from metadata."""
        return SimpleNamespace(cached=True)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON dict."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> T1_4MRendererMetadata:
        """Deserialize from JSON dict."""
        return cls(**data)


@dataclasses.dataclass
class T2_1RendererMetadata:
    """Metadata for T2_1Renderer (Session Tree) - data only."""

    report_dir: str
    rendered_at: str

    @classmethod
    def from_display_context(cls, display_context: dict[str, Any]) -> T2_1RendererMetadata:
        """Build metadata from display context."""
        return cls(
            report_dir=display_context['pcontext'].report_dir,
            rendered_at=display_context['pcontext'].timestamp.isoformat()
            if hasattr(display_context['pcontext'], 'timestamp')
            else '',
        )

    def to_display_context(self) -> dict[str, Any]:
        """Reconstruct display context from metadata."""
        return SimpleNamespace(cached=True)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON dict."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> T2_1RendererMetadata:
        """Deserialize from JSON dict."""
        return cls(**data)


@dataclasses.dataclass
class T2_2_2RendererMetadata:
    """Metadata for T2_2_2Renderer (Spectral Setup)."""

    report_dir: str
    ms_basename: str
    ms_session: str
    show_science_windows: bool
    show_all_windows: bool
    rendered_at: str

    @classmethod
    def from_display_context(cls, display_context: dict[str, Any]) -> T2_2_2RendererMetadata:
        """Build metadata from display context."""
        col_info = display_context.get('show_online_spec_avg_col', {})
        return cls(
            report_dir=display_context['pcontext'].report_dir,
            ms_basename=display_context['ms'].basename,
            ms_session=str(display_context['ms'].session),
            show_science_windows=getattr(col_info, 'science_windows', False),
            show_all_windows=getattr(col_info, 'all_windows', False),
            rendered_at=display_context['pcontext'].timestamp.isoformat()
            if hasattr(display_context['pcontext'], 'timestamp')
            else '',
        )

    def to_display_context(self) -> dict[str, Any]:
        """Reconstruct display context from metadata."""
        return SimpleNamespace(
            show_online_spec_avg_col=SimpleNamespace(
                science_windows=self.show_science_windows,
                all_windows=self.show_all_windows,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON dict."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> T2_2_2RendererMetadata:
        """Deserialize from JSON dict."""
        return cls(**data)


@dataclasses.dataclass
class T2_4MRendererMetadata:
    """Metadata for T2_4MRenderer (Task Tree) - data only."""

    report_dir: str
    rendered_at: str

    @classmethod
    def from_display_context(cls, display_context: dict[str, Any]) -> T2_4MRendererMetadata:
        """Build metadata from display context."""
        return cls(
            report_dir=display_context['pcontext'].report_dir,
            rendered_at=display_context['pcontext'].timestamp.isoformat()
            if hasattr(display_context['pcontext'], 'timestamp')
            else '',
        )

    def to_display_context(self) -> dict[str, Any]:
        """Reconstruct display context from metadata."""
        return SimpleNamespace(cached=True)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON dict."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> T2_4MRendererMetadata:
        """Deserialize from JSON dict."""
        return cls(**data)


@dataclasses.dataclass
class T2_4MDetailsRendererMetadata:
    """Metadata for T2_4MDetailsRenderer (Task Details orchestrator)."""

    report_dir: str
    rendered_at: str

    @classmethod
    def from_display_context(cls, display_context: dict[str, Any]) -> T2_4MDetailsRendererMetadata:
        """Build metadata from display context."""
        return cls(
            report_dir=display_context['pcontext'].report_dir,
            rendered_at=display_context['pcontext'].timestamp.isoformat()
            if hasattr(display_context['pcontext'], 'timestamp')
            else '',
        )

    def to_display_context(self) -> dict[str, Any]:
        """Reconstruct display context from metadata."""
        return SimpleNamespace(cached=True)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON dict."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> T2_4MDetailsRendererMetadata:
        """Deserialize from JSON dict."""
        return cls(**data)


# =============================================================================
# Load/save/export functions for data-only renderers
# =============================================================================

def _t1_1_metadata_path(report_dir: str) -> str:
    return os.path.join(report_dir, 't1-1.metadata.json')


def load_t1_1_metadata(report_dir: str) -> T1_1RendererMetadata | None:
    """Load T1_1Renderer metadata if present."""
    path = _t1_1_metadata_path(report_dir)
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        data = json.load(f)
    return T1_1RendererMetadata.from_dict(data)


def save_t1_1_metadata(metadata: T1_1RendererMetadata) -> None:
    """Persist T1_1Renderer metadata to JSON."""
    path = _t1_1_metadata_path(metadata.report_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(metadata.to_dict(), f, indent=2, default=str)


def export_t1_1_metadata(context: Any) -> None:
    """Export T1_1Renderer metadata."""
    path = _t1_1_metadata_path(context.report_dir)
    if os.path.exists(path):
        return

    from pipeline.infrastructure.renderer import htmlrenderer

    display_context = htmlrenderer.T1_1Renderer.get_display_context(context)
    metadata = T1_1RendererMetadata.from_display_context(display_context)
    save_t1_1_metadata(metadata)


def _t1_2_metadata_path(report_dir: str) -> str:
    return os.path.join(report_dir, 't1-2.metadata.json')


def load_t1_2_metadata(report_dir: str) -> T1_2RendererMetadata | None:
    """Load T1_2Renderer metadata if present."""
    path = _t1_2_metadata_path(report_dir)
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        data = json.load(f)
    return T1_2RendererMetadata.from_dict(data)


def save_t1_2_metadata(metadata: T1_2RendererMetadata) -> None:
    """Persist T1_2Renderer metadata to JSON."""
    path = _t1_2_metadata_path(metadata.report_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(metadata.to_dict(), f, indent=2, default=str)


def export_t1_2_metadata(context: Any) -> None:
    """Export T1_2Renderer metadata."""
    path = _t1_2_metadata_path(context.report_dir)
    if os.path.exists(path):
        return

    from pipeline.infrastructure.renderer import htmlrenderer

    display_context = htmlrenderer.T1_2Renderer.get_display_context(context)
    metadata = T1_2RendererMetadata.from_display_context(display_context)
    save_t1_2_metadata(metadata)


def _t1_3m_metadata_path(report_dir: str) -> str:
    return os.path.join(report_dir, 't1-3.metadata.json')


def load_t1_3m_metadata(report_dir: str) -> T1_3MRendererMetadata | None:
    """Load T1_3MRenderer metadata if present."""
    path = _t1_3m_metadata_path(report_dir)
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        data = json.load(f)
    return T1_3MRendererMetadata.from_dict(data)


def save_t1_3m_metadata(metadata: T1_3MRendererMetadata) -> None:
    """Persist T1_3MRenderer metadata to JSON."""
    path = _t1_3m_metadata_path(metadata.report_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(metadata.to_dict(), f, indent=2, default=str)


def export_t1_3m_metadata(context: Any) -> None:
    """Export T1_3MRenderer metadata."""
    path = _t1_3m_metadata_path(context.report_dir)
    if os.path.exists(path):
        return

    from pipeline.infrastructure.renderer import htmlrenderer

    display_context = htmlrenderer.T1_3MRenderer.get_display_context(context)
    metadata = T1_3MRendererMetadata.from_display_context(display_context)
    save_t1_3m_metadata(metadata)


def _t1_4m_metadata_path(report_dir: str) -> str:
    return os.path.join(report_dir, 't1-4.metadata.json')


def load_t1_4m_metadata(report_dir: str) -> T1_4MRendererMetadata | None:
    """Load T1_4MRenderer metadata if present."""
    path = _t1_4m_metadata_path(report_dir)
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        data = json.load(f)
    return T1_4MRendererMetadata.from_dict(data)


def save_t1_4m_metadata(metadata: T1_4MRendererMetadata) -> None:
    """Persist T1_4MRenderer metadata to JSON."""
    path = _t1_4m_metadata_path(metadata.report_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(metadata.to_dict(), f, indent=2, default=str)


def export_t1_4m_metadata(context: Any) -> None:
    """Export T1_4MRenderer metadata."""
    path = _t1_4m_metadata_path(context.report_dir)
    if os.path.exists(path):
        return

    from pipeline.infrastructure.renderer import htmlrenderer

    display_context = htmlrenderer.T1_4MRenderer.get_display_context(context)
    metadata = T1_4MRendererMetadata.from_display_context(display_context)
    save_t1_4m_metadata(metadata)


def _t2_1_metadata_path(report_dir: str) -> str:
    return os.path.join(report_dir, 't2-1.metadata.json')


def load_t2_1_metadata(report_dir: str) -> T2_1RendererMetadata | None:
    """Load T2_1Renderer metadata if present."""
    path = _t2_1_metadata_path(report_dir)
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        data = json.load(f)
    return T2_1RendererMetadata.from_dict(data)


def save_t2_1_metadata(metadata: T2_1RendererMetadata) -> None:
    """Persist T2_1Renderer metadata to JSON."""
    path = _t2_1_metadata_path(metadata.report_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(metadata.to_dict(), f, indent=2, default=str)


def export_t2_1_metadata(context: Any) -> None:
    """Export T2_1Renderer metadata."""
    path = _t2_1_metadata_path(context.report_dir)
    if os.path.exists(path):
        return

    from pipeline.infrastructure.renderer import htmlrenderer

    display_context = htmlrenderer.T2_1Renderer.get_display_context(context)
    metadata = T2_1RendererMetadata.from_display_context(display_context)
    save_t2_1_metadata(metadata)


def _t2_2_2_metadata_path(report_dir: str, session: str, ms_basename: str) -> str:
    return os.path.join(report_dir, f'session{session}', ms_basename, 't2-2-2.metadata.json')


def load_t2_2_2_metadata(report_dir: str, session: str, ms_basename: str) -> T2_2_2RendererMetadata | None:
    """Load T2_2_2Renderer metadata if present."""
    path = _t2_2_2_metadata_path(report_dir, session, ms_basename)
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        data = json.load(f)
    return T2_2_2RendererMetadata.from_dict(data)


def save_t2_2_2_metadata(metadata: T2_2_2RendererMetadata) -> None:
    """Persist T2_2_2Renderer metadata to JSON."""
    path = _t2_2_2_metadata_path(metadata.report_dir, metadata.ms_session, metadata.ms_basename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(metadata.to_dict(), f, indent=2, default=str)


def export_t2_2_2_metadata(context: Any) -> None:
    """Export T2_2_2Renderer metadata for all measurement sets."""
    if not hasattr(context, 'observing_run') or context.observing_run is None:
        return

    from pipeline.infrastructure.renderer import htmlrenderer

    for ms in context.observing_run.measurement_sets:
        path = _t2_2_2_metadata_path(context.report_dir, str(ms.session), ms.basename)
        if os.path.exists(path):
            continue

        display_context = htmlrenderer.T2_2_2Renderer.get_display_context(context, ms)
        metadata = T2_2_2RendererMetadata.from_display_context(display_context)
        save_t2_2_2_metadata(metadata)


def _t2_4m_metadata_path(report_dir: str) -> str:
    return os.path.join(report_dir, 't2-4m.metadata.json')


def load_t2_4m_metadata(report_dir: str) -> T2_4MRendererMetadata | None:
    """Load T2_4MRenderer metadata if present."""
    path = _t2_4m_metadata_path(report_dir)
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        data = json.load(f)
    return T2_4MRendererMetadata.from_dict(data)


def save_t2_4m_metadata(metadata: T2_4MRendererMetadata) -> None:
    """Persist T2_4MRenderer metadata to JSON."""
    path = _t2_4m_metadata_path(metadata.report_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(metadata.to_dict(), f, indent=2, default=str)


def export_t2_4m_metadata(context: Any) -> None:
    """Export T2_4MRenderer metadata."""
    path = _t2_4m_metadata_path(context.report_dir)
    if os.path.exists(path):
        return

    from pipeline.infrastructure.renderer import htmlrenderer

    display_context = htmlrenderer.T2_4MRenderer.get_display_context(context)
    metadata = T2_4MRendererMetadata.from_display_context(display_context)
    save_t2_4m_metadata(metadata)


def _t2_4m_details_metadata_path(report_dir: str) -> str:
    return os.path.join(report_dir, 't2-4m_details.metadata.json')


def load_t2_4m_details_metadata(report_dir: str) -> T2_4MDetailsRendererMetadata | None:
    """Load T2_4MDetailsRenderer metadata if present."""
    path = _t2_4m_details_metadata_path(report_dir)
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        data = json.load(f)
    return T2_4MDetailsRendererMetadata.from_dict(data)


def save_t2_4m_details_metadata(metadata: T2_4MDetailsRendererMetadata) -> None:
    """Persist T2_4MDetailsRenderer metadata to JSON."""
    path = _t2_4m_details_metadata_path(metadata.report_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(metadata.to_dict(), f, indent=2, default=str)


def export_t2_4m_details_metadata(context: Any) -> None:
    """Export T2_4MDetailsRenderer metadata."""
    path = _t2_4m_details_metadata_path(context.report_dir)
    if os.path.exists(path):
        return
    
    # Note: T2_4MDetailsRenderer is an orchestrator that doesn't have get_display_context
    # It delegates to task-specific renderers. We just mark that it was rendered.
    metadata = T2_4MDetailsRendererMetadata(
        report_dir=context.report_dir,
        rendered_at=context.timestamp.isoformat()
        if hasattr(context, 'timestamp')
        else '',
    )
    save_t2_4m_details_metadata(metadata)
