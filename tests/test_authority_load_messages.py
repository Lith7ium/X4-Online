"""Synthetic codec contract; no network, filesystem transfer, or X4 execution."""
import dataclasses
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from authority.load_messages import (
    Offer, Receipt, decode_offer, decode_receipt, encode_offer, encode_receipt,
    matches_offer, from_load_offer,
)
from authority.save_transfer import SaveOffer
from authority.session import SessionCoordinator
from authority.ship_state import _integer
from authority.world import LoadOffer


BASE = dict(
    world_epoch='world_1-A', connection_handle=1, baseline_id=2,
    load_generation=3, attempt_id='a' * 32, checkpoint_id='checkpoint-' + 'b' * 32,
    sha256='c' * 64, size=4096,
)


class LoadMessageTests(unittest.TestCase):
    def setUp(self):
        self.offer = Offer(**BASE, name='j1.xml.gz')
        self.receipt = Receipt(**BASE)

    def test_round_trip_and_receipt_matching(self):
        offer_wire = encode_offer(self.offer)
        receipt_wire = encode_receipt(self.receipt)
        self.assertIsInstance(offer_wire, bytes)
        self.assertIsInstance(receipt_wire, bytes)
        self.assertEqual(decode_offer(offer_wire), self.offer)
        second = dataclasses.replace(self.offer, name='j2.xml.gz')
        self.assertEqual(decode_offer(encode_offer(second)), second)
        self.assertEqual(decode_receipt(receipt_wire), self.receipt)
        self.assertTrue(matches_offer(self.receipt, self.offer))
        self.assertEqual(json.loads(offer_wire)['version'], 1)
        self.assertEqual(json.loads(offer_wire)['kind'], 'offer')
        self.assertEqual(json.loads(receipt_wire)['kind'], 'receipt')
        with self.assertRaises(dataclasses.FrozenInstanceError):
            self.offer.size = 5

    def test_from_real_coordinator_offer(self):
        save = SaveOffer(name='j1.xml.gz', sha256=BASE['sha256'], size=BASE['size'],
                         checkpoint_id=BASE['checkpoint_id'])
        original = LoadOffer(world_epoch=BASE['world_epoch'], connection_handle=BASE['connection_handle'],
                             baseline_id=BASE['baseline_id'], load_generation=BASE['load_generation'],
                             save=save)
        self.assertEqual(from_load_offer(original, BASE['attempt_id']), self.offer)
        self.assertEqual(decode_offer(encode_offer(from_load_offer(original, BASE['attempt_id']))), self.offer)
        for bad in (None, save, self.offer, dataclasses.replace(original, save=object())):
            with self.subTest(bad=type(bad).__name__), self.assertRaises(ValueError):
                from_load_offer(bad, BASE['attempt_id'])
        with self.assertRaises(ValueError):
            from_load_offer(original, 'invalid-attempt')

    def test_each_receipt_field_must_match(self):
        changes = {
            'world_epoch': 'another_world', 'connection_handle': 4,
            'baseline_id': 4, 'load_generation': 2, 'attempt_id': 'd' * 32,
            'checkpoint_id': 'checkpoint-' + 'd' * 32, 'sha256': 'd' * 64,
            'size': 4097,
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                self.assertFalse(matches_offer(dataclasses.replace(self.receipt, **{field: value}), self.offer))

    def test_comparison_does_not_establish_freshness_or_bind_filename(self):
        old_offer = self.offer
        newer_offer = dataclasses.replace(old_offer, load_generation=old_offer.load_generation + 1,
                                           attempt_id='d' * 32)
        self.assertTrue(matches_offer(self.receipt, old_offer))
        self.assertFalse(matches_offer(self.receipt, newer_offer))
        # The receipt has no filename: callers must enforce locator ownership.
        self.assertTrue(matches_offer(self.receipt, dataclasses.replace(old_offer, name='j2.xml.gz')))

    def test_decoder_accepts_distinct_json_bytes_for_equal_values(self):
        canonical = encode_offer(self.offer)
        reordered = json.dumps(json.loads(canonical), indent=2, sort_keys=False).encode('utf-8')
        self.assertNotEqual(canonical, reordered)
        self.assertEqual(decode_offer(canonical), decode_offer(reordered))

    def test_coordinator_offer_may_exceed_codec_contract(self):
        save = SaveOffer(name='j1.xml.gz', sha256=BASE['sha256'], size=BASE['size'],
                         checkpoint_id=BASE['checkpoint_id'])
        SessionCoordinator('valid to coordinator')
        self.assertEqual(_integer(2**53, 'connection_handle', 1), 2**53)
        for changes in ({'world_epoch': 'valid to coordinator'}, {'connection_handle': 2**53}):
            args = {key: BASE[key] for key in ('world_epoch', 'connection_handle', 'baseline_id', 'load_generation')}
            args.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                from_load_offer(LoadOffer(**args, save=save), BASE['attempt_id'])

    def test_round_trip_boundaries(self):
        for size in (1, 512 * 1024 * 1024):
            obj = dataclasses.replace(self.offer, size=size, world_epoch='x' * 64,
                                      connection_handle=2**53 - 1, baseline_id=2**53 - 1,
                                      load_generation=2**53 - 1)
            with self.subTest(size=size):
                self.assertEqual(decode_offer(encode_offer(obj)), obj)

    def test_missing_extra_wrong_kind_or_version(self):
        for original, decoder in ((json.loads(encode_offer(self.offer)), decode_offer),
                                  (json.loads(encode_receipt(self.receipt)), decode_receipt)):
            cases = []
            for field in original:
                msg = dict(original); del msg[field]; cases.append(msg)
            cases += [dict(original, extra=1), dict(original, version=2),
                      dict(original, version=True), dict(original, kind='other')]
            for msg in cases:
                with self.subTest(message=msg):
                    with self.assertRaises(ValueError):
                        decoder(json.dumps(msg).encode())
        with self.assertRaises(ValueError):
            decode_offer(encode_receipt(self.receipt))
        with self.assertRaises(ValueError):
            decode_receipt(encode_offer(self.offer))

    def test_invalid_fields_are_rejected_by_codec(self):
        invalid = {
            'world_epoch': ['', 'x' * 65, 'bad space', 'ümlaut'],
            'connection_handle': [0, -1, True, 1.5, 2**53],
            'baseline_id': [0, False, 2**53],
            'load_generation': [0, True, 2**53],
            'attempt_id': ['A' * 32, 'a' * 31, 'g' * 32],
            'checkpoint_id': ['checkpoint-' + 'A' * 32, 'x' * 32, 'checkpoint-' + 'a' * 31],
            'sha256': ['A' * 64, 'a' * 63, 'g' * 64],
            'size': [0, True, -1, 512 * 1024 * 1024 + 1, 1.5],
            'name': ['', '../j1.xml.gz', 'j0.xml.gz', '.x4join', 'J1.xml.gz'],
        }
        for field, values in invalid.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    msg = json.loads(encode_offer(self.offer)); msg[field] = value
                    with self.assertRaises(ValueError):
                        decode_offer(json.dumps(msg).encode())
                    with self.assertRaises(ValueError):
                        encode_offer(dataclasses.replace(self.offer, **{field: value}))

    def test_duplicate_nonfinite_malformed_and_oversized_bytes(self):
        valid = encode_offer(self.offer)
        duplicate = valid[:-1] + b',"kind":"offer"}'
        for wire in (duplicate, b'{"version":NaN}', b'{"version":Infinity}',
                     b'{"version":-Infinity}', b'not json', b'\xff', b' ' * 4097):
            with self.subTest(wire=wire[:40]):
                with self.assertRaises(ValueError):
                    decode_offer(wire)
        with self.assertRaises(ValueError):
            decode_offer('not bytes')
        # Valid envelope with a nonfinite value must not be accepted as a number.
        for token in ('NaN', 'Infinity', '-Infinity'):
            wire = json.dumps(dict(json.loads(valid), size=0)).replace('\"size\": 0', '\"size\": ' + token).encode()
            with self.subTest(token=token), self.assertRaises(ValueError):
                decode_offer(wire)

    def test_wrong_object_types_rejected(self):
        for func, args in ((encode_offer, (self.receipt,)),
                           (encode_receipt, (self.offer,)),
                           (matches_offer, (self.offer, self.offer)),
                           (matches_offer, (self.receipt, self.receipt))):
            with self.subTest(func=func.__name__), self.assertRaises(ValueError):
                func(*args)

    def test_constructor_validates_all_fields(self):
        for field, value in (('world_epoch', ''), ('connection_handle', True),
                             ('baseline_id', 0), ('load_generation', 2**53),
                             ('attempt_id', 'x' * 32), ('checkpoint_id', 'bad'),
                             ('sha256', 'A' * 64), ('size', 0)):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    dataclasses.replace(self.offer, **{field: value})
                with self.assertRaises(ValueError):
                    dataclasses.replace(self.receipt, **{field: value})
        with self.assertRaises(ValueError):
            dataclasses.replace(self.offer, name='../j1.xml.gz')


if __name__ == '__main__':
    unittest.main()
