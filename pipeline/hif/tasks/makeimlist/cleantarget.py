class CleanTarget(dict):

    '''Clean target template definition.'''

    def __init__(self, *args, **kwargs):
        self['antenna'] = None         # list of strings
        self['field'] = None           # string
        self['intent'] = None          # string
        self['spw'] = None             # string
        self['spwsel_lsrk'] = None     # dictionary
        self['spwsel_topo'] = None     # list
        self['spwsel_all_cont'] = None # boolean
        self['num_all_spws'] = None    # int
        self['num_good_spws'] = None   # int
        self['cell'] = None            # string
        self['cfcache'] = None         # string
        self['imsize'] = None          # string / list
        self['pblimit'] = None         # float
        self['phasecenter'] = None     # string
        self['specmode'] = None        # string
        self['gridder'] = None         # string
        self['datacolumn'] = None      # string
        self['datatype_info'] = None   # string
        self['deconvolver'] = None     # string
        self['imagename'] = None       # string
        self['start'] = None           # string
        self['width'] = None           # string
        self['nbin'] = None            # int
        self['nchan'] = None           # int
        self['stokes'] = None          # string
        self['nterms'] = None          # int
        self['robust'] = None          # float
        self['uvrange'] = None         # string / list
        self['bl_ratio'] = None        # float
        self['uvtaper'] = None         # list
        self['scales'] = None          # list
        self['niter'] = None           # int
        self['cycleniter'] = None      # int
        self['cyclefactor'] = None     # float
        self['sensitivity'] = None     # string
        self['threshold'] = None       # string
        self['reffreq'] = None         # string
        self['restfreq'] = None        # string
        self['heuristics'] = None      # object
        self['vis'] = None             # list of strings
        self['is_per_eb'] = None       # boolean
        self['usepointing'] = None     # boolean
        self['mosweight'] = None       # boolean

        dict.__init__(self, *args, **kwargs)
