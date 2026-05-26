from datetime import datetime

from numpy.typing import NDArray

from .antenna import Antenna
from .antennaarray import AntennaArray
from .datadescription import DataDescription
from .datatype import DataType
from .field import Field
from .fluxmeasurement import FluxMeasurement
from .measurementset import MeasurementSet
from .polarization import Polarization
from .observingrun import ObservingRun
from .scan import Scan
from .source import Source
from .spectralwindow import SpectralWindow, SpectralWindowWithChannelSelection
from .state import State
from .datatable import DataTableImpl as DataTable
from .singledish import MSReductionGroupDesc, MSReductionGroupMember
from pipeline.infrastructure.utils.casa_types import EpochDict


def _rebuild_pydantic_models() -> None:
	types_namespace = {
		**globals(),
		'datetime': datetime,
		'NDArray': NDArray,
		'EpochDict': EpochDict,
	}

	for model in (
		AntennaArray,
		DataDescription,
		Field,
		FluxMeasurement,
		MeasurementSet,
		ObservingRun,
		Polarization,
		Scan,
		Source,
		SpectralWindow,
		State,
		MSReductionGroupMember,
		MSReductionGroupDesc,
	):
		model.model_rebuild(_types_namespace=types_namespace, raise_errors=False)


_rebuild_pydantic_models()
