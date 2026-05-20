# Luke Maud - code based on plotmosaics code
# Do not evaluate type annotations at definition time.
from __future__ import annotations

from typing import TYPE_CHECKING

import itertools
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
import pipeline.domain.unitformat as unitformat

#from matplotlib.axes import Axes
#from matplotlib.figure import Figure
#from numpy.typing import NDArray
#from pipeline.domain import Field, MeasurementSet, Source 
from pipeline.domain.measures import ArcUnits, EquatorialArc
#from pipeline.infrastructure.utils.casa_types import DirectionDict


LOG = infrastructure.logging.get_logger(__name__)

# repeated code, also in the new "separation_angles.py"
#def _is_mosaic(
#        ms,
#        field_name
#) -> bool:
#    """ 
#    Code based loosly on imageparams_base
#    that used two small functions in a class to define if
#    a field/intent was a mosaic and its own defined 'field' 
#    parameter to get a list. Here we can do more simply
#    as we are dealing only with the TARGET and we 
#    passed a single field name, check it 
#    there are multiple ids for it#
#
#    ms is the measurement set object 
#    field is the field name
#    
#    """
#    is_f_mosaic = False
#    field_str_list = []
#
#    # Should we have a protection here for no field - e.g. calsurvey?
#    
#    # converting field to ids
#    fld_obj = ms.get_fields(intent='TARGET')
#    field_str_list = [fld.id for fld in fld_obj if
 #                     field_name.replace(' ', '') == fld.name.replace(' ','')]
 #                     # note matching string methodology used fromm imageparams_base code#
#
#    field_str_list = ','.join(str(fld_id) for fld_id in field_str_list)#
#
#    # again following imageparams_base
#    # because a string chain was now made, if there is a ','
#    # it means there is more than one field ID for the field name
#    # i.e. a mosaic 
#    for field_str in field_str_list:
#        if ',' in field_str:
#            is_f_mosaic = True#
#
#    return is_f_mosaic


def plot_separations(
        ms,
        figfile
) -> None:
    """
    Produce a plot of the position for each target 
    and the PHASE and CHECK calibrators with the 
    field types coloured by intent.
    """

    phase_fld = [fld for fld in ms.get_fields(intent='PHASE')]
    check_fld =[fld for fld in ms.get_fields(intent='CHECK')]  # no problem if there is not a field will continue, nothing to plot
    target_fld = [fld for fld in ms.get_fields(intent='TARGET')] 
    target_fld_final = [] # for appending fields after checking if the targets form a mosaic or not
    
    # if we have a mosaic, just pass the first position, append later name of 'mosaic'
    unique_tars = np.unique([fld.name for fld in target_fld])
    # need to loop these to consider what to append to the target_fld list
    for fld_unq_name in unique_tars:
        if utils.separation_angles.is_mosaic(ms,fld_unq_name):
            field_hold =   [fld for fld in ms.get_fields(intent='TARGET', name=fld_unq_name)][0] 
            field_hold.id = 'mosaic'
            target_fld_final.append(field_hold) # single 
        else:
            target_fld_final.extend([fld for fld in ms.get_fields(intent='TARGET', name=fld_unq_name)]) # list of list

    
    # now the field objects
    fields = list(itertools.chain.from_iterable([phase_fld, check_fld, target_fld_final])) # flatten all the lists to a single list, with PHASE(s) up front

   
    # longitude and latitude in radians for all fields  - NOTE EPHEMERIS appears to work with m.direction correctly, I assume if the ephemeris coods are imported already
    ra  = np.array([quanta.convert(f.mdirection['m0']['value'], 'rad')['value'] for f in fields])
    dec = np.array([quanta.convert(f.mdirection['m1']['value'], 'rad')['value'] for f in fields])

    # store the Reference RA, DEC, i.e. that of the PHASE is first listed 
    ref_ra  = ra[0]
    ref_dec = dec[0]  

    # compute offsets in longitude (taking into account the cos(lat) factor) and latitude, still in radians
    delta_ra  = np.cos(dec) * np.sin(ra - ref_ra)
    delta_dec = np.sin(dec) * np.cos(ref_dec) - np.cos(dec) * np.sin(ref_dec) * np.cos(ra - ref_ra)

    # some heuristics to determine the appropriate x- and y-range for plotting, adjusting the figure size as needed
    radians_to_deg = 180 / np.pi  # can use np.degrees below? 
    ra_range_deg  = (max(delta_ra)  - min(delta_ra))  * radians_to_deg
    dec_range_deg = (max(delta_dec) - min(delta_dec)) * radians_to_deg

    # testing indicates these are ok, previous (local) version calculated parameters but it made a mess
    smallest_beam = 1. # this is now in deg units
    pixels_per_beam = 60.
    min_size_in_pixels = 400.
    max_size_in_pixels = 2000.
    margin_x = 100.0  # margins outside the axes in pixels, approximate (the axes object is automatically resized anyway)
    margin_y = 80.0
    pixels_x = max(min_size_in_pixels, min(max_size_in_pixels, pixels_per_beam * ra_range_deg / smallest_beam))
    pixels_y = max(min_size_in_pixels, min(max_size_in_pixels, pixels_per_beam * dec_range_deg / smallest_beam))
    pixels_per_smallest_beam = smallest_beam / max(ra_range_deg / pixels_x, dec_range_deg / pixels_y)
    fontsize = max(8, min(12, 0.1 * pixels_per_smallest_beam))   # font size for labelling the field id 

    dpi = 100  # pixels per inch
    fig = plt.figure(figsize=((pixels_x + margin_x) / dpi, (pixels_y + margin_y) / dpi))
    ax = fig.add_subplot(1, 1, 1)

    # field labels overlap and become unintelligible if there are too many of them
    draw_field_labels = len(fields) <= 500

    legend_labels = {}
    legend_colours = {}

    legend_labels['PHASE']=Line2D(list(range(1)), list(range(1)), color='r', linewidth=2,linestyle='solid')
    legend_colours['PHASE']='r'

    legend_labels['TARGET']=Line2D(list(range(1)), list(range(1)), color='k', linewidth=2,linestyle='solid')
    legend_colours['TARGET']='k'

    if len(check_fld) > 0:
        legend_labels['CHECK']=Line2D(list(range(1)), list(range(1)), color='b', linewidth=2,linestyle='solid')
        legend_colours['CHECK']='b'        

    # Doing the plot     
    for field, rel_ra, rel_dec in zip(fields, delta_ra, delta_dec):
        x = rel_ra  * radians_to_deg
        y = rel_dec * radians_to_deg
        colour = get_circ_colour(field.name, phase_fld, check_fld)
        cir = Circle((x, y), radius=0.5 * smallest_beam, facecolor='none', edgecolor=colour,
                     linestyle='solid', alpha=0.6, linewidth=2, zorder=2)
        ax.add_patch(cir)
        ax.text(x, y, '{}'.format(field.id), ha='center', va='center', fontsize=fontsize, color=colour)


    # Title        
    title_string = f'{ms.basename}\n Separation from PHASE - {phase_fld[0].name}(#{phase_fld[0].id})  '
    # pad the end in the case the title is longer than x plot size this looks better - doesnt always work 
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


def get_circ_colour(
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

