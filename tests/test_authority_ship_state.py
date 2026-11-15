"""Synthetic contract tests for the experimental ship authority registry."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from authority import Position, ShipRegistry, Velocity


class ShipRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = ShipRegistry('session-1')
        self.p0 = Position('frame-a', 0, 1, 2)
        self.p1 = Position('frame-b', 3, 4, 5)
        self.start = self.registry.create('ship-1', 1, self.p0)

    def test_server_client_server_handoff_rejects_late_updates(self):
        r = self.registry
        low = r.update('session-1', 'ship-1', 1, 1, None, 8, self.p1)
        high = r.assign('ship-1', 1, low.authority_epoch, 'client-a')
        self.assertEqual((high.position, high.sequence, high.authority_epoch), (self.p1, 0, 2))
        for args in [
            ('session-1', 'ship-1', 1, 1, None, 9, self.p0),
            ('session-1', 'ship-1', 1, 2, 'client-b', 1, self.p0),
            ('session-1', 'ship-1', 1, 2, None, 1, self.p0),
        ]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                r.update(*args)
        latest = r.update('session-1', 'ship-1', 1, 2, 'client-a', 3, self.p0)
        resumed = r.assign('ship-1', 1, 2, None)
        self.assertEqual((resumed.position, resumed.authority_epoch), (latest.position, 3))
        with self.assertRaises(ValueError):
            r.update('session-1', 'ship-1', 1, 2, 'client-a', 4, self.p1)
        self.assertEqual(r.update('session-1', 'ship-1', 1, 3, None, 1, self.p1).position, self.p1)

    def test_duplicate_reordered_and_wrong_world_rejected_without_mutation(self):
        r = self.registry
        current = r.update('session-1', 'ship-1', 1, 1, None, 10, self.p1)
        for world, sequence in [('session-1', 10), ('session-1', 9), ('old-session', 11)]:
            with self.subTest(world=world, sequence=sequence), self.assertRaises(ValueError):
                r.update(world, 'ship-1', 1, 1, None, sequence, self.p0)
            self.assertEqual(r.snapshot(), (current,))

    def test_generation_tombstones_and_stale_control_operations(self):
        r = self.registry
        current = r.assign('ship-1', 1, 1, 'a')
        with self.assertRaises(ValueError):
            r.remove('ship-1', 1, 1)
        r.remove('ship-1', 1, current.authority_epoch)
        with self.assertRaises(ValueError):
            r.create('ship-1', 1, self.p0)
        replacement = r.create('ship-1', 2, self.p1)
        for operation in (
            lambda: r.assign('ship-1', 1, 1, 'a'),
            lambda: r.remove('ship-1', 1, 1),
            lambda: r.update('session-1', 'ship-1', 1, 1, None, 1, self.p0),
        ):
            with self.assertRaises(ValueError):
                operation()
        self.assertEqual(r.snapshot(), (replacement,))

    def test_sorted_snapshot_is_immutable_and_prior_snapshot_does_not_change(self):
        r = self.registry
        r.create('a', 7, self.p1)
        before = r.snapshot()
        self.assertEqual([s.ship_id for s in before], ['a', 'ship-1'])
        r.update('session-1', 'ship-1', 1, 1, None, 1, self.p1)
        self.assertEqual(before[1].position, self.p0)
        with self.assertRaises(AttributeError):
            before[1].owner = 'client'
        with self.assertRaises(AttributeError):
            before[1].position.x = 10

    def test_limit_counts_removed_ids_and_recreation_does_not_consume_slot(self):
        r = ShipRegistry('s', max_known_ships=1)
        r.create('a', 1, self.p0)
        r.remove('a', 1, 1)
        with self.assertRaises(ValueError):
            r.create('b', 1, self.p0)
        self.assertEqual(r.create('a', 2, self.p0).generation, 2)

    def test_invalid_coordinates_sequences_and_inputs_do_not_mutate(self):
        r = self.registry
        for invalid in [math.nan, math.inf, -math.inf, True, '1', 10 ** 1000]:
            with self.subTest(value=str(invalid)[:20]), self.assertRaises(ValueError):
                Position('frame', invalid, 0, 0)
        for sequence in [0, -1, True, 1.5, 1 << 63]:
            with self.subTest(sequence=sequence), self.assertRaises(ValueError):
                r.update('session-1', 'ship-1', 1, 1, None, sequence, self.p1)
        with self.assertRaises(ValueError):
            r.update('session-1', 'ship-1', 1, 1, None, 1, (1, 2, 3))
        self.assertEqual(r.snapshot(), (self.start,))

    def test_assign_same_owner_is_idempotent(self):
        r = self.registry
        self.assertIs(r.assign('ship-1', 1, 1, None), self.start)
        client = r.assign('ship-1', 1, 1, 'a')
        self.assertIs(r.assign('ship-1', 1, 2, 'a'), client)
        with self.assertRaises(ValueError):
            r.assign('ship-1', 1, 1, 'a')

    def test_velocity_is_complete_finite_and_fenced_with_owner(self):
        r = self.registry
        velocity = Velocity(1, -2, 3.5)
        first = r.update('session-1', 'ship-1', 1, 1, None, 1, self.p0, velocity)
        captured = r.snapshot()
        self.assertEqual(captured[0].velocity, velocity)
        with self.assertRaises(AttributeError):
            captured[0].velocity.x = 5
        for invalid in (math.nan, math.inf, -math.inf, True, '1', 10**1000):
            with self.subTest(value=str(invalid)[:20]), self.assertRaises(ValueError):
                Velocity(invalid, 0, 0)
        with self.assertRaises(ValueError):
            r.update('session-1', 'ship-1', 1, 1, None, 2, self.p1, (1, 2, 3))
        self.assertEqual(r.snapshot(), (first,))
        assigned = r.assign('ship-1', 1, 1, 'client-a')
        self.assertIsNone(assigned.velocity)
        with self.assertRaises(ValueError):
            r.update('session-1', 'ship-1', 1, 1, None, 2, self.p0, Velocity(9, 9, 9))
        self.assertEqual(r.snapshot(), (assigned,))
        current = r.update('session-1', 'ship-1', 1, 2, 'client-a', 1, self.p0, velocity)
        self.assertEqual(current.velocity, velocity)
        self.assertIs(r.assign('ship-1', 1, 2, 'client-a'), current)
        changed_frame = r.update('session-1', 'ship-1', 1, 2, 'client-a', 2, self.p1)
        self.assertIsNone(changed_frame.velocity)
        self.assertEqual(captured[0].velocity, velocity)
        r.update('session-1', 'ship-1', 1, 2, 'client-a', 3, self.p1, velocity)
        self.assertIsNone(r.update('session-1', 'ship-1', 1, 2, 'client-a', 4, self.p1).velocity)


if __name__ == '__main__':
    unittest.main()
