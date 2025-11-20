# Do not evaluate type annotations at definition time.
from __future__ import annotations

import contextlib
import copy
import os
from typing import TYPE_CHECKING, Any, TypedDict

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import lines, patches, ticker
from scipy import interpolate

from pipeline import infrastructure
from pipeline.domain import measures, unitformat
from pipeline.h.heuristics.tsysfieldmap import get_intent_to_tsysfield_map
from pipeline.infrastructure import casa_tools, utils

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

    from pipeline.domain import Field, MeasurementSet, Source
    from pipeline.domain.measures import Distance, EquatorialArc

COLORBLIND_PALETTE = {
    'on_tsys': "#FF00E6",
    'off_tsys': "#FF0011",
    '7m': "#1500FA",
    '12m': "#000000",
}
LOG = infrastructure.logging.get_logger(__name__)

# used when deciding primary beam colour
SEVEN_M = measures.Distance(7, measures.DistanceUnits.METRE)
# used to convert frequency to wavelength
C_MKS = 299792458
# used to convert between radians and arcsec
RADIANS_TO_ARCSEC = 180 / np.pi * 60 * 60


class CoordValue(TypedDict):
    unit: str
    value: float


class MDirection(TypedDict):
    m0: CoordValue
    m1: CoordValue
    refer: str
    type: str


def compute_obs_data(
        ms: MeasurementSet,
        fields: list[Field],
        ) -> tuple[np.ndarray, np.ndarray, float, list[Distance], list[float]]:
    """Extract and compute relevant observation data for plotting.

    Args:
        ms: MeasurementSet object.
        fields: A list of Field objects including the non Tsys-only fields.

    Returns:
        ra: RA values in radians for each field related to the source.
        dec: Dec values in radians for each field related to the source.
        median_ref_freq: the median reference wavelength in meters.
        dish_diameters: a list of dish diameters in meters.
        beam_diameters: a list of primary beam diameters in arcsecs.
    """

    median_ref_freq = np.median([
        spw.ref_frequency.to_units(measures.FrequencyUnits.HERTZ)
        for spw in ms.get_spectral_windows(science_windows_only=True)
    ])
    median_ref_wavelength = measures.Distance(C_MKS / median_ref_freq, measures.DistanceUnits.METRE)

    dish_diameters = [measures.Distance(d, measures.DistanceUnits.METRE) for d in {a.diameter for a in ms.antennas}]
    taper = antenna_taper_factor(ms.antenna_array.name)
    beam_diameters = [float(primary_beam_fwhm(median_ref_wavelength, dish_diameter, taper)
                            .to_units(measures.ArcUnits.ARC_SECOND))
                      for dish_diameter in dish_diameters]

    ra = np.array([casa_tools.quanta.convert(f.mdirection['m0']['value'], 'rad')['value'] for f in fields])
    dec = np.array([casa_tools.quanta.convert(f.mdirection['m1']['value'], 'rad')['value'] for f in fields])

    return ra, dec, median_ref_freq, dish_diameters, beam_diameters


def compute_offsets(ra: np.ndarray, dec: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Compute RA/Dec offsets for plotting.

    Args:
        ra: an array of RA values.
        dec: an array of Dec values.

    Returns:
        delta_ra: the RA offsets from the median position.
        delta_dec: the Dec offsets from the median position.
        mean_ra: the median RA values in radians.
        mean_dec: the median Dec values in radians.
    """
    mean_ra = np.arctan2(np.mean(np.sin(ra)), np.mean(np.cos(ra)))
    mean_dec = np.mean(dec)

    delta_ra = np.cos(dec) * np.sin(ra - mean_ra)
    delta_dec = np.sin(dec) * np.cos(mean_dec) - np.cos(dec) * np.sin(mean_dec) * np.cos(ra - mean_ra)

    return delta_ra, delta_dec, mean_ra, mean_dec


def create_figure(
        delta_ra: np.ndarray,
        delta_dec: np.ndarray,
        beam_diameters: list[float],
        margin_x: int = 100,
        margin_y: int = 80,
        dpi: int = 100
        ) -> tuple[Figure, Axes, int]:
    """Initialize a figure with correct dimensions.

    Args:
        delta_ra: a list of offsets in RA from the median position in radians.
        delta_dec: a list of offsets in Dec from the median position in radians.
        beam_diameters: a list of the primary beam diameters in arcsecs.
        margin_x: buffer pixel value in the x-axis.
        margin_y: buffer pixel value in the y-axis.
        dpi: dots per inch value used for the created figure.

    Returns:
        fig: the Figure object.
        ax: the Axes object.
        fontsize: the calculated fontsize used for the plot.
    """
    # some heuristics to determine the appropriate x- and y-range for plotting, adjusting the figure size as needed
    ra_range_arcsec = (delta_ra.max() - delta_ra.min()) * RADIANS_TO_ARCSEC
    dec_range_arcsec = (delta_dec.max() - delta_dec.min()) * RADIANS_TO_ARCSEC

    pixels_per_beam = 60.
    min_size, max_size = 400, 2000
    smallest_beam = min(beam_diameters)  # arcsec
    pixels_x = np.clip(pixels_per_beam * ra_range_arcsec / smallest_beam, min_size, max_size)
    pixels_y = np.clip(pixels_per_beam * dec_range_arcsec / smallest_beam, min_size, max_size)

    fig = plt.figure(figsize=((pixels_x + margin_x) / dpi, (pixels_y + margin_y) / dpi))
    ax = fig.add_subplot(1, 1, 1)
    beam_res = max(ra_range_arcsec / pixels_x, dec_range_arcsec / pixels_y)
    fontsize = 6
    if beam_res > 0:
        fontsize = max(fontsize, min(12, 0.1 * smallest_beam / beam_res))
    return fig, ax, fontsize


def add_elements_to_plot(
        ax: Axes,
        plot_dict: dict[str, dict[str, dict[int, dict[str, Any]] | float]],
        fontsize: int = 10,
        draw_labels: bool = False
        ) -> tuple[dict[str, lines.Line2D], dict[str, str]]:
    """Plot element circles and labels

    Args:
        ax: the Axes object containing information related to the x- and y- plot axes.
        plot_dict: dictionary containing field information for each dish diameter used for plotting.
        fontsize: the size used for the text information printed on the figure.
        draw_labels: indicates whether the field/scan number is printed or just a '+' at the circle center.

    Returns:
        legend_labels: dictionary containing label information for the plotted elements.
        legend_colors: dictionary containing color information for the plotted elements.
    """
    legend_labels, legend_colors = {}, {}

    for values in plot_dict.values():
        beam_diameter = values['beam diameter']
        if 'tsys scans' in values.keys():
            for intent, scans_dict in values['tsys scans'].items():
                color = COLORBLIND_PALETTE['off_tsys'] if intent == 'OFF' else COLORBLIND_PALETTE['on_tsys']
                linestyle = 'dotted' if intent == 'OFF' else 'dashed'
                for scan_id, scan_dict in scans_dict.items():
                    x, y = scan_dict['radec']
                    ax.add_patch(patches.Circle((x, y), radius=0.5 * beam_diameter,
                                        facecolor='none', edgecolor=color, linestyle=linestyle, alpha=0.6))

                    if scan_dict['azel offset']:
                        ax.text(x, y, f'{scan_id}', ha='center', va='center', fontsize=fontsize, color=color)
                    else:
                        ax.plot(x, y, marker='+', linestyle='None', color=color, markersize=4)

                if f'Tsys {intent} Scan(s)' not in legend_labels:
                    legend_labels[f'Tsys {intent} Scan(s)'] = lines.Line2D([0], [0], color=color, linewidth=2, linestyle=linestyle)
                    legend_colors[f'Tsys {intent} Scan(s)'] = color
        for key, specs in values['target fields'].items():
            linestyle = 'dotted'
            ax.add_patch(patches.Circle((specs['x'], specs['y']), radius=0.5 * beam_diameter,
                                facecolor='none', edgecolor=specs['color'], linestyle=linestyle, alpha=0.6))

            if draw_labels:
                ax.text(specs['x'], specs['y'], f'{key}',
                        ha='center', va='center', fontsize=fontsize, color=specs['color'])
            else:
                ax.plot(specs['x'], specs['y'], marker='+', linestyle='None', color=specs['color'], markersize=4)

            if specs['label'] not in legend_labels:
                legend_labels[specs['label']] = lines.Line2D(
                    [0], [0], color=specs['color'], linewidth=2, linestyle=linestyle
                    )
                legend_colors[specs['label']] = specs['color']

    return legend_labels, legend_colors


def compute_element_locs(
        fields: list[Field],
        delta_ra: list[float],
        delta_dec: list[float],
        dish_diameters: list[Distance],
        beam_diameters: list[float],
        tsys_scans_dict: dict[int, dict[str, tuple[float, float] | bool]] | None = None,
        ) -> dict[str, dict[str, dict[int, dict[str, Any]] | float]]:
    """Compute the field locations to use for plotting.

    Args:
        fields: A list of Field objects including the non Tsys-only fields.
        delta_ra: A list of offset RA values from the median position in radians.
        delta_dec: A list of offset Dec values from the median position in radians.
        dish_diameters: A list of Distance objects indicating the size of the antennas used for observation.
        beam_diameters: A list of primary beam sizes in arcsecs.
        tsys_scans_dict: A dictionary containing Tsys OFF_SOURCE (and possibly ON_SOURCE) scan information, including
            offset values in arcsecs and whether a horizontal coordinate offset was applied.

    Returns:
        plot_dict: Plot information for the source fields, including location, color, label, and beam diameter.
    """
    plot_dict = {}
    for dish_diameter, beam_diameter in zip(dish_diameters, beam_diameters):
        plot_dict[str(dish_diameter.value)] = {'beam diameter': beam_diameter,
                                               'target fields': {}}
        for field, rel_ra, rel_dec in zip(fields, delta_ra, delta_dec):
            if not is_tsys_only(field):
                field_dict = {
                    'x': rel_ra * RADIANS_TO_ARCSEC,
                    'y': rel_dec * RADIANS_TO_ARCSEC,
                    'color': COLORBLIND_PALETTE['7m'] if dish_diameter == SEVEN_M else COLORBLIND_PALETTE['12m'],
                    'label': f"{dish_diameter} Field(s)",
                    }
                plot_dict[str(dish_diameter.value)]['target fields'][field.id] = field_dict
        if tsys_scans_dict:
            plot_dict[str(dish_diameter.value)]['tsys scans'] = tsys_scans_dict
        # Clean-up dictionary if empty (possible with mixed antenna datasets)
        if not plot_dict[str(dish_diameter.value)]:
            del plot_dict[str(dish_diameter.value)]

    return plot_dict


def configure_labels(
        ax: Axes,
        legend_labels: dict[str, lines.Line2D],
        legend_colors: dict[str, str],
        mean_ra: float,
        mean_dec: float,
        median_ref_freq: float,
        vis: str,
        source_name: str
        ) -> None:
    """Set the plot title and labels.

    Args:
        ax: the Axes object.
        legend_labels: dictionary containing label information for the plotted elements.
        legend_colors: dictionary containing color information for the plotted elements.
        mean_ra: the mean value of the field RA values in radians.
        mean_dec: the mean value of the field Dec values in radians.
        median_ref_freq: the median reference frequency of the observation.
        vis: the name of the measurement set associated with the observation.
        source_name: the name of the source being plotted.

    Returns:
        None: The function updates the Axes object with title and label information and format.
    """
    spacer = '\n' if len(vis) > 50 else ' '
    title_string = f'{vis},{spacer}{source_name}, avg freq.={unitformat.frequency.format(median_ref_freq)}'
    ax.set_title(title_string, size=12)

    ra_string = r'{:02d}$^{{\rm h}}${:02d}$^{{\rm m}}${:02.3f}$^{{\rm s}}$'.format(
        *measures.EquatorialArc(mean_ra % (2*np.pi), measures.ArcUnits.RADIAN).toHms())
    ax.set_xlabel(f'Right ascension offset from {ra_string}')

    dec_string = r'{:02d}$\degree${:02d}$^\prime${:02.1f}$^{{\prime\prime}}$'.format(
        *measures.EquatorialArc(mean_dec, measures.ArcUnits.RADIAN).toDms())
    ax.set_ylabel(f'Declination offset from {dec_string}')

    # Add legend
    legend = ax.legend(legend_labels.values(), legend_labels.keys(), prop={'size': 10}, loc='best', framealpha=0.8)
    for text in legend.get_texts():
        text.set_color(legend_colors[text.get_text()])

    ax.axis('equal')
    arcsec_formatter = ticker.FuncFormatter(label_format)
    ax.xaxis.set_major_formatter(arcsec_formatter)
    ax.yaxis.set_major_formatter(arcsec_formatter)
    ax.xaxis.grid(True, which='major')
    ax.yaxis.grid(True, which='major')
    ax.invert_xaxis()

    # Set plot scale based on Axes data limits
    bbox = ax.dataLim
    x_span = bbox.width
    y_span = bbox.height
    max_range_arcsec = 1.1 * max(x_span, y_span)
    enforce_axis_scale_bounds(ax, min_range_arcsec=2.0, max_range_arcsec=max_range_arcsec)


def plot_mosaic_source(ms: MeasurementSet, source: Source, figfile: str) -> None:
    """
    Produce a plot of the pointings with the primary beam FWHM and field ids.
    Excludes Tsys-only fields per PIPE-52/PIPE-2067

    Args:
        ms: MeasurementSet object.
        source: Source object.
        figfile: file name of the mosaic plot to be created.

    Returns:
        None: The function saves the plot to a file and does not return any value.
    """
    LOG.info("Creating mosaic plot for source %s.", source.name)
    # Retrieve field positions and configurations
    fields = [f for f in source.fields if not is_tsys_only(f)]
    ra, dec, median_ref_freq, dish_diameters, beam_diameters = compute_obs_data(ms, fields)
    delta_ra, delta_dec, mean_ra, mean_dec = compute_offsets(ra, dec)

    # Create mosaic plot
    fig, ax, fontsize = create_figure(delta_ra, delta_dec, beam_diameters)
    draw_field_labels = len(fields) <= 500  # field labels become hard to read if there are too many of them
    plot_dict = compute_element_locs(fields, delta_ra, delta_dec, dish_diameters, beam_diameters)
    legend_labels, legend_colors = add_elements_to_plot(
        ax, plot_dict, fontsize=fontsize, draw_labels=draw_field_labels
        )

    # Add title, legend, and labels
    configure_labels(ax, legend_labels, legend_colors, mean_ra, mean_dec, median_ref_freq, ms.basename, source.name)

    # Adjust title size if necessary
    plt.tight_layout()
    renderer = fig.canvas.get_renderer()
    if ax.title.get_window_extent(renderer).xmax > fig.canvas.get_width_height()[0]:
        ax.title.set_fontsize(10)

    fig.savefig(figfile, dpi=100, bbox_inches='tight')
    plt.close(fig)


def plot_tsys_scans(ms: MeasurementSet, source: Source, figfile: str) -> None:
    """
    Produce a plot of the Tsys scans relative to the target pointings.

    Args:
        ms: MeasurementSet object.
        source: Source object.
        figfile: file name of the Tsys scans plot to be created.

    Returns:
        None: The function saves the plot to a file and does not return any value.
    """
    LOG.info("Creating Tsys plot for source %s.", source.name)
    # Retrieve correct Tsys field for source based on mapping
    tsys_field = select_tsys_field(ms, source)

    # Retrieve TARGET field positions and configurations
    fields = [f for f in source.fields if not is_tsys_only(f)]
    ra, dec, median_ref_freq, dish_diameters, beam_diameters = compute_obs_data(ms, fields)
    delta_ra, delta_dec, mean_ra, mean_dec = compute_offsets(ra, dec)
    mean_direction = radec_to_direction(mean_ra, mean_dec)

    # Calculate Tsys scans offset to apply to plot
    tsys_scans_dict = tsys_scans_radec(ms, mean_direction, tsys_field)

    # Create Tsys scans plot
    fig, ax, fontsize = create_figure(delta_ra, delta_dec, beam_diameters)
    plot_dict = compute_element_locs(fields, delta_ra, delta_dec, dish_diameters, beam_diameters, tsys_scans_dict=tsys_scans_dict)
    legend_labels, legend_colors = add_elements_to_plot(ax, plot_dict, fontsize=fontsize)

    # Add title, legend, and labels
    configure_labels(ax, legend_labels, legend_colors, mean_ra, mean_dec, median_ref_freq, ms.basename, source.name)

    # Adjust title size if necessary
    plt.tight_layout()
    renderer = fig.canvas.get_renderer()
    if ax.title.get_window_extent(renderer).xmax > fig.canvas.get_width_height()[0]:
        ax.title.set_fontsize(10)

    fig.savefig(figfile, dpi=100, bbox_inches='tight')
    plt.close(fig)


def enforce_axis_scale_bounds(
        ax: plt.Axes,
        min_range_arcsec: float = 2.0,
        max_range_arcsec: float = 1000.0
        ) -> None:
    """
    Enforces that the plot's x and y axis ranges are not smaller than `min_range_arcsec`
    and not larger than `max_range_arcsec`.

    Args:
        ax (plt.Axes): The matplotlib Axes object.
        min_range_arcsec (float): Minimum total span in arcseconds (e.g. 2.0 for ±1 arcsec).
        max_range_arcsec (float): Maximum total span in arcseconds (e.g. 1000.0 for ±500 arcsec).
    """
    def adjust_limits(lim):
        center = 0.5 * (lim[0] + lim[1])
        span = abs(lim[1] - lim[0])

        if span < min_range_arcsec:
            half_span = 0.5 * min_range_arcsec
            return (center - half_span, center + half_span)

        if span > max_range_arcsec:
            half_span = 0.5 * max_range_arcsec
            return (center - half_span, center + half_span)

        return lim  # within range, no change

    xlim = ax.get_xlim()
    ylim = ax.get_ylim()

    new_xlim = adjust_limits(xlim)
    new_ylim = adjust_limits(ylim)

    ax.set_xlim(new_xlim)
    ax.set_ylim(new_ylim)


def label_format(x: float, _: Any) -> str:
    """
    Labels plot axes for plots specified in units of arcseconds.

    Args:
        x (float): The tick value in arcseconds.
        _ (Any): The tick position (ignored).

    Returns:
        str: The formatted label string.
    """
    abs_x = abs(x)
    precision = 1  # can parameterize if needed

    if abs_x < 1:
        # Enforce lower bound: round to 1 decimal in arcsec, don't use mas/µas
        formatted = f"{x:.{precision}f}" + r"$^{\prime\prime}$"
    elif abs_x <= 500:
        # Show arcseconds
        formatted = f"{x:.{precision}f}" + r"$^{\prime\prime}$"
    else:
        # Convert to arcmin
        arcmin = x / 60.0
        formatted = f"{arcmin:.{precision}f}" + r"$^\prime$"

    return formatted


def select_tsys_field(
        ms: MeasurementSet,
        source: Source,
        ) -> Field:
    """
    Pick the best-matching Tsys field for a given source.

    Selection order (stop at first non-empty result):
      1) Exact ID match among the source's fields
      2) Exact NAME match among the source's fields (case-insensitive configurable)
      3) Partial NAME match to account for prefix/suffix additions

    Args:
        ms: MeasurementSet object.
        source: Source object.

    Returns:
        A Field object of the associated Tsys field.

    Raises:
        LookupError if no Tsys fields are found or if no Tsys field is matched to the source.
    """
    # Retrieve correct Tsys field for source based on mapping
    is_sd = ms.array_name == 'TP'
    tsys_fields = get_intent_to_tsysfield_map(ms, is_single_dish=is_sd)['TARGET'].split(',')
    if not tsys_fields:
        raise LookupError('No Tsys fields associated with TARGET.')

    # Precompute lookup structures
    src_fields = source.fields
    src_by_id = {f.id: f for f in src_fields}
    src_by_name = {f.name.strip().strip('"'): f for f in src_fields}

    # ID or name match to a source field
    for field_str in tsys_fields:
        field_str_clean = field_str.strip().strip('"')
        if field_str_clean.isdigit() and int(field_str_clean) in src_by_id:
            return src_by_id[int(field_str_clean)]
        if field_str_clean in src_by_name:
            return src_by_name[field_str_clean]
        # PIPE-2869: Partial name match
        for name in src_by_name:
            if name in field_str_clean:
                return ms.get_fields(name=field_str)[0]

    # If truly nothing matched, raise a clear error instead of returning a wrong field silently.
    raise LookupError(f"No Tsys field match for Tsys fields: {tsys_fields}")


def is_tsys_only(field: Field) -> bool:
    """
    Looks at the field intents and determines if it is a Tsys-only field or not.

    Args:
        field: Field object.

    Returns:
        True if the field was only used to observe Tsys else False
    """
    return 'TARGET' not in field.intents and 'ATMOSPHERE' in field.intents


def primary_beam_fwhm(wavelength: Distance, diameter: list[Distance], taper: float) -> EquatorialArc:
    """
    Implements the Baars formula: b*lambda / D.
      if use2007formula==True, use the formula from Baars 2007 book
        (see au.baarsTaperFactor)
      In either case, the taper value is expected to be entered as positive.
        Note: if a negative value is entered, it is converted to positive.
    The effect of the central obstruction on the pattern is also accounted for
    by using a spline fit to Table 10.1 of Schroeder's Astronomical Optics.
    The default values correspond to our best knowledge of the ALMA 12m antennas.
      diameter: outer diameter of the dish in meters
      obscuration: diameter of the central obstruction in meters

    Args:
        wavelength: a Distance object containing the median reference wavelength of the source
        diameter: a list of Distance objects containing the diameters of the dish(es) related to the source
        taper: the primary beam taper factor

    Returns:
        An Equatorial Arc object on the calculated magnitude and units.
    """
    b = baars_taper_factor(taper) * central_obstruction_factor(diameter)
    lambda_m = float(wavelength.to_units(measures.DistanceUnits.METRE))
    diameter_m = float(diameter.to_units(measures.DistanceUnits.METRE))
    return measures.EquatorialArc(b * lambda_m / diameter_m, measures.ArcUnits.RADIAN)


def central_obstruction_factor(diameter: Distance, obscuration: float = 0.75) -> float:
    """
    Computes the scale factor of an Airy pattern as a function of the
    central obscuration, using Table 10.1 of Schroeder's "Astronomical Optics".
    -- Todd Hunter

    Args:
        diameter: a Distance object with outer diameter of the dish in meters
        obscuration: diameter of the central obstruction in meters

    Returns:
        A UnivariateSpline object adjusted by a factor of 1.22.
    """
    epsilon = obscuration / float(diameter.to_units(measures.DistanceUnits.METRE))
    spline_func = interpolate.UnivariateSpline([0, 0.1, 0.2, 0.33, 0.4], [1.22, 1.205, 1.167, 1.098, 1.058], s=0)
    return spline_func(epsilon) / 1.22


def baars_taper_factor(taper_dB: float) -> float:
    """
    Converts a taper in dB to the constant X
    in the formula FWHM=X*lambda/D for the parabolic illumination pattern.
    We assume that taper_dB comes in as a positive value.
    - Todd Hunter

    Args:
        taper_dB: taper factor for the relevant antenna

    Returns:
        the Baars taper factor
    """
    # use Equation 4.13 from Baars 2007 book
    tau = 10 ** (-0.05 * taper_dB)
    return 1.269 - 0.566 * tau + 0.534 * (tau ** 2) - 0.208 * (tau ** 3)


def antenna_taper_factor(array_name: str) -> float:
    """
    Primary beam taper in dB.

    Args:
        array_name: name of the array used for this project

    Returns:
        the primary beam taper factor in dB
    """
    antenna_taper = {
        'ALMA': 10.0,
        'EVLA': 0.0,
        'VLA': 0.0,
    }
    try:
        return antenna_taper[array_name]
    except KeyError:
        LOG.warning('Unknown array name: {}. Using null antenna taper factor in plots'.format(array_name))
        return 0.0


def tsys_scans_radec(
        ms: MeasurementSet,
        mean_direction: MDirection,
        tsys_field: Field,
) -> dict[str, dict[int, dict[str, tuple[float, float] | bool]]]:
    """
    Computes the offset RA/Dec values based on pointing and ASDM_POINTING tables.
    Adapted from Todd Hunter's AU tool tsysOffSourceRADec

    Args:
        ms: MeasurementSet object.
        mean_direction: CASA 'direction' measure dictionary representing mean RA and Dec values.
        tsys_field: The field used for TARGET Tsys.

    Returns:
        A dictionary containing Tsys OFF_SOURCE (and possibly ON_SOURCE) scan information, including
        offset values in arcsecs and whether a horizontal coordinate offset was applied.
    """
    vis = ms.basename
    observatory = ms.antenna_array.name.upper()
    ALMA_cycle_number = ms.get_alma_cycle_number()
    # Read POINTING table and return if it's empty
    with casa_tools.TableReader(os.path.join(vis, 'POINTING')) as mytb:
        if mytb.nrows() < 1:
            LOG.warning("The POINTING table is empty.")
            raise Exception("The POINTING table is empty.")

        pointing_times = mytb.getcol('TIME')  # MJD seconds
        pointing_offsets = mytb.getcol('POINTING_OFFSET')[:, 0, :]  # radians

    # Read ASDM_POINTING table if available
    ap_path = os.path.join(vis, 'ASDM_POINTING')
    if os.path.exists(ap_path):
        with casa_tools.TableReader(ap_path) as mytb:
            num_samples = mytb.getcol('numSample')
            nrows = np.sum(num_samples)

            source_offsets = np.zeros((nrows, 2))
            time_origins = np.zeros(nrows)

            j = 0
            for i, num_sample in enumerate(num_samples):
                entry = mytb.getcell('sourceOffset', i)  # radians
                source_offsets[j:j + num_sample] = entry
                time_origins[j:j + num_sample] = float(mytb.getcell('timeOrigin', i))  # stored as string
                j += num_sample
    else:
        LOG.warning("ASDM_POINTING table not found.")
        if observatory == 'ALMA':
            if ALMA_cycle_number:
                if int(ms.get_alma_cycle_number()) < 11:
                    LOG.attention("This is likely fine for data before Cycle 11.")
                else:
                    LOG.warning("Result may be inaccurate, especially if it's (0,0).")
            else:
                LOG.attention("Cycle number could not be determined. Result may be inaccurate, especially if it's (0,0).")

    with (
        casa_tools.MSReader(vis) as myms,
        casa_tools.MSMDReader(vis) as mymsmd,
        contextlib.closing(casa_tools.measures) as myme,
    ):
        # Compute values that are not scan-dependent
        base_dict = {'radec': (0.0, 0.0),
                     'azel offset': False}
        tsys_field_scans = mymsmd.scansforfield(field=tsys_field.id)
        off_intent = 'CALIBRATE_ATMOSPHERE#OFF_SOURCE'
        off_intent_scans = mymsmd.scansforintent(off_intent)
        off_tsys_scans = np.intersect1d(tsys_field_scans, off_intent_scans)
        scans_dict = {'OFF': {scan: copy.deepcopy(base_dict) for scan in off_tsys_scans}}

        # Check if there are any ON_SOURCE intents to plot
        if ALMA_cycle_number and int(ALMA_cycle_number) > 2:
            intents = ms.get_original_intent('ATMOSPHERE')
            on_source_intents = ['CALIBRATE_ATMOSPHERE#ON_SOURCE', 'CALIBRATE_ATMOSPHERE#TEST']
            if any(item in on_source_intents for item in intents):
                on_intent = 'CALIBRATE_ATMOSPHERE#ON_SOURCE'
                on_intent = on_intent if on_intent in intents else 'CALIBRATE_ATMOSPHERE#TEST'
                on_intent_scans = mymsmd.scansforintent(on_intent)
                on_tsys_scans = np.intersect1d(tsys_field_scans, on_intent_scans)
                if on_tsys_scans.size > 0:
                    scans_dict['ON'] = {scan: copy.deepcopy(base_dict) for scan in on_tsys_scans}

        for key, scan_dict in scans_dict.items():
            intent = on_intent if key == 'ON' else off_intent
            LOG.info("Calculating offset(s) for intent %s", intent)
            intent_times = mymsmd.timesforintent(intent)
            for scan_id in list(scan_dict.keys()):
                field_id = mymsmd.fieldsforscan(scan_id)[0]
                field_name = mymsmd.namesforfields(field_id)[0]
                field_direction = myms.getfielddirmeas(fieldid=field_id)

                scan_times = mymsmd.timesforscan(scan_id)
                mytimes = np.intersect1d(scan_times, intent_times)

                if mytimes.size == 0:
                    LOG.warning("No common times for scan %s and intent %s.", scan_id, intent)
                    continue

                # Find relevant pointing timestamps
                LOG.info("Calculating offset for scan %s", scan_id)
                first_time, last_time = np.min(mytimes), np.max(mytimes)
                mjdsec = np.nanmedian(mytimes)
                mjdtime = utils.mjd_seconds_to_datetime([mjdsec])[0]
                idx = np.where((pointing_times < last_time) & (pointing_times >= first_time))[0]
                LOG.info("Found %s pointing timestamps within the subscan time frame centered at %s",
                         idx.size, utils.format_datetime(mjdtime))

                # Set reference frame
                myme.doframe(myme.epoch('mjd', f"{mjdsec}s"))
                myme.doframe(myme.observatory(observatory))
                myazel = myme.measure(field_direction, 'AZEL')

                # Compute median cross-elevation offsets
                cross_elevation_offset = np.nanmedian(pointing_offsets[0, idx])
                el_pointing_offset = np.nanmedian(pointing_offsets[1, idx])
                elevation = myazel['m1']['value']  # radians
                az_pointing_offset = cross_elevation_offset / np.cos(elevation)

                LOG.info("Median offset = %+.2f in cross-elevation (%+.2f in azimuth), %+.2f in elevation (arcsec)",
                         3600 * np.degrees(cross_elevation_offset),
                         3600 * np.degrees(az_pointing_offset),
                         3600 * np.degrees(el_pointing_offset))

                LOG.info("Tsys Scan %s (%s) az, el = %s, %s", scan_id, field_name,
                         np.degrees(myazel['m0']['value']), np.degrees(myazel['m1']['value']))

                # Apply cross-elevation offsets
                if az_pointing_offset or el_pointing_offset:
                    scan_dict[scan_id]['azel offset'] = True
                    myazel['m0']['value'] += az_pointing_offset
                    myazel['m1']['value'] += el_pointing_offset
                    myicrs = myme.measure(myazel, 'ICRS')
                else:
                    # Converting between frames can cause small variations which show up downstream
                    # Revert to using field direction if no offsets are found.
                    myicrs = field_direction

                # Compute RA/Dec offset values
                radec_offsets = 0, 0
                if os.path.exists(ap_path):
                    # Compute amount of offset to apply to RA/Dec
                    if len(pointing_times) != len(time_origins):
                        LOG.warning("POINTING table entries (%s) ≠ ASDM_POINTING table entries (%s)",
                                    len(pointing_times), len(time_origins))
                        LOG.warning("No RA/Dec offset will be applied.")
                    else:
                        radec_offsets = np.nanmedian(source_offsets[idx, 0]), np.nanmedian(source_offsets[idx, 1])
                        LOG.info("Median offset = %+.2f in RA and %+.2f in Dec (arcsec)",
                                 3600 * np.degrees(radec_offsets[0]), 3600 * np.degrees(radec_offsets[1]))

                # Apply offset to RA/Dec and compare with field RA/Dec
                field_ra, field_dec = direction_to_radec(field_direction)
                offset_ra, offset_dec = apply_offset_to_radec(myicrs, offsets=radec_offsets)
                source_ra, source_dec = direction_to_radec(mean_direction)
                diff_ra, diff_dec = diff_directions(mean_direction, radec_to_direction(offset_ra, offset_dec))
                ang_sep = angular_separation(source_ra, source_dec, offset_ra, offset_dec, in_arcsecs=False)
                LOG.info("Calculating the total offset")
                LOG.info("Tsys Field radec = %s", radec_to_sexagesimal(field_ra, field_dec))
                LOG.info("Scan Offset radec = %s", radec_to_sexagesimal(offset_ra, offset_dec))
                LOG.info("Mean Source radec = %s", radec_to_sexagesimal(source_ra, source_dec))
                LOG.info("Angular separation between source and offset Tsys = %s arcsecs",
                         round(ang_sep * RADIANS_TO_ARCSEC, 3))
                scan_dict[scan_id]['radec'] = diff_ra, diff_dec

    return scans_dict


def apply_offset_to_radec(
        direction: MDirection,
        offsets: tuple[float, float] = (0.0, 0.0),
        use_euler_angles: bool = True
        ) -> tuple[float, float]:
    """
    Computes the right ascension (RA) and declination (Dec) with optional offsets.
    Adapted from Todd Hunter's AU tool radecOffsetToRadec

    Args:
        direction: CASA 'direction' measure dictionary representing RA and Dec values.
        offsets: Offset of RA and Dec in radians, default is (0.0, 0.0).
        use_euler_angles: If True, applies Euler rotation for offset computation.

    Returns:
        Adjusted RA and Dec values in radians.
    """
    ra, dec = direction_to_radec(direction)
    return (
        rotation_euler(offsets[0], offsets[1], ra, dec)
        if use_euler_angles else
        (ra + offsets[0] / np.cos(dec), dec + offsets[1])
    )


def radec_to_sexagesimal(ra: float, dec: float) -> str:
    """
    Converts RA and Dec from radians to sexagesimal (HMS and DMS) format.
    Adapted from Todd Hunter's AU tool direction2radec

    Args:
        ra: Right Ascension (RA) in radians.
        dec: Declination (Dec) in radians.

    Returns:
        RA and Dec in sexagesimal format as a string.
    """
    ra_hms = casa_tools.quanta.formxxx(f"{ra:.12f}rad", format="hms", prec=5)
    dec_dms = casa_tools.quanta.formxxx(f"{dec:.12f}rad", format="dms", prec=5).replace(".", ":", 2)

    return f"{ra_hms}, {dec_dms}"


def rotation_euler(rao: float, deco: float, r_long: float, r_lat: float) -> tuple[float, float]:
    """
    Rotates a point (rao, deco) using an Euler rotation defined by (r_long, r_lat).
    Adapted from Todd Hunter's AU tool rotationEuler

    Parameters:
        rao: Right Ascension (RA) in radians.
        deco: Declination (Dec) in radians.
        r_long: Rotation longitude in radians.
        r_lat: Rotation latitude in radians.

    Returns:
        (new RA in radians, new Dec in radians)
    """
    # Compute the initial position vector
    cos_deco = np.cos(deco)
    sin_deco = np.sin(deco)
    cos_rao = np.cos(rao)
    sin_rao = np.sin(rao)

    p_l = np.array([cos_rao * cos_deco, sin_rao * cos_deco, sin_deco])

    # Compute rotated position vector
    cos_r_long = np.cos(r_long)
    sin_r_long = np.sin(r_long)
    cos_r_lat = np.cos(r_lat)
    sin_r_lat = np.sin(r_lat)

    p_s = np.array([
        cos_r_long * cos_r_lat * p_l[0] - sin_r_long * p_l[1] - cos_r_long * sin_r_lat * p_l[2],
        sin_r_long * cos_r_lat * p_l[0] + cos_r_long * p_l[1] - sin_r_long * sin_r_lat * p_l[2],
        sin_r_lat * p_l[0] + cos_r_lat * p_l[2]
    ])

    # Compute new RA and Dec
    new_ra = np.arctan2(p_s[1], p_s[0])
    new_ra = new_ra % (2 * np.pi)  # Ensure RA is within [0, 2π]

    new_dec = np.arcsin(p_s[2])

    return new_ra, new_dec


def radec_to_direction(ra: float, dec: float, unit: str = "rad", frame: str = 'ICRS') -> MDirection:
    """
    Converts RA and Dec float values into a CASA direction dictionary.
    Adapted from Todd Hunter's AU tool rad2direction

    Args:
        ra: RA value.
        dec: Dec value.
        unit: Unit type of provided RA/Dec values; will be used to convert to radians.
        frame: Reference frame of direction measurement. Default is 'ICRS'.

    Returns:
        direction: CASA 'direction' measure dictionary representing RA and Dec values.
    """
    return casa_tools.measures.direction(frame, f'{ra}{unit}', f'{dec}{unit}')


def direction_to_radec(direction: MDirection) -> tuple[float, float]:
    """
    Extracts RA and Dec values from a CASA direction dictionary.
    Adapted from Todd Hunter's AU tool direction2rad

    Args:
        direction: CASA 'direction' measure dictionary representing RA and Dec values.

    Returns:
        a tuple containing extracted RA and Dec values
    """
    return direction['m0']['value'], direction['m1']['value']


def diff_directions(orig_direction: MDirection, offset_direction: MDirection) -> tuple[float, float]:
    """
    Compute the relative difference between the original position and an offset position.

    Args:
        orig_direction: CASA 'direction' dictionary containing the original RA/Dec values.
        offset_direction: CASA 'direction' dictionary containing the offset RA/Dec values.

    Returns:
        the relative difference in both RA and Dec between the two positions in arcsecs
    """
    orig_ra, orig_dec = direction_to_radec(orig_direction)
    offset_ra, offset_dec = direction_to_radec(offset_direction)

    # Normalize RA difference to [-π, π] to account for wraparound
    delta_ra = (offset_ra - orig_ra + np.pi) % (2 * np.pi) - np.pi
    delta_dec = offset_dec - orig_dec

    ra_offset = delta_ra * RADIANS_TO_ARCSEC * np.cos(offset_dec)
    dec_offset = delta_dec * RADIANS_TO_ARCSEC

    return ra_offset, dec_offset


def angular_separation(
        ra1: float, dec1: float, ra2: float, dec2: float, in_arcsecs: bool = True,
        ) -> float:
    """
    Compute angular separation between two sky coordinates (RA, Dec). Coordinates can either
        be in radians (in_arcsecs=False) or arcsecs (in_arcsecs=True), and the return values
        will be in the same units.

    Args:
        ra1: RA measurement of the first target.
        dec1: Dec measurement of the first target.
        ra2: RA measurement of the second target.
        dec2: Dec measurement of the second target.
        in_arcsecs: Allows the user to switch between radians and arcsecs.
            Default is arcsecs (in_arcsecs=True).

    Returns:
        Angular separation.
    """
    # Converts values into radians if in arcsecs.
    if in_arcsecs:
        ra1 = ra1 / RADIANS_TO_ARCSEC
        dec1 = dec1 / RADIANS_TO_ARCSEC
        ra2 = ra2 / RADIANS_TO_ARCSEC
        dec2 = dec2 / RADIANS_TO_ARCSEC

    # Compute angular separation
    delta_ra = ra2 - ra1
    sin_ddec = np.sin((dec2 - dec1) / 2)
    sin_dra = np.sin(delta_ra / 2)
    a = sin_ddec**2 + np.cos(dec1) * np.cos(dec2) * sin_dra**2
    angle = 2 * np.arcsin(np.sqrt(a))

    # Converts back to arcsecs if desired.
    return angle * RADIANS_TO_ARCSEC if in_arcsecs else angle
