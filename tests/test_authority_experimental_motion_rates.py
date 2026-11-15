"""Pure timestamped rate integration; no X4, transport or game writes."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from authority.experimental_motion_rates import ExperimentalMotionRates
from authority.ship_state import Position, ShipRegistry, Velocity


class MotionRatesTests(unittest.TestCase):
    def setUp(self):
        self.registry = ShipRegistry('world')
        self.registry.create('one', 1, Position('sector-a', 0, 0, 0))
        self.rates = ExperimentalMotionRates(self.registry, max_tracks=2)

    def update(self, sequence, time, x, *, frame='sector-a', generation=1, authority=1, owner=None):
        return self.rates.update('world', 'one', generation, authority, owner, sequence,
                                 Position(frame, x, 0, 0), time)

    def test_estimates_source_seconds_and_clears_unknown(self):
        self.assertIsNone(self.update(1, 1., 0).velocity)
        self.assertIsNone(self.update(2, 1.01, 1).velocity)
        self.assertAlmostEqual(self.update(3, 1.1, 10).velocity.x, 100)
        # A missing fresh estimate clears the registry's last rate.
        self.assertIsNone(self.update(4, 1.101, 10).velocity)
        stationary = self.update(5, 1.2, 10)
        self.assertEqual(stationary.velocity, Velocity(0, 0, 0))
        self.assertEqual(self.registry.snapshot()[0], stationary)

    def test_frame_gap_and_overlimit_start_new_reference(self):
        self.update(1, 0, 0); self.assertEqual(self.update(2, .1, 10).velocity.x, 100)
        self.assertIsNone(self.update(3, .2, 1000, frame='sector-b').velocity)
        self.assertAlmostEqual(self.update(4, .3, 1010, frame='sector-b').velocity.x, 100)
        self.assertIsNone(self.update(5, 3, 1020, frame='sector-b').velocity)
        self.assertIsNone(self.update(6, 3.1, 100000, frame='sector-b').velocity)
        self.assertAlmostEqual(self.update(7, 3.2, 100010, frame='sector-b').velocity.x, 100)

    def test_transfer_recreation_and_regressed_clock_fence_rates(self):
        self.update(1, 10, 0); self.update(2, 10.1, 10)
        before = self.registry.snapshot()
        with self.assertRaises(ValueError): self.update(3, 10.05, 999)
        with self.assertRaises(ValueError): self.update(2, 10.2, 999)
        self.assertEqual(self.registry.snapshot(), before)
        self.assertAlmostEqual(self.update(3, 10.2, 20).velocity.x, 100)
        transfer = self.registry.assign('one', 1, 1, 'pilot')
        self.assertEqual(transfer.authority_epoch, 2)
        self.assertIsNone(self.update(1, .1, 21, authority=2, owner='pilot').velocity)
        self.assertAlmostEqual(self.update(2, .2, 31, authority=2, owner='pilot').velocity.x, 100)
        self.registry.remove('one', 1, 2)
        self.registry.create('one', 2, Position('sector-a', 1, 0, 0))
        self.assertIsNone(self.update(1, .01, 2, generation=2).velocity)

    def test_rejected_registry_update_does_not_advance_reference(self):
        self.update(1, 1, 0)
        for kwargs in ({'owner':'intruder'}, {'authority':2}, {'generation':2}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): self.update(2, 1.1, 900, **kwargs)
        with self.assertRaises(ValueError):
            self.rates.update('other', 'one', 1, 1, None, 2, Position('sector-a', 900, 0, 0), 1.1)
        self.assertAlmostEqual(self.update(2, 1.2, 20).velocity.x, 100)

    def test_invalid_clocks_capacity_and_forget_have_no_registry_side_effect(self):
        self.update(1, 1, 0)
        for val in (None, True, -1, math.inf, math.nan, 1e13, '1'):
            with self.subTest(val=val), self.assertRaises(ValueError): self.update(2, val, 1)
        self.registry.create('two', 1, Position('sector-a', 0, 0, 0))
        self.registry.create('three', 1, Position('sector-a', 0, 0, 0))
        self.rates.update('world', 'two', 1, 1, None, 1, Position('sector-a', 1, 0, 0), 1)
        before = self.registry.snapshot()
        with self.assertRaises(ValueError):
            self.rates.update('world', 'three', 1, 1, None, 1, Position('sector-a', 2, 0, 0), 1)
        self.assertEqual(self.registry.snapshot(), before)
        self.assertTrue(self.rates.forget('one'))
        self.assertIsNone(self.rates.update('world', 'three', 1, 1, None, 1, Position('sector-a', 2, 0, 0), 1).velocity)
        self.assertFalse(self.rates.forget('one'))

    def test_external_registry_update_fences_derived_rate(self):
        self.update(1, 1, 0)
        external = self.registry.update('world', 'one', 1, 1, None, 2,
                                        Position('sector-b', 500, 0, 0))
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.update(3, 1.2, 20)
        self.assertIs(self.registry.snapshot()[0], external)
        self.assertTrue(self.rates.forget('one'))
        self.assertIsNone(self.update(3, 1.2, 20).velocity)

    def test_interleaved_ships_have_independent_reference_clocks(self):
        self.registry.create('two', 1, Position('sector-b', 0, 0, 0))
        self.update(1, 1, 0)
        self.rates.update('world', 'two', 1, 1, None, 1, Position('sector-b', 0, 0, 0), 100)
        one = self.update(2, 1.1, 10)
        two = self.rates.update('world', 'two', 1, 1, None, 2, Position('sector-b', 20, 0, 0), 100.1)
        self.assertAlmostEqual(one.velocity.x, 100)
        self.assertAlmostEqual(two.velocity.x, 200)

    def test_overflowing_difference_is_unknown_not_reused(self):
        self.update(1, 0, 1e308)
        self.assertIsNone(self.update(2, .1, -1e308).velocity)


if __name__ == '__main__': unittest.main()
