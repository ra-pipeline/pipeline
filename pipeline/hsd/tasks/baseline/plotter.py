"""Plotter for baseline subtraction result."""
import collections
import itertools
import os
from typing import TYPE_CHECKING, Generator, Iterable, List, Optional, Tuple, Union

import matplotlib.figure as figure
import matplotlib.pyplot as plt
import numpy
from numpy.ma.core import MaskedArray

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.renderer.logger as logger
from pipeline.h.tasks.common import atmutil
from pipeline.infrastructure import casa_tools
from pipeline.infrastructure.displays.plotstyle import casa5style_plot
from ..common import utils
from ..common import compress
from ..common import display
from ..common.display import DPIDetail, ch_to_freq, sd_polmap
from ..common import direction_utils as dirutil

if TYPE_CHECKING:
    from numbers import Integral

    from pipeline.infrastructure.launcher import Context
    from pipeline.domain.datatable import DataTableImpl as DataTable
    from pipeline.domain.measurementset import MeasurementSet


LOG = infrastructure.get_logger(__name__)

# A named tuple to store statistics of baseline quality
BinnedStat = collections.namedtuple('BinnedStat', 'bin_min_ratio bin_max_ratio bin_diff_ratio')


class PlotterPool(object):
    """Pool class to hold resources for plotting.

    TODO: this class is not useful. Should be removed in future.
          create_plotter must be separated from the class.
    """

    def __init__(self) -> None:
        """Construct PlotterPool instance."""
        self.pool = {}

    def create_plotter(self,
                       num_ra: int,
                       num_dec: int,
                       num_plane: int,
                       ralist: List[float],
                       declist: List[float],
                       direction_reference: Optional[str] = None,
                       brightnessunit: str = 'Jy/beam') -> display.SDSparseMapPlotter:
        """Create plotter instance.

        Args:
            num_ra: Number of panels along horizontal axis
            num_dec: Number of panels along vertical axis
            num_plane: Not used
            ralist: List of RA values for labeling
            declist: List of Dec values for labeling
            direction_reference: Directon reference string. Defaults to None.
            brightnessunit: Brightness unit string. Defaults to 'Jy/beam'.

        Returns:
            Plotter instance
        """
        fig = figure.Figure()
        plotter = display.SDSparseMapPlotter(fig, nh=num_ra, nv=num_dec,
                                             step=1, brightnessunit=brightnessunit)
        plotter.direction_reference = direction_reference
        plotter.setup_labels_absolute( ralist, declist )
        return plotter

    def done(self) -> None:
        """Close plotters registered to the pool."""
        for plotter in self.pool.values():
            plotter.done()


class PlotDataStorage(object):
    """Storage class to hold array data for plotting."""

    def __init__(self) -> None:
        """Construct PlotDataStorage instance.

        This class holds three sets of data storage, one dimensional
        numpy array with a certain length, and the data array that refers
        whole or part of data storage. They are assigned to map data (float),
        associated mask (bool), and integrated data (float), respectively.

        Each data array is multi-dimensional array with (npol, nchan) for
        integrated data while (nh, nv, npol, nchan) for other arrays.
        Each data storage is one-dimensional array whose length should be
        larger than the total number of elements for associated data array.

        Intension is to minimize the number of memory allocation/de-allocation.
        To do that, data storage (memory for array) and data array (actual array
        accessed by the user) are separated so that allocated memory is reused
        if possible. Data storage is resized only when size of data storage is
        smaller than the size of data array which can vary upon request from
        the user.

        The constructor initializes data storage as zero-length array, which
        effectively means no memory allocation for the data array, and data
        array nominally refers to empty data storage. Actual memory allocation
        will be performed when the user first provides the array shape.
        """
        self.map_data_storage = numpy.zeros((0), dtype=float)
        self.integrated_data_storage = numpy.zeros((0), dtype=float)
        self.map_mask_storage = numpy.zeros((0), dtype=bool)
        self.integrated_mask_storage = numpy.zeros((0), dtype=bool)
        self.map_data = self.map_data_storage
        self.integrated_data = self.integrated_data_storage
        self.map_mask = self.map_mask_storage
        self.integrated_mask = self.integrated_mask_storage

    def resize_storage(self, num_ra: int, num_dec: int, num_pol: int, num_chan: int) -> None:
        """Resize storage.

        Resize storage array if necessary, i.e., only when current size is less than
        requested size calculated from input args. Data array refers storage but is
        reshaped to match the number of panels of sparse profile map.

        Args:
            num_ra: Number of panels along horizontal axis
            num_dec: Number of panels along vertical axis
            num_pol: Number of polarizations
            num_chan: Number of spectral channels
        """
        num_integrated = num_pol * num_chan
        num_map = num_ra * num_dec * num_integrated
        if len(self.map_data_storage) < num_map:
            self.map_data_storage = numpy.resize(self.map_data_storage, num_map)
        self.map_data = numpy.reshape(self.map_data_storage[:num_map], (num_ra, num_dec, num_pol, num_chan))

        if len(self.map_mask_storage) < num_map:
            self.map_mask_storage = numpy.resize(self.map_mask_storage, num_map)
        self.map_mask = numpy.reshape(self.map_mask_storage[:num_map], (num_ra, num_dec, num_pol, num_chan))

        if len(self.integrated_data_storage) < num_integrated:
            self.integrated_data_storage = numpy.resize(self.integrated_data_storage, num_integrated)
        self.integrated_data = numpy.reshape(self.integrated_data_storage[:num_integrated], (num_pol, num_chan))


class BaselineSubtractionPlotManager(object):
    """Manages any operation necessary to produce baseline subtraction plot."""

    @staticmethod
    def _generate_plot_meta_table(
        spw_id: int,
        polarization_ids: List[int],
        grid_table: List[List[Union[int, float, numpy.ndarray]]]
    ) -> Generator[List[Union[int, float]], None, None]:
        """Extract necessary data from grid_table.

        Rows of grid_table are filtered by spw and polarization ids,
        and only spatial location of the grid are extracted.

        Args:
            spw_id: spw id for filtering
            polarization_ids: polarization ids for filtering
            grid_table: grid_table generated by simplegrid module

        Yields:
            List of spatial position information (pixel and world)
        """
        for row in grid_table:
            if row[0] == spw_id and row[1] in polarization_ids:
                new_row_entry = row[2:6]
                yield new_row_entry

    @staticmethod
    def generate_plot_meta_table(
        spw_id: int,
        polarization_ids: List[int],
        grid_table: List[List[Union[int, float, numpy.ndarray]]]
    ) -> List[List[Union[int, float]]]:
        """Return metadata table for plotting.

        Metadata table for given spw and polarization ids contains
        spatial position information in both pixel and world coordinates.

        Args:
            spw_id: spw id for filtering
            polarization_ids: polarization ids for filtering
            grid_table: grid_table generated by simplegrid module

        Returns:
            Metadata table (plot_table). The table is intended to be used jointly
            with the return value of generate_plot_rowlist.
            plot_table layout: [RA_ID, DEC_ID, RA_DIR, DEC_DIR]

                [[0, 0, RA0, DEC0], <- plane 0
                 [0, 0, RA0, DEC0], <- plane 1
                 [0, 0, RA0, DEC0], <- plane 2
                 [1, 0, RA1, DEC0], <- plane 0
                  ...
                 [M, 0, RAM, DEC0], <- plane 2
                 [0, 1, RA0, DEC1], <- plane 0
                 ...
                 [M, N, RAM, DECN]] <- plane 2
        """
        new_table = list(BaselineSubtractionPlotManager._generate_plot_meta_table(spw_id,
                                                                                  polarization_ids,
                                                                                  grid_table))
        return new_table

    @staticmethod
    def _generate_plot_rowlist(
        origin_ms_id: int,
        antenna_id: int,
        spw_id: int,
        polarization_ids: List[int],
        grid_table: List[List[Union[int, float, numpy.ndarray]]],
        grid_list: List[Tuple[int, int]]
    ) -> Generator[numpy.ndarray, None, None]:
        """Yield list of datatable row ids that match selection.

        Extract list of datatable row ids that match the selection for
        MS, spw, polarization, and spatial grid location. Yield row
        ids as numpy array.

        Args:
            origin_ms_id: MS id for selection
            antenna_id: Antenna id for selection
            spw_id: Spw id for selection
            polarization_ids: List of polarization ids
            grid_table: grid_table generated by simplegrid module
            grid_list: Spatial grid indices (ix, iy) for selection

        Yields:
            List of datatable row ids that matches selection
        """
        for row in grid_table:
            if row[0] == spw_id and row[1] in polarization_ids and (row[2], row[3]) in grid_list:
                new_row_entry = numpy.fromiter((r[3] for r in row[6] if r[-1] == origin_ms_id and r[-2] == antenna_id),
                                               dtype=int)
                yield new_row_entry

    @staticmethod
    def generate_plot_rowlist(
        origin_ms_id: int,
        antenna_id: int,
        spw_id: int,
        polarization_ids: List[int],
        grid_table: List[List[Union[int, float, numpy.ndarray]]],
        plot_table: List[List[Union[int, float]]],
        each_plane: List[int]
    ) -> List[int]:
        """Generate list of datatable row ids for plotting.

        Extract list of datatable row ids that matches selection for
        MS, spw, polarization, and spatial grid location. Return
        one-dimensional list of row ids to process.

        Args:
            origin_ms_id: MS id for selection
            antenna_id: Antenna id for selection
            spw_id: Spw id for selection
            polarization_ids: List of polarization ids for selection
            grid_table: grid_table generated by simplegrid module
            plot_table: Metadata table generated by generate_plot_meta_table
            each_plane: List of indices for grid_table/plot_table

        Returns:
            List of datatable row ids for plotting. Return value is intended
            to be used jointly with the table returned by generate_plot_meta_table.
        """
        xlist = [ plot_table[idx][0] for idx in each_plane ]
        ylist = [ plot_table[idx][1] for idx in each_plane ]
        grid_list = list(zip( xlist, ylist ))
        new_table = list(BaselineSubtractionPlotManager._generate_plot_rowlist(origin_ms_id,
                                                                               antenna_id,
                                                                               spw_id,
                                                                               polarization_ids,
                                                                               grid_table,
                                                                               grid_list))
        return list(itertools.chain.from_iterable(new_table))

    def __init__(self, context: 'Context', datatable: 'DataTable') -> None:
        """Construct BaselineSubtractionPlotManager instance.

        Args:
            context: Pipeline context
            datatable: DataTable instance
        """
        self.context = context
        self.datatable = datatable
        stage_number = self.context.task_counter
        self.stage_dir = os.path.join(self.context.report_dir, "stage%d" % stage_number)
        self.baseline_quality_stat = dict()

        if basetask.DISABLE_WEBLOG:
            self.pool = None
            self.prefit_storage = None
            self.postfit_storage = None
        else:
            if not os.path.exists(self.stage_dir):
                os.makedirs(self.stage_dir, exist_ok=True)   #handle race condition in Tier-0 operation gracefully

            self.pool = PlotterPool()
            self.prefit_storage = PlotDataStorage()
            self.postfit_storage = PlotDataStorage()

    def initialize(self, ms: 'MeasurementSet', blvis: str) -> bool:
        """Initialize plot manager with given MS.

        Args:
            ms: Domain object for the MS before baseline subtraction
            blvis: Name of the MS after baseline subtraction

        Returns:
            Initialization status
        """
        if basetask.DISABLE_WEBLOG:
            return True

        self.ms = ms

        origin_ms = self.context.observing_run.get_ms(self.ms.origin_ms)
        self.out_rowmap = utils.make_row_map(origin_ms, blvis)
        self.in_rowmap = None if ms.name == ms.origin_ms else utils.make_row_map(origin_ms, ms.name)
        self.prefit_data = ms.name
        self.postfit_data = blvis

        return True

    def finalize(self) -> None:
        """Finalize plot manager.

        Release resources allocated for plotting.
        """
        if self.pool is not None:
            self.pool.done()

    def resize_storage(self, num_ra: int, num_dec: int, num_pol: int, num_chan: int) -> None:
        """Resize storage as necessary.

        Args:
            num_ra: Number of panels along horizontal axis
            num_dec: Number of panels along vertical axis
            num_pol: Number of polarizations
            num_chan: Number of spectral channels
        """
        self.prefit_storage.resize_storage(num_ra, num_dec, num_pol, num_chan)
        self.postfit_storage.resize_storage(num_ra, num_dec, num_pol, num_chan)

    @casa5style_plot
    def plot_spectra_with_fit(
        self,
        field_id: int,
        antenna_id: int,
        spw_id: int,
        org_direction: dirutil.Direction,
        grid_table: Optional[List[List[Union[int, float, numpy.ndarray]]]] = None,
        deviation_mask: Optional[List[Tuple[int, int]]] = None,
        channelmap_range: Optional[List[Tuple[int, int, bool]]] = None,
        edge: Optional[List[int]] = None,
        showatm: bool = True
    ) -> List[compress.CompressedObj]:
        """Create various types of plots.

        For given set of field, antenna, and spw ids, this method generates
        plots of the following types:

            - sparse profile map for raw spectra before baseline subtraction
            - sparse profile map for spatially averaged spectra before baseline subtraction
            - sparse profile map for raw spectra after baseline subtraction
            - sparse profile map for spatially averaged spectra after baseline subtraction
            - visual illustration of baseline flatness after baseline subtraction

        Args:
            field_id: Field id to process
            antenna_id: Antnena id to process
            spw_id: Spw id to process. Should be the real spw id.
            org_direction: direction of the origin
            grid_table: grid_table generated by simplegrid module
            deviation_mask: List of channel ranges identified as "deviation mask". Each range
                            is represented as a tuple of start and end channels. Those ranges
                            are shown as red rectangle to indicate they are excluded from the fit.
                            None means no deviation mask is provided.
            channelmap_range: List of channel ranges identified as astronomical lines by
                              line detection and validation process. Channel range is represented
                              as a tuple of line center channel, line width in channel, and
                              validation result (boolean). Those ranges are shown as cyan rectangle
                              to indicate they are excluded from the fit. None means no line ranges
                              are provided.
            edge: Edge channels to exclude. Plot whole channels if None is given.
            showatm: Whether or not overlay ATM transmission curve. Defaults to True.

        Raises:
            Exception: Invalid plot type (maybe internal error)

        Returns:
            List of compressed Plot objects
        """
        if basetask.DISABLE_WEBLOG:
            return []

        if grid_table is None:
            return []

        # convert channelmap_range to plotter-aware format
        if channelmap_range is None:
            line_range = None
        else:
            line_range = [[r[0] - 0.5 * r[1], r[0] + 0.5 * r[1]] for r in channelmap_range if r[2] is True]
            if len(line_range) == 0:
                line_range = None

        self.field_id = field_id
        self.antenna_id = antenna_id
        self.spw_id = spw_id
        self.virtual_spw_id = self.context.observing_run.real2virtual_spw_id(self.spw_id, self.ms)
        data_desc = self.ms.get_data_description(spw=spw_id)
        num_pol = data_desc.num_polarizations
        self.pol_list = numpy.arange(num_pol, dtype=int)
        source_name = self.ms.fields[self.field_id].source.name.replace(' ', '_').replace('/', '_')
        LOG.debug('Generating plots for source %s ant %s spw %s',
                  source_name, self.antenna_id, self.spw_id)

        outprefix_template = lambda x: 'spectral_plot_%s_subtraction_%s_%s_ant%s_spw%s'%(x,
                                                                                         '.'.join(self.ms.basename.split('.')[:-1]),
                                                                                         source_name,
                                                                                         self.antenna_id,
                                                                                         self.virtual_spw_id)
        prefit_prefix = os.path.join(self.stage_dir, outprefix_template('before'))
        postfit_prefix = os.path.join(self.stage_dir, outprefix_template('after'))
        LOG.debug('prefit_prefix=\'%s\'', os.path.basename(prefit_prefix))
        LOG.debug('postfit_prefix=\'%s\'', os.path.basename(postfit_prefix))

        if showatm is True:
            atm_freq, atm_transmission = atmutil.get_transmission(vis=self.ms.name, antenna_id=self.antenna_id,
                                                                  spw_id=self.spw_id, doplot=False)
        else:
            atm_transmission = None
            atm_freq = None
        plot_list = self.plot_profile_map_with_fit(prefit_prefix, postfit_prefix, grid_table,
                                                   deviation_mask, line_range,
                                                   org_direction,
                                                   atm_transmission, atm_freq, edge)
        ret = []
        for plot_type, plots in plot_list.items():
            if plot_type == 'pre_fit':
                ptype = 'sd_sparse_map_before_subtraction_raw'
                data = self.prefit_data
            elif plot_type == 'post_fit':
                ptype = 'sd_sparse_map_after_subtraction_raw'
                data = self.postfit_data
            elif plot_type == 'pre_fit_avg':
                ptype = 'sd_sparse_map_before_subtraction_avg'
                data = self.prefit_data
            elif plot_type == 'post_fit_flatness':
                ptype = 'sd_spectrum_after_subtraction_flatness'
                data = self.postfit_data
            else:
                raise Exception('Unrecognized plot type.')
            for pol, figfile in plots.items():
                if os.path.exists(figfile):
                    parameters = {'intent': 'TARGET',
                                  'spw': self.virtual_spw_id, # parameter for plots are virtual spw id
                                  'pol': sd_polmap[pol],
                                  'ant': self.ms.antennas[self.antenna_id].name,
                                  'vis': os.path.basename(self.ms.origin_ms),
                                  'type': ptype,
                                  'file': data}
                    plot = logger.Plot(figfile,
                                       x_axis='Frequency',
                                       y_axis='Intensity',
                                       field=source_name,
                                       parameters=parameters)
                    ret.append(compress.CompressedObj(plot))
                    del plot
        return ret

    def plot_profile_map_with_fit(
        self,
        prefit_figfile_prefix: str,
        postfit_figfile_prefix: str,
        grid_table: List[List[Union[int, float, numpy.ndarray]]],
        deviation_mask: Optional[List[Tuple[int, int]]],
        line_range: Optional[List[Tuple[int, int]]],
        org_direction: dirutil.Direction,
        atm_transmission: Optional[numpy.ndarray],
        atm_frequency: Optional[numpy.ndarray],
        edge: Optional[List[int]]
    ) -> dict:
        """Create various type of plots.

        This method produces the following plots.

            - sparse profile map for raw spectra before baseline subtraction
            - sparse profile map for spatially averaged spectra before baseline subtraction
            - sparse profile map for raw spectra after baseline subtraction
            - sparse profile map for spatially averaged spectra after baseline subtraction
            - visual illustration of baseline flatness after baseline subtraction

        Args:
            prefit_figfile_prefix: Prefix string for the filename (before baseline subtraction)
            postfit_figfile_prefix: Prefix for the filename (after baseline subtraction)
            grid_table: grid_table generated by simplegrid module
            deviation_mask: List of channel ranges identified as the "deviation mask"
            line_range: List of channel ranges identified as astronomical line
            org_direction: direction of the origin
            atm_transmission: ATM tranmission data
            atm_frequency: frequency label associated with ATM transmission
            edge: Edge channels excluded from the baseline fitting

        Returns:
            Dictionary containing names of the figure with plot type and
            polarization id as keys

                plot_list[plot_type][polarization_id] = figfile
        """
        ms = self.ms
        origin_ms = self.context.observing_run.get_ms(ms.origin_ms)
        origin_ms_id = self.context.observing_run.measurement_sets.index(origin_ms)
        antid = self.antenna_id
        spwid = self.spw_id
        virtual_spwid = self.virtual_spw_id
        polids = self.pol_list
        prefit_data = self.prefit_data
        postfit_data = self.postfit_data
        out_rowmap = self.out_rowmap
        in_rowmap = self.in_rowmap

        dtrows = self.datatable.getcol('ROW')

        # get brightnessunit from MS
        # default is Jy/beam
        bunit = utils.get_brightness_unit(ms.name, defaultunit='Jy/beam')

        # grid_table is baseed on virtual spw id
        num_ra, num_dec, num_plane, rowlist = analyze_plot_table(ms,
                                                                 origin_ms_id,
                                                                 antid,
                                                                 virtual_spwid,
                                                                 polids,
                                                                 grid_table,
                                                                 org_direction)

        # ralist/declist holds coordinates for axis labels (center of each panel)
        ralist  = [ r.get('RA')  for r in rowlist if r['DECID']==0 ]
        declist = [ r.get('DEC') for r in rowlist if r['RAID'] ==0 ]

        plotter = self.pool.create_plotter(num_ra, num_dec, num_plane, ralist, declist,
                                           direction_reference=self.datatable.direction_ref,
                                           brightnessunit=bunit)
        LOG.debug('vis %s ant %s spw %s plotter has %s axes',
                  ms.basename, antid, spwid, len(plotter.axes.figure.axes))
#         LOG.info('axes list: {}', [x.__hash__()  for x in plotter.axes.figure.axes])
        spw = ms.spectral_windows[spwid]
        nchan = spw.num_channels
        data_desc = ms.get_data_description(spw=spw)
        npol = data_desc.num_polarizations
        LOG.debug('nchan=%s', nchan)

        self.resize_storage(num_ra, num_dec, npol, nchan)

        frequency = numpy.fromiter((spw.channels.chan_freqs[i] * 1.0e-9 for i in range(nchan)),
                                   dtype=numpy.float64)  # unit in GHz
        LOG.debug('frequency=%s~%s (nchan=%s)',
                  frequency[0], frequency[-1], len(frequency))

        if out_rowmap is None:
            out_rowmap = utils.make_row_map(origin_ms, postfit_data)
        postfit_integrated_data, postfit_map_data = get_data(postfit_data, dtrows,
                                                             num_ra, num_dec, nchan, npol,
                                                             rowlist, rowmap=out_rowmap,
                                                             integrated_data_storage=self.postfit_storage.integrated_data,
                                                             map_data_storage=self.postfit_storage.map_data,
                                                             map_mask_storage=self.postfit_storage.map_mask)
        if line_range is not None:
            lines_map = get_lines(self.datatable, num_ra, npol, rowlist)
        else:
            lines_map = None

        plot_list = {}

        # plot post-fit spectra
        plot_list['post_fit'] = {}
        plotter.setup_reference_level(0.0)
        plotter.set_deviation_mask(deviation_mask)
        plotter.set_edge(edge)
        plotter.set_atm_transmission(atm_transmission, atm_frequency)
        plotter.set_global_scaling()
        if utils.is_nro(self.context):
            plotter.set_channel_axis()
        for ipol in range(npol):
            postfit_figfile = postfit_figfile_prefix + '_pol%s.png' % ipol
            #LOG.info('#TIMING# Begin SDSparseMapPlotter.plot(postfit,pol%s)'%(ipol))
            if lines_map is not None:
                plotter.setup_lines(line_range, lines_map[ipol])
            else:
                plotter.setup_lines(line_range)
            plotter.plot(postfit_map_data[:, :, ipol, :],
                         postfit_integrated_data[ipol],
                         frequency, figfile=postfit_figfile)
            #LOG.info('#TIMING# End SDSparseMapPlotter.plot(postfit,pol%s)'%(ipol))
            if os.path.exists(postfit_figfile):
                plot_list['post_fit'][ipol] = postfit_figfile

        prefit_integrated_data, prefit_map_data = get_data(prefit_data, dtrows,
                                                           num_ra, num_dec,
                                                           nchan, npol, rowlist,
                                                           rowmap=in_rowmap,
                                                           integrated_data_storage=self.prefit_storage.integrated_data,
                                                           map_data_storage=self.prefit_storage.map_data,
                                                           map_mask_storage=self.prefit_storage.map_mask)

        # fit_result shares its storage with postfit_map_data to reduce memory usage
        fit_result = postfit_map_data
        for x in range(num_ra):
            for y in range(num_dec):
                prefit = prefit_map_data[x][y]
                if not numpy.all(prefit == display.NoDataThreshold):
                    postfit = postfit_map_data[x][y]
                    fit_result[x, y] = prefit - postfit
                else:
                    fit_result[x, y, ::] = display.NoDataThreshold

        # plot pre-fit spectra
        plot_list['pre_fit'] = {}
        plotter.setup_reference_level(None)
        plotter.unset_global_scaling()
        for ipol in range(npol):
            prefit_figfile = prefit_figfile_prefix + '_pol%s.png'%(ipol)
            #LOG.info('#TIMING# Begin SDSparseMapPlotter.plot(prefit,pol%s)'%(ipol))
            if lines_map is not None:
                plotter.setup_lines(line_range, lines_map[ipol])
            else:
                plotter.setup_lines(line_range)
            plotter.plot(prefit_map_data[:, :, ipol, :],
                         prefit_integrated_data[ipol],
                         frequency, fit_result=fit_result[:, :, ipol, :], figfile=prefit_figfile)
            #LOG.info('#TIMING# End SDSparseMapPlotter.plot(prefit,pol%s)'%(ipol))
            if os.path.exists(prefit_figfile):
                plot_list['pre_fit'][ipol] = prefit_figfile

        del prefit_map_data, postfit_map_data, fit_result

        prefit_averaged_data = get_averaged_data(prefit_data, dtrows,
                                                 num_ra, num_dec,
                                                 nchan, npol, rowlist,
                                                 rowmap=in_rowmap,
                                                 map_data_storage=self.prefit_storage.map_data,
                                                 map_mask_storage=self.prefit_storage.map_mask)

        if line_range is not None:
            lines_map_avg = get_lines2(prefit_data, self.datatable, num_ra,
                                       rowlist, polids, rowmap=in_rowmap)
        else:
            lines_map_avg = None
        # plot pre-fit averaged spectra
        plot_list['pre_fit_avg'] = {}
        plotter.setup_reference_level(None)
        plotter.unset_global_scaling()
        for ipol in range(npol):
            prefit_avg_figfile = prefit_figfile_prefix + '_avg_pol{}.png'.format(ipol)
            if lines_map_avg is not None:
                plotter.setup_lines(line_range, lines_map_avg[ipol])
            else:
                plotter.setup_lines(line_range)
            plotter.plot(prefit_averaged_data[:, :, ipol, :],
                         prefit_integrated_data[ipol],
                         frequency, fit_result=None, figfile=prefit_avg_figfile)

            if os.path.exists(prefit_avg_figfile):
                plot_list['pre_fit_avg'][ipol] = prefit_avg_figfile

        del prefit_integrated_data, prefit_averaged_data

        plotter.done()

        # baseline flatness plots
        plot_list['post_fit_flatness'] = {}
        for ipol in range(npol):
            postfit_qa_figfile = postfit_figfile_prefix + '_flatness_pol%s.png' % ipol
            stat = self.analyze_and_plot_flatness(postfit_integrated_data[ipol],
                                                  frequency, line_range,
                                                  deviation_mask,  edge, bunit,
                                                  postfit_qa_figfile)
            if os.path.exists(postfit_qa_figfile):
                plot_list['post_fit_flatness'][ipol] = postfit_qa_figfile
                if stat:
                    self.baseline_quality_stat[postfit_qa_figfile] = [stat]

        del postfit_integrated_data

        return plot_list

    def analyze_and_plot_flatness(self, spectrum: List[float], frequency: List[float],
                         line_range: Optional[List[Tuple[float, float]]],
                         deviation_mask: Optional[List[Tuple[int, int]]],
                         edge: Tuple[int, int], brightnessunit: str,
                         figfile: str) -> Optional[BinnedStat]:
        """
        Calculate baseline flatness of a spectrum and create a plot.

        Args:
            spectrum: A spectrum to analyze baseline flatness and plot.
            frequency: Frequency values of each element in spectrum.
            line_range: ID ranges in spectrum array that should be considered
                as spectral lines and eliminated from inspection of baseline
                flatness.
            deviation_mask: ID ranges of deviation mask. These ranges are also
                eliminated from inspection of baseline flatness.
            edge: Number of elements in left and right edges that should be
                eliminated from inspection of baseline flatness.
            brightnessunit: Brightness unit of spectrum.
            figfile: A file name to save figure.

        Returns:
            Statistic information to evaluate baseline flatness.
        """
        masked_data = numpy.ma.masked_array(spectrum, mask=False)
        if edge is not None:
            (ch1, ch2) = edge
            masked_data.mask[0:ch1] = True
            masked_data.mask[len(masked_data)-ch2:] = True
        if line_range is not None:
            for chmin, chmax in line_range:
                masked_data.mask[int(chmin):int(numpy.ceil(chmax))+1] = True
        if deviation_mask is not None:
            for chmin, chmax in deviation_mask:
                masked_data.mask[chmin:chmax+1] = True
        nbin = 20 if len(frequency) >= 512 else 10
        binned_freq, binned_data = binned_mean_ma(frequency, masked_data, nbin)
        stddev = masked_data.std()
        if binned_data.count() < 2 \
           or stddev is numpy.ma.masked \
           or not numpy.isfinite(stddev):
            # not enough valid data or stddev is invalid
            return None
        bin_min = numpy.nanmin(binned_data)
        bin_max = numpy.nanmax(binned_data)
        stat = BinnedStat(bin_min_ratio=bin_min/stddev,
                          bin_max_ratio=bin_max/stddev,
                          bin_diff_ratio=(bin_max-bin_min)/stddev)
        # create a plot
        xmin = min(frequency[0], frequency[-1])
        xmax = max(frequency[0], frequency[-1])
        ymin = -3*stddev
        ymax = 3*stddev
        plt.clf()
        plt.plot(frequency, spectrum, color='b', linestyle='-', linewidth=0.4)
        plt.axis((xmin, xmax, ymin, ymax))
        plt.gca().get_xaxis().get_major_formatter().set_useOffset(False)
        plt.gca().get_yaxis().get_major_formatter().set_useOffset(False)
        plt.title('Spatially Averaged Spectrum')
        plt.ylabel(f'Intensity ({brightnessunit})')
        plt.xlabel('Frequency (GHz)')
        if edge is not None:
            (ch1, ch2) = edge
            fedge0 = ch_to_freq(0, frequency)
            fedge1 = ch_to_freq(ch1-1, frequency)
            fedge2 = ch_to_freq(len(frequency)-ch2, frequency)
            fedge3 = ch_to_freq(len(frequency)-1, frequency)
            plt.axvspan(fedge0, fedge1, color='lightgray')
            plt.axvspan(fedge2, fedge3, color='lightgray')
        if line_range is not None:
            for chmin, chmax in line_range:
                fmin = ch_to_freq(chmin, frequency)
                fmax = ch_to_freq(chmax, frequency)
                plt.axvspan(fmin, fmax, color='cyan')
        if deviation_mask is not None:
            for chmin, chmax in deviation_mask:
                fmin = ch_to_freq(chmin, frequency)
                fmax = ch_to_freq(chmax, frequency)
                plt.axvspan(fmin, fmax, ymin=0.97, ymax=1.0, color='red')
        plt.hlines([-stddev, 0.0, stddev], xmin, xmax, colors='k', linestyles='dashed')
        plt.plot(binned_freq, binned_data, 'ro')
        plt.savefig(figfile, dpi=DPIDetail)
        return stat


def generate_grid_panel_map(ngrid: int, npanel: int, num_plane: int = 1) -> Generator[List[int], None, None]:
    """Yield list of grid table indices that belong to the sparse map panel.

    Args:
        ngrid: Number of grid positions
        npanel: Number of panels
        num_plane: Number of planes per grid position. Defaults to 1.

    Yields:
        List of indices for the grid table
    """
    ng = ngrid // npanel
    mg = ngrid % npanel
    ng_per_panel = [ng * num_plane for i in range(npanel)]
    for i in range(mg):
        ng_per_panel[i] += num_plane

    s = 0
    e = 0
    for i in range(npanel):
        s = e
        e = s + ng_per_panel[i]
        yield list(range(s, e))


def configure_1d_panel(
    nx: int,
    ny: int,
    num_plane: int = 1
) -> Tuple[List[List[int]], List[List[int]]]:
    """Configure linear mapping between grid table index and sparse map panel.

    When number of grid positions, nx * ny, exceeds 50, neighboring positions
    are combined so that number of sparse map panels does not exceed 50.

    Args:
        nx: Number of grid positions along horizontal axis
        ny: Number of grid positions along vertical axis
        num_plane: Number of planes per grid position. Defaults to 1.

    Returns:
        Linear mapping between grid table index and sparse map panel
    """
    max_panels = 50
    num_panels = nx * ny

    nnx = nx
    nny = ny
    if num_panels > max_panels:
        div = lambda x: x // 2 + x % 2
        LOG.debug('original: {} x {} = {}'.format(nx, ny, num_panels))
        ndiv = 0
        nnp = num_panels
        while nnp > max_panels:
            nnx = div(nnx)
            nny = div(nny)
            nnp = nnx * nny
            ndiv += 1
            LOG.trace('div {}: {} x {} = {}'.format(ndiv, nnx, nny, nnp))
        LOG.debug('processed: {} x {} = {}'.format(nnx, nny, nnp))

    xpanel = list(generate_grid_panel_map(nx, nnx, num_plane))
    ypanel = list(generate_grid_panel_map(ny, nny, num_plane))

    return xpanel, ypanel


def configure_2d_panel(
    xpanel: List[List[int]],
    ypanel: List[List[int]],
    ngridx: int,
    ngridy: int,
    num_plane: int = 3
) -> List[List[int]]:
    """Confure two-dimensional mapping between grid table and sparse map panel.

    Args:
        xpanel: Linear mapping result returned by configure_1d_panel
        ypanel: Linear mapping result returned by configure_1d_panel
        ngridx: Number of grid positions along horizontal axis
        ngridy: Number of grid positions along vertical axis
        num_plane: Number of planes per grid position. Defaults to 3.

    Returns:
        Two-dimensional mapping between grid table and sparse map panel
    """
    xypanel = []
    for ygrid in ypanel:
        for xgrid in xpanel:
            p = []
            for y in ygrid:
                for x in xgrid:
                    a = ngridx * num_plane * y + num_plane * x
                    p.extend(list(range(a, a + num_plane)))
            xypanel.append(p)
    return xypanel


#@utils.profiler
def analyze_plot_table(
    ms: 'MeasurementSet',
    origin_ms_id: int,
    antid: int,
    virtual_spwid: int,
    polids: List[int],
    grid_table: List[List[Union[int, float, numpy.ndarray]]],
    org_direction: dirutil.Direction
) -> Tuple[int, int, int, List[dict]]:
    """Create and analyze plot table.

    Extract datatable row ids that match the selection given by
    MS id, antenna id, (virtual) spw id, and polarization ids, and
    associate them with the sparse map panels.

    Args:
        ms: Domain object for the MS (not used)
        origin_ms_id: MS id for selection
        antid: Antenna id for selection
        virtual_spwid: Virtual spw id for selection
        polids: List of polarization ids for selection
        grid_table: grid_table created by simplegrid module
        org_direction: direction of the origin

    Returns:
        Position information and associated datatable row ids
        for each sparse map positions
    """
    # plot table is separated into two parts: meta data part and row list part
    # plot_table layout: [RA_ID, DEC_ID, RA_DIR, DEC_DIR]
    # [[0, 0, RA0, DEC0], <- plane 0
    #  [0, 0, RA0, DEC0], <- plane 1
    #  [0, 0, RA0, DEC0], <- plane 2
    #  [1, 0, RA1, DEC0], <- plane 0
    #   ...
    #  [M, 0, RAM, DEC0], <- plane 2
    #  [0, 1, RA0, DEC1], <- plane 0
    #  ...
    #  [M, N, RAM, DECN]] <- plane 2
    plot_table = BaselineSubtractionPlotManager.generate_plot_meta_table(virtual_spwid,
                                                                         polids,
                                                                         grid_table)
    num_grid_rows = len(plot_table)  # num_plane * num_grid_ra * num_grid_dec
    assert num_grid_rows > 0
    num_grid_dec = plot_table[-1][1] + 1
    num_grid_ra = plot_table[-1][0] + 1
    num_plane = num_grid_rows // (num_grid_dec * num_grid_ra)
    LOG.debug('num_grid_ra=%a, num_grid_dec=%s, num_plane=%s, num_grid_rows=%s',
              num_grid_ra, num_grid_dec, num_plane, num_grid_rows)
    xpanel, ypanel = configure_1d_panel(num_grid_ra, num_grid_dec)
    num_ra = len(xpanel)
    num_dec = len(ypanel)
    each_grid = configure_2d_panel(xpanel, ypanel, num_grid_ra, num_grid_dec, num_plane)
    rowlist = [{} for i in range(num_dec * num_ra)]

    for row_index, each_plane in enumerate(each_grid):
        dataids = BaselineSubtractionPlotManager.generate_plot_rowlist( origin_ms_id,
                                                                        antid,
                                                                        virtual_spwid,
                                                                        polids,
                                                                        grid_table,
                                                                        plot_table,
                                                                        each_plane )
        raid = row_index % num_ra
        decid = row_index // num_ra
        ralist = [plot_table[i][2] for i in each_plane]
        declist = [plot_table[i][3] for i in each_plane]
        ra = numpy.mean(ralist)
        dec = numpy.mean(declist)
        if org_direction is not None:
            ra, dec = dirutil.direction_recover( ra, dec, org_direction )

        rowlist[row_index].update(
                {"RAID": raid, "DECID": decid, "RA": ra, "DEC": dec,
                 "IDS": dataids})
        LOG.trace('RA %s DEC %s: dataids=%s',
                  raid, decid, dataids)

    return num_ra, num_dec, num_plane, rowlist


#@utils.profiler
def get_data(
    infile: str,
    dtrows: numpy.ndarray,
    num_ra: int,
    num_dec: int,
    num_chan: int,
    num_pol: int,
    rowlist: dict,
    rowmap: Optional[dict] = None,
    integrated_data_storage: Optional[numpy.ndarray] = None,
    integrated_mask_storage: Optional[numpy.ndarray] = None,
    map_data_storage: Optional[numpy.ndarray] = None,
    map_mask_storage: Optional[numpy.ndarray] = None
) -> Tuple[numpy.ma.masked_array, numpy.ma.masked_array]:
    """Create array data for sparse map.

    Computes two masked array data for sparse map. One is the integrated
    spectrum averaged over whole spectral data regardless of their spatial
    position, which is displayed in the top panel of the figure.
    Another array is the spectra for sparse map averaged for each spatial
    position of the sparse map panel. Spatial grouping information is
    held by rowlist.

    Args:
        infile: Name of the MS
        dtrows: List of datatable rows
        num_ra: Number of panels along horizontal axis
        num_dec: Number of panels along vertical axis
        num_chan: Number of spectral channels
        num_pol: Number of polarizaionts
        rowlist: List of datatable row ids per sparse map panel with metadata
        rowmap: Row mapping between original (calibrated) MS and the MS
                specified by infile. It will be EchoDictionary if None is given.
        integrated_data_storage: Storage for integrated spectrum. If None is given,
                                 new array is created.
        integrated_mask_storage: Storage for integrated mask (not used).
        map_data_storage: Storage for sparse map. If None is given, new array is created.
        map_mask_storage: Storage for sparse map mask. If None is given, new array is created.

    Returns:
        Two masked arrays corresponding to integrated spectrum and sparse map data.
        The former has the shape of (npol, nchan) while tha latter is four-dimensional,
        (nx, ny, npol, nchan).
    """
    # default rowmap is EchoDictionary
    if rowmap is None:
        rowmap = utils.EchoDictionary()

    integrated_shape = (num_pol, num_chan)
    map_shape = (num_ra, num_dec, num_pol, num_chan)
    if integrated_data_storage is not None:
        assert integrated_data_storage.shape == integrated_shape
        assert integrated_data_storage.dtype == float
        integrated_data = integrated_data_storage
        integrated_data[:] = 0.0
    else:
        integrated_data = numpy.zeros((num_pol, num_chan), dtype=float)

    num_accumulated = numpy.zeros((num_pol, num_chan), dtype=int)

    if map_data_storage is not None:
        assert map_data_storage.shape == map_shape
        assert map_data_storage.dtype == float
        map_data = map_data_storage
        map_data[:] = display.NoDataThreshold
    else:
        map_data = numpy.zeros((num_ra, num_dec, num_pol, num_chan), dtype=float) + display.NoDataThreshold
    if map_mask_storage is not None:
        assert map_mask_storage.shape == map_shape
        assert map_mask_storage.dtype == bool
        map_mask = map_mask_storage
        map_mask[:] = False
    else:
        map_mask = numpy.zeros((num_ra, num_dec, num_pol, num_chan), dtype=bool)

    # column name for spectral data
    with casa_tools.TableReader(infile) as tb:
        colnames = ['CORRECTED_DATA', 'DATA', 'FLOAT_DATA']
        colname = None
        for name in colnames:
            if name in tb.colnames():
                colname = name
                break
        assert colname is not None

        for d in rowlist:
            ix = num_ra - 1 - d['RAID']
            iy = d['DECID']
            idxs = d['IDS']
            if len(idxs) > 0:
                # to access MS rows in sorted order (avoid jumping distant row, accessing back and forth)
                rows = dtrows[idxs].copy()
                sorted_index = numpy.argsort(rows)
                idxperpol = [[], [], [], []]
                for isort in sorted_index:
                    row = rows[isort]
                    mapped_row = rowmap[row]
                    LOG.debug('row %s: mapped_row %s', row, mapped_row)
                    this_data = tb.getcell(colname, mapped_row)
                    this_mask = tb.getcell('FLAG', mapped_row)
                    LOG.trace('this_mask.shape=%s', this_mask.shape)
                    for ipol in range(num_pol):
                        pmask = this_mask[ipol]
                        allflagged = numpy.all(pmask == True)
                        LOG.trace('all(this_mask==True) = %s', allflagged)
                        if allflagged == False:
                            idxperpol[ipol].append(idxs[isort])
                        else:
                            LOG.debug('spectrum for pol %s is completely flagged at %s, %s (row %s)',
                                      ipol, ix, iy, mapped_row)
                    binary_mask = numpy.asarray(numpy.logical_not(this_mask), dtype=int)
                    integrated_data += this_data.real * binary_mask
                    num_accumulated += binary_mask
                midxperpol = []
                for ipol in range(num_pol):
                    pidxs = idxperpol[ipol]
                    if len(pidxs) > 0:
                        midx = median_index(pidxs)
                        median_row = dtrows[pidxs[midx]]
                        mapped_row = rowmap[median_row]
                        LOG.debug('median row for (%s,%s) with pol %s is %s (mapped to %s)',
                                  ix, iy, ipol, median_row, mapped_row)
                        this_data = tb.getcell(colname, mapped_row)
                        this_mask = tb.getcell('FLAG', mapped_row)
                        map_data[ix, iy, ipol] = this_data[ipol].real
                        map_mask[ix, iy, ipol] = this_mask[ipol]
                        midxperpol.append(midx)
                    else:
                        midxperpol.append(None)
            else:
                LOG.debug('no data is available for (%s,%s)', ix, iy)
                midxperpol = [None for ipol in range(num_pol)]
            d['MEDIAN_INDEX'] = midxperpol
            LOG.debug('MEDIAN_INDEX for %s, %s is %s', ix, iy, midxperpol)
    integrated_data_masked = numpy.ma.masked_array(integrated_data, num_accumulated == 0)
    integrated_data_masked /= num_accumulated
    map_data_masked = numpy.ma.masked_array(map_data, map_mask)
    LOG.trace('integrated_data=%s', integrated_data)
    LOG.trace('num_accumulated=%s', num_accumulated)
    LOG.trace('map_data.shape=%s', map_data.shape)

    return integrated_data_masked, map_data_masked


def get_averaged_data(
    infile: str,
    dtrows: numpy.ndarray,
    num_ra: int,
    num_dec: int,
    num_chan: int,
    num_pol: int,
    rowlist: dict,
    rowmap: Optional[dict] = None,
    map_data_storage: Optional[numpy.ndarray] = None,
    map_mask_storage: Optional[numpy.ndarray] = None
) -> numpy.ma.masked_array:
    """Create array data for sparse map.

    Computes the spectra for sparse map averaged for each spatial
    position of the sparse map panel. Spatial grouping information is
    held by rowlist.

    Args:
        infile: Name of the MS
        dtrows: List of datatable rows
        num_ra: Number of panels along horizontal axis
        num_dec: Number of panels along vertical axis
        num_chan: Number of spectral channels
        num_pol: Number of polarizaionts
        rowlist: List of datatable row ids per sparse map panel with metadata
        rowmap: Row mapping between original (calibrated) MS and the MS
                specified by infile. Defaults to None.
        map_data_storage: Storage for sparse map. If None is given, new array is created.
        map_mask_storage: Storage for sparse map mask. If None is given, new array is created.

    Returns:
        Sparse map data as masked array. Shape of the array is four-dimensional,
        (nx, ny, npol, nchan).
    """
    # default rowmap is EchoDictionary
    if rowmap is None:
        rowmap = utils.EchoDictionary()

    map_shape = (num_ra, num_dec, num_pol, num_chan)

    num_accumulated = numpy.zeros((num_ra, num_dec, num_pol, num_chan), dtype=int)

    if map_data_storage is not None:
        assert map_data_storage.shape == map_shape
        assert map_data_storage.dtype == float
        map_data = map_data_storage
        map_data[:] = 0.0
    else:
        map_data = numpy.zeros((num_ra, num_dec, num_pol, num_chan), dtype=float)
    if map_mask_storage is not None:
        assert map_mask_storage.shape == map_shape
        assert map_mask_storage.dtype == bool
        map_mask = map_mask_storage
        map_mask[:] = False
    else:
        map_mask = numpy.zeros((num_ra, num_dec, num_pol, num_chan), dtype=bool)

    # column name for spectral data
    with casa_tools.TableReader(infile) as tb:
        colnames = ['CORRECTED_DATA', 'DATA', 'FLOAT_DATA']
        colname = None
        for name in colnames:
            if name in tb.colnames():
                colname = name
                break
        assert colname is not None

        for d in rowlist:
            ix = num_ra - 1 - d['RAID']
            iy = d['DECID']
            idxs = d['IDS']
            if len(idxs) > 0:
                # to access MS rows in sorted order (avoid jumping distant row, accessing back and forth)
                rows = dtrows[idxs].copy()
                sorted_index = numpy.argsort(rows)
#                 idxperpol = [[], [], [], []]
                for isort in sorted_index:
                    row = rows[isort]
                    mapped_row = rowmap[row]
                    LOG.debug('row %s: mapped_row %s', row, mapped_row)
                    this_data = tb.getcell(colname, mapped_row)
                    this_mask = tb.getcell('FLAG', mapped_row)
                    LOG.trace('this_mask.shape=%s', this_mask.shape)
                    binary_mask = numpy.asarray(numpy.logical_not(this_mask), dtype=int)
                    map_data[ix, iy] += this_data.real * binary_mask
                    num_accumulated[ix, iy] += binary_mask
            else:
                LOG.debug('no data is available for (%s,%s)', ix, iy)
    map_mask[:] = num_accumulated == 0
    map_data[map_mask] = display.NoDataThreshold
    map_data_masked = numpy.ma.masked_array(map_data, map_mask)
    map_data_masked /= num_accumulated
#     LOG.trace('integrated_data={}', integrated_data)
    LOG.trace('num_accumulated=%s', num_accumulated)
    LOG.trace('map_data.shape=%s', map_data.shape)

    return map_data_masked


def get_lines(
    datatable: 'DataTable',
    num_ra: int,
    num_pol: int,
    rowlist: List[dict]
) -> List[collections.defaultdict]:
    """Get detected line ranges per sparse map panel.

    Line information is taken from the datatable row specified
    by 'MEDIAN_INDEX' value of each item in rowlist.

    Args:
        datatable  Datatable instance
        num_ra: Number of panels along horizontal axis
        num_pol: Number of polarizations
        rowlist: List of datatable row indices per sparse map panel with metadata

    Returns:
        List of detected line ranges per panel
    """
    lines_map = [collections.defaultdict(dict)] * num_pol
    # with casa_tools.TableReader(rwtablename) as tb:
    for d in rowlist:
        ix = num_ra - 1 - d['RAID']
        iy = d['DECID']
        ids = d['IDS']
        midx = d['MEDIAN_INDEX']
        for ipol in range(len(midx)):
            if midx is not None:
                if midx[ipol] is not None:
                    masklist = datatable.getcell('MASKLIST', ids[midx[ipol]])
                    lines_map[ipol][ix][iy] = None if (len(masklist) == 0 or numpy.all(masklist == -1)) else masklist
                else:
                    lines_map[ipol][ix][iy] = None
            else:
                lines_map[ipol][ix][iy] = None
    return lines_map


def get_lines2(
    infile: str,
    datatable: 'DataTable',
    num_ra: int,
    rowlist: dict,
    polids: List[int],
    rowmap: Optional[dict] = None
) -> List[collections.defaultdict]:
    """Get detected line ranges per sparse map panel.

    get_lines2 performs the same operation with get_lines from
    the different input arguments.

    Args:
        infile: Name of MS before baseline subtraction
        datatable: Datatable instance
        num_ra: Number of panels along horizontal axis
        rowlist: List of datatable row ids per sparse map panel with metadata
        polids: List of polarization ids
        rowmap: Row mapping between original (calibrated) MS and the MS
                before baseline subtraction. It will be EchoDictionary if
                None is given.

    Returns:
        List of detected line ranges per panel
    """
    if rowmap is None:
        rowmap = utils.EchoDictionary()

    num_pol = len(polids)
    lines_map = [collections.defaultdict(dict)] * num_pol
#     plot_table = BaselineSubtractionPlotManager.generate_plot_meta_table(spwid,
#                                                                          polids,
#                                                                          grid_table)
#     num_rows = len(plot_table)  # num_plane * num_ra * num_dec
#     num_dec = plot_table[-1][1] + 1
#     num_ra = plot_table[-1][0] + 1
#     num_plane = num_rows / (num_dec * num_ra)
#     LOG.debug('num_ra={}, num_dec={}, num_plane={}, num_rows={}',
#               num_ra, num_dec, num_plane, num_rows)
    with casa_tools.TableReader(infile) as tb:
        for d in rowlist:
            ix = num_ra - 1 - d['RAID']
            iy = d['DECID']
            ids = d['IDS']
            ref_ra = d['RA']
            ref_dec = d['DEC']
            rep_ids = [-1 for i in range(num_pol)]
            min_distance = [1e30 for i in range(num_pol)]
            for dt_id in ids:
                row = rowmap[datatable.getcell('ROW', dt_id)]
                flag = tb.getcell('FLAG', row)
#                ra = datatable.getcell('RA', dt_id)
#                dec = datatable.getcell('DEC', dt_id)
#                ra = datatable.getcell('SHIFT_RA', dt_id)
#                dec = datatable.getcell('SHIFT_DEC', dt_id)
                ra = datatable.getcell('OFS_RA', dt_id)
                dec = datatable.getcell('OFS_DEC', dt_id)
                sqdist = (ra - ref_ra) * (ra - ref_ra) + (dec - ref_dec) * (dec - ref_dec)
                for ipol in range(num_pol):
                    if numpy.all(flag[ipol] == True):
                        #LOG.info('TN: ({}, {}) row {} pol {} is all flagged'.format(ix, iy, row, ipol))
                        continue

                    if sqdist <= min_distance[ipol]:
                        rep_ids[ipol] = dt_id

            #LOG.info('TN: rep_ids for ({}, {}) is {}'.format(ix, iy, rep_ids))
            for ipol in range(num_pol):
                if rep_ids[ipol] >= 0:
                    masklist = datatable.getcell('MASKLIST', rep_ids[ipol])
                    lines_map[ipol][ix][iy] = None if (len(masklist) == 0 or numpy.all(masklist == -1)) else masklist
                else:
                    lines_map[ipol][ix][iy] = None

    return lines_map


def median_index(arr: Iterable) -> 'Integral':
    """Return array index that corresponds to median value.

    Args:
        arr (): Array with type that implements comparison operator

    Returns:
        Index of median value. If arr is empty or not iterable,
        NaN is returned.
    """
    if not numpy.iterable(arr) or len(arr) == 0:
        return numpy.nan
    else:
        sorted_index = numpy.argsort(arr)
        if len(arr) < 3:
            return sorted_index[0]
        else:
            return sorted_index[len(arr) // 2]


def binned_mean_ma(x: List[float], masked_data: MaskedArray,
                   nbin: int) -> Tuple[numpy.ndarray, MaskedArray]:
    """
    Bin an array.

    Return an array of averaged values of masked_data in each bin.
    An element of binned_data is masked if any of elements in masked_data that
    contribute to the bin is masked.

    Args:
        x: Abcissa value of each element in masked_data.
        masked_data: Data to be binned. The length of array must be equal to that of x.
        nbin: Number of bins.
    Returns:
        Arrays of binned abcissa and binned data
    """
    ndata = len(masked_data)
    assert nbin < ndata
    assert len(x)==ndata
    bin_width = ndata/nbin # float
    # Prepare return values
    binned_data = numpy.ma.masked_array(numpy.zeros(nbin), mask=False)
    binned_x = numpy.zeros(nbin)
    min_i = 0
    for i in range(nbin):
        max_i = min(int(numpy.floor((i+1)*bin_width)), ndata-1)
        binned_x[i] = numpy.mean(x[min_i:max_i+1])
        if any(masked_data.mask[min_i:max_i+1]):
            binned_data.mask[i] = True
        else:
            binned_data[i] = numpy.nanmean(masked_data[min_i:max_i+1])
        min_i = max_i+1

    # mask NaN or Inf value
    binned_data.mask |= numpy.logical_not(numpy.isfinite(binned_data.data))

    return binned_x, binned_data
