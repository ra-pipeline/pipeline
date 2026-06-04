# Do not evaluate type annotations at definition time.
from __future__ import annotations

import copy
import itertools
from typing import TYPE_CHECKING

from matplotlib.lines import Line2D
from matplotlib.patches import Polygon
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
    fields = list(itertools.chain.from_iterable([phase_fld, check_fld, target_fld_final]))
    # flatten all the lists to a single list, with PHASE(s) first

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
    ra_range_deg  = np.degrees((max(delta_ra)  - min(delta_ra)))
    dec_range_deg = np.degrees((max(delta_dec) - min(delta_dec)))

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

    ax.margins(0.15) # 15% buffers symbol size and text annotation
 
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

    label_list = [[],[],[]]
    for field, rel_ra, rel_dec in zip(fields, delta_ra, delta_dec):
        x = np.degrees(rel_ra)
        y = np.degrees(rel_dec)
        colour = get_sym_colour(field.intents)
        xyver = make_plus_patch(x,y,1.0)
        plus = Polygon(xyver, facecolor='none', edgecolor=colour,
                     linestyle='solid', alpha=0.6, linewidth=2, zorder=2)
        ax.add_patch(plus)

        # Always label the PHASE(s) and CHECK(s) directly
        if 'PHASE' in field.intents or 'CHECK' in field.intents:
            ax.text(x, y, '{}'.format(field.id), ha='center', va='center', fontsize=fontsize, color=colour)             
            
        # Check the keys for CHECK if a CHECK intent is to be plotted
        if 'CHECK' in field.intents and 'CHECK' not in legend_colours.keys():
            legend_labels['CHECK']=Line2D(list(range(1)), list(range(1)), color='b', linewidth=2,linestyle='solid')
            legend_colours['CHECK']= get_sym_colour({'CHECK'})

        # Build label list for TARGET intents to consolidate
        if 'TARGET' in field.intents:
             label_list[0].append(field.id)
             label_list[1].append(x)
             label_list[2].append(y)

    # Loop over the targets listed for possible consolidation of the field ID annotations         
    colour = get_sym_colour({'TARGET'})     
    # if there is only one label then plot it, else consolidate
    if len(label_list[0]) == 1:
        label_plot = zip(label_list[0],label_list[1],label_list[2], ['center']) # 4th value is for the horizontal aligment 
    else:   
        # Consolidate the target labels 
        label_plot = consolidate_labels(label_list)
        colour = get_sym_colour({'TARGET'})
    # Plot the text     
    for lab_fields, lab_ra, lab_dec, lab_loc in label_plot:
            ax.text(lab_ra, lab_dec, '{}'.format(lab_fields), ha=lab_loc, va='center', fontsize=fontsize, color=colour)  

    return legend_labels, legend_colours

def make_plus_patch(
        xpos: float,
        ypos: float,
        len_sym: float
        ) -> List : # (of lists?)
    """Produce a plus symbol outline to act as the plot symbol
    for the separation angle plots between INTENTS. Plus
    symbol is assumed to be symetric 

    Args:
        xpos: x-axes central position as a float
        ypos: y-axes central position as a float
        len_sym: total length of the symbol in plot axis units

    Returns:
        xyvertex: verties of the plus symbol   
    """

    # 12 vertex points
    # main distances are 0.5 * len_sym
    # and 1/6 * len_sym

    # moving top right most vertex and around
    sm_ver = 0.167 * len_sym
    lg_ver = 0.5 * len_sym
    xyvertex = [[xpos+sm_ver,ypos+lg_ver],
              [xpos+sm_ver,ypos+sm_ver],
              [xpos+lg_ver,ypos+sm_ver],
              [xpos+lg_ver,ypos-sm_ver],
              [xpos+sm_ver,ypos-sm_ver],
              [xpos+sm_ver,ypos-lg_ver],
              [xpos-sm_ver,ypos-lg_ver],
              [xpos-sm_ver,ypos-sm_ver],
              [xpos-lg_ver,ypos-sm_ver],
              [xpos-lg_ver,ypos+sm_ver],
              [xpos-sm_ver,ypos+sm_ver],
              [xpos-sm_ver,ypos+lg_ver]]
    
    return xyvertex
        
def consolidate_labels(
        field_ra_dec: List, ##Tuple,
        overlap: float = 0.6
        ) -> Tuple:
    """ Function to take the zip of the field object, ra and dec 
    delta positions of the fields that are plotted and consolidate 
    the lables as the field.id if they are overlapping too much.

    Args:
        field_ra_dec the list of lists of field, delta_ra, delta_dec.
        overlap: value in degrees below which a label overlap is considered.
    
    Return:
        zip tuple of the field ids, plot ra postion, and plot dec position for 
        the lables, and the label locator w.r.t. the plot position.
    """

    field_ids=[]
    lab_ra=[]
    lab_dec=[]
    lab_loc=[]

    # have to better search all positions with others, then
    # assign a mask ?
    # iterative loop and remove?
    
    # get a mask if the positions are individual or not
    diff_mask = ((np.abs(np.diff(field_ra_dec[1]))>overlap) | (np.abs(np.diff(field_ra_dec[2]))>overlap))
    # because this is a diff, we need to prepend a first mask same as the first boolean
    # if the first element in diff_mask is True, this means the first and second positons are far and should
    # be separate groups, given the later cumsum, this means set to true. Otherwise, if
    # the first element is False, they do overlap and thus prepends a False to be part of same group
    diff_mask = np.concatenate(([diff_mask[0]],diff_mask))
    # now find the unqiue groups with np.cumsum, increments with True
    groups = np.cumsum(diff_mask)
    LOG.info(diff_mask)
    LOG.info(groups)
    # loop the unique groups and assess if we need a common label and average location
    # limit is same number of groups as targets themselves
    for group_ids in np.unique(groups):
        # mask for coords we want
        mask_cords = (groups == group_ids)
        # if we have more than one element we need to assess the consolidation
        if np.sum(mask_cords)>1:
            LOG.info('Testing only - more than one coord overlap plot')
            LOG.info(np.array(field_ra_dec[0])[mask_cords])
            # symbol to right (more negative)
            lab_ra.append(np.min(np.array(field_ra_dec[1])[mask_cords]) - 0.55) # based on symbol size
            lab_dec.append(np.mean(np.array(field_ra_dec[2])[mask_cords]))
            lab_loc.append('left') # want label to be written from right hand side (note units axis flips) otherwise long strings overruns the plus patch
            # manipulate the string
            field_str = ','.join([str(s_use) for s_use in np.unique(np.array(field_ra_dec[0])[mask_cords])])
            # finally check if the string is a mosaic add an 's'
            if field_str == 'mosaic':
                field_ids.append('mosaics')
            else:
                field_ids.append(field_str)
            
        else:
            LOG.info('No overlap for this coord')
            field_ids.append(str(np.array(field_ra_dec[0])[mask_cords][0]))
            lab_ra.append(float(np.array(field_ra_dec[1])[mask_cords][0])) # np float
            lab_dec.append(float(np.array(field_ra_dec[2])[mask_cords][0])) # np float
            lab_loc.append('center')


    return zip(field_ids, lab_ra, lab_dec, lab_loc)
