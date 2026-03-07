"""Pydantic-based State domain objects prototype for Phase 5 modernization."""

from __future__ import annotations

import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, field_validator

import pipeline.infrastructure as infrastructure

LOG = infrastructure.get_logger(__name__)


class State(BaseModel):
    """A logical representation of rows in the STATE table.

    Relates STATE_ID (in the MAIN table) to the observing mode(s) and
    corresponding pipeline intent(s).

    Attributes:
        id: Numerical identifier of this State.
        obs_mode: Unique obs_mode values associated with this State.
        obs_mode_mapping: Class-level dictionary mapping obs_mode strings to
            pipeline intent strings.
    """

    id: int
    obs_mode: str

    obs_mode_mapping: ClassVar[dict[str, str]] = {}

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra='allow',
        validate_default=True,
    )

    def __init__(self, state_id: int | None = None, obs_mode: Any | None = None, **data: Any) -> None:
        """Initialize a State.

        The legacy pipeline constructs states positionally as
        ``State(state_id, obs_mode)``.
        """

        if state_id is not None and 'id' not in data:
            data['id'] = state_id
        if obs_mode is not None and 'obs_mode' not in data:
            data['obs_mode'] = obs_mode

        super().__init__(**data)

    @field_validator('obs_mode', mode='before')
    @classmethod
    def _normalize_obs_mode(cls, value: Any) -> str:
        if value is None:
            return ''

        # Work around historical NumPy empty-string/bytes quirks.
        try:
            import numpy as np

            if isinstance(value, np.bytes_):
                value = value.tobytes()
            elif isinstance(value, np.str_):
                value = str(value)
        except Exception:
            pass

        if isinstance(value, bytes):
            value = value.decode('utf-8', errors='ignore')

        text = str(value).strip()

        # Canonicalize common separator variants so the existing mapping tables
        # match reliably without changing their contents.
        for suffix in ('ON_SOURCE', 'OFF_SOURCE', 'UNSPECIFIED'):
            text = text.replace(f'.{suffix}', f'#{suffix}')
            text = text.replace(f'_{suffix}', f'#{suffix}')

        text = text.replace('UNSPECIFIED.UNSPECIFIED', 'UNSPECIFIED#UNSPECIFIED')
        text = text.replace('UNSPECIFIED_UNSPECIFIED', 'UNSPECIFIED#UNSPECIFIED')

        return text

    def __repr__(self) -> str:
        return '{0}({1!r}, {2!r})'.format(self.__class__.__name__, self.id, self.obs_mode)

    def __hash__(self) -> int:
        return hash((self.__class__, self.id, self.obs_mode))

    @property
    def intents(self) -> set[str]:
        """Return all intents associated with this State."""

        return {intent for mode, intent in self.obs_mode_mapping.items() if self.obs_mode.find(mode) != -1}

    def get_obs_mode_for_intent(self, intent: str) -> list[str]:
        """Return list of obs_mode values associated with given intent."""

        intents = {i.strip('*') for i in intent.split(',') if i is not None}
        return [
            mode
            for mode, pipeline_intent in self.obs_mode_mapping.items()
            if pipeline_intent in intents and self.obs_mode.find(mode) != -1
        ]

    def __str__(self) -> str:
        return '{0}(id={1}, intents={2})'.format(self.__class__.__name__, self.id, self.intents)


class StateALMA(State):
    """State representation for ALMA Observatory measurement sets."""

    obs_mode_mapping: ClassVar[dict[str, str]] = {
        'CALIBRATE_POLARIZATION#ON_SOURCE': 'POLARIZATION',
        'CALIBRATE_POLARIZATION.ON_SOURCE': 'POLARIZATION',
        'CALIBRATE_POLARIZATION_ON_SOURCE': 'POLARIZATION',
        'CALIBRATE_POL_ANGLE#ON_SOURCE': 'POLANGLE',
        'CALIBRATE_POL_ANGLE.ON_SOURCE': 'POLANGLE',
        'CALIBRATE_POL_ANGLE_ON_SOURCE': 'POLANGLE',
        'CALIBRATE_POL_LEAKAGE#ON_SOURCE': 'POLLEAKAGE',
        'CALIBRATE_POL_LEAKAGE.ON_SOURCE': 'POLLEAKAGE',
        'CALIBRATE_POL_LEAKAGE_ON_SOURCE': 'POLLEAKAGE',
        'CALIBRATE_BANDPASS#ON_SOURCE': 'BANDPASS',
        'CALIBRATE_BANDPASS.ON_SOURCE': 'BANDPASS',
        'CALIBRATE_BANDPASS_ON_SOURCE': 'BANDPASS',
        'CALIBRATE_AMPLI#ON_SOURCE': 'AMPLITUDE',
        'CALIBRATE_AMPLI.ON_SOURCE': 'AMPLITUDE',
        'CALIBRATE_AMPLI_ON_SOURCE': 'AMPLITUDE',
        'CALIBRATE_FLUX#ON_SOURCE': 'AMPLITUDE',
        'CALIBRATE_FLUX.ON_SOURCE': 'AMPLITUDE',
        'CALIBRATE_FLUX_ON_SOURCE': 'AMPLITUDE',
        'CALIBRATE_PHASE#ON_SOURCE': 'PHASE',
        'CALIBRATE_PHASE.ON_SOURCE': 'PHASE',
        'CALIBRATE_PHASE_ON_SOURCE': 'PHASE',
        'CALIBRATE_TARGET#ON_SOURCE': 'TARGET',
        'CALIBRATE_TARGET.ON_SOURCE': 'TARGET',
        'CALIBRATE_TARGET_ON_SOURCE': 'TARGET',
        'CALIBRATE_POINTING#ON_SOURCE': 'POINTING',
        'CALIBRATE_POINTING.ON_SOURCE': 'POINTING',
        'CALIBRATE_POINTING_ON_SOURCE': 'POINTING',
        'CALIBRATE_FOCUS#ON_SOURCE': 'FOCUS',
        'CALIBRATE_FOCUS.ON_SOURCE': 'FOCUS',
        'CALIBRATE_FOCUS_ON_SOURCE': 'FOCUS',
        'CALIBRATE_WVR#ON_SOURCE': 'WVR',
        'CALIBRATE_WVR.ON_SOURCE': 'WVR',
        'CALIBRATE_WVR_ON_SOURCE': 'WVR',
        'CALIBRATE_ATMOSPHERE#ON_SOURCE': 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE.ON_SOURCE': 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE_ON_SOURCE': 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE#AMBIENT': 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE#HOT': 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE#OFF_SOURCE': 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE.OFF_SOURCE': 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE_OFF_SOURCE': 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE#TEST': 'ATMOSPHERE',
        'CALIBRATE_SIDEBAND_RATIO#ON_SOURCE': 'SIDEBAND',
        'CALIBRATE_SIDEBAND_RATIO.ON_SOURCE': 'SIDEBAND',
        'CALIBRATE_SIDEBAND_RATIO_ON_SOURCE': 'SIDEBAND',
        'CALIBRATE_SIDEBAND_RATIO#OFF_SOURCE': 'SIDEBAND',
        'CALIBRATE_SIDEBAND_RATIO.OFF_SOURCE': 'SIDEBAND',
        'CALIBRATE_SIDEBAND_RATIO_OFF_SOURCE': 'SIDEBAND',
        'CALIBRATE_DIFFGAIN#REFERENCE': 'DIFFGAINREF',
        'CALIBRATE_DIFFGAIN#ON_SOURCE': 'DIFFGAINSRC',
        'CALIBRATE_DELAY#ON_SOURCE': 'CHECK',
        'CALIBRATE_DELAY.ON_SOURCE': 'CHECK',
        'CALIBRATE_DELAY_ON_SOURCE': 'CHECK',
        'OBSERVE_CHECK_SOURCE#ON_SOURCE': 'CHECK',
        'OBSERVE_CHECK_SOURCE.ON_SOURCE': 'CHECK',
        'OBSERVE_CHECK_SOURCE_ON_SOURCE': 'CHECK',
        'OBSERVE_TARGET#ON_SOURCE': 'TARGET',
        'OBSERVE_TARGET.ON_SOURCE': 'TARGET',
        'OBSERVE_TARGET_ON_SOURCE': 'TARGET',
        'OBSERVE_TARGET#OFF_SOURCE': 'REFERENCE',
        'OBSERVE_TARGET.OFF_SOURCE': 'REFERENCE',
        'OBSERVE_TARGET_OFF_SOURCE': 'REFERENCE',
    }

    def model_post_init(self, __context: Any) -> None:
        if 'CALIBRATE_FLUX' in self.obs_mode:
            LOG.trace('Translating %s intent to AMPLITUDE for state #%s', self.obs_mode, self.id)


class StateALMACycle0(StateALMA):
    """State representation for ALMA Cycle 0 measurement sets."""

    _PHASE_BYPASS_INTENTS: ClassVar[frozenset[str]] = frozenset(('BANDPASS', 'AMPLITUDE'))

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)

        intents = self.intents
        has_bypass_intent = not intents.isdisjoint(self._PHASE_BYPASS_INTENTS)

        if 'PHASE' not in intents or not has_bypass_intent:
            return

        LOG.info('Cycle 0 mislabeled data workaround: removing PHASE intent for State %s', self.id)

        phase_obs_modes = [k for k, v in self.obs_mode_mapping.items() if v == 'PHASE']
        dephased_obs_modes = [m for m in self.obs_mode.split(',') if m not in phase_obs_modes]
        self.obs_mode = ','.join(dephased_obs_modes)


class StateVLA(State):
    """State representation for VLA Observatory measurement sets."""

    obs_mode_mapping: ClassVar[dict[str, str]] = {
        'CALIBRATE_POLARIZATION#ON_SOURCE': 'POLARIZATION',
        'CALIBRATE_POLARIZATION.ON_SOURCE': 'POLARIZATION',
        'CALIBRATE_POLARIZATION_ON_SOURCE': 'POLARIZATION',
        'CALIBRATE_POLARIZATION#UNSPECIFIED': 'POLARIZATION',
        'CALIBRATE_POL_ANGLE#ON_SOURCE': 'POLANGLE',
        'CALIBRATE_POL_ANGLE.ON_SOURCE': 'POLANGLE',
        'CALIBRATE_POL_ANGLE_ON_SOURCE': 'POLANGLE',
        'CALIBRATE_POL_ANGLE#UNSPECIFIED': 'POLANGLE',
        'CALIBRATE_POL_LEAKAGE#ON_SOURCE': 'POLLEAKAGE',
        'CALIBRATE_POL_LEAKAGE.ON_SOURCE': 'POLLEAKAGE',
        'CALIBRATE_POL_LEAKAGE_ON_SOURCE': 'POLLEAKAGE',
        'CALIBRATE_POL_LEAKAGE#UNSPECIFIED': 'POLLEAKAGE',
        'CALIBRATE_BANDPASS#ON_SOURCE': 'BANDPASS',
        'CALIBRATE_BANDPASS.ON_SOURCE': 'BANDPASS',
        'CALIBRATE_BANDPASS_ON_SOURCE': 'BANDPASS',
        'CALIBRATE_AMPLI#ON_SOURCE': 'PHASE',
        'CALIBRATE_AMPLI.ON_SOURCE': 'PHASE',
        'CALIBRATE_AMPLI_ON_SOURCE': 'PHASE',
        'CALIBRATE_FLUX#ON_SOURCE': 'AMPLITUDE',
        'CALIBRATE_FLUX.ON_SOURCE': 'AMPLITUDE',
        'CALIBRATE_FLUX_ON_SOURCE': 'AMPLITUDE',
        'CALIBRATE_PHASE#ON_SOURCE': 'PHASE',
        'CALIBRATE_PHASE.ON_SOURCE': 'PHASE',
        'CALIBRATE_PHASE_ON_SOURCE': 'PHASE',
        'CALIBRATE_TARGET#ON_SOURCE': 'TARGET',
        'CALIBRATE_TARGET.ON_SOURCE': 'TARGET',
        'CALIBRATE_TARGET_ON_SOURCE': 'TARGET',
        'CALIBRATE_POINTING#ON_SOURCE': 'POINTING',
        'CALIBRATE_POINTING.ON_SOURCE': 'POINTING',
        'CALIBRATE_POINTING_ON_SOURCE': 'POINTING',
        'CALIBRATE_FOCUS#ON_SOURCE': 'FOCUS',
        'CALIBRATE_FOCUS.ON_SOURCE': 'FOCUS',
        'CALIBRATE_FOCUS_ON_SOURCE': 'FOCUS',
        'CALIBRATE_WVR#ON_SOURCE': 'WVR',
        'CALIBRATE_WVR.ON_SOURCE': 'WVR',
        'CALIBRATE_WVR_ON_SOURCE': 'WVR',
        'CALIBRATE_ATMOSPHERE#ON_SOURCE': 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE.ON_SOURCE': 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE_ON_SOURCE': 'ATMOSPHERE',
        'CALIBRATE_SIDEBAND_RATIO#ON_SOURCE': 'SIDEBAND',
        'CALIBRATE_SIDEBAND_RATIO.ON_SOURCE': 'SIDEBAND',
        'CALIBRATE_SIDEBAND_RATIO_ON_SOURCE': 'SIDEBAND',
        'OBSERVE_TARGET#ON_SOURCE': 'TARGET',
        'OBSERVE_TARGET.ON_SOURCE': 'TARGET',
        'OBSERVE_TARGET_ON_SOURCE': 'TARGET',
        'OBSERVE_TARGET#UNSPECIFIED': 'TARGET',
        'OBSERVE_TARGET#OFF_SOURCE': 'REFERENCE',
        'OBSERVE_TARGET.OFF_SOURCE': 'REFERENCE',
        'OBSERVE_TARGET_OFF_SOURCE': 'REFERENCE',
        'CALIBRATE_BANDPASS#UNSPECIFIED': 'BANDPASS',
        'CALIBRATE_FLUX#UNSPECIFIED': 'AMPLITUDE',
        'CALIBRATE_PHASE#UNSPECIFIED': 'PHASE',
        'CALIBRATE_AMPLI#UNSPECIFIED': 'PHASE',
        'UNSPECIFIED#UNSPECIFIED': 'UNSPECIFIED#UNSPECIFIED',
        'SYSTEM_CONFIGURATION': 'SYSTEM_CONFIGURATION',
        'SYSTEM_CONFIGURATION#UNSPECIFIED': 'SYSTEM_CONFIGURATION',
    }


class StateAPEX(State):
    """State representation for APEX Observatory measurement sets."""

    obs_mode_mapping: ClassVar[dict[str, str]] = {
        'OBSERVE_TARGET#ON_SOURCE': 'TARGET',
    }


class StateSMT(State):
    """State representation for SMT Observatory measurement sets."""

    obs_mode_mapping: ClassVar[dict[str, str]] = {
        'OBSERVE_TARGET#ON_SOURCE': 'TARGET',
    }


class StateNAOJ(State):
    """State representation for Nobeyama or ASTE Observatory measurement sets."""

    obs_mode_mapping: ClassVar[dict[str, str]] = {
        'OBSERVE_TARGET#ON_SOURCE': 'TARGET',
        'OBSERVE_TARGET#OFF_SOURCE': 'REFERENCE',
        'CALIBRATE_ATMOSPHERE#R_SOURCE': 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE#SKY_SOURCE': 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE#ZERO_SOURCE': 'ATMOSPHERE',
    }


class StateFactory:
    """Factory for building State instances based on facility and start time."""

    _CYCLE0_END: ClassVar[datetime.datetime] = datetime.datetime(2013, 1, 21)

    def __init__(self, facility: str, dt_start: datetime.datetime | None) -> None:
        self.facility = facility
        self.dt_start = dt_start
        self._state_cls = self._resolve_state_class()

    def _resolve_state_class(self) -> type[State]:
        facility_upper = self.facility.upper()

        if 'ALMA' in facility_upper:
            if self.dt_start is not None and self.dt_start < self._CYCLE0_END:
                return StateALMACycle0
            return StateALMA
        if 'VLA' in facility_upper or 'EVLA' in facility_upper:
            return StateVLA
        if 'APEX' in facility_upper:
            return StateAPEX
        if facility_upper == 'SMT':
            return StateSMT
        if facility_upper in {'NRO', 'ASTE'}:
            return StateNAOJ

        return State

    def create_state(self, state_id: int, obs_mode: Any) -> State:
        """Create a State instance for the given ID and observing mode."""

        return self._state_cls(state_id=state_id, obs_mode=obs_mode)
