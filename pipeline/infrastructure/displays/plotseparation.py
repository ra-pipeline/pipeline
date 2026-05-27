# Do not evaluate type annotations at definition time.
from __future__ import annotations

import copy
import itertools
from typing import TYPE_CHECKING


from matplotlib.lines import Line2D
from matplotlib.patches import Circle
from matplotlib.ticker import FuncFormatter
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import lines, patches, ticker
from scipy import interpolate

from pipeline import infrastructure
from pipeline.domain import measures, unitformat
from pipeline.h.heuristics.tsysfieldmap import get_intent_to_tsysfield_map
from pipeline.infrastructure import utils
from pipeline.infrastructure.casa_tools import quanta
from pipeline.domain.measures import ArcUnits, EquatorialArc

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from matplotlib.figure import Figure
    from matplotlib.text import Text
    from numpy.typing import NDArray
    from numpy import floating
    from pipeline.domain import Field, MeasurementSet, Source 

    
LOG = infrastructure.logging.get_logger(__name__)

def plot_separations(
        ms: MeasurementSet,
        figfile
) -> None:
    """
    Produce a plot of the position for each target 
    and the PHASE and CHECK calibrators with the 
    field types coloured by intent.
    """

    fields = get_field_object(ms)

    ref_ra, ref_dec, delta_ra, delta_dec = get_position_offsets(fields)
   
    fig, ax, fontsize, dpi= create_figure(delta_ra, delta_dec)

    # add fields on the plot axes
    legend_labels, legend_colours = add_to_plot(ax, fontsize, fields, delta_ra, delta_dec)
    
    # Add title, labels, format
    title_text = configure_labels(ax, legend_labels, legend_colours, ref_ra, ref_dec,  ms.basename, fields[0].name, fields[0].id)

    # Set tight layout and adjust title
    plt.tight_layout()

    
    # make sure title text fits into the picture, if not, then reduce the font size
    xmax = title_text.get_window_extent(fig.canvas.get_renderer()).xmax
    figwidth = fig.canvas.get_width_height()[0]
    if xmax > figwidth:
        title_text.set_fontsize(title_font_size * figwidth / (2*xmax-figwidth))

    fig.savefig(figfile, dpi=dpi)
    plt.close(fig)
    

def get_arc_formatter(
        precision):  
    """
    Presents a value of equatorial arc in user-friendly units. Input in deg
    """
    s = '{0:.' + str(precision) + 'f}'
    f = unitformat.UnitFormat(prefer_integers=True)
    f.addUnitOfMagnitude(1./3600., s + r'$^{{\prime\prime}}$')
    f.addUnitOfMagnitude(1/60., s + r'$^\prime$')
    f.addUnitOfMagnitude(1., s + r'$\degree$')
    return f


# Used to label x and y plot axes
AXES_FORMATTER = get_arc_formatter(1)


def label_format(x, _):
    """
    Labels plot axes for plots specified in units of degrees
    """
    # x is given in DEGREES, _ is tick position
    return AXES_FORMATTER.format(x)


def get_sym_colour_orig(
        field_name,
        phases,
        checks
) -> str:
    if field_name in [fld.name for fld in phases]:  
        return 'r'
    if field_name in [fld.name for fld in checks]:
        return 'b'
    else:
        return 'k'


def get_sym_colour(
        fieldintent: set # object 
) -> str:
    """ Provide the fixed colour back dependent on the field intent.

    Args:
        field: Field intent set

    Returns:
        string for the matplotlib color
    """
        
    if 'PHASE' in fieldintent: 
        return 'r'
    if 'CHECK' in fieldintent:
        return 'b'
    else:
        # assumed a target
        return 'k'



def get_field_object(
        ms
        ) -> list:
    """Extract and create a list of the field objects for the 
    PHASE cal, CHECK source (if present) and TARGET(s)

    Args:
        ms: MesurementSet object
    
    Returns:
        fields: flattened list of the field objects in order for PHASE, CHECK, TARGET(s)
    """
    
    phase_fld = [fld for fld in ms.get_fields(intent='PHASE')]
    check_fld =[fld for fld in ms.get_fields(intent='CHECK')] 
    target_fld = [fld for fld in ms.get_fields(intent='TARGET')] 
    target_fld_final = [] # use to only append the targets we plot, e.g. mosaic is a single positon with name mosaic
    
    # if we have a mosaic, just pass the first position, append later name of 'mosaic'
    unique_tars = np.unique([fld.name for fld in target_fld])
    for fld_unq_name in unique_tars:
        if utils.separation_angles.is_mosaic(ms,fld_unq_name):
            field_hold =   copy.deepcopy([fld for fld in ms.get_fields(intent='TARGET', name=fld_unq_name)][0])
            # required because we reassign the object.id attribute and otherwise it propagates back through PL            
            field_hold.id = 'mosaic' # for the plot
            target_fld_final.append(field_hold) # single extracted position 
        else:
            # multiple targets, keep extending
            target_fld_final.extend([fld for fld in ms.get_fields(intent='TARGET', name=fld_unq_name)]) # list of list

    # now the field objects
    fields = list(itertools.chain.from_iterable([phase_fld, check_fld, target_fld_final])) # flatten all the lists to a single list, with PHASE(s) first

    return fields   


def get_position_offsets(
        fields: list
        ) -> tuple[NDArray[floating], NDArray[floating], NDArray[floating], NDArray[floating]]: # returns two arrays
    """Extract the relavant RA and DEC directions and compute the 
    offsets with respect to the first in the list of fields positions for plotting

    Args:
        ms: MeasurementSet object.
        fields: A list of Field objects including the non Tsys-only fields.

    Returns:
        delta_ra: difference in ra values w.r.t the first field positon in radians for each field.
        delta_dec: difference in dec values w.r.t the first field posiion in radians for each field.
    """
    
    ra  = np.array([quanta.convert(f.mdirection['m0']['value'], 'rad')['value'] for f in fields])
    dec = np.array([quanta.convert(f.mdirection['m1']['value'], 'rad')['value'] for f in fields])

    # store the Reference RA, DEC, i.e. that of the PHASE is first listed 
    ref_ra  = ra[0]
    ref_dec = dec[0]  

    # compute offsets in longitude (taking into account the cos(lat) factor) and latitude, still in radians
    delta_ra  = np.cos(dec) * np.sin(ra - ref_ra)
    delta_dec = np.sin(dec) * np.cos(ref_dec) - np.cos(dec) * np.sin(ref_dec) * np.cos(ra - ref_ra)

    return ref_ra, ref_dec, delta_ra, delta_dec


def create_figure(
        delta_ra: NDArray[floating],
        delta_dec: NDArray[floating],
        margin_x: int = 100,
        margin_y: int = 80,
        dpi: int = 100
        ) -> tuple[Figure, Axes, float, int]:  #, dict, dict]:  # is that right?
    """Initialize a figure with correct dimensions.

    Args:
        delta_ra: a list of offsets in RA from the position of the first field in radians.
        delta_dec: a list of offsets in Dec from the position of the first field in radians.
        margin_x: buffer pixel value in the x-axis.
        margin_y: buffer pixel value in the y-axis.
        dpi: dots per inch value used for the created figure.

    Returns:
        fig: the Figure object.
        ax: the Axes object.
        fontsize: appropriately scaled fontsize
        dpi: dots per inch value returned

    """

    # some heuristics to determine the appropriate x- and y-range for plotting, adjusting the figure size as needed
    radians_to_deg = 180 / np.pi  # can use np.degrees below?     
    ra_range_deg  = (max(delta_ra)  - min(delta_ra))  * radians_to_deg
    dec_range_deg = (max(delta_dec) - min(delta_dec)) * radians_to_deg

    # testing indicates these are ok, previous (local) version calculated parameters but it made a mess
    pixels_per_beam = 60.
    min_size_in_pixels = 400.
    max_size_in_pixels = 2000.
    margin_x = 100.0 
    margin_y = 80.0
    pixels_x = max(min_size_in_pixels, min(max_size_in_pixels, pixels_per_beam * ra_range_deg))
    pixels_y = max(min_size_in_pixels, min(max_size_in_pixels, pixels_per_beam * dec_range_deg))
    pixels_per_smallest_beam = 1.0 / max(ra_range_deg / pixels_x, dec_range_deg / pixels_y)
    fontsize = max(8, min(12, 0.1 * pixels_per_smallest_beam))   # font size for labelling the field id 

    dpi = 100  # pixels per inch
    fig = plt.figure(figsize=((pixels_x + margin_x) / dpi, (pixels_y + margin_y) / dpi))
    ax = fig.add_subplot(1, 1, 1)


    return fig, ax, fontsize, dpi



def configure_labels(
        ax: Axes,
        legend_labels: dict[str, lines.Line2D],
        legend_colours: dict[str, str],
        ref_ra: float,
        ref_dec: float,
        vis: str,
        field_name: str,
        field_id: int
        ) -> Text:
    """Set the plot title and labels.
    The function updates the Axes object with title and label information and format
    along with setting the axis limits based on the data added.

    Args:
        ax: the Axes object.
        legend_labels: dictionary containing label information for the plotted elements.
        legend_colours: dictionary containing color information for the plotted elements.
        ref_ra: the reference value of the first PHASE field RA values in radians.
        ref_dec: the reference value of the first PHASE field Dec values in radians.
        vis: the name of the measurement set associated with the observation.
        field_name: the name of the refrence PHASE calibrator field.
        field_id: the id of the reference PHASE calibrator field. 

    Returns:
        title text: The matplotlib format text of the title.
    """

    # Title        
    title_string = f'{vis}\n Separation from PHASE - {field_name}(#{field_id})  '
    title_font_size = 12
    title_text = ax.set_title(title_string, size=title_font_size)

    # Axes labels
    ra_string = r'{:02d}$^{{\rm h}}${:02d}$^{{\rm m}}${:02.3f}$^{{\rm s}}$'.format(
        *EquatorialArc(ref_ra % (2*np.pi), ArcUnits.RADIAN).toHms())
    ax.set_xlabel('Right ascension offset from {}'.format(ra_string))
    dec_string = r'{:02d}$\degree${:02d}$^\prime${:02.1f}$^{{\prime\prime}}$'.format(
        *EquatorialArc(ref_dec, ArcUnits.RADIAN).toDms())
    ax.set_ylabel('Declination offset from {}'.format(dec_string))

    # legend information
    leg_lines = [legend_labels[i] for i in sorted(legend_labels)]
    leg_labels = sorted(legend_labels)
    leg = ax.legend(leg_lines, leg_labels, prop={'size': 10}, loc='best')
    leg.get_frame().set_alpha(0.8)
    for text in leg.get_texts():
        text.set_color(legend_colours[text.get_text()])

    # axis properties 
    ax.axis('equal')
    degree_formatter = FuncFormatter(label_format)
    ax.xaxis.set_major_formatter(degree_formatter)
    ax.yaxis.set_major_formatter(degree_formatter)
    ax.xaxis.grid(True, which='major')
    ax.yaxis.grid(True, which='major')
    ax.invert_xaxis()

    ax.margins(0.15) # default is 5% update to 15% buffers symbol size and text annotation
 
    return title_text



def add_to_plot(
        ax: Axes,
        fontsize: float,
        fields: list,
        delta_ra: NDArray,
        delta_dec: NDArray
        ) -> Tuple[dict,dict]:
    """Loop over list of field objects and plot the position
    offsets from the first phase calibrator field

    Args:
        field: list of field objects
        delta_ra: 
        delta_dec:

    Returns:
        legend_labels: dictionary of string label keyed by field intent
        legend_colours: dictionary of string colour keyed by field intent
    """

    legend_labels = {}
    legend_colours = {}


    legend_labels['PHASE']=Line2D(list(range(1)), list(range(1)), color='r', linewidth=2,linestyle='solid')
    legend_colours['PHASE']= get_sym_colour({'PHASE'})

    legend_labels['TARGET']=Line2D(list(range(1)), list(range(1)), color='k', linewidth=2,linestyle='solid')
    legend_colours['TARGET']= get_sym_colour({'TARGET'})
    
    for field, rel_ra, rel_dec in zip(fields, delta_ra, delta_dec):
        x = np.degrees(rel_ra)
        y = np.degrees(rel_dec)
        colour = get_sym_colour(field.intents)
        ax.plot(x, y, marker = '+', linestyle='None', color = colour, markersize=30, markeredgewidth=6, zorder = 2) 
        ax.text(x-0.2, y+0.2, '{}'.format(field.id), ha='center', va='center', fontsize=fontsize, color=colour) # offset in degrees

        # check the keys for CHECK if a CHECK intent is to be plotted
        if 'CHECK' in field.intents and 'CHECK' not in legend_colours.keys():
            legend_labels['CHECK']=Line2D(list(range(1)), list(range(1)), color='b', linewidth=2,linestyle='solid')
            legend_colours['CHECK']= get_sym_colour({'CHECK'})      

    return legend_labels, legend_colours

