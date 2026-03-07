"""Unit tests for State prototypes (Phase 5)."""

import unittest

from pipeline.domain.state import State, StateALMA, StateALMACycle0, StateVLA


class TestState(unittest.TestCase):
    """Test State implementation."""

    def test_intents(self) -> None:
        state = State(id=1, obs_mode='OBSERVE_TARGET#ON_SOURCE')
        self.assertEqual(state.intents, set())

    def test_alma_intent_mapping(self) -> None:
        state = StateALMA(id=1, obs_mode='CALIBRATE_BANDPASS#ON_SOURCE')
        self.assertIn('BANDPASS', state.intents)

    def test_cycle0_phase_removal(self) -> None:
        state = StateALMACycle0(
            id=1,
            obs_mode='CALIBRATE_PHASE#ON_SOURCE,CALIBRATE_BANDPASS#ON_SOURCE',
        )
        self.assertNotIn('PHASE', state.intents)

    def test_vla_intent_mapping(self) -> None:
        state = StateVLA(id=1, obs_mode='CALIBRATE_PHASE#ON_SOURCE')
        self.assertIn('PHASE', state.intents)

    def test_vla_phase_mapping_from_ampli(self) -> None:
        state = StateVLA(id=1, obs_mode='CALIBRATE_AMPLI#ON_SOURCE')
        self.assertIn('PHASE', state.intents)

    def test_vla_amplitude_mapping_from_flux(self) -> None:
        state = StateVLA(id=1, obs_mode='CALIBRATE_FLUX#ON_SOURCE')
        self.assertIn('AMPLITUDE', state.intents)

    def test_vla_intent_mapping_unspecified_variants(self) -> None:
        state = StateVLA(
            id=1,
            obs_mode='CALIBRATE_BANDPASS#UNSPECIFIED,CALIBRATE_FLUX#UNSPECIFIED,OBSERVE_TARGET#UNSPECIFIED',
        )
        self.assertIn('BANDPASS', state.intents)
        self.assertIn('AMPLITUDE', state.intents)
        self.assertIn('TARGET', state.intents)

    def test_obs_mode_normalization(self) -> None:
        state = StateVLA(id=1, obs_mode=b'CALIBRATE_FLUX.UNSPECIFIED')
        self.assertIn('AMPLITUDE', state.intents)
