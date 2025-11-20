from dataclasses import dataclass
from enum import Enum
import itertools
import os
import pathlib

import matplotlib.pyplot as plt
import numpy as np
import scipy

import pipeline.extern.adopted as adopted
from pipeline.domain.measurementset import MeasurementSet
import pipeline.domain.measures as measures
from pipeline.infrastructure import casa_tools
import pipeline.infrastructure.logging as logging
from pipeline.infrastructure.utils import caltable_tools


WVR_LO = [38.1927, 45.83125, 91.6625, 183.325, 259.7104, 274.9875, 366.650, 458.3125, 641.6375]

LOG = logging.get_logger(__name__)


# kberry added code to track failures and associated type
class FailureType(Enum):
    PHASE = "phase"
    AMP = "amp"
    AMP_AND_PHASE = "amp and phase"
    SPW_BINNING = "binning"
    SPW_SMALL_BANDWIDTH = "bandwidth"


@dataclass
class SpwFailure:
    ant_set: set
    failure_type: FailureType


def add_spw_failure(failing_spws: dict[int, SpwFailure], spw_id: int,
                    ant_id: str, failure_type: FailureType) -> None:
    """
    Adds failure information for a single antenna and associated failure type
    to the dict of failing spws.
    """
    if failure_type in (FailureType.SPW_BINNING, FailureType.SPW_SMALL_BANDWIDTH):
        # This fails for the entire spw so we don't need per-antenna information
        failing_spws[spw_id] = SpwFailure(set(), failure_type)
        return

    if spw_id in failing_spws:
        failing_spws[spw_id].ant_set.add(ant_id)
        if failure_type != failing_spws[spw_id].failure_type:
            failing_spws[spw_id].failure_type = FailureType.AMP_AND_PHASE
    else:
        failing_spws[spw_id] = SpwFailure({ant_id}, failure_type)


# Utility functions added by kberry or adopted from AU
def science_spw_bandwidths(vis: MeasurementSet) -> dict[int, float]:
    """
    Returns a dict of the bandwidths of the science spectral windows,
    indexed by the spw id.
    """
    spws = vis.get_spectral_windows(science_windows_only=True)
    bandwidths = {}
    for spw in spws:
        bandwidths[spw.id] = float(spw.bandwidth.to_units(measures.FrequencyUnits.HERTZ))
    return bandwidths


# Unmodified by kberry, excepting formatting
def fitAtmLines(ATMprof, freq):
    """
    Purpose:
        Given an atmospheric profile, find the features caused by water/ozone/etc
        and fit a Lorentzian profile to it, returning the center and gamma scale.

    Inputs:
        ATMprof : numpy.ndarray
            An atmospheric profile as returned by ATMtrans()

        verbose : boolean : OPTIONAL
            If True, then information about the fit will be printed to the terminal.

    Outputs:
        centers : list of floats
            The center channel of found features.

        scales : list of floats
            The gamma scale factor of found features.

    """

    def get_atm_peaks(ATMprof):
        """
        Purpose: Use scipy's peak finding algorithm to find ATM dips >1%.

        Inputs:
            ATMprof : array
                An atmospheric profile which is simply a 1 dimensional array.
        """
        normATM = -ATMprof + np.median(ATMprof)
        peaks, _ = scipy.signal.find_peaks(normATM, height=0.01)
        return peaks

    def lorentzian(x, x0, a, gam, off):
        """
        Purpose: Standard definition of a Lorentzian to optimize.

        Inputs:
            x : array
                The x data to fit to
            x0 : float
                The line center.
            a : float
                The amplitude of the feature.
            gam : float
                The width of the feature (2*gamma = FWHM).
            off : float
                The offset from 0.
        """
        return a * gam**2 / (gam**2 + (x - x0)**2) + off

    def get_gamma_bounds(center, width=50.):
        """
        Purpose: Assuming that atmospheric features are typically about 50km/s
                wide, return the frequency width for a given center frequency
                using the standard radio convention for velocity width.

                    delta_V = delta_nu / nu_0 * c
        Inputs:
            center : float
                Frequency location of the line center, nu_0 in the above equation.

            width : float : OPTIONAL
                The velocity width in km/s.
                Default: 50.
        """
        ckms = 299792.4580
        return width * center / ckms

    # Find atmospheric features in the profile
    atm_feature_idxs = get_atm_peaks(ATMprof)

    # Define our x and y data.
    xData = np.arange(0, len(ATMprof))
    yData = ATMprof

    # Loop over each feature, fitting a Lorentzian and reporting the fits.
    centers, scales = [], []
    for i in range(len(atm_feature_idxs)):
        x0_guess = atm_feature_idxs[i]
        a_guess = yData[x0_guess] - max(yData)
        gamma_guess = 1.0
        off_guess = np.median(yData)

        # center must be +/- 20 channels,
        # amp must be between 0 and -1 (atm dips are always negative here)
        # gamma must be between 1 channel and 50 km/s (in channel space).
        # offset is between 0 (no transmission at all) and 1 (no opacity issues).
        x0_bounds = [x0_guess - 20, x0_guess + 20]
        a_bounds = [-1, 0]
        gamma_bounds = [1, get_gamma_bounds(freq[x0_guess] / abs(freq[1] - freq[0]))]
        off_bounds = [0, 1]

        popt, cov = scipy.optimize.curve_fit(
                        f=lorentzian,
                        xdata=xData,
                        ydata=yData,
                        p0=[x0_guess, a_guess, gamma_guess, off_guess],
                        bounds=([x0_bounds[0], a_bounds[0], gamma_bounds[0], off_bounds[0]], [x0_bounds[1], a_bounds[1], gamma_bounds[1], off_bounds[1]])
                    )
        x2 = int(np.ceil(popt[0]))
        x1 = int(np.floor(popt[0]))

        centers.append((popt[0]-x1)*(float(freq[x2])-float(freq[x1]))/(x2-x1) + float(freq[x1]))
        scales.append(popt[2]*abs(float(freq[1])-float(freq[0])))
    return centers, scales


def getInfoFromTable(vis, caltable) -> tuple[list[int], list[str], list[int], list[str], list[int], float]:
    """
    Returns a tuple of field ids, field names, spw ids, antenna names, 
    and antenna ids from the specified caltable.
    """
    fieldIds = caltable_tools.field_ids_from_caltable(caltable)
    fieldNames = caltable_tools.field_names_from_caltable(caltable)
    spwIds = caltable_tools.get_spws_from_table(caltable)
    antennaNames = caltable_tools.antenna_names_from_caltable(caltable)
    antIds = caltable_tools.get_ant_ids_from_caltable(caltable)
    pwv, pwv_sigma = adopted.getMedianPWV(vis)
    return fieldIds, fieldNames, spwIds, antennaNames, antIds, pwv


def extractValues(data, vis, caltable):
    fieldIds, fieldNames, spwIds, antennaNames, antIds, pwv = getInfoFromTable(vis, caltable)
    fieldname = fieldNames[0]

    # create lists, with indexes antenna, poln, spw
    bandpass_phase = [[] for i in range(len(spwIds))]
    bandpass_amp = [[] for i in range(len(spwIds))]
    bandpass_phase2 = [[] for i in range(len(spwIds))]
    bandpass_amp2 = [[] for i in range(len(spwIds))]
    bandpass_flag = [[] for i in range(len(spwIds))]
    for i, ispw in enumerate(spwIds):
        bandpass_phase[i] = [[] for iant in range(len(antIds))]
        bandpass_amp[i] = [[] for iant in range(len(antIds))]
        bandpass_phase2[i] = [[] for iant in range(len(antIds))]
        bandpass_amp2[i] = [[] for iant in range(len(antIds))]
        bandpass_flag[i] = [[] for iant in range(len(antIds))]
        for j, iant in enumerate(antennaNames):
            bandpass_phase[i][j] = [[] for ipol in range(2)]
            bandpass_amp[i][j] = [[] for ipol in range(2)]
            bandpass_phase2[i][j] = [[] for ipol in range(2)]
            bandpass_amp2[i][j] = [[] for ipol in range(2)]
            bandpass_flag[i][j] = [[] for ipol in range(2)]

    for i, ifield in enumerate(list(data.keys())[1:]):
        for j, ispw in enumerate(list(data[fieldname].keys())):
            for k, iant in enumerate(list(data[fieldname][ispw].keys())[3:]):
                for l, ipol in enumerate(list(data[fieldname][ispw][iant].keys())):
                    bandpass_phase[j][k][l] = (data[ifield][ispw][iant][ipol]['phase'])
                    bandpass_amp[j][k][l] = (data[ifield][ispw][iant][ipol]['amp'])
                    bandpass_phase2[j][k][l] = (data[ifield][ispw][iant][ipol]['phase2'])
                    bandpass_amp2[j][k][l] = (data[ifield][ispw][iant][ipol]['amp2'])
                    bandpass_flag[j][k][l] = (data[ifield][ispw][iant][ipol]['flag'])

    return bandpass_phase, bandpass_amp, bandpass_phase2, bandpass_amp2, bandpass_flag


def evalPerAntBP_Platform(data, output_dir, ms, caltable) -> dict:
    """
    Evaluate bandpass platforming for each ms and caltable

    Args:
        data: dict containing info needed for evaluation generated by bandpass_platforming()
        output_dir: directory to save the output files
        ms: measurement set
        caltable: calibration table name

    Returns:
        spws_affected: dict containing the spws affected by platforming
    """
    vis = ms.name
    LOG.info(f"Doing Platforming evaluation for {vis}, {caltable}")

    # Added by kberry to track failing spws
    spws_affected = {}  # Format spw: SpwFailure({ant1...n}, FailureType)

    pldir = str(pathlib.Path(output_dir).parent)

    caltable_name = pathlib.Path(caltable).name
    LOG.info(f"{caltable} in Platforming evaluation")

    # Get the meta data from caltable
    fieldIds, fieldNames, spwIds, antennaNames, antIds, pwv = getInfoFromTable(vis, caltable)

    # Construct the multidimensional array containing the bandpass solution (amp and phase) from bandpass dict and caltable
    # Bandpass_{amp/phase}[spwid][antid][polz]
    bandpass_phase, bandpass_amp, bandpass_phase2, bandpass_amp2, bandpass_flag = extractValues(data, vis, caltable)

    # Bandpass calibrator field name
    fieldname = list(data.keys())[1]

    # Pre-compute the atmospheric model per spw to avoid repeating the calculation per-antenna
    atm_cache = {}

    for spwid in spwIds:
        spw_bandwidth = data[fieldname][spwid]['bw']
        # This heuristic is only evaluated for FDM spws, so skip this calculation when it's not needed
        spw_type = ms.get_spectral_window(spwid).type
        if 'FDM' in spw_type:
            spw_freq = data[fieldname][spwid]['freq']
            LOG.info(f"Caching atm for {spwid}")
            frequency, channel, transmission, Tebbsky, tau = adopted.CalcAtmosphere(spw_freq, pwv)
            atm_cache[spwid] = {
                "frequency": frequency,
                "channel": channel,
                "transmission": transmission,
                "Tebbsky": Tebbsky,
                "tau": tau,
            }

    # Taking statistical summary values for heuristics
    # per spw, ant, and pol
    spwIds = caltable_tools.get_spws_from_table(caltable)
    antennaNames = caltable_tools.antenna_names_from_caltable(caltable)

    # Store information which needs to be written to files:

    # Appended string containing the heuristics values
    note_platform_start_formatted_strings = []

    # Appended string containing the flagging commands
    flagnote_formatted_strings = []

    note_platform_formatted_strings = []
    ##############################
    # Heuristics evaluation is done per ant, per spw, per pol
    # Therefore we loop through antennas, spwids, polz
    ##############################

    # Loop over antennas and spws
    for j, k in itertools.product(range(len(antennaNames)), range(len(spwIds))):
        iant = antennaNames[j]
        ispw = spwIds[k]

        # This heuristic is only evaluated for FDM spws
        spw_type = ms.get_spectral_window(ispw).type
        if 'FDM' not in spw_type:
            LOG.info(f"Subband qa heuristic not evaluated for spw {ispw} as it is not a FDM spw.")
            continue

        ################################
        # Read ancillary information
        ################################
        spw_bandwidth = data[fieldname][ispw]['bw']
        spw_nchan = data[fieldname][ispw]['nchan']
        spw_freq = data[fieldname][ispw]['freq']
        subb_bw = 62.5e6 * 15.0/16.0  # for edge channels
        subb_num = abs(int(round(spw_bandwidth / subb_bw)))  # Number of subband chunks
        subb_nchan = int(spw_nchan / subb_num)  # Number of channels per subband

        # This heuristic is not evaluated if the spw binning is high enough that the channel width
        # is larger than the subband width
        chanwidth = spw_bandwidth/spw_nchan

        if chanwidth >= subb_bw:
            add_spw_failure(spws_affected, ispw, "", FailureType.SPW_BINNING)
            continue

        # This heuristic is not evaluated if the bandwidth of the spw is equal
        # or smaller than twice the subband width
        if spw_bandwidth <= 2 * subb_bw:
            add_spw_failure(spws_affected, ispw, "", FailureType.SPW_SMALL_BANDWIDTH)
            continue

        #################################
        # naming plot files
        # bandpass amp   pol0 pol1
        # bandpass phase pol0 pol1
        #################################
        figure_name = caltable_name + '_ant' + iant + '_spw' + str(ispw) + '_platforming.png'
        figure_path = os.path.join(output_dir, figure_name)
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(18, 15))
        fig.suptitle(pldir + ' ' + vis + ' ' + 'ant ' + iant + ' spw ' + str(ispw), fontsize=20)


        ################################
        # Generating or using the pre-computed atmospheric transmission model using median pwv value
        # this has two purposes
        # 1. the heuristics skips if the subband center frequency is within the frequency range (+/-2FWHM) affected by atmospheric absorption line
        # 2. the heuristics skips if the transmission value is less than 0.3 at the subband center frequency even if the subband center frequency is
        #   outside the atmospheric absorption line
        ###############################

        # Use the cached atmosphere transmission model if it exists.
        if ispw in atm_cache:
            LOG.debug(f"Using cached atm for {ispw}")
            atm = atm_cache[ispw]
            frequency, channel, transmission, Tebbsky, tau = (
                atm[elt] for elt in ['frequency', 'channel', 'transmission', 'Tebbsky', 'tau']
            )
        else:
            LOG.debug(f"Recalculating atm for {ispw}")
            frequency, channel, transmission, Tebbsky, tau = adopted.CalcAtmosphere(spw_freq, pwv)
        centers, scales = fitAtmLines(transmission, spw_freq)  # FWHM=2xscale
        bounds = []
        for b in range(len(centers)):
            bounds.append([centers[b] - 2 * scales[b], centers[b] + 2 * scales[b]])
        ###############################

        # Loop 3: Polarization
        for ipol in range(2):
            flagnote = ''

            # This is a container to keep the value: value[i+4]-value[i]
            bp_amp_diff = []
            bp_phs_diff = []

            # Bandpass amp and phase from a given antenna, spw, pol
            bp_phs = (bandpass_phase[k][j][ipol])
            bp_amp = (bandpass_amp[k][j][ipol])

            # bp_amp2 and bp_phs2 are used for plotting
            bp_phs2 = (bandpass_phase2[k][j][ipol])
            bp_amp2 = (bandpass_amp2[k][j][ipol])

            for ichan in range(spw_nchan-4):
                if bp_amp[ichan+4] > 0.0:
                    bp_amp_diff.append(bp_amp[ichan+4]-bp_amp[ichan])
                    bp_phs_diff.append(bp_phs[ichan+4]-bp_phs[ichan])
            bp_amp_rms = min(np.nanstd(bp_amp_diff), np.nanstd(bp_amp))
            bp_phs_rms = min(np.nanstd(bp_phs_diff), np.nanstd(bp_phs))  # Median of all values !=0

            note_platform = ''

            flagchan_range_amp = []
            flagchan_range_phs = []

            ################################
            # Heuristics are evaluated only if the data is from BLC mode
            # Following aoscheck, we check this by spw_bandwidth < 1.9GHz
            # This heuristic is only run from the hifa_bandpass qa when
            # the data is from BLC FDM mode.
            ################################
            #########################
            # Quantities measure for each subband
            #########################
            subb_phs_rms = []
            subb_amp_rms = []
            subb_phs = []
            subb_amp = []
            subb_phs_sobel_rms = []
            subb_amp_sobel_rms = []
            if subb_num > 1:
                note_platform_start = vis + ' ' + str(ispw) + ' ' + iant + ' ' + str(ipol) + ' '
                #####################
                # Sobel filter applied to the amp and phase
                #####################
                kernel = np.array([-1, 0, 1])
                check_phs = np.copy(bp_phs)
                check_amp = np.copy(bp_amp)
                sobel_phs = scipy.ndimage.convolve(check_phs[:, 0], kernel, mode='constant')
                sobel_amp = scipy.ndimage.convolve(check_amp[:, 0], kernel, mode='constant')
                sobel_phs[0] = sobel_phs[1]
                sobel_phs[-1] = sobel_phs[-2]
                sobel_amp[0] = sobel_amp[1]
                sobel_amp[-1] = sobel_amp[-2]
                #####################

                #####################
                # For each subband, estimate
                #    standard deviation of amp and phase: subb_{amp/phs}_rms
                #    mean of amp and phase: subb_{amp/phs}
                #    standard deviation of 'sobel' filtered amp and phase: subb_{amp/phs}_sobel_rms
                #####################
                for isubb in range(subb_num):
                    subb_phs_rms.append(np.nanstd(bp_phs[(isubb*subb_nchan):((isubb+1)*subb_nchan)]))
                    subb_amp_rms.append(np.nanstd(bp_amp[(isubb*subb_nchan):((isubb+1)*subb_nchan)]))
                    subb_phs.append(np.nanmean(bp_phs[(isubb*subb_nchan):((isubb+1)*subb_nchan)]))
                    subb_amp.append(np.nanmedian(bp_amp[(isubb*subb_nchan):((isubb+1)*subb_nchan)]))
                    subb_phs_sobel_rms.append(np.nanstd(sobel_phs[(isubb*subb_nchan):((isubb+1)*subb_nchan)]))
                    subb_amp_sobel_rms.append(np.nanstd(sobel_amp[(isubb*subb_nchan):((isubb+1)*subb_nchan)]))

                ######################
                # Heuristics 1: find the subband with anomalously large phase RMS   
                ######################

                # Estimate the median value of the subband RMS by excluding the largest value
                subb_phs_rms_sort = np.sort(subb_phs_rms)
                subb_phs_rms_med = np.nanmedian(subb_phs_rms_sort[:-1])
                subb_phs_sobel_rms_sort = np.sort(subb_phs_sobel_rms)
                subb_phs_sobel_rms_med = np.nanmedian(subb_phs_sobel_rms_sort[:-1])

                ######################
                # string that indicates the detection of platform "yes" or "no"
                # maxvalue keeps the maximum heuristics value
                ######################
                yesorno = 'NO'
                maxvalue = -999
                for isubb in range(subb_num):
                    ###########################
                    # Do atmospheric modeling and find
                    # 1. the absorption line peaks and their FWHM
                    # 2. transmission
                    # atmimpact checks whether the subband center frequency is affected by the atmospheric absorption line 
                    # transimpact measure the transmission value and check whether the transmission is less than 30%
                    # It is performed in several places in the code, so ideally it should be isolated as a seperate function
                    ###########################
                    atmimpact = False
                    transimpact = False
                    subb_center_freq = np.mean([spw_freq[(isubb)*subb_nchan], spw_freq[(isubb+1)*subb_nchan-1]])
                    for b, bound in enumerate(bounds):
                        if (subb_center_freq<bound[1] and subb_center_freq>bound[0]):
                            atmimpact = True
                    tid = np.argmin(np.abs(frequency-subb_center_freq))
                    if (transmission[tid]<0.3):
                        transimpact = True
                    ############################

                    ###################################
                    # Pre-check:
                    # Sobel filtered phase values in a given subband.
                    # 1.if the standard deviation of the Sobel filtered phase is larger than 3x
                    # the median subband RMS of the Sobel filtered phase value
                    # -OR-
                    # 2.if the maximum value of the Sobel filtered phase value is larger than 7x
                    # the median subband RMS of the Sobel filtered phase value,
                    # set check_subb_phs_var="YES"
                    ###################################

                    check_subb_phs_var = 'NO'
                    if (np.nanstd(sobel_phs[(isubb*subb_nchan):((isubb+1)*subb_nchan)])>3.0*subb_phs_sobel_rms_med) or (np.max(np.abs(sobel_phs[(isubb*subb_nchan):((isubb+1)*subb_nchan)]))>7.0*subb_phs_sobel_rms_med):
                        check_subb_phs_var = 'YES'

                    ###################################
                    # Update the maxvalue if the new subb_phs_rms is larger
                    ###################################
                    if maxvalue < subb_phs_rms[isubb]:
                        maxvalue = subb_phs_rms[isubb]
                    ###################################

                    ###################################
                    # Now evaluation 
                    # check, 
                    #  1. subband RMS is 5 x larger than the median subband RMS 
                    #  2. subband RMS is > 10 degree
                    #  3. subband is not affected by atmospheric absorption and low transmission
                    ###################################
                    if ((subb_phs_rms[isubb] > 5.0*subb_phs_rms_med and subb_phs_rms[isubb] > 10.0) and (not atmimpact) and (not transimpact)):
                        ###########################
                        #  check, the subband is neither of the first and the last subband, and the Sobel filtered RMS pre-check
                        ###########################
                        if (isubb != 0 and isubb != subb_num-1) and (check_subb_phs_var == 'YES'):
                            yesorno = 'YES'
                            #########################
                            # this is verbose message, which can be skipped for PL
                            #########################
                            this_note_platform = ' QA0_High_phase_spectral_rms subband: '+str(isubb)+' Spw '+str(ispw)+' Ant '+iant+'  P:'+str(ipol)+' BB:'+' TBD'+'  '+ "%.2f"%(subb_phs_rms[isubb]) + 'deg ('+"%.2f" %(subb_phs_rms[isubb]/subb_phs_rms_med)+'sigma)'
                            note_platform += (this_note_platform+'\n')
                            add_spw_failure(spws_affected, ispw, iant, FailureType.PHASE)
                            #########################

                            #########################
                            # this list contains the frequency range of the affected subband
                            # it is necessary for plotting
                            #########################
                            this_flagchan_range = [spw_freq[(isubb) * subb_nchan], spw_freq[(isubb + 1) * subb_nchan - 1]]
                            flagchan_range_phs.append(this_flagchan_range)
                            #########################
                    
                        #############################
                        # check, the subband is either the first or the last subband
                        #############################
                        elif (isubb == 0 or isubb == subb_num - 1):
                            ############################
                            # check if the standard deviation of the Sobel filtered value is 10 x larger than
                            # the median value of the subbands with the Sobel filtered phase value
                            ############################
                            if (np.nanstd(sobel_phs[(isubb * subb_nchan):((isubb + 1) * subb_nchan)]) > 10.0 * subb_phs_sobel_rms_med):
                                yesorno = 'YES'
                                ###########################
                                # this verbose message, which can be skipped for PL
                                ###########################
                                this_note_platform = ' QA0_High_phase_spectral_rms subband: '+str(isubb)+' Spw '+str(ispw)+' Ant '+iant+'  P:'+str(ipol)+' BB:'+' TBD'+'  '+ "%.2f"%(subb_phs_rms[isubb]) + 'deg ('+"%.2f" %(subb_phs_rms[isubb]/subb_phs_rms_med)+'sigma)'
                                note_platform += (this_note_platform+'\n')
                                add_spw_failure(spws_affected, ispw, iant, FailureType.PHASE)
                                #########################

                                #########################
                                # this list contains the frequency range of the affected subband
                                # it is necessary for plotting
                                #########################
                                this_flagchan_range = [spw_freq[(isubb)*subb_nchan], spw_freq[(isubb+1)*subb_nchan-1]]
                                flagchan_range_phs.append(this_flagchan_range)
                                ###########################

                #######################
                # this string is important and appends the heuristics values for each heuristics
                #######################
                note_platform_phsrms = 'Platform(HighPhaseRMS)'+' '+yesorno+' max phs RMS: '+"%.6f"%(maxvalue)+' degrees'+' subb median RMS: '+"%.6f"%(subb_phs_rms_med)+' degrees'+' ' 
                note_platform_start += note_platform_phsrms
                #######################

                ######################
                # Heuristics 2: find the subband with anomalously large amplitude RMS   
                ######################

                # estimate the median value of the subband RMS by excluding the largest value
                subb_amp_rms_sort = np.sort(subb_amp_rms)
                subb_amp_rms_med = np.nanmedian(subb_amp_rms_sort[:-1])
                subb_amp_sobel_rms_sort = np.sort(subb_amp_sobel_rms)
                subb_amp_sobel_rms_med = np.nanmedian(subb_amp_sobel_rms_sort[:-1])

                ######################
                # string that indicates the detection of platform "yes" or "no"
                # maxvalue keeps the maximum heuristics value
                ######################
                yesorno = 'NO'
                maxvalue = -999
                for isubb in range(subb_num):
                    ###########################
                    # Do atmospheric modeling and find
                    # 1. the absorption line peaks and their FWHM
                    # 2. transmission
                    # atmimpact checks whether the subband center frequency is affected by the atmospheric absorption line 
                    # transimpact measure the transmission value and check whether the transmission is less than 30%
                    # It is performed in several places in the code, so ideally it should be isolated as a seperate function
                    ###########################
                    atmimpact = False
                    transimpact = False
                    subb_center_freq = np.mean([spw_freq[(isubb)*subb_nchan], spw_freq[(isubb+1)*subb_nchan-1]])
                    for b, bound in enumerate(bounds):
                        if (subb_center_freq < bound[1] and subb_center_freq > bound[0]):
                            atmimpact=True
                    tid = np.argmin(np.abs(frequency-subb_center_freq))
                    if (transmission[tid] < 0.3):
                        transimpact=True

                    ###################################
                    # Pre-check:
                    # Sobel filtered phase values in a given subband.
                    # 1.if the standard deviation of the Sobel filtered amp is larger than 3x
                    # the median subband RMS of the Sobel filtered amp value
                    # -OR-
                    # 2.if the maximum value of the Sobel filtered amp value is larger than 7x
                    # the median subband RMS of the Sobel filtered amp value,
                    # set check_subb_phs_var="YES"
                    ###################################
                    check_subb_amp_var = 'NO'
                    if (np.nanstd(sobel_amp[(isubb*subb_nchan):((isubb+1)*subb_nchan)])>3.0*subb_amp_sobel_rms_med) or (np.max(np.abs(sobel_amp[(isubb*subb_nchan):((isubb+1)*subb_nchan)]))>7.0*subb_amp_sobel_rms_med):
                        check_subb_amp_var = 'YES'
                    
                    ###################################
                    # Update the maxvalue if the new subb_amp_rms is larger
                    ###################################
                    if maxvalue < subb_amp_rms[isubb]:
                        maxvalue = subb_amp_rms[isubb]
                    
                    ###################################
                    # Now evaluation 
                    # check, 
                    #  1. subband RMS is 5 x larger than the median subband RMS 
                    #  2. subband is not affected by atmospheric absorption and low transmission
                    ###################################                              
                    if ((subb_amp_rms[isubb] > 5.0 * subb_amp_rms_med) and (not atmimpact) and (not transimpact)):
                    ###########################
                    #  Check, the subband is neither of the first and the last subband, and the Sobel filtered RMS pre-check
                    ###########################
                        if (isubb != 0 and isubb != subb_num-1) and (check_subb_amp_var == 'YES'): 
                            yesorno='YES'
                            #########################
                            # This is verbose message, which can be skipped for PL
                            #########################
                            this_note_platform = ' QA0_High_amp_spectral_rms  subband: '+str(isubb)+' Spw '+str(ispw)+' Ant '+iant+'  P:'+str(ipol)+' BB:'+' TBD'+'  '+ "%.2f"%(subb_amp_rms[isubb]) + 'amp ('+"%.2f" %(subb_amp_rms[isubb]/subb_amp_rms_med)+'sigma)'
                            note_platform += (this_note_platform+'\n')
                            add_spw_failure(spws_affected, ispw, iant, FailureType.AMP)
                            #########################

                            #########################
                            # This list contains the frequency range of the affected subband
                            # it is necessary for plotting
                            #########################
                            this_flagchan_range=[spw_freq[(isubb)*subb_nchan], spw_freq[(isubb+1)*subb_nchan-1]]
                            flagchan_range_amp.append(this_flagchan_range)
                            #########################
                    
                        #############################
                        # Check, the subband is either the first or the last subband
                        #############################
                        elif (isubb == 0 or isubb == subb_num-1):
                            ############################
                            # Check if the standard deviation of the Sobel filtered value is 10 x larger than
                            # the median value of the subbands with the Sobel filtered amp value
                            ############################
                            if (np.nanstd(sobel_amp[(isubb*subb_nchan):((isubb+1)*subb_nchan)])>10.0*subb_amp_sobel_rms_med):
                                yesorno = 'YES'
                                ###########################
                                # This verbose message, which can be skipped for PL
                                ###########################
                                this_note_platform = ' QA0_High_amp_spectral_rms  subband: '+str(isubb)+' Spw '+str(ispw)+' Ant '+iant+'  P:'+str(ipol)+' BB:'+' TBD'+'  '+ "%.2f"%(subb_amp_rms[isubb]) + 'amp ('+"%.2f" %(subb_amp_rms[isubb]/subb_amp_rms_med)+'sigma)'
                                note_platform += (this_note_platform+'\n')
                                add_spw_failure(spws_affected, ispw, iant, FailureType.AMP)
                                #########################

                                #########################
                                # This list contains the frequency range of the affected subband
                                # It is necessary for plotting
                                #########################
                                this_flagchan_range = [spw_freq[(isubb)*subb_nchan], spw_freq[(isubb+1)*subb_nchan-1]]
                                flagchan_range_amp.append(this_flagchan_range)
                                ######################### 

                #######################
                # This string is important and appends the heuristics values for each heuristics
                #######################
                note_platform_amprms = 'Platform(HighAmplitudeRMS)'+' '+yesorno+' max amp RMS: '+"%.6f"%(maxvalue)+' amp'+' subb median RMS: '+"%.6f"%(subb_amp_rms_med)+ ' amp'+' ' 
                note_platform_start += note_platform_amprms
                #######################

                ######################
                # Heuristics 3: find the subband with anomalously large phase offset
                # Each subband is compared against the two adjacent subbands, using 
                # several thresholds below
                ######################
                
                bp_jump_sigma = 3.0     # jump threshold for 2,...,N-1 th subbands
                bp_jump_sigma2 = 6.0    # jump threshold for the first and the last subband
                ch_step_sigma = 3.0     # step threshold at the border of two subbands

                ######################
                # Variables with string and numerical values of heuristics
                ######################
                yesorno = 'NO'
                maxvalue = -999
                maxvalue_ch = -999
                ######################
                
                #######################
                # The first and the second subband are evaluated separately if the total number of subband is >3
                #######################
                if subb_num > 3:
                    ########################### 
                    # The first subband
                    ###########################
                    ###########################
                    # Do atmospheric modeling and find
                    # 1. the absorption line peaks and their FWHM
                    # 2. transmission 
                    # atmimpact checks whether the subband center frequency is affected by the atmospheric absorption line 
                    # transimpact measure the transmission value and check whether the transmission is less than 30%
                    # It is performed in several places in the code, so ideally it should be isolated as a seperate function
                    ###########################

                    atmimpact = False
                    transimpact = False
                    subb_center_freq = np.mean([spw_freq[(0)*subb_nchan], spw_freq[(1)*subb_nchan-1]])
                    for b, bound in enumerate(bounds):
                        if (subb_center_freq < bound[1] and subb_center_freq > bound[0]):
                            atmimpact = True
                    tid = np.argmin(np.abs(frequency-subb_center_freq))
                    if (transmission[tid] < 0.3):
                        transimpact=True

                    ###########################
                    # measure the phase jump for the first subband
                    # and save the measurement into maxvalue if it is larger 
                    # than the current measurement
                    ###########################
                    subb_jump = abs((subb_phs[1]+subb_phs[2])/2.0 - subb_phs[0])    # jump of the first subband
                    if maxvalue < subb_jump:
                        maxvalue = subb_jump

                    ##########################
                    # measure the phase step between the first and the second subband
                    # and save the measurement into maxvalue_ch if it is larger 
                    # than the current measurement
                    ##########################
                    ishift = 1
                    ch_step = abs(np.nanmedian(bp_phs[((0+1)*subb_nchan-1):((0+1)*subb_nchan)]) - np.nanmedian(bp_phs[((0+1)*subb_nchan):((0+1)*subb_nchan+1)]))
                    while np.isnan(ch_step) and ishift < subb_nchan:
                        ch_step = abs(np.nanmedian(bp_phs[((0+1)*subb_nchan-ishift):((0+1)*subb_nchan)]) - np.nanmedian(bp_phs[((0+1)*subb_nchan):((0+1)*subb_nchan+ishift)]))
                        ishift += 1

                    if maxvalue_ch < ch_step:
                        maxvalue_ch = ch_step

                    ##########################
                    # check if the subband jump and subband step is larger than the threshold 
                    #       and if the subband is not affected by low transmission
                    ##########################
                    checkif = False
                    if subb_jump > bp_jump_sigma2 * bp_phs_rms and subb_jump > 5.0 and ch_step > ch_step_sigma * bp_phs_rms and (not transimpact):    # platform offset AND step too large
                        checkif = True

                    if checkif:
                        yesorno = 'YES'
                        #########################
                        # this is verbose message, which can be skipped for PL
                        #########################
                        freq_max = (spw_freq[0*subb_nchan])  # GHz
                        this_note_platform = ' QA0_Platforming  phase  subband : ' + str(0) +'Spw '+str(ispw)+' Ant '+iant+'  '+"%9.6f"%freq_max + ' GHz   P'+str(ipol)+' BB'+'TBD'+' ' +"%.1f" %(subb_jump/bp_phs_rms)+ ' ' +"%.1f" %(ch_step/bp_phs_rms)+'sigma   '+ "%.1f" %(subb_jump) +' degrees'
                        note_platform += (this_note_platform+'\n')
                        add_spw_failure(spws_affected, ispw, iant, FailureType.PHASE)
                        #########################
                        # this list contains the frequency range of the affected subband
                        # it is necessary for plotting
                        #########################
                        this_flagchan_range = [spw_freq[0*subb_nchan], spw_freq[(1)*subb_nchan-1]]
                        flagchan_range_phs.append(this_flagchan_range)
                    
                    #############################
                    # The last subband
                    #############################
                    ###########################
                    # Do atmospheric modeling and find
                    # 1. the absorption line peaks and their FWHM
                    # 2. transmission 
                    # atmimpact checks whether the subband center frequency is affected by the atmospheric absorption line 
                    # transimpact measure the transmission value and check whether the transmission is less than 30%
                    # It is performed in several places in the code, so ideally it should be isolated as a seperate function
                    ###########################
                
                    atmimpact = False
                    transimpact = False
                    subb_center_freq = np.mean([spw_freq[(subb_num-2)*subb_nchan], spw_freq[(subb_num-1)*subb_nchan-1]])
                    for b, bound in enumerate(bounds):
                        if (subb_center_freq < bound[1] and subb_center_freq > bound[0]):
                            atmimpact = True
                    tid = np.argmin(np.abs(frequency-subb_center_freq))
                    if (transmission[tid] < 0.3):
                        transimpact=True
                    ###########################
                    
                    ###########################
                    # measure the phase jump for the last subband
                    # and save the measurement into maxvalue if it is larger 
                    # than the current measurement
                    ###########################
                    subb_jump = abs((subb_phs[subb_num-3]+subb_phs[subb_num-2])/2.0 - subb_phs[subb_num-1])    # jump of the last subband
                    if maxvalue < subb_jump:
                        maxvalue = subb_jump
                    
                    ##########################
                    # measure the phase step between the N and N-1 th subband
                    # and save the measurement into maxvalue_ch if it is larger 
                    # than the current measurement
                    ##########################
                    ishift = 1
                    ch_step = abs(np.nanmedian(bp_phs[((subb_num-2)*subb_nchan-1):((subb_num-2)*subb_nchan)]) - np.nanmedian(bp_phs[((subb_num-2)*subb_nchan):((subb_num-2)*subb_nchan+1)]))
                    while np.isnan(ch_step) and ishift<subb_nchan:
                        ch_step = abs(np.nanmedian(bp_phs[((subb_num-2)*subb_nchan-ishift):((subb_num-2)*subb_nchan)]) - np.nanmedian(bp_phs[((subb_num-2)*subb_nchan):((subb_num-2)*subb_nchan+ishift)]))
                        ishift += 1
                    
                    if maxvalue_ch < ch_step:
                        maxvalue_ch = ch_step
                
                    ##########################
                    # check if the subband jump and subband step is larger than the threshold 
                    #       and if the subband is not affected by low transmission
                    ##########################

                    checkif = False
                    if subb_jump > bp_jump_sigma2 * bp_phs_rms and subb_jump > 5.0 and ch_step > ch_step_sigma * bp_phs_rms and (not transimpact):    # platform step too large
                        checkif = True

                    if checkif:
                        yesorno='YES'
                        
                        #########################
                        # this is verbose message, which can be skipped for PL
                        #########################
                        freq_max=(spw_freq[(subb_num-1)*subb_nchan])  # GHz
                        this_note_platform = ' QA0_Platforming  phase  subband : ' + str(subb_num-1) +'Spw '+str(ispw)+' Ant '+iant+'  '+"%9.6f"%freq_max + ' GHz   P'+str(ipol)+' BB'+'TBD'+' ' +"%.1f" %(subb_jump/bp_phs_rms)+ ' ' +"%.1f" %(ch_step/bp_phs_rms)+'sigma   '+ "%.1f" %(subb_jump) +' degrees'
                        note_platform += (this_note_platform+'\n')
                        add_spw_failure(spws_affected, ispw, iant, FailureType.PHASE)
                        
                        #########################
                        # this list contains the frequency range of the affected subband
                        # it is necessary for plotting
                        #########################
                        this_flagchan_range=[spw_freq[(subb_num-2)*subb_nchan], spw_freq[(subb_num-1)*subb_nchan-1]]
                        flagchan_range_phs.append(this_flagchan_range)

                ###########################
                # From the 2nd to Nth subband
                ###########################

                for isubb in range(1, subb_num - 1):
                    ###########################
                    # Do atmospheric modeling and find
                    # 1. the absorption line peaks and their FWHM
                    # 2. transmission 
                    # atmimpact checks whether the subband center frequency is affected by the atmospheric absorption line 
                    # transimpact measure the transmission value and check whether the transmission is less than 30%
                    # It is performed in several places in the code, so ideally it should be isolated as a seperate function
                    ###########################
                    atmimpact = False
                    transimpact = False
                    subb_center_freq = np.mean([spw_freq[(isubb) * subb_nchan], spw_freq[(isubb + 1) * subb_nchan - 1]])
                    for b, bound in enumerate(bounds):
                        if (subb_center_freq < bound[1] and subb_center_freq > bound[0]):
                            atmimpact = True
                    tid = np.argmin(np.abs(frequency-subb_center_freq))
                    if (transmission[tid] < 0.3):
                        transimpact = True

                    ###########################
                    # measure the phase jump for the given subband
                    # and save the measurement into maxvalue if it is larger 
                    # than the current measurement
                    ###########################

                    subb_jump = abs((subb_phs[isubb-1]+subb_phs[isubb+1])/2.0 - subb_phs[isubb])    # jump of this subband
                    if maxvalue < subb_jump:
                        maxvalue = subb_jump
                    
                    ##########################
                    # measure the phase step at the edge of subband (left and right)
                    # and save the measurement into maxvalue_ch (left) and maxvalue_ch1 (right) 
                    # if they are larger than the current measurement
                    ##########################
                    ishift = 1
                    ch_step = abs(np.nanmedian(bp_phs[(isubb*subb_nchan-1):(isubb*subb_nchan)]) - np.nanmedian(bp_phs[(isubb*subb_nchan):(isubb*subb_nchan+1)]))
                    while np.isnan(ch_step) and ishift<subb_nchan:
                        ch_step = abs(np.nanmedian(bp_phs[(isubb*subb_nchan-ishift):(isubb*subb_nchan)]) - np.nanmedian(bp_phs[(isubb*subb_nchan):(isubb*subb_nchan+ishift)]))
                        ishift += 1

                    ishift = 1
                    ch_step1 = abs(np.nanmedian(bp_phs[((isubb+1)*subb_nchan-1):((isubb+1)*subb_nchan)]) - np.nanmedian(bp_phs[((isubb+1)*subb_nchan):((isubb+1)*subb_nchan+1)]))
                    while np.isnan(ch_step1) and ishift < subb_nchan:
                        ch_step1 = abs(np.nanmedian(bp_phs[((isubb+1)*subb_nchan-ishift):((isubb+1)*subb_nchan)]) - np.nanmedian(bp_phs[((isubb+1)*subb_nchan):((isubb+1)*subb_nchan+ishift)]))
                        ishift += 1

                    if maxvalue_ch < np.max([ch_step,ch_step1]):
                        maxvalue_ch = np.max([ch_step,ch_step1])
                    ###########################

                    ##########################
                    # check if the subband jump and subband step are larger than the threshold 
                    #       and if the subband is not affected by low transmission
                    ##########################
                    checkif = False

                    if subb_jump > bp_jump_sigma * bp_phs_rms and subb_jump > 5.0 and ch_step > ch_step_sigma * bp_phs_rms and ch_step1 > ch_step_sigma*bp_phs_rms and (not transimpact):    # platform offset AND step too large
                        checkif = True

                    if checkif:  # platform offset AND step too large
                        yesorno = 'YES'
                        #########################
                        # this is verbose message, which can be skipped for PL
                        #########################
                        freq_max = (spw_freq[isubb*subb_nchan])  # GHz
                        this_note_platform = ' QA0_Platforming  phase  subband : ' + str(isubb) +'Spw '+str(ispw)+' Ant '+iant+'  '+"%9.6f"%freq_max + ' GHz   P'+str(ipol)+' BB'+'TBD'+' ' +"%.1f" %(subb_jump/bp_phs_rms)+ ' ' +"%.1f" %(ch_step/bp_phs_rms)+'sigma   '+ "%.1f" %(subb_jump) +' degrees'
                        note_platform += (this_note_platform+'\n')
                        add_spw_failure(spws_affected, ispw, iant, FailureType.PHASE)

                        #########################
                        # this list contains the frequency range of the affected subband
                        # it is necessary for plotting
                        #########################
                        this_flagchan_range = [spw_freq[isubb*subb_nchan], spw_freq[(isubb+1)*subb_nchan-1]]
                        flagchan_range_phs.append(this_flagchan_range)
                
                #######################
                # this string is important and appends the heuristics values for each heuristics
                #######################
                note_platform_phsjump = 'Platform(PhaseJump)'+' '+yesorno+' max phs Jump: '+"%.6f"%(maxvalue)+' degree'+' max phs Step: '+"%.6f"%(maxvalue_ch)+' degree'+'  subb diff RMS: '+"%.6f"%(bp_phs_rms)+ ' degree'+' ' 
                note_platform_start += note_platform_phsjump
                #######################

                ######################
                # Heuristics 4: find the subband with anomalously large amp offset
                # Each subband is compared against the two adjacent subbands, using 
                # several thresholds below
                #
                # Heuristics 5: find the subband with anomalously large amp spike at edge
                # The first and the last subband are not evaluated
                # Each subband is compared against the two adjacent subbands, using 
                # several thresholds below
                ######################

                bp_jump_sigma = 3.0     # jump threshold for 2,...,N-1 th subbands
                bp_jump_sigma2 = 6.0    # jump threshold for the first and the last subband
                ch_step_sigma = 5.0     # step threshold at the border of two subbands
                spk_step_sigma = 6.0    

                ######################
                # variables with string and numerical values of heuristics 
                ######################
                yesorno = 'NO'
                maxvalue = -999
                maxvalue_ch = -999
                subb_spike = -999
                subb_base = -999

                #######################
                # The first and the second subband are evaluated separately if the total number of subband is >3
                #######################
                if subb_num > 3:
                    ########################### 
                    # The first subband
                    ###########################
                    ###########################
                    # Do atmospheric modeling and find
                    # 1. the absorption line peaks and their FWHM
                    # 2. transmission 
                    # atmimpact checks whether the subband center frequency is affected by the atmospheric absorption line 
                    # transimpact measure the transmission value and check whether the transmission is less than 30%
                    # It is performed in several places in the code, so ideally it should be isolated as a seperate function
                    ###########################

                    atmimpact = False
                    transimpact = False
                    subb_center_freq = np.mean([spw_freq[(0)*subb_nchan], spw_freq[(1)*subb_nchan-1]])
                    for b, bound in enumerate(bounds):
                        if (subb_center_freq < bound[1] and subb_center_freq > bound[0]):
                            atmimpact = True
                    tid = np.argmin(np.abs(frequency-subb_center_freq))
                    if (transmission[tid] < 0.3):
                        transimpact = True

                    ###########################
                    # measure the amp jump for the first subband
                    # and save the measurement into maxvalue if it is larger 
                    # than the current measurement
                    ###########################

                    subb_jump = abs((subb_amp[1]+subb_amp[2])/2.0 - subb_amp[0])    # step or offset of the first subband
                    if maxvalue < subb_jump:
                        maxvalue = subb_jump
                    
                    ##########################
                    # measure the amp step between the first and the second subband
                    # and save the measurement into maxvalue_ch if it is larger 
                    # than the current measurement
                    ##########################

                    ishift = 1
                    ch_step = abs(np.nanmedian(bp_amp[((0+1)*subb_nchan-1):((0+1)*subb_nchan)]) - np.nanmedian(bp_amp[((0+1)*subb_nchan):((0+1)*subb_nchan+1)]))
                    
                    while np.isnan(ch_step) and ishift < subb_nchan:
                        ch_step = abs(np.nanmedian(bp_amp[((0+1)*subb_nchan-ishift):((0+1)*subb_nchan)]) - np.nanmedian(bp_amp[((0+1)*subb_nchan):((0+1)*subb_nchan+ishift)]))
                        ishift += 1

                    if maxvalue_ch < ch_step:
                        maxvalue_ch = ch_step

                    ##########################
                    # check if the subband jump and subband step is larger than the threshold 
                    #       and if the subband is not affected by low transmission
                    ##########################

                    checkif = False
                    if subb_jump > bp_jump_sigma2 * bp_amp_rms and ch_step > ch_step_sigma * bp_amp_rms and (not transimpact):    # platform offset AND step too large
                        checkif = True

                    if checkif:
                        yesorno = 'YES'
                        #########################
                        # this is verbose message, which can be skipped for PL
                        #########################
                        freq_max = (spw_freq[0*subb_nchan])  # GHz
                        this_note_platform = ' QA0_Platforming  amplitude subband: ' + str(0) +' Spw '+str(ispw)+' Ant '+iant+'  '+"%9.6f"%freq_max + ' GHz   P: '+str(ipol)+' BB:'+' TBD'+ \
                                            ' sigmas: ' +"%.1f"%(subb_jump/bp_amp_rms)+ ' '+"%.1f"%(ch_step/bp_amp_rms)
                        note_platform += (this_note_platform+'\n')
                        add_spw_failure(spws_affected, ispw, iant, FailureType.AMP)

                        #########################
                        # this list contains the frequency range of the affected subband
                        # it is necessary for plotting
                        #########################                                  
                        this_flagchan_range = [spw_freq[0*subb_nchan], spw_freq[(0+1)*subb_nchan-1]]
                        flagchan_range_amp.append(this_flagchan_range)

                    ########################### 
                    # The last subband
                    ###########################
                    ###########################
                    # Do atmospheric modeling and find
                    # 1. the absorption line peaks and their FWHM
                    # 2. transmission 
                    # atmimpact checks whether the subband center frequency is affected by the atmospheric absorption line 
                    # transimpact measure the transmission value and check whether the transmission is less than 30%
                    # It is performed in several places in the code, so ideally it should be isolated as a seperate function
                    ###########################
                    atmimpact = False
                    transimpact = False
                    subb_center_freq = np.mean([spw_freq[(subb_num-2)*subb_nchan], spw_freq[(subb_num-1)*subb_nchan-1]])
                    for b, bound in enumerate(bounds):
                        if (subb_center_freq < bound[1] and subb_center_freq > bound[0]):
                            atmimpact = True
                    tid = np.argmin(np.abs(frequency-subb_center_freq))
                    if (transmission[tid] < 0.3):
                        transimpact = True
                    ###########################

                    ###########################
                    # measure the amp jump for the last subband
                    # and save the measurement into maxvalue if it is larger
                    # than the current measurement
                    ###########################
                    subb_jump = abs((subb_amp[subb_num-3] + subb_amp[subb_num-2])/2.0 - subb_amp[subb_num-1])    # step or offset of the first subband
                    if maxvalue < subb_jump:
                        maxvalue = subb_jump
                    
                    ##########################
                    # measure the phase step between the N and N-1 th subband
                    # and save the measurement into maxvalue_ch if it is larger 
                    # than the current measurement
                    ##########################
                    ishift = 1
                    ch_step = abs(np.nanmedian(bp_amp[((subb_num-2)*subb_nchan-1):((subb_num-2)*subb_nchan)]) - np.nanmedian(bp_amp[((subb_num-2)*subb_nchan):((subb_num-2)*subb_nchan+1)]))
                    while np.isnan(ch_step) and ishift<subb_nchan:
                        ch_step = abs(np.nanmedian(bp_amp[((subb_num-2)*subb_nchan-ishift):((subb_num-2)*subb_nchan)]) - np.nanmedian(bp_amp[((subb_num-2)*subb_nchan):((subb_num-2)*subb_nchan+ishift)]))
                        ishift +=1
                    if maxvalue_ch < ch_step:
                        maxvalue_ch = ch_step

                    ##########################
                    # check if the subband jump and subband step is larger than the threshold 
                    #       and if the subband is not affected by low transmission
                    ##########################
                    checkif = False
                    if subb_jump > bp_jump_sigma2 * bp_amp_rms and ch_step > ch_step_sigma * bp_amp_rms and (not transimpact):    # platform offset AND step too large
                        checkif = True

                    if checkif:
                        yesorno = 'YES'

                        #########################
                        # this is verbose message, which can be skipped for PL
                        #########################
                        freq_max = (spw_freq[(subb_num-1) * subb_nchan])  # GHz
                        this_note_platform = ' QA0_Platforming  amplitude subband: ' + str(subb_num-1) +' Spw '+str(ispw)+' Ant '+iant+'  '+"%9.6f"%freq_max + ' GHz   P: '+str(ipol)+' BB:'+' TBD'+ \
                                            ' sigmas: ' +"%.1f"%(subb_jump/bp_amp_rms)+ ' '+"%.1f"%(ch_step/bp_amp_rms)
                        note_platform += (this_note_platform+'\n')
                        add_spw_failure(spws_affected, ispw, iant, FailureType.AMP)

                        #########################
                        # this list contains the frequency range of the affected subband
                        # it is necessary for plotting
                        #########################
                        this_flagchan_range=[spw_freq[(subb_num-2)*subb_nchan], spw_freq[(subb_num-1)*subb_nchan-1]]
                        flagchan_range_amp.append(this_flagchan_range)

                ########################### 
                # From the 2nd to Nth subband
                # Additionally, we also evaluate anomalous spikes in the subband
                ###########################
                countsubspike=0
                for isubb in range(1, subb_num-1):
                    ###########################
                    # Do atmospheric modeling and find
                    # 1. the absorption line peaks and their FWHM
                    # 2. transmission 
                    # atmimpact checks whether the subband center frequency is affected by the atmospheric absorption line 
                    # transimpact measure the transmission value and check whether the transmission is less than 30%
                    # It is performed in several places in the code, so ideally it should be isolated as a seperate function
                    ###########################
                    atmimpact = False
                    transimpact = False
                    subb_center_freq = np.mean([spw_freq[(isubb)*subb_nchan], spw_freq[(isubb+1)*subb_nchan-1]])
                    for b, bound in enumerate(bounds):
                        if (subb_center_freq < bound[1] and subb_center_freq > bound[0]):
                            atmimpact = True
                    tid = np.argmin(np.abs(frequency-subb_center_freq))
                    if (transmission[tid] < 0.3):
                        transimpact = True
                    
                    ###########################
                    # measure the phase jump for the given subband
                    # and save the measurement into maxvalue if it is larger 
                    # than the current measurement
                    ###########################

                    subb_jump = abs((subb_amp[isubb-1]+subb_amp[isubb+1])/2.0 - subb_amp[isubb])    # step or offset of this subband
                    if maxvalue < subb_jump:
                        maxvalue = subb_jump

                    ##########################
                    # measure the phase step at the edge of subband (left and right)
                    # and save the measurement into maxvalue_ch (left) and maxvalue_ch1 (right) 
                    # if they are larger than the current measurement
                    ##########################
                    ishift = 1
                    ch_step = np.nanmean(bp_amp[(isubb*subb_nchan-ishift):(isubb*subb_nchan)]) - np.nanmean(bp_amp[(isubb*subb_nchan):(isubb*subb_nchan+ishift)])
                    while np.isnan(ch_step) and ishift<subb_nchan:
                        ch_step = np.nanmean(bp_amp[(isubb*subb_nchan-ishift):(isubb*subb_nchan)]) - np.nanmean(bp_amp[(isubb*subb_nchan):(isubb*subb_nchan+ishift)])   # start of subband
                        ishift += 1
                    
                    ishift = 1
                    ch_step1 = np.nanmean(bp_amp[((isubb+1)*subb_nchan-ishift):((isubb+1)*subb_nchan)]) - np.nanmean(bp_amp[((isubb+1)*subb_nchan):((isubb+1)*subb_nchan+ishift)])
                    while np.isnan(ch_step1) and ishift<subb_nchan:
                        ch_step1 = np.nanmean(bp_amp[((isubb+1)*subb_nchan-ishift):((isubb+1)*subb_nchan)]) - np.nanmean(bp_amp[((isubb+1)*subb_nchan):((isubb+1)*subb_nchan+ishift)])   # start of subband
                        ishift += 1

                    if maxvalue_ch < np.max([ch_step,ch_step1]):
                        maxvalue_ch=np.max([ch_step,ch_step1])
                    ###########################

                    ###########################
                    # measure a spike for the given subband
                    # and count it if the spike is significant
                    ###########################

                    # Spectral channel segment for spike estimate
                    ishift_spk = np.max([int(subb_nchan * 0.3), 1])
                    left = np.nanmean(bp_amp[isubb * subb_nchan - 2 * ishift_spk:isubb * subb_nchan - ishift_spk])
                    right = np.nanmean(bp_amp[isubb * subb_nchan + ishift_spk:isubb * subb_nchan + 2 * ishift_spk])

                    if (isubb * subb_nchan) - ishift_spk < 0:
                        LOG.info(f"Falling back to 0 for lower index in spike detection array in correlator subband QA metrics for MS: {vis} ant: {iant} spw: {ispw} pol: {ipol}")

                    lower_index = max(0, isubb * subb_nchan - ishift_spk)

                    if (isubb * subb_nchan) + ishift_spk > len(bp_amp) - 1:
                        LOG.info(f"Falling back to (length - 1) for upper index in spike detection array in correlator subband QA metrics for MS: {vis} ant: {iant} spw: {ispw} pol: {ipol}")
    
                    upper_index = min(isubb * subb_nchan + ishift_spk, len(bp_amp) - 1)

                    if lower_index >= upper_index:
                        LOG.warning(f"Not evaluating remaining correlator subband QA metrics for MS: {vis} ant: {iant} spw: {ispw} pol: {ipol} due to invalid slice bounds.")
                        break

                    subb_spk = np.abs(np.nanmean([left,right]) - bp_amp[lower_index:upper_index])
                    subb_spkmax_id = np.argmax(subb_spk)
                    spk_step = subb_spk[subb_spkmax_id]

                    if subb_spike < abs(spk_step):
                        subb_spike = abs(spk_step)
                        subb_base = abs(np.nanmean([left,right]))
                    
                    ##########################
                    # if the spike channel is within atmospheric absorption band,
                    # we consider that this is not a genuine spike
                    ##########################
                    spk_atmimpact = False
                    for b, bound in enumerate(bounds):
                        if (spw_freq[subb_spkmax_id+isubb*subb_nchan-ishift_spk] < bound[1] and spw_freq[subb_spkmax_id+isubb*subb_nchan-ishift_spk] > bound[0]):
                            spk_atmimpact = True

                    if (abs(spk_step)>0.1*np.nanmean([left,right])) and (abs(spk_step) > spk_step_sigma*bp_amp_rms) and (not spk_atmimpact) and (not transimpact):
                        countsubspike += 1

                        #########################
                        # this is verbose message, which can be skipped for PL
                        #########################
                        freq1_max = (spw_freq[subb_spkmax_id+isubb*subb_nchan-ishift_spk])  # GHz
                        this_note_platform = ' QA0_Platforming  amp subband spike: ' + str(isubb) +' Spw '+str(ispw)+' Ant '+iant+'  '+"%9.6f"%freq1_max +'GHz  P: '+str(ipol)+' BB:'+' TBD'+ \
                                            ' sigmas: ' +"%.1f"%(subb_jump/bp_amp_rms)+ ' '+"%.1f"%(spk_step/bp_amp_rms)
                        note_platform += (this_note_platform+'\n')
                        add_spw_failure(spws_affected, ispw, iant, FailureType.AMP)

                        #########################
                        # this list contains the frequency range of the affected subband
                        # it is necessary for plotting
                        #########################
                        this_flagchan_range1 = [spw_freq[subb_spkmax_id+isubb*subb_nchan-1-ishift_spk], spw_freq[subb_spkmax_id+isubb*subb_nchan+1-ishift_spk]]
                        flagchan_range_amp.append(this_flagchan_range1)

                    #############################
                    
                    ##########################
                    # check if the subband jump and subband step are larger than the threshold 
                    #       and if the subband is not affected by low transmission
                    ##########################
                    checkif=False
                    if (subb_jump > bp_jump_sigma * bp_amp_rms and abs(ch_step) > ch_step_sigma*bp_amp_rms and abs(ch_step1) > ch_step_sigma*bp_amp_rms and np.sign(ch_step) == -np.sign(ch_step1) and (not transimpact)):
                        checkif = True

                    if checkif:
                        yesorno='YES'
                        freq_max=(spw_freq[isubb*subb_nchan])  # GHz
                        this_note_platform = ' QA0_Platforming  amplitude subband: ' + str(isubb) +' Spw '+str(ispw)+' Ant '+iant+'  '+"%9.6f"%freq_max + ' GHz   P: '+str(ipol)+' BB:'+' TBD'+ \
                                            ' sigmas: ' +"%.1f"%(subb_jump/bp_amp_rms)+ ' '+"%.1f"%(ch_step/bp_amp_rms)+ ' ' +"%.1f"%(ch_step1/bp_amp_rms)
                        note_platform += (this_note_platform+'\n')
                        this_flagchan_range=[spw_freq[isubb*subb_nchan], spw_freq[(isubb+1)*subb_nchan-1]]
                        flagchan_range_amp.append(this_flagchan_range)
                        add_spw_failure(spws_affected, ispw, iant, FailureType.AMP)

                #######################
                # this string is important and appends the heuristics values for each heuristics
                #######################
                note_platform_ampjump = 'Platform(AmplitudeJump)'+' '+yesorno+' max amp Jump: '+"%.6f"%(maxvalue)+' amp'+' max amp Step: '+"%.6f"%(maxvalue_ch)+' amp'+' subb diff RMS: '+"%.6f"%(bp_amp_rms)+ ' amp'+' ' 
                
                ##############################
                # after counting spikes acorss the subband (from 2 to N-1 th subbands)
                # if more then one spikes, we report it
                ##############################
                if countsubspike > 0:
                    note_platform_subbspk = 'Platform(AmpSubbSpike)'+' '+'YES'+' max amp Spike: '+"%.6f"%(subb_spike)+' amp'+' subb base: '+"%.6f"%(subb_base)+ ' amp'+' subb diff RMS: '+"%.6f"%(bp_amp_rms)+' amp'+' '
                else:
                    note_platform_subbspk = 'Platform(AmpSubbSpike)'+' '+'NO'+' max amp Spike: '+"%.6f"%(subb_spike)+' amp'+' subb base: '+"%.6f"%(subb_base)+ ' amp'+' subb diff RMS: '+"%.6f"%(bp_amp_rms)+' amp'+' '
                #############################

                #############################
                # aggregate the verbose note
                #############################
                note_platform_start += note_platform_ampjump
                note_platform_start += note_platform_subbspk
                note_platform_start += '\n'

                note_platform_start_formatted_strings.append(note_platform_start)
                note_platform_formatted_strings.append(note_platform)

                #############################
                # aggregate the outlier note
                #############################
                flag_note_oneline = note_platform_phsrms + note_platform_amprms + note_platform_phsjump + note_platform_ampjump + note_platform_subbspk

                ############################
                # creating the flagging command
                # if there is at least one "YES" in the outlier note
                ############################
                if 'YES' in flag_note_oneline:
                    flagnote += "# mode='manual' antenna='"+iant+"' spw='"+str(ispw)+"' pol='"+str(ipol)+"' reason='BP platforming'"+"\n"
                    flagnote_formatted_strings.append(flagnote)

            #######################
            # plotting
            #######################
            freq_range=np.max(spw_freq)-np.min(spw_freq)
            margin=freq_range*0.05
            if ipol==0:
                amp_range=np.max(bp_amp2)-np.min(bp_amp2)
                amargin=amp_range*0.1
                transmission2=(transmission-1.0)*0.1+np.max(bp_amp2)+amargin
                pcolor='blue'
                ax1.plot(spw_freq,bp_amp2,color=pcolor)
                ax1.plot(spw_freq,transmission2,color='black',alpha=0.5)
                ax1.set_ylabel('amplitude')
                ax1.set_xlabel('frequency [GHz]')
                ax1.set_xlim(np.min(spw_freq)-margin,np.max(spw_freq)+margin)
                if (len(flagchan_range_amp)>0):
                    for p in range(len(flagchan_range_amp)):
                        ax1.hlines(y=np.max(bp_amp2)*1.05,xmin=flagchan_range_amp[p][0], xmax=flagchan_range_amp[p][1],color='black', linewidth=4)
                        ax1.axvspan(flagchan_range_amp[p][0], flagchan_range_amp[p][1],color='black', alpha=0.4)
                ax3.plot(spw_freq,bp_phs2,color=pcolor)
                ax3.set_ylabel('degree')
                ax3.set_xlabel('frequency [GHz]')
                ax3.set_xlim(np.min(spw_freq)-margin,np.max(spw_freq)+margin)
                if (len(flagchan_range_phs)>0):
                    for p in range(len(flagchan_range_phs)):
                        ax3.hlines(y=np.max(bp_phs2)*1.05,xmin=flagchan_range_phs[p][0], xmax=flagchan_range_phs[p][1],color='black', linewidth=4)
                        ax3.axvspan(flagchan_range_phs[p][0], flagchan_range_phs[p][1],color='black', alpha=0.4)

            else:
                amp_range=np.max(bp_amp2)-np.min(bp_amp2)
                amargin=amp_range*0.1
                transmission2=(transmission-1.0)*0.1+np.max(bp_amp2)+amargin
                pcolor='green'
                ax2.plot(spw_freq,bp_amp2,color=pcolor)
                ax2.plot(spw_freq,transmission2,color='black',alpha=0.5)
                ax2.set_ylabel('amplitude')
                ax2.set_xlabel('frequency [GHz]')
                ax2.set_xlim(np.min(spw_freq)-margin,np.max(spw_freq)+margin)
                if (len(flagchan_range_amp)>0):
                    for p in range(len(flagchan_range_amp)):
                        ax2.hlines(y=np.max(bp_amp2)*1.05,xmin=flagchan_range_amp[p][0], xmax=flagchan_range_amp[p][1],color='black', linewidth=4)
                        ax2.axvspan(flagchan_range_amp[p][0], flagchan_range_amp[p][1],color='black', alpha=0.4)
                ax4.plot(spw_freq,bp_phs2,color=pcolor)
                ax4.set_ylabel('degree')
                ax4.set_xlabel('frequency [GHz]')
                ax4.set_xlim(np.min(spw_freq)-margin,np.max(spw_freq)+margin)
                if (len(flagchan_range_phs)>0):
                    for p in range(len(flagchan_range_phs)):
                        ax4.hlines(y=np.max(bp_phs2)*1.05,xmin=flagchan_range_phs[p][0], xmax=flagchan_range_phs[p][1],color='black', linewidth=4)
                        ax4.axvspan(flagchan_range_phs[p][0], flagchan_range_phs[p][1],color='black', alpha=0.4)

        plt.savefig(figure_path)
        plt.close()

    # Create the output files
    outfile_name = os.path.join(output_dir, f"{caltable_name}_platform.txt")
    outfile_val_name = os.path.join(output_dir, f"{vis}_platform_value.txt")
    outfile_flag_name = os.path.join(output_dir, f"{vis}_flagging.txt")

    # Write information logged to files
    with open(outfile_name, "w") as outfile:
        outfile.write("\n".join(note_platform_formatted_strings))

    with open(outfile_val_name, "w") as outfile_val:
        outfile_val.write("\n".join(note_platform_start_formatted_strings))

    with open(outfile_flag_name, "w") as outfile_flag:
        outfile_flag.write("\n".join(flagnote_formatted_strings))

    # Reformat and return spws_affected as a dict
    spw_affected_return = {}
    for spw_id, failure in spws_affected.items():
        spw_affected_return[spw_id] = {
            'antennas': sorted(failure.ant_set),  # return sorted list of antennas
            'failure': failure.failure_type.value  # convert enum back to string 
        } 

    return spw_affected_return


def setup_bandpass_dict(ms: MeasurementSet, caltable: str) -> dict:
    """
    Setup the bandpass dict structure used for analysis.

    Args:
        ms: Measurement Set
        caltable: bandpass table

    Returns:
        dict: bandpass dict for  ms and caltable
    """
    # Structure of bandpass_library dict:

    # bandpass_library[myfield][myspw][myant][mypol]['amp']=amp2
    # bandpass_library[key1][key2][key3][key4][key5]
    # key1: reference antenna name and field names
    # key2: spw ID
    # key3: bandwidth, num of channels, frequency, antennas
    # key4: polarization, 0 and 1
    # key5: 'amp'(original data with the PL flag applied, WVR LO checked additionally)
    #       'phase'(original data with the PL flag applied, WVR LO checked additionally)
    #       'amp2' (copy of the original with the PL flag only): not used for the analysis but used for plotting only
    #       'phase2'(copy of the original with the PL flag only): not used for the analyis but used for plotting only 
    #       'flag'
    # Overall structure of the dictionary, for example
    # bandpass_library.keys(['refAnt','J0821+1234','J1234-0234'])
    # bandpass_library['refAnt'] = 'DA41'
    # bandpass_library['J0821+1234'].keys(['17,19,21,23'])
    # bandpass_library['J0821+1234']['19'].keys(['bw','nchan','freq','DA41','DA42',...,])
    # bandpass_library['J0821+1234']['19']['bw']=1.9
    # bandpass_library['J0821+1234']['19']['nchan']=512
    # bandpass_library['J0821+1234']['19']['freq']=[123.122,123.123,123.124,.....,]
    # bandpass_library['J0821+1234']['19']['freq']=[123.122,123.123,123.124,.....,]
    # bandpass_library['J0821+1234']['19']['DA41'].keys([0,1])
    # bandpass_library['J0821+1234']['19']['DA41'][0].keys(['amp','phase','amp2','phase2','flag'])
    # bandpass_library['J0821+1234']['19']['DA41'][0]['amp']=[1.01,0.92,1.03,0.97,...,0.98]
    # bandpass_library['J0821+1234']['19']['DA41'][0]['phase']=[0.15,0.12,0.10,0.23,...,0.23]
    # bandpass_library['J0821+1234']['19']['DA41'][0]['flag']=[0,1,1,....,0]

    bandpass_library = {}

    mytab = pathlib.Path(caltable).name
    with casa_tools.TableReader(caltable) as tb:
        LOG.info(f"Bandpass subband QA, processing table: {mytab}")
        fieldIds, fieldNames, spwIds, antennaNames, antIds, pwv = getInfoFromTable(ms.name, caltable)

        tmp = tb.getcol('ANTENNA2')
        _ = scipy.stats.mode(tmp)
        refAnt = antennaNames[np.bincount(tb.getcol('ANTENNA2')).argmax()]
        bandpass_library['RefAnt'] = refAnt

        # Check bandwidth and nchan
        spw_bandwidth = science_spw_bandwidths(ms)

        for j, myfield in enumerate(fieldNames):
            myfieldid = fieldIds[j]
            bandpass_library[myfield] = {}

            for m, myspw in enumerate(spwIds):
                bandpass_library[myfield][myspw] = {}
                spw_nchan = caltable_tools.nchan_from_caltable(caltable, myspw)
                spw_freq = caltable_tools.chan_freq_from_caltable(caltable, myspw)  # GHz
                bandpass_library[myfield][myspw]['bw'] = spw_bandwidth[myspw]
                bandpass_library[myfield][myspw]['nchan'] = spw_nchan
                bandpass_library[myfield][myspw]['freq'] = spw_freq

                for k, myant in enumerate(antennaNames):
                    bandpass_library[myfield][myspw][myant] = {}
                    myantid = antIds[k]
                    mytb = tb.query('FIELD_ID == ' + str(myfieldid) + ' AND SPECTRAL_WINDOW_ID == ' + str(myspw) + ' AND ANTENNA1 == '+str(myantid))
                    gain = mytb.getcol('CPARAM')
                    flag = mytb.getcol('FLAG')

                    for mypol in range(len(gain)):
                        bandpass_library[myfield][myspw][myant][mypol] = {}
                        phase = np.angle(gain[mypol])
                        phase = np.unwrap(phase)
                        deg = np.degrees(phase)
                        amp = np.absolute(gain[mypol])
                        amp2 = np.copy(amp)
                        deg2 = np.copy(deg)
                        myflag = flag[mypol]
                        idx = np.where(myflag == True)[0]
                        for myid in range(len(myflag)):
                            if (myid in idx):
                                amp2[myid] = np.nan
                                deg2[myid] = np.nan

                        amp3 = np.copy(amp2)
                        deg3 = np.copy(deg2)

                        for ifreq, lofreq in enumerate(WVR_LO):
                            freq1 = lofreq - 62.5/1000.0/2.0
                            freq2 = lofreq + 62.5/1000.0/2.0
                            if (np.min(spw_freq) < lofreq and np.max(spw_freq) > lofreq):
                                wvrlo_id = np.where((spw_freq > freq1) & (spw_freq < freq2))[0]
                                amp2[wvrlo_id] = np.nan
                                deg2[wvrlo_id] = np.nan
                        bandpass_library[myfield][myspw][myant][mypol]['amp'] = amp2
                        bandpass_library[myfield][myspw][myant][mypol]['phase'] = deg2
                        bandpass_library[myfield][myspw][myant][mypol]['amp2'] = amp3
                        bandpass_library[myfield][myspw][myant][mypol]['phase2'] = deg3
                        bandpass_library[myfield][myspw][myant][mypol]['flag'] = myflag

    return bandpass_library


def bandpass_platforming(ms: MeasurementSet, caltable) -> dict:
    """
    Evaluate bandpass platforming for each ms and caltable.
    Interface with pipeline.qa.bandpass_platforming.

    Args:
        ms: Measurement Set
        caltable: bandpass table

    Returns:
        dict: bandpass platforming results for each ms and caltable
    """
    # Create the dictionary structure used by the main analysis loop
    bandpass_library = setup_bandpass_dict(ms, caltable)

    # Create output directory for heuristics-related plots and logfiles
    output_dir = "bandpass_subband_qa"
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)

    # Evaluate the bandpass platforming qa heuristics
    spws_affected = evalPerAntBP_Platform(bandpass_library, output_dir, ms, caltable)

    return spws_affected
