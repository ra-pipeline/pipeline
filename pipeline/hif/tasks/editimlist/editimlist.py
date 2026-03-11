"""A pipeline task to add to a list of images to be made by hif_makeimages()

The hif_editimlist() task typically uses a parameter file as input.  Depending
on the use case, there will usually be a minimal set of input parameters
defined in this file.  Each set of image parameters gets stored in the global
context in the clean_list_pending attribute.

Example:
    A common case is providing a list of VLASS image parameters via a file::

        CASA <1>: hif_editimlist(parameter_file='vlass_QLIP_parameters.list')

    The ``vlass_QLIP_parameters.list`` file might contain something like the
    following::

        phasecenter = 'J2000 12:16:04.600 +059.24.50.300'
        imagename = 'QLIP_image'

    An equivalent way to invoke the above example would be::

        CASA <2>: hif_editimlist(phasecenter='J2000 12:16:04.600 +059.24.50.300',
                                 imagename='QLIP_image')

Any imaging parameters that are not specified when hif_editimlist() is called,
either as a task parameter or via a parameter file, will have a default value
or heuristic applied.

Todo:
    * In the future this task will be modified to allow editing the parameters
    of an existing context.clean_list_pending entry.

"""
import ast
import os

import pipeline.domain.measures as measures
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.vdp as vdp
from pipeline.domain import DataType
from pipeline.hif.heuristics import imageparams_factory
from pipeline.hif.tasks.makeimlist.cleantarget import CleanTarget
from pipeline.infrastructure import casa_tools, task_registry
from pipeline.infrastructure.utils import utils

from .resultobjects import EditimlistResult

LOG = infrastructure.get_logger(__name__)


class EditimlistInputs(vdp.StandardInputs):
    # Search order of input vis
    processing_data_type = [
        DataType.SELFCAL_LINE_SCIENCE,
        DataType.REGCAL_LINE_SCIENCE,
        DataType.SELFCAL_CONTLINE_SCIENCE,
        DataType.REGCAL_CONTLINE_SCIENCE,
        DataType.REGCAL_CONTLINE_ALL,
        DataType.RAW,
    ]

    search_radius_arcsec = vdp.VisDependentProperty(default=1000.0)
    conjbeams = vdp.VisDependentProperty(default=False)
    cfcache = vdp.VisDependentProperty(default='')
    cfcache_nowb = vdp.VisDependentProperty(default='')
    cyclefactor = vdp.VisDependentProperty(default=-999.)
    cycleniter = vdp.VisDependentProperty(default=-999)
    nmajor = vdp.VisDependentProperty(default=None)
    datatype = vdp.VisDependentProperty(default='')
    datacolumn = vdp.VisDependentProperty(default='')
    deconvolver = vdp.VisDependentProperty(default='')
    editmode = vdp.VisDependentProperty(default='')
    imaging_mode = vdp.VisDependentProperty(default='')
    imagename = vdp.VisDependentProperty(default='')
    intent = vdp.VisDependentProperty(default='')
    gridder = vdp.VisDependentProperty(default='')
    mask = vdp.VisDependentProperty(default=None)
    pbmask = vdp.VisDependentProperty(default=None)
    nchan = vdp.VisDependentProperty(default=-1)
    niter = vdp.VisDependentProperty(default=0)
    nterms = vdp.VisDependentProperty(default=0)
    parameter_file = vdp.VisDependentProperty(default='')
    pblimit = vdp.VisDependentProperty(default=-999.)
    phasecenter = vdp.VisDependentProperty(default='')
    reffreq = vdp.VisDependentProperty(default='')
    restfreq = vdp.VisDependentProperty(default='')
    robust = vdp.VisDependentProperty(default=-999.)
    scales = vdp.VisDependentProperty(default='')
    specmode = vdp.VisDependentProperty(default='')
    start = vdp.VisDependentProperty(default='')
    stokes = vdp.VisDependentProperty(default='')
    threshold = vdp.VisDependentProperty(default='')
    nsigma = vdp.VisDependentProperty(default=-999.)
    uvtaper = vdp.VisDependentProperty(default='')
    uvrange = vdp.VisDependentProperty(default='')
    width = vdp.VisDependentProperty(default='')
    sensitivity = vdp.VisDependentProperty(default=0.0)
    # VLASS-SE-CONT specific option: if True then perform final clean iteration without mask for selfcal image
    clean_no_mask_selfcal_image = vdp.VisDependentProperty(default=False)
    # VLASS-SE-CONT specific option: user settable cycleniter in cleaning without mask in final imaging stage
    cycleniter_final_image_nomask = vdp.VisDependentProperty(default=None)
    # VLASS-SE-CUBE plane rejection parameters
    vlass_plane_reject_ms = vdp.VisDependentProperty(default=True)

    @vdp.VisDependentProperty
    def cell(self):
        # mutable object, so should not use VisDependentProperty(default=[])
        if 'hm_cell' in self.context.size_mitigation_parameters:
            return self.context.size_mitigation_parameters['hm_cell']
        return []

    @cell.convert
    def cell(self, val):
        if isinstance(val, str):
            val = [val]
        for item in val:
            if isinstance(item, str):
                if 'ppb' in item:
                    return item
        return val

    @vdp.VisDependentProperty
    def imsize(self):
        # mutable object, so should not use VisDependentProperty(default=[])
        if 'hm_imsize' in self.context.size_mitigation_parameters:
            return self.context.size_mitigation_parameters['hm_imsize']
        return []

    @imsize.convert
    def imsize(self, val):
        if not isinstance(val, list):
            val = [val]

        for item in val:
            if isinstance(item, str):
                if 'pb' in item:
                    return item
        return val

    @vdp.VisDependentProperty
    def field(self):
        # mutable object, so should not use VisDependentProperty(default=[])
        return []

    @field.convert
    def field(self, val):
        if not isinstance(val, (str, list, type(None))):
            # PIPE-1881: allow field names that mistakenly get casted into non-string datatype by
            # recipereducer (utils.string_to_val) and executeppr (XmlObjectifier.castType)
            LOG.warning('The field selection input %r is not a string and will be converted.', val)
            val = str(val)
        if not isinstance(val, list):
            val = [val]
        return val

    @vlass_plane_reject_ms.postprocess
    def vlass_plane_reject_ms(self, unprocessed):
        """Convert the allowed argument input datatype to the dictionary form used by the task."""
        vlass_plane_reject_dict = {'apply': True, 'exclude_spw': '', 'flagpct_thresh': 0.9, 'nfield_thresh': 12}
        if isinstance(unprocessed, dict):
            vlass_plane_reject_dict.update(unprocessed)
        if isinstance(unprocessed, bool):
            vlass_plane_reject_dict['apply'] = unprocessed
        LOG.debug(
            'convert the task input of vlass_plane_reject_ms from %r to %r.', unprocessed, vlass_plane_reject_dict
        )
        return vlass_plane_reject_dict

    @vdp.VisDependentProperty
    def nbin(self):
        if 'nbins' in self.context.size_mitigation_parameters:
            return self.context.size_mitigation_parameters['nbins']
        return -1

    @vdp.VisDependentProperty
    def spw(self):
        return ''

    @spw.convert
    def spw(self, val):
        # Use str() method to catch single spwid case via PPR which maps to int.
        return str(val)

    # docstring and type hints: supplements hif_editimlist
    def __init__(self, context, output_dir=None, vis=None,
                 search_radius_arcsec=None, cell=None, cfcache=None, conjbeams=None,
                 cyclefactor=None, cycleniter=None, nmajor=None, datatype=None, datacolumn=None, deconvolver=None,
                 editmode=None, field=None, imaging_mode=None,
                 imagename=None, imsize=None, intent=None, gridder=None,
                 mask=None, pbmask=None, nbin=None, nchan=None, niter=None, nterms=None,
                 parameter_file=None, pblimit=None, phasecenter=None, reffreq=None, restfreq=None,
                 robust=None, scales=None, specmode=None, spw=None,
                 start=None, stokes=None, threshold=None, nsigma=None,
                 uvtaper=None, uvrange=None, width=None, sensitivity=None, clean_no_mask_selfcal_image=None,
                 vlass_plane_reject_ms=None,
                 cycleniter_final_image_nomask=None):
        """Initialize Inputs.

        Args:
            context: Pipeline context object containing state information.

            output_dir: Output directory.

                Default: ``None``, corresponds to the current working directory.

            vis: List of input visibility files.

            search_radius_arcsec: Size of the field finding beam search radius in arcsec.

            cell: Image cell size(s) in X and Y, specified in angular units or pixels per beam.

                - A single value applies to both axes.

                - Use the format ``'<number>ppb'`` to specify pixels per beam.

                By default, the cell size is computed from the UV coverage of all fields to be imaged,
                assuming a sampling of 5 pixels per beam, i.e., `'5ppb'``. When using the pixels-per-beam format
                (e.g., ``'3ppb'``), the cell size is scaled accordingly.

                Examples: ``['0.5arcsec', '0.5arcsec']``, ``'3ppb'``

            cfcache: Convolution function cache directory name

            conjbeams: Use conjugate frequency in tclean for wideband A-terms.

            cyclefactor: Controls the depth of clean in minor cycles based on PSF.

            cycleniter: Controls max number of minor cycle iterations in a single major cycle.

            nmajor: Controls the maximum number of major cycles to evaluate.

            datatype: Data type(s) to image. The default ``''`` selects the best available data type (e.g. selfcal over regcal) with
                an automatic fallback to the next available data type.
                With the ``datatype`` parameter of ``'regcal'`` or ``'selfcal'``, one
                can force the use of only given data type(s).
                Note that this parameter is only for non-VLASS data when the datacolumn
                is not explictly set by user or imaging heuristics.

            datacolumn: Data column to image; this will take precedence over the datatype parameter.

            deconvolver: Minor cycle algorithm (multiscale or mtmfs)

            editmode: The edit mode of the task (``'add'`` or ``'replace'``). Defaults to ``'add'``.

            field: Set of data selection field names or ids.

            imaging_mode: Identity of product type (e.g. VLASS quick look) desired.  This will determine the heuristics used.

            imagename: Prefix for output image names.

            imsize: Image X and Y size(s) in pixels or PB level (single fields), ``''`` for default. Single value same for both. ``'<number>pb'`` for PB level.

            intent: Set of data selection intents

            gridder: Name of the gridder to use with tclean

            mask: Used to declare whether to use a predefined mask for tclean.

            pbmask: Used to declare primary beam gain level for cleaning with primary beam mask (``usemask='pb'``), used only for VLASS-SE-CONT imaging mode.

            nbin: Channel binning factor.

            nchan: Number of channels,

                Default: ``-1``, which means all channels.

            niter: The max total number of minor cycle iterations allowed for tclean

            nterms: Number of Taylor coefficients in the spectral model

            parameter_file: keyword=value text file as alternative method of input parameters

            pblimit: PB gain level at which to cut off normalizations

            phasecenter: The default phase center is set to the mean of the field directions of all fields that are to be image together.

                Example: ``0``, ``'J2000 19h30m00 -40d00m00'``

            reffreq: Reference frequency of the output image coordinate system

            restfreq: List of rest frequencies or a rest frequency in a string for output image.

            robust: Briggs robustness parameter for tclean

            scales: The scales for multi-scale imaging.

            specmode: Spectral gridding type. Options: ``'mfs'``, ``'cont'``, ``'cube'``, ``''``.

            spw: Set of data selection spectral window/channels, ``''`` for all

            start: First channel for frequency mode images. Starts at first input channel of the spw.

                Example: ``'22.3GHz'``

            stokes: Stokes Planes to make

            threshold: Stopping threshold (number in units of Jy, or string)

            nsigma: Multiplicative factor for rms-based threshold stopping

            uvtaper: Used to set a uv-taper during clean.

            uvrange: Set of data selection uv ranges, ``''`` for all.

            width: Channel width

            sensitivity: Theoretical sensitivity (override internal calculation)

            clean_no_mask_selfcal_image:

            vlass_plane_reject_ms (bool or dict, optional): Control VLASS Coarse Cube plane
                rejection based on flagging percentages. Only applies to the ``'VLASS-SE-CUBE'``
                imaging mode.

                Default is ``True``, which automatically rejects planes with high flagging
                percentages using built-in heuristics (see details below).

                Options:

                - ``True``: Enable automatic plane rejection with default thresholds.

                - ``False``: Disable flagging-based plane rejection entirely.

                - ``dict``: Enable plane rejection with custom threshold parameters.

                When providing a dictionary, supported keys are:

                - ``exclude_spw`` (str, default ``''``): Comma-separated list of spectral
                windows to exclude from rejection consideration (always preserved).

                - ``flagpct_thresh`` (float, default ``0.9``): Flagging percentage threshold
                per field for triggering plane rejection.

                - ``nfield_thresh`` (int, default ``12``): Minimum number of fields that must
                exceed the flagging threshold before rejecting the plane.

            cycleniter_final_image_nomask:

        """
        super().__init__()
        self.context = context
        self.output_dir = output_dir
        self.vis = vis

        self.search_radius_arcsec = search_radius_arcsec
        self.cell = cell
        self.cfcache = cfcache
        self.conjbeams = conjbeams
        self.cyclefactor = cyclefactor
        self.cycleniter = cycleniter
        self.nmajor = nmajor
        self.datatype = datatype
        self.datacolumn = datacolumn
        self.deconvolver = deconvolver
        self.editmode = editmode
        self.field = field
        self.imaging_mode = imaging_mode
        self.imagename = imagename
        self.imsize = imsize
        self.intent = intent
        self.gridder = gridder
        self.mask = mask
        self.pbmask = pbmask
        self.nbin = nbin
        self.nchan = nchan
        self.niter = niter
        self.nterms = nterms
        self.parameter_file = parameter_file
        self.pblimit = pblimit
        self.phasecenter = phasecenter
        self.reffreq = reffreq
        self.restfreq = restfreq
        self.robust = robust
        self.scales = scales
        self.specmode = specmode
        self.spw = spw
        self.start = start
        self.stokes = stokes
        self.threshold = threshold
        self.nsigma = nsigma
        self.uvtaper = uvtaper
        self.uvrange = uvrange
        self.width = width
        self.sensitivity = sensitivity
        self.clean_no_mask_selfcal_image = clean_no_mask_selfcal_image
        self.cycleniter_final_image_nomask = cycleniter_final_image_nomask
        self.vlass_plane_reject_ms = vlass_plane_reject_ms

# tell the infrastructure to give us mstransformed data when possible by
# registering our preference for imaging measurement sets
#api.ImagingMeasurementSetsPreferred.register(EditimlistInputs)


@task_registry.set_equivalent_casa_task('hif_editimlist')
class Editimlist(basetask.StandardTaskTemplate):
    # 'Inputs' will be used later in execute_task().
    #   See h/cli/utils.py and infrastructure/argmagger.py
    Inputs = EditimlistInputs

    # hif_editimlist is a multi-vis task which operates over multiple MSs.
    is_multi_vis_task = True

    def prepare(self):

        inp = self.inputs

        # get the class inputs as a dictionary
        inpdict = inp.as_dict()
        LOG.debug(inp.as_dict())

        # if a file is given, read whatever parameters are defined in the file.
        # note: inputs from the parameter file take precedence over individual task arguements.
        if inp.parameter_file:
            if os.access(inp.parameter_file, os.R_OK):
                with open(inp.parameter_file) as parfile:
                    for line in parfile:
                        # ignore comment lines or lines that don't contain '='
                        if line.startswith('#') or '=' not in line:
                            continue
                        # split key=value into a key, value components
                        parameter, value = line.partition('=')[::2]
                        # strip whitespace
                        parameter = parameter.strip()
                        value = value.strip()
                        # all params come in as strings.  evaluate it to set it to the proper type
                        value = ast.literal_eval(value)

                        # use this information to change the values in inputs
                        LOG.debug("Setting inputdict['{k}'] to {v} {t}".format(k=parameter, v=value, t=type(value)))
                        inpdict[parameter] = value
            else:
                LOG.error('Input parameter file is not readable: {fname}'.format(fname=inp.parameter_file))

        # now construct the list of imaging command parameter lists that must
        # be run to obtain the required images
        result = EditimlistResult()

        # will default to adding a new image list entry
        inpdict.setdefault('editmode', 'add')

        # Use the ms object from the context to change field ids to fieldnames, if needed
        # TODO think about how to handle multiple MSs
        ms = inp.context.observing_run.get_ms(inp.vis[-1])
        fieldnames = []

        if inpdict['field']:
            # assume field entries are either all integers or all strings, but not a mix
            if isinstance(inpdict['field'][0], int):
                fieldobj = ms.get_fields(field_id=inpdict['field'][0])
                for fieldname in fieldobj.name:
                    fieldnames.append(fieldname)
            else:
                for fieldname in inpdict['field']:
                    fieldnames.append(fieldname)

            if len(fieldnames) > 1:
                fieldnames = [','.join(fieldnames)]
        # fieldnames is now a list of fieldnames: ['fieldA', 'fieldB', ...]
        # add quotes to any fieldnames with disallowed characters
        fieldnames = [utils.fieldname_for_casa(fn) for fn in fieldnames]

        imlist_entry = CleanTarget()  # initialize a target structure for clean_list_pending

        img_mode = 'VLASS-QL' if not inpdict['imaging_mode'] else inpdict['imaging_mode']
        result.img_mode = img_mode
        result.editmode = inpdict['editmode'].lower()

        # The default spw range for VLASS is 2~17. hif_makeimages() needs a csv list.
        # We set the imlist_entry spw before the heuristics object because the heursitics class
        # uses it in initialization.
        if img_mode.startswith('VLASS-'):
            if not inpdict['spw']:
                imlist_entry['spw'] = ','.join([str(x) for x in range(2, 18)])
                if img_mode.startswith('VLASS-SE-CUBE'):
                    imlist_entry['spw'] = [str(x) for x in range(2, 18)]
            else:
                if 'MHz' in inpdict['spw']:
                    # map the center frequencies (MHz) to spw ids
                    cfreq_spw = {}
                    spws = ms.get_spectral_windows(science_windows_only=True)
                    for spw_ii in spws:
                        centre_freq = int(spw_ii.centre_frequency.to_units(measures.FrequencyUnits.MEGAHERTZ))
                        spwid = spw_ii.id
                        cfreq_spw[centre_freq] = spwid

                    user_freqs = inpdict['spw'].split(',')
                    spws = []
                    for uf in user_freqs:
                        uf_int = int(uf.replace('MHz', ''))
                        spws.append(cfreq_spw[uf_int])
                    imlist_entry['spw'] = ','.join([str(x) for x in spws])
                else:
                    imlist_entry['spw'] = inpdict['spw']
        else:
            if inpdict['spw'].replace(',', '').replace(' ', '').isdigit():  # with spaces and commas removed
                imlist_entry['spw'] = inpdict['spw']
            else:
                # if these are spw names, translate them to spw ids
                spws = ms.get_spectral_windows(science_windows_only=True)
                tmpspw_str = inpdict['spw']
                for spw_ii in spws:
                    if spw_ii.name in inpdict['spw']:
                        LOG.info('Using spwd id {id} for spw name {name}'.format(id=spw_ii.id, name=spw_ii.name))
                        tmpspw_str = tmpspw_str.replace(spw_ii.name, str(spw_ii.id))
                for spw_jj in inpdict['spw'].replace(' ', '').split(','):
                    if spw_jj in tmpspw_str:  # if spwname hasn't been replaced with an id, then warn
                        LOG.warning('spw name \'{name}\' was not found in {ms}'.format(name=spw_jj, ms=inp.vis[-1]))
                imlist_entry['spw'] = tmpspw_str

        # phasecenter is required user input (not determined by heuristics)
        imlist_entry['phasecenter'] = inpdict['phasecenter']

        iph = imageparams_factory.ImageParamsHeuristicsFactory()

        # note: heuristics.imageparams_base expects 'spw' to be a selection string.
        # For VLASS-SE-CUBE, 'spw' is the representational string of spw group list, e.g. spw="['1,2','3,4,5']"
        th = imlist_entry['heuristics'] = iph.getHeuristics(vislist=inp.vis, spw=str(imlist_entry['spw']),
                                                            observing_run=inp.context.observing_run,
                                                            imagename_prefix=inp.context.project_structure.ousstatus_entity_id,
                                                            proj_params=inp.context.project_performance_parameters,
                                                            imaging_params=inp.context.imaging_parameters,
                                                            processing_intents=inp.context.processing_intents,
                                                            imaging_mode=img_mode)

        # Determine current VLASS-SE-CONT imaging stage (used in heuristics to make decisions)
        # Intended to cover VLASS-SE-CONT, VLASS-SE-CONT-AWP-P001, VLASS-SE-CONT-AWP-P032 modes as of 01.03.2021
        if img_mode.startswith('VLASS-SE-CONT'):
            # If 0 hif_makeimlist results are found, then we are in stage 1
            th.vlass_stage = utils.get_task_result_count(inp.context, 'hif_makeimages') + 1

            # Below method only exists for ImageParamsHeuristicsVlassSeCont and ImageParamsHeuristicsVlassSeContAWPP001
            th.set_user_cycleniter_final_image_nomask(inpdict['cycleniter_final_image_nomask'])

            # PIPE-2834: set custom wprojplanes for VLASS-SE-CONT-AWP modes if speciefied by user
            if img_mode in ('VLASS-SE-CONT', 'VLASS-SE-CONT-AWP', 'VLASS-SE-CONT-AWP2', 'VLASS-SE-CONT-AWPHPG'):
                imlist_entry['wprojplanes'] = inpdict.get('wprojplanes', None)

        # For VLASS-SE-CUBE, we only run hif_makeimages once and reuse most imaging heuristics
        # from SE-CONT-MOSAIC/vlass_stage=3. Therefore, ImageParamsHeuristicsVlassSeCube is constructed
        # as a subclass of ImageParamsHeuristicsVlassSeContMosaic with vlass_stage=3 at its initialization.
        # vlass_stage=3 stays once the workflow starts to create the imaging target list.
        if img_mode.startswith('VLASS-SE-CUBE'):
            th.set_user_cycleniter_final_image_nomask(inpdict['cycleniter_final_image_nomask'])
            # the below statement is redundant and only serves as a reminder that vlass_stage=3 for all VLASS-SE-CUBE heuristics.
            th.vlass_stage = 3

        imlist_entry['threshold'] = inpdict['threshold']
        imlist_entry['hm_nsigma'] = None if inpdict['nsigma'] in (None, -999.0) else float(inpdict['nsigma'])

        if imlist_entry['threshold'] and imlist_entry['hm_nsigma']:
            LOG.warning("Both 'threshold' and 'nsigma' were specified.")

        imlist_entry['pblimit'] = None if inpdict['pblimit'] in (None, -999.0) else inpdict['pblimit']
        imlist_entry['stokes'] = th.stokes() if not inpdict['stokes'] else inpdict['stokes']
        imlist_entry['conjbeams'] = th.conjbeams() if not inpdict['conjbeams'] else inpdict['conjbeams']
        imlist_entry['reffreq'] = th.reffreq() if not inpdict['reffreq'] else inpdict['reffreq']

        # niter_correction is run again in tclean.py
        imlist_entry['niter'] = th.niter() if not inpdict['niter'] else inpdict['niter']
        imlist_entry['cyclefactor'] = inpdict['cyclefactor']
        imlist_entry['cycleniter'] = inpdict['cycleniter']
        imlist_entry['nmajor'] = inpdict['nmajor']
        imlist_entry['cfcache'], imlist_entry['cfcache_nowb'] = th.get_cfcaches(inpdict['cfcache'])
        imlist_entry['scales'] = th.scales() if not inpdict['scales'] else inpdict['scales']
        imlist_entry['uvtaper'] = (th.uvtaper() if not 'uvtaper' in inp.context.imaging_parameters
                                   else inp.context.imaging_parameters['uvtaper']) if not inpdict['uvtaper'] else inpdict['uvtaper']

        imlist_entry['specmode'] = th.specmode() if not inpdict['specmode'] else inpdict['specmode']
        imlist_entry['deconvolver'] = th.deconvolver(
            imlist_entry['specmode'], None) if not inpdict['deconvolver'] else inpdict['deconvolver']
        imlist_entry['mask'] = th.mask() if not inpdict['mask'] else inpdict['mask']
        imlist_entry['pbmask'] = None if not inpdict['pbmask'] else inpdict['pbmask']
        imlist_entry['robust'] = th.robust(specmode=imlist_entry['specmode']
                                           ) if inpdict['robust'] in (None, -999.0) else inpdict['robust']

        imlist_entry['uvrange'], _ = th.uvrange(field=fieldnames[0] if fieldnames else None,
                                                spwspec=imlist_entry['spw'],
                                                specmode=imlist_entry['specmode']) if not inpdict['uvrange'] else inpdict['uvrange']

        LOG.info('RADIUS')
        LOG.info(repr(inpdict['search_radius_arcsec']))
        LOG.info('default={d}'.format(d=not inpdict['search_radius_arcsec']
                                      and not isinstance(inpdict['search_radius_arcsec'], float)
                                      and not isinstance(inpdict['search_radius_arcsec'], int)))
        buffer_arcsec = th.buffer_radius() \
            if (not inpdict['search_radius_arcsec']
                and not isinstance(inpdict['search_radius_arcsec'], float)
                and not isinstance(inpdict['search_radius_arcsec'], int)) else inpdict['search_radius_arcsec']
        LOG.info("{k} = {v}".format(k='search_radius', v=buffer_arcsec))
        result.capture_buffer_size(buffer_arcsec)
        imlist_entry['intent'] = th.intent() if not inpdict['intent'] else inpdict['intent']

        # imlist_entry['datacolumn'] is either None or an non-empty string here based on the current heuristics implementation.
        imlist_entry['datacolumn'] = th.datacolumn() if not inpdict['datacolumn'] else inpdict['datacolumn']
        imlist_entry['nterms'] = th.nterms(imlist_entry['spw']) if not inpdict['nterms'] else inpdict['nterms']

        # Specify the sensitivity value to be used in TcleanInputs
        if 'VLASS' in img_mode:
            # Force sensitivity = 0.0 to disable sensitivity calculation inside hif_tclean()
            imlist_entry['sensitivity'] = 0.0
        else:
            # Assign user input if not None or 0.0; otherwise, set to None for in-flight calculation by hif_tclean()
            imlist_entry['sensitivity'] = inpdict['sensitivity'] if inpdict['sensitivity'] else None

        # ---------------------------------------------------------------------------------- set cell (SRDP ALMA)
        ppb = 5.0  # pixels per beam
        if fieldnames:
            synthesized_beam, _ = th.synthesized_beam(field_intent_list=[[fieldnames[0], 'TARGET']],
                                                        spwspec=imlist_entry['spw'],
                                                        robust=imlist_entry['robust'],
                                                        uvtaper=imlist_entry['uvtaper'],
                                                        pixperbeam=ppb,
                                                        known_beams=inp.context.synthesized_beams,
                                                        force_calc=False, shift=True)
        else:
            synthesized_beam = None

        # inpdict['cell'] can have input of the form ['0.5arcsec', '0.5arcsec'] or '3ppb'
        # It is only a string if the pixel-per-beam value is provided.
        # With pixel-per-beam input, the cell size needs to be calculated using
        # th.cell(), so set inpdict['cell'] to the empty list here to trigger this calculation.
        if inpdict['cell'] and isinstance(inpdict['cell'], str):
            ppb = float(inpdict['cell'].split('ppb')[0])
            inpdict['cell'] = []

        imlist_entry['cell'] = th.cell(beam=synthesized_beam,
                                       pixperbeam=ppb) if not inpdict['cell'] else inpdict['cell']
        # ----------------------------------------------------------------------------------  set imsize (SRDP ALMA)
        largest_primary_beam = th.largest_primary_beam_size(spwspec=imlist_entry['spw'], intent='TARGET')
        fieldids = th.field('TARGET', fieldnames)

        # Fail if there is no field to image. This could occur if a field is requested that is not in the MS.
        # th.field will return [''] if no fields were found in the MS that match any input fields and intents
        # PIPE-2189: fieldnames is an empty list in the case of VLASS imaging.
        if fieldnames and len(fieldids) == 1 and fieldids[0] == '':
            msg = "Field(s): {} not present in MS: {}".format(','.join(fieldnames), ms.name)
            LOG.error(msg)

        if isinstance(inpdict['imsize'], str):
            sfpblimit = float(inpdict['imsize'].split('pb')[0])
            inpdict['imsize'] = []
        else:
            sfpblimit = 0.2

        if inpdict['imsize']:
            # PIPE-2189: take the manually specfied imsize; commonly used by VLASS.
            imlist_entry['imsize'] = inpdict['imsize']
        else:
            if img_mode == 'VLA' and imlist_entry['specmode'] == 'cont':
                # PIPE-675: VLA imsize heuristic update; band dependent FOV in 'cont' specmode.
                imlist_entry['imsize'] = th.imsize(fields=fieldids, cell=imlist_entry['cell'],
                                                   primary_beam=largest_primary_beam, spwspec=imlist_entry['spw'],
                                                   intent=imlist_entry['intent'], specmode=imlist_entry['specmode'])
            else:
                imlist_entry['imsize'] = th.imsize(fields=fieldids, cell=imlist_entry['cell'],
                                                   primary_beam=largest_primary_beam,
                                                   sfpblimit=sfpblimit, intent=imlist_entry['intent'],
                                                   specmode=imlist_entry['specmode'])

        imlist_entry['nchan'] = inpdict['nchan']
        imlist_entry['nbin'] = inpdict['nbin']
        imlist_entry['start'] = inpdict['start']
        imlist_entry['width'] = inpdict['width']

        imlist_entry['restfreq'] = th.restfreq(
            specmode=imlist_entry['specmode'],
            nchan=imlist_entry['nchan'],
            start=imlist_entry['start'],
            width=imlist_entry['width']) if not inpdict['restfreq'] else inpdict['restfreq']

        # for VLASS phasecenter is required user input (not determined by heuristics)
        if inpdict['phasecenter']:
            imlist_entry['phasecenter'] = inpdict['phasecenter']
            imlist_entry['psf_phasecenter'] = inpdict['phasecenter']
        else:
            phasecenter, psf_phasecenter = th.phasecenter(fieldids)
            imlist_entry['phasecenter'] = phasecenter
            imlist_entry['psf_phasecenter'] = psf_phasecenter

        # set the field name list in the image list target
        if fieldnames:
            imlist_entry['field'] = fieldnames[0]
        else:
            # only used for VLASS imaging modes where fieldnames is empty
            if imlist_entry['phasecenter'] not in ['', None]:
                # TODO: remove the dependency on cell size being in arcsec

                # remove brackets and begin/end string characters
                # if cell is a list, get the first string element
                if isinstance(imlist_entry['cell'], type([])):
                    imlist_entry['cell'] = imlist_entry['cell'][0]
                imlist_entry['cell'] = imlist_entry['cell'].strip('[').strip(']')
                imlist_entry['cell'] = imlist_entry['cell'].replace("'", '')
                imlist_entry['cell'] = imlist_entry['cell'].replace('"', '')

                cutout_imsize = inpdict.get('cutout_imsize', None)
                if cutout_imsize is not None:
                    imlist_entry['imsize'] = th.imsize_from_cutout(
                        cutout_imsize, imlist_entry['cell'], largest_primary_beam)
                    imlist_entry['misc_vlass'] = (imlist_entry['misc_vlass'] or {}) | {'cutout_imsize': cutout_imsize}
                    qa_tool = casa_tools.quanta
                    dist_arcsec = [qa_tool.tos(qa_tool.mul(imlist_entry['cell'], ct_size/2.0)) for ct_size in cutout_imsize]
                else:
                    # We always search for fields in 1sq degree with a surrounding buffer
                    mosaic_side_arcsec = 3600  # 1 degree
                    dist = (mosaic_side_arcsec / 2.) + float(buffer_arcsec)
                    dist_arcsec = str(dist) + 'arcsec'

                LOG.info("{k} = {v}".format(k='dist_arcsec', v=dist_arcsec))

                # PIPE-1948/PIPE-2004: we updated the field select algorithm for VLASS-PL2023.
                # * restrict field intents to 'TARGET'
                # * restrict field names to beginning with '0', '1', '2', or 'T' (e.g. the NCP field 'T32t02.NCP')
                #   note: we also consider rge double quote possibility because field names might be protected in
                #   the name strings of Field domain objects.
                # * use spherical sky offsets to select fields based on positions.
                found_fields_per_ms = th.select_fields(
                    offsets=dist_arcsec,
                    intent='TARGET',
                    phasecenter=imlist_entry['phasecenter'],
                    name='0*,"0*,1*,"1*,2*,"2*,T*,"T*',
                )

                # Build lists of vis and fields that have good selection
                vis_field_pairs = [
                    (th.vislist[idx], ','.join(str(x) for x in found_fields))
                    for idx, found_fields in enumerate(found_fields_per_ms)
                    if found_fields
                ]

                if vis_field_pairs:
                    vis_list, field_list = zip(*vis_field_pairs)
                    imlist_entry['vis'] = list(vis_list)
                    imlist_entry['field'] = list(field_list)

        if not imlist_entry['spw']:  # could be None or an empty string
            LOG.warning('spw is not specified')   # probably should raise an error rather than warning? - will likely fail later anyway
            imlist_entry['spw'] = None

        if not imlist_entry['field']:
            LOG.warning('field is not specified')   # again, should probably raise an error, as it will eventually fail anyway
            imlist_entry['field'] = None

        # validate specmode
        if imlist_entry['specmode'] not in ('mfs', 'cont', 'cube', 'repBW'):
            msg = 'specmode must be one of "mfs", "cont", "cube", or "repBW"'
            LOG.error(msg)
            result.error = True
            result.error_msg = msg
            return result

        if not img_mode.startswith('VLASS'):
            # this block is only executed for non-VLASS data
            if imlist_entry['datacolumn'] in (None, ''):
                # if datacolumn is not specified by the user input or heuristics, we need to determine the datacolumn
                # from the list of datatypes to consider in the order of preference.
                specmode_datatypes = DataType.get_specmode_datatypes(imlist_entry['intent'], imlist_entry['specmode'])
                # PIPE-1798: filter the list to only include the one(s) starting with the user supplied restriction str, i.e., inputs.datatype.
                if isinstance(inpdict['datatype'], str):
                    specmode_datatypes = [dt for dt in specmode_datatypes if dt.name.startswith(inpdict['datatype'].upper())]
                # loop over the datatype candidate list find the first one that appears in the given (source,spw) combinations.
                for dtype in specmode_datatypes:
                    datacolumn_name = ms.get_data_column(dtype, imlist_entry['field'], imlist_entry['spw'])
                    if datacolumn_name in ('DATA', 'CORRECTED_DATA'):
                        imlist_entry['datatype'] = imlist_entry['datatype_info'] = dtype.name
                        if datacolumn_name == 'DATA':
                            imlist_entry['datacolumn'] = 'data'
                        if datacolumn_name == 'CORRECTED_DATA':
                            imlist_entry['datacolumn'] = 'corrected'
                        break
                    else:
                        LOG.debug(f'No valid datacolumn is associated with the  data selection: '
                                  f"datatype={dtype!r}, field={imlist_entry['field']!r}, spw={imlist_entry['spw']!r}")
                specmode_datatypes_str = ', '.join([dt.name for dt in specmode_datatypes])
                if imlist_entry['datatype'] is None:
                    LOG.warning(
                        f"No data from field={imlist_entry['field']!r} / spw={imlist_entry['spw']!r} is "
                        f'in the allowed datatype(s): {specmode_datatypes_str}.'
                        ' No clean target will be added.')
                    return result
            else:
                # if datacolumn is specified, pick it and label cleantarget with the corresponding datatype (when available).
                ms_datacolumn = imlist_entry['datacolumn'].upper()
                if ms_datacolumn == 'CORRECTED':
                    ms_datacolumn = 'CORRECTED_DATA'
                dtype = ms.get_data_type(ms_datacolumn, imlist_entry['field'], imlist_entry['spw'])
                LOG.warning(
                    f'datacolumn={imlist_entry["datacolumn"]!r} is selected based on user or heuristic input, which overrides the datatype-based selection.')
                if dtype is None:
                    LOG.warning(f'No valid datatype is associated with the data selection: '
                                f"datacolumn={imlist_entry['datacolumn']!r}, field={imlist_entry['field']!r}, spw={imlist_entry['spw']!r}")
                else:
                    imlist_entry['datatype'] = imlist_entry['datatype_info'] = dtype.name

        # PIPE-1710/PIPE-1474: append a corresponding suffix to the image file name according to the datatype of selected visibilities.
        datatype_suffix = None
        if isinstance(imlist_entry['datatype'], str):
            if imlist_entry['datatype'].lower().startswith('selfcal'):
                datatype_suffix = 'selfcal'
            if imlist_entry['datatype'].lower().startswith('regcal'):
                datatype_suffix = 'regcal'

        imlist_entry['gridder'] = th.gridder(imlist_entry['intent'], imlist_entry['field']
                                             ) if not inpdict['gridder'] else inpdict['gridder']
        imlist_entry['imagename'] = th.imagename(intent=imlist_entry['intent'], field=imlist_entry['field'],
                                                 spwspec=imlist_entry['spw'], specmode=imlist_entry['specmode'],
                                                 band=None, datatype=datatype_suffix) if not inpdict['imagename'] else inpdict['imagename']

        # In this case field and spwspec is not needed in the filename, furthermore, imaging is done in multiple stages
        # prepend the STAGENUMBER string in order to differentiate them. In TcleanInputs class this is replaced by the
        # actual stage number string.
        # Intended to cover VLASS-SE-CONT, VLASS-SE-CONT-AWP-P001, VLASS-SE-CONT-AWP-P032,
        # VLASS-SE-CONT-MOSAIC, and VLASS-SE-CUBE as of 05/03/2022
        if img_mode.startswith('VLASS-SE-CONT') or img_mode.startswith('VLASS-SE-CUBE'):
            imagename = th.imagename(intent=imlist_entry['intent'], field=None, spwspec=None,
                                     specmode=imlist_entry['specmode'],
                                     band=None) if not inpdict['imagename'] else inpdict['imagename']
            imlist_entry['imagename'] = 's{}.{}'.format('STAGENUMBER', imagename)
            # Try to obtain previously computed mask name
            imlist_entry['mask'] = th.mask(results_list=inp.context.results,
                                           clean_no_mask=inpdict['clean_no_mask_selfcal_image']) if not inpdict['mask'] \
                else inpdict['mask']


        for key, value in imlist_entry.items():
            LOG.info("%s = %r", key, value)

        try:
            if imlist_entry['field']:
                result.add_target(imlist_entry, self.inputs)
            else:
                raise TypeError
        except TypeError:
            LOG.error('No fields to image.')

        # check for required user inputs
        if not imlist_entry['imagename']:
            LOG.error('No imagename provided.')

        if not imlist_entry['phasecenter']:
            LOG.error('No phasecenter provided.')

        return result

    def analyse(self, result):
        return result
