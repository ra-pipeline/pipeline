# Do not evaluate type annotations at definition time.
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Dict, List, Tuple, TypedDict

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import lines, patches, ticker
from scipy import interpolate

from pipeline import infrastructure
from pipeline.domain import measures, unitformat
from pipeline.h.tasks.tsyscal import tsyscal
from pipeline.infrastructure import casa_tools, utils

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure
    from pipeline.domain import Field, MeasurementSet, Source
    from pipeline.domain.measures import Distance, EquatorialArc

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


def compute_mosaic_data(
        ms: MeasurementSet,
        source: Source
        ) -> Tuple[np.ndarray, np.ndarray, float, List[Distance], List[float]]:
    """Extract and compute relevant data for plotting.

    Args:
        ms: MeasurementSet object.
        source: Source object.

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

    ra = np.array([casa_tools.quanta.convert(f.mdirection['m0']['value'], 'rad')['value'] for f in source.fields])
    dec = np.array([casa_tools.quanta.convert(f.mdirection['m1']['value'], 'rad')['value'] for f in source.fields])

    return ra, dec, median_ref_freq, dish_diameters, beam_diameters


def compute_offsets(ra: np.ndarray, dec: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float, float]:
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


def create_mosaic_figure(
        delta_ra: np.ndarray,
        delta_dec: np.ndarray,
        beam_diameters: List[float],
        margin_x: int = 100,
        margin_y: int = 80,
        dpi: int = 100
        ) -> Tuple[Figure, Axes, int]:
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
    ra_range_arcsec  = (delta_ra.max() - delta_ra.min())  * RADIANS_TO_ARCSEC
    dec_range_arcsec = (delta_dec.max() - delta_dec.min()) * RADIANS_TO_ARCSEC

    pixels_per_beam = 60.
    min_size, max_size = 400, 2000
    smallest_beam = min(beam_diameters)  # arcsec
    pixels_x = np.clip(pixels_per_beam * ra_range_arcsec / smallest_beam, min_size, max_size)
    pixels_y = np.clip(pixels_per_beam * dec_range_arcsec / smallest_beam, min_size, max_size)

    fig = plt.figure(figsize=((pixels_x + margin_x) / dpi, (pixels_y + margin_y) / dpi))
    ax = fig.add_subplot(1, 1, 1)
    fontsize = max(6, min(12, 0.1 * smallest_beam / max(ra_range_arcsec / pixels_x, dec_range_arcsec / pixels_y)))
    return fig, ax, fontsize


def add_elements_to_plot(
        ax: Axes,
        plot_dict: Dict[str, Dict[str, Dict[int, Dict[str, Any]] | float]],
        fontsize: int = 10,
        draw_labels: bool = False
        ) -> Tuple[Dict[str, lines.Line2D], Dict[str, str]]:
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
        for key, specs in values['target fields'].items():
            ax.add_patch(patches.Circle((specs['x'], specs['y']), radius=0.5 * beam_diameter,
                                facecolor='none', edgecolor=specs['color'], linestyle='dotted', alpha=0.6))

            if draw_labels:
                ax.text(specs['x'], specs['y'], f'{key}',
                        ha='center', va='center', fontsize=fontsize, color=specs['color'])
            else:
                ax.plot(specs['x'], specs['y'], f'{specs["color"]}+', markersize=4)

            if specs['label'] not in legend_labels:
                legend_labels[specs['label']] = lines.Line2D(
                    [0], [0], color=specs['color'], linewidth=2, linestyle='dotted'
                    )
                legend_colors[specs['label']] = specs['color']
        if 'tsys scans' in values.keys():
            for scan_id, scan_dict in values['tsys scans'].items():
                x, y = scan_dict['radec']
                ax.add_patch(patches.Circle((x, y), radius=0.5 * beam_diameter,
                                    facecolor='none', edgecolor='r', linestyle='dotted', alpha=0.6))

                if scan_dict['azel offset']:
                    ax.text(x, y, f'{scan_id}', ha='center', va='center', fontsize=fontsize, color='r')
                else:
                    ax.plot(x, y, f'{"r"}+', markersize=4)

            if 'Tsys Scan' not in legend_labels:
                legend_labels['Tsys Scan'] = lines.Line2D([0], [0], color='r', linewidth=2, linestyle='dotted')
                legend_colors['Tsys Scan'] = 'r'

    return legend_labels, legend_colors


def compute_element_locs(
        source: Source,
        delta_ra: List[float],
        delta_dec: List[float],
        dish_diameters: List[Distance],
        beam_diameters: List[float],
        tsys_scans_dict: Dict[int, Dict[str, Tuple[float, float] | bool]] | None = None,
        ) -> Dict[str, Dict[str, Dict[int, Dict[str, Any]] | float]]:
    """Compute the field locations to use for plotting.

    Args:
        source: the Source object.
        delta_ra: a list of offset RA values from the median position in radians.
        delta_dec: a list of offset Dec values from the median position in radians.
        dish_diameters: a list of Distance objects indicating the size of the antennas used for observation.
        beam_diameters: a list of primary beam sizes in arcsecs.

    Returns:
        plot_dict: plot information for the source fields, including location, color, label, and beam diameter.
    """
    plot_dict = {}
    for dish_diameter, beam_diameter in zip(dish_diameters, beam_diameters):
        plot_dict[str(dish_diameter.value)] = {'beam diameter': beam_diameter,
                                               'target fields': {}}
        for field, rel_ra, rel_dec in zip(source.fields, delta_ra, delta_dec):
            if not is_tsys_only(field):
                field_dict = {
                    'x': rel_ra * RADIANS_TO_ARCSEC,
                    'y': rel_dec * RADIANS_TO_ARCSEC,
                    'color': 'b' if dish_diameter == SEVEN_M else 'k',
                    'label': str(dish_diameter),
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
        legend_labels: Dict[str, lines.Line2D],
        legend_colors: Dict[str, str],
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
    title_string = f'{vis}, {source_name}, avg freq.={unitformat.frequency.format(median_ref_freq)}'
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
    # Retrieve field positions and configurations
    ra, dec, median_ref_freq, dish_diameters, beam_diameters = compute_mosaic_data(ms, source)
    delta_ra, delta_dec, mean_ra, mean_dec = compute_offsets(ra, dec)

    # Create mosaic plot
    fig, ax, fontsize = create_mosaic_figure(delta_ra, delta_dec, beam_diameters)
    draw_field_labels = len(source.fields) <= 500  # field labels become hard to read if there are too many of them
    plot_dict = compute_element_locs(source, delta_ra, delta_dec, dish_diameters, beam_diameters)
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

    fig.savefig(figfile, dpi=100)
    plt.close(fig)


def plot_mosaic_tsys_scans(ms: MeasurementSet, source: Source, figfile: str) -> None:
    """
    Produce a plot of the Tsys scans relative to the target pointings.

    Args:
        ms: MeasurementSet object.
        source: Source object.
        figfile: file name of the mosaic plot to be created.

    Returns:
        None: The function saves the plot to a file and does not return any value.
    """
    # Retrieve correct Tsys field for source based on mapping
    tsys_fields = tsyscal.get_gainfield_map(ms, is_single_dish=False)['TARGET'].split(',')
    if not tsys_fields:
        raise Exception('No TSYS fields associated with TARGET.')

    try:
        # Grabs correct field if more that one Tsys field and/or the returned ID or name match
        tsys_field = [
            field for field in source.fields if str(field.id) in tsys_fields or field.name in tsys_fields
            ][0]
    except IndexError:
        # Defaults to first Tsys TARGET field if there are no Tsys fields associated with source
        if tsys_fields[0].isdigit():
            tsys_field = ms.get_fields(field_id=int(tsys_fields[0]))[0]
        else:
            tsys_field = ms.get_fields(name=tsys_fields[0])[0]

    # Calculate Tsys scan(s) offset to apply to plot
    tsys_scans_dict = tsys_off_source_radec(ms, tsys_field)

    # Retrieve TARGET field positions and configurations
    ra, dec, median_ref_freq, dish_diameters, beam_diameters = compute_mosaic_data(ms, source)
    delta_ra, delta_dec, mean_ra, mean_dec = compute_offsets(ra, dec)

    # Create mosaic plot
    fig, ax, fontsize = create_mosaic_figure(delta_ra, delta_dec, beam_diameters)
    plot_dict = compute_element_locs(source, delta_ra, delta_dec, dish_diameters, beam_diameters, tsys_scans_dict=tsys_scans_dict)
    legend_labels, legend_colors = add_elements_to_plot(ax, plot_dict, fontsize=fontsize)

    # Add title, legend, and labels
    configure_labels(ax, legend_labels, legend_colors, mean_ra, mean_dec, median_ref_freq, ms.basename, source.name)

    # Adjust title size if necessary
    plt.tight_layout()
    renderer = fig.canvas.get_renderer()
    if ax.title.get_window_extent(renderer).xmax > fig.canvas.get_width_height()[0]:
        ax.title.set_fontsize(10)

    fig.savefig(figfile, dpi=100)
    plt.close(fig)


def get_arc_formatter(precision: int) -> unitformat.UnitFormat:
    """
    Presents a value of equatorial arc in user-friendly units.

    Args:
        precision: number of significant figures used by formatter

    Returns:
        a UnitFormat object used to create the mosaic plot
    """
    s = '{0:.' + str(precision) + 'f}'
    f = unitformat.UnitFormat(prefer_integers=True)
    f.addUnitOfMagnitude(1. / 1000000, s + r' $\mu$as')
    f.addUnitOfMagnitude(1. / 1000, s + ' mas')
    f.addUnitOfMagnitude(1., s + r'$^{{\prime\prime}}$')
    f.addUnitOfMagnitude(60., s + r'$^\prime$')
    f.addUnitOfMagnitude(3600., s + r'$\degree$')
    return f


# Used to label x and y plot axes
AXES_FORMATTER = get_arc_formatter(1)


def label_format(x: float, _: Any) -> str:
    """
    Labels plot axes for plots specified in units of arcseconds.

    Args:
        x (float): The tick value in arcseconds.
        _ (Any): The tick position (ignored).

    Returns:
        str: The formatted label string.
    """
    return AXES_FORMATTER.format(x)


def is_tsys_only(field: Field) -> bool:
    """
    Looks at the field intents and determines if it is a Tsys-only field or not.

    Args:
        field: Field object.

    Returns:
        True if the field was only used to observe Tsys else False
    """
    return 'TARGET' not in field.intents and 'ATMOSPHERE' in field.intents


def primary_beam_fwhm(wavelength: Distance, diameter: List[Distance], taper: float) -> EquatorialArc:
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
        LOG.warning('Unknown array name: {}. Using null antenna taper factor in mosaic plots'.format(array_name))
        return 0.0


def tsys_off_source_radec(
        ms: MeasurementSet,
        tsys_field: Field,
        intent: str = 'CALIBRATE_ATMOSPHERE#OFF_SOURCE',
        observatory: str = 'ALMA',
        ) -> Dict[int, Dict[str, Tuple[float, float] | bool]] | None:
    """
    Computes the off-source RA/Dec based on pointing and ASDM_POINTING tables.
    Adapted from Todd Hunter's AU tool tsysOffSourceRADec

    Args:
        ms: MeasurementSet object.
        tsys_scans: a list of Scan objects used for TARGET Tsys
        observatory: Observatory name for Az/El to RA/Dec conversion.

    Returns:
        Computed scan offset values in radians.
    """
    vis = ms.basename
    # Read POINTING table and return if it's empty
    with casa_tools.TableReader(os.path.join(vis, 'POINTING')) as mytb:
        if mytb.nrows() < 1:
            mytb.close()
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
        if ms.get_alma_cycle_number() < 11:
            LOG.attention("This is likely fine for data before Cycle 11.")
        else:
            LOG.warning("Result may be inaccurate, especially if it's (0,0).")

    # create needed CASA tools
    myme = casa_tools.measures
    myms = casa_tools.ms
    mymsmd = casa_tools.msmd
    myms.open(vis)
    mymsmd.open(vis)

    # # Compute values that are not scan-dependent
    intent_scans = mymsmd.scansforintent(intent)
    tsys_field_scans = mymsmd.scansforfield(field=tsys_field.id)
    tsys_scans = np.intersect1d(tsys_field_scans, intent_scans)
    scan_dict = {'radec': (0.0, 0.0),
                 'azel offset': False}
    scans_dict = {scan: scan_dict.copy() for scan in tsys_scans}

    for scan_id in list(scans_dict.keys()):
        field_id = mymsmd.fieldsforscan(scan_id)[0]
        field_name = mymsmd.namesforfields(field_id)[0]
        field_direction = myms.getfielddirmeas(fieldid=field_id)

        scan_times = mymsmd.timesforscan(scan_id)

        if scan_times.size == 0:
            LOG.warning("No common times for scan %s and intent %s.", scan_id, intent)
            continue

        # # Find relevant pointing timestamps
        LOG.info("Calculating offset for scan %s", scan_id)
        first_time, last_time = np.min(scan_times), np.max(scan_times)
        mjdsec = np.nanmedian(scan_times)
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

        LOG.info("FIELD %s (%s) az, el = %s, %s", field_id, field_name,
                np.degrees(myazel['m0']['value']), np.degrees(myazel['m1']['value']))

        # Apply cross-elevation offsets
        if az_pointing_offset or el_pointing_offset:
            scans_dict[scan_id]['azel offset'] = True
            myazel['m0']['value'] += az_pointing_offset
            myazel['m1']['value'] += el_pointing_offset
        myicrs = myme.measure(myazel, 'ICRS')

        # Compute RA/Dec offset values
        radec_offsets = 0, 0
        if os.path.exists(ap_path):
            # Compute amount of offset to apply to RA/Dec
            if len(pointing_times) != len(time_origins):
                LOG.warning("WARNING: POINTING table entries (%s) ≠ ASDM_POINTING table entries (%s)",
                            len(pointing_times), len(time_origins))
                LOG.warning("No RA/Dec offset will be applied.")
            else:
                radec_offsets = np.nanmedian(source_offsets[idx, 0]), np.nanmedian(source_offsets[idx, 1])
                LOG.info("Median offset = %+.2f in RA and %+.2f in Dec (arcsec)",
                        3600 * np.degrees(radec_offsets[0]), 3600 * np.degrees(radec_offsets[1]))

        # Apply offset to RA/Dec and compare with field RA/Dec
        field_ra, field_dec = direction_to_radec(field_direction)
        offset_ra, offset_dec = apply_offset_to_radec(myicrs, offsets=radec_offsets)
        LOG.info("Calculating the total offset")
        LOG.info("FIELD radec = %s", radec_to_sexagesimal(field_ra, field_dec))
        LOG.info("OFF_SOURCE radec = %s", radec_to_sexagesimal(offset_ra, offset_dec))
        scans_dict[scan_id]['radec'] = diff_directions(field_direction, radec_to_direction(offset_ra, offset_dec))

    # cleanup measures tool
    myme.done()
    mymsmd.close()

    return scans_dict


def apply_offset_to_radec(
        direction: MDirection,
        offsets: Tuple[float, float] = (0.0, 0.0),
        use_euler_angles: bool = True
        ) -> Tuple[float, float]:
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


def rotation_euler(rao: float, deco: float, r_long: float, r_lat: float) -> Tuple[float, float]:
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


def direction_to_radec(direction: MDirection) -> Tuple[float, float]:
    """
    Extracts RA and Dec values from a CASA direction dictionary.
    Adapted from Todd Hunter's AU tool direction2rad

    Args:
        direction: CASA 'direction' measure dictionary representing RA and Dec values.

    Returns:
        a tuple containing extracted RA and Dec values
    """
    return direction['m0']['value'], direction['m1']['value']


def diff_directions(orig_direction: MDirection, offset_direction: MDirection) -> Tuple[float, float]:
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

    ra_offset = (offset_ra - orig_ra) * RADIANS_TO_ARCSEC * np.cos(offset_dec)
    dec_offset = (offset_dec - orig_dec) * RADIANS_TO_ARCSEC

    return ra_offset, dec_offset
