"""Synthetic byte snapshots; no process, file provenance or admission."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from authority import load_observations as observations
from authority.load_messages import Offer
from authority.trusted_marker_load_session import MarkerBoundOffer


class ClientLoadObservations(unittest.TestCase):
    def setUp(self):
        self.offer = Offer(world_epoch='world', connection_handle=2, baseline_id=3,
                           load_generation=4, checkpoint_id='checkpoint-' + 'a' * 32,
                           sha256='b' * 64, attempt_id='c' * 32, size=123, name='j1.xml.gz')
        self.bound = MarkerBoundOffer(self.offer, 'd' * 32)
        self.ticket = {name: getattr(self.offer, name) for name in observations.TICKET_FIELDS if name != 'slot'}
        self.ticket['slot'] = 'save_009'
        fields = '|'.join(str(self.ticket[name]) for name in observations.TICKET_FIELDS).encode('ascii')
        self.request = observations.LOAD_TAG + b'load_requested|' + fields + b'\n'
        self.marker = b'[X4LAN] AUTH_MARKER load INSPECTED ' + self.bound.marker.encode('ascii') + b'\n'
        self.pause = observations.LOAD_TAG + b'pause_observed|' + fields + b'\n'
        self.snapshot = self.request + b'unrelated\n' + self.marker + self.pause

    def validate(self, data, bound=None, slot='save_009'):
        return observations.validate_bound_offer_receipts(data, self.bound if bound is None else bound, slot=slot)

    def test_exact_order_with_unrelated_lines(self):
        self.assertIsNone(self.validate(self.snapshot))

    def test_wrong_offer_marker_or_slot_refused(self):
        variants = [replace(self.offer, **{name: value}) for name, value in (
            ('world_epoch', 'other'), ('connection_handle', 9), ('baseline_id', 9),
            ('load_generation', 9), ('checkpoint_id', 'checkpoint-' + 'e' * 32),
            ('sha256', 'e' * 64), ('attempt_id', 'e' * 32))]
        for offer in variants:
            with self.subTest(field=offer), self.assertRaises(ValueError):
                self.validate(self.snapshot, MarkerBoundOffer(offer, self.bound.marker))
        with self.assertRaises(ValueError):
            self.validate(self.snapshot, MarkerBoundOffer(self.offer, 'e' * 32))
        with self.assertRaises(ValueError):
            self.validate(self.snapshot, slot='save_008')
        for slot in ('save_9', 'save_00９', '../save_009', 'save_009.xml.gz'):
            with self.subTest(slot=slot), self.assertRaises(ValueError):
                self.validate(self.snapshot, slot=slot)

    def test_incomplete_duplicate_out_of_order_and_error_records(self):
        cases = (b'', self.snapshot[:-1], self.request, self.request + self.pause + self.marker,
                 self.snapshot + self.request, self.request + self.marker + self.marker + self.pause,
                 self.request + b'[X4LAN] AUTH_MARKER load ERROR\n' + self.pause,
                 self.request + self.marker + observations.LOAD_TAG + b'ERROR\n' + self.pause)
        for value in cases:
            with self.subTest(data=value[:40]), self.assertRaises(ValueError):
                self.validate(value)

    def test_oversize_and_line_bound(self):
        with patch.object(observations, 'MAX_LOG', len(self.snapshot) - 1):
            with self.assertRaisesRegex(ValueError, 'oversized'):
                self.validate(self.snapshot)
        with patch.object(observations, 'MAX_LINE', 8):
            with self.assertRaisesRegex(ValueError, 'line too long'):
                self.validate(self.snapshot)

    def test_invalid_bound_offer_and_mutated_frozen_offer(self):
        with self.assertRaises(ValueError):
            self.validate(self.snapshot, object())
        with self.assertRaises(ValueError):
            self.validate(self.snapshot, MarkerBoundOffer(self.offer, 'invalid'))
        object.__setattr__(self.offer, 'connection_handle', True)
        with self.assertRaises(ValueError):
            self.validate(self.snapshot)


if __name__ == '__main__':
    unittest.main()
