class Sensitivity(dict):  # noqa: D100
    """Sensitivity template definition."""

    def __init__(self, *args, **kwargs):  # noqa: D107
        self['array'] = None                   # string
        self['intent'] = None                  # string
        self['field'] = None                   # string
        self['spw'] = None                     # string
        self['is_representative'] = None       # boolean
        self['bandwidth'] = None               # quanta
        self['bwmode'] = None                  # string
        self['beam'] = None                    # a beam dictionary
        self['cell'] = None                    # quanta array
        self['robust'] = None                  # string
        self['uvtaper'] = None                 # list
        self['theoretical_sensitivity'] = None # quanta
        self['observed_sensitivity'] = None    # quanta
        self['effective_bw'] = None            # quanta
        self['pbcor_image_min'] = None         # quanta
        self['pbcor_image_max'] = None         # quanta
        self['nonpbcor_image_min'] = None      # quanta
        self['nonpbcor_image_max'] = None      # quanta
        self['imagename'] = None               # string
        self['datatype'] = None                # string

        dict.__init__(self, *args, **kwargs)
