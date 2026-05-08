import collections
import copy
import os

import numpy as np

import pipeline.domain.measures as measures
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.contfilehandler as contfilehandler
import pipeline.infrastructure.mpihelpers as mpihelpers
import pipeline.infrastructure.utils as utils
import pipeline.infrastructure.vdp as vdp
from pipeline.domain import DataType
from pipeline.hif.heuristics import findcont
from pipeline.infrastructure import casa_tasks, casa_tools, task_registry

from .resultobjects import FindContResult

LOG = infrastructure.get_logger(__name__)

FINDCONT_BASE_PPB = 5.0
FINDCONT_12M_TARGET_PPB = 4.0
FINDCONT_7M_TARGET_PPB = 4.0
FINDCONT_MIN_IMSIZE = 64

FINDCONT_L80_MIN_M = 100.0
FINDCONT_L80_PIVOT_M = 250.0
FINDCONT_L80_MAX_M = 8000.0
FINDCONT_L80_MIN_IMSIZE_RATIO = 1.5
FINDCONT_L80_PIVOT_IMSIZE_RATIO = 2.5
FINDCONT_L80_MAX_IMSIZE_RATIO = 3.0
FINDCONT_ALPHA_POWER = np.log(
    (FINDCONT_L80_PIVOT_IMSIZE_RATIO - FINDCONT_L80_MIN_IMSIZE_RATIO) /
    (FINDCONT_L80_MAX_IMSIZE_RATIO - FINDCONT_L80_MIN_IMSIZE_RATIO)
) / np.log(
    (np.log(FINDCONT_L80_PIVOT_M) - np.log(FINDCONT_L80_MIN_M)) /
    (np.log(FINDCONT_L80_MAX_M) - np.log(FINDCONT_L80_MIN_M))
)


def _coarse_findcont_parameters(context, image_heuristics, vislist, cell, imsize, spw=None):
    qa = casa_tools.quanta
    mses = [context.observing_run.get_ms(vis) for vis in vislist]
    array_descs = image_heuristics.arrays(vislist)
    size_mitigation_parameters = getattr(context, 'size_mitigation_parameters', {}) or {}

    def ppb_mitigation_for(spw_id=None):
        mitigation = None
        if spw_id is not None:
            mitigation = size_mitigation_parameters.get('multi_target_size_mitigation', {}).get(spw_id, {}).get('hm_cell')
        mitigation = mitigation or size_mitigation_parameters.get('hm_cell')
        if isinstance(mitigation, (list, tuple)):
            mitigation = next((item for item in mitigation if isinstance(item, str) and 'ppb' in item), None)
        if isinstance(mitigation, str) and 'ppb' in mitigation:
            try:
                return float(mitigation.split('ppb', 1)[0])
            except ValueError:
                pass
        return FINDCONT_BASE_PPB

    ppb_mitigation = ppb_mitigation_for(spw)
    ppb_scale = ppb_mitigation / FINDCONT_BASE_PPB

    def scale_cell(quantity_or_list, ratio):
        if quantity_or_list in (None, '', []):
            return quantity_or_list
        if isinstance(quantity_or_list, list):
            return [scale_cell(item, ratio) for item in quantity_or_list]

        quantity = qa.quantity(quantity_or_list)
        scaled_quantity = qa.mul(quantity, ratio)
        scaled_value = np.asarray(qa.getvalue(scaled_quantity)).item()
        return '%.2g%s' % (scaled_value, qa.getunit(scaled_quantity))

    def scale_imsize(size_or_list, ratio, minimum=None):
        if size_or_list in (None, '', []):
            return size_or_list
        if isinstance(size_or_list, (list, tuple)):
            return [scale_imsize(size, ratio, minimum=minimum) for size in size_or_list]
        scaled = int(utils.round_half_up(float(size_or_list) / ratio))
        if minimum is not None:
            scaled = max(scaled, minimum)
        return casa_tools.synthesisutils.getOptimumSize(max(1, scaled))

    def taper_arcsec(local_cell, ratio):
        if local_cell in (None, '', []):
            return None
        first_cell = local_cell[0] if isinstance(local_cell, list) else local_cell
        cell_arcsec = float(np.asarray(qa.getvalue(qa.convert(qa.quantity(first_cell), 'arcsec'))).item())
        new_cell_arcsec = cell_arcsec * ratio
        target_beam_arcsec = FINDCONT_12M_TARGET_PPB * new_cell_arcsec
        input_beam_arcsec = ppb_mitigation * cell_arcsec
        taper_arcsec_value = np.sqrt(max(0.0, target_beam_arcsec**2 - input_beam_arcsec**2))
        return ['%.2garcsec' % taper_arcsec_value]

    if '7m' in array_descs:
        imsize_ratio = (FINDCONT_BASE_PPB / FINDCONT_7M_TARGET_PPB) * ppb_scale
        return {
            'weighting': 'briggs',
            'robust': 1.0,
            'perchanweightdensity': False,
            'mosweight': False,
            'cell': scale_cell(cell, imsize_ratio),
            'imsize': scale_imsize(imsize, imsize_ratio, minimum=FINDCONT_MIN_IMSIZE),
            'uvtaper': None,
        }

    baselines = [
        ms.antenna_array.baselines_m for ms in mses
        if ms.antenna_array is not None and len(ms.antenna_array.baselines_m) > 0
    ]
    if not baselines:
        raise ValueError('Could not determine L80 for coarse findcont imaging')

    l80 = float(np.percentile(np.concatenate(baselines), 80))
    x = (np.log(l80) - np.log(FINDCONT_L80_MIN_M)) / (np.log(FINDCONT_L80_MAX_M) - np.log(FINDCONT_L80_MIN_M))
    imsize_ratio = FINDCONT_L80_MIN_IMSIZE_RATIO + (
        FINDCONT_L80_MAX_IMSIZE_RATIO - FINDCONT_L80_MIN_IMSIZE_RATIO
    ) * (float(np.clip(x, 0.0, 1.0)) ** FINDCONT_ALPHA_POWER)
    imsize_ratio *= ppb_scale

    return {
        'weighting': 'briggs',
        'robust': 1.0,
        'perchanweightdensity': False,
        'mosweight': False,
        'cell': scale_cell(cell, imsize_ratio),
        'imsize': scale_imsize(imsize, imsize_ratio, minimum=FINDCONT_MIN_IMSIZE),
        'uvtaper': taper_arcsec(cell, imsize_ratio),
    }


class FindContInputs(vdp.StandardInputs):
    # Must use empty data type list to allow for user override and
    # automatic determination depending on specmode, field and spw.
    processing_data_type = []

    hm_perchanweightdensity = vdp.VisDependentProperty(default=None)
    hm_weighting = vdp.VisDependentProperty(default=None)
    hm_findcontmode = vdp.VisDependentProperty(default='coarse')
    datacolumn = vdp.VisDependentProperty(default='')
    parallel = vdp.VisDependentProperty(default='automatic')

    @hm_findcontmode.convert
    def hm_findcontmode(self, value):
        allowed = ('coarse', 'normal')
        if value not in allowed:
            m = ', '.join(('{!r}'.format(i) for i in allowed))
            raise ValueError(
                'Value not in allowed value set ({!s}): {!r}'.format(m, value)
            )
        return value

    @vdp.VisDependentProperty(null_input=['', None, {}])
    def target_list(self):
        # Note that the deepcopy is necessary to avoid changing the
        # context's clean_list inadvertently when removing the heuristics
        # objects from the inputs' clean_list.
        return copy.deepcopy(self.context.clean_list_pending)

    # docstring and type hints: supplements hif_findcont
    def __init__(self, context, output_dir=None, vis=None, target_list=None, hm_mosweight=None,
                 hm_perchanweightdensity=None, hm_weighting=None, hm_findcontmode=None,
                 datacolumn=None, parallel=None):
        """Initialize Inputs.

        Args:
            context: Pipeline context object containing state information.

            output_dir: Output directory.
                Defaults to None, which corresponds to the current working directory.

            vis: The list of input MeasurementSets. Defaults to the list of MeasurementSets specified in the <hifa,hifv>_importdata task.
                '': use all MeasurementSets in the context

                Examples: 'ngc5921.ms', ['ngc5921a.ms', ngc5921b.ms', 'ngc5921c.ms']

            target_list: Dictionary specifying targets to be imaged; blank will read list from context.

            hm_mosweight: Mosaic weighting. Defaults to '' to enable the automatic heuristics calculation.
                Can be set to True or False manually.

            hm_perchanweightdensity: Calculate the weight density for each channel independently.
                Defaults to '' to enable the automatic heuristics calculation. Can be set to True or False manually.

            hm_weighting: Weighting scheme (natural,uniform,briggs,briggsabs[experimental],briggsbwtaper[experimental])

            hm_findcontmode: Continuum-finding imaging mode. "coarse" applies the new fast local override
                and "normal" preserves the previous-cycle behavior.

            datacolumn: Data column to image. Only to be used for manual overriding when the automatic choice by data type is not appropriate.

            parallel: Use CASA/tclean built-in parallel imaging when possible.

                Options: ``'automatic'``, ``'true'``, ``'false'``, ``True``, ``False``

                Default: ``'automatic'``
        """
        super().__init__()
        self.context = context
        self.output_dir = output_dir
        self.vis = vis

        self.target_list = target_list
        self.hm_mosweight = hm_mosweight
        self.hm_perchanweightdensity = hm_perchanweightdensity
        self.hm_weighting = hm_weighting
        self.hm_findcontmode = hm_findcontmode
        self.datacolumn = datacolumn
        self.parallel = parallel


@task_registry.set_equivalent_casa_task('hif_findcont')
class FindCont(basetask.StandardTaskTemplate):
    Inputs = FindContInputs

    is_multi_vis_task = True

    def prepare(self):
        inputs = self.inputs
        context = self.inputs.context
        coarse_mode = inputs.hm_findcontmode == 'coarse'

        # Check if this stage should be skipped
        if self._skip_findcont():
            # only triggered for VLA-PI pieplein (not for ALMA)
            result = FindContResult({}, {}, '', 0, 0, [], {})
            return result

        # Check for size mitigation errors.
        if 'status' in inputs.context.size_mitigation_parameters and \
                inputs.context.size_mitigation_parameters['status'] == 'ERROR':
            result = FindContResult({}, {}, '', 0, 0, [], {})
            result.mitigation_error = True
            return result

        qaTool = casa_tools.quanta

        # make sure inputs.vis is a list, even if it is one that contains a
        # single measurement set
        if not isinstance(inputs.vis, list):
            inputs.vis = [inputs.vis]

        if inputs.datacolumn not in (None, ''):
            datacolumn = inputs.datacolumn
        else:
            datacolumn = ''

        # Select the correct vis list
        if inputs.vis in ('', [''], [], None):
            datatypes = [DataType.SELFCAL_CONTLINE_SCIENCE, DataType.REGCAL_CONTLINE_SCIENCE, DataType.REGCAL_CONTLINE_ALL, DataType.RAW]

            ms_objects_and_columns, selected_datatype = context.observing_run.get_measurement_sets_of_type(dtypes=datatypes, msonly=False)

            if ms_objects_and_columns == collections.OrderedDict():
                LOG.error('No data found for continuum finding.')
                result = FindContResult({}, {}, '', 0, 0, [], {})
                return result

            LOG.info(f'Using data type {str(selected_datatype).split(".")[-1]} for continuum finding.')
            if selected_datatype == DataType.RAW:
                LOG.warning('Falling back to raw data for continuum finding.')

            columns = list(ms_objects_and_columns.values())
            if not all(column == columns[0] for column in columns):
                LOG.warning(
                    f'Data type based column selection changes among MSes: {",".join(f"{k.basename}: {v}" for k, v in ms_objects_and_columns.items())}.')

            if datacolumn != '':
                LOG.info(
                    f'Manual override of datacolumn to {datacolumn}. Data type based datacolumn would have been "{"data" if columns[0] == "DATA" else "corrected"}".')
            else:
                if columns[0] == 'DATA':
                    datacolumn = 'data'
                elif columns[0] == 'CORRECTED_DATA':
                    datacolumn = 'corrected'
                else:
                    LOG.warning(f'Unknown column name {columns[0]}')
                    datacolumn = ''

            inputs.vis = [k.basename for k in ms_objects_and_columns.keys()]

        findcont_heuristics = findcont.FindContHeuristics(context)

        contfile_handler = contfilehandler.ContFileHandler(context.contfile)
        cont_ranges = contfile_handler.read()

        result_cont_ranges = {}
        joint_mask_names = {}
        momDiffSNRs = {}

        num_found = 0
        num_total = 0
        single_range_channel_fractions = []
        coarse_fallbacks = []
        for i, target in enumerate(inputs.target_list):
            target_coarse_params = None
            for spwid in target['spw'].split(','):
                source_name = utils.dequote(target['field'])
                spw_name = context.observing_run.virtual_science_spw_ids[int(spwid)]

                # get continuum ranges dict for this source, also setting it if accessed for first time
                source_continuum_ranges = result_cont_ranges.setdefault(source_name, {})

                # get continuum ranges list for this source and spw, also setting them if accessed for first time
                cont_ranges_source_spw = cont_ranges['fields'].setdefault(source_name, {}).setdefault(spwid, {'spwname': spw_name, 'ranges': [], 'flags': []})

                if len(cont_ranges_source_spw['ranges']) > 0:
                    LOG.info('Using existing selection {!r} for field {!s}, '
                             'spw {!s}'.format(cont_ranges_source_spw['ranges'], source_name, spwid))
                    source_continuum_ranges[spwid] = {
                        'cont_ranges': cont_ranges_source_spw,
                        'plotfile': 'none',
                        'status': 'OLD'
                    }
                    if cont_ranges_source_spw['ranges'] != ['NONE']:
                        num_found += 1

                else:
                    LOG.info('Determining continuum ranges for field %s, spw %s' % (source_name, spwid))

                    findcont_basename = '%s.I.findcont' % (os.path.basename(target['imagename']).replace(
                        'spw%s' % (target['spw'].replace(',', '_')),
                        'spw%s' % spwid
                    ).replace('STAGENUMBER', str(context.stage)))

                    # Determine the gridder mode
                    image_heuristics = target['heuristics']
                    gridder = image_heuristics.gridder(target['intent'], target['field'])
                    if inputs.hm_mosweight not in (None, ''):
                        mosweight = inputs.hm_mosweight
                    elif target['mosweight'] not in (None, ''):
                        mosweight = target['mosweight']
                    else:
                        mosweight = image_heuristics.mosweight(target['intent'], target['field'])

                    # Determine weighting and perchanweightdensity parameters
                    if inputs.hm_weighting in (None, ''):
                        weighting = image_heuristics.weighting('cube')
                        perchanweightdensity = image_heuristics.perchanweightdensity('cube')
                    else:
                        weighting = inputs.hm_weighting
                        perchanweightdensity = inputs.hm_perchanweightdensity

                    # Usually the inputs value takes precedence over the one from the target list.
                    # For PIPE-557 it was necessary to fill target['vis'] in hif_makeimlist to filter
                    # out fully flagged selections. Using the default vislist one would have to
                    # re-determine all dependendent parameters such as "antenna", etc. here. Most
                    # likely the use case of defining an explicit vislist for hif_findcont will
                    # happen very rarely if at all. Thus changing the paradigm here for now.
                    if target['vis']:
                        vislist = target['vis']
                        scanidlist, _ = image_heuristics.get_scanidlist(target['vis'], target['field'],
                                                                        target['intent'])
                    else:
                        scanidlist, visindexlist = image_heuristics.get_scanidlist(inputs.vis, target['field'],
                                                                                   target['intent'])
                        # Remove MSs that do not contain data for the given field(s)
                        vislist = [inputs.vis[i] for i in visindexlist]

                    if coarse_mode and target_coarse_params is None:
                        try:
                            target_coarse_params = _coarse_findcont_parameters(
                                context, image_heuristics, vislist, target['cell'], target['imsize'], spw=target['spw']
                            )
                        except Exception as exc:
                            LOG.warning(
                                'Unable to derive coarse findcont parameters for field %s: %s. '
                                'Using previous-cycle imaging parameters for this target.',
                                target['field'], exc
                            )
                            coarse_fallbacks.append({
                                'field': target['field'],
                                'spw': target['spw'],
                                'message': str(exc),
                            })

                    # Need to make an LSRK or SOURCE/REST (ephemeris sources) cube to get
                    # the real ranges in the source frame.
                    # The LSRK or SOURCE/REST ranges will need to be translated to the
                    # individual TOPO ranges for the involved MSs in hif_tclean.
                    if image_heuristics.is_eph_obj(target['field']):
                        frame = 'REST'
                    else:
                        frame = 'LSRK'

                    # To avoid noisy edge channels, use only the LSRK or SOURCE/REST frequency
                    # intersection and skip one channel on either end.
                    # Use only the current spw ID here !
                    if0, if1, channel_width = image_heuristics.freq_intersection(vislist, target['field'], target['intent'], spwid, frame)
                    if (if0 == -1) or (if1 == -1):
                        LOG.error('No %s frequency intersect among selected MSs for Field %s '
                                  'SPW %s' % (frame, target['field'], spwid))
                        cont_ranges['fields'][source_name][spwid]['spwname'] = spw_name
                        cont_ranges['fields'][source_name][spwid]['ranges'] = ['NONE']
                        cont_ranges['fields'][source_name][spwid]['flags'] = []
                        result_cont_ranges[source_name][spwid] = {
                            'cont_ranges': cont_ranges['fields'][source_name][spwid],
                            'plotfile': 'none',
                            'status': 'NEW'
                        }
                        continue

                    # Check for manually supplied values
                    if0_auto = if0
                    if1_auto = if1
                    channel_width_auto = channel_width

                    if target['start'] != '':
                        if0 = qaTool.convert(target['start'], 'Hz')['value']
                        if if0 < if0_auto:
                            LOG.error('Supplied start frequency (%s GHz) < f_low_native (%s GHz) for Field %s '
                                      'SPW %s' % (if0/1e9, if0_auto/1e9, target['field'], target['spw']))
                            continue
                        LOG.info('Using supplied start frequency %s' % (target['start']))

                    if target['width'] != '' and target['nbin'] not in (None, -1):
                        LOG.error('Field %s SPW %s: width and nbin are mutually exclusive' % (target['field'],
                                                                                              target['spw']))
                        continue

                    if target['width'] != '':
                        channel_width_manual = qaTool.convert(target['width'], 'Hz')['value']
                        if channel_width_manual < channel_width_auto:
                            LOG.error(
                                'User supplied channel width (%s MHz) is smaller than the native value (%s MHz) '
                                'for Field %s SPW %s',
                                channel_width_manual / 1e6,
                                channel_width_auto / 1e6,
                                target['field'],
                                target['spw'],
                            )
                            continue
                        LOG.info('Using supplied width %s' % (target['width']))
                        channel_width = channel_width_manual
                        if channel_width > channel_width_auto:
                            target['nbin'] = int(utils.round_half_up(channel_width / channel_width_auto) + 0.5)
                    elif target['nbin'] not in (None, -1):
                        LOG.info('Applying binning factor %d' % (target['nbin']))
                        channel_width *= target['nbin']

                    # Get real spwid
                    ref_ms = context.observing_run.get_ms(vislist[0])
                    real_spwid = context.observing_run.virtual2real_spw_id(int(spwid), ref_ms)
                    real_spwid_obj = ref_ms.get_spectral_window(real_spwid)

                    if image_heuristics.is_eph_obj(target['field']):
                        # Determine extra channels to skip for ephemeris objects to
                        # account for fast moving objects.
                        centre_frequency_TOPO = float(real_spwid_obj.centre_frequency.to_units(measures.FrequencyUnits.HERTZ))
                        channel_width_freq_TOPO = float(real_spwid_obj.channels[0].getWidth().to_units(measures.FrequencyUnits.HERTZ))
                        freq0 = qaTool.quantity(centre_frequency_TOPO, 'Hz')
                        freq1 = qaTool.quantity(centre_frequency_TOPO + channel_width_freq_TOPO, 'Hz')
                        channel_width_velo_TOPO = float(qaTool.getvalue(qaTool.convert(utils.frequency_to_velocity(freq1, freq0), 'km/s'))[0])
                        # Skip 1 km/s
                        extra_skip_channels = int(np.ceil(1.0 / abs(channel_width_velo_TOPO)))
                    else:
                        extra_skip_channels = 0

                    if target['nchan'] not in (None, -1):
                        if1 = if0 + channel_width * target['nchan']
                        if if1 > if1_auto:
                            LOG.error('Calculated stop frequency (%s GHz) > f_high_native (%s GHz) for Field %s '
                                      'SPW %s' % (if1/1e9, if1_auto/1e9, target['field'], target['spw']))
                            continue
                        LOG.info('Using supplied nchan %d' % (target['nchan']))
                        nchan = target['nchan']
                    else:
                        # Skip edge channels and extra channels if no nchan is supplied.
                        # Adjust to binning since the normal nchan heuristics already includes it.
                        if target['nbin'] not in (None, -1):
                            nchan = int(utils.round_half_up((if1 - if0) / channel_width - 2)) - 2 * int(extra_skip_channels // target['nbin'])
                        else:
                            nchan = int(utils.round_half_up((if1 - if0) / channel_width - 2)) - 2 * extra_skip_channels

                    if target['start'] == '':
                        # tclean interprets the start frequency as the center of the
                        # first channel. We have, however, an edge to edge range.
                        # Thus shift by 0.5 channels if no start is supplied.
                        # Additionally skipping the edge channel (cf. "- 2" above)
                        # means a correction of 1.5 channels.
                        if target['nbin'] not in (None, -1):
                            start = '%.10fGHz' % ((if0 + (1.5 + extra_skip_channels) * channel_width / target['nbin']) / 1e9)
                        else:
                            start = '%.10fGHz' % ((if0 + (1.5 + extra_skip_channels) * channel_width) / 1e9)
                    else:
                        start = target['start']

                    width = '%.7fMHz' % (channel_width / 1e6)

                    parallel = mpihelpers.parse_mpi_input_parameter(inputs.parallel)

                    real_spwsel = context.observing_run.get_real_spwsel([str(spwid)]*len(vislist), vislist)

                    # Set special phasecenter, frame and specmode for ephemeris objects.
                    # Needs to be done here since the explicit coordinates are
                    # used in heuristics methods upstream.
                    if image_heuristics.is_eph_obj(target['field']):
                        phasecenter = 'TRACKFIELD'
                        psf_phasecenter = None
                        # 'REST' does not yet work (see CAS-8965, CAS-9997)
                        #outframe = 'REST'
                        outframe = ''
                        specmode = 'cubesource'
                    else:
                        phasecenter = target['phasecenter']
                        if gridder == 'mosaic' and target['psf_phasecenter'] != target['phasecenter']:
                            psf_phasecenter = target['psf_phasecenter']
                        else:
                            psf_phasecenter = None
                        outframe = 'LSRK'
                        specmode = 'cube'

                    # PIPE-107 requests using a fixed robust value of 1.0.
                    robust = 1.0
                    coarse_cell = target['cell']
                    coarse_imsize = target['imsize']
                    coarse_weighting = weighting
                    coarse_perchanweightdensity = perchanweightdensity
                    coarse_mosweight = mosweight
                    coarse_robust = robust
                    coarse_uvtaper = None

                    if target['uvtaper'] not in ([], None):
                        uvtaper = target['uvtaper']
                    else:
                        uvtaper = None
                    coarse_uvtaper = uvtaper

                    if coarse_mode and target_coarse_params is not None:
                        coarse_weighting = target_coarse_params['weighting']
                        coarse_perchanweightdensity = target_coarse_params['perchanweightdensity']
                        coarse_mosweight = target_coarse_params['mosweight']
                        coarse_robust = target_coarse_params['robust']
                        coarse_cell = target_coarse_params['cell']
                        coarse_imsize = target_coarse_params['imsize']
                        coarse_uvtaper = target_coarse_params['uvtaper']

                    if target['uvrange'] not in (None, [], ''):
                        uvrange = target['uvrange']
                    else:
                        uvrange = None

                    if target['antenna'] not in ([], None):
                        antenna = target['antenna']
                    else:
                        antenna = None

                    if target['usepointing'] not in (None,):
                        usepointing = target['usepointing']
                    else:
                        usepointing = None

                    job = casa_tasks.tclean(vis=vislist, imagename=findcont_basename, datacolumn=datacolumn,
                                            antenna=antenna, spw=real_spwsel,
                                            intent=utils.to_CASA_intent(inputs.ms[0], target['intent']),
                                            field=target['field'], start=start, width=width, nchan=nchan,
                                            outframe=outframe, scan=scanidlist, specmode=specmode, gridder=gridder,
                                            mosweight=coarse_mosweight, perchanweightdensity=coarse_perchanweightdensity,
                                            pblimit=0.2, niter=0, threshold='0mJy', deconvolver='hogbom',
                                            interactive=False, imsize=coarse_imsize, cell=coarse_cell,
                                            phasecenter=phasecenter, psfphasecenter=psf_phasecenter,
                                            stokes='I', weighting=coarse_weighting, robust=coarse_robust, uvrange=uvrange,
                                            uvtaper=coarse_uvtaper,
                                            npixels=0, restoration=False, restoringbeam=[], pbcor=False,
                                            usepointing=usepointing, savemodel='none', parallel=parallel,
                                            fullsummary=False)
                    self._executor.execute(job)

                    # Try detecting continuum frequency ranges

                    # Determine the representative source name and spwid for the ms
                    repsource_name, repsource_spwid = ref_ms.get_representative_source_spw()

                    # Determine reprBW mode
                    repr_target, _, repr_spw, _, reprBW_mode, real_repr_target, _, _, _, _ = image_heuristics.representative_target()
                    real_repr_spw = context.observing_run.virtual2real_spw_id(int(repr_spw), ref_ms)
                    real_repr_spw_obj = ref_ms.get_spectral_window(real_repr_spw)

                    if reprBW_mode in ['nbin', 'repr_spw']:
                        # Approximate reprBW with nbin
                        physicalBW_of_1chan = float(real_repr_spw_obj.channels[0].getWidth().convert_to(measures.FrequencyUnits.HERTZ).value)
                        reprBW_nbin = int(qaTool.getvalue(qaTool.convert(repr_target[2], 'Hz'))[0]/physicalBW_of_1chan + 0.5)
                    else:
                        reprBW_nbin = 1

                    spw_transitions = ref_ms.get_spectral_window(real_spwid).transitions
                    single_continuum = any(['Single_Continuum' in t for t in spw_transitions])
                    # PIPE-1855: use spectralDynamicRangeBandWidth from SBSummary if available
                    dynrange_bw = ref_ms.science_goals.get('spectralDynamicRangeBandWidth', None)

                    if dynrange_bw is not None:  # None means that a value was not provided, and it should remain None
                        dynrange_bw = qaTool.tos(dynrange_bw)

                    (cont_ranges_and_flags, png, single_range_channel_fraction, warning_strings, joint_mask_name, momDiffSNR) = \
                        findcont_heuristics.find_continuum(dirty_cube='%s.residual' % findcont_basename,
                                                           pb_cube='%s.pb' % findcont_basename,
                                                           psf_cube='%s.psf' % findcont_basename,
                                                           single_continuum=single_continuum,
                                                           is_eph_obj=image_heuristics.is_eph_obj(target['field']),
                                                           ref_ms_name=ref_ms.name,
                                                           nbin=reprBW_nbin,
                                                           dynrange_bw=dynrange_bw)

                    joint_mask_names[(source_name, spwid)] = joint_mask_name
                    momDiffSNRs[(source_name, spwid)] = momDiffSNR

                    # PIPE-74
                    if single_range_channel_fraction < 0.05:
                        LOG.warning('Only a single narrow range of channels was found for continuum in '
                                    '{field} in spw {spw}, so the continuum subtraction '
                                    'may be poor for that spw.'.format(field=target['field'], spw=spwid))

                    # Internal findContinuum warnings
                    for warning_msg in warning_strings:
                        # PIPE-2158: Exclude empty strings
                        if warning_msg:
                            LOG.warning('Field {field}, spw {spw}: {warning_msg}'.format(field=target['field'], spw=spwid, warning_msg=warning_msg))

                    is_repsource = (repsource_name == target['field']) and (repsource_spwid == spwid)
                    chanfrac = {'fraction'    : single_range_channel_fraction,
                                'field'       : target['field'],
                                'spw'         : spwid,
                                'is_repsource': is_repsource}

                    single_range_channel_fractions.append(chanfrac)

                    cont_ranges['fields'][source_name][spwid].update(cont_ranges_and_flags)

                    source_continuum_ranges[spwid] = {
                        'cont_ranges': cont_ranges_and_flags,
                        'flags': [],
                        'plotfile': png,
                        'status': 'NEW'
                    }

                    if cont_ranges_and_flags['ranges'] not in [['NONE'], [''], []]:
                        num_found += 1

                num_total += 1

        result = FindContResult(result_cont_ranges, cont_ranges, joint_mask_names, num_found, num_total, single_range_channel_fractions, momDiffSNRs)
        result.coarse_mode_fallbacks = coarse_fallbacks

        return result

    def analyse(self, result):
        return result

    def _skip_findcont(self) -> bool:
        """Check if we can proceed with the continuum finding heuristics.

        Note: this is only relevant for VLA to detect if we should proceed with VLA cube imaging sequence
        """
        findcont_datatypes = [
            DataType.SELFCAL_CONTLINE_SCIENCE,
            DataType.REGCAL_CONTLINE_SCIENCE,
        ]
        ms_list = self.inputs.context.observing_run.get_measurement_sets_of_type(findcont_datatypes, msonly=True)
        telescope = self.inputs.context.project_summary.telescope
        return 'VLA' in telescope.upper() and not ms_list
