import os, sys
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.ndimage import convolve1d
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import minimize_scalar
from astropy import units as u
from casatools import msmetadata as msmdtool
from casatools import table as tbtool
import colorsys

#Useful function for fully flattening array
flattenlist = lambda l: [item for sublist in l for item in sublist]

def genColorList(N, purity = 0.75, brightness = 0.75):
    '''Generate list of distictive colors for plotting, return RGB value tuples.'''
    HSV_tuples = [(idx*1.0/N, purity, brightness) for idx in range(N)]
    RGB_tuples = list(map(lambda x: colorsys.hsv_to_rgb(*x), HSV_tuples))
    return RGB_tuples

def createCasaTool(mytool):
    """
    A wrapper to handle the changing ways in which casa tools are invoked.
    For CASA < 6, it relies on "from taskinit import *" in the preamble above.
    mytool: a tool name, like tbtool
    Todd Hunter
    """
    if 'casac' in locals():
        if (type(casac.Quantity) != type):  # casa 4.x and 5.x
            myt = mytool()
        else:  # casa 3.x
            myt = mytool.create()
    else:
        # this is CASA 6
        myt = mytool()
    return(myt)

def segmentEdges(seq, gap, label, sortdata = True):
    '''Return edges of sequence of values with gaps
    Assumes 1D array "seq" is ordered. Otherwise one should sort it first.
    seq: Sequence of values to search gaps in.
    gap: Gap size to consider.
    label: Label to put in the numpy array returned.
    sortdata: Whether to sort data in the seq vector.
    '''

    if sortdata:
        seq = np.sort(seq)
    n = len(seq)
    diff = seq[1:] - seq[0:n-1]
    if np.any(diff < 0):
        print('Array is not sorted, use sortdata = True')
        return None
    isgap = (diff > gap)
    if np.sum(isgap) > 0:
        startseg = seq[np.append([True],isgap)]
        endseg = seq[np.append(isgap,[True])]
        output = np.array([(startseg[i], endseg[i], label) for i in range(len(startseg))], np.dtype([('tstart',np.float64),('tend',np.float64),('intent',np.str_,40)]))
    else:
        output = np.array([(seq[0], seq[-1], label)], np.dtype([('tstart',np.float64),('tend',np.float64),('intent',np.str_,40)]))

    return output

def segment_edges_optimized(seq):
    '''Optimized return edges for mask arrays'''
    n = len(seq)
    if n < 2:
        return np.array([(seq[0] if n == 1 else np.nan, seq[-1] if n == 1 else np.nan)],
                        dtype=[('tstart', np.float64), ('tend', np.float64)])

    is_gap = (np.diff(seq) > 2)
    gap_indices = np.where(is_gap)[0]

    if not gap_indices.size:
        return np.array([(seq[0], seq[-1])], dtype=[('tstart', np.float64), ('tend', np.float64)])

    starts = np.concatenate(([seq[0]], seq[gap_indices + 1]))
    ends = np.concatenate((seq[gap_indices], [seq[-1]]))
    return np.array(list(zip(starts, ends)), dtype=[('tstart', np.float64), ('tend', np.float64)])

def selectRanges(timeseq, rangetable):
    '''Return selection boolean array for a time sequence, given a table of time ranges.
    '''
    nranges = len(rangetable)
    ndata = len(timeseq)
    sel = np.zeros(ndata, dtype=bool)
    for i in range(nranges):
        sel += np.all([timeseq >= rangetable['tstart'][i], timeseq <= rangetable['tend'][i]], axis=0)
    return sel

def range2str(sel):
    '''Return a string representing the list of channels ranges in a boolean selection vector.
    '''
    rangetbl = segmentEdges(np.arange(len(sel))[sel], 1.1, 'sciline')
    if len(rangetbl) > 0:
        return ';'.join(['{0:d}~{1:d}'.format(int(s['tstart']),int(s['tend'])) for s in rangetbl])
    else:
        return ''

def sci_line_sel_2str(data_stats_comb: dict) -> str:
    '''Return a string representation of channels with science line detections.
    '''
    outputstr = ''
    for fieldname in data_stats_comb['comb_metadata']['fieldnames']:
        outputstr += fieldname + '='
        spwstr = []
        for spwname in data_stats_comb['comb_metadata']['spwnamelist']:
            scilinesel = data_stats_comb[fieldname][spwname]['sci_line_sel']
            if np.sum(scilinesel) > 0:
                spwstr.append(spwname+':'+range2str(scilinesel))
        outputstr += ','.join(spwstr)
        outputstr += '\n'
    return outputstr

def abs_rfft_wmask(data, minsectionsize = 20, full_freqfft=None, mask_sections=None):
    '''Function used estimate the amplitude of the FFT of a 1D dataset having uniform sampling
    but masked sections. Algorithm will calculate the absolute value of the FFT in each section,
    and return the addition of each of the results of the individual sections.
    param:
        data: Data given in the form of a 1D MaskedArray.
        minsectionsize: Minimum size of the section to be considered.
    '''
    n = len(data)

    if full_freqfft is None:
        full_freqfft = np.fft.rfftfreq(n)

    masked_count = np.sum(data.mask)

    if masked_count > n - minsectionsize:
        return np.zeros_like(full_freqfft), None
    elif masked_count == 0:
        return np.abs(np.fft.rfft(data.data)), None

    unmasked_indices = np.where(~data.mask)[0]
    if not unmasked_indices.size:
        return np.zeros_like(full_freqfft)

    if mask_sections is None:
        mask_sections = segment_edges_optimized(unmasked_indices)

    absfft_list = []

    for section in mask_sections:
        start, end = int(section['tstart']), int(section['tend'])
        n_section = end - start
        if n_section >= minsectionsize:
            segment = data.data[start:end]
            absfft = np.abs(np.fft.rfft(segment))
            freqfft = np.fft.rfftfreq(n_section)
            resamp_absfft = np.interp(full_freqfft, freqfft, absfft)
            absfft_list.append(resamp_absfft)

    if not absfft_list:
        return np.zeros_like(full_freqfft), None

    sumabsfft = np.sum(np.array(absfft_list), axis=0)
    return sumabsfft, mask_sections

#Copied over from analysisUtils
def getSpwList(msmd, intent='OBSERVE_TARGET#ON_SOURCE',tdm=True,fdm=True, sqld=False):
    spws = msmd.spwsforintent(intent)
    almaspws = msmd.almaspws(tdm=tdm,fdm=fdm,sqld=sqld)
    scienceSpws = np.intersect1d(spws,almaspws)
    return(list(scienceSpws))

#Copied over from analysisUtils
def onlineChannelAveraging(msmd, spws=None):
    """
    For Cycle 3-onward data, determines the channel averaging factor from
    the ratio of the effective channel bandwidth to the channel width.
    spw: a single value, or a list; if Nonne, then uses science spws
    Returns: single value for a single spw, or a list for a list of spws
    -Todd Hunter
    """
    hanning_effBw = {1: 2.667, 2: 3.200, 4: 4.923, 8: 8.828, 16: 16.787}
    if spws is None:
        spws = getSpwList(msmd)
    if type(spws) != list:
        spws = [spws]
    Ns = list(hanning_effBw.keys())
    ratios = [hanning_effBw[i]/i for i in Ns]
    Nvalues = []
    for spw in spws:
        chanwidths = msmd.chanwidths(spw)
        nchan = len(chanwidths)
        if (nchan < 5):
            return 1
        chanwidth = abs(chanwidths[0])
        chaneffwidth = msmd.chaneffbws(spw)[0]
        ratio = chaneffwidth/chanwidth
        Nvalues.append(Ns[np.argmin(abs(ratios - ratio))])
    if (len(spws) == 1):
        return Nvalues[0]
    else:
        return Nvalues

#Obtain spectral setup
def getSpecSetup(myms: str, spwlist: list = [], intentlist: list = ['*OBSERVE_TARGET#ON_SOURCE*', '*OBSERVE_TARGET#OFF_SOURCE*', '*CALIBRATE_ATMOSPHERE#OFF_SOURCE*']):
    '''Task to gather spectral setup information.
    myms: MS to be processed.
    spwlist: List of SPW to be included in queries, if left empty, all science SPWs
    will be considered.
    intentlist: List of intents to be included in the queries. By default is *OBSERVE_TARGET*.
    '''

    #Else read in the information from the MS
    #if spwlist is empty, get all science SPWs
    msmd = createCasaTool(msmdtool)
    msmd.open(myms)
    if len(spwlist) == 0:
        spwlist = getSpwList(msmd)
    spwsetup = {}
    spwsetup['spwlist'] = spwlist
    spwsetup['intentlist'] = intentlist
    spwsetup['namesfor'] = msmd.fieldsforsources(asnames=True)
    spwsetup['scan'] = {}
    spwsetup['fieldname'] = {}
    spwsetup['fieldid'] = {}
    for intent in intentlist:
        spwsetup['scan'][intent] = list(msmd.scansforintent(intent))
        spwsetup['fieldname'][intent] = list(msmd.fieldsforintent(intent,asnames=True))
        spwsetup['fieldid'][intent] = list(msmd.fieldsforintent(intent,asnames=False))
    spwsetup['scifieldidoff'] = {}
    spwsetup['scansforfield'] = {}
    for fieldid in spwsetup['fieldid']['*OBSERVE_TARGET#ON_SOURCE*']:
        fieldname = spwsetup['namesfor'][str(fieldid)][0]
        listfieldnameoff = [item[0] for item in spwsetup['namesfor'].values() if (fieldname in item[0]) and ('OFF' in item[0])]
        if len(listfieldnameoff) == 1:
            fieldidoff = [i for i in spwsetup['namesfor'].keys() if listfieldnameoff[0] == spwsetup['namesfor'][i]][0]
            spwsetup['scifieldidoff'][str(fieldid)] = fieldidoff
        else:
            spwsetup['scifieldidoff'][str(fieldid)] = ''
        allscansforfield = list(msmd.scansforfield(field=int(fieldid)))
        spwsetup['scansforfield'][str(fieldid)] = [item for item in allscansforfield if item not in spwsetup['scan']['*CALIBRATE_ATMOSPHERE#OFF_SOURCE*']]
    allscans = list(set(flattenlist([spwsetup['scan'][intent] for intent in intentlist])))
    spwsetup['allscans'] = allscans
    spwsetup['scantimes'] = {}
    for scan in spwsetup['allscans']:
        scantimestamps = msmd.timesforscans(scan)
        spwsetup['scantimes'][scan] = [np.min(scantimestamps), np.max(scantimestamps)]
    spwsetup['intent'] = {}
    for scan in allscans:
        spwsetup['intent'][scan] = [intent for intent in spwsetup['intentlist'] if scan in spwsetup['scan'][intent]]
    spwsetup['antids'] = msmd.antennasforscan(scan = spwsetup['scan'][intentlist[0]][0])
    spwsetup['antnames'] = np.array(msmd.antennanames(spwsetup['antids']))
    spwsetup['spwnames'] = np.array(msmd.namesforspws(spwlist))
    spwsetup['fdmspws'] = msmd.fdmspws()
    spwsetup['tdmspws'] = msmd.tdmspws()

    nchanperbb = [0, 0, 0, 0]

    for spwid in spwlist:
        spwsetup[spwid] = {}
        #Get SPW information: frequencies of each channel, etc.
        chanfreqs = msmd.chanfreqs(spw=spwid)
        nchan = len(chanfreqs)
        fcenter = (chanfreqs[int(nchan/2-1)]+chanfreqs[int(nchan/2)])/2.
        chansep = (chanfreqs[-1]-chanfreqs[0])/(nchan-1)
        spwsetup[spwid]['chanfreqs'] = chanfreqs
        spwsetup[spwid]['nchan'] = nchan
        spwsetup[spwid]['fcenter'] = fcenter
        spwsetup[spwid]['chansep'] = chansep
        spwsetup[spwid]['Nave'] = onlineChannelAveraging(msmd, spwid)
        #Get data descriptor for each SPW
        spwsetup[spwid]['ddi'] = msmd.datadescids(spw=spwid)[0]
        spwsetup[spwid]['npol'] = msmd.ncorrforpol(msmd.polidfordatadesc(spwsetup[spwid]['ddi']))
        #Get baseband for each SPW
        try:
            spwsetup[spwid]['BB'] = int(msmd.baseband(spwid))
            spwsetup[spwid]['BBname'] = 'BB_'+str(spwsetup[spwid]['BB'])
        except Exception:
            spwsetup[spwid]['BB'] = 0
            spwsetup[spwid]['BBname'] = 'BB_0'
        spwsetup[spwid]['istdm'] = (spwid in spwsetup['tdmspws'])
        spwsetup[spwid]['nchan_high'] = nchan*5
        spwsetup[spwid]['chansep_high'] = chansep/5.
        spwsetup[spwid]['chanfreqs_high']  = chanfreqs[0] + (chansep/5.)*np.arange(nchan*5)
        spwsetup[spwid]['fcenter_high'] = (spwsetup[spwid]['chanfreqs_high'][int(nchan/2-1)]+spwsetup[spwid]['chanfreqs_high'][int(nchan/2)])/2.
        nchanperbb[spwsetup[spwid]['BB'] - 1] += spwsetup[spwid]['nchan']

    spwsetup['nchanperbb'] = nchanperbb
    for spwid in spwlist:
        spwsetup[spwid]['istdm2'] = (nchanperbb[spwsetup[spwid]['BB'] - 1] in [128, 256])
        spwsetup[spwid]['dosmooth'] = (nchanperbb[spwsetup[spwid]['BB'] - 1]*spwsetup[spwid]['npol'] in [256, 8192])
        if spwsetup[spwid]['dosmooth']:
            print('Spw %d in BB_%d (total Nchan within BB is %d, sp avg likely not applied).  dosmooth=True' % (spwid, spwsetup[spwid]['BB'], nchanperbb[spwsetup[spwid]['BB'] - 1]*spwsetup[spwid]['npol']))
        else:
            print('Spw %d in BB_%d (total Nchan within BB is %d, sp avg likely applied).  dosmooth=False' % (spwid, spwsetup[spwid]['BB'], nchanperbb[spwsetup[spwid]['BB'] - 1]*spwsetup[spwid]['npol']))

    msmd.close()

    #Get science goal information
    scigoaldata = getScienceGoalData(myms)
    if 'sensitivityGoal' in scigoaldata:
        spwsetup['sensitivityGoalinJy'] = u.Unit(scigoaldata['sensitivityGoal']).to(u.Jy)
    else:
        spwsetup['sensitivityGoalinJy'] = None

    if 'representativeFrequency' in scigoaldata:
        spwsetup['representativeFrequencyinHz'] = u.Unit(scigoaldata['representativeFrequency']).to(u.Hz)
        reprdist = [np.abs(spwsetup[s]['fcenter']-spwsetup['representativeFrequencyinHz']) for s in spwsetup['spwlist']]
        spwsetup['representativeSPW'] = spwsetup['spwlist'][np.argsort(reprdist)[0]]
    else:
        spwsetup['representativeFrequencyinHz'] = None
        spwsetup['representativeSPW'] = spwsetup['spwlist'][0]

    if 'representativeBandwidth' in scigoaldata:
        spwsetup['representativeBandwidthinHz'] = u.Unit(scigoaldata['representativeBandwidth']).to(u.Hz)
    else:
        spwsetup['representativeBandwidthinHz'] = None

    return spwsetup

def getCalAtmData(ms: str, spws: list, spwsetup: dict, antenna: str = ''):
    '''Funtion to extract Tsys, Trec, Tatm and tau data from the ASDM's CALATMOSPHERE table.
    param:
        ms: MS filename
        spws: List of SPWs to load
        spwsetup: Dictionary of metadata obtained from getSpecSetup()
        antenna: String of Antenna name, if only one antenna is desired. If '' is given, results
        for all antennas will be returned.
    '''
    #Check if CALATMOSPHERE table is therem if not, return None
    if not os.path.exists(os.path.join(ms, 'ASDM_CALATMOSPHERE')):
        print('Error: Could not find ASDM_CALATMOSPHERE table!')
        return None

    tb = createCasaTool(tbtool)
    #Open CALATMOSPHERE table
    tb.open(os.path.join(ms, 'ASDM_CALATMOSPHERE'))
    #Get weather parameters
    tground_all = tb.getcol('groundTemperature')
    pground_all = tb.getcol('groundPressure')
    hground_all = tb.getcol('groundRelHumidity')
    #Get the spectra of the ATM measurements
    tmatm_all = {}
    tsys = {}
    trec = {}
    tatm = {}
    tau = {}
    antatm = {}
    for spwid in spws:
        minfreq = np.min(spwsetup[spwid]['chanfreqs'])
        maxfreq = np.max(spwsetup[spwid]['chanfreqs'])
        midfreq = 0.5*(minfreq+maxfreq)
        samebbspw = [s for s in spwsetup['spwlist'] if spwsetup[s]['BBname'] == spwsetup[spwid]['BBname']]

        #Create query string
        if (len(antenna) > 0) and (antenna in spwsetup['antnames']):
            tbselstr = 'basebandName=="{0:s}" && syscalType=="TEMPERATURE_SCALE" && antennaName=="{1:s}"'.format(str(spwsetup[spwid]['BBname']), antenna)
        else:
            tbselstr = 'basebandName=="{0:s}" && syscalType=="TEMPERATURE_SCALE"'.format(str(spwsetup[spwid]['BBname']))

        subtb = tb.query(tbselstr)
        tmatm_all[spwid] = np.unique(subtb.getcol('startValidTime'))
        #Get frequency vector and find section belonging to this SPW
        fullfreq = subtb.getcell('frequencySpectrum', 0)
        sectionmid = []
        freqsection = []
        chansec = []
        chanidx = 0
        for s in samebbspw:
            chansec.append([chanidx,chanidx+spwsetup[s]['nchan']])
            section = fullfreq[chanidx:chanidx+spwsetup[s]['nchan']]
            chanidx += spwsetup[s]['nchan']
            sectionmid.append(np.mean(section))
            freqsection.append(section)
        thissection = np.argsort(np.abs(np.array(sectionmid) - midfreq))[0]
        freq = freqsection[thissection]
        order = np.argsort(freq)
        startchan = chansec[thissection][0]
        endchan = chansec[thissection][1]
        #Load Tsys and Trx tables
        auxtsys = [subtb.getcell('tSysSpectrum', i) for i in range(subtb.nrows())]
        auxtrec = [subtb.getcell('tRecSpectrum', i) for i in range(subtb.nrows())]
        auxtatm = [subtb.getcell('tAtmSpectrum', i) for i in range(subtb.nrows())]
        # (npols, nchantsys, nrowstsys) = np.shape(auxtsys)
        npols = auxtsys[0].shape[0]
        nrowstsys = len(auxtsys)
        tsys[spwid] = np.zeros((npols, spwsetup[spwid]['nchan'], nrowstsys))
        trec[spwid] = np.zeros((npols, spwsetup[spwid]['nchan'], nrowstsys))
        tatm[spwid] = np.zeros((npols, spwsetup[spwid]['nchan'], nrowstsys))
        #Resample the curves to match the frequency of the data SPWs
        for pol in range(npols):
            for row in range(nrowstsys):
                tsysfit = CubicSpline(freq[order], auxtsys[row][pol][startchan:endchan][order], bc_type='not-a-knot')
                trecfit = CubicSpline(freq[order], auxtrec[row][pol][startchan:endchan][order], bc_type='not-a-knot')
                tatmfit = CubicSpline(freq[order], auxtatm[row][pol][startchan:endchan][order], bc_type='not-a-knot')
                tsys[spwid][pol,:,row] = tsysfit(spwsetup[spwid]['chanfreqs'])
                trec[spwid][pol,:,row] = trecfit(spwsetup[spwid]['chanfreqs'])
                tatm[spwid][pol,:,row] = tatmfit(spwsetup[spwid]['chanfreqs'])
        antatm[spwid] = subtb.getcol('antennaName')
        #To get the skyline list, pick index of first antenna, first entry of tau, for the first polarization
        #Resample according to the same procedure used for Tsys and Trx
        auxtau = subtb.getcell('tauSpectrum', 0)[0]
        taufit = CubicSpline(freq[order], auxtau[startchan:endchan][order], bc_type='not-a-knot')
        tau[spwid] = taufit(spwsetup[spwid]['chanfreqs'])
    tb.close()

    return (tground_all, pground_all, hground_all, tmatm_all, tsys, trec, tatm, tau, antatm)

def getScienceGoalData(ms: str):
    '''Function used to obtain Science Goal data from the SB Summary table
    param:
        ms: String with MS filename
    '''

    scigoaldata = {}
    asdm_sbsummary = os.path.join(ms, 'ASDM_SBSUMMARY')

    if not os.path.exists(asdm_sbsummary):
        return scigoaldata

    tb = createCasaTool(tbtool)
    #Open ASDM_SBSUMMARY table
    tb.open(asdm_sbsummary)
    scigoaltable = tb.getcol('scienceGoal')
    for line in scigoaltable.flatten():
        items = line.split('=')
        item = items[0].replace(' ','')
        value = items[1].replace(' ','')
        scigoaldata[item] = value
    tb.close()

    return scigoaldata

def robuststats(A):
    '''Return median and estimate standard deviation
    of numpy array A using median statistics.
    '''
    #correction factor for obtaining sigma from MAD
    madfactor = 1.482602218505602
    n = len(A)
    #Fitting parameters for sample size correction factor b(n)
    alpha = 1.32
    beta = -1.5 if (n % 2 == 0) else -0.9
    bn = 1.0 - 1.0 / (alpha * n + beta)
    mu = np.ma.median(A)
    sigma = (1.0 / bn) * madfactor * np.ma.median(np.ma.abs(A - mu))
    return (mu, sigma)

def nearestFinite(A, i):
    '''Function used to search for the nearest unmasked, finite datapoint left and right
    from a given position inside an array, where left means a lower index in the
    array, and right a higher index.

    Parameters:
    A: Numpy Masked array containing the data in question.
    i: The index reference point from which to search for unmasked and finite data.
    '''

    n = len(A)
    left = np.nan
    right = np.nan
    #Search left
    if i >= 1:
        for k in range(1, i+1):
            if (not np.ma.is_masked(A[i-k])) and (np.isfinite(A[i-k])):
                left = i - k
                break
    else:
        left = 0

    if np.isnan(left):
        left = i

    #Search right
    if i <= n - 2:
        for k in range(1, n-i):
            if (not np.ma.is_masked(A[i+k])) and (np.isfinite(A[i+k])):
                right = i + k
                break
    else:
        right = n - 1

    if np.isnan(right):
        right = i

    return (left, right)

def enlargesel(sel, box):
    '''Enlarge selection by "box" pixels around each selected pixel
    in "sel" vector.
    '''
    n = len(sel)
    newsel = np.zeros(n, dtype=bool)
    for i in range(n):
        startrange = max(0, i - box)
        endrange = min(n - 1, i + box + 1)
        newsel[i] = np.ma.max(sel[startrange:endrange])

    return newsel

def smooth(y: np.ma.core.MaskedArray, box_pts: int):
    '''Smooth using boxcar convolution including masking, if it is a MaskedArray object.
    param:
        y: Data to be smoothed.
        box_pts: Size of the boxcar smoothing kernel (int).
    '''
    if not isinstance(y, np.ma.MaskedArray):
        ymasked = np.ma.MaskedArray(y, mask=np.zeros_like(y, dtype=bool))
    else:
        ymasked = y.copy()

    if box_pts < 2:
        # Smoothing with kernel size < 2 has no effect,
        # or is invalid.
        return ymasked

    mask = ymasked.mask
    data = ymasked.filled(0)

    kernel = np.ones(box_pts) / box_pts
    smoothed_data = convolve1d(data, kernel, mode='reflect')
    if np.sum(mask) > 0:
        smoothed_mask = convolve1d(1.0*mask, kernel, mode='reflect')
        smoothed_mask = (smoothed_mask > 0.0)
    else:
        smoothed_mask = mask

    smoothed_masked = np.ma.MaskedArray(smoothed_data, mask=smoothed_mask)

    return smoothed_masked

def smooth_gauss(y: np.ma.core.MaskedArray, box_pts: float, box_sigma_ratio = 3.55):
    '''Smooth using gaussian convolution including masking, if it is a MaskedArray object.
    param:
        y: Data to be smoothed.
        box_pts: Size of the smoothing kernel, float value.
        box_sigma_ratio: Ratio between box_pts and gaussian sigma.
    '''
    if not isinstance(y, np.ma.MaskedArray):
        ymasked = np.ma.MaskedArray(y, mask=np.zeros_like(y, dtype=bool))
    else:
        ymasked = y.copy()

    mask = ymasked.mask
    data = ymasked.filled(0)

    smoothed_data = gaussian_filter1d(data, box_pts/box_sigma_ratio)
    if np.sum(mask) > 0:
        smoothed_mask = gaussian_filter1d(1.0*mask, box_pts/box_sigma_ratio)
        smoothed_mask = (smoothed_mask > 0.0)
    else:
        smoothed_mask = mask

    smoothed_masked = np.ma.MaskedArray(smoothed_data, mask=smoothed_mask)

    return smoothed_masked

def smoothed_sigma_clip(data: np.ma.MaskedArray, threshold: float, max_smooth_frac: float = 0.1,
                             smooth_box_sigma: int = 20, mode: str = 'two-sided', fixedwidth = None) -> dict:
    '''Perform sigma-clipping selection of outlier datapoints in a 1-D dataset, after applying a boxcar smoothing of varying
    amount to the data. The amount of smoothing is selected by the maximizing the peak of the outliers. Then the resulting
    boolean selection vector of outlier, the coordinate (channel), the SNR, the data value of the maximum outlier and the
    smoothing width used to maximize SNR are given as output in a dictionary. Additionally the normalization sigma (stdev of data)
    used to estimate the number of standard deviations, and the normalized version of the data used for outlier selection is also returned.
    param:
        data: (numpy array) Data to be tested for outliers.
        threshold: (float) Threshold used for sigma-clipping of outliers
        max_smooth_frac: (float) Maximum size of smoothing box to use, given as a fraction of the total number of channels.
        smooth_box_sigma: (int) Smoothing box size used to subtract large scale trends and obtain a channel-to-channel standard deviation value,
                                used for data normalization into number of sigmas.
        mode: (str) Either 'two-sided' for positive and negative sigma-clipping, or 'one-sided' for only positive sigma-clipping.
        fixedwidth: (float) Return result without maximizing SNR but rather a fixed value of smoothing width.
    returns:
        Dictionary, with keys:
        chanmax:  Channel number of the maximum outlier.
        snrmax: SNR of the maximum outlier.
        outliers: Numpy boolean array for selection of outliers.
        widthmax: Smoothing width that maximizes SNR of maximum outlier.
        smsigma: Channel-to-channel standard deviation
        datamax: Data value of the maximum outlier.
        widths: List of boxcar smoothing widths used.
        normdata: Normalized data used for outlier detection, in units of number of sigmas.
    '''

    nchan = len(data)
    maxsmbox = int(max_smooth_frac * nchan)
    smboxstep = max(1, int(maxsmbox / 40.0))
    # Obtain estimate of pixel-to-pixel RMS, without baseline structure
    mudata, _ = robuststats(data)
    smdata_baseline = smooth(data, smooth_box_sigma)
    _, smsigma = robuststats(data - smdata_baseline)
    if fixedwidth is None:
        if mode == 'two-sided':
            def min_neg_snr(w):
                smy = smooth_gauss(data, w)
                snr = (smy - mudata)/(smsigma/np.sqrt(w))
                return np.ma.min(-np.abs(snr))
        elif mode == 'one-sided':
            def min_neg_snr(w):
                smy = smooth_gauss(data, w)
                snr = (smy - mudata)/(smsigma/np.sqrt(w))
                return np.ma.min(-snr)
        #Find best w that maximizes SNR
        wfit = minimize_scalar(min_neg_snr, bounds=(1.0, maxsmbox), method='bounded')
        widthmax = wfit.x
    else:
        widthmax = fixedwidth
    smdata = smooth_gauss(data, widthmax)
    normdata = (smdata - mudata)/(smsigma/np.sqrt(widthmax))
    snrmax = np.ma.max(normdata)
    if mode == 'two-sided':
        thresdata = np.ma.abs(normdata)
    elif mode == 'one-sided':
        thresdata = normdata
    outliers = (thresdata > threshold)
    chanmax = np.argmax(thresdata)
    datamax = data[chanmax]

    return {'chanmax': chanmax, 'snrmax': snrmax, 'outliers': outliers, 'widthmax': widthmax, 'smsigma': smsigma,
            'datamax': datamax, 'widths': [widthmax], 'normdata': normdata}


def getAtmDataForSPW(fname: str, spw_setup: dict, spw: int, antenna: str, smooth_trec_factor: float = 0.01,
                    nchan_flagged_border: int = 5):
    ''' Wrapper task to getCalAtmData(), organizes data per single SPW, and creates MaskedArray objects, for convenience
    in further calculations. Additionally, adds flagged border to avoid issues in the border of Tsys tables.
    param:
        fname: (str) Filename of MS dataset
        spw_setup: (dict) SpwSetup dictionary obtained from sd_qa_utils.getSpecSetup()
        spw: (int) Spectral window ID
        antenna: (str) Antenna name
        smooth_trec_factor: (float) Smothing factor for Trec table, as a fraction of SPW bandwidth
        nchan_flagged_border: (int) Number of channels to flag in the border of Tsys, Trec, etc. SPWs.
    '''

    #Get CalATM table data
    calatmtables = getCalAtmData(fname, [spw], spw_setup, antenna = antenna)
    if calatmtables is None:
        print('Error: Could not find ASDM_CALATMOSPHERE table!')
        return None
    (tground_all, pground_all, hground_all, tmatm_all, rawtsys, rawtrec, rawtatm, tau, antatm) = calatmtables

    #Initialize variables
    npol = spw_setup[spw]['npol']
    nchan = spw_setup[spw]['nchan']
    scanlist = spw_setup['scan']['*OBSERVE_TARGET#ON_SOURCE*']
    nscans = len(scanlist)
    tsys_scanlist = spw_setup['scan']['*CALIBRATE_ATMOSPHERE#OFF_SOURCE*']
    ntsysscans = len(tsys_scanlist)

    #Find out if there is some missing scan, if so, fill in with masked data
    atmtimes = np.unique(tmatm_all[spw])
    start_times = np.array([spw_setup['scantimes'][i][0] for i in tsys_scanlist])
    timediff = [np.min(np.abs(time-atmtimes)) for time in start_times]
    if len(start_times) > 1:
        delta_atmtimes = np.min(np.diff(start_times))
        isclose = (timediff/delta_atmtimes < 0.5)
    else:
        isclose = np.array([False] * len(timediff))
    idx = np.intp(np.cumsum(1.0*isclose) - 1.0)
    tsys = np.ma.MaskedArray(np.zeros((npol, nchan, ntsysscans)), mask=np.zeros((npol, nchan, ntsysscans)))
    trec = np.ma.MaskedArray(np.zeros((npol, nchan, ntsysscans)), mask=np.zeros((npol, nchan, ntsysscans)))
    tatm = np.ma.MaskedArray(np.zeros((npol, nchan, ntsysscans)), mask=np.zeros((npol, nchan, ntsysscans)))
    for pol in range(npol):
        for i, scan in enumerate(tsys_scanlist):
            if isclose[i]:
                tsys[pol,:,i] = rawtsys[spw][pol,:,idx[i]]
                trec[pol,:,i] = rawtrec[spw][pol,:,idx[i]]
                tatm[pol,:,i] = rawtatm[spw][pol,:,idx[i]]
                if nchan_flagged_border > 0:
                    tsys.mask[pol,0:nchan_flagged_border,i] = True
                    tsys.mask[pol,nchan-nchan_flagged_border:nchan,i] = True
                    trec.mask[pol,0:nchan_flagged_border,i] = True
                    trec.mask[pol,nchan-nchan_flagged_border:nchan,i] = True
                    tatm.mask[pol,0:nchan_flagged_border,i] = True
                    tatm.mask[pol,nchan-nchan_flagged_border:nchan,i] = True
            else:
                tsys.mask[pol,:,i] = np.ones(nchan, dtype=bool)
                trec.mask[pol,:,i] = np.ones(nchan, dtype=bool)
                tatm.mask[pol,:,i] = np.ones(nchan, dtype=bool)
    #Create smoothed version of Trec
    smtrec = np.zeros_like(trec)
    for pol in range(npol):
        for i, scan in enumerate(tsys_scanlist):
            kernel_size = int(smooth_trec_factor * spw_setup[spw]['nchan'])
            if kernel_size < 2:
                # No smoothing
                smtrec[pol, :, i] = trec[pol, :, i]
            else:
                smtrec[pol, :, i] = smooth(trec[pol, :, i], kernel_size)
    #Get indices for Tsys scan before and after each science scan
    idx_tsys_scan_low = {}
    idx_tsys_scan_high = {}
    for scan in scanlist:
        #Get closest tsys scan before science scan
        idx_closest_before = np.where(np.array(tsys_scanlist) < scan)[0]
        if len(idx_closest_before) > 0:
            idx_tsys_scan_low[scan] = idx_closest_before[-1]
        else:
            idx_tsys_scan_low[scan] = -1
        #Get closest tsys scan after science scan
        idx_closest_after = np.where(np.array(tsys_scanlist) > scan)[0]
        if len(idx_closest_after) > 0:
            idx_tsys_scan_high[scan] = idx_closest_after[0]
        else:
            idx_tsys_scan_high[scan] = -1

    return {'tground_all': tground_all, 'pground_all': pground_all, 'hground_all': hground_all,
            'atmtimes': atmtimes, 'tsys': tsys, 'trec': trec, 'tatm': tatm,
            'tau': tau[spw], 'smtrec': smtrec, 'idx_tsys_scan_low': idx_tsys_scan_low, 'idx_tsys_scan_high': idx_tsys_scan_high}

def sigclipfit(x, A, Asig, fitdeg, nclips, nsigma, bordertokeep = 0.05, progdegree = False, smoothselbox = 0.05):
    '''Return polynomial model parameters done to vector A and residuals from the fit.
    x: x coordinate
    A: Data set vector.
    Asig: Data sigma vector. Should include variance due to skylines and science target emission.
    fitdeg: Fitting polynomial degree.
    nclips: Number of sigma clipping iterations.
    nsigma: Number of sigmas in sigma clipping iterations. Positive float or two-value tuple.
    bordertokeep: Fraction of channels to keep in the borders
    progdegree: Whether to increase polynomial fit progressively in each iteration.
    smoothselbox: Enlarge each outlier detection with a box of this size (as fraction of SPW).
    '''
    if type(nsigma) == float:
        nsigmahigh = nsigma
        nsigmalow = nsigma
    elif ((type(nsigma) == tuple) or (type(nsigma) == list)) and (len(nsigma) == 2):
        nsigmahigh = nsigma[1]
        nsigmalow = nsigma[0]
    output = {}
    gooddata = np.ma.MaskedArray(np.ones(len(A)), mask=A.mask)
    #Start data selection with all good data
    sel = gooddata
    minx = np.ma.min(x)
    maxx = np.ma.max(x)
    bordermin = minx + bordertokeep*(maxx - minx)
    bordermax = maxx - bordertokeep*(maxx - minx)
    #Set border selection, avoiding any bad data
    border = np.ma.MaskedArray(np.ma.all([np.ma.any([x < bordermin, x > bordermax], axis=0), gooddata], axis=0), mask=A.mask)
    if progdegree:
        degree = 0
    else:
        degree = fitdeg
    if smoothselbox > 0.0:
        box = max(2, int(smoothselbox*len(A)))
    else:
        box = 1
    while (degree <= fitdeg):
        for i in range(nclips):
            #Include constant border, if demanded
            thissel = np.ma.any([sel, border], axis=0)
            #If everything is flagged, continue with a default selection of everything
            if np.sum(~A.mask[thissel]) <= fitdeg:
                thissel = np.ma.any([gooddata, border], axis=0)
            try:
                coefs = np.polyfit(x[thissel], A[thissel], fitdeg, w=1/Asig[thissel])
            except:
                coefs = [0.0 for i in range(degree+1)]
                print('No data!!!\nx='+str(x[thissel])+'\nA='+str(A[thissel])+'\nAsig='+str(Asig[thissel]))
            model = np.ma.sum([coefs[i]*(x**(degree-i)) for i in range(degree+1)], axis=0)
            diff = A - model
            (mu, sigma) = robuststats(diff)
            #Select pixels to use in the next iteration from pixels within nsigma of mean
            #including only non-masked data, but not in the border.
            sel = np.ma.all([((diff - mu)/sigma >= -nsigmalow), ((diff - mu)/sigma <= nsigmahigh), gooddata], axis=0)
            #If boxcar smoothing of selection is chosen (smoothselbox > 0), broadening non-selected pixels
            if box > 1:
                sel = np.ma.logical_not(enlargesel(np.ma.logical_not(sel), box))
        degree += 1
    output['coefs'] = coefs
    output['residuals'] = diff
    output['sel'] = sel
    output['border'] = border
    return output

def getskylines(tauspec, spw, spwsetup, fraclevel = 0.5, minpeaklevel = 0.0, spwbordertoavoid = 0.025, taudeg = 2):
    '''Get position of sky lines and line widths from the optical depth.
    fraclevel: fraction of the maximum of the optical depth to look for.
    If fraclevel=0.5 (default), the width results will be the HWHM.
    minpeaklevel: Minimum relative opacity at a given peak (relative to median opacity)
    to consider a line. Lines smaller than this level are ignored. (default 0.05)
    spwbordertoavoid: Fractional border of the SPW to avoid for peak detection.
    Default is 0.025 (2.5% of SPW BW)
    '''
    nch = len(tauspec)
    borderpix = int(max(1.0,np.round(nch*spwbordertoavoid)))
    noborder = np.ones(nch, dtype=bool)
    noborder[0:borderpix] = False
    noborder[nch-borderpix:nch] = False
    mintau = np.min(tauspec)
    mediantau = np.median(tauspec)
    tauzeroD = np.array(np.ediff1d(1.0*(np.ediff1d(tauspec) > 0.0), to_begin=0, to_end=0), dtype=bool)
    taunegDD = np.array(np.ediff1d(np.ediff1d(tauspec), to_begin=0, to_end=0) < 0.0, dtype=bool)
    taugtminlevel = (tauspec/mediantau >= (1.0 + minpeaklevel))
    taupeak = np.all([tauzeroD, taunegDD, taugtminlevel, noborder], axis=0)
    tauvalley = np.all([tauzeroD, ~taunegDD], axis=0)
    idxpeak = np.arange(nch, dtype=int)[taupeak]
    idxvalley = np.arange(nch, dtype=int)[tauvalley]
    npeak = len(idxpeak)
    peaktau = tauspec[idxpeak]
    output = {'nch': nch, 'npeak': npeak, 'taumin': mintau, 'fraclevel': fraclevel, 'valley': idxvalley, 'peaksinfo': {}}
    hwhmleft = np.zeros(npeak)
    hwhmright = np.zeros(npeak)
    widthratio = np.zeros(npeak)
    #Fit "baseline" to tau
    nu = spwsetup[spw]['chanfreqs']/1.e09
    taufit = sigclipfit(nu, np.ma.MaskedArray(tauspec, mask=np.zeros(nch)),
                        np.ma.MaskedArray(np.sqrt(tauspec), mask=np.zeros(nch)), 2, 3, 5.0)
    taubline = np.ma.sum([taufit['coefs'][deg]*(nu**(taudeg-deg)) for deg in range(taudeg + 1)], axis = 0)
    subtau = tauspec - taubline
    output['taufit'] = taufit
    for k, idx in enumerate(idxpeak):
        #calculate the decrease from the tau depth relative to the minimum tau in the SPW
        #peakratioleft = np.array([(tauspec[idx - i]-mintau)/(peaktau[k]-mintau) for i in range(idx)])
        #peakratioright = np.array([(tauspec[idx + i]-mintau)/(peaktau[k]-mintau) for i in range(nch-idx)])
        peakratioleft = np.array([subtau[idx - i]/subtau[idx] for i in range(idx)])
        peakratioright = np.array([subtau[idx + i]/subtau[idx] for i in range(nch-idx)])
        posrightneg = peakratioright < fraclevel
        if np.sum(posrightneg) > 0:
            hwhmright[k] = np.where(posrightneg)[0][0]
        else:
            #search of peak to the right of this peak, select the border if none
            if k < npeak-1:
                hwhmright[k] = 0.5*(idxpeak[k+1] - idx)
            else:
                hwhmright[k] = nch - idx - 1
        posleftneg = peakratioleft < fraclevel
        if np.sum(posleftneg) > 0:
            hwhmleft[k] = np.where(posleftneg)[0][0]
        else:
            #search of peak to the left of this peak, select the border if none
            if k > 0:
                hwhmleft[k] = 0.5*(idx - idxpeak[k-1])
            else:
                hwhmleft[k] = idx

    #If the range of the skylines goes beyond a valley, shrink range around line using those valleys
    for k in range(npeak):
        valleypointsleft = np.sort([point for point in idxvalley if (point < idxpeak[k])])
        if (len(valleypointsleft) > 0) and (idxpeak[k]-hwhmleft[k] < valleypointsleft[-1]):
            hwhmleft[k] = idxpeak[k] - valleypointsleft[-1]
        valleypointsright = np.sort([point for point in idxvalley if (point > idxpeak[k])])
        if (len(valleypointsright) > 0) and (idxpeak[k]+hwhmright[k] > valleypointsright[0]):
            hwhmright[k] = valleypointsright[0] - idxpeak[k]

    #Check if there is more than one peak and if so check if ranges overlap and correct in that case
    if npeak > 1:
        for k in range(npeak - 1):
            if (idxpeak[k]+hwhmright[k] > idxpeak[k+1]-hwhmleft[k+1]):
                #If there is an valley point detected between the peaks, choose that one.
                #If not, just pick the middle point between peaks
                valleypoints = [point for point in idxvalley if (point > idxpeak[k]) and (point < idxpeak[k+1])]
                if len(valleypoints) > 0:
                    hwhmright[k] = valleypoints[0]-idxpeak[k]
                    hwhmleft[k+1] = idxpeak[k+1]-valleypoints[0]
                else:
                    hwhmright[k] = 0.5*(idxpeak[k+1]-idxpeak[k])
                    hwhmleft[k+1] = 0.5*(idxpeak[k+1]-idxpeak[k])

    #Create output dictionary
    for k, idx in enumerate(idxpeak):
        output['peaksinfo'][k] = {}
        output['peaksinfo'][k]['peakpos'] = int(idx)
        output['peaksinfo'][k]['taupeak'] = tauspec[idx]
        output['peaksinfo'][k]['hwhmleft'] = int(hwhmleft[k])
        output['peaksinfo'][k]['hwhmright'] = int(hwhmright[k])
        output['peaksinfo'][k]['minrange'] = int(idx - hwhmleft[k])
        output['peaksinfo'][k]['maxrange'] = int(idx + hwhmright[k])
    return output

def skysel(skylines, linestouse = 'all', avoidpeak = 0.0):
    '''Create selection array from dictionary of skylines list.
    avoidpeak: Parameter to avoid a range around the line peak as fraction of FWHM
    '''
    skysel = np.zeros(skylines['nch'], dtype=bool)
    if linestouse == 'all':
        linestouse = range(skylines['npeak'])
    for i in linestouse:
        skysel[skylines['peaksinfo'][i]['minrange']:skylines['peaksinfo'][i]['maxrange']+1] = 1
        if avoidpeak > 0.0:
            startrange = max(0, skylines['peaksinfo'][i]['peakpos']-int(avoidpeak*skylines['peaksinfo'][i]['hwhmleft']))
            endrange = min(skylines['peaksinfo'][i]['peakpos']+int(avoidpeak*skylines['peaksinfo'][i]['hwhmright']), skylines['nch'])
            skysel[startrange:endrange] = 0

    return skysel

def get_skysel_from_msw(msw, fraclevel = 0.5, minpeaklevel = 0.05):

    (tground_all, pground_all, hground_all, tmatm_all, tsys, trec, tatm, tau, antatm) = getCalAtmData(msw.fname, [msw.spw], msw.spw_setup, antenna = str(msw.antenna))
    skylines = getskylines(tau[msw.spw], msw.spw, msw.spw_setup, fraclevel = fraclevel, minpeaklevel = minpeaklevel)
    skylinesel = skysel(skylines)

    return skylinesel
