import casatools
import numpy as np
import os
import pickle
import datetime
import glob
from astropy.coordinates import EarthLocation, AltAz, CartesianRepresentation, ICRS, SkyCoord
import astropy.units as u
from astropy.time import Time
import colorsys

#This file contains functions that were borrowed from AnalysisUtils
#the very few functions we are actually using were moved here

#List of SSO objects
SSOfieldnames = ['Ceres', 'Pallas', 'Vesta', 'Venus', 'Mars', 'Jupiter', 'Uranus', 'Neptune', 'Ganymede', 'Titan', 'Callisto', 'Juno', 'Europa']

def genColorList(N, purity = 0.75, brightness = 0.75, rndseed = None):
    '''Generate list of distictive colors for plotting, return RGB value tuples.'''
    if rndseed is not None:
        np.random.seed(rndseed)
    rng = np.random.default_rng()
    HSV_tuples = [(idx*1.0/N, purity, brightness) for idx in range(N)]
    raw_RGB_tuples = list(map(lambda x: colorsys.hsv_to_rgb(*x), HSV_tuples))
    RGB_tuples = rng.permutation(raw_RGB_tuples)
    return RGB_tuples

def getSpwList(msmd,intent='OBSERVE_TARGET#ON_SOURCE',tdm=True,fdm=True, sqld=False):
    '''Function to obtain the list of science SPWs. From aU.
    '''
    spws = msmd.spwsforintent(intent)
    almaspws = msmd.almaspws(tdm=tdm,fdm=fdm,sqld=sqld)
    scienceSpws = np.intersect1d(spws,almaspws)
    return(list(scienceSpws))

def project_vectors_to_sky_direction(vectors, sky_direction, time, location = 'Atacama Large Millimeter Array'):
    '''Funtion to project array antenna positions towards a direction in the sky.
    
    Parameters:
    vectors: List of array position vectors, given as a list of 3D tuples/lists, in meters.
    location: Location of observatory, could be string with the site location, or
              a tuple of (long[deg], lat[deg], alt[m]). If none given, use ALMA
    sky_direction: Coordinates of projection onto the sky, can be an astropy SkyCoord object
                   or a tuple of float value in degrees in ICRS: (ra[deg], dec[deg])
    time: Epoch of observation, can be a float, which is understood as a time in MJD,
          or can be an astropy Time object.
    output: List of 2D projected vectors.
    '''

    vecshape = np.shape(vectors)
    if (len(vecshape) != 2) or (vecshape[1] != 3):
        print('Please give vectors as a list of (X,Y,Z) tuples of 3D vectors! Exiting...')
        return None

    # Convert sky_direction to a SkyCoord object
    if ((type(sky_direction) == list) or (type(sky_direction) == tuple)) and (len(sky_direction) == 2):
        sky_coord = SkyCoord(ra=sky_direction[0] * u.deg, dec=sky_direction[1] * u.deg, frame='icrs')
    elif type(sky_direction) == SkyCoord:
        sky_coord = sky_direction
    else:
        print('Cannot understand sky_direction='+str(sky_direction)+'! Exiting...')
        return None

    # Define the Earth location
    if type(location) == str:
        earth_location = EarthLocation.of_site(location)
    elif ((type(location) == tuple) or (type(location) == list)) and (len(location) == 3):
        earth_location = EarthLocation(lon=location[0] * u.deg, lat=location[1] * u.deg, height=location[2] * u.m)
    else:
        print('Did not understand location='+str(location)+', exiting...')
        return None

    # Create an AltAz frame at the given location and time
    if (type(time) == float) or (type(time) == np.float_):
        obstime = Time(time, format='mjd')
    elif type(time) == Time:
        obstime = time
    else:
        print('Did not understand time='+str(time)+', exiting...')
        return None
    altaz_frame = AltAz(obstime=obstime, location=earth_location)

    # Convert the sky direction to AltAz coordinates
    observation_altaz = sky_coord.transform_to(altaz_frame)

    # Calculate the normal vector to the observation plane
    normal_vector = np.array([np.cos(observation_altaz.alt)*np.sin(observation_altaz.az),
                              np.cos(observation_altaz.alt)*np.cos(observation_altaz.az),
                              np.sin(observation_altaz.alt)])

    projected_vectors = []
    for vec in vectors:
        projection = vec - np.dot(vec, normal_vector) * normal_vector
        projected_vectors.append(projection[:2])  # Keep only the first two components X,Y

    return np.array(projected_vectors)

def onlineChannelAveraging(msmd, spws=None):
    """
    For Cycle 3-onward data, determines the channel averaging factor from
    the ratio of the effective channel bandwidth to the channel width. From aU.
    
    Parameters:
    spw: a single value, or a list; if Nonne, then uses science spws
    Returns: single value for a single spw, or a list for a list of spws
    -Todd Hunter.
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

def calcProjDist(spwsetup, intentlist, refant = -1, scantouse = -1):
    '''Function called to take a list of X,Y,Z positions vectors from a
    given reference antenna to each of the antennas used in the array, and project
    these vectors towards the direction in the sky observed in a given scan.
    
    Parameters:
    spwsetup: Dictionary obtained from the getSpecSetup() function
    intentlist: List of intents to process (i.e. whose scan to consider)
    refant: The antenna used as reference. If none given, a centroid at
            X,Y,Z = 0,0,0 will be used.
    scantouse: Scan(s) to consider in the calculation. If none given, the list
               of all scans of the requested intent will be used.
    '''

    #If refant is points to one of the antennas, use that as center
    X = np.transpose(spwsetup['antposXYZ'])[0]
    Y = np.transpose(spwsetup['antposXYZ'])[1]
    Z = np.transpose(spwsetup['antposXYZ'])[2]
    if refant in spwsetup['antids']:
        X0 = X[refant]
        Y0 = Y[refant]
        Z0 = Z[refant]
    else:
        X0 = 0
        Y0 = 0
        Z0 = 0
    XYZ = np.transpose(np.array([X-X0, Y-Y0, Z-Z0]))
    #Define scan list to use
    if scantouse > 0:
        scanlist = [scantouse]
    else:
        scanlist = spwsetup['scan']['*PHASE*']

    #Calculate projected distances for each scan
    antposXYproj = {}
    antcenterdistproj = {}
    for intent in intentlist:
        if len(spwsetup['fieldid'][intent]) == 0:
            continue
        fieldid = spwsetup['fieldid'][intent][0]
        fieldcoords = SkyCoord(ra=spwsetup['coords'][fieldid]['m0']['value'],
                               dec=spwsetup['coords'][fieldid]['m1']['value'],
                               unit=(u.Quantity('1'+spwsetup['coords'][fieldid]['m0']['unit']),
                                     u.Quantity('1'+spwsetup['coords'][fieldid]['m1']['unit'])),
                               frame=spwsetup['coords'][fieldid]['refer'].lower())
        for scan in scanlist:
            antposXYproj[scan] = project_vectors_to_sky_direction(XYZ, fieldcoords, spwsetup['scan_mean_time'][scan]/86400.0)
            Xproj, Yproj = np.transpose(antposXYproj[scan])
            antcenterdistproj[scan] = np.sqrt(Xproj**2+Yproj**2)

    return (antposXYproj, antcenterdistproj)

def getSpecSetup(myms, spwlist = [], intentlist = ['*BANDPASS*', '*FLUX*', '*PHASE*', '*CHECK*', '*POLARIZATION*'], bfolder = None, applycalQAversion=""):
    '''Obtain spectral setup dictionary from MS.
    Positional Parameters:
    myms: MS folder name
    Keyword Parameters:
    spwlist: List of SPWs to include in the dictionary. Default is to use all science SPWs.
    intentlist: List of intents to include in the dictionary.
    bfolder: Use buffer folder to read dictionary from previous execution of this command, saved as a pickle file.
             Default is None. If some folder is given, but no pickle file for the requested MS is found, create
             it with current result.
    '''

    #If full path is given, take last bit for MS name
    mssplit = myms.split('/')
    if len(mssplit) > 1:
        msname = mssplit[-1]
    else:
        msname = myms

    #If the buffer folder bfolder is used, and there is a pickle file for the spwsetup, read it
    spwpkl = str(bfolder)+'/'+str(msname)+'_spwsetup'+'.v'+str(applycalQAversion)+'.pkl'
    if (bfolder is not None) and os.path.exists(spwpkl):
        print("Buffering existing spectral setup at : "+spwpkl)
        #Pickle file for spw setup
        spwpklfile = open(spwpkl, 'rb')
        spwsetup = pickle.load(spwpklfile)
        spwpklfile.close()
        # print("using bfolder")
        return spwsetup

    #Else read in the information from the MS
    #if spwlist is empty, get all science SPWs
    msmd = casatools.msmetadata()
    msmd.open(myms)
    if len(spwlist) == 0:
        spwlist = getSpwList(msmd)
    spwsetup = {}
    spwsetup['msname'] = msname
    spwsetup['spwlist'] = spwlist
    spwsetup['intentlist'] = intentlist
    spwsetup['scan'] = {}
    spwsetup['fieldname'] = {}
    spwsetup['fieldid'] = {}
    for intent in intentlist:
        spwsetup['scan'][intent] = list(msmd.scansforintent(intent))
        spwsetup['fieldname'][intent] = list(msmd.fieldsforintent(intent,asnames=True))
        spwsetup['fieldid'][intent] = list(msmd.fieldsforintent(intent,asnames=False))
    spwsetup['fieldlist'] = np.unique([fieldid[0] for fieldid in spwsetup['fieldid'].values() if len(fieldid) > 0])
    spwsetup['coords'] = {}
    for fieldid in spwsetup['fieldlist']:
        spwsetup['coords'][fieldid] = msmd.phasecenter(fieldid=fieldid)

    spwsetup['antids'] = msmd.antennasforscan(scan = spwsetup['scan'][intentlist[0]][0])
    spwsetup['antnames'] = np.array(msmd.antennanames(spwsetup['antids']))
    spwsetup['spwnames'] = np.array(msmd.namesforspws(spwlist))
    spwsetup['fdmspws'] = msmd.fdmspws()
    spwsetup['tdmspws'] = msmd.tdmspws()
    spwsetup['station'] = msmd.antennastations()

    #Get scan times
    start_time = {}
    end_time = {}
    mean_time = {}
    for intent in intentlist:
        for scan in spwsetup['scan'][intent]:
            this_scan_times = msmd.timesforscan(scan=scan) 
            start_time[scan] = np.min(this_scan_times)
            end_time[scan] = np.max(this_scan_times)
            mean_time[scan] = np.mean(this_scan_times)
    spwsetup['scan_start_time'] = start_time
    spwsetup['scan_end_time'] = end_time
    spwsetup['scan_mean_time'] = mean_time

    #Read in antenna positions
    antlong = []
    antlat = []
    antalt = []
    for i in spwsetup['antids']:
        posdict = msmd.antennaposition(i)
        antlong.append(posdict['m0']['value'])
        antlat.append(posdict['m1']['value'])
        antalt.append(posdict['m2']['value'])
    #Project the coordinates to the tangent plane centered at the array center
    midlong = np.mean(antlong)
    midlat = np.mean(antlat)
    midalt = np.mean(antalt)
    Xpp = (antlong-midlong)*midalt*np.cos(midlat)
    Ypp = (antlat-midlat)*midalt
    Zpp = antalt-midalt
    spwsetup['antposgeodetic'] = np.transpose(np.array([antlong, antlat, antalt]))
    spwsetup['antposXYZ'] = np.transpose(np.array([Xpp, Ypp, Zpp]))
    spwsetup['antcenterpos'] = np.array([midlong, midlat, midalt])
    centerdist = np.sqrt(Xpp**2+Ypp**2+Zpp**2)
    spwsetup['antcenterdist'] = centerdist
    alldists = []
    for i in spwsetup['antids']:
        distsi = []
        for j in spwsetup['antids']:
            if i != j:
                distsi.append(np.sqrt((Xpp[i]-Xpp[j])**2+(Ypp[i]-Ypp[j])**2+(Zpp[i]-Zpp[j])**2))
        alldists.append(distsi)
    spwsetup['alldists'] = alldists

    #Calculate projected distances for each scan with respect to x,y,z=(0,0,0)
    (antposXYproj, antcenterdistproj) = calcProjDist(spwsetup, intentlist)
    spwsetup['antposXYproj'] = antposXYproj
    spwsetup['antcenterdistproj'] = antcenterdistproj

    #Get SPW info
    nchanperbb = [0, 0, 0, 0]
    for spwid in spwlist:
        spwsetup[spwid] = {}
        #Get SPW information: frequencies of each channel, etc.
        chanfreqs = msmd.chanfreqs(spw=spwid)
        nchan = len(chanfreqs)
        fcenter = (chanfreqs[nchan//2-1]+chanfreqs[nchan//2])/2.
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
        spwsetup[spwid]['BB'] = int(msmd.baseband(spwid))
        spwsetup[spwid]['BBname'] = 'BB_'+str(spwsetup[spwid]['BB'])
        spwsetup[spwid]['istdm'] = (spwid in spwsetup['tdmspws'])
        spwsetup[spwid]['nchan_high'] = nchan*5
        spwsetup[spwid]['chansep_high'] = chansep/5.
        spwsetup[spwid]['chanfreqs_high']  = chanfreqs[0] + (chansep/5.)*np.arange(nchan*5)
        spwsetup[spwid]['fcenter_high'] = (spwsetup[spwid]['chanfreqs_high'][nchan//2-1]+spwsetup[spwid]['chanfreqs_high'][nchan//2])/2.
        nchanperbb[spwsetup[spwid]['BB'] - 1] += spwsetup[spwid]['nchan']

    #Save SPW setup in buffer folder
    if (bfolder is not None) and (not os.path.exists(spwpkl)):
        spwpkl = str(bfolder)+'/'+msname+'_spwsetup'+'.v'+str(applycalQAversion)+'.pkl'
        print('Writing pickle dump of SPW setup to '+spwpkl)
        pklfile = open(spwpkl, 'wb')
        pickle.dump(spwsetup, pklfile, protocol=2)
        pklfile.close()
    msmd.close()
    return spwsetup

def get_intents_to_process(spwsetup, intents = None):
    #Define intents that need to be processed
    #avoiding intents with repeated scans

    if intents is None:
        intents = spwsetup['intentlist']
    intents2proc = []
    for intent in intents: 
        if intent in spwsetup['intentlist']: 
            alreadyincluded = any([(spwsetup['scan'][intent] == spwsetup['scan'][prevint]) for prevint in intents2proc])
            if (len(spwsetup['scan'][intent]) > 0) and (not alreadyincluded) and \
               (not (spwsetup['fieldname'][intent][0] in SSOfieldnames)):
                intents2proc.append(intent)

    return intents2proc

def getUnitsDicts(spwsetup):
    '''Return dictionaries with factor and unit strings from spwsetup dictionary.'''

    unitfactor = {}
    unitstr = {}
    for spw in spwsetup['spwlist']:
        #plot factors to get the right units, frequencies in GHz:
        frequencies = (1.e-09)*spwsetup[int(spw)]['chanfreqs']
        bandwidth = np.ma.max(frequencies) - np.ma.min(frequencies)
        band_midpoint = (np.ma.max(frequencies) + np.ma.min(frequencies)) / 2.0
        unitfactor[spw] = {'amp_slope': 1.0/bandwidth, 'amp_intercept': 1.0, 'phase_slope': (180.0/np.pi)/bandwidth, 'phase_intercept': (180.0/np.pi)}
        unitstr[spw] = {'amp_slope': '[Jy/GHz]', 'amp_intercept': '[Jy]', 'phase_slope': '[deg/GHz]', 'phase_intercept': '[deg]'}

    return (unitfactor, unitstr)

def getFieldSPWFromFileList(namelist):
    '''Obtain SPW and Fields inside each of the casa tables in a list of filenames.
    Return dictionary with field ID and list of SPWs for each filename.
    '''

    tbldata = {'fieldid': {}, 'spws': {}}
    #Start the casa tools table
    tb = casatools.table()

    for name in namelist:
        tb.open(name)
        tbldata['fieldid'][name] = np.unique(tb.getcol('FIELD_ID'))
        tbldata['spws'][name] = np.unique(tb.getcol('SPECTRAL_WINDOW_ID'))
        tb.close()

    return tbldata

def getDiagTimegaincalTables(plfolder, ms, spwsetup, tbltype = 'inf', intent = '*PHASE*'):
    ''' Obtain filenames of amplitude and phase diagnostic tables inside of pipeline working
    folder.
    
    Parameters:
    plfolder: Full pipeline execution folder, including the path to the working subfolder.
    ms: MS filename
    spwsetup: Dictionary obtained from the getSpecSetup() function
    tbltype: String specifying which type of timegaincal table to search for.
             Either 'inf' or 'int'.
    intent: Intent to search for inside the timegaincal tables.
    '''

    full_phase_tblist = glob.glob(plfolder+'/'+ms+'.hifa_timegaincal.*.solint*.gpcal.tbl')
    tbldata_phase = getFieldSPWFromFileList(full_phase_tblist)
    if tbltype == 'int':
        sel_phase_table = [name for name in full_phase_tblist if (spwsetup['fieldid'][intent][0] in tbldata_phase['fieldid'][name]) and (not 'solintinf' in name)]
    elif tbltype == 'inf':
        sel_phase_table = [name for name in full_phase_tblist if (spwsetup['fieldid'][intent][0] in tbldata_phase['fieldid'][name]) and ('solintinf' in name)]
    else:
        print('Please choose tbltype=int/inf ! Exiting...')
        return {'amp_table': None, 'nspws_amp_table': None, 'phase_table': None, 'nspws_phase_table': None}
    nspw_in_phase_table = [len(tbldata_phase['spws'][name]) for name in sel_phase_table]
    maxspws_phase = np.argsort(nspw_in_phase_table)[-1]
    nmaxspws_phase = nspw_in_phase_table[maxspws_phase]
    phase_table = sel_phase_table[maxspws_phase]
        
    full_amp_tblist = glob.glob(plfolder+'/'+ms+'.hifa_timegaincal.*.solint*.gacal.tbl')
    tbldata_amp = getFieldSPWFromFileList(full_amp_tblist)
    if tbltype == 'int':
        sel_amp_table = [name for name in full_amp_tblist if (spwsetup['fieldid'][intent][0] in tbldata_amp['fieldid'][name]) and (not 'solintinf' in name)]
    elif tbltype == 'inf':
        sel_amp_table = [name for name in full_amp_tblist if (spwsetup['fieldid'][intent][0] in tbldata_amp['fieldid'][name]) and ('solintinf' in name)]
    nspw_in_amp_table = [len(tbldata_amp['spws'][name]) for name in sel_amp_table]
    maxspws_amp = np.argsort(nspw_in_amp_table)[-1]
    nmaxspws_amp = nspw_in_amp_table[maxspws_amp]
    amp_table = sel_amp_table[maxspws_amp]
    
    return {'amp_table': amp_table, 'nspws_amp_table': nmaxspws_amp, 'phase_table': phase_table, 'nspws_phase_table': nmaxspws_phase}


def robust_stats(a, forcezeromu = False):
    """
    Return median and estimate standard deviation
    of numpy array A using median statistics

    Parameters:
    a: Array in which to perform statistical calculations.
    forcezeromu: Boolean. Whether to force the assumption of median to be zero.
    returns: Tuple (median estimate, 1-sigma estimate).
    """
    # correction factor for obtaining sigma from MAD
    madfactor = 1.482602218505602

    n = len(a)
    # Fitting parameters for sample size correction factor b(n)
    if n % 2 == 0:
        alpha = 1.32
        beta = -1.5
    else:
        alpha = 1.32
        beta = -0.9
    bn = 1.0 - 1.0 / (alpha * n + beta)
    if not forcezeromu:
        mu = np.median(a)
    else:
        mu = 0.0
    sigma = (1.0 / bn) * madfactor * np.ma.median(np.ma.abs(a - mu))
    return mu, sigma

def robust_amp_stats(A):
    '''Function to calculate the median and median centered standard deviation
    of a sample of angles in radians, where the median is calculated in vector form
    (median of real and imaginary parts of complex values corresponding to these angles).
    
    A: Numpy (Masked) Array of amplitudes.
    '''
    goodvalues = np.isfinite(A)
    if type(A) == np.ma.core.MaskedArray:
        z = 1.0*A
        z.mask = (A.mask | ~goodvalues)
    else:
        z = np.ma.MaskedArray(A, mask=~goodvalues)
    ngoodvals = np.sum(~z.mask)
    avgA = np.ma.mean(z)
    medianA = np.ma.median(z)
    if ngoodvals >= 2:
        stdA = np.ma.std(A)
        madA = np.ma.median(np.ma.abs(z - medianA))
    else:
        stdA = np.nan
        madA = np.nan
    return {'avg': avgA, 'median': medianA, 'std': stdA, 'mad': madA}

def robust_phase_stats(phi):
    '''Function to calculate the median and median centered standard deviation
    of a sample of angles in radians, where the median is calculated in vector form
    (median of real and imaginary parts of complex values corresponding to these angles).
    
    phi: Numpy (Masked) Array of phases.
    '''
    goodvalues = np.isfinite(phi)
    if type(phi) == np.ma.core.MaskedArray:
        z = np.ma.exp(1.j*phi)
        z.mask = (phi.mask | ~goodvalues)
    else:
        z = np.ma.MaskedArray(np.ma.exp(1.j*phi), mask=~goodvalues)
    ngoodvals = np.sum(~z.mask)
    meanreal = np.ma.mean(np.real(z))
    meanimag = np.ma.mean(np.imag(z))
    medianreal = np.ma.median(np.real(z))
    medianimag = np.ma.median(np.imag(z))
    if np.ma.is_masked(medianreal) or np.ma.is_masked(medianimag):
        medianreal = 0
        medianimag = 0
    meanz = meanreal + 1.j*meanimag
    avgphi = np.angle(meanz)
    medianz = medianreal + 1.j*medianimag
    medianphi = np.angle(medianz)
    z0 = z*np.exp(-1.j*medianphi)
    phi0 = np.ma.angle(z0)
    if ngoodvals >= 2:
        stdphi = np.ma.std(phi0)
        madphi = np.ma.median(np.ma.abs(phi0))
    else:
        stdphi = np.nan
        madphi = np.nan
    return {'avg': avgphi, 'median': medianphi, 'std': stdphi, 'mad': madphi}

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

def table_stats(bptab, var = 'phase', axis = 'time'):
    '''Calculate summary statistics for a TableWrapper object.
    
    Parameters:
    var: Variable to calculate statistic for, options: 'amp', 'phase'(default).
    axis: Independent variable to gather data from. options: 'freq', 'time'(default).
    '''

    doexit = False
    if var == 'phase':
        scalefactor = 180.0/np.pi
        statsfunc = robust_phase_stats
        if axis == 'time':
            data = bptab.phase_time
            flag = bptab.flag_time
            is_fully_flagged = bptab.is_fully_flagged_time
            refant = bptab.refant_time
        elif axis == 'freq':
            data = bptab.phase_freq
            flag = bptab.flag_freq
            is_fully_flagged = bptab.is_fully_flagged_freq
            refant = bptab.refant_freq
        else:
            print('Unknown axis '+str(axis)+'! exiting...')
            doexit = True
    elif var == 'amp':
        scalefactor = 1.0
        statsfunc = robust_amp_stats
        if axis == 'time':
            data = bptab.amp_time
            flag = bptab.flag_time
            is_fully_flagged = bptab.is_fully_flagged_time
            refant = bptab.refant_time
        elif axis == 'freq':
            data = bptab.amp_freq
            flag = bptab.flag_freq
            is_fully_flagged = bptab.is_fully_flagged_freq
            refant = bptab.refant_freq
        else:
            print('Unknown axis '+str(axis)+'! exiting...')
            doexit = True
    else:
        print('Unknown variable '+str(var)+'! exiting...')
        doexit = True

    if doexit:
        return None

    #Get number of SPWs, scans, antennas, pols in the table
    nspws = len(bptab.spws)
    nscans = len(bptab.scanlist)
    nants = len(bptab.antids)
    #Assuming all the SPWs, scans and antennas have the same npol
    #(npols, nints) = np.shape(data[bptab.spws[0]][bptab.scanlist[0]][0])
    npols = bptab.spwsetup[bptab.spws[0]]['npol']
    avg = np.ma.MaskedArray(np.zeros((nspws, nscans, nants, npols)), mask = np.ones((nspws, nscans, nants, npols), dtype=bool))
    med = np.ma.MaskedArray(np.zeros((nspws, nscans, nants, npols)), mask = np.ones((nspws, nscans, nants, npols), dtype=bool))
    std = np.ma.MaskedArray(np.zeros((nspws, nscans, nants, npols)), mask = np.ones((nspws, nscans, nants, npols), dtype=bool))
    mad = np.ma.MaskedArray(np.zeros((nspws, nscans, nants, npols)), mask = np.ones((nspws, nscans, nants, npols), dtype=bool))
    for sidx, spwid in enumerate(bptab.spws):
        for cidx, scan in enumerate(bptab.scanlist):
            for aidx, antid in enumerate(bptab.antids):
                (thisnpols, thisnints) = np.shape(data[spwid][scan][antid])
                for pol in range(thisnpols):
                    #print('[spwid][scan][antid]:'+str((spwid,scan,antid)))
                    #thisdatashape = np.shape(data[spwid][scan][antid])
                    #print('thisdatashape:'+str(thisdatashape))
                    #print(' len(thisdatashape):'+str(len(thisdatashape)))
                    if is_fully_flagged[spwid][scan][antid] or (len(np.shape(data[spwid][scan][antid])) != 2):
                        avg.data[sidx,cidx,aidx,pol] = np.nan
                        avg.mask[sidx,cidx,aidx,pol] = True
                        med.data[sidx,cidx,aidx,pol] = np.nan
                        med.mask[sidx,cidx,aidx,pol] = True
                        std.data[sidx,cidx,aidx,pol] = np.nan
                        std.mask[sidx,cidx,aidx,pol] = True
                        mad.data[sidx,cidx,aidx,pol] = np.nan
                        mad.mask[sidx,cidx,aidx,pol] = True
                    else:
                        statsdict = statsfunc(data[spwid][scan][antid][pol])
                        avg.data[sidx,cidx,aidx,pol] = statsdict['avg']*scalefactor
                        avg.mask[sidx,cidx,aidx,pol] = False
                        med.data[sidx,cidx,aidx,pol] = statsdict['median']*scalefactor
                        med.mask[sidx,cidx,aidx,pol] = False
                        std.data[sidx,cidx,aidx,pol] = statsdict['std']*scalefactor
                        std.mask[sidx,cidx,aidx,pol] = False
                        mad.data[sidx,cidx,aidx,pol] = statsdict['mad']*scalefactor
                        mad.mask[sidx,cidx,aidx,pol] = False

    return {'avg': avg, 'med': med, 'std': std, 'mad': mad, 'idx': ['spw','scan','ant','pol'],
        'var': var, 'axis': axis, 'refant': refant}

