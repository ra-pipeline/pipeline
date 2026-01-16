import sys
from typing import List, Tuple, Union
import numpy as np
import re
import glob
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from astropy.nddata import block_reduce
from astropy.time import Time
import matplotlib.dates as mdates
import casatools
import copy

from pipeline.infrastructure.filenamer import sanitize
from . import sd_qa_utils
from . import mswrapper_sd


def show_heat_XYdiff(msw: mswrapper_sd.MSWrapperSD, nchanbin: int = 1, nvisbin: int = 1,
                     zrange: str = '0.9', remove_skylines: bool = False, nchanstdblock: int = 20,
                     plot_output_path: str = '.', colorlist: Union[list, str] = 'auto'):
    """ Show heat map of TP data for Antenna/Spw for a MSWrapperSD object. Object must have the "data"
        and "spw_setup" attributes.
    param:
        msw: MSWrapperSD object with the data to be plotted
        nchanbin (int): Number of channels to bin.
        nvisbin (int): Number of visibilities (integrations) to bin.
        column (str): Column to plot.
        zrange (str): Heat map scale quantile e.g. '0.95' or 'full', 'sym', '-3 24'
        remove_skylines (bool): Whether to mask data around skylines.
        nchanstdblock (int): Size of chunks of data taken to calculate standard deviation of data
                             for sigma plot estimation.
        plot_output_path (str): Path to output plot.
        colorlist (str or list): Either list of colors to use for each Trec curve, or 'auto' to assign
                                 random colors.
    Returns:
        List of filenames of produced plots
    """
    #Turn off interactive plotting
    plt.ioff()

    msname = msw.fname.split('/')[-1]
    #Get channel frequencies
    chan_freq = msw.spw_setup[msw.spw]['chanfreqs']
    #Get antenna ID
    antenna_id = msw.spw_setup['antids'][msw.spw_setup['antnames'] == msw.antenna][0]
    #Get field name
    #fieldname = msw.spw_setup['fieldname']['*OBSERVE_TARGET#ON_SOURCE*'][msw.spw_setup['fieldid']['*OBSERVE_TARGET#ON_SOURCE*'].index(msw.fieldid)]
    fieldname = sanitize(msw.spw_setup['namesfor'][str(msw.fieldid)][0])
    if str(colorlist) == 'auto':
        colorlist = sd_qa_utils.genColorList(len(scanlist))

    #Add string to show options in filename
    if msw.onoffsel == 'BOTH':
        onoffstr = ''
    else:
        onoffstr = '_'+msw.onoffsel+'-source'

    data = copy.deepcopy(msw.data)
    data_outlier2D = copy.deepcopy(msw.outliers)
    data_outlier = copy.deepcopy(msw.outlierfreq)
    weight = copy.deepcopy(msw.weight)
    datatime = copy.deepcopy(msw.time)
    (npol, nchan, nrows) = np.shape(data)
    print('(npol, nchan, nrows): '+str((npol, nchan, nrows)))

    #If science line detected, get the data from the 'all' scans data
    if (msw.data_stats is not None) and ('sci_line_sel' in msw.data_stats.keys()):
        sciline = msw.data_stats['sci_line_sel']
    else:
        sciline = []

    #Tsys data info
    if msw.tsysdata is not None:
        (npol_trec, nchan_trec, nscan_trec) = np.shape(msw.tsysdata['trec'])
        tsys_scanlist = msw.spw_setup['scan']['*CALIBRATE_ATMOSPHERE#OFF_SOURCE*']
    #Convert time format
    ts = Time(datatime/3600/24, format='mjd' )
    ts.format = 'isot'
    maxtime = mdates.date2num(ts.max().to_datetime())
    mintime = mdates.date2num(ts.min().to_datetime())
    time = np.array([mdates.date2num(t.to_datetime()) for t in ts])
    tfromstart = time - mintime
    #Get time range per scan
    mintime_scan = []
    maxtime_scan = []
    scanlist = msw.spw_setup['scansforfield'][str(msw.fieldid)]
    for scan in scanlist:
        timesel = time[msw.scantimesel[scan]]
        if len(timesel) >= 2:
            mintime_scan.append(np.min(timesel))
            maxtime_scan.append(np.max(timesel))
        else:
            mintime_scan.append(-1.0)
            maxtime_scan.append(-1.0)

    chan_freq = chan_freq.flatten()

    if (nchan > 1) and (chan_freq[1] < chan_freq[0]):
        # reverse channels if not incremental
        chan_freq = chan_freq[::-1]
        data_outlier = data_outlier[::-1]
        data = data[:, ::-1, :]
        data_outlier2D = data_outlier2D[::-1, :]
        sciline = sciline[::-1]
    freq_ghz = chan_freq * 1e-9
    freqmin, freqmax = freq_ghz.min(), freq_ghz.max()
    extent = (freqmin, freqmax, maxtime, mintime)

    #Averaging in channels, integrations
    data = block_reduce(data, block_size=[1, nchanbin, nvisbin], func=np.ma.mean)
    data_outlier2D = block_reduce(data_outlier2D, block_size=[nchanbin, nvisbin], func=np.ma.max)
    weight = block_reduce(weight, block_size=[1, nvisbin], func=np.ma.mean)
    data_outlier = block_reduce(data_outlier, block_size=nchanbin, func=np.ma.max)
    freq_ghz = block_reduce(freq_ghz, block_size=nchanbin, func=np.ma.mean)

    #Take X-Y difference
    datapolcomp = data[0] - data[1]
    comptitle = 'Pol X-Y'

    #Collapse data in time for detection and 2D plot afterwards
    meandata = np.ma.MaskedArray(np.zeros((npol, nchan)), mask=np.zeros((npol, nchan)))
    meandatapolcomp = np.ma.MaskedArray(np.zeros(nchan), mask=np.zeros(nchan))
    for i in range(npol):
        meandata[i] = np.ma.average(data[i], axis=1, weights=weight[i])
        meandata.mask[i] = np.ma.min(data.mask[i], axis=1)
    polcomp = np.ma.mean(datapolcomp, axis=1)
    polcomp.mask = np.ma.min(datapolcomp.mask, axis=1)

    #Get Tsys data to create skyline selection, if requested
    if remove_skylines:
        (tground_all, pground_all, hground_all, tmatm_all, tsys, trec, tatm, tau, antatm) = sd_qa_utils.getCalAtmData(msw.fname, [msw.spw], msw.spw_setup)
        skylinesel = sd_qa_utils.get_skysel_from_msw(msw, fraclevel = 0.5, minpeaklevel = 0.05)
        #Add skyline selection to masked pixels in the comparison data
        for i in range(npol):
            meandata.mask[i] = np.logical_or(meandata.mask[i], skylinesel)
        polcomp.mask = np.logical_or(polcomp.mask, skylinesel)
        # if (np.shape(polcomp) == np.shape(polcompstd)):
        #     polcompstd.mask = np.logical_or(polcompstd.mask, skylinesel)
        for j in range(nrows):
            for i in range(npol):
                data.mask[i,:,j] = np.logical_or(data.mask[i,:,j], skylinesel)
            datapolcomp.mask[:,j] = np.logical_or(datapolcomp.mask[:,j], skylinesel)
    else:
        skylinesel = None
        skylineimg = None

    stdchanchunks = block_reduce(datapolcomp, block_size=[nchanstdblock, 1], func=np.ma.std)
    stddata = np.ma.median(stdchanchunks)
    mudata = 0.0
    polcompnsigma = polcomp/stddata
    mediannsigma = np.ma.median(np.ma.abs(polcompnsigma))
    if msw.outlierfreq is not None:
        meannsigmasel = np.ma.mean(np.ma.abs(polcompnsigma[msw.outlierfreq]))
    else:
        meannsigmasel = 'N/A'

    # Set scale of color map
    data_cr = data.compressed().real
    #datapolcomp_cr = polcomp.compressed().real
    datapolcomp_cr = datapolcomp.compressed().real
    if (type(zrange) == str) and (zrange.lower() == 'full'):
        zmin = data_cr.min()
        zmax = data_cr.max()
        diffmin = datapolcomp_cr.min()
        diffmax = datapolcomp_cr.max()
    elif (type(zrange) == str) and (zrange.lower() == 'sym'):
        zmin = -np.max([data_cr.min(), data_cr.max()])
        zmax = np.max([data_cr.min(), data_cr.max()])
        diffmin = -np.max([datapolcomp_cr.min(), datapolcomp_cr.max()])
        diffmax = np.max([datapolcomp_cr.min(), datapolcomp_cr.max()])
    elif (type(zrange) == str) and (len(zrange.split(',')) == 2):
        zmin, zmax = map(float, zrange.split(','))
        diffmin, diffmax = map(float, zrange.split(','))
    elif float(zrange):
        zmin = np.nanquantile(data_cr, 1-float(zrange))
        zmax = np.nanquantile(data_cr, float(zrange))
        diffmin = np.nanquantile(datapolcomp_cr, 1-float(zrange))
        diffmax = np.nanquantile(datapolcomp_cr, float(zrange))
    else:
        zmin = np.nanquantile(data_cr, 0.05)
        zmax = np.nanquantile(data_cr, 0.95)
        diffmin = np.nanquantile(datapolcomp_cr, 0.05)
        diffmax = np.nanquantile(datapolcomp_cr, 0.95)

    #Clear
    plt.clf()
    # Create figure and plot unflagged data
    # PIPE-2806 set facecolor to default (white) explicitly to
    # avoid randomly getting gray background in some environments
    fig, axs = plt.subplots(nrows=3, ncols=3, sharex=True, sharey=False,
                        gridspec_kw={'height_ratios': [1, 5, 2]},
                        figsize=(12.0, 12.0),
                        facecolor=plt.rcParams['figure.facecolor'])

    cmap = 'winter'# 'RdBu_r'  # 'viridis'
    cmapsky = 'cividis'
    cmapmask = 'gray'
    cmapsel = 'Reds'

    #Make upper plots with average data
    axs[0,0].plot(freq_ghz, meandata[0].real, '.b')
    axs[0,0].set_ylim((zmin, zmax))
    axs[0,1].plot(freq_ghz, meandata[1].real, '.b')
    axs[0,1].set_ylim((zmin, zmax))
    axs[0,2].plot(freq_ghz, polcomp.real)
    axs[0,2].set_ylim((diffmin, diffmax))
    #Plot science line detection, if available
    if np.sum(sciline) > 0:
        axs[0,0].plot(freq_ghz[sciline], meandata[0].real[sciline], '.r')
        axs[0,1].plot(freq_ghz[sciline], meandata[1].real[sciline], '.r')

    im1 = axs[1, 0].imshow(data[0].real.T, aspect='auto',
                           vmin=zmin, vmax=zmax, cmap=cmap,
                           extent=extent, alpha = 0.8)
    im2 = axs[1, 1].imshow(data[1].real.T, aspect='auto',
                           vmin=zmin, vmax=zmax, cmap=cmap,
                           extent=extent, alpha = 0.8)
    im3 = axs[1, 2].imshow(datapolcomp.real.T, aspect='auto',
                           vmin=diffmin, vmax=diffmax, cmap=cmap,
                           extent=extent, alpha = 0.8)

    #Draw scan boudaries
    for j in [0, 1, 2]:
        for k, scan in enumerate(scanlist):
            if (mintime_scan[k] > 0) and (maxtime_scan[k] > 0):
                axs[1, j].plot([freqmin, freqmax], [mintime_scan[k], mintime_scan[k]], '-k')
                axs[1, j].plot([freqmin, freqmax], [maxtime_scan[k], maxtime_scan[k]], '-k')
                axs[1, j].text(freqmax, 0.5*(mintime_scan[k]+maxtime_scan[k]), str(scan), fontsize=8)
        axs[1, j].text(freqmax+0.05*(freqmax-freqmin), 0.5*(mintime+maxtime), "scan number", fontsize=10, rotation=90)

    if remove_skylines:
        #Make skyline image for 2D plots
        skylineimgdata = np.zeros_like(data[0])
        skylineimgcomp = np.zeros_like(data[0])
        for j in range(nrows):
            skylineimgdata[:,j] = skylinesel*(zmax - zmin) + zmin
            skylineimgcomp[:,j] = skylinesel*(diffmax - diffmin) + diffmin
        axs[1, 2].imshow(skylineimgcomp.T, aspect='auto',
                         vmin=diffmin, vmax=diffmax, cmap=cmapsky,
                         extent=extent, alpha = 0.5)

    #Make lower plots
    #Trec plots
    if msw.tsysdata is not None:
        deltatrxmin = 1000.0
        deltatrxmax = -1000.0
        for pol in [0, 1]:
            for k in range(nscan_trec-1):
                deltatrx = np.ma.MaskedArray(msw.tsysdata['trec'][pol,:,k+1]-msw.tsysdata['trec'][pol,:,k], mask=meandata.mask[pol])
                axs[2,pol].plot(msw.spw_setup[msw.spw]['chanfreqs']*(1.e-09), deltatrx, label = '({0:d}-{1:d})'.format(tsys_scanlist[k+1], tsys_scanlist[k]))
                deltatrxmin = min(deltatrxmin, np.ma.min(deltatrx))
                deltatrxmax = max(deltatrxmax, np.ma.max(deltatrx))
            axs[2,pol].legend(loc='upper left', ncol=3, fontsize='x-small', title='Trec scan-to-scan diff') #bbox_to_anchor=(0., 1.02, 1., .102), borderaxespad=0.,
            axs[2,pol].set_xlabel('Freq [GHz]')
            axs[2,pol].set_ylabel('Trec diff [K]')
        deltrxborder = 0.05*np.abs(deltatrxmax-deltatrxmin)
        for pol in [0, 1]:
            axs[2,pol].set_ylim((deltatrxmin - deltrxborder, deltatrxmax + deltrxborder))

    #Plot nsigma detection v/s frequency
    axs[2,2].plot(freq_ghz, polcompnsigma, '.b')

    if msw.outliers is not None:
        #Make outlier image for 2D plots
        axs[1, 2].imshow(np.ma.MaskedArray(data_outlier2D, mask=~data_outlier2D).T, aspect='auto',
                         vmin=0.0, vmax=1.0, cmap=cmapsel,
                         extent=extent, alpha = 0.5)
    if msw.outlierfreq is not None:
        #Paint red the outliers in nsigma plot
        axs[2,2].plot(freq_ghz[data_outlier], polcompnsigma[data_outlier], 'sr')

    date_format = mdates.DateFormatter('%H:%M')
    for ax in axs[1,:]:
        ax.yaxis_date()
        ax.yaxis.set_major_formatter(date_format)

    for ax in axs[1,:]:
        ax.set_xlabel('Freq [GHz]')

    axs[0,0].set_ylabel('Real')
    axs[1,0].set_ylabel('Time [hh:mm]')
    axs[2,2].set_ylabel('n-Sigma excess')
    axs[2,2].set_xlabel('Freq [GHz]')
    plt.tight_layout()
    fig.subplots_adjust(right=0.85, top=0.92)
    cbar_ax = fig.add_axes([0.88, 0.07, 0.04, 0.7])
    fig.colorbar(im2, cax=cbar_ax)
    axs[0, 0].set_title('Pol X')
    axs[0, 1].set_title('Pol Y')
    axs[0, 2].set_title(comptitle)
    plt.suptitle(f'{msname}, {fieldname}, {antenna_id}:{msw.antenna}, Spw {msw.spw}')
    filename1 = f'{plot_output_path}/{msname}_{fieldname}_{msw.antenna}_Spw{msw.spw}{onoffstr}_heatmap.png'
    print('filename1: '+str(filename1))
    plt.savefig(filename1, bbox_inches='tight')
    plt.close()

    return filename1

def plot_data_trec(msw: mswrapper_sd.MSWrapperSD, thresholds: Union[dict, None] = None, plot_output_path: str = '.',
                  colorlist: Union[list, str] = 'auto', detmsg: str = '') -> str:
    '''Task used to 3-panel diagnostic plots of ON-source data and Trec tables (if available).
    param:
        msw: MSWrapperSD object with the data to be plotted
        thresholds (dict): Dictionary containing the thresholds used in the QA analysis of the dataset.
        plot_output_path (str): Path to the output plot image file.
        colorlist (str or list): Either list of colors to use for each Trec curve, or 'auto' to assign
                                 random colors.
        detmsg (str): Detail message (optional) to be put under the title of the plot.
    Returns:
        List of filenames of produced plots
    '''

    #List of science scan list
    scanlist = msw.analysis.keys()
    #List of Tsys scan list
    tsys_scanlist = msw.spw_setup['scan']['*CALIBRATE_ATMOSPHERE#OFF_SOURCE*']
    #Channel frequencies in GHz and separation in MHz, and min and max frequency
    freqs = msw.spw_setup[msw.spw]['chanfreqs']*1.e-09
    chansep = msw.spw_setup[msw.spw]['chansep']*(1.e-06)
    minfreq = np.min(freqs)
    maxfreq = np.max(freqs)
    nchan = len(freqs)
    msname = msw.fname.split('/')[-1]
    antenna_id = msw.spw_setup['antids'][msw.spw_setup['antnames'] == msw.antenna][0]
    fieldname = sanitize(msw.spw_setup['namesfor'][str(msw.fieldid)][0])
    if str(colorlist) == 'auto':
        colorlist = sd_qa_utils.genColorList(len(scanlist))

    #If science line detected, get the data from the 'all' scans data
    if (msw.data_stats is not None) and ('sci_line_sel' in msw.data_stats.keys()):
        sciline = msw.data_stats['sci_line_sel']
    else:
        sciline = []

    #Turn off interactive plotting
    plt.ioff()
    plt.clf()
    #Set plot size
    fig = plt.gcf()
    # PIPE-2806 set facecolor to default (white) explicitly to
    # avoid randomly getting gray background in some environments
    fig.set_facecolor(plt.rcParams['figure.facecolor'])
    fig.set_size_inches(10, 8)
    #Upper section, data
    if (msw.tsysdata is not None):
        ax1 = plt.subplot(311)
    else:
        ax1 = plt.subplot(111)
    for k, scan in enumerate(scanlist):
        if msw.analysis[scan] is None:
            continue
        plt.plot(freqs, msw.analysis[scan]['ondata']['normdata'], '.', color=colorlist[k], label=str(scan))
        #If there are outliers, plot them in bold
        sel = msw.analysis[scan]['ondata']['outliers']
        if np.sum(sel) > 0:
            plt.plot(freqs[sel], msw.analysis[scan]['ondata']['normdata'][sel], 's', color=colorlist[k])
        #Plot threshold lines
        if thresholds is not None:
            plt.plot([minfreq, maxfreq], [thresholds['X-Y_freq_dev'], thresholds['X-Y_freq_dev']], '--k')
            plt.plot([minfreq, maxfreq], [-thresholds['X-Y_freq_dev'], -thresholds['X-Y_freq_dev']], '--k')
        #Plot science line point, if any detected.
        if (np.sum(sciline) > 0) and scan == 'all':
            plt.plot(freqs[sciline], msw.analysis[scan]['ondata']['normdata'][sciline], 'sk', label='Sci.Line Chan')
        elif (np.sum(sciline) > 0):
            plt.plot(freqs[sciline], msw.analysis[scan]['ondata']['normdata'][sciline], 'sk')

    plt.legend(loc='upper left', ncol=3, fontsize='x-small', title='XX-YY data')
    plt.ylabel('(XX-YY)/sigma (data norm. excess)')
    plt.tick_params('x', labelbottom=False)

    if (msw.tsysdata is not None):
        # Mid section Trec XX
        ax2 = plt.subplot(312, sharex=ax1)
        for k, scan in enumerate(scanlist):
            if msw.analysis[scan] is None:
                continue
            if scan != 'all':
                treclabel = 'diff ({0:d}-{1:d})'.format(msw.tsysdata['idx_tsys_scan_high'][scan], msw.tsysdata['idx_tsys_scan_low'][scan])
            else:
                treclabel = 'diff all'
            plt.plot(freqs, msw.analysis[scan]['trecX']['normdata'], '.', color=colorlist[k], label=treclabel)
            sel = msw.analysis[scan]['trecX']['outliers']
            if np.sum(sel) > 0:
                plt.plot(freqs[sel], msw.analysis[scan]['trecX']['normdata'][sel], 's', color=colorlist[k])
            if thresholds is not None:
                plt.plot([minfreq, maxfreq], [thresholds['Trec_freq_dev'], thresholds['Trec_freq_dev']], '--k')
                plt.plot([minfreq, maxfreq], [-thresholds['Trec_freq_dev'], -thresholds['Trec_freq_dev']], '--k')
        plt.legend(loc='upper left', ncol=3, fontsize='x-small', title='Trec scan-to-scan diff (XX)')
        plt.ylabel('Trec diff (XX)/sigma (norm. excess)')
        # make these tick labels invisible
        plt.tick_params('x', labelbottom=False)

        # Lower section, Trec YY
        ax3 = plt.subplot(313, sharex=ax1)
        for k, scan in enumerate(scanlist):
            if msw.analysis[scan] is None:
                continue
            if scan != 'all':
                treclabel = 'diff ({0:d}-{1:d})'.format(msw.tsysdata['idx_tsys_scan_high'][scan], msw.tsysdata['idx_tsys_scan_low'][scan])
            else:
                treclabel = 'diff all'
            plt.plot(freqs, msw.analysis[scan]['trecY']['normdata'], '.', color=colorlist[k], label=treclabel)
            sel = msw.analysis[scan]['trecY']['outliers']
            if np.sum(sel) > 0:
                plt.plot(freqs[sel], msw.analysis[scan]['trecY']['normdata'][sel], 's', color=colorlist[k])
            if thresholds is not None:
                plt.plot([minfreq, maxfreq], [thresholds['Trec_freq_dev'], thresholds['Trec_freq_dev']], '--k')
                plt.plot([minfreq, maxfreq], [-thresholds['Trec_freq_dev'], -thresholds['Trec_freq_dev']], '--k')
        plt.legend(loc='upper left', ncol=3, fontsize='x-small', title='Trec scan-to-scan diff (YY)')
        plt.ylabel('Trec diff (YY)/sigma (norm. excess)')

    #X-axis
    plt.xlabel('Freq [GHz]')
    plt.xlim(minfreq, maxfreq)

    #write titles and detections info
    title = f'{msname}, {fieldname}, {antenna_id}:{msw.antenna}, Spw {msw.spw}'
    if len(detmsg) > 0:
        title = title + '\nOutliers '+detmsg
    plt.suptitle(title)
    #Save file and return filename
    filename = f'{plot_output_path}/{msname}_{fieldname}_{msw.antenna}_Spw{msw.spw}_data_trec_excess.png'
    print('Plot filename: '+str(filename))
    plt.savefig(filename, bbox_inches='tight')
    plt.close()

    return filename

def plot_data(msw: mswrapper_sd.MSWrapperSD, thresholds: Union[dict, None] = None, plot_output_path: str = '.',
                  colorlist: Union[list, str] = 'auto', detmsg: str = '') -> str:
    '''Task used the diagnostic plot of ON-source XX-YY data for pipeline weblog.
    param:
        msw: MSWrapperSD object with the data to be plotted
        thresholds (dict): Dictionary containing the thresholds used in the QA analysis of the dataset.
        plot_output_path (str): Path to the output plot image file.
        colorlist (str or list): Either list of colors to use for each Trec curve, or 'auto' to assign
                                 random colors.
        detmsg (str): Detail message (optional) to be put under the title of the plot.
    Returns:
        List of filenames of produced plots
    '''

    #List of science scan list
    scanlist = msw.analysis.keys()
    #Channel frequencies in GHz and separation in MHz, and min and max frequency
    freqs = msw.spw_setup[msw.spw]['chanfreqs']*1.e-09
    chansep = msw.spw_setup[msw.spw]['chansep']*(1.e-06)
    minfreq = np.min(freqs)
    maxfreq = np.max(freqs)
    nchan = len(freqs)
    msname = msw.fname.split('/')[-1]
    antenna_id = msw.spw_setup['antids'][msw.spw_setup['antnames'] == msw.antenna][0]
    fieldname = sanitize(msw.spw_setup['namesfor'][str(msw.fieldid)][0])
    if str(colorlist) == 'auto':
        colorlist = sd_qa_utils.genColorList(len(scanlist))

    #If science line detected, get the data from the 'all' scans data
    if (msw.data_stats is not None) and ('sci_line_sel' in msw.data_stats.keys()):
        sciline = msw.data_stats['sci_line_sel']
    else:
        sciline = []

    #Turn off interactive plotting
    plt.ioff()
    plt.clf()
    #Set plot size
    fig = plt.gcf()
    # PIPE-2806 set facecolor to default (white) explicitly to
    # avoid randomly getting gray background in some environments
    fig.set_facecolor(plt.rcParams['figure.facecolor'])
    fig.set_size_inches(10, 8)
    #Upper section, data
    ax1 = plt.subplot(111)
    for k, scan in enumerate(scanlist):
        if msw.analysis[scan] is None:
            continue
        data_label = "all scans" if str(scan) == "all" else f"scan {scan}"
        plt.plot(freqs, msw.analysis[scan]['ondata']['normdata'], '.', color=colorlist[k], label=data_label)
        #If there are outliers, plot them in bold
        sel = msw.analysis[scan]['ondata']['outliers']
        if np.sum(sel) > 0:
            plt.plot(freqs[sel], msw.analysis[scan]['ondata']['normdata'][sel], 's', color=colorlist[k])
        #Plot threshold lines
        if thresholds is not None:
            plt.plot([minfreq, maxfreq], [thresholds['X-Y_freq_dev'], thresholds['X-Y_freq_dev']], '--k')
            plt.plot([minfreq, maxfreq], [-thresholds['X-Y_freq_dev'], -thresholds['X-Y_freq_dev']], '--k')
        #Plot science line point, if any detected.
        if (np.sum(sciline) > 0) and scan == 'all':
            plt.plot(freqs[sciline], msw.analysis[scan]['ondata']['normdata'][sciline], 'sk', label='Sci.Line Chan')
        elif (np.sum(sciline) > 0):
            plt.plot(freqs[sciline], msw.analysis[scan]['ondata']['normdata'][sciline], 'sk')

    plt.legend(loc='upper left', ncol=3, fontsize='x-small', title='XX-YY data')
    #Y-axis
    plt.ylabel('(XX-YY)/sigma (data norm. excess)')
    #X-axis
    plt.xlabel('Freq [GHz]')
    plt.xlim(minfreq, maxfreq)

    #write titles and detections info
    title = f'{msname}, {fieldname}, {antenna_id}:{msw.antenna}, Spw {msw.spw}'
    if len(detmsg) > 0:
        title = title + '\nOutliers '+detmsg
    plt.suptitle(title)
    #Save file and return filename
    filename = f'{plot_output_path}/{msname}_{fieldname}_{msw.antenna}_Spw{msw.spw}_XX-YY_excess.png'
    print('Plot filename: '+str(filename))
    plt.savefig(filename, bbox_inches='tight')
    plt.close()

    return filename

def plot_science_det(msw: mswrapper_sd.MSWrapperSD, thresholds: Union[dict, None] = None,
                    plot_output_path: str = '.') -> str:
    '''Task used to 3-panel diagnostic plots of ON-source time-averaged data, peak of FFT spectrum and
    XX-YY cross-correlation spectrum used for science line detection.
    param:
        msw: MSWrapperSD object with the data to be plotted
        thresholds (dict): Dictionary containing the thresholds used in the QA analysis of the dataset.
        plot_output_path (str): Path to the output plot image file.
    Returns:
        List of filenames of produced plots
    '''

    #Set plot size
    plt.rcParams["figure.figsize"] = (10,8)
    #Channel frequencies in GHz and separation in MHz, and min and max frequency
    freqs = msw.spw_setup[msw.spw]['chanfreqs']*1.e-09
    chansep = msw.spw_setup[msw.spw]['chansep']*(1.e-06)
    minfreq = np.min(freqs)
    maxfreq = np.max(freqs)
    nchan = len(freqs)
    msname = msw.fname.split('/')[-1]
    antenna_id = msw.spw_setup['antids'][msw.spw_setup['antnames'] == msw.antenna][0]
    fieldname = sanitize(msw.spw_setup['namesfor'][str(msw.fieldid)][0])

    #If science line detected, get the data from the 'all' scans data
    if (msw.data_stats is not None) and ('sci_line_sel' in msw.data_stats.keys()):
        sciline = msw.data_stats['sci_line_sel']
    else:
        sciline = []

    #Turn off interactive plotting
    plt.ioff()
    plt.clf()
    # PIPE-2806 set facecolor to default (white) explicitly to
    # avoid randomly getting gray background in some environments
    plt.gcf().set_facecolor(plt.rcParams['figure.facecolor'])
    #Upeer section, data
    ax1 = plt.subplot(311)
    plt.plot(freqs, msw.time_mean_scan['all'][0], '.b', label='Pol XX')
    plt.plot(freqs, msw.time_mean_scan['all'][1], '.g', label='Pol YY')

    #Plot science line point, if any detected.
    if (np.sum(sciline) > 0):
        plt.plot(freqs[sciline], msw.time_mean_scan['all'][0][sciline], '.r', label='Sci.Line Chan')
        plt.plot(freqs[sciline], msw.time_mean_scan['all'][1][sciline], '.m')

    plt.legend(loc='upper left', ncol=3, fontsize='x-small', title='ON-src data')
    plt.ylabel('Real XX,YY [Jy]')
    plt.tick_params('x', labelbottom=False)

    # Mid section Trec XX
    ax2 = plt.subplot(312, sharex=ax1)
    plt.plot(freqs, msw.data_stats['fft_results']['normdata'], '.b')
    #Plot threshold lines
    if thresholds is not None:
        plt.plot([minfreq, maxfreq], [thresholds['sci_threshold'], thresholds['sci_threshold']], '--k')
        plt.plot([minfreq, maxfreq], [-thresholds['sci_threshold'], -thresholds['sci_threshold']], '--k')

    plt.ylabel('Peak FFT Spectrum')
    # make these tick labels invisible
    plt.tick_params('x', labelbottom=False)

    # Lower section, Trec YY
    ax3 = plt.subplot(313, sharex=ax1)
    plt.plot(freqs, msw.data_stats['XYcorr_results']['normdata'], '.b')
    if thresholds is not None:
        plt.plot([minfreq, maxfreq], [thresholds['XYcorr_threshold'], thresholds['XYcorr_threshold']], '--k')
        plt.plot([minfreq, maxfreq], [-thresholds['XYcorr_threshold'], -thresholds['XYcorr_threshold']], '--k')
    plt.ylabel('XX-YY cross-correlation')

    #X-axis
    plt.xlabel('Freq [GHz]')
    plt.xlim(minfreq, maxfreq)

    #write titles and detections info
    title = f'{msname}, {fieldname}, {antenna_id}:{msw.antenna}, Spw {msw.spw}'
    plt.suptitle(title)
    #Save file and return filename
    filename = f'{plot_output_path}/{msname}_{fieldname}_{msw.antenna}_Spw{msw.spw}_science_line_det.png'
    print('Plot filename: '+str(filename))
    plt.savefig(filename, bbox_inches='tight')
    plt.close()
    #Reset figure size
    plt.rcParams["figure.figsize"] = plt.rcParamsDefault["figure.figsize"]

    return filename


def makeSummaryTable(qascore_list, plots_fnames, plfolder, working_folder = '.', output_file = 'sd_applycal_output/qascore_summary.csv', writemode = 'w', weblog_adress = 'file://'):

    if plots_fnames == '':
        plots_fnames = ['N/A' for i in range(len(qascore_list))]
    fout = open(output_file, writemode)
    fout.write('PLfolder,msname,spw,antenna,scan,qascore_value,metric_data,metric_trec,width_pcent,plot_filename,weblog_link\n')
    fmt = '{0:s},{1:s},{2:d},{3:s},{4:s},{5:.3f},{6:.3f},{7:.3f},{8:.3f},{9:s},{10:s}\n'
    for k, qascore in enumerate(qascore_list):
        msname = list(qascore.applies_to.vis)[0]
        spw = list(qascore.applies_to.spw)[0]
        antenna = list(qascore.applies_to.ant)[0]
        scan = str(list(qascore.applies_to.scan)[0]).replace(',',';')
        #Metric data value
        metric_data = qascore.origin[1]
        #Search For Trec info and find maximum value
        match = re.search(r"Trec: (?P<tx>[0-9]+\.[0-9]{3}),(?P<ty>[0-9]+\.[0-9]{3})", qascore.longmsg)
        if match:
            tvalues = match.groupdict()
            metric_trec = max(float(tvalues['tx']), float(tvalues['ty']))
        else:
            metric_trec = 0.0
        #Search width
        match = re.search(r"width: (?P<width>[0-9]+\.[0-9]{2})%", qascore.longmsg)
        if match:
            wvalues = match.groupdict()
            width = float(wvalues['width'])
        else:
            width = 0.0
        #Search FieldName
        match = re.search(r"\(field (?P<field>.+)\)", qascore.longmsg)
        if match:
            fieldmatch = match.groupdict()
            fieldname = sanitize(fieldmatch['field'])
        else:
            fieldname = 'NNN'
        #Find filename of plot, if present.
        plot_fname = plots_fnames[k]
        if not plot_fname == 'N/A':
            plot_fname = plot_fname.split('/')[-1]
        #If a PL working folder is provided, search for relevant weblog plot
        weblogpath = working_folder + 'pipeline-*/html/stage8/{0:s}-*-{1:s}-spw_{2:d}-antenna_{3:s}-atmcor-TARGET-real_vs_freq.png'.format(msname,fieldname,spw,antenna)
        weblogplots = glob.glob(weblogpath)
        if len(weblogplots) == 1:
            weblink = weblog_adress + weblogplots[0]
        else:
            weblink = 'weblog_plot_not_found'
        fout.write(fmt.format(plfolder,msname,spw,antenna,scan+'('+fieldname+')',qascore.score,metric_data,metric_trec,width,plot_fname,weblink))
    fout.close()

    return

def makeQAmsgTable(qascore_list, plfolder, output_file = 'sd_applycal_output/qascores_details.csv', writemode = 'w'):

    fout = open(output_file, writemode)
    fout.write('PLfolder,msname,message\n')
    fmt = '{0:s},{1:s},\"{2:s}\"\n'
    for k, qascore in enumerate(qascore_list):
        msname = list(qascore.applies_to.vis)[0]
        fout.write(fmt.format(plfolder,msname,qascore.longmsg))
    fout.close()

    return

def addFLSLentry(qascore_list, output_file = './prototype_qa_score.csv', dtime_min = -1, writemode = 'a'):

    qascore_values = np.array([qascore.score for qascore in qascore_list])
    qascore_lowest = qascore_list[np.argsort(qascore_values)[0]]
    msname_lowest = list(qascore_lowest.applies_to.vis)[0]
    dtime = ' Script Runtime: {0:.2f} min.'.format(dtime_min) if dtime_min > 0.0 else ''
    fout = open(output_file, writemode)
    fout.write('PIPEREQ-176,{0:.3f},\"{1:s}:{2:s}\"\n'.format(qascore_lowest.score,msname_lowest,qascore_lowest.longmsg+dtime))
    fout.close()

    return

