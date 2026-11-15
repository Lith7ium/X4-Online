"""Fake-engine/transport-free tests; they never perform native admission."""
from dataclasses import replace
import gzip
import hashlib
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from authority.checkpoints import CheckpointStore
from authority.experimental_load_session import ExperimentalLoadSession
from authority.load_messages import MAX_INTEGER, Receipt, encode_offer, decode_offer, encode_receipt, decode_receipt
from authority.save_transfer import SaveOffers
from authority.world import WorldCoordinator


class FakeEngine:
    def __init__(self, root): self.root = root; self.calls = []
    def pause(self): self.calls.append('pause')
    def save(self):
        self.calls.append('save')
        path = self.root / 'fake-save.gz'
        path.write_bytes(gzip.compress(b'<savegame><fake/></savegame>'))
        return path
    def resume(self): raise AssertionError('a synthetic receipt must not resume X4')


class FakeService:
    def __init__(self): self.offered = {}; self.lock = threading.Lock()
    def offer(self, name, path, expected):
        data = path.read_bytes(); digest = hashlib.sha256(data).hexdigest()
        if digest != expected: raise ValueError('wrong digest')
        with self.lock: self.offered[name] = (path, len(data), digest)
        return len(data), digest
    def withdraw(self, name):
        with self.lock: self.offered.pop(name, None)
    def withdraw_many(self, names):
        with self.lock:
            for name in names: self.offered.pop(name, None)


def receipt(offer):
    return Receipt(**{key: getattr(offer, key) for key in Receipt.__dataclass_fields__})


class ExperimentalSessionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name); (root / 'store').mkdir()
        self.store = CheckpointStore(root / 'store'); self.engine = FakeEngine(root)
        self.service = FakeService(); self.offers = SaveOffers(self.service, self.store)
        self.world = WorldCoordinator('epoch-1', self.engine, self.store, self.offers)
        self.adapter = ExperimentalLoadSession(self.world)
        self.a = self.adapter.attach('alice'); self.b = self.adapter.attach('bob')
        self.world.step(); self.world.step()
        self.assertEqual(self.world.session.state, 'paused')

    def test_roundtrip_consumes_one_fake_receipt_without_admission(self):
        offer = self.adapter.begin('alice')
        self.assertEqual(decode_offer(encode_offer(offer)), offer)
        response = decode_receipt(encode_receipt(receipt(offer)))
        observation = self.adapter.observe_test_receipt('alice', response)
        self.assertFalse(observation.native_load_proven)
        self.assertFalse(observation.authenticated)
        self.assertFalse(observation.admitted)
        self.assertEqual(self.world.session.ready_players, ())
        self.assertEqual(self.world.session.state, 'paused')
        self.assertNotIn(offer.name, self.service.offered)
        with self.assertRaises(ValueError): self.adapter.observe_test_receipt('alice', response)
        self.assertEqual(self.engine.calls, ['pause', 'save'])

    def test_wrong_peer_or_identity_fields_refused(self):
        first = self.adapter.begin('alice'); second = self.adapter.begin('bob')
        with self.assertRaises(ValueError): self.adapter.observe_test_receipt('bob', receipt(first))
        for field, value in [('world_epoch','other'),('connection_handle',self.b),('baseline_id',100),
                             ('load_generation',100),('attempt_id','e'*32),
                             ('checkpoint_id','checkpoint-'+'f'*32),('sha256','f'*64),('size',1)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.adapter.observe_test_receipt('alice', replace(receipt(first), **{field:value}))
        self.assertFalse(self.adapter.observe_test_receipt('bob', receipt(second)).admitted)
        self.assertFalse(self.adapter.observe_test_receipt('alice', receipt(first)).admitted)

    def test_unhashable_peer_values_are_cleanly_rejected(self):
        offer = self.adapter.begin('alice')
        for action in (lambda: self.adapter.begin([]), lambda: self.adapter.disconnect([]),
                       lambda: self.adapter.observe_test_receipt([], receipt(offer))):
            with self.subTest(action=action), self.assertRaises(ValueError): action()
        self.assertFalse(self.adapter.observe_test_receipt('alice', receipt(offer)).admitted)

    def test_reoffer_disconnect_and_external_revocation_fence_old(self):
        old = self.adapter.begin('alice'); new = self.adapter.begin('alice')
        self.assertNotEqual(old.attempt_id, new.attempt_id)
        with self.assertRaises(ValueError): self.adapter.observe_test_receipt('alice', receipt(old))
        self.offers.revoke(self.world._load_offers[self.a].save)
        with self.assertRaises(ValueError): self.adapter.observe_test_receipt('alice', receipt(new))
        next_offer = self.adapter.begin('alice')
        self.adapter.disconnect('alice')
        self.adapter.attach('alice')
        with self.assertRaises(ValueError): self.adapter.observe_test_receipt('alice', receipt(next_offer))

    def test_actual_service_withdrawal_and_external_reoffer_are_rejected(self):
        old = self.adapter.begin('alice'); self.service.withdraw(old.name)
        with self.assertRaises(ValueError): self.adapter.observe_test_receipt('alice', receipt(old))
        new = self.adapter.begin('alice')
        self.world.offer_load(self.a)
        with self.assertRaises(ValueError): self.adapter.observe_test_receipt('alice', receipt(new))

    def test_global_offer_invalidation_fences_all_peers(self):
        alice = self.adapter.begin('alice'); bob = self.adapter.begin('bob')
        self.offers.invalidate()
        for peer, old in (('alice', alice), ('bob', bob)):
            with self.subTest(peer=peer), self.assertRaises(ValueError):
                self.adapter.observe_test_receipt(peer, receipt(old))

    def test_failed_reoffer_faults_without_restoring_prior_attempt(self):
        old = self.adapter.begin('alice')
        with patch.object(self.offers, 'offer', side_effect=RuntimeError('indeterminate publication')):
            with self.assertRaises(RuntimeError): self.adapter.begin('alice')
        self.assertNotIn(old.name, self.service.offered)
        with self.assertRaises(RuntimeError): self.adapter.observe_test_receipt('alice', receipt(old))
        with self.assertRaises(RuntimeError): self.adapter.begin('alice')

    def test_disconnect_that_mutates_then_raises_faults_all_adapter_calls(self):
        self.adapter.begin('alice'); bob = self.adapter.begin('bob')
        original = self.world.disconnect
        def partial(handle):
            original(handle)
            raise RuntimeError('uncertain disconnect')
        with patch.object(self.world, 'disconnect', side_effect=partial):
            with self.assertRaises(RuntimeError): self.adapter.disconnect('alice')
        self.assertIn(bob.name, self.service.offered)  # external cleanup still required
        with self.assertRaises(RuntimeError): self.adapter.observe_test_receipt('bob', receipt(bob))

    def test_receipt_revoke_that_mutates_then_raises_faults_adapter(self):
        offer = self.adapter.begin('alice')
        original = self.offers.revoke
        def partial(save):
            original(save)
            raise RuntimeError('uncertain revoke')
        with patch.object(self.offers, 'revoke', side_effect=partial):
            with self.assertRaises(RuntimeError): self.adapter.observe_test_receipt('alice', receipt(offer))
        self.assertNotIn(offer.name, self.service.offered)
        self.assertEqual(self.world.session.ready_players, ())
        with self.assertRaises(RuntimeError): self.adapter.begin('alice')

    def test_codec_limits_rejected_before_world_mutation(self):
        before = (self.world.session._next_load, dict(self.world._load_offers))
        self.world.session._next_load = MAX_INTEGER + 1
        with self.assertRaises(ValueError): self.adapter.begin('alice')
        self.assertEqual(self.world.session._next_load, MAX_INTEGER + 1)
        self.assertEqual(self.world._load_offers, before[1])
        self.world.session._next_connection = MAX_INTEGER + 1
        with self.assertRaises(RuntimeError): self.adapter.attach('charlie')  # adapter faulted

    def test_connection_limit_rejected_before_join(self):
        self.world.session._next_connection = MAX_INTEGER + 1
        before = self.world.session.players
        with self.assertRaises(ValueError): self.adapter.attach('charlie')
        self.assertEqual(self.world.session.players, before)
        self.assertEqual(self.world.session._next_connection, MAX_INTEGER + 1)

    def test_join_that_mutates_then_fails_faults_adapter(self):
        # join() inserts before _reconcile(), which can itself exhaust IDs.
        self.world.session._save_required = True
        self.world.session._next_request = 1 << 63
        with self.assertRaises(ValueError): self.adapter.attach('charlie')
        self.assertIn('charlie', [peer for _, peer in self.world.session.players])
        with self.assertRaises(RuntimeError): self.adapter.begin('alice')
        with self.assertRaises(RuntimeError): self.adapter.attach('dave')

    def test_nonce_collision_never_reuses_attempt(self):
        with patch('authority.experimental_load_session.secrets.token_hex', return_value='a'*32):
            offer = self.adapter.begin('alice')
            with self.assertRaises(ValueError): self.adapter.begin('alice')
        with self.assertRaises(RuntimeError): self.adapter.observe_test_receipt('alice', receipt(offer))


if __name__ == '__main__': unittest.main()
