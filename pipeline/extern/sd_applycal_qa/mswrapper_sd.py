import os, sys
import numpy as np
import copy
import casatools
from scipy import signal

from . import sd_qa_utils


class MSWrapperSD(object):
    """
    MSWrapper is a wrapper around a NumPy array populated with measurement set
    data for a specified scan and spectral window of Single Dish dataset.

    The static method MSWrapperSD.create_from_ms should be used to instantiate
    MSWrapper objects.
    """

    def __init__(self, fname=None, antenna=None, spw=None, npol=None, nchan=None, nrows=None,
        fieldid=None, column='CORRECTED_DATA', onoffsel='ON', spw_setup=None,
        data=None, weight=None, time=None, outliers=None, outlierfreq=None, outliertime=None,
        tsysdata=None, scantimesel=None, nrowscan=None, time_mean_scan=None, time_std_scan=None,
        data_stats=None, analysis=None):
        """
        Create a new MSWrapperSD object for the specified ms, antenna, etc.
        :param fname: measurement set filename
        :param antenna: string antenna name
        :param spw: integer spw ID
        :param fieldid: integer field ID
        :param column: string data column to use DATA/FLOAT_DATA/CORRECTED_DATA
        :param onoffsel: string select target data either in on-source, off-source or both: ON/OFF/BOTH
        :param spw_setup: SpwSetup dictionary obtained from SDcalatmcorr.getSpecSetup()
        :param data: NumPy MaskedArray containing the data to store
        :param weight: NumPy MaskedArray containing the weight of data to store
        :param time: NumPy MaskedArray containing the time array of the data
        :return: MSWrapperSD instance
        """
        self.fname = fname
        self.antenna = antenna
        self.spw = spw
        self.npol = npol
        self.nchan = nchan
        self.nrows = nrows
        self.fieldid = fieldid
        self.column = column
        self.onoffsel = onoffsel
        self.spw_setup = spw_setup
        self.data = data
        self.weight = weight
        self.time = time
        self.outliers = outliers
        self.outlierfreq = outlierfreq
        self.outliertime = outliertime
        self.tsysdata = tsysdata
        self.scantimesel = scantimesel
        self.nrowscan = nrowscan
        self.time_mean_scan = time_mean_scan
        self.time_std_scan = time_std_scan
        self.data_stats = data_stats
        self.analysis = analysis


    @staticmethod
    def create_from_ms(fname=None, antenna=None, spw=None, fieldid=None, spw_setup=None, column='CORRECTED_DATA', onoffsel='BOTH', attach_tsys_data=True):
        """
        Create a new MSWrapperSD for the specified data from the MS.

        :param fname: measurement set filename
        :param antenna: string antenna name
        :param spw: integer spw ID
        :param fieldid: integer field ID
        :param column: string data column to use DATA/FLOAT_DATA/CORRECTED_DATA
        :param onoffsel: string select target data either in on-source, off-source or both: ON/OFF/BOTH
        :param spw_setup: SpwSetup dictionary obtained from sd_qa_utils.getSpecSetup()
        :return: MSWrapper instance
        """

        if fname is None:
            print('Missing parameter fname! Exiting...')
            return None
        if antenna is None:
            print('Missing parameter antenna! Exiting...')
            return None
        if spw is None:
            print('Missing parameter spw! Exiting...')
            return None
        if fieldid is None:
            print('Missing parameter fieldid! Exiting...')
            return None
        if spw_setup is None:
            print('Missing parameter spw_setup! Exiting...')
            return None

        msmd = casatools.msmetadata()
        ms = casatools.ms()
        tb = casatools.table()
        #Select ON or OFF data
        if onoffsel == 'ON':
            tb.open(fname + '/STATE')
            tb_on = tb.query('OBS_MODE ~ m/^OBSERVE_TARGET#ON_SOURCE/')
            state_ids = tb_on.rownumbers().tolist()
            tb_on.close()
            tb.close()
        elif onoffsel == 'OFF':
            tb.open(fname + '/STATE')
            tb_off = tb.query('OBS_MODE ~ m/^OBSERVE_TARGET#OFF_SOURCE/')
            state_ids = tb_off.rownumbers().tolist()
            tb_off.close()
            tb.close()
        elif onoffsel == 'BOTH':
            state_ids = []
        else:
            print('Could not understand parameter onoffsel='+onoffsel+' Must be ON|OFF|BOTH! Exiting...')
            return None

        #Get field ID
        if (fieldid is None) and (len(spw_setup['fieldid']['*OBSERVE_TARGET#ON_SOURCE*']) == 1):
            fieldid = spw_setup['fieldid']['*OBSERVE_TARGET#ON_SOURCE*'][0]

        #Get columns
        tb.open(fname, nomodify=True)
        mscolnames = tb.colnames()

        #Select data column
        if (column == 'CORRECTED_DATA') and ('CORRECTED_DATA' in mscolnames):
            datacol = "CORRECTED_DATA"
        elif (column == 'CORRECTED_DATA') and ('CORRECTED_DATA' not in mscolnames) and ('DATA' in mscolnames):
            print('No data in "CORRECTED DATA", using fallback "DATA" column')
            datacol = "DATA"
        elif (column == 'CORRECTED_DATA') and ('CORRECTED_DATA' not in mscolnames) and ('FLOAT_DATA' in mscolnames):
            print('No data in "CORRECTED DATA", using fallback "FLOAT_DATA" column')
            datacol = "FLOAT_DATA"
        elif ((column == 'FLOAT_DATA') or (column == 'DATA')) and ('DATA' in mscolnames):
            datacol = "DATA"
        elif ((column == 'FLOAT_DATA') or (column == 'DATA')) and ('FLOAT_DATA' in mscolnames):
            datacol = "FLOAT_DATA"
        print('Using "'+datacol+'" column')

        #Get ID of selected antenna
        if (antenna in spw_setup['antnames']):
            antenna_id = spw_setup['antids'][spw_setup['antnames'] == antenna][0]
        else:
            print('Cannot find antenna: '+str(antenna))
            return None

        if attach_tsys_data:
            tsysdata = sd_qa_utils.getAtmDataForSPW(fname, spw_setup, spw, antenna)
        else:
            tsysdata = None

        #Open MS and read DATA/CORRECTED column
        querystr = 'DATA_DESC_ID == {0:s} && FIELD_ID == {1:s} && ANTENNA1 == {2:s}'.format(str(spw_setup[spw]['ddi']), str(fieldid), str(antenna_id))
        querystr += ' && NOT FLAG_ROW'
        if len(state_ids) > 0:
            querystr += f'  && STATE_ID IN {state_ids}'
        print('Reading data for TaQL query: '+querystr)
        subtb = tb.query(querystr)
        tmdata = subtb.getcol('TIME')
        data = subtb.getcol(datacol).real
        flag = subtb.getcol('FLAG')
        weight = subtb.getcol('WEIGHT')
        subtb.close()
        tb.close()

        #If all data is flagged, return dummy object
        if np.shape(data) == (0,):
            npol = spw_setup[spw]['npol']
            nchan = spw_setup[spw]['nchan']
            return MSWrapperSD(fname=fname, antenna=antenna, spw=spw, npol=npol, nchan=nchan, nrows=0, fieldid=fieldid, column=column, onoffsel=onoffsel, spw_setup=spw_setup, data=None, weight=None, time=None, tsysdata=tsysdata, scantimesel=None, nrowscan=None, time_mean_scan=None, time_std_scan=None, data_stats=None, analysis=None)

        (npol, nchan, nrows) = np.shape(data)
        #Create masked data numpy array for ease of use
        data = np.ma.masked_array(data, mask=flag, fill_value=0.0)

        scanlist = spw_setup['scansforfield'][str(fieldid)]
        nscans = len(scanlist)
        scantimesel = {}
        nrowscan = {}
        time_mean_scan = {}
        time_std_scan = {}
        for scan in scanlist:
            scantimesel[scan] = (tmdata >= spw_setup['scantimes'][scan][0]) & (tmdata < spw_setup['scantimes'][scan][1])
            nrowscan[scan] = np.sum(scantimesel[scan])
            time_mean_scan[scan] = np.ma.mean(data[:,:,scantimesel[scan]], axis=2)
            time_std_scan[scan] = np.ma.std(data[:,:,scantimesel[scan]], axis=2)
        #Compute average for all data
        time_mean_scan['all'] = np.ma.mean(data, axis=2)
        time_std_scan['all'] = np.ma.std(data, axis=2)

        return MSWrapperSD(fname=fname, antenna=antenna, spw=spw, npol=npol, nchan=nchan, nrows=nrows, fieldid=fieldid, column=column, onoffsel=onoffsel, spw_setup=spw_setup, data=data, weight=weight, time=tmdata, tsysdata=tsysdata, scantimesel=scantimesel, nrowscan=nrowscan, time_mean_scan=time_mean_scan, time_std_scan=time_std_scan, data_stats=None,
            analysis=None)

    def average_data_per_scan(self):
        ''' Method to average data per scan and all data, and update per-scan and all scan average arrays.
        '''

        #If no data is contained in this object, just return
        if self.nrows == 0:
            return

        scanlist = self.spw_setup['scansforfield'][str(self.fieldid)]
        self.time_mean_scan = {}
        self.time_std_scan = {}

        #Compute averages per scan
        for scan in scanlist:
            self.time_mean_scan[scan] = np.ma.mean(self.data[:,:,self.scantimesel[scan]], axis=2)
            self.time_std_scan[scan] = np.ma.std(self.data[:,:,self.scantimesel[scan]], axis=2)

        #Compute average for all data
        self.time_mean_scan['all'] = np.ma.mean(self.data, axis=2)
        self.time_std_scan['all'] = np.ma.std(self.data, axis=2)

        return

    def filter(self, type: str = 'rowmedian', returnfit: bool = False, polydeg: int = 2, filter_order: int = 5,
              filter_cutoff: float = 0.01):
        '''Task to apply filters to the data.
        param
            msw: MSWrapperSD object, containing the data to be filtered.
            type: String telling the type of filter to apply. Options are:
                  rowmedian: Subtract the median value of each row (integration) of the data.
                  chanmedian: Subtract the median value of each channel of the data.
                  rowlinearfit: Fit and subtract the a linear fit per row (integration) of the data.
                  rowpolyfit: Fit and subtract the a polynomial fit per row (integration) of the data.
                  chanpolyfit: Fit and subtract the a polynomial fit per channel (integration) of the data.
                  chanhighpass: Pass the data through a highpass filter for each channel.
                  chanautocorr: Calculate the autocorrelation of the data in each channel.
            returnfit: Boolean, whether to return the result of the fit subtracted to the data.
            polydeg: Degree of the polynomial fitted.
            filter_order, filter_cutoff: parameters to be used with signal.butter highpass filter.
        :return: MSWrapperSD instance (optional a tuple of a (MSWrapperSD, dict), where the dictionary
                 contains the fitted data.
        '''

        #If no data is contained in this object, just return
        if self.nrows == 0:
            return

        (npol, nchan, nrows) = np.shape(self.data)
        (npoltsys, nchantsys, nscanstsys) = np.shape(self.tsysdata['tsys'])
        freqs = self.spw_setup[self.spw]['chanfreqs']*(1.e-09)
        newdata = copy.deepcopy(self.data)
        #Fitted data to return
        fitdata = {}

        #Apply filters
        if type == 'rowmedian':
            rowmedian = np.ma.median(self.data, axis=1)
            fitdata['rowmedian'] = rowmedian
            for pol in range(npol):
                for row in range(nrows):
                    newdata[pol,:,row] = self.data[pol,:,row] - rowmedian[pol,row]
        elif type == 'chanmedian':
            chanmedian = np.ma.median(self.data, axis=2)
            fitdata['chanmedian'] = chanmedian
            for pol in range(npol):
                for ch in range(nchan):
                    newdata[pol,ch,:] = self.data[pol,ch,:] - chanmedian[pol,ch]
        elif type == 'rowlinearfit':
            linearfit = {}
            for pol in range(npol):
                linearfit[pol] = {}
                for row in range(nrows):
                    linearfit[pol][row] = np.polyfit(freqs, self.data[pol,:,row], 1)
                    fiteval = freqs*linearfit[pol][row][0] + linearfit[pol][row][1]
                    newdata[pol,:,row] = self.data[pol,:,row] - fiteval
            fitdata['rowlinearfit'] = linearfit
        elif type == 'rowpolyfit':
            polyfit = {}
            for pol in range(npol):
                polyfit[pol] = {}
                for row in range(nrows):
                    polyfit[pol][row] = np.polyfit(freqs, self.data[pol,:,row], polydeg)
                    fiteval = np.ma.sum([polyfit[pol][row][k]*(freqs**(polydeg - k)) for k in range(polydeg+1)], axis=0)
                    newdata[pol,:,row] = self.data[pol,:,row] - fiteval
            fitdata['rowpolyfit'] = polyfit
        elif type == 'chanpolyfit':
            polyfit = {}
            xr = np.arange(nrows)
            for pol in range(npol):
                polyfit[pol] = {}
                for ch in range(self.nchan):
                    polyfit[pol][ch] = np.polyfit(xr, self.data[pol,ch,:], polydeg)
                    fiteval = np.ma.sum([polyfit[pol][ch][k]*(xr**(polydeg - k)) for k in range(polydeg+1)], axis=0)
                    newdata[pol,ch,:] = self.data[pol,ch,:] - fiteval
            fitdata['chanpolyfit'] = polyfit
        elif type == 'chanhighpass':
            b, a = signal.butter(filter_order, filter_cutoff/0.5, btype='high', analog=False)
            for pol in range(npol):
                for ch in range(self.nchan):
                    newdata[pol,ch,:] = signal.filtfilt(b, a, self.data[pol,ch,:])
            newdata.mask = self.data.mask
        elif type == 'chanautocorr':
            xr = np.arange(nrows)
            for pol in range(npol):
                for ch in range(self.nchan):
                    newdata[pol,ch,:] = signal.correlate(self.data[pol,ch,:], self.data[pol,ch,:], mode='same')
            newdata.mask = self.data.mask

        #Update data
        self.data = newdata
        #Update per-scan averages
        self.average_data_per_scan()

        if returnfit:
            return fitdata

        return
