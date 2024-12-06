import numpy as np
import casatools
import pickle as pkl
import qa_utils as qau
import glob

def init_nested_dict(spwlist, scanlist):
    outdict = {}
    for spw in spwlist:
        outdict[spw] = {}
        for scan in scanlist:
            outdict[spw][scan] = {}
    return outdict

class TableWrapper(object):
    """
    TableWrapper is a wrapper to load and store in numpy arrays the data necessary
    to analyze the bandpass calibration table.
    """

    @staticmethod
    def create_from_tables(field_id = None, intent = None, scanlist = None,
                           bcaltbl = None, gpcaltbl = None, spwsetup = None):
        """
        Create a new TableWrapper from the bandpass table given and the spwsetup dictionary.

        :param field_id: Field ID of the target to load data from (required, if intent not given)
        :param intent: intent of the target to load data from (required, if field_id not given)
        :param scanlist: List of scans to load. I not given, all scans for the field_id/intent will be loaded
        :param bcaltbl: Bandpass table filename
        :param gpcaltbl: Gain table filename
        :param spwsetup: spwsetup dictionary (required)
        :return: TableWrapper instance
        """
        #We need at least a field ID or the intent and the spwsetup
        if spwsetup is None:
            print('spwsetup variable must be set! Exiting...')
            return None
        #Normalize intent string, if it exists
        if (intent is not None) and (intent.count('*') == 0):
            intent = '*'+intent+'*'
        intents_available = [i for i in spwsetup['fieldid'].keys() if len(spwsetup['fieldid'][i]) == 1]
        #Define field_id, if it doesn't exist, use the intent to get it
        if (field_id is None) and (intent is None):
            print('Need either FIELD_ID or intent to look for data! Exiting...')
            return None
        elif (field_id is None) and (intent is not None) and (intent in intents_available):
            field_id = spwsetup['fieldid'][intent][0]
        elif (field_id is not None) and (intent is None):
            intent = [i for i, f in spwsetup['fieldid'].items() if len(f) == 1 and f[0] == field_id]
            if len(intent) > 0:
                intent = intent[0]
            else:
                print('Could not find intent of FIELD_ID='+str(field_id)+' Exiting...')
                return None
        field_id = int(field_id)

        #Select scan list
        if (scanlist is None) or (scanlist == '*'):
            scanlist = spwsetup['scan'][intent]
        if type(scanlist) == int:
            scanlist = [scanlist]

        #Dictionares with arrays with data
        refant_freq = init_nested_dict(spwsetup['spwlist'], scanlist)
        cparam_freq = init_nested_dict(spwsetup['spwlist'], scanlist)
        cparamerr_freq = init_nested_dict(spwsetup['spwlist'], scanlist)
        flag_freq = init_nested_dict(spwsetup['spwlist'], scanlist)
        snr_freq = init_nested_dict(spwsetup['spwlist'], scanlist)
        amp_freq = init_nested_dict(spwsetup['spwlist'], scanlist)
        phase_freq = init_nested_dict(spwsetup['spwlist'], scanlist)
        is_fully_flagged_freq = init_nested_dict(spwsetup['spwlist'], scanlist)
        refant_time = init_nested_dict(spwsetup['spwlist'], scanlist)
        cparam_time = init_nested_dict(spwsetup['spwlist'], scanlist)
        flag_time = init_nested_dict(spwsetup['spwlist'], scanlist)
        snr_time = init_nested_dict(spwsetup['spwlist'], scanlist)
        amp_time = init_nested_dict(spwsetup['spwlist'], scanlist)
        phase_time = init_nested_dict(spwsetup['spwlist'], scanlist)
        is_fully_flagged_time = init_nested_dict(spwsetup['spwlist'], scanlist)

        #Save SPW parameters
        time = {}
        freq = {}
        nchan = {}
        npol = {}
        for spwid in spwsetup['spwlist']:
            #Save channel frequencies in GHz
            freq[spwid] = spwsetup[spwid]['chanfreqs']*(1.e-09)
            nchan[spwid] = spwsetup[spwid]['nchan']
            npol[spwid] = spwsetup[spwid]['npol']
            time[spwid] = {}

        #Start the casa tools table
        tb = casatools.table()

        if bcaltbl is not None:
            #Let open the BPCAL table
            tb.open(bcaltbl)
            bpfields = np.unique(tb.getcol('FIELD_ID'))
            #Separate de data rows by spw, antenna
            for spwid in spwsetup['spwlist']:
                #Test whether we have the field in the table
                if field_id not in bpfields:
                    print('Could not find FIELD_ID '+str(field_id)+' in file '+bcaltbl+'!!')
                    print('Available fields in this table: '+str(bpfields))
                    break
                for scan in scanlist:
                    for antid in spwsetup['antids']:
                        subtb = tb.query('SPECTRAL_WINDOW_ID == '+str(spwid)+' && ANTENNA1 == '+str(antid)+' && FIELD_ID == '+str(field_id)+' && SCAN_NUMBER == '+str(scan))
                        refant_freq[spwid][scan][antid] = subtb.getcol('ANTENNA2')[0]
                        cparam_freq[spwid][scan][antid] = subtb.getcol('CPARAM')[:,:,0]
                        #Check array sizes
                        (thisnpol, thisnchan) = np.shape(cparam_freq[spwid][scan][antid])
                        if not ((thisnpol == npol[spwid]) and (thisnchan == nchan[spwid])):
                            print('Unexpected data size for SPW '+str(spwid)+', antenna '+str(antid)+' ('+spwsetup['antnames'][antid]+')')
                            print('thisnpol, npol[spwid] = '+str((thisnpol, npol[spwid])))
                            print('thisnchan, nchan[spwid] = '+str((thisnchan, nchan[spwid])))
                        cparamerr_freq[spwid][scan][antid] = subtb.getcol('PARAMERR')[:,:,0]
                        flag_freq[spwid][scan][antid] = subtb.getcol('FLAG')[:,:,0]
                        snr_freq[spwid][scan][antid] = subtb.getcol('SNR')[:,:,0]
                        amp_freq[spwid][scan][antid] = np.ma.MaskedArray(np.abs(cparam_freq[spwid][scan][antid]), mask=flag_freq[spwid][scan][antid])
                        phase_freq[spwid][scan][antid] = np.ma.MaskedArray(np.angle(cparam_freq[spwid][scan][antid]), mask=flag_freq[spwid][scan][antid])
                        is_fully_flagged_freq[spwid][scan][antid] = (np.sum(flag_freq[spwid][scan][antid]) == np.product(np.shape(flag_freq[spwid][scan][antid])))
                        #Add keywords in antenna names for convenience
                        antname = spwsetup['antnames'][antid]
                        refant_freq[spwid][scan][antname] = refant_freq[spwid][scan][antid]
                        cparam_freq[spwid][scan][antname] = cparam_freq[spwid][scan][antid]
                        cparamerr_freq[spwid][scan][antname] = cparamerr_freq[spwid][scan][antid]
                        flag_freq[spwid][scan][antname] = flag_freq[spwid][scan][antid]
                        snr_freq[spwid][scan][antname] = snr_freq[spwid][scan][antid]
                        amp_freq[spwid][scan][antname] = amp_freq[spwid][scan][antid]
                        phase_freq[spwid][scan][antname] = phase_freq[spwid][scan][antid]
                        is_fully_flagged_freq[spwid][scan][antname] = is_fully_flagged_freq[spwid][scan][antid]
            #Let's close the bpcal table.
            tb.close()

        if gpcaltbl is not None:
            #Now let open the gpcal table and read the data
            tb.open(gpcaltbl)
            data_fields = tb.getcol('FIELD_ID')
            gfields = np.unique(data_fields)
            data_cparam = tb.getcol('CPARAM')[:,0,:]
            data_flag = tb.getcol('FLAG')[:,0,:]
            data_ant1 = tb.getcol('ANTENNA1')
            data_ant2 = tb.getcol('ANTENNA2')
            data_spw = tb.getcol('SPECTRAL_WINDOW_ID')
            data_scan = tb.getcol('SCAN_NUMBER')
            data_time = tb.getcol('TIME')
            data_snr = tb.getcol('SNR')[:,0,:]
            #Let's close the gpcal table.
            tb.close()
            #Separate de data rows by spw, antenna
            for spwid in spwsetup['spwlist']:
                #Test whether we have the field in the table
                if field_id not in gfields:
                    print('Could not find FIELD_ID '+str(field_id)+' in file '+gpcaltbl+'!!')
                    print('Available fields in this table: '+str(gfields))
                    break
                for scan in scanlist:
                    for antid in spwsetup['antids']:
                        #subtb = tb.query('SPECTRAL_WINDOW_ID == '+str(spwid)+' && ANTENNA1 == '+str(antid)+' && FIELD_ID == '+str(field_id)+' && SCAN_NUMBER == '+str(scan))
                        sel = (data_fields == field_id) & (data_spw == spwid) & \
                              (data_scan == scan) & (data_ant1 == antid)
                        nsel = np.sum(sel)
                        #print('time sel for spw,scan='+str((spwid,scan))+' nsel: '+str(np.sum(sel)))
                        if nsel > 0:
                            if antid == 0:
                                time[spwid][scan] = data_time[sel]
                            cparam_time[spwid][scan][antid] = data_cparam[:,sel]
                            flag_time[spwid][scan][antid] = data_flag[:,sel]
                            snr_time[spwid][scan][antid] = data_snr[:,sel]
                            refant_time[spwid][scan][antid] = data_ant2[sel][0]
                            amp_time[spwid][scan][antid] = np.ma.MaskedArray(np.abs(data_cparam[:,sel]),
                                                                             mask=data_flag[:,sel])
                            phase_time[spwid][scan][antid] = np.ma.MaskedArray(np.angle(data_cparam[:,sel]),
                                                                               mask=data_flag[:,sel])
                            is_fully_flagged_time[spwid][scan][antid] = (np.sum(flag_time[spwid][scan][antid]) == np.product(np.shape(flag_time[spwid][scan][antid])))
                        else:
                            cparam_time[spwid][scan][antid] = np.ma.MaskedArray([[np.nan] for i in range(spwsetup[spwid]['npol'])], mask = [[True] for i in range(spwsetup[spwid]['npol'])])
                            flag_time[spwid][scan][antid] = np.ma.MaskedArray([[np.nan] for i in range(spwsetup[spwid]['npol'])], mask = [[True] for i in range(spwsetup[spwid]['npol'])])
                            refant_time[spwid][scan][antid] = np.ma.MaskedArray([[np.nan] for i in range(spwsetup[spwid]['npol'])], mask = [[True] for i in range(spwsetup[spwid]['npol'])])
                            amp_time[spwid][scan][antid] = np.ma.MaskedArray([[np.nan] for i in range(spwsetup[spwid]['npol'])], mask = [[True] for i in range(spwsetup[spwid]['npol'])])
                            phase_time[spwid][scan][antid] = np.ma.MaskedArray([[np.nan] for i in range(spwsetup[spwid]['npol'])], mask = [[True] for i in range(spwsetup[spwid]['npol'])])
                            is_fully_flagged_time[spwid][scan][antid] = True

                        #Add keywords in antenna names for convenience
                        antname = spwsetup['antnames'][antid]
                        amp_time[spwid][scan][antname] = amp_time[spwid][scan][antid]
                        phase_time[spwid][scan][antname] = phase_time[spwid][scan][antid]
                        flag_time[spwid][scan][antname] = flag_time[spwid][scan][antid]
                        refant_time[spwid][scan][antname] = refant_time[spwid][scan][antid]
                        is_fully_flagged_time[spwid][scan][antname] = is_fully_flagged_time[spwid][scan][antid]

        return TableWrapper(bcaltbl=bcaltbl, gpcaltbl=gpcaltbl, field_id=field_id, spwsetup=spwsetup,
                            spws=spwsetup['spwlist'],
                            scanlist=scanlist, antids=spwsetup['antids'], antnames=spwsetup['antnames'],
                            antcenterdist=spwsetup['antcenterdist'],
                            refant_freq=refant_freq, freq=freq, amp_freq=amp_freq, phase_freq=phase_freq,
                            is_fully_flagged_freq=is_fully_flagged_freq,
                            npol=npol, nchan=nchan, cparam_freq=cparam_freq, cparamerr_freq=cparamerr_freq,
                            flag_freq=flag_freq, snr_freq=snr_freq,
                            time=time, cparam_time=cparam_time, flag_time=flag_time, snr_time=snr_time,
                            amp_time=amp_time, phase_time=phase_time,
                            is_fully_flagged_time=is_fully_flagged_time, refant_time=refant_time)


    def __init__(self, bcaltbl=None, gpcaltbl=None, field_id=None, spwsetup=None, spws=None, scanlist=None, antids=None,
                 antnames=None, antcenterdist=None, refant_freq=None, freq=None, amp_freq=None, phase_freq=None,
                 is_fully_flagged_freq=None, npol=None, nchan=None, cparam_freq=None, cparamerr_freq=None,
                 flag_freq=None, snr_freq=None, time=None, cparam_time=None, flag_time=None, snr_time=None,
                 amp_time=None, phase_time=None, is_fully_flagged_time=None, refant_time=None):
        self.bcaltbl = bcaltbl
        self.gpcaltbl = gpcaltbl
        self.field_id = field_id
        self.spwsetup = spwsetup
        self.spws = spws
        self.scanlist = scanlist
        self.antids = antids
        self.antnames = antnames
        self.antcenterdist = antcenterdist
        self.refant_freq = refant_freq
        self.freq = freq
        self.amp_freq = amp_freq
        self.phase_freq = phase_freq
        self.is_fully_flagged_freq = is_fully_flagged_freq
        self.npol = npol
        self.nchan = nchan
        self.cparam_freq = cparam_freq
        self.cparamerr_freq = cparamerr_freq
        self.flag_freq = flag_freq
        self.snr_freq = snr_freq
        self.time = time
        self.cparam_time = cparam_time
        self.flag_time=flag_time
        self.snr_time = snr_time
        self.amp_time=amp_time
        self.phase_time=phase_time
        self.is_fully_flagged_time = is_fully_flagged_time
        self.refant_time = refant_time
