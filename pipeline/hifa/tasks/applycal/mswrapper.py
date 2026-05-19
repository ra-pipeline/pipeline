import numpy as np
import pickle

import pipeline.infrastructure.logging as logging
from pipeline.infrastructure import casa_tools

LOG = logging.get_logger(__name__)


def average_visibility_dtype(npol,nchan,f_avg_max_length):
    dtype = [
        ('antenna', np.dtype('int32')),
        ('t_avg', np.dtype('complex128'), (npol, nchan)),
        ('t_sigma', np.dtype('complex128'), (npol, nchan)),
        ('f_avg', np.dtype('complex128'), (npol, f_avg_max_length)),
        ('f_sigma', np.dtype('complex128'), (npol, f_avg_max_length)),
        ('flagged',np.dtype('bool'))
    ]
    return dtype


class MSWrapper:
    """
    MSWrapper is a wrapper around a NumPy array populated with measurement set
    data for a specified scan and spectral window. The MSWrapper can be
    filtered on various criteria, e.g, spw, scan, antenna, etc., to narrow the
    data to a particular data selection.

    The static methods MSWrapper.create_averages_from_ms and
    MSWrapper.create_averages_from_combination can also be used to create a new
    instance of a MSWrapper object.
    """

    @staticmethod
    def create_averages_from_ms(filename, scan, spw, memlim, perantave=True):
        """
        Create a new MSWrapper for the specified scan and spw.

        Reading in raw measurement set data can be a very memory-intensive
        process, so data selection is deliberately limited to one scan and one
        spw at a time.

        :param filename: measurement set filename
        :param scan: integer scan ID
        :param spw: integer spw ID
        :param memlim: Limit for memory for data buffer use, given in Gigabytes
        :param perantave: Compute per antenna average (default True)
        :type perantave: bool
        :return: MSWrapper instance
        """
        # Method added as part of PIPE-687
        LOG.trace('MSWrapper.create_averages_from_ms(%r, %r, %r, %r, %r)',
                  filename, scan, spw, memlim, perantave)

        # Epsilon used to avoid division by zero in sigma calculations
        epsilon = 1.e-6

        # put memory limit in bytes
        memlim = int(memlim * (1024.0 ** 3))

        # Initialize necessary column name lists
        col_names = ['antenna1', 'antenna2', 'flag', 'time', 'corrected_data']
        # Data type for these columns
        col_dtypes = [
            np.dtype('int32'),
            np.dtype('int32'),
            np.dtype('bool'),
            np.dtype('float64'),
            np.dtype('complex128')
        ]
        # Data size per element for each column, in bytes
        col_dsizes = np.array([c.itemsize for c in col_dtypes], dtype='int32')
        # Is polarization a dimension of the column? 1=True, 0=False
        poldim = np.array([0, 0, 1, 0, 1], dtype='int32')
        # Is frequency a dimension of the column? 1=True, 0=False
        freqdim = np.array([0, 0, 1, 0, 1], dtype='int32')
        # Total size of the whole piece of data should be:
        # Size = nrows*Sum( dsizes*(npols*poldim+1)*(nchan*freqdim+1) )(over number of colnames)

        # commented out from copied PL code
        with casa_tools.MSReader(filename) as openms:

            # select data for this scan
            data_selection = {"scan": str(scan), "spw": str(spw)}
            openms.msselect(data_selection)
            md = openms.metadata()
            antennaids = md.antennaids()
            nant = len(antennaids)
            nbl = nant * (nant - 1) / 2 + nant
            nrows = openms.nrow(selected=True)
            ntstamps = nrows / nbl

            axis_info = openms.getdata(['axis_info'])
            # Create frequency axes to be introduced in output V
            corr_axis = axis_info['axis_info']['corr_axis']
            freq_axis = axis_info['axis_info']['freq_axis']

            npol = len(corr_axis)
            nchan = len(freq_axis['chan_freq'])

            # Data size per row and for the whole scan
            rowdatasize = np.sum(col_dsizes * (npol * poldim + 1) * (nchan * freqdim + 1))
            scandatasize = nrows * rowdatasize
            # Calculate the number of iteration that need to be done to go over
            # the entire piece of data for this scan,spw
            niter = int(np.ceil(1.0 * scandatasize / memlim))
            nrowsbuffer = int(np.floor(1.0 * memlim / rowdatasize))
            LOG.debug('Scan {0:d} has {1:d} rows ({2:.3f} Gb), memory limit is set to {3:.3f} Gb'.format(scan, nrows, 1.0*scandatasize/(1024.0**3), 1.0*memlim/(1024.0**3)))
            LOG.debug('reading data in {0:d} chunks of {1:d} rows'.format(niter, nrowsbuffer))

            norm_sigma_tavg = np.sqrt(ntstamps * (nant - 1.0))
            norm_sigma_favg = np.sqrt(nchan)

            #arrays to sum over so we can average later
            t_real_sum = {ant: np.ma.zeros((npol, nchan), dtype=np.dtype('float64')) for ant in antennaids}
            t_imag_sum = {ant: np.ma.zeros((npol, nchan), dtype=np.dtype('float64')) for ant in antennaids}
            t_real_sq_sum = {ant: np.ma.zeros((npol, nchan), dtype=np.dtype('float64')) for ant in antennaids}
            t_imag_sq_sum = {ant: np.ma.zeros((npol, nchan), dtype=np.dtype('float64')) for ant in antennaids}
            n_t_points = {ant: np.ma.zeros((npol, nchan), dtype=np.dtype('float64')) for ant in antennaids}

            f_avg = {ant: None for ant in antennaids}
            f_sigma = {ant: None for ant in antennaids}

            #Variable to store starting time
            tstart = 1.e12

            openms.iterinit(maxrows=nrowsbuffer)
            do_next = openms.iterorigin()

            while do_next:
                raw_data = openms.getdata(col_names)
                # Create maked array of corrected and masked data
                # data has axis order pol->channel->time. Swap order to a more natural time->pol->channel
                data = np.ma.MaskedArray(
                    data=raw_data['corrected_data'].swapaxes(0, 2).swapaxes(1, 2),
                    dtype=np.dtype('complex128'),
                    mask=raw_data['flag'].swapaxes(0, 2).swapaxes(1, 2)
                )
                tstart = min(tstart, np.min(raw_data['time']))
                # Iterate over antennas, selecting rows of data for averaging
                for antenna in antennaids:
                    sel = np.logical_xor(raw_data['antenna1'] == antenna, raw_data['antenna2'] == antenna)
                    seldatareal = data[sel].real
                    seldataimag = data[sel].imag
                    # If the per antenna adjustment is selected, invert the sign of the imaginary part when the
                    # antenna is in position 2
                    if perantave:
                        ant2sel = raw_data['antenna2'][sel]
                        sel2 = np.where(ant2sel == antenna)[0]
                        for j in sel2:
                            seldataimag[j, :, :] *= -1.0
                    # Accumulate the sum of data averaged over time and baselines (MS rows)
                    t_r_sum = seldatareal.sum(axis=0)
                    t_i_sum = seldataimag.sum(axis=0)
                    t_r_sq_sum = np.square(seldatareal).sum(axis=0)
                    t_i_sq_sum = np.square(seldataimag).sum(axis=0)

                    #No need to accumulate the sum of data averaged over frequency
                    f_r_avg = seldatareal.mean(axis=2)
                    f_i_avg = seldataimag.mean(axis=2)
                    f_ant_avg = (f_r_avg + 1j*f_i_avg).swapaxes(0,1)

                    f_r_sq_sum=np.square(np.ma.array([seldatareal[:,:,i]-f_r_avg for i in np.arange(seldatareal.shape[-1])])).sum(axis=0)
                    f_r_sigma = np.sqrt(f_r_sq_sum/nchan).swapaxes(0,1)

                    f_i_sq_sum=np.square(np.ma.array([seldataimag[:,:,i]-f_i_avg for i in np.arange(seldataimag.shape[-1])])).sum(axis=0)
                    f_i_sigma = np.sqrt(f_i_sq_sum/nchan).swapaxes(0,1)#(s,pol)->(pol,s)
                    f_ant_sigma = (f_r_sigma + 1j* f_i_sigma)/norm_sigma_favg

                    # Perform the the stacking to existing sums with np.ma.sum() to avoid
                    # propagating masking over the cumulative sum
                    t_real_sum[antenna] = np.ma.MaskedArray([t_real_sum[antenna], t_r_sum]).sum(axis=0)
                    t_imag_sum[antenna] = np.ma.MaskedArray([t_imag_sum[antenna], t_i_sum]).sum(axis=0)
                    t_real_sq_sum[antenna] = np.ma.MaskedArray([t_real_sq_sum[antenna], t_r_sq_sum]).sum(axis=0)
                    t_imag_sq_sum[antenna] = np.ma.MaskedArray([t_imag_sq_sum[antenna], t_i_sq_sum]).sum(axis=0)
                    # Perform the the stacking to existing sums with np.ma.sum() to avoid
                    # propagating masking over the cumulative sum
                    if f_avg[antenna] is not None:
                        f_avg[antenna] = np.ma.append(f_avg[antenna],f_ant_avg,axis=1)
                    else:
                        f_avg[antenna] = f_ant_avg
                    if f_sigma[antenna] is not None:
                        f_sigma[antenna] = np.ma.append(f_sigma[antenna],f_ant_sigma,axis=1)
                    else:
                        f_sigma[antenna] = f_ant_sigma
                    n_t_points[antenna] = np.ma.MaskedArray([n_t_points[antenna], data[sel].count(axis=0)]).sum(axis=0)
                # Jump to next chunk of data
                do_next = openms.iternext()

            # For pixels with no unmasked data accumulated, make sure those
            # pixels are filled with some epsilon dummy value
            #On the same iteration, get the maximum length of freq averages and use that length as masked array size
            f_avg_max_length = 0

            for antenna in antennaids:
                zeroselt = n_t_points[antenna].data < 1.0 #if no t_points were counted, antenna should be flagged.should it not be masked already?
                n_t_points[antenna].data[zeroselt] = epsilon
                n_t_points[antenna].mask += zeroselt

                f_avg_l = f_avg[antenna].shape[1]
                if f_avg_l>f_avg_max_length:
                    f_avg_max_length = f_avg_l

            # Iterate over antennas, now calculating the mean and sigma of the data
            # creating the variable V to be returned as output
            dtype = average_visibility_dtype(npol,nchan,f_avg_max_length)
            visibilities=np.ma.empty((0,), dtype=dtype)
            for antenna in antennaids:
                #compute avgs
                t_avg = (t_real_sum[antenna] + 1j*t_imag_sum[antenna]) / n_t_points[antenna]
                t_sigma_real = np.ma.sqrt((t_real_sq_sum[antenna] - np.square(t_real_sum[antenna]) / n_t_points[antenna]) / (n_t_points[antenna] - 1.0))
                t_sigma_imag = np.ma.sqrt((t_imag_sq_sum[antenna] - np.square(t_imag_sum[antenna]) / n_t_points[antenna]) / (n_t_points[antenna] - 1.0))
                # apply final formula from sigma values
                t_sigma = (t_sigma_real + 1j * t_sigma_imag) / norm_sigma_tavg

                v=np.ma.empty((1,), dtype=dtype)
                v['antenna'] = antenna
                v['t_avg'] = t_avg
                v['t_sigma'] = t_sigma
                v['f_avg'] = f_avg[antenna]
                v['f_sigma'] = f_sigma[antenna]
                v['flagged'] = n_t_points[antenna].mask.all() #flagg antenna if all points were flagged.
                visibilities = np.ma.concatenate((visibilities,v),axis=0)

        #Set up time axis
        int_axis = np.array([i for i in range(int(ntstamps)) for ant in range(nant-1)])
        time_axis = tstart + 1.0*int_axis

        return MSWrapper(filename, scan, spw, None, corr_axis, freq_axis, int_axis, time_axis, V=visibilities)

    @staticmethod
    def create_averages_from_combination(mswlist,antennaids):
        """
        Calculate and return the average MSWrapper of the list of MSWrapper objects given as input.
        The 'sigma' column get filled with the standard error of the mean, by adding inverse squared variances
        of each of the objects in the list.

        :mswlist: Python List of MSWrapper objects to combine. All of them must be from the same
                  dataset and SPW, otherwise a dummy object is returned.
        :return: MSWrapper object
        """
        # Get data from first MSWrapper element of the list, scan will be the list of scans
        # discard raw data if present
        nscans = len(mswlist)
        scan = [mswlist[idxscan].scan for idxscan in range(nscans)]
        filename = mswlist[0].filename
        spw = mswlist[0].spw
        corr_axis = mswlist[0].corr_axis
        freq_axis = mswlist[0].freq_axis
        int_axis = mswlist[0].int_axis
        time_axis = mswlist[0].time_axis
        nant = len(antennaids)
        npol = len(corr_axis)
        nchan = len(freq_axis['chan_freq'])

        f_avg_max_length = mswlist[0].V['f_avg'].shape[2]

        dtype = average_visibility_dtype(npol,nchan,f_avg_max_length)
        visibilities=np.ma.empty((0,), dtype=dtype)

        # Average data
        for ant in range(nant):
            t_data = [mswlist[idxscan].V['t_avg'][ant, :, :] for idxscan in range(nscans)]
            t_mean = np.ma.mean(t_data, axis=0)
            t_invsigmasqreal = [1.0 / (mswlist[idxscan].V['t_sigma'][ant, :, :].real ** 2) for idxscan in range(nscans)]
            t_invsigmasqimag = [1.0 / (mswlist[idxscan].V['t_sigma'][ant, :, :].imag ** 2) for idxscan in range(nscans)]
            t_sigmameanreal = 1.0 / np.ma.sqrt(np.ma.sum(t_invsigmasqreal, axis=0))
            t_sigmameanimag = 1.0 / np.ma.sqrt(np.ma.sum(t_invsigmasqimag, axis=0))
            t_sigma = t_sigmameanreal + 1.j * t_sigmameanimag

            flags = [mswlist[idxscan].V['flagged'][ant] for idxscan in range(nscans)]

            dtype = average_visibility_dtype(npol,nchan,f_avg_max_length)

            v=np.ma.empty((1,), dtype=dtype)
            v['antenna'] = ant
            v['t_avg'] = t_mean
            v['t_sigma'] = t_sigma
            v['f_avg'] = None #f_mean
            v['f_sigma'] = None #f_sigma
            v['flagged'] = all(flags) #check this
            visibilities = np.ma.concatenate((visibilities,v),axis=0)

        return MSWrapper(filename, scan, spw, None, corr_axis, freq_axis,
                         int_axis, time_axis, V=visibilities)

    def __init__(self, filename, scan=None, spw=None, data=None, corr_axis=None, freq_axis=None,
                 int_axis=None, time_axis=None, V=None):
        """
        Create a new MSWrapper for the specified ms, scan and spw.
        :param filename: measurement set filename
        :param scan: integer scan ID
        :param spw: integer spw ID
        :param data: averaged visibilities in case they already exist
        :return: MSWrapper instance
        """
        self.filename = filename
        self.scan = scan
        self.spw = spw
        self.data = data
        self.corr_axis = corr_axis
        self.freq_axis = freq_axis
        self.int_axis = int_axis
        self.time_axis = time_axis
        self.V = V

    def __getitem__(self, key):
        return self.data[key]

    def __contains__(self, key):
        return key in self.data.dtype.names

    def __len__(self):
        return len(self.data)

    def __iter__(self):
        return (i for i in self.data)

    def save(self, filename):
        """
        Save averaged visibilities into a pickle file.
        :param filename: file where visibilities will be stored
        """

        if self.V is not None or self.data is not None:
            with open(filename, 'wb') as pklfile:
                LOG.info(f'Saving MSWrapper data arrays to {self.filename}')
                pickle.dump((self.filename,self.scan,self.spw,self.data,self.corr_axis,self.freq_axis,self.int_axis,self.time_axis,self.V), pklfile, protocol=2)
        else:
            LOG.info(f"Nothing to save for {self.filename}")

    def load(self,filename):
        """
        load averaged visibilities into an MSWrapper object
        :param filename: file where visibilities are stored
        """
        with open(filename, 'rb') as f:
            (self.filename,self.scan,self.spw,self.data,self.corr_axis,self.freq_axis,self.int_axis,self.time_axis,self.V)=pickle.load(f)
        LOG.info(f'MSWrapper data arrays loaded from {filename}')
