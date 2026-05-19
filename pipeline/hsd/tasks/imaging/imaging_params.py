"""Parameter classes of Imaging."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Generic, TypeVar

import numpy

from casatools import coordsys
from pipeline.hsd.tasks.common import utils as sdutils
from pipeline.infrastructure import casa_tools
from pipeline.infrastructure.utils.debugwrapper import debugwrapper

if TYPE_CHECKING:
    from typing import Any, Final, NamedTuple

    from pipeline.hsd.tasks.imaging.resultobjects import SDImagingResults, SDImagingResultItem
    from pipeline.hsd.tasks.common.direction_utils import Direction
    from pipeline.infrastructure import Context
    from pipeline.domain.datatable import DataTableImpl
    from pipeline.domain import MeasurementSet
    from pipeline.domain.singledish import MSReductionGroupDesc

    class RasterInfo(NamedTuple):
        center_ra: float
        center_dec: float
        width: float
        height: float
        scan_angle: float
        row_separation: float
        row_duration: float

    ImageGroup = dict[str, list[MeasurementSet | int | list[str | list[list[float | bool]]]]]

T = TypeVar('T')


class ObservedList(list[T], Generic[T]):
    """Class inherit list to observe its behavior.

    This class intends to observe/output list stuff for debugging more easier.
    If you want to search a needle in a haystack, please uncomment out @debugwrapper()."""

    # @debugwrapper(msg='list.setitem')
    def __setitem__(self, index: int, value: object):
        """Overrode list.__setitem__().

        Args:
            index : index
            value : object to set at index
        """
        super().__setitem__(index, value)

    # @debugwrapper(msg='list.insert')
    def insert(self, index: int, value: object):
        """Overrode list.insert().

        Args:
            index : index
            value : object to insert at index
        """
        super().insert(index, value)

    # @debugwrapper(msg='list.append')
    def append(self, value: object):
        """Overrode list.append().

        Args:
            value : object to append
        """
        super().append(value)

    # @debugwrapper(msg='list.extend')
    def extend(self, value: list):
        """Overrode list.extend().

        Args:
            value : object to merge
        """
        super().extend(value)


class Parameters:
    """Abstract class of Parameter object.

    Note: _immutable_parameters is the list which is set some parameter names of a class inherit Parameter.
    All parameters in _immutable_parameters are set immutable by freeze().
    """

    # List immutable-able parameter names in it at a child class
    _immutable_parameters = []
    _immutable_prefix = '__immutable_'

    def __init__(self) -> None:
        """Initialize an instance."""
        self.__dict__[self._immutable_prefix] = False
        # initialize immutable-able parameters.
        # the name of parameters must be started with an alphanumeric character.
        for _name in self._immutable_parameters:
            if re.match(r'^[a-zA-Z0-9].\w*$', _name):
                self.__dict__[f'{self._immutable_prefix}{_name}'] = True
            else:
                raise ValueError('invalid parameter name')

    def is_immutable(self, _name: str='') -> bool:
        """Check itself or an attribute whether immutable or not.

        Args:
            _name (str): Attribute name. If it is a default value, the method returns
                         a boolean whether the instance itself is immutable or not.

        Returns:
            True if it is immutable.
        """
        return self.__dict__.get(f'{self._immutable_prefix}{_name}', False)

    def freeze(self) -> None:
        """Set the instance immutable."""
        self.__dict__[self._immutable_prefix] = True

    @debugwrapper(msg='setattr')
    def __setattr__(self, _name: str, _value: Any) -> None:
        """Override object.__setattr__().

        Args:
            _name (str): Attribute name
            _value (Any): Attribute Object

        Raises:
            NotImplementedError: raises if _name is immutable.
        """
        if self.is_immutable() and self.is_immutable(_name):
            raise NotImplementedError(f'attribute {_name} is immutable.')
        super.__setattr__(self, _name, _value)


class CommonParameters(Parameters):
    """Common parameters class of prepare()."""

    _immutable_parameters = ['reduction_group', 'restfreq_list', 'ms_names', 'session_names', 'args_spw',
                             'imagemode', 'is_nro', 'results', 'edge', 'dt_dict']

    def is_not_nro(self) -> numpy.bool_:
        """Return True if is_nro is False.

        Returns:
            True if this data is not from NRO.
        """
        return not self.is_nro


def initialize_common_parameters(args_spw: dict[str, str], dt_dict: dict[str, DataTableImpl],
                                 edge: list[int], imagemode: str, in_field: str,
                                 infiles: list[str], is_nro: numpy.bool_, ms_list: list[MeasurementSet],
                                 ms_names: list[str], session_names: list[str], reduction_group: dict[int, MSReductionGroupDesc],
                                 restfreq_list: str | list[str], results: SDImagingResults,
                                 ) -> CommonParameters:
    """Initialize an instance of CommonParameters and return it.

    Args:
        args_spw (dict[str, str]): Spw selection per MS
        dt_dict (dict[str, DataTableImpl]): Dictionary of input MS and corresponding datatable
        edge (list[int]): Edge channel of most recent SDBaselineResults or [0, 0]
        imagemode (str): Image mode
        in_field (str): Comma-separated list of target field names that are extracted from all input MSs
        infiles (list[str]): List of input files
        is_nro (numpy.bool_): Flag of NRO data
        ms_list (list[MeasurementSet]): List of ms to process
        ms_names (list[str]): List of name of ms in ms_list
        session_names (list[str]): List of session name of ms in ms_list
        reduction_group (dict[int, MSReductionGroupDesc]): Reduction group object
        restfreq_list (str | list[str]): List of rest frequency
        results (SDImagingResults): Instance of SDImagingResults

    Returns:
        An instance of CommonParameters
    """
    _tmp = CommonParameters()
    _tmp.args_spw = args_spw
    _tmp.dt_dict = dt_dict
    _tmp.edge = edge
    _tmp.imagemode = imagemode
    _tmp.in_field = in_field
    _tmp.infiles = infiles
    _tmp.is_nro = is_nro
    _tmp.ms_list = ms_list
    _tmp.ms_names = ms_names
    _tmp.session_names = session_names
    _tmp.reduction_group = reduction_group
    _tmp.restfreq_list = restfreq_list
    _tmp.results = results
    _tmp.freeze()
    return _tmp


class ReductionGroupParameters(Parameters):
    """Parameters of Reduction Group Processing."""

    def __init__(self, group_id: int, group_desc: MSReductionGroupDesc):
        """Initialize an object with group value.

        Args:
            group_id : Reduction group ID
            group_desc : MeasurementSet Reduction Group Desciption object
        """
        super().__init__()
        self.group_id: int = group_id
        self.group_desc: MSReductionGroupDesc = group_desc
        self.antenna_list: list[int] | None = None
        self.antids: list[int] | None = None
        self.ant_name: str | None = None
        self.asdm: str | None = None
        self.cellx: dict[str, float] | None = None
        self.celly: dict[str, float] | None = None
        self.chanmap_range_list: list[list[list[float | bool]]] | None = None
        self.channelmap_range_list: list[list[list[float | bool]]] | None = None
        self.combined: CombinedImageParameters | None = None
        self.coord_set: bool = False
        self.correlations: str | None = None
        self.fieldid_list: list[int] | None = None
        self.fieldids: list[int] | None = None
        self.image_group: ImageGroup | None = None
        self.imagename: str | None = None
        self.imagename_nro: str | None = None
        self.imager_result: SDImagingResultItem | None = None
        self.imager_result_nro: SDImagingResultItem | None = None
        self.member_list: list[int] | None = None
        self.members: list[list[MeasurementSet | int | list[str]]] | None = None
        self.msobjs: list[MeasurementSet] | None = None
        self.name: str | None = None
        self.nx: int | numpy.int64 | None = None
        self.ny: int | numpy.int64 | None = None
        self.org_direction: Direction | None = None
        self.phasecenter: str | None = None
        self.polslist: list[list[str]] | None = None
        self.pols_list: list[list[str]] | None = None
        self.ref_ms: MeasurementSet | None = None
        self.restfreq: str | None = None
        self.rmss: list[float] | None = None
        self.source_name: str | None = None
        self.specmode: str | None = None
        self.spwid_list: list[int] | None = None
        self.spwids: list[int] | None = None
        self.stokes_list: list[str] | None = None
        self.tocombine: ToCombineImageParameters | None = None
        self.validsps: list[list[int]] | None = None
        self.v_spwids: list[int] | None = None


class CombinedImageParameters(Parameters):
    """Parameter class for combined image."""

    def __init__(self):
        """Initialize an object."""
        super().__init__()
        self.antids: ObservedList[int] = ObservedList()
        self.fieldids: ObservedList[int] = ObservedList()
        self.infiles: ObservedList[str] = ObservedList()
        self.pols: ObservedList[list[str]] = ObservedList()
        self.rms_exclude: ObservedList[numpy.ndarray] = ObservedList()
        self.spws: ObservedList[int] = ObservedList()
        self.v_spws: ObservedList[int] = ObservedList()
        self.v_spws_unique: ObservedList[int] = ObservedList()

    def extend(self, _cp: CommonParameters, _rgp: ReductionGroupParameters):
        """Extend list properties using CP and RGP.

        Args:
            _cp : CommonParameters object
            _rgp : ReductionGroupParameters object
        """
        self.infiles.extend(_cp.infiles)
        self.antids.extend(_rgp.antids)
        self.fieldids.extend(_rgp.fieldids)
        self.spws.extend(_rgp.spwids)
        self.v_spws.extend(_rgp.v_spwids)
        self.pols.extend(_rgp.polslist)


class ToCombineImageParameters(Parameters):
    """Parameter class to combine image."""

    def __init__(self):
        """Initialize an object."""
        super().__init__()
        self.images: ObservedList[str] = ObservedList()
        self.images_nro: ObservedList[str] = ObservedList()
        self.org_directions: ObservedList[Direction] = ObservedList()
        self.org_directions_nro: ObservedList[Direction] = ObservedList()
        self.specmodes: ObservedList[str] = ObservedList()


class PostProcessParameters(Parameters):
    """Parameters for post processing of image generating."""

    def __init__(self):
        """Initialize an object."""
        super().__init__()
        self.beam: dict[str, dict[str, float]] | None = None
        self.brightnessunit: str | None = None
        self.chan_width: numpy.float64 | None = None
        self.cs: coordsys | None = None
        self.faxis: int | None = None
        self.imagename: str | None = None
        self.image_rms: float | None = None
        self.image_max: float | None = None
        self.image_min: float | None = None
        self.include_channel_range: list[int] | None = None
        self.is_representative_source_and_spw: bool | None = None
        self.nx: numpy.int64 | None = None
        self.ny: numpy.int64 | None = None
        self.org_direction: Direction | None = None
        self.qcell: dict[str, dict[str, float]] | None = None
        self.raster_infos: list[RasterInfo] | None = None
        self.region: str | None = None
        self.rmss: list[float] | None = None
        self.stat_chans: str | None = None
        self.stat_freqs: str | None = None
        self.theoretical_rms: dict[str, float] | None = None
        self.validsps: list[int] | None = None

    def done(self):
        if isinstance(self.cs, coordsys):
            self.cs.done()


class TheoreticalImageRmsParameters(Parameters):
    """ Parameter class of calculate_theoretical_image_rms()."""

    def __init__(self, _pp: PostProcessParameters, context: Context):
        """Initialize the object.

        Args:
            _pp : imaging post process parameters of prepare()
            context : pipeline Context
        """
        super().__init__()
        self.cqa: Any = casa_tools.quanta
        self.failed_rms: Any = self.cqa.quantity(-1, _pp.brightnessunit)
        self.sq_rms: float = 0.0
        self.weight_sum: float = 0.0
        self.time_unit: Final[str] = 's'
        self.ang_unit: str = self.cqa.getunit(_pp.qcell[0])
        self.cx_val: float = self.cqa.getvalue(_pp.qcell[0])[0]
        self.cy_val: float = self.cqa.getvalue(self.cqa.convert(_pp.qcell[1], self.ang_unit))[0]
        self.bandwidth: float = numpy.abs(_pp.chan_width)
        self.context: Context = context
        self.is_nro: bool = sdutils.is_nro(context)
        self.infile: str | None = None
        self.antid: int | None = None
        self.fieldid: int | None = None
        self.spwid: int | None = None
        self.pol_names: list[str] | None = None
        self.polids: list[int] | None = None
        self.raster_info: RasterInfo | None = None
        self.msobj: MeasurementSet | None = None
        self.calmsobj: MeasurementSet | None = None
        self.error_msg: str | None = None
        self.dt: DataTableImpl | None = None
        self.index_list: numpy.ndarray | None = None
        self.effBW: float | None = None
        self.mean_tsys_per_pol: numpy.ndarray | None = None
        self.width: float | None = None
        self.height: float | None = None
        self.calst: Any | None = None
        self.t_on_act: float | None = None
        self.t_sub_on: float | None = None
        self.t_sub_off: float | None = None
