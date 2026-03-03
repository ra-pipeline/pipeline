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
