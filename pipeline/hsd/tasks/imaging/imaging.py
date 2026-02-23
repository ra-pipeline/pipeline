"""Imaging stage."""

import collections
import functools
import math
import os
from numbers import Number
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Union

import numpy
from scipy import interpolate

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.callibrary as callibrary
import pipeline.infrastructure.filenamer as filenamer
import pipeline.infrastructure.imageheader as imageheader
import pipeline.infrastructure.utils as utils
import pipeline.infrastructure.vdp as vdp
from pipeline.domain import DataTable, DataType, MeasurementSet
from pipeline.h.heuristics import fieldnames
from pipeline.h.tasks.common.sensitivity import Sensitivity
from pipeline.hsd.heuristics import rasterscan
from pipeline.hsd.heuristics.rasterscan import RasterScanHeuristicsResult, RasterScanHeuristicsFailure
from pipeline.hsd.tasks import common
from pipeline.hsd.tasks.baseline import baseline
from pipeline.hsd.tasks.common import compress, direction_utils, observatory_policy, rasterutil, sdtyping
from pipeline.hsd.tasks.common import utils as sdutils
from pipeline.hsd.tasks.imaging import (detect_missed_lines,
                                        detectcontamination, gridding,
                                        imaging_params, resultobjects,
                                        sdcombine, worker)
from pipeline.infrastructure import casa_tools, task_registry

if TYPE_CHECKING:
    from casatools import coordsys
    from pipeline.infrastructure import Context
    from resultobjects import SDImagingResults

LOG = infrastructure.get_logger(__name__)

# SensitivityInfo:
#     sensitivity: Sensitivity of an image
#     frequency_range: frequency ranges from which the sensitivity is calculated
#     to_export: True if the sensitivity shall be exported to aqua report. (to avoid exporting NRO sensitivity in K)
SensitivityInfo = collections.namedtuple('SensitivityInfo', 'sensitivity frequency_range to_export')
# RasterInfo: center_ra, center_dec = R.A. and Declination of map center
#             width=map extent along scan, height=map extent perpendicular to scan
#             angle=scan direction w.r.t. horizontal coordinate, row_separation=separation between raster rows.
RasterInfo = collections.namedtuple('RasterInfo', 'center_ra center_dec width height '
                                                  'scan_angle row_separation row_duration')
# Reference MS in combined list
REF_MS_ID = 0
# The minimum limit of integration time (seconds) to be a valid scan duration (0.99 ms)
# The current minimum, 0.99 ms, comes from the typical integration time of fast-scan observation
# by SQLD in ALMA (1 ms) with 1% margin to avoid rejecting the exact 1 ms case (w/ numerical error).
# Adjust the value when Pipeline supports observation modes/instruments with smaller integration time.
MIN_INTEGRATION_SEC = 9.9e-4


class SDImagingInputs(vdp.StandardInputs):
    """Inputs for imaging task class."""

    # Search order of input vis
    processing_data_type = [DataType.BASELINED, DataType.ATMCORR,
                            DataType.REGCAL_CONTLINE_ALL, DataType.RAW]

    infiles = vdp.VisDependentProperty(default='', null_input=['', None, [], ['']])
    spw = vdp.VisDependentProperty(default='')
    pol = vdp.VisDependentProperty(default='')
    field = vdp.VisDependentProperty(default='')
    mode = vdp.VisDependentProperty(default='line')

    @field.postprocess
    def field(self, unprocessed: Optional[str]) -> Optional[str]:
        """Get fields as a string.

        Args:
            unprocessed : Unprocessed fields

        Returns:
            fields as a string
        """
        # LOG.info('field.postprocess: unprocessed = "{0}"'.format(unprocessed))
        if unprocessed is not None and unprocessed != '':
            return unprocessed

        # filters field with intents in self.intent
        p = fieldnames.IntentFieldnames()
        fields = set()
        vislist = [self.vis] if isinstance(self.vis, str) else self.vis
        for vis in vislist:
            # This assumes the same fields in all MSes
            msobj = self.context.observing_run.get_ms(vis)
            # this will give something like '0542+3243,0343+242'
            intent_fields = p(msobj, self.intent)
            fields.update(utils.safe_split(intent_fields))

        # LOG.info('field.postprocess: fields = "{0}"'.format(fields))

        return ','.join(fields)

    @property
    def antenna(self) -> str:
        return ''

    @property
    def intent(self) -> str:
        return 'TARGET'

    # Synchronization between infiles and vis is still necessary
    @vdp.VisDependentProperty
    def vis(self) -> List[str]:
        return self.infiles

    @property
    def is_ampcal(self) -> bool:
        return self.mode.upper() == 'AMPCAL'

    # TODO: Replace the decorator with @functools.cached_property
    #       when we completely get rid of python 3.6 support
    @property
    @functools.lru_cache(1)
    def datatype(self) -> DataType:
        """Return datatype enum corresponding to dataset returned by vis/infiles attribute."""
        # TODO: It would be ideal to integrate datatype stuff into vdp.
        #       Since this is urgent fix for PIPE-1480, it is better for now
        #       to confine the change into single file to avoid unexpected
        #       side effect.
        _, _datatype = self.context.observing_run.get_measurement_sets_of_type(
            self.processing_data_type, msonly=False
        )
        return _datatype

    # docstring and type hints: supplements hsd_imaging
    def __init__(self, context: 'Context', mode: Optional[str]=None, restfreq: Optional[str]=None,
                 infiles: Optional[List[str]]=None, field: Optional[str]=None, spw: Optional[str]=None,
                 org_direction: Optional['sdtyping.Direction']=None):
        """Initialize an object.

        Args:
            context : Pipeline context

            mode: Imaging mode controls imaging parameters in the task.
                Accepts either "line" (spectral line imaging) or "ampcal"
                (image settings for amplitude calibrator).

                Default: ``None`` (equivalent to ``'line'``)

            restfreq: Rest frequency. Defaults to None,
                it executes without rest frequency.

            infiles: List of data files. These must be a name of
                MeasurementSets that are registered to context via
                hsd_importdata or hsd_restoredata tasks.

                Example: ``vis=['uid___A002_X85c183_X36f.ms', 'uid___A002_X85c183_X60b.ms']``

                Default: ``None`` (process all registered MeasurementSets)

            field: Data selection by field names or ids.

                Example: ``"*Sgr*,M100"``

                Default: ``None`` (process all science fields)

            spw: Data selection by spw ids.

                Example: ``"3,4"`` (generate images for spw 3 and 4)

                Default: ``None`` (process all science spws)

            org_direction: Directions of the origin for moving targets.
                Defaults to ``None``, it doesn't have some moving targets.

        """
        super().__init__()

        self.context = context
        self.restfreq = restfreq
        if self.restfreq is None:
            self.restfreq = ''
        self.mode = mode
        self.infiles = infiles
        self.field = field
        self.mode = mode
        self.spw = spw
        self.org_direction = org_direction


@task_registry.set_equivalent_casa_task('hsd_imaging')
@task_registry.set_casa_commands_comment('Perform single dish imaging.')
class SDImaging(basetask.StandardTaskTemplate):
    """SDImaging processing class."""

    Inputs = SDImagingInputs
    # stokes to image and requred POLs for it
    stokes = 'I'
    # for linear feed in ALMA. this affects pols passed to gridding module
    required_pols = ['XX', 'YY']

    is_multi_vis_task = True

    def prepare(self) -> resultobjects.SDImagingResults:
        """Execute imaging process. This is the main method of imaging.

        Returns:
            result object of imaging
        """
        cp = self._initialize_common_parameters()

        # loop over reduction group (spw and source combination)
        for _group_id, _group_desc in cp.reduction_group.items():
            rgp = imaging_params.ReductionGroupParameters(_group_id, _group_desc)

            if not self._initialize_reduction_group_parameters(cp, rgp):
                continue

            for rgp.name, rgp.members in rgp.image_group.items():
                self._set_image_group_item_into_reduction_group_patameters(cp, rgp)

                # Step 1: (removed with PIPE-2491)

                # Step 2: imaging
                if not self._execute_imaging(cp, rgp):
                    continue

                if self._has_imager_result_outcome(rgp):
                    # Imaging was successful, proceed following steps

                    self._add_image_list_to_combine(rgp)

                    # Additional Step.
                    # Make grid_table and put rms and valid spectral number array
                    # to the outcome.
                    # The rms and number of valid spectra is used to create RMS maps.
                    self._make_grid_table(cp, rgp)
                    self._define_rms_range_in_image(cp, rgp)
                    self._set_asdm_to_outcome_vis_if_imagemode_is_ampcal(cp, rgp)

                    # NRO doesn't need per-antenna Stokes I images
                    if cp.is_not_nro():
                        self._append_result(cp, rgp)

                if self._has_nro_imager_result_outcome(rgp):
                    self._additional_imaging_process_for_nro(cp, rgp)

            if self._skip_this_loop(rgp):
                continue

            self._prepare_for_combine_images(rgp)

            # Step 3: imaging of all antennas
            self._execute_combine_images(rgp)

            pp = imaging_params.PostProcessParameters()
            if self._has_imager_result_outcome(rgp):

                # Imaging was successful, proceed following steps

                # Additional Step.
                # Make grid_table and put rms and valid spectral number array
                # to the outcome
                # The rms and number of valid spectra is used to create RMS maps
                self._make_post_grid_table(cp, rgp, pp)

                # calculate RMS of line free frequencies in a combined image
                try:
                    self._generate_parameters_for_calculate_sensitivity(cp, rgp, pp)

                    self._set_representative_flag(rgp, pp)

                    self._warn_if_early_cycle(rgp)

                    self._calculate_sensitivity(cp, rgp, pp)
                finally:
                    pp.done()

                self._detect_missed_lines( cp, rgp, pp )

                self._detect_contamination(rgp)

                self._append_result(cp, rgp)

            # NRO specific: generate combined image for each correlation
            if cp.is_nro and not self._execute_combine_images_for_nro(cp, rgp, pp):
                continue

        return cp.results

    @classmethod
    def _finalize_worker_result(cls,
                                context: 'Context',
                                result: 'SDImagingResults',
                                session: str,
                                sourcename: str,
                                spwlist: List[int],
                                antenna: str,
                                specmode: str,
                                imagemode: str,
                                stokes: str,
                                datatype: DataType,
                                datamin: Optional[float],
                                datamax: Optional[float],
                                datarms: Optional[float],
                                validsp: List[List[int]],
                                rms: List[List[float]],
                                edge: List[int],
                                reduction_group_id: int,
                                file_index: List[int],
                                assoc_antennas: List[int],
                                assoc_fields: List[int],
                                assoc_spws: List[int],
                                sensitivity_info: Optional[SensitivityInfo]=None,
                                theoretical_rms: Optional[Dict]=None,
                                effbw: Optional[float]=None):
        """
        Fanalize the worker result.

        Args:
            context            : Pipeline context
            result             : SDImagingResults instance
            session            : Session name
            sourcename         : Name of the source
            spwlist            : List of SpWs
            antenna            : Antenna name
            specmode           : Specmode for tsdimaging
            imagemode          : Image mode
            stokes             : Stokes parameter
            datatype           : Datatype enum
            datamin            : Minimum value of the image
            datamax            : Maximum value of the image
            datarms            : Rms of the image
            validsp            : # of combined spectra
            rms                : Rms values
            edge               : Edge channels
            reduction_group_id : Reduction group ID
            file_index         : MS file index
            assoc_antennas     : List of associated antennas
            assoc_fields       : List of associated fields
            assoc_spws         : List of associated SpWs
            sensitivity_info   : Sensitivity information
            theoretical_rms    : Theoretical RMS
            effbw              : Effective channel bandwidth in Hz
        Returns:
            (none)
        """
        # override attributes for image item
        # the following attribute is currently hard-coded
        sourcetype = 'TARGET'

        _locals = locals()
        image_keys = ('sourcename', 'spwlist', 'antenna', 'ant_name', 'specmode', 'sourcetype')
        for x in image_keys:
            if x in _locals:
                setattr(result.outcome['image'], x, _locals[x])

        # fill outcomes
        outcome_keys = ('imagemode', 'stokes', 'validsp', 'rms', 'edge', 'reduction_group_id',
                        'file_index', 'assoc_antennas', 'assoc_fields', 'assoc_spws', 'assoc_spws')
        for x in outcome_keys:
            if x in _locals:
                result.outcome[x] = _locals[x]

        # attach sensitivity_info if available
        if sensitivity_info is not None:
            result.sensitivity_info = sensitivity_info
        # attach theoretical RMS if available
        if theoretical_rms is not None:
            result.theoretical_rms = theoretical_rms

        # set some information to image header
        image_item = result.outcome['image']
        imagename = image_item.imagename

        # Virtual spws are not applicable for NRO data.
        # So if is_nro() returns True, the 'virtspw' flag is set to False.
        virtspw = not sdutils.is_nro(context)

        for name in (imagename, imagename + '.weight'):
            imageheader.set_miscinfo(name=name,
                                     spw=','.join(map(str, spwlist)),
                                     virtspw=virtspw,
                                     field=image_item.sourcename,
                                     nfield=1,
                                     datatype=datatype.name,
                                     type='singledish',
                                     iter=1,  # nominal
                                     intent=sourcetype,
                                     specmode=specmode,
                                     is_per_eb=False,
                                     context=context)

            # update miscinfo
            # TODO: Eventually, the following code together with
            #       Tclean.update_miscinfo should be merged into
            #       imageheader.set_miscinfo.
            with casa_tools.ImageReader(name) as image:
                info = image.miscinfo()

                if '.weight' not in name:
                    if datamin:
                        info['datamin'] = datamin

                    if datamax:
                        info['datamax'] = datamax

                    if datarms:
                        info['datarms'] = datarms

                info['stokes'] = stokes

                if effbw:
                    info['effbw'] = effbw

                info['level'] = 'member'
                info['obspatt'] = 'sd'
                info['arrays'] = 'TP'
                info['modifier'] = ''

                # PIPE-2148, limiting 'sessionX' keyword length to 68 characters
                # due to FITS header keyword string length limit.
                info = imageheader.wrap_key(info, 'sessio', session)

                image.setmiscinfo(info)

        # finally replace task attribute with the top-level one
        result.task = cls

    def _get_edge(self) -> List[int]:
        """
        Search results and retrieve edge parameter from the most recent SDBaselineResults if it exists.

        Returns:
            A list of edge
        """
        _getresult = lambda r: r.read() if hasattr(r, 'read') else r
        _registered_results = [_getresult(r) for r in self.inputs.context.results]
        _baseline_stage = -1
        for _stage in range(len(_registered_results) - 1, -1, -1):
            if isinstance(_registered_results[_stage], baseline.SDBaselineResults):
                _baseline_stage = _stage
        if _baseline_stage > 0:
            ret = list(_registered_results[_baseline_stage].outcome['edge'])
            LOG.info('Retrieved edge information from SDBaselineResults: {}'.format(ret))
        else:
            LOG.info('No SDBaselineResults available. Set edge as [0,0]')
            ret = [0, 0]
        return ret

    def _initialize_common_parameters(self) -> imaging_params.CommonParameters:
        """Initialize common parameters of prepare().

        Returns:
            common parameters object of prepare()
        """
        return imaging_params.initialize_common_parameters(
            reduction_group=self.inputs.context.observing_run.ms_reduction_group,
            infiles=self.inputs.infiles,
            restfreq_list=self.inputs.restfreq,
            ms_list=self.inputs.ms,
            ms_names=[msobj.name for msobj in self.inputs.ms],
            session_names=[msobj.session for msobj in self.inputs.ms],
            args_spw=sdutils.convert_spw_virtual2real(self.inputs.context, self.inputs.spw),
            in_field=self.inputs.field,
            imagemode=self.inputs.mode.upper(),
            is_nro=sdutils.is_nro(self.inputs.context),
            results=resultobjects.SDImagingResults(),
            edge=self._get_edge(),
            dt_dict=dict((_ms.basename, DataTable(sdutils.get_data_table_path(self.inputs.context, _ms)))
                         for _ms in self.inputs.ms)
        )

    def _get_correlations_if_nro(self, cp: imaging_params.CommonParameters,
                                 rgp: imaging_params.ReductionGroupParameters) -> Optional[str]:
        """If data is from NRO, then get correlations.

        Args:
            cp : Common parameters object of prepare()
            rgp : Reduction group parameter object of prepare()

        Returns:
            joined list of correlations
        """
        if cp.is_nro:
            _correlations = []
            for c in rgp.pols_list:
                if c not in _correlations:
                    _correlations.append(c)

            assert len(_correlations) == 1
            return ''.join(_correlations[0])
        else:
            return None

    def _get_rgp_image_group(self, cp: imaging_params.CommonParameters,
                             rgp: imaging_params.ReductionGroupParameters) -> Dict[str, List[List[str]]]:
        """Get image group of reduction group.

        Args:
            cp : Common parameters object of prepare()
            rgp : Reduction group parameter object of prepare()

        Returns:
            image group dictionary, value is list of [ms, antenna, spwid,
            fieldid, pollist, channelmap]
        """
        _image_group = {}
        for _msobj, _ant, _spwid, _fieldid, _pollist, _chanmap in \
                zip(cp.ms_list, rgp.antenna_list, rgp.spwid_list, rgp.fieldid_list, rgp.pols_list,
                    rgp.channelmap_range_list):
            _identifier = _msobj.fields[_fieldid].name
            _antenna = _msobj.antennas[_ant].name
            _identifier += '.' + _antenna
            # create image per asdm and antenna for ampcal
            if self.inputs.is_ampcal:
                _asdm_name = common.asdm_name_from_ms(_msobj)
                _identifier += '.' + _asdm_name
            if _identifier in _image_group:
                _image_group[_identifier].append([_msobj, _ant, _spwid, _fieldid, _pollist, _chanmap])
            else:
                _image_group[_identifier] = [[_msobj, _ant, _spwid, _fieldid, _pollist, _chanmap]]

        return _image_group

    def _initialize_reduction_group_parameters(self, cp: imaging_params.CommonParameters,
                                               rgp: imaging_params.ReductionGroupParameters) -> bool:
        """Set default values into the instance of imaging_params.ReductionGroupParameters.

        Note: cp.ms_list is set in this function.

        Args:
            cp : Common parameter object of prepare()
            rgp : Reduction group parameter object of prepare()
        """
        LOG.debug('Processing Reduction Group {}'.format(rgp.group_id))
        LOG.debug('Group Summary:')
        for _group in rgp.group_desc:
            LOG.debug('\t{}: Antenna {:d} ({}) Spw {:d} Field {:d} ({})'.format(_group.ms.basename, _group.antenna_id,
                                                                                _group.antenna_name, _group.spw_id,
                                                                                _group.field_id, _group.field_name))

        # Which group in group_desc list should be processed
        # fix for CAS-9747
        # There may be the case that observation didn't complete so that some of
        # target fields are missing in MS. In this case, directly pass in_field
        # to get_valid_ms_members causes trouble. As a workaround, ad hoc pre-selection
        # of field name is applied here.
        # 2017/02/23 TN
        _field_sel = ''
        if len(cp.in_field) == 0:
            # fine, just go ahead
            _field_sel = cp.in_field
        elif rgp.group_desc.field_name in [x.strip('"') for x in cp.in_field.split(',')]:
            # pre-selection of the field name
            _field_sel = rgp.group_desc.field_name
        else:
            LOG.info('Skip reduction group {:d}'.format(rgp.group_id))
            return False  # no field name is included in in_field, skip

        rgp.member_list = list(common.get_valid_ms_members(rgp.group_desc, cp.ms_names, self.inputs.antenna,
                               _field_sel, cp.args_spw))
        LOG.trace('group {}: member_list={}'.format(rgp.group_id, rgp.member_list))

        # skip this group if valid member list is empty
        if len(rgp.member_list) == 0:
            LOG.info('Skip reduction group {:d}'.format(rgp.group_id))
            return False
        rgp.member_list.sort()  # list of group_desc IDs to image
        rgp.antenna_list = [rgp.group_desc[i].antenna_id for i in rgp.member_list]
        rgp.spwid_list = [rgp.group_desc[i].spw_id for i in rgp.member_list]
        cp.ms_list = [rgp.group_desc[i].ms for i in rgp.member_list]
        rgp.fieldid_list = [rgp.group_desc[i].field_id for i in rgp.member_list]
        _temp_dd_list = [cp.ms_list[i].get_data_description(spw=rgp.spwid_list[i])
                         for i in range(len(rgp.member_list))]
        rgp.channelmap_range_list = [rgp.group_desc[i].channelmap_range for i in rgp.member_list]
        # this becomes list of list [[poltypes for ms0], [poltypes for ms1], ...]
        #             polids_list = [[ddobj.get_polarization_id(corr) for corr in ddobj.corr_axis \
        #                             if corr in self.required_pols ] for ddobj in temp_dd_list]
        rgp.pols_list = [[_corr for _corr in _ddobj.corr_axis if
                          _corr in self.required_pols] for _ddobj in _temp_dd_list]

        # NRO specific
        rgp.correlations = self._get_correlations_if_nro(cp, rgp)

        LOG.debug('Members to be processed:')
        for i in range(len(rgp.member_list)):
            LOG.debug('\t{}: Antenna {} Spw {} Field {}'.format(cp.ms_list[i].basename, rgp.antenna_list[i],
                                                                rgp.spwid_list[i], rgp.fieldid_list[i]))

        # image is created per antenna (science) or per asdm and antenna (ampcal)
        rgp.image_group = self._get_rgp_image_group(cp, rgp)

        LOG.debug('image_group={}'.format(rgp.image_group))

        rgp.combined = imaging_params.CombinedImageParameters()
        rgp.tocombine = imaging_params.ToCombineImageParameters()

        return True

    def _pick_restfreq_from_restfreq_list(self, cp: imaging_params.CommonParameters,
                                          rgp: imaging_params.ReductionGroupParameters):
        """Pick restfreq from restfreq_list.

        Args:
            cp : Common parameter object of prepare()
            rgp : Reduction group parameter object of prepare()
        """
        if isinstance(cp.restfreq_list, list):
            _v_spwid = self.inputs.context.observing_run.real2virtual_spw_id(rgp.spwids[0], rgp.msobjs[0])
            _v_spwid_list = [
                self.inputs.context.observing_run.real2virtual_spw_id(int(i), rgp.msobjs[0]) for
                i in cp.args_spw[rgp.msobjs[0].name].split(',')]
            _v_idx = _v_spwid_list.index(_v_spwid)
            if len(cp.restfreq_list) > _v_idx:
                rgp.restfreq = cp.restfreq_list[_v_idx]
                if rgp.restfreq is None:
                    rgp.restfreq = ''
                LOG.info("Picked restfreq = '{}' from {}".format(rgp.restfreq, cp.restfreq_list))
            else:
                rgp.restfreq = ''
                LOG.warning("No restfreq for spw {} in {}. Applying default value.".format(_v_spwid,
                                                                                           cp.restfreq_list))
        else:
            rgp.restfreq = cp.restfreq_list
            LOG.info("Processing with restfreq = {}".format(rgp.restfreq))

    def _set_image_name_based_on_virtual_spwid(self, cp: imaging_params.CommonParameters,
                                               rgp: imaging_params.ReductionGroupParameters):
        """Generate image name based on virtual spw id and set it to RGP.

        Args:
            cp : Common parameter object of prepare()
            rgp : Reduction group parameter object of prepare()
        """
        _v_spwids_unique = numpy.unique(rgp.v_spwids)
        assert len(_v_spwids_unique) == 1
        rgp.imagename = self.get_imagename(rgp.source_name, _v_spwids_unique, rgp.ant_name,
                                           rgp.asdm, specmode=rgp.specmode)
        LOG.info("Output image name: {}".format(rgp.imagename))
        rgp.imagename_nro = None
        if cp.is_nro:
            rgp.imagename_nro = self.get_imagename(rgp.source_name, _v_spwids_unique, rgp.ant_name, rgp.asdm,
                                                   stokes=rgp.correlations, specmode=rgp.specmode)
            LOG.info("Output image name for NRO: {}".format(rgp.imagename_nro))

    def _set_image_group_item_into_reduction_group_patameters(self, cp: imaging_params.CommonParameters,
                                                              rgp: imaging_params.ReductionGroupParameters):
        """Set values for imaging into RGP.

        This method does (1)get parameters from image group in RGP to do gridding(imaging) and set them into RGP,
        and (2)generate an image name and pick the rest frequency.

        Args:
            cp : Common parameter object of prepare()
            rgp : Reduction group parameter object of prepare()
        """
        rgp.msobjs = [x[0] for x in rgp.members]
        rgp.antids = [x[1] for x in rgp.members]
        rgp.spwids = [x[2] for x in rgp.members]
        rgp.fieldids = [x[3] for x in rgp.members]
        rgp.polslist = [x[4] for x in rgp.members]
        rgp.chanmap_range_list = [x[5] for x in rgp.members]
        LOG.info("Processing image group: {}".format(rgp.name))
        for idx in range(len(rgp.msobjs)):
            LOG.info(
                "\t{}: Antenna {:d} ({}) Spw {} Field {:d} ({})"
                "".
                format(rgp.msobjs[idx].basename, rgp.antids[idx], rgp.msobjs[idx].antennas[rgp.antids[idx]].name,
                       rgp.spwids[idx], rgp.fieldids[idx], rgp.msobjs[idx].fields[rgp.fieldids[idx]].name))

        # reference data is first MS
        rgp.ref_ms = rgp.msobjs[0]
        rgp.ant_name = rgp.ref_ms.antennas[rgp.antids[0]].name

        # for ampcal
        rgp.asdm = None
        if self.inputs.is_ampcal:
            rgp.asdm = common.asdm_name_from_ms(rgp.ref_ms)

        # source name
        rgp.source_name = rgp.group_desc.field_name.replace(' ', '_')

        # specmode
        _ref_field = rgp.fieldids[0]
        _is_eph_obj = rgp.ref_ms.get_fields(field_id=_ref_field)[0].source.is_eph_obj
        rgp.specmode = 'cubesource' if _is_eph_obj else 'cube'

        # filenames for gridding
        cp.infiles = [_ms.name for _ms in rgp.msobjs]
        LOG.debug('infiles={}'.format(cp.infiles))

        # virtual spw ids
        rgp.v_spwids = [self.inputs.context.observing_run.real2virtual_spw_id(s, m)
                        for s, m in zip(rgp.spwids, rgp.msobjs)]

        # image name
        self._set_image_name_based_on_virtual_spwid(cp, rgp)

        # restfreq
        self._pick_restfreq_from_restfreq_list(cp, rgp)

    def _initialize_coord_set(self, cp: imaging_params.CommonParameters,
                              rgp: imaging_params.ReductionGroupParameters) -> bool:
        """Initialize coordinate set of MS.

        if initialize is fault, current loop of reduction group goes to next loop immediately.

        Args:
            cp : Common parameter object of prepare()
            rgp : Reduction group parameter object of prepare()
        Returns:
            A flag initialize succeeded or not
        """
        # PIPE-313: evaluate map extent using pointing data from all the antenna in the data
        _dummyids = [None for _ in rgp.antids]
        _image_coord = worker.ImageCoordinateUtil(self.inputs.context, cp.infiles,
                                                  _dummyids, rgp.spwids, rgp.fieldids)
        if not _image_coord:  # No valid data is found
            return False
        rgp.coord_set = True
        rgp.phasecenter, rgp.cellx, rgp.celly, rgp.nx, rgp.ny, rgp.org_direction = _image_coord
        return True

    def _execute_imaging_worker(self, cp: imaging_params.CommonParameters,
                                rgp: imaging_params.ReductionGroupParameters):
        """Execute imaging worker.

        Args:
            cp : Common parameter object of prepare()
            rgp : Reduction group parameter object of prepare()
        """
        # register data for combining
        rgp.combined.extend(cp, rgp)
        rgp.stokes_list = [self.stokes]
        _imagename_list = [rgp.imagename]
        if cp.is_nro:
            rgp.stokes_list.append(rgp.correlations)
            _imagename_list.append(rgp.imagename_nro)

        _imager_results = []
        for _stokes, _imagename in zip(rgp.stokes_list, _imagename_list):
            _imager_inputs = worker.SDImagingWorker.Inputs(self.inputs.context, cp.infiles,
                                                           outfile=_imagename,
                                                           mode=cp.imagemode,
                                                           antids=rgp.antids,
                                                           spwids=rgp.spwids,
                                                           fieldids=rgp.fieldids,
                                                           restfreq=rgp.restfreq,
                                                           stokes=_stokes,
                                                           edge=cp.edge,
                                                           phasecenter=rgp.phasecenter,
                                                           cellx=rgp.cellx,
                                                           celly=rgp.celly,
                                                           nx=rgp.nx, ny=rgp.ny,
                                                           org_direction=rgp.org_direction)
            _imager_task = worker.SDImagingWorker(_imager_inputs)
            _imager_result = self._executor.execute(_imager_task)
            _imager_results.append(_imager_result)

        # per-antenna image (usually Stokes I)
        rgp.imager_result = _imager_results[0]
        # per-antenna correlation image (XXYY/RRLL)
        rgp.imager_result_nro = _imager_results[1] if cp.is_nro else None

    def _make_grid_table(self, cp: imaging_params.CommonParameters, rgp: imaging_params.ReductionGroupParameters):
        """Make grid table for gridding.

        Args:
            cp : Common parameter object of prepare()
            rgp : Reduction group parameter object of prepare()
        """
        LOG.info('Additional Step. Make grid_table')
        rgp.imagename = rgp.imager_result.outcome['image'].imagename
        with casa_tools.ImageReader(rgp.imagename) as ia:
            _cs = ia.coordsys()
            _dircoords = [i for i in range(_cs.naxes()) if _cs.axiscoordinatetypes()[i] == 'Direction']
            _cs.done()
            rgp.nx = ia.shape()[_dircoords[0]]
            rgp.ny = ia.shape()[_dircoords[1]]
        _observing_pattern = rgp.msobjs[0].observing_pattern[rgp.antids[0]][rgp.spwids[0]][rgp.fieldids[0]]
        _grid_task_class = gridding.gridding_factory(_observing_pattern)
        rgp.validsps = []
        rgp.rmss = []
        _grid_input_dict = {}
        for _msobj, _antid, _spwid, _fieldid, _poltypes, _ in rgp.members:
            _msname = _msobj.name  # Use parent ms
            for p in _poltypes:
                if p not in _grid_input_dict:
                    _grid_input_dict[p] = [[_msname], [_antid], [_fieldid], [_spwid]]
                else:
                    _grid_input_dict[p][0].append(_msname)
                    _grid_input_dict[p][1].append(_antid)
                    _grid_input_dict[p][2].append(_fieldid)
                    _grid_input_dict[p][3].append(_spwid)

        # Generate grid table for each POL in image (per ANT,
        # FIELD, and SPW, over all MSes)
        for _pol, _member in _grid_input_dict.items():
            _mses = _member[0]
            _antids = _member[1]
            _fieldids = _member[2]
            _spwids = _member[3]
            _pols = [_pol for i in range(len(_mses))]
            _gridding_inputs = _grid_task_class.Inputs(self.inputs.context, infiles=_mses,
                                                       antennaids=_antids,
                                                       fieldids=_fieldids,
                                                       spwids=_spwids,
                                                       poltypes=_pols,
                                                       nx=rgp.nx, ny=rgp.ny)
            _gridding_task = _grid_task_class(_gridding_inputs)
            _gridding_result = self._executor.execute(_gridding_task, merge=False,
                                                      datatable_dict=cp.dt_dict)
            # Extract RMS and number of spectra from grid_tables
            if isinstance(_gridding_result.outcome, compress.CompressedObj):
                _grid_table = _gridding_result.outcome.decompress()
            else:
                _grid_table = _gridding_result.outcome
            rgp.validsps.append([r[6] for r in _grid_table])
            rgp.rmss.append([r[8] for r in _grid_table])

    def _add_image_list_to_combine(self, rgp: imaging_params.ReductionGroupParameters):
        """Add image list to combine.

        Args:
            rgp : Reduction group parameter object of prepare()
        """
        if os.path.exists(rgp.imagename) and os.path.exists(rgp.imagename + '.weight'):
            rgp.tocombine.images.append(rgp.imagename)
            rgp.tocombine.org_directions.append(rgp.org_direction)
            rgp.tocombine.specmodes.append(rgp.specmode)

    def _define_rms_range_in_image(self, cp: imaging_params.CommonParameters,
                                   rgp: imaging_params.ReductionGroupParameters):
        """Define RMS range and finalize worker result.

        Args:
            cp : Common parameter object of prepare()
            rgp : Reduction group parameter object of prepare()
        """
        _cqa = casa_tools.quanta

        LOG.info("Calculate spectral line and deviation mask frequency ranges in image.")
        with casa_tools.ImageReader(rgp.imagename) as ia:
            _cs = ia.coordsys()
            _frequency_frame = _cs.getconversiontype('spectral')
            _cs.done()
            _rms_exclude_freq = self._get_rms_exclude_freq_range_image(_frequency_frame, cp, rgp)
            LOG.info("The spectral line and deviation mask frequency ranges = {}".format(str(_rms_exclude_freq)))
        rgp.combined.rms_exclude.extend(_rms_exclude_freq)
        _file_index = [common.get_ms_idx(self.inputs.context, name) for name in cp.infiles]
        _spwid = str(rgp.combined.v_spws[REF_MS_ID])
        _spwobj = rgp.ref_ms.get_spectral_window(_spwid)
        _effective_bw = _cqa.quantity(_spwobj.channels.chan_effbws[0], 'Hz')
        effbw = float(_cqa.getvalue(_effective_bw)[0])
        self._finalize_worker_result(self.inputs.context, rgp.imager_result, session=','.join(cp.session_names), sourcename=rgp.source_name,
                                     spwlist=rgp.v_spwids, antenna=rgp.ant_name, specmode=rgp.specmode,
                                     imagemode=cp.imagemode, stokes=self.stokes,
                                     datatype=self.inputs.datatype, datamin=None, datamax=None, datarms=None,
                                     validsp=rgp.validsps,
                                     rms=rgp.rmss, edge=cp.edge, reduction_group_id=rgp.group_id,
                                     file_index=_file_index, assoc_antennas=rgp.antids, assoc_fields=rgp.fieldids,
                                     assoc_spws=rgp.v_spwids, effbw=effbw)

    def _additional_imaging_process_for_nro(self, cp: imaging_params.CommonParameters,
                                            rgp: imaging_params.ReductionGroupParameters):
        """Add image list to combine and finalize worker result.

        Args:
            cp : Common parameter object of prepare()
            rgp : Reduction group parameter object of prepare()
        """
        _cqa = casa_tools.quanta

        # Imaging was successful, proceed following steps
        # add image list to combine
        if os.path.exists(rgp.imagename_nro) and os.path.exists(rgp.imagename_nro + '.weight'):
            rgp.tocombine.images_nro.append(rgp.imagename_nro)
            rgp.tocombine.org_directions_nro.append(rgp.org_direction)
            rgp.tocombine.specmodes.append(rgp.specmode)
        _file_index = [common.get_ms_idx(self.inputs.context, name) for name in cp.infiles]
        _spwid = str(rgp.combined.v_spws[REF_MS_ID])
        _spwobj = rgp.ref_ms.get_spectral_window(_spwid)
        _effective_bw = _cqa.quantity(_spwobj.channels.chan_effbws[0], 'Hz')
        effbw = float(_cqa.getvalue(_effective_bw)[0])
        self._finalize_worker_result(self.inputs.context, rgp.imager_result_nro, session=','.join(cp.session_names), sourcename=rgp.source_name,
                                     spwlist=rgp.v_spwids, antenna=rgp.ant_name, specmode=rgp.specmode,
                                     imagemode=cp.imagemode, stokes=rgp.stokes_list[1],
                                     datatype=self.inputs.datatype, datamin=None, datamax=None, datarms=None,
                                     validsp=rgp.validsps,
                                     rms=rgp.rmss, edge=cp.edge, reduction_group_id=rgp.group_id,
                                     file_index=_file_index, assoc_antennas=rgp.antids, assoc_fields=rgp.fieldids,
                                     assoc_spws=rgp.v_spwids, effbw=effbw)
        cp.results.append(rgp.imager_result_nro)

    def _make_post_grid_table(self, cp: imaging_params.CommonParameters,
                              rgp: imaging_params.ReductionGroupParameters,
                              pp: imaging_params.PostProcessParameters):
        """Make grid table on post process.

        Args:
            cp : Common parameter object of prepare()
            rgp : Reduction group parameter object of prepare()
            pp : Imaging post process parameters of prepare()
        """
        LOG.info('Additional Step. Make grid_table')
        pp.imagename = rgp.imager_result.outcome['image'].imagename
        pp.org_direction = rgp.imager_result.outcome['image'].org_direction
        with casa_tools.ImageReader(pp.imagename) as ia:
            _cs = ia.coordsys()
            _dircoords = [i for i in range(_cs.naxes()) if _cs.axiscoordinatetypes()[i] == 'Direction']
            _cs.done()
            pp.nx = ia.shape()[_dircoords[0]]
            pp.ny = ia.shape()[_dircoords[1]]
        _antid = rgp.combined.antids[REF_MS_ID]
        _spwid = rgp.combined.spws[REF_MS_ID]
        _fieldid = rgp.combined.fieldids[REF_MS_ID]
        _observing_pattern = rgp.ref_ms.observing_pattern[_antid][_spwid][_fieldid]
        _grid_task_class = gridding.gridding_factory(_observing_pattern)
        pp.validsps = []
        pp.rmss = []
        _grid_input_dict = {}
        for _msname, _antid, _spwid, _fieldid, _poltypes in zip(rgp.combined.infiles,
                                                                rgp.combined.antids,
                                                                rgp.combined.spws,
                                                                rgp.combined.fieldids,
                                                                rgp.combined.pols):
            for p in _poltypes:
                if p not in _grid_input_dict:
                    _grid_input_dict[p] = [[_msname], [_antid], [_fieldid], [_spwid]]
                else:
                    _grid_input_dict[p][0].append(_msname)
                    _grid_input_dict[p][1].append(_antid)
                    _grid_input_dict[p][2].append(_fieldid)
                    _grid_input_dict[p][3].append(_spwid)

        for _pol, _member in _grid_input_dict.items():
            _mses = _member[0]
            _antids = _member[1]
            _fieldids = _member[2]
            _spwids = _member[3]
            _pols = [_pol for i in range(len(_mses))]
            _gridding_inputs = _grid_task_class.Inputs(self.inputs.context, infiles=_mses, antennaids=_antids,
                                                       fieldids=_fieldids, spwids=_spwids, poltypes=_pols,
                                                       nx=pp.nx, ny=pp.ny)
            _gridding_task = _grid_task_class(_gridding_inputs)
            _gridding_result = self._executor.execute(_gridding_task, merge=False, datatable_dict=cp.dt_dict)
            # Extract RMS and number of spectra from grid_tables
            if isinstance(_gridding_result.outcome, compress.CompressedObj):
                _grid_table = _gridding_result.outcome.decompress()
            else:
                _grid_table = _gridding_result.outcome
            pp.validsps.append([r[6] for r in _grid_table])
            pp.rmss.append([r[8] for r in _grid_table])

    def _generate_parameters_for_calculate_sensitivity(self, cp: imaging_params.CommonParameters,
                                                       rgp: imaging_params.ReductionGroupParameters,
                                                       pp: imaging_params.PostProcessParameters):
        """Generate parameters to calculate sensitivity.

        Note: If it fails to calculate image statistics for some reason, it sets the RMS value to -1.0.
              -1.0 is the special value in image statistics calculation of all tasks.

        Args:
            cp : Common parameter object of prepare()
            rgp : Reduction group parameter object of prepare()
            pp : Imaging post process parameters of prepare()
        """
        LOG.info('Calculate sensitivity of combined image')
        with casa_tools.ImageReader(pp.imagename) as ia:
            pp.cs = ia.coordsys()
            pp.faxis = pp.cs.findaxisbyname('spectral')
            pp.chan_width = pp.cs.increment()['numeric'][pp.faxis]
            pp.brightnessunit = ia.brightnessunit()
            pp.beam = ia.restoringbeam()
        pp.qcell = list(pp.cs.increment(format='q', type='direction')['quantity'].values())
        # cs.increment(format='s', type='direction')['string']

        # Define image channels to calculate statistics
        pp.include_channel_range = self._get_stat_chans(pp.imagename, rgp.combined.rms_exclude, cp.edge)
        pp.stat_chans = convert_range_list_to_string(pp.include_channel_range)
        # Define region to calculate statistics
        pp.raster_infos = self.get_raster_info_list(cp, rgp)
        pp.region = self._get_stat_region(pp)

        # Image statistics
        if pp.region is None:
            LOG.warning('Could not get valid region of interest to calculate image statistics.')
            pp.image_rms = -1.0
        else:
            _statval = calc_image_statistics(pp.imagename, pp.stat_chans, pp.region)
            if len(_statval['rms']):
                pp.image_rms = _statval['rms'][0]
                LOG.info("Statistics of line free channels ({}): RMS = {:f} {}, Stddev = {:f} {}, "
                         "Mean = {:f} {}".format(pp.stat_chans, _statval['rms'][0], pp.brightnessunit,
                                                 _statval['sigma'][0], pp.brightnessunit,
                                                 _statval['mean'][0], pp.brightnessunit))
            else:
                LOG.warning('Could not get image statistics. Potentially no valid pixel in region of interest.')
                pp.image_rms = -1.0

            for _stat_name in ['max', 'min']:
                _val = _statval.get(_stat_name, [])
                setattr(pp, f'image_{_stat_name}', _val[0] if _val else -1.0)

        # Theoretical RMS
        LOG.info('Calculating theoretical RMS of image, {}'.format(pp.imagename))
        pp.theoretical_rms = self.calculate_theoretical_image_rms(cp, rgp, pp)

    def _execute_combine_images(self, rgp: imaging_params.ReductionGroupParameters):
        """Combine images.

        Args:
            rgp : Reduction group parameter object of prepare()
        """
        LOG.info('Combine images of Source {} Spw {:d}'.format(rgp.source_name, rgp.combined.v_spws[REF_MS_ID]))
        _combine_inputs = sdcombine.SDImageCombineInputs(self.inputs.context, inimages=rgp.tocombine.images,
                                                         outfile=rgp.imagename,
                                                         org_directions=rgp.tocombine.org_directions,
                                                         specmodes=rgp.tocombine.specmodes)
        _combine_task = sdcombine.SDImageCombine(_combine_inputs)
        _freq_chan_reversed = False
        if isinstance(rgp.imager_result, resultobjects.SDImagingResultItem):
            _freq_chan_reversed = rgp.imager_result.frequency_channel_reversed
        rgp.imager_result = self._executor.execute(_combine_task)
        rgp.imager_result.frequency_channel_reversed = _freq_chan_reversed

    def _set_representative_flag(self,
                                 rgp: imaging_params.ReductionGroupParameters,
                                 pp: imaging_params.PostProcessParameters):
        """Set is_representative_source_and_spw flag.

        Args:
            rgp : Reduction group parameter object of prepare()
            pp : Imaging post process parameters of prepare()
        """
        _rep_source_name, _rep_spw_id = rgp.ref_ms.get_representative_source_spw()
        pp.is_representative_source_and_spw = \
            _rep_spw_id == rgp.combined.spws[REF_MS_ID] and \
            _rep_source_name == utils.dequote(rgp.source_name)

    def _warn_if_early_cycle(self, rgp: imaging_params.ReductionGroupParameters):
        """Warn when it processes MeasurementSet of ALMA Cycle 2 and earlier.

        Args:
            rgp (imaging_params.ReductionGroupParameters): Reduction group parameter object of prepare()
        """
        _cqa = casa_tools.quanta
        if rgp.ref_ms.antenna_array.name == 'ALMA' and \
           _cqa.time(rgp.ref_ms.start_time['m0'], 0, ['ymd', 'no_time'])[0] < '2015/10/01':
            LOG.warning("ALMA Cycle 2 and earlier project does not have a valid effective bandwidth. "
                        "Therefore, a nominal value of channel separation loaded from the MS "
                        "is used as an effective bandwidth for RMS estimation.")

    def _calculate_sensitivity(self, cp: imaging_params.CommonParameters,
                               rgp: imaging_params.ReductionGroupParameters,
                               pp: imaging_params.PostProcessParameters):
        """Calculate channel and frequency ranges of line free channels.

        Args:
            cp : Common parameter object of prepare()
            rgp : Reduction group parameter object of prepare()
            pp : Imaging post process parameters of prepare()
        """
        _ref_pixel = pp.cs.referencepixel()['numeric']
        _freqs = []
        _cqa = casa_tools.quanta

        for _ichan in pp.include_channel_range:
            _ref_pixel[pp.faxis] = _ichan
            _freqs.append(pp.cs.toworld(_ref_pixel)['numeric'][pp.faxis])

        if len(_freqs) > 1 and _freqs[0] > _freqs[1]:  # LSB
            _freqs.reverse()
        pp.stat_freqs = str(', ').join(['{:f}~{:f}GHz'.format(_freqs[_iseg] * 1.e-9, _freqs[_iseg + 1] * 1.e-9)
                                        for _iseg in range(0, len(_freqs), 2)])
        _file_index = [common.get_ms_idx(self.inputs.context, name) for name in rgp.combined.infiles]
        _bw = _cqa.quantity(pp.chan_width, 'Hz')
        _spwid = str(rgp.combined.v_spws[REF_MS_ID])
        _spwobj = rgp.ref_ms.get_spectral_window(_spwid)
        _effective_bw = _cqa.quantity(_spwobj.channels.chan_effbws[0], 'Hz')
        _theoretical_rms_aqua = pp.theoretical_rms if pp.brightnessunit == 'Jy/beam' else None  # for some telescopes, the unit might be different from 'Jy/beam'
        _sensitivity = Sensitivity(array='TP', intent='TARGET', field=rgp.source_name,
                                   spw=_spwid, is_representative=pp.is_representative_source_and_spw,
                                   bandwidth=_bw, bwmode='cube', beam=pp.beam, cell=pp.qcell,
                                   observed_sensitivity=_cqa.quantity(pp.image_rms, pp.brightnessunit),
                                   effective_bw=_effective_bw, imagename=rgp.imagename,
                                   datatype=self.inputs.datatype.name, theoretical_sensitivity=_theoretical_rms_aqua)
        _theoretical_noise = Sensitivity(array='TP', intent='TARGET', field=rgp.source_name,
                                         spw=_spwid, is_representative=pp.is_representative_source_and_spw,
                                         bandwidth=_bw, bwmode='cube', beam=pp.beam, cell=pp.qcell,
                                         theoretical_sensitivity=pp.theoretical_rms, observed_sensitivity=None)
        _sensitivity_info = SensitivityInfo(_sensitivity, pp.stat_freqs, (cp.is_not_nro()))
        effbw = float(_cqa.getvalue(_effective_bw)[0])
        self._finalize_worker_result(self.inputs.context, rgp.imager_result, session=','.join(cp.session_names), sourcename=rgp.source_name,
                                     spwlist=rgp.combined.v_spws, antenna='COMBINED', specmode=rgp.specmode,
                                     imagemode=cp.imagemode, stokes=self.stokes,
                                     datatype=self.inputs.datatype, datamin=pp.image_min, datamax=pp.image_max,
                                     datarms=pp.image_rms, validsp=pp.validsps, rms=pp.rmss,
                                     edge=cp.edge, reduction_group_id=rgp.group_id, file_index=_file_index,
                                     assoc_antennas=rgp.combined.antids, assoc_fields=rgp.combined.fieldids,
                                     assoc_spws=rgp.combined.v_spws, sensitivity_info=_sensitivity_info,
                                     theoretical_rms=_theoretical_noise, effbw=effbw)

    def _execute_combine_images_for_nro(self, cp: imaging_params.CommonParameters,
                                        rgp: imaging_params.ReductionGroupParameters,
                                        pp: imaging_params.PostProcessParameters) -> bool:
        """Combine images for NRO data.

        Args:
            cp : Common parameter object of prepare()
            rgp : Reduction group parameter object of prepare()
            pp : Imaging post process parameters of prepare()
        Returns:
            False if a valid image to combine does not exist for a specified source or spw.
        """
        _cqa = casa_tools.quanta

        if len(rgp.tocombine.images_nro) == 0:
            LOG.warning("No valid image to combine for Source {}, Spw {:d}".format(rgp.source_name, rgp.spwids[0]))
            return False
        # image name
        # image name should be based on virtual spw id
        pp.imagename = self.get_imagename(rgp.source_name, rgp.combined.v_spws_unique,
                                          stokes=rgp.correlations, specmode=rgp.specmode)

        # Imaging of all antennas
        LOG.info('Combine images of Source {} Spw {:d}'.format(rgp.source_name, rgp.combined.v_spws[REF_MS_ID]))
        _combine_inputs = sdcombine.SDImageCombineInputs(self.inputs.context, inimages=rgp.tocombine.images_nro,
                                                         outfile=pp.imagename,
                                                         org_directions=rgp.tocombine.org_directions_nro,
                                                         specmodes=rgp.tocombine.specmodes)
        _combine_task = sdcombine.SDImageCombine(_combine_inputs)
        rgp.imager_result = self._executor.execute(_combine_task)
        if rgp.imager_result.outcome is not None:
            # Imaging was successful, proceed following steps
            _file_index = [common.get_ms_idx(self.inputs.context, name) for name in rgp.combined.infiles]
            _spwid = str(rgp.combined.v_spws[REF_MS_ID])
            _spwobj = rgp.ref_ms.get_spectral_window(_spwid)
            _effective_bw = _cqa.quantity(_spwobj.channels.chan_effbws[0], 'Hz')
            effbw = float(_cqa.getvalue(_effective_bw)[0])
            self._finalize_worker_result(self.inputs.context, rgp.imager_result, session=','.join(cp.session_names), sourcename=rgp.source_name,
                                         spwlist=rgp.combined.v_spws, antenna='COMBINED', specmode=rgp.specmode,
                                         imagemode=cp.imagemode, stokes=rgp.stokes_list[1],
                                         datatype=self.inputs.datatype, datamin=pp.image_min, datamax=pp.image_max,
                                         datarms=pp.image_rms, validsp=pp.validsps,
                                         rms=pp.rmss, edge=cp.edge, reduction_group_id=rgp.group_id,
                                         file_index=_file_index, assoc_antennas=rgp.combined.antids,
                                         assoc_fields=rgp.combined.fieldids, assoc_spws=rgp.combined.v_spws, effbw=effbw)
            cp.results.append(rgp.imager_result)
        return True

    def _prepare_for_combine_images(self, rgp: imaging_params.ReductionGroupParameters):
        """Prepare before combining images.

        Args:
            rgp : Reduction group parameter object of prepare()
        """
        # reference MS
        rgp.ref_ms = self.inputs.context.observing_run.get_ms(name=rgp.combined.infiles[REF_MS_ID])
        # image name
        # image name should be based on virtual spw id
        rgp.combined.v_spws_unique = numpy.unique(rgp.combined.v_spws)
        assert len(rgp.combined.v_spws_unique) == 1
        rgp.imagename = self.get_imagename(rgp.source_name, rgp.combined.v_spws_unique, specmode=rgp.specmode)

    def _skip_this_loop(self, rgp: imaging_params.ReductionGroupParameters) -> bool:
        """Determine whether combine should be skipped.

        Args:
            rgp : Reduction group parameter object of prepare()

        Returns:
            A boolean flag of determination whether the loop should be skipped or not.
        """
        if self.inputs.is_ampcal:
            LOG.info("Skipping combined image for the amplitude calibrator.")
            return True
        # Make combined image
        if len(rgp.tocombine.images) == 0:
            LOG.warning("No valid image to combine for Source {}, Spw {:d}".format(rgp.source_name, rgp.spwids[0]))
            return True
        return False

    def _execute_imaging(self, cp: imaging_params.CommonParameters,
                         rgp: imaging_params.ReductionGroupParameters) -> bool:
        """Execute imaging per antenna, source.

        Args:
            cp : Common parameter object of prepare()
            rgp : Reduction group parameter object of prepare()
        Returns:
            False if coordinate setting fails before imaging is executed.
        """
        LOG.info('Imaging Source {}, Ant {} Spw {:d}'.format(rgp.source_name, rgp.ant_name, rgp.spwids[0]))
        # map coordinate (use identical map coordinate per spw)
        if not rgp.coord_set and not self._initialize_coord_set(cp, rgp):
            return False
        self._execute_imaging_worker(cp, rgp)
        return True

    def _set_asdm_to_outcome_vis_if_imagemode_is_ampcal(self, cp: imaging_params.CommonParameters,
                                                        rgp: imaging_params.ReductionGroupParameters):
        """Set ASDM to vis.outcome if imagemode of the vis is AMPCAL.

        Args:
            cp : Common parameter object of prepare()
            rgp : Reduction group parameter object of prepare()
        """
        if self.inputs.is_ampcal:
            if len(cp.infiles) == 1 and (rgp.asdm not in ['', None]):
                rgp.imager_result.outcome['vis'] = rgp.asdm

    def _has_imager_result_outcome(self, rgp: imaging_params.ReductionGroupParameters) -> bool:
        """Check whether imager_result.outcome has some value or not.

        Args:
            rgp : Reduction group parameter object of prepare()
        Returns:
            True if imager_result.outcome has some value.
        """
        return rgp.imager_result.outcome is not None

    def _has_nro_imager_result_outcome(self, rgp: imaging_params.ReductionGroupParameters) -> bool:
        """Check whether imager_result_nro.outcome has some value or not.

        Args:
            rgp : Reduction group parameter object of prepare()
        Returns:
            True if imager_result_nro.outcome has some value.
        """
        return rgp.imager_result_nro is not None and rgp.imager_result_nro.outcome is not None

    def _detect_missed_lines(self,
                             cp: imaging_params.CommonParameters,
                             rgp: imaging_params.ReductionGroupParameters,
                             pp: imaging_params.PostProcessParameters ):
        """
        Detect lines that are possibly missed to be identified

        Args:
            cp  : Common parameter object of prepare()
            rgp : Reduction group parameter object of prepare()
            pp  : Imaging post process parameters of prepare()
        Raises:
            ValueError if unknown mask mode is returned DetectMissedLines.analyze()
        """
        do_plot = not basetask.DISABLE_WEBLOG

        # pick valid_lines
        valid_lines = [ ll[0:2] for ll in rgp.channelmap_range_list[0] if ll[2] is True ]

        # get linefree ranges from pp
        linefree_ranges = convert_range_list_to_ranges( pp.include_channel_range )

        # initialize
        missed_lines = detect_missed_lines.DetectMissedLines(
            self.inputs.context,
            rgp.msobjs,
            rgp.spwid_list,
            rgp.fieldid_list,
            rgp.imager_result.outcome['image'],
            rgp.imager_result.frequency_channel_reversed,
            cp.edge,
            do_plot
        )

        # analyze
        detections = missed_lines.analyze( valid_lines, linefree_ranges )

        # register the results
        rgp.imager_result.outcome['line_emission_off_range_at_peak'] = detections['single_beam']
        rgp.imager_result.outcome['line_emission_off_range_extended'] = detections['moment_mask']

    def _detect_contamination(self, rgp: imaging_params.ReductionGroupParameters):
        """Detect contamination of image.

        Args:
            rgp : Reduction group parameter object of prepare()
        """
        # PIPE-251: detect contamination
        do_plot = not basetask.DISABLE_WEBLOG
        contaminated = detectcontamination.detect_contamination(
            self.inputs.context, rgp.imager_result.outcome['image'],
            rgp.imager_result.frequency_channel_reversed,
            do_plot
        )
        rgp.imager_result.outcome['contaminated'] = contaminated

    def _append_result(self, cp: imaging_params.CommonParameters, rgp: imaging_params.ReductionGroupParameters):
        """Append result to RGP.

        Args:
            rgp : Reduction group parameter object of prepare()
        """
        cp.results.append(rgp.imager_result)

    def analyse(self, result: 'SDImagingResults') -> 'SDImagingResults':
        """Override method of basetask.

        Args:
            result : Result object

        Returns:
            Result object
        """
        return result

    def _get_rms_exclude_freq_range_image(self, to_frame: str, cp: imaging_params.CommonParameters,
                                          rgp: imaging_params.ReductionGroupParameters) -> List[Tuple[Number, Number]]:
        """
        Return a combined list of frequency ranges.

        This method combines deviation mask, channel map ranges, and edges.

        Args
            to_frame : The frequency frame of output
            cp : Common parameter object of prepare()
            rgp : Reduction group parameter object of prepare()

        Returns:
            a list of combined frequency ranges in output frequency frame (to_frame),
            e.g., [ [minfreq0,maxfreq0], [minfreq1,maxfreq1], ...]
        """
        image_rms_freq_range = []
        channelmap_range = []
        # LOG.info("#####Raw chanmap_range={}".format(str(rgp.chanmap_range_list)))
        for chanmap_range in rgp.chanmap_range_list:
            for map_range in chanmap_range:
                if map_range[2]:
                    min_chan = int(map_range[0] - map_range[1] * 0.5)
                    max_chan = int(numpy.ceil(map_range[0] + map_range[1] * 0.5))
                    channelmap_range.append([min_chan, max_chan])
        LOG.debug("#####CHANNEL MAP RANGE = {}".format(str(channelmap_range)))
        for i in range(len(rgp.msobjs)):
            # define channel ranges of lines and deviation mask for each MS
            msobj = rgp.msobjs[i]
            fieldid = rgp.fieldids[i]
            antid = rgp.antids[i]
            spwid = rgp.spwids[i]
            spwobj = msobj.get_spectral_window(spwid)
            deviation_mask = getattr(msobj, 'deviation_mask', {})
            exclude_range = deviation_mask.get((fieldid, antid, spwid), [])
            LOG.debug("#####{} : DEVIATION MASK = {}".format(msobj.basename, str(exclude_range)))
            if len(exclude_range) == 1 and exclude_range[0] == [0, spwobj.num_channels - 1]:
                # deviation mask is full channel range when all data are flagged
                LOG.warning("Ignoring DEVIATION MASK of {} (SPW {:d}, FIELD {:d}, ANT {:d}). "
                            "Possibly all data flagged".format(msobj.basename, spwid, fieldid, antid))
                exclude_range = []
            if cp.edge[0] > 0:
                exclude_range.append([0, cp.edge[0] - 1])
            if cp.edge[1] > 0:
                exclude_range.append([spwobj.num_channels - cp.edge[1], spwobj.num_channels - 1])
            if len(channelmap_range) > 0:
                exclude_range.extend(channelmap_range)
            # check the validity of channel number and fix it when out of range
            min_chan = 0
            max_chan = spwobj.num_channels - 1
            exclude_channel_range = [[max(min_chan, x[0]), min(max_chan, x[1])]
                                     for x in merge_ranges(exclude_range)]
            LOG.info("{} : channel map and deviation mask channel ranges "
                     "in MS frame = {}".format(msobj.basename, str(exclude_channel_range)))
            # define frequency ranges of RMS
            exclude_freq_range = numpy.zeros(2 * len(exclude_channel_range))
            for jseg in range(len(exclude_channel_range)):
                (lfreq, rfreq) = (spwobj.channels.chan_freqs[jchan] for jchan in exclude_channel_range[jseg])
                # handling of LSB
                exclude_freq_range[2 * jseg: 2 * jseg + 2] = [min(lfreq, rfreq), max(lfreq, rfreq)]
            LOG.debug("#####CHANNEL MAP AND DEVIATION MASK FREQ RANGE = {}".format(str(exclude_freq_range)))
            if len(exclude_freq_range) == 0:
                continue  # no ranges to add
            # convert MS freqency ranges to image frame
            field = msobj.fields[fieldid]
            direction_ref = field.mdirection
            start_time = msobj.start_time
            end_time = msobj.end_time
            me = casa_tools.measures
            qa = casa_tools.quanta
            qmid_time = qa.quantity(start_time['m0'])
            qmid_time = qa.add(qmid_time, end_time['m0'])
            qmid_time = qa.div(qmid_time, 2.0)
            time_ref = me.epoch(rf=start_time['refer'],
                                v0=qmid_time)
            position_ref = msobj.antennas[antid].position

            if to_frame == 'REST':
                mse = casa_tools.ms
                mse.open(msobj.name)
                obstime = qa.time(qmid_time, form='ymd')[0]
                v_to = mse.cvelfreqs(spwids=[spwid], obstime=obstime, outframe='SOURCE')
                v_from = mse.cvelfreqs(spwids=[spwid], obstime=obstime, outframe=spwobj.frame)
                mse.close()
                _to_imageframe = interpolate.interp1d(v_from, v_to, kind='linear',
                                                      bounds_error=False, fill_value='extrapolate')
            else:
                # initialize
                me.done()
                me.doframe(time_ref)
                me.doframe(direction_ref)
                me.doframe(position_ref)

                def _to_imageframe(x):
                    m = me.frequency(rf=spwobj.frame, v0=qa.quantity(x, 'Hz'))
                    converted = me.measure(v=m, rf=to_frame)
                    qout = qa.convert(converted['m0'], outunit='Hz')
                    return qout['value']

            image_rms_freq_range.extend(map(_to_imageframe, exclude_freq_range))
            me.done()

        # LOG.info("#####Overall LINE CHANNELS IN IMAGE FRAME = {}".format(str(image_rms_freq_range)))
        if len(image_rms_freq_range) == 0:
            return image_rms_freq_range

        return merge_ranges(numpy.reshape(image_rms_freq_range, (len(image_rms_freq_range) // 2, 2), 'C'))

    def get_imagename(self, source: str, spwids: List[int],
                      antenna: str=None, asdm: str=None, stokes: str=None, specmode: str='cube') -> str:
        """Generate a filename of the image.

        Args:
            source : Source name
            spwids : SpW IDs
            antenna : Antenna name. Defaults to None.
            asdm : ASDM. Defaults to None.
            stokes : Stokes parameter. Defaults to None.
            specmode : specmode for tsdimaging. Defaults to 'cube'.

        Raises:
            ValueError: if asdm is not provided for ampcal

        Returns:
            A filename of the image
        """
        context = self.inputs.context
        is_nro = sdutils.is_nro(context)
        if is_nro:
            namer = filenamer.Image(virtspw=False)
        else:
            namer = filenamer.Image()
        if self.inputs.is_ampcal:
            nameroot = asdm
            if nameroot is None:
                raise ValueError('ASDM uid must be provided to construct ampcal image name')
        elif is_nro:
            nameroot = ''
        else:
            nameroot = context.project_structure.ousstatus_entity_id
            if nameroot == 'unknown':
                nameroot = 'oussid'
        nameroot = filenamer.sanitize(nameroot)
        namer._associations.asdm(nameroot)
        # output_dir = context.output_dir
        # if output_dir:
        #    namer.output_dir(output_dir)
        if not is_nro:
            namer.stage(context.stage)

        namer.source(source)
        if self.inputs.is_ampcal:
            namer.intent(self.inputs.mode.lower())
        elif is_nro:
            pass
        else:
            namer.science()
        namer.spectral_window(spwids[0])
        if stokes is None:
            stokes = self.stokes
        namer.polarization(stokes)
        namer.specmode(specmode)
        # so far we always create native resolution, full channel image
        # namer.spectral_image()
        namer._associations.format('image.sd')
        # namer.single_dish()
        namer.antenna(antenna)
        # iteration is necessary for exportdata
        namer.iteration(0)
        imagename = namer.get_filename()
        return imagename

    def _get_stat_chans(self, imagename: str,
                        combined_rms_exclude: List[Tuple[float, float]],
                        edge: Tuple[int, int]=(0, 0)) -> List[int]:
        """Return a list of channel ranges to calculate image statistics.

        Args:
            imagename : A filename of the image
            combined_rms_exclude : A list of frequency ranges to exclude
            edge : The left and right edge channels to exclude. Defaults to (0, 0).
        Retruns:
            A 1-d list of channel ranges to INCLUDE in calculation of image
            statistics, e.g., [imin0, imax0, imin0, imax0, ...]
        """
        with casa_tools.ImageReader(imagename) as ia:
            try:
                cs = ia.coordsys()
                faxis = cs.findaxisbyname('spectral')
                num_chan = ia.shape()[faxis]
                exclude_chan_ranges = convert_frequency_ranges_to_channels(combined_rms_exclude, cs, num_chan)
            finally:
                cs.done()
        LOG.info("Merged spectral line channel ranges of combined image = {}".format(str(exclude_chan_ranges)))
        include_chan_ranges = invert_ranges(exclude_chan_ranges, num_chan, edge)
        LOG.info("Line free channel ranges of image to calculate RMS = {}".format(str(include_chan_ranges)))
        return include_chan_ranges

    def _get_stat_region(self, pp: imaging_params.PostProcessParameters) -> Optional[str]:
        """
        Retrun region to calculate statistics.

        Median width, height, and position angle is adopted as a reference
        map extent and then the width and height will be shrinked by 2 beam
        size in each direction.

        Arg:
            pp : Imaging post process parameters of prepare()

        Retruns:
            Region expression string of a rotating box.
            Returns None if no valid region of interest is defined.
        """
        cqa = casa_tools.quanta
        beam_unit = cqa.getunit(pp.beam['major'])
        assert cqa.getunit(pp.beam['minor']) == beam_unit
        beam_size = numpy.sqrt(cqa.getvalue(pp.beam['major'])[0] * cqa.getvalue(pp.beam['minor'])[0])
        center_unit = 'deg'
        angle_unit = None
        for r in pp.raster_infos:
            if r is None:
                continue
            angle_unit = cqa.getunit(r.scan_angle)
            break
        if angle_unit is None:
            LOG.warning('No valid raster information available.')
            return None

        def _value_in_unit(quantity: dict, unit: str) -> float:
            # Get value(s) of quantity in a specified unit
            return cqa.getvalue(cqa.convert(quantity, unit))

        def _extract_values(value: str, unit: str) -> Number:
            # Extract valid values of specified attributes in list
            return [_value_in_unit(getattr(r, value), unit) for r in pp.raster_infos if r is not None]

        rep_width = numpy.nanmedian(_extract_values('width', beam_unit))
        rep_height = numpy.nanmedian(_extract_values('height', beam_unit))
        rep_angle = numpy.nanmedian([cqa.getvalue(r.scan_angle) for r in pp.raster_infos if r is not None])
        center_ra = numpy.nanmedian(_extract_values('center_ra', center_unit))
        center_dec = numpy.nanmedian(_extract_values('center_dec', center_unit))
        width = rep_width - beam_size
        height = rep_height - beam_size
        if width <= 0 or height <= 0:  # No valid region selected.
            return None
        if pp.org_direction is not None:
            (center_ra, center_dec) = direction_utils.direction_recover(center_ra,
                                                                        center_dec,
                                                                        pp.org_direction)
        center = [cqa.tos(cqa.quantity(center_ra, center_unit)),
                  cqa.tos(cqa.quantity(center_dec, center_unit))]

        region = "rotbox[{}, [{}{}, {}{}], {}{}]".format(center,
                                                         width, beam_unit,
                                                         height, beam_unit,
                                                         rep_angle, angle_unit)
        return region

    def get_raster_info_list(self, cp: imaging_params.CommonParameters,
                             rgp: imaging_params.ReductionGroupParameters) -> List[RasterInfo]:
        """
        Retrun a list of raster information.

        Each raster infromation is analyzed for element wise combination of
        infile, antenna, field, and SpW IDs in input parameter lists.

        Args:
            cp : Common parameter object of prepare()
            rgp : Reduction group parameter object of prepare()

        Returns:
            A list of RasterInfo. If raster information could not be obtained,
            the corresponding elements in the list will be None.
        """
        assert len(rgp.combined.infiles) == len(rgp.combined.antids)
        assert len(rgp.combined.infiles) == len(rgp.combined.fieldids)
        assert len(rgp.combined.infiles) == len(rgp.combined.spws)
        raster_info_list = []
        for (infile, antid, fieldid, spwid) in \
                zip(rgp.combined.infiles, rgp.combined.antids, rgp.combined.fieldids, rgp.combined.spws):
            msobj = self.inputs.context.observing_run.get_ms(name=infile)
            # Non raster data set.
            if msobj.observing_pattern[antid][spwid][fieldid] != 'RASTER':
                f = msobj.get_fields(field_id=fieldid)[0]
                LOG.warning('Not a raster map: field {} in {}'.format(f.name, msobj.basename))
                raster_info_list.append(None)
            dt = cp.dt_dict[msobj.basename]
            try:
                raster_info_list.append(_analyze_raster_pattern(dt, msobj, fieldid, spwid, antid, rgp))
            except Exception:
                f = msobj.get_fields(field_id=fieldid)[0]
                a = msobj.get_antenna(antid)[0]
                LOG.info('Could not get raster information of field {}, Spw {}, Ant {}, MS {}. '
                         'Potentially be because all data are flagged.'.format(f.name, spwid, a.name, msobj.basename))
                raster_info_list.append(None)
        assert len(rgp.combined.infiles) == len(raster_info_list)
        return raster_info_list

    def calculate_theoretical_image_rms(self, cp: imaging_params.CommonParameters,
                                        rgp: imaging_params.ReductionGroupParameters,
                                        pp: imaging_params.PostProcessParameters) -> Dict[str, float]:
        """Calculate theoretical RMS of an image (PIPE-657).

        Args:
            cp : Common parameter object of prepare()
            rgp : Reduction group parameter object of prepare()
            pp : Imaging post process parameters of prepare()

        Note: the number of elements in rgp.combined.antids, fieldids, spws, and pols should be equal
              to that of infiles

        Returns:
            A quantum value of theoretical image RMS.
            The value of quantity will be negative when calculation is aborted, i.e., -1.0 Jy/beam
        """
        tirp = imaging_params.TheoreticalImageRmsParameters(pp, self.inputs.context)

        if len(rgp.combined.infiles) == 0:
            LOG.error('No MS given to calculate a theoretical RMS. Aborting calculation of theoretical thermal noise.')
            return tirp.failed_rms
        assert len(rgp.combined.infiles) == len(rgp.combined.antids)
        assert len(rgp.combined.infiles) == len(rgp.combined.fieldids)
        assert len(rgp.combined.infiles) == len(rgp.combined.spws)
        assert len(rgp.combined.infiles) == len(rgp.combined.pols)
        assert len(rgp.combined.infiles) == len(pp.raster_infos)

        for (tirp.infile, tirp.antid, tirp.fieldid, tirp.spwid, tirp.pol_names, tirp.raster_info) in \
            zip(rgp.combined.infiles, rgp.combined.antids, rgp.combined.fieldids,
                rgp.combined.spws, rgp.combined.pols, pp.raster_infos):
            halt, skip = self._loop_initializer_of_theoretical_image_rms(cp, rgp, tirp)
            if halt:
                return tirp.failed_rms
            if skip:
                continue

            # effective BW
            self._obtain_effective_BW(tirp)
            # obtain average Tsys
            self._obtain_average_tsys(tirp)
            # obtain Wx, and Wy
            self._obtain_wx_and_wy(tirp)
            # obtain T_ON
            self._obtain_t_on_actual(tirp)
            if tirp.t_on_act < MIN_INTEGRATION_SEC:
                continue
            # obtain calibration tables applied
            self._obtain_calibration_tables_applied(tirp)
            # obtain Tsub,on, Tsub,off (average ON and OFF integration duration per raster row)
            if not self._obtain_t_sub_on_off(tirp):
                return tirp.failed_rms
            if tirp.t_sub_on < MIN_INTEGRATION_SEC or \
                    tirp.t_sub_off < MIN_INTEGRATION_SEC:
                continue
            # obtain factors by convolution function
            # (THIS ASSUMES SF kernel with either convsupport = 6 (ALMA) or 3 (NRO)
            # TODO: Ggeneralize factor for SF, and Gaussian convolution function
            if not self._obtain_and_set_factors_by_convolution_function(pp, tirp):
                return tirp.failed_rms

        if tirp.weight_sum == 0:
            LOG.warning('No rms estimate is available.')
            return tirp.failed_rms

        _theoretical_rms = numpy.sqrt(tirp.sq_rms) / tirp.weight_sum
        LOG.info('Theoretical RMS of image = {} {}'.format(_theoretical_rms, pp.brightnessunit))
        return tirp.cqa.quantity(_theoretical_rms, pp.brightnessunit)

    def _obtain_t_sub_on_off(self, tirp: imaging_params.TheoreticalImageRmsParameters) -> bool:
        """Obtain Tsub,on and Tsub,off. A sub method of calculate_theoretical_image_rms().

        Args:
            tirp : Parameter object of calculate_theoretical_image_rms()

        Returns:
            False if it cannot get Tsub,on/off values by some error.

        Raises:
            BaseException : raises when it cannot find a sky caltable applied.
        """
        tirp.t_sub_on = tirp.cqa.getvalue(tirp.cqa.convert(tirp.raster_info.row_duration, tirp.time_unit))[0]
        _sky_field = tirp.calmsobj.calibration_strategy['field_strategy'][tirp.fieldid]
        try:
            _skytab = ''
            _caltabs = tirp.context.callibrary.applied.get_caltable('ps')
            # For some reasons, sky caltable is not registered to calstate
            for _cto, _cfrom in tirp.context.callibrary.applied.merged().items():
                if _cto.vis == tirp.calmsobj.name and (_cto.field == '' or
                                                       tirp.fieldid in
                                                       [f.id for f in tirp.calmsobj.get_fields(name=_cto.field)]):
                    for _cf in _cfrom:
                        if _cf.gaintable in _caltabs:
                            _skytab = _cf.gaintable
                            break
        except BaseException:
            LOG.error('Could not find a sky caltable applied. ' + tirp.error_msg)
            raise
        if not os.path.exists(_skytab):
            LOG.warning('Could not find a sky caltable applied. ' + tirp.error_msg)
            return False
        LOG.info('Searching OFF scans in {}'.format(os.path.basename(_skytab)))
        with casa_tools.TableReader(_skytab) as tb:
            _interval_unit = tb.getcolkeyword('INTERVAL', 'QuantumUnits')[0]
            _t = tb.query('SPECTRAL_WINDOW_ID=={}&&ANTENNA1=={}&&FIELD_ID=={}'.format(tirp.spwid, tirp.antid,
                                                                                      _sky_field),
                           columns='INTERVAL')
            if _t.nrows == 0:
                LOG.warning('No sky caltable row found for spw {}, antenna {}, field {} in {}. {}'.format(
                    tirp.spwid, tirp.antid, _sky_field, os.path.basename(_skytab), tirp.error_msg))
                _t.close()
                return False
            try:
                _interval = _t.getcol('INTERVAL')
            finally:
                _t.close()

        tirp.t_sub_off = tirp.cqa.getvalue(tirp.cqa.convert(tirp.cqa.quantity(_interval.mean(),
                                                                              _interval_unit), tirp.time_unit))[0]
        LOG.info('Subscan Time ON = {} {}, OFF = {} {}'.format(tirp.t_sub_on, tirp.time_unit,
                 tirp.t_sub_off, tirp.time_unit))
        return True

    def _obtain_jy_per_k(self, pp: imaging_params.PostProcessParameters,
                         tirp: imaging_params.TheoreticalImageRmsParameters) -> Union[float, bool]:
        """Obtain Jy/K. A sub method of calculate_theoretical_image_rms().

        Args:
            pp : Imaging post process parameters of prepare()
            tirp : Parameter object of calculate_theoretical_image_rms()

        Returns:
            Jy/K value or failure flag

        Raises:
            BaseException : raises when it cannot find a Jy/K caltable applied.
        """
        if pp.brightnessunit == 'K':
            _jy_per_k = 1.0
            LOG.info('No Jy/K conversion was performed to the image.')
        else:
            try:
                _k2jytab = ''
                _caltabs = tirp.context.callibrary.applied.get_caltable(('amp', 'gaincal'))
                _found = _caltabs.intersection(tirp.calst.get_caltable(('amp', 'gaincal')))
                if len(_found) == 0:
                    LOG.warning('Could not find a Jy/K caltable applied. ' + tirp.error_msg)
                    return False
                if len(_found) > 1:
                    LOG.warning('More than one Jy/K caltables are found.')
                _k2jytab = _found.pop()
                LOG.info('Searching Jy/K factor in {}'.format(os.path.basename(_k2jytab)))
            except BaseException:
                LOG.error('Could not find a Jy/K caltable applied. ' + tirp.error_msg)
                raise
            if not os.path.exists(_k2jytab):
                LOG.warning('Could not find a Jy/K caltable applied. ' + tirp.error_msg)
                return False
            with casa_tools.TableReader(_k2jytab) as tb:
                _t = tb.query('SPECTRAL_WINDOW_ID=={}&&ANTENNA1=={}'.format(tirp.spwid, tirp.antid),
                              columns='CPARAM')
                if _t.nrows == 0:
                    LOG.warning('No Jy/K caltable row found for spw {}, antenna {} in {}. {}'.format(tirp.spwid,
                                tirp.antid, os.path.basename(_k2jytab), tirp.error_msg))
                    _t.close()
                    return False
                try:
                    tc = _t.getcol('CPARAM')
                finally:
                    _t.close()

                _jy_per_k = (1. / tc.mean(axis=-1).real ** 2).mean()
                LOG.info('Jy/K factor = {}'.format(_jy_per_k))  # obtain Jy/k factor
        return _jy_per_k

    def _obtain_and_set_factors_by_convolution_function(self, pp: imaging_params.PostProcessParameters,
                                                        tirp: imaging_params.TheoreticalImageRmsParameters) -> bool:
        """Obtain factors by convolution function, and set it into TIRP. A sub method of calculate_theoretical_image_rms().

        Args:
            pp : Imaging post process parameters of prepare()
            tirp : Parameter object of calculate_theoretical_image_rms()

        Returns:
            False if it cannot get Jy/K
        """
        policy = observatory_policy.get_imaging_policy(tirp.context)
        jy_per_k = self._obtain_jy_per_k(pp, tirp)
        if jy_per_k is False:
            return False
        ang = tirp.cqa.getvalue(tirp.cqa.convert(tirp.raster_info.scan_angle, 'rad'))[0] + 0.5 * numpy.pi
        c_proj = numpy.sqrt((tirp.cy_val * numpy.sin(ang)) ** 2 + (tirp.cx_val * numpy.cos(ang)) ** 2)
        inv_variant_on = tirp.effBW * numpy.abs(tirp.cx_val * tirp.cy_val) * \
            tirp.t_on_act / tirp.width / tirp.height
        inv_variant_off = tirp.effBW * c_proj * tirp.t_sub_off * tirp.t_on_act / tirp.t_sub_on / tirp.height
        weight = tirp.t_on_act ** 2 * tirp.t_sub_off / tirp.t_sub_on
        for ipol in tirp.polids:
            tirp.sq_rms += (jy_per_k * tirp.mean_tsys_per_pol[ipol] * weight) ** 2 * \
                (policy.get_conv2d() ** 2 / inv_variant_on + policy.get_conv1d() ** 2 / inv_variant_off)
            tirp.weight_sum += weight
        return True

    def _obtain_t_on_actual(self, tirp: imaging_params.TheoreticalImageRmsParameters):
        """Obtain T_on actual. A sub method of calculate_theoretical_image_rms().

        Args:
            tirp : Parameter object of calculate_theoretical_image_rms()
        """
        unit = tirp.dt.getcolkeyword('EXPOSURE', 'UNIT')
        # Total time on source of data not online flagged for all polarizations.
        t_on_tot = tirp.cqa.getvalue(tirp.cqa.convert(tirp.cqa.quantity(
            tirp.dt.getcol('EXPOSURE').take(tirp.index_list, axis=-1).sum(), unit), tirp.time_unit))[0]
        # Additional flag fraction
        flag_summary = tirp.dt.getcol('FLAG_SUMMARY').take(tirp.index_list, axis=-1)
        (num_pol, num_data) = flag_summary.shape
        # PIPE-2508: fraction of data where any of polarization is flagged. (FLAG_SUMMARY is 0 for flagged data)
        # TODO: This logic should be improved in future when full polarization is supported.
        num_flagged = numpy.count_nonzero(flag_summary.sum(axis=0) < num_pol)
        frac_flagged = num_flagged / num_data
        LOG.debug('Per polarization flag summary (# of integrations): total=%d, flagged per pol=%s, any pol flagged=%d',
                  num_data, num_data - flag_summary.sum(axis=1), num_flagged)
        # the actual time on source
        tirp.t_on_act = t_on_tot * (1.0 - frac_flagged)
        LOG.info('The actual on source time = {} {}'.format(tirp.t_on_act, tirp.time_unit))
        LOG.info('- total time on source (excl. online flagged integrations) = {} {}'.format(t_on_tot, tirp.time_unit))
        LOG.info('- addtional flag fraction = {} %'.format(100 * frac_flagged))

    def _obtain_calibration_tables_applied(self, tirp: imaging_params.TheoreticalImageRmsParameters):
        """Obtain calibration tables applied. A sub method of calculate_theoretical_image_rms().

        Args:
            tirp : Parameter object of calculate_theoretical_image_rms()
        """
        _calto = callibrary.CalTo(vis=tirp.calmsobj.name, field=str(tirp.fieldid))
        tirp.calst = tirp.context.callibrary.applied.trimmed(tirp.context, _calto)

    def _obtain_wx_and_wy(self, tirp: imaging_params.TheoreticalImageRmsParameters):
        """Obtain Wx and Wy. A sub method of calculate_theoretical_image_rms().

        Args:
            tirp : Parameter object of calculate_theoretical_image_rms()
        """
        tirp.width = tirp.cqa.getvalue(tirp.cqa.convert(tirp.raster_info.width, tirp.ang_unit))[0]
        tirp.height = tirp.cqa.getvalue(tirp.cqa.convert(tirp.raster_info.height, tirp.ang_unit))[0]

    def _obtain_average_tsys(self, tirp: imaging_params.TheoreticalImageRmsParameters):
        """Obtain average Tsys. A sub method of calculate_theoretical_image_rms().

        Args:
            tirp : Parameter object of calculate_theoretical_image_rms()
        """
        tirp.mean_tsys_per_pol = tirp.dt.getcol('TSYS').take(tirp.index_list, axis=-1).mean(axis=-1)
        LOG.info('Mean Tsys = {} K'.format(str(tirp.mean_tsys_per_pol)))

    def _obtain_effective_BW(self, tirp: imaging_params.TheoreticalImageRmsParameters):
        """Obtain effective BW. A sub method of calculate_theoretical_image_rms().

        Args:
            tirp : Parameter object of calculate_theoretical_image_rms()
        """
        with casa_tools.MSMDReader(tirp.infile) as _msmd:
            tirp.effBW = _msmd.chaneffbws(tirp.spwid).mean()
            LOG.info('Using an MS effective bandwidth, {} kHz'.format(tirp.effBW * 0.001))

    def _loop_initializer_of_theoretical_image_rms(self, cp: imaging_params.CommonParameters,
                                                   rgp: imaging_params.ReductionGroupParameters,
                                                   tirp: imaging_params.TheoreticalImageRmsParameters) -> Tuple[bool]:
        """Initialize imaging_params.TheoreticalImageRmsParameters for the loop of calculate_theoretical_image_rms().

        Args:
            cp : Common parameter object of prepare()
            rgp : Reduction group parameter object of prepare()
            tirp : Parameter object of calculate_theoretical_image_rms()

        Returns:
            Tupled flag to describe the loop action [go|halt|skip].
                GO   : (False, False)
                HALT : (True,  True)
                SKIP : (False, True)
        """
        tirp.msobj = tirp.context.observing_run.get_ms(name=tirp.infile)
        _callist = tirp.context.observing_run.get_measurement_sets_of_type([DataType.REGCAL_CONTLINE_ALL])
        tirp.calmsobj = sdutils.match_origin_ms(_callist, tirp.msobj.origin_ms)
        _dd_corrs = tirp.msobj.get_data_description(spw=tirp.spwid).corr_axis
        tirp.polids = [_dd_corrs.index(p) for p in tirp.pol_names if p in _dd_corrs]
        _field_name = tirp.msobj.get_fields(field_id=tirp.fieldid)[0].name
        tirp.error_msg = 'Aborting calculation of theoretical thermal noise of ' + \
                          'Field {} and SpW {}'.format(_field_name, rgp.combined.spws)
        HALT = (True, True)
        SKIP = (False, True)
        GO = (False, False)
        if tirp.msobj.observing_pattern[tirp.antid][tirp.spwid][tirp.fieldid] != 'RASTER':
            LOG.warning('Unable to calculate RMS of non-Raster map. ' + tirp.error_msg)
            return HALT
        LOG.info(
            'Processing MS {}, Field {}, SpW {}, '
            'Antenna {}, Pol {}'.
            format(tirp.msobj.basename, _field_name, tirp.spwid,
                   tirp.msobj.get_antenna(tirp.antid)[0].name, str(tirp.pol_names)))
        if tirp.raster_info is None:
            _rsres = RasterScanHeuristicsResult(tirp.msobj)
            rgp.imager_result.rasterscan_heuristics_results_incomp \
                             .setdefault(tirp.msobj.origin_ms, []) \
                             .append(_rsres)
            _rsres.set_result_fail(tirp.antid, tirp.spwid, tirp.fieldid)
            LOG.debug(f'Raster scan analysis incomplete. Skipping calculation of theoretical image RMS : EB:{tirp.msobj.execblock_id}:{tirp.msobj.antennas[tirp.antid].name}')
            return SKIP
        tirp.dt = cp.dt_dict[tirp.msobj.basename]
        # Note: index_list is a list of DataTable row IDs for selected data EXCLUDING rows where all pols are flagged online.
        tirp.index_list = common.get_index_list_for_ms(tirp.dt, [tirp.msobj.origin_ms],
                                                       [tirp.antid], [tirp.fieldid], [tirp.spwid])
        if len(tirp.index_list) == 0:  # this happens when permanent flag is set to all selection.
            LOG.info('No unflagged row in DataTable. Skipping further calculation.')
            return SKIP
        return GO


def _analyze_raster_pattern(datatable: DataTable, msobj: MeasurementSet,
                            fieldid: int, spwid: int, antid: int, rgp: 'imaging_params.ReductionGroupParameters') -> RasterInfo:
    """Analyze raster scan pattern from pointing in DataTable.

    Args:
        datatable : DataTable instance
        msobj : MS class instance to process
        fieldid : A field ID to process
        spwid : An SpW ID to process
        antid : An antenna ID to process
        rgp : Reduction group parameter object of prepare()

    Returns:
        A named Tuple of RasterInfo
    """
    origin_basename = os.path.basename(msobj.origin_ms)
    metadata = rasterutil.read_datatable(datatable)
    pflag = metadata.pflag
    ra = metadata.ra
    dec = metadata.dec
    exposure = datatable.getcol('EXPOSURE')
    timetable = datatable.get_timetable(ant=antid, spw=spwid, field_id=fieldid, ms=origin_basename, pol=None)
    # dtrow_list is a list of numpy array holding datatable rows separated by raster rows
    # [[r00, r01, r02, ...], [r10, r11, r12, ...], ...]
    dtrow_list_nomask = rasterutil.extract_dtrow_list(timetable)
    dtrow_list = [rows[pflag[rows]] for rows in dtrow_list_nomask if numpy.any(pflag[rows] == True)]
    radec_unit = datatable.getcolkeyword('OFS_RA', 'UNIT')
    assert radec_unit == datatable.getcolkeyword('OFS_DEC', 'UNIT')
    exp_unit = datatable.getcolkeyword('EXPOSURE', 'UNIT')
    _rsres = RasterScanHeuristicsResult(msobj)
    rgp.imager_result.rasterscan_heuristics_results_rgap \
                     .setdefault(msobj.origin_ms, []) \
                     .append(_rsres)
    try:
        gap_r = rasterscan.find_raster_gap(ra, dec, dtrow_list)
    except Exception as e:
        if isinstance(e, RasterScanHeuristicsFailure):
            _rsres.set_result_fail(antid, spwid, fieldid)
            LOG.debug('{} : EB:{}:{}'.format(e, msobj.execblock_id, msobj.antennas[antid].name))
        try:
            dtrow_list_large = rasterutil.extract_dtrow_list(timetable, for_small_gap=False)
            se_small = [(v[0], v[-1]) for v in dtrow_list]
            se_large = [(v[0], v[-1]) for v in dtrow_list_large]
            gap_r = []
            for sl, el in se_large:
                for i, (ss, es) in enumerate(se_small):
                    if ss == sl:
                        gap_r.append(i)
                        break
            gap_r.append(len(dtrow_list))
        except Exception:
            LOG.warning('Could not find gaps between raster scans. No result is produced.')
            return None

    cqa = casa_tools.quanta
    idx_all = numpy.concatenate(dtrow_list)
    mean_dec = numpy.mean(datatable.getcol('DEC')[idx_all])
    dec_unit = datatable.getcolkeyword('DEC', 'UNIT')
    map_center_dec = cqa.getvalue(
        cqa.convert(cqa.quantity(mean_dec, dec_unit), 'rad')
    )[0]
    dec_factor = numpy.abs(numpy.cos(map_center_dec))

    ndata = len(dtrow_list)
    duration = numpy.fromiter(
        map(lambda x: exposure[x].sum(), dtrow_list),
        dtype=float, count=ndata
    )
    num_integration = numpy.fromiter(
        map(len, dtrow_list), dtype=int, count=ndata
    )
    center_ra = numpy.fromiter(
        map(lambda x: ra[x].mean(), dtrow_list),
        dtype=float, count=ndata
    )
    center_dec = numpy.fromiter(
        map(lambda x: dec[x].mean(), dtrow_list),
        dtype=float, count=ndata
    )
    delta_ra = numpy.fromiter(
        map(lambda x: (ra[x[-1]] - ra[x[0]]) * dec_factor, dtrow_list),
        dtype=float, count=ndata
    )
    delta_dec = numpy.fromiter(
        map(lambda x: dec[x[-1]] - dec[x[0]], dtrow_list),
        dtype=float, count=ndata
    )
    height_list = []
    for s, e in zip(gap_r[:-1], gap_r[1:]):
        start_ra = center_ra[s]
        start_dec = center_dec[s]
        end_ra = center_ra[e - 1]
        end_dec = center_dec[e - 1]
        height_list.append(
            numpy.hypot((start_ra - end_ra) * dec_factor, start_dec - end_dec)
        )
    LOG.debug('REFACTOR: ant %s, spw %s, field %s', antid, spwid, fieldid)
    LOG.debug('REFACTOR: map_center_dec=%s, dec_factor=%s', map_center_dec, dec_factor)
    LOG.debug('REFACTOR: duration=%s', list(duration))
    LOG.debug('REFACTOR: num_integration=%s', list(num_integration))
    LOG.debug('REFACTOR: delta_ra=%s', list(delta_ra))
    LOG.debug('REFACTOR: delta_dec=%s', list(delta_dec))
    LOG.debug('REFACTOR: center_ra=%s', list(center_ra))
    LOG.debug('REFACTOR: center_dec=%s', list(center_dec))
    LOG.debug('REFACTOR: height_list=%s', list(height_list))
    LOG.debug('REFACTOR: dtrows')
    for rows in dtrow_list:
        LOG.debug('REFACTOR:   %s', list(rows))
    center_ra = numpy.array(center_ra)
    center_dec = numpy.array(center_dec)
    row_sep_ra = (center_ra[1:] - center_ra[:-1]) * dec_factor
    row_sep_dec = center_dec[1:] - center_dec[:-1]
    row_separation = numpy.median(numpy.hypot(row_sep_ra, row_sep_dec))
    # find complate raster
    num_row_int = rasterutil.find_most_frequent(num_integration)
    complete_idx = numpy.where(num_integration >= num_row_int)
    # raster scan parameters
    row_duration = numpy.array(duration)[complete_idx].mean()
    assert row_duration > 0
    row_delta_ra = numpy.abs(delta_ra)[complete_idx].mean()
    row_delta_dec = numpy.abs(delta_dec)[complete_idx].mean()
    width = numpy.hypot(row_delta_ra, row_delta_dec)
    assert width > 0
    sign_ra = +1.0 if delta_ra[complete_idx[0][0]] >= 0 else -1.0
    sign_dec = +1.0 if delta_dec[complete_idx[0][0]] >= 0 else -1.0
    scan_angle = math.atan2(sign_dec * row_delta_dec, sign_ra * row_delta_ra)
    height = numpy.max(height_list)
    assert height > 0
    center = (cqa.quantity(0.5 * (center_ra.min() + center_ra.max()), radec_unit),
              cqa.quantity(0.5 * (center_dec.min() + center_dec.max()), radec_unit))
    raster_info = RasterInfo(center[0], center[1],
                             cqa.quantity(width, radec_unit), cqa.quantity(height, radec_unit),
                             cqa.quantity(scan_angle, 'rad'), cqa.quantity(row_separation, radec_unit),
                             cqa.quantity(row_duration, exp_unit))
    LOG.info('Raster Information')
    LOG.info('- Map Center: [{}, {}]'.format(cqa.angle(raster_info.center_ra, prec=8, form='time')[0],
                                             cqa.angle(raster_info.center_dec, prec=8)[0]))
    LOG.info('- Scan Extent: [{}, {}] (scan direction: {})'.format(cqa.tos(raster_info.width),
                                                                   cqa.tos(raster_info.height),
                                                                   cqa.tos(raster_info.scan_angle)))
    LOG.info('- Raster row separation = {}'.format(cqa.tos(raster_info.row_separation)))
    LOG.info('- Raster row scan duration = {}'.format(cqa.tos(cqa.convert(raster_info.row_duration, 's'))))
    return raster_info


def calc_image_statistics(imagename: str, chans: str, region: str) -> dict:
    """Return image statistics with channel and region selection.

    Args:
        imagename : Path to image to calculate statistics
        chans : Channel range selection string, e.g., '0~110;240~300'
        region : Region definition string.

    Returns:
        A dictionary of statistic values returned by ia.statistics.
    """
    LOG.info("Calculateing image statistics of chans='{}', region='{}' in {}".format(chans, region, imagename))
    rg = casa_tools.regionmanager
    with casa_tools.ImageReader(imagename) as ia:
        cs = ia.coordsys()
        try:
            chan_sel = rg.frombcs(csys=cs.torecord(), shape=ia.shape(), chans=chans)
        finally:
            cs.done()
            rg.done()
        subim = ia.subimage(region=chan_sel)
        try:
            stat = subim.statistics(region=region)
        finally:
            subim.close()
    return stat


# Utility methods to calcluate channel ranges
def convert_frequency_ranges_to_channels(range_list: List[Tuple[float, float]],
                                         cs: 'coordsys', num_chan: int) -> List[Tuple[int, int]]:
    """Convert frequency ranges to channel ones.

    Args:
        range_list : A list of min/max frequency ranges,
            e.g., [[fmin0,fmax0],[fmin1, fmax1],...]
        cs : A coordinate system to convert world values to pixel one
        num_chan : The number of channels in frequency axis

    Returns:
        A list of min/max channels, e.g., [[imin0, imax0],[imin1,imax1],...]
    """
    faxis = cs.findaxisbyname('spectral')
    ref_world = cs.referencevalue()['numeric']
    LOG.info("Aggregated spectral line frequency ranges of combined image = {}".format(str(range_list)))
    channel_ranges = []  # should be list for sort
    for segment in range_list:
        ref_world[faxis] = segment[0]
        start_chan = cs.topixel(ref_world)['numeric'][faxis]
        ref_world[faxis] = segment[1]
        end_chan = cs.topixel(ref_world)['numeric'][faxis]
        # handling of LSB
        min_chan = min(start_chan, end_chan)
        max_chan = max(start_chan, end_chan)
        # LOG.info("#####Freq to Chan: [{:f}, {:f}] -> [{:f}, {:f}]".format(segment[0], segment[1], min_chan, max_chan))
        if max_chan < -0.5 or min_chan > num_chan - 0.5:  # out of range
            # LOG.info("#####Omitting channel range [{:f}, {:f}]".format(min_chan, max_chan))
            continue
        channel_ranges.append([max(int(min_chan), 0),
                               min(int(max_chan), num_chan - 1)])
    channel_ranges.sort()
    return merge_ranges(channel_ranges)


def convert_range_list_to_string(range_list: List[int]) -> str:
    """Convert a list of index ranges to string.

    Args:
        range_list : A list of ranges, e.g., [imin0, imax0, imin1, imax1, ...]

    Returns:
        A string in form, e.g., 'imin0~imax0;imin1~imax1'

    Examples:
        >>> convert_range_list_to_string( [5, 10, 15, 20] )
        '5~10;15~20'
    """
    stat_chans = str(';').join(['{:d}~{:d}'.format(range_list[iseg], range_list[iseg + 1])
                               for iseg in range(0, len(range_list), 2)])
    return stat_chans


def convert_range_list_to_ranges(range_list: List[int]) -> List[List[int]]:
    """
    Convert a list of index ranges to list of signle ranges

    Args:
        range_list : A list of ranges, e.g., [imin0, imax0, imin1, imax1, ...]

    Returns:
        A list of single ranges, e.g. '[ [imin0, imax0], [imin1, imax1], ...]

    Example:
        >>> convert_range_list_to_string( [5, 10, 15, 20] )
        '[[5, 10], [15, 20]]'
    """
    ranges = [ [range_list[i], range_list[i+1]] for i in range(0, len(range_list), 2) ]

    return ranges


def merge_ranges(range_list: List[Tuple[Number, Number]]) -> List[Tuple[Number, Number]]:
    """Merge overlapping ranges in range_list.

    Args:
        range_list : A list of ranges to merge, e.g., [ [min0,max0], [min1,max1], .... ]
                    Each range in the list should be in ascending order (min0 <= max0)
                    There is no assumption in the order of ranges, e.g., min0 w.r.t min1

    Raises:
        ValueError: too few elements in the range description, such as [] or [min0]

    Returns:
        A list of merged ranges
        e.g., [[min_merged0,max_marged0], [min_merged1,max_merged1], ....]
    """
    # LOG.info("#####Merge ranges: {}".format(str(range_list)))
    num_range = len(range_list)
    if num_range == 0:
        return []
    merged = [range_list[0][0:2]]
    for i in range(1, num_range):
        segment = range_list[i]
        if len(segment) < 2:
            raise ValueError("segments in range list must have 2 elements")
        overlap = -1
        for j in range(len(merged)):
            if segment[1] < merged[j][0] or segment[0] > merged[j][1]:  # no overlap
                continue
            else:
                overlap = j
                break
        if overlap < 0:
            merged.append(segment[0:2])
        else:
            merged[j][0] = min(merged[j][0], segment[0])
            merged[j][1] = max(merged[j][1], segment[1])
    # Check if further merge is necessary
    while len(merged) < num_range:
        num_range = len(merged)
        merged = merge_ranges(merged)
    # LOG.info("#####Merged: {}".format(str(merged)))
    return merged


def invert_ranges(id_range_list: List[Tuple[int, int]],
                  num_ids: int, edge: Tuple[int, int]) -> List[int]:
    """Return inverted ID ranges.

    Args:
        id_range_list : A list of min/max ID ranges to invert. The list should
            be sorted in the ascending order of min IDs.
        num_ids : Number of IDs to consider
        edge : The left and right edges to exclude

    Returns:
        A 1-d list of inverted ranges

    Examples:
        >>> id_range_list = [[5,10],[15,20]]
        >>> num_ids = 30
        >>> edge = (2,3)
        >>> invert_ranges(id_range_list, num_ids, edge)
        [2, 4, 11, 14, 21, 26]
    """
    inverted_list = []
    if len(id_range_list) == 0:
        inverted_list = [edge[0], num_ids - 1 - edge[1]]
    else:
        if id_range_list[0][0] > edge[0]:
            inverted_list.extend([edge[0], id_range_list[0][0] - 1])
        for j in range(len(id_range_list) - 1):
            start_include = id_range_list[j][1] + 1
            end_include = id_range_list[j + 1][0] - 1
            if start_include <= end_include:
                inverted_list.extend([start_include, end_include])
        if id_range_list[-1][1] + 1 < num_ids - 1 - edge[1]:
            inverted_list.extend([id_range_list[-1][1] + 1, num_ids - 1 - edge[1]])
    return inverted_list
