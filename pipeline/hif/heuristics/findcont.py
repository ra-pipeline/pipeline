import os

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.utils as utils
from pipeline.extern.findContinuum import findContinuum
from pipeline.extern.findContinuum import countChannelsInRanges
from pipeline.extern.findContinuum import numberOfChannelsInCube
from pipeline.infrastructure import casa_tools

LOG = infrastructure.get_logger(__name__)


class FindContHeuristics:
    def __init__(self, context):
        self.context = context

    def find_continuum(self, dirty_cube: str, pb_cube: str | None = None, psf_cube: str | None = None,
                       single_continuum: bool = False, is_eph_obj: bool = False,
                       ref_ms_name: str = '', nbin: int = 1, dynrange_bw: str | None = None):

        """
        Continuum finding heuristics wrapper class. Its main input parameter is
        the name of a dirty cube. Optional arguments are names of PB and PSF
        cubes and a reference MS as well as some control parameters to steer the
        findContinuum algorithm in certain ways.

        Args:
            dirty_cube (str): Name of the dirty cube to use to find continuum
                frequency ranges
            pb_cube (str): Name of the PB cube
            psf_cube (str): Name of the PSF cube
            single_continuum (bool): Flag from the observing project setup to
                tell if an spw was meant to be a single continuum setup
            is_eph_obj (bool): Flag to tell if the source is an ephemeris object
            ref_ms_name (str): Name of the reference MS
            nbin (int): Binning factor
            dynrange_bw (str): Spectral dynamic range bandwidth

        Returns:
            cont_ranges_and_flags (dict): Dictionary of continuum ranges and
                flags
            png_name (str): Name of the findContinuum summary plot
            single_range_channel_fraction (float): Ratio of number of channels
                in single continuum range to total number of spw channels or
                999.0 if there is more than one range
            warning_strings (list): List of warning texts
            joint_mask_name (str): Name of the joint mask file
            momDiffSNR (float): Moment difference SNR
        """

        with casa_tools.ImageReader(dirty_cube) as image:
            stats = image.statistics()

        if stats['min'][0] == stats['max'][0]:
            LOG.error('Cube %s is constant at level %s.' % (dirty_cube, stats['max'][0]))
            return {'ranges': ['NONE'], 'flags': []}, 'none', 999.0, ['Cube %s is constant at level %s.' % (dirty_cube, stats['max'][0])], 'none', -999.0

        # Run continuum finder on cube
        channel_selection, png_name, aggregate_bw, all_continuum, warning_strings, joint_mask_name, momDiffSNR = \
            findContinuum(img=dirty_cube,
                          pbcube=pb_cube,
                          psfcube=psf_cube,
                          singleContinuum=single_continuum,
                          returnAllContinuumBoolean=True,
                          returnWarnings=True,
                          vis=ref_ms_name,
                          nbin=nbin,
                          spectralDynamicRangeBandWidth=dynrange_bw,
                          returnMomDiffSNR=True)

        # PIPE-74
        channel_counts = countChannelsInRanges(channel_selection)
        if 1 == len(channel_counts):
            single_range_channel_fraction = channel_counts[0]/float(numberOfChannelsInCube(dirty_cube))
        else:
            single_range_channel_fraction = 999.0

        flags = []
        if channel_selection == '':
            frequency_ranges_GHz = ['NONE']
        else:
            if all_continuum:
                flags.append('ALLCONT')

            if is_eph_obj:
                refer = 'SOURCE'
            else:
                refer = 'LSRK'

            frequency_ranges_GHz = [{'range': item, 'refer': refer} for item in utils.chan_selection_to_frequencies(dirty_cube, channel_selection, 'GHz')]

        if warning_strings[0]:
            flags.append('LOWBANDWIDTH')
        if warning_strings[1]:
            flags.append('LOWSPREAD')

        cont_ranges_and_flags = {'ranges': frequency_ranges_GHz, 'flags': flags}

        return cont_ranges_and_flags, png_name, single_range_channel_fraction, warning_strings, os.path.basename(joint_mask_name), momDiffSNR
