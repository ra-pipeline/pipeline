import datetime

import pipeline.infrastructure as infrastructure

LOG = infrastructure.get_logger(__name__)


class State:
    """A logical representation of rows in the STATE table.

    Relates STATE_ID (in the MAIN table) to the observing mode(s) and
    corresponding pipeline intent(s).

    Attributes:
        id: Numerical identifier of this State.
        obs_mode: Unique obs_mode values associated with this State.
        obs_mode_mapping: Class-level dictionary mapping obs_mode strings to
            pipeline intent strings.
    """
    obs_mode_mapping = {}

    __slots__ = ('id', 'obs_mode')

    def __getstate__(self) -> tuple[int, str]:
        return self.id, self.obs_mode

    def __setstate__(self, state) -> None:
        self.id, self.obs_mode = state

    def __init__(self, state_id: int, obs_mode: str) -> None:
        """
        Initialize a State object.

        Args:
            state_id: Numerical identifier of this State.
            obs_mode: Unique obs_mode values associated with this State.
        """
        self.id = state_id
        # work around NumPy bug with empty strings
        # http://projects.scipy.org/numpy/ticket/1239
        self.obs_mode = str(obs_mode)

    def __repr__(self) -> str:
        return '{0}({1!r}, {2!r})'.format(
            self.__class__.__name__, self.id, self.obs_mode)

    @property
    def intents(self) -> set[str]:
        """Return all intents associated with this State."""
        # return all intents
        return {intent for mode, intent in self.obs_mode_mapping.items() if self.obs_mode.find(mode) != -1}

    def get_obs_mode_for_intent(self, intent: str) -> list[str]:
        """Return list of obs_mode values associated with given intent."""
        intents = {i.strip('*') for i in intent.split(',') if i is not None}
        return [mode for mode, pipeline_intent in self.obs_mode_mapping.items()
                if pipeline_intent in intents and self.obs_mode.find(mode) != -1]

    def __str__(self) -> str:
        return '{0}(id={1}, intents={2})'.format(self.__class__.__name__, 
                                                 self.id, self.intents)


class StateALMA(State):
    """State representation for ALMA Observatory measurement sets.

    Extends State with ALMA-specific obs_mode to pipeline intent mappings.

    Attributes:
        id: Numerical identifier of this State.
        obs_mode: Unique obs_mode values associated with this State.
    """
    # dictionary to map from STATE table obs_mode to pipeline intent
    obs_mode_mapping = {
        'CALIBRATE_POLARIZATION#ON_SOURCE'   : 'POLARIZATION',
        'CALIBRATE_POLARIZATION.ON_SOURCE'   : 'POLARIZATION',
        'CALIBRATE_POLARIZATION_ON_SOURCE'   : 'POLARIZATION',
        'CALIBRATE_POL_ANGLE#ON_SOURCE'      : 'POLANGLE',
        'CALIBRATE_POL_ANGLE.ON_SOURCE'      : 'POLANGLE',
        'CALIBRATE_POL_ANGLE_ON_SOURCE'      : 'POLANGLE',
        'CALIBRATE_POL_LEAKAGE#ON_SOURCE'    : 'POLLEAKAGE',
        'CALIBRATE_POL_LEAKAGE.ON_SOURCE'    : 'POLLEAKAGE',
        'CALIBRATE_POL_LEAKAGE_ON_SOURCE'    : 'POLLEAKAGE',
        'CALIBRATE_BANDPASS#ON_SOURCE'       : 'BANDPASS',
        'CALIBRATE_BANDPASS.ON_SOURCE'       : 'BANDPASS',
        'CALIBRATE_BANDPASS_ON_SOURCE'       : 'BANDPASS',
        'CALIBRATE_AMPLI#ON_SOURCE'          : 'AMPLITUDE',
        'CALIBRATE_AMPLI.ON_SOURCE'          : 'AMPLITUDE',
        'CALIBRATE_AMPLI_ON_SOURCE'          : 'AMPLITUDE',
        'CALIBRATE_FLUX#ON_SOURCE'           : 'AMPLITUDE',
        'CALIBRATE_FLUX.ON_SOURCE'           : 'AMPLITUDE',
        'CALIBRATE_FLUX_ON_SOURCE'           : 'AMPLITUDE',
        'CALIBRATE_PHASE#ON_SOURCE'          : 'PHASE',
        'CALIBRATE_PHASE.ON_SOURCE'          : 'PHASE',
        'CALIBRATE_PHASE_ON_SOURCE'          : 'PHASE',
        'CALIBRATE_TARGET#ON_SOURCE'         : 'TARGET',
        'CALIBRATE_TARGET.ON_SOURCE'         : 'TARGET',
        'CALIBRATE_TARGET_ON_SOURCE'         : 'TARGET',
        'CALIBRATE_POINTING#ON_SOURCE'       : 'POINTING',
        'CALIBRATE_POINTING.ON_SOURCE'       : 'POINTING',
        'CALIBRATE_POINTING_ON_SOURCE'       : 'POINTING',
        'CALIBRATE_FOCUS#ON_SOURCE'          : 'FOCUS',
        'CALIBRATE_FOCUS.ON_SOURCE'          : 'FOCUS',
        'CALIBRATE_FOCUS_ON_SOURCE'          : 'FOCUS',
        'CALIBRATE_WVR#ON_SOURCE'            : 'WVR',
        'CALIBRATE_WVR.ON_SOURCE'            : 'WVR',
        'CALIBRATE_WVR_ON_SOURCE'            : 'WVR',
        'CALIBRATE_ATMOSPHERE#ON_SOURCE'     : 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE.ON_SOURCE'     : 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE_ON_SOURCE'     : 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE#AMBIENT'       : 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE#HOT'           : 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE#OFF_SOURCE'    : 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE.OFF_SOURCE'    : 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE_OFF_SOURCE'    : 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE#TEST'          : 'ATMOSPHERE',
        'CALIBRATE_SIDEBAND_RATIO#ON_SOURCE' : 'SIDEBAND',
        'CALIBRATE_SIDEBAND_RATIO.ON_SOURCE' : 'SIDEBAND',
        'CALIBRATE_SIDEBAND_RATIO_ON_SOURCE' : 'SIDEBAND',
        'CALIBRATE_SIDEBAND_RATIO#OFF_SOURCE': 'SIDEBAND',
        'CALIBRATE_SIDEBAND_RATIO.OFF_SOURCE': 'SIDEBAND',
        'CALIBRATE_SIDEBAND_RATIO_OFF_SOURCE': 'SIDEBAND',
        'CALIBRATE_DIFFGAIN#REFERENCE'       : 'DIFFGAINREF',
        'CALIBRATE_DIFFGAIN#ON_SOURCE'       : 'DIFFGAINSRC',
        'CALIBRATE_DELAY#ON_SOURCE'          : 'CHECK',
        'CALIBRATE_DELAY.ON_SOURCE'          : 'CHECK',
        'CALIBRATE_DELAY_ON_SOURCE'          : 'CHECK',
        'OBSERVE_CHECK_SOURCE#ON_SOURCE'     : 'CHECK',
        'OBSERVE_CHECK_SOURCE.ON_SOURCE'     : 'CHECK',
        'OBSERVE_CHECK_SOURCE_ON_SOURCE'     : 'CHECK',
        'OBSERVE_TARGET#ON_SOURCE'           : 'TARGET',
        'OBSERVE_TARGET.ON_SOURCE'           : 'TARGET',
        'OBSERVE_TARGET_ON_SOURCE'           : 'TARGET',
        'OBSERVE_TARGET#OFF_SOURCE'          : 'REFERENCE',
        'OBSERVE_TARGET.OFF_SOURCE'          : 'REFERENCE',
        'OBSERVE_TARGET_OFF_SOURCE'          : 'REFERENCE'
    }

    def __init__(self, state_id: int, obs_mode: str) -> None:
        """
        Initialize a StateALMA object.

        Args:
            state_id: Numerical identifier of this State.
            obs_mode: Unique obs_mode values associated with this State.
        """
        super().__init__(state_id, obs_mode)

        if 'CALIBRATE_FLUX' in obs_mode:
            LOG.trace('Translating %s intent to AMPLITUDE for state #%s'
                      '' % (obs_mode, state_id))


class StateALMACycle0(StateALMA):
    """State representation for ALMA Cycle 0 measurement sets.

    Extends StateALMA with workarounds for mislabeled Cycle 0 data, including
    removal of spurious PHASE intents when co-existing with BANDPASS or
    AMPLITUDE intents.

    Attributes:
        id: Numerical identifier of this State.
        obs_mode: Unique obs_mode values associated with this State.
    """
    # Check whether these states co-exist with PHASE
    _PHASE_BYPASS_INTENTS = frozenset(('BANDPASS', 'AMPLITUDE'))

    def __init__(self, state_id: int, obs_mode: str) -> None:
        """
        Initialize a StateALMACycle0 object.

        Args:
            state_id: Numerical identifier of this State.
            obs_mode: Unique obs_mode values associated with this State.
        """
        super().__init__(state_id, obs_mode)

        # For Cycle 0, check whether this state has PHASE and another cal
        # intent. If so, the PHASE obsmode will be removed.

        # First collect the intents using the raw obsmodes recorded in the
        # state table.. 
        intents = self.intents
        # .. and test to see if any of these intents require phase removal
        has_bypass_intent = intents.isdisjoint(StateALMACycle0._PHASE_BYPASS_INTENTS)

        # if so, and PHASE is indeed included as an intent, ..
        if 'PHASE' in intents and not has_bypass_intent:
            LOG.info('Cycle 0 mislabeled data workaround: removing PHASE '
                     'intent for State %s' % self.id)

            # .. find the obs_mode(s) responsible for the addition of the
            # phase intent..
            phase_obs_modes = [k for k, v in self.obs_mode_mapping.items() if v == 'PHASE']
            # and remove them from the obsmodes we should register
            dephased_obs_modes = [m for m in obs_mode.split(',') if m not in phase_obs_modes]

            LOG.trace('Before: %s' % self.__repr__())
            # .. so that in resetting this object's obs_modes to the 
            # corrected value, we remove the registration of the pipeline
            # PHASE intent
            self.obs_mode = ','.join(dephased_obs_modes)
            LOG.trace('After: %s' % self.__repr__())


class StateVLA(State):
    """State representation for VLA Observatory measurement sets.

    Extends State with VLA-specific obs_mode to pipeline intent mappings.

    Attributes:
        id: Numerical identifier of this State.
        obs_mode: Unique obs_mode values associated with this State.
    """
    # dictionary to map from STATE table obs_mode to pipeline intent
    obs_mode_mapping = {
        'CALIBRATE_POLARIZATION#ON_SOURCE'   : 'POLARIZATION',
        'CALIBRATE_POLARIZATION.ON_SOURCE'   : 'POLARIZATION',
        'CALIBRATE_POLARIZATION_ON_SOURCE'   : 'POLARIZATION',
        'CALIBRATE_POLARIZATION#UNSPECIFIED' : 'POLARIZATION',
        'CALIBRATE_POL_ANGLE#ON_SOURCE'      : 'POLANGLE',
        'CALIBRATE_POL_ANGLE.ON_SOURCE'      : 'POLANGLE',
        'CALIBRATE_POL_ANGLE_ON_SOURCE'      : 'POLANGLE',
        'CALIBRATE_POL_ANGLE#UNSPECIFIED'    : 'POLANGLE',
        'CALIBRATE_POL_LEAKAGE#ON_SOURCE'    : 'POLLEAKAGE',
        'CALIBRATE_POL_LEAKAGE.ON_SOURCE'    : 'POLLEAKAGE',
        'CALIBRATE_POL_LEAKAGE_ON_SOURCE'    : 'POLLEAKAGE',
        'CALIBRATE_POL_LEAKAGE#UNSPECIFIED'  : 'POLLEAKAGE',
        'CALIBRATE_BANDPASS#ON_SOURCE'       : 'BANDPASS',
        'CALIBRATE_BANDPASS.ON_SOURCE'       : 'BANDPASS',
        'CALIBRATE_BANDPASS_ON_SOURCE'       : 'BANDPASS',
        'CALIBRATE_AMPLI#ON_SOURCE'          : 'PHASE',  # Was amplitude
        'CALIBRATE_AMPLI.ON_SOURCE'          : 'PHASE',  # Was amplitude
        'CALIBRATE_AMPLI_ON_SOURCE'          : 'PHASE',  # Was amplitude
        'CALIBRATE_FLUX#ON_SOURCE'           : 'AMPLITUDE',
        'CALIBRATE_FLUX.ON_SOURCE'           : 'AMPLITUDE',
        'CALIBRATE_FLUX_ON_SOURCE'           : 'AMPLITUDE',
        'CALIBRATE_PHASE#ON_SOURCE'          : 'PHASE',
        'CALIBRATE_PHASE.ON_SOURCE'          : 'PHASE',
        'CALIBRATE_PHASE_ON_SOURCE'          : 'PHASE',
        'CALIBRATE_TARGET#ON_SOURCE'         : 'TARGET',
        'CALIBRATE_TARGET.ON_SOURCE'         : 'TARGET',
        'CALIBRATE_TARGET_ON_SOURCE'         : 'TARGET',
        'CALIBRATE_POINTING#ON_SOURCE'       : 'POINTING',
        'CALIBRATE_POINTING.ON_SOURCE'       : 'POINTING',
        'CALIBRATE_POINTING_ON_SOURCE'       : 'POINTING',
        'CALIBRATE_FOCUS#ON_SOURCE'          : 'FOCUS',
        'CALIBRATE_FOCUS.ON_SOURCE'          : 'FOCUS',
        'CALIBRATE_FOCUS_ON_SOURCE'          : 'FOCUS',
        'CALIBRATE_WVR#ON_SOURCE'            : 'WVR',
        'CALIBRATE_WVR.ON_SOURCE'            : 'WVR',
        'CALIBRATE_WVR_ON_SOURCE'            : 'WVR',
        'CALIBRATE_ATMOSPHERE#ON_SOURCE'     : 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE.ON_SOURCE'     : 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE_ON_SOURCE'     : 'ATMOSPHERE',
        'CALIBRATE_SIDEBAND_RATIO#ON_SOURCE' : 'SIDEBAND',
        'CALIBRATE_SIDEBAND_RATIO.ON_SOURCE' : 'SIDEBAND',
        'CALIBRATE_SIDEBAND_RATIO_ON_SOURCE' : 'SIDEBAND',
        'OBSERVE_TARGET#ON_SOURCE'           : 'TARGET',
        'OBSERVE_TARGET.ON_SOURCE'           : 'TARGET',
        'OBSERVE_TARGET_ON_SOURCE'           : 'TARGET',
        'OBSERVE_TARGET#UNSPECIFIED'         : 'TARGET',
        'OBSERVE_TARGET#OFF_SOURCE'          : 'REFERENCE',
        'OBSERVE_TARGET.OFF_SOURCE'          : 'REFERENCE',
        'OBSERVE_TARGET_OFF_SOURCE'          : 'REFERENCE',
        'CALIBRATE_BANDPASS#UNSPECIFIED'     : 'BANDPASS',    
        'CALIBRATE_FLUX#UNSPECIFIED'         : 'AMPLITUDE',
        'CALIBRATE_PHASE#UNSPECIFIED'        : 'PHASE',
        'CALIBRATE_AMPLI#UNSPECIFIED'        : 'PHASE',  # Was amplitude
        'UNSPECIFIED#UNSPECIFIED'            : 'UNSPECIFIED#UNSPECIFIED',
        'SYSTEM_CONFIGURATION'               : 'SYSTEM_CONFIGURATION',
        'SYSTEM_CONFIGURATION#UNSPECIFIED'   : 'SYSTEM_CONFIGURATION'
    }

    def __init__(self, state_id: int, obs_mode: str) -> None:
        """
        Initialize a StateVLA object.

        Args:
            state_id: Numerical identifier of this State.
            obs_mode: Unique obs_mode values associated with this State.
        """
        super().__init__(state_id, obs_mode)


class StateAPEX(State):
    """State representation for APEX Observatory measurement sets.

    Extends State with APEX-specific obs_mode to pipeline intent mappings.

    Attributes:
        id: Numerical identifier of this State.
        obs_mode: Unique obs_mode values associated with this State.
    """
    # dictionary to map from STATE table obs_mode to pipeline intent
    obs_mode_mapping = {
        'OBSERVE_TARGET#ON_SOURCE': 'TARGET'
    }

    def __init__(self, state_id: int, obs_mode: str) -> None:
        """
        Initialize a StateAPEX object.

        Args:
            state_id: Numerical identifier of this State.
            obs_mode: Unique obs_mode values associated with this State.
        """
        super().__init__(state_id, obs_mode)


class StateSMT(State):
    """State representation for SMT Observatory measurement sets.

    Extends State with SMT-specific obs_mode to pipeline intent mappings.

    Attributes:
        id: Numerical identifier of this State.
        obs_mode: Unique obs_mode values associated with this State.
    """
    # dictionary to map from STATE table obs_mode to pipeline intent
    obs_mode_mapping = {
        'OBSERVE_TARGET#ON_SOURCE': 'TARGET'
    }

    def __init__(self, state_id: int, obs_mode: str) -> None:
        """
        Initialize a StateSMT object.

        Args:
            state_id: Numerical identifier of this State.
            obs_mode: Unique obs_mode values associated with this State.
        """
        super().__init__(state_id, obs_mode)


class StateNAOJ(State):
    """State representation for Nobeyama or ASTE Observatory measurement sets.

    Extends State with NAOJ-specific obs_mode to pipeline intent mappings.

    Attributes:
        id: Numerical identifier of this State.
        obs_mode: Unique obs_mode values associated with this State.
    """
    # dictionary to map from STATE table obs_mode to pipeline intent
    obs_mode_mapping = {
        'OBSERVE_TARGET#ON_SOURCE'           : 'TARGET',
        'OBSERVE_TARGET#OFF_SOURCE'          : 'REFERENCE',
        'CALIBRATE_ATMOSPHERE#R_SOURCE'      : 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE#SKY_SOURCE'    : 'ATMOSPHERE',
        'CALIBRATE_ATMOSPHERE#ZERO_SOURCE'   : 'ATMOSPHERE'
    }

    def __init__(self, state_id: int, obs_mode: str) -> None:
        """
        Initialize a StateNAOJ object.

        Args:
            state_id: Numerical identifier of this State.
            obs_mode: Unique obs_mode values associated with this State.
        """
        super().__init__(state_id, obs_mode)



class StateFactory:
    """Factory for creating observatory-specific State objects.

    Creates the appropriate State subclass based on the observatory name and
    observation start time.
    """
    def __init__(self, observatory: str, start: datetime.datetime | None = None) -> None:
        """
        Initialize a StateFactory object.

        Args:
            observatory: name of observatory to create State(s) for.
            start: start time of observation / measurement set; this is used
                to distinguish between Cycle 0 and later ALMA datasets.
        """
        if observatory == 'ALMA':
            if start and start < datetime.datetime(2013, 1, 21, tzinfo=datetime.timezone.utc):
                self._constructor = StateALMACycle0
            else:
                self._constructor = StateALMA
        elif observatory == 'VLA' or observatory == 'EVLA':
            self._constructor = StateVLA
        elif observatory == 'APEX':
            self._constructor = StateAPEX
        elif observatory == 'SMT':
            self._constructor = StateSMT
        elif observatory == 'NRO' or observatory == 'ASTE':
            self._constructor = StateNAOJ
        else:
            raise KeyError('%s has no matching State class' % observatory)

    def create_state(self, state_id: int, obs_mode: str) -> State:
        """Return a State object with given ID and obs_mode."""
        return self._constructor(state_id, obs_mode)
