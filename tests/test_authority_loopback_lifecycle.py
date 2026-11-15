"""Real loopback TCP with fake readiness and fake simulation; never launches X4.

The direct trusted confirmations below are an explicit test assumption. They do
not follow from TCP transfer, a synthetic receipt, or a real client load.
"""
import gzip
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from authority.checkpoints import CheckpointStore
from authority.experimental_load_session import ExperimentalLoadSession
from authority.load_messages import Receipt, decode_offer, encode_offer, decode_receipt, encode_receipt
from authority.save_transfer import SaveOffer, SaveOffers, receive
from authority.world import WorldCoordinator
from lockstep.launcher import joinfiles
if __package__:
    from .test_authority_world import FakeEngine, FakeParticipants
else:
    from test_authority_world import FakeEngine, FakeParticipants


class ProgressFakeEngine(FakeEngine):
    """Explicitly simulated progress; the saved XML is not an X4 save."""
    def __init__(self, directory):
        super().__init__(directory)
        self.tick = 0

    def advance(self, ticks):
        if self.paused:
            raise AssertionError('fake progress requires running fake engine')
        self.tick += ticks

    def save(self):
        if not self.paused:
            raise AssertionError('cannot save a running fake engine')
        self.actions.append('save')
        self.sequence += 1
        path = self.directory / 'fake-world.xml.gz'
        path.write_bytes(gzip.compress(f'<savegame><tick>{self.tick}</tick></savegame>'.encode()))
        return path


class LoopbackLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store_path = self.root / 'store'; self.store_path.mkdir()
        self.store = CheckpointStore(self.store_path)
        self.engine = ProgressFakeEngine(self.root)
        self.participants = FakeParticipants()
        self.token = 'a' * 32  # Local synthetic fixture; never an Internet credential.
        self.service = joinfiles.FileService(self.token, bind='127.0.0.1', slots=(1, 2)).start()
        self.addCleanup(self.close_service)
        self.offers = SaveOffers(self.service, self.store)
        self.world = WorldCoordinator('fake-loopback-world', self.engine, self.store, self.offers,
                                      participants=self.participants)
        self.adapter = ExperimentalLoadSession(self.world)

    def close_service(self):
        try:
            self.offers.invalidate()
        finally:
            self.service.close()
            self.service.thread.join(timeout=2)
        self.assertFalse(self.service.thread.is_alive())

    def step(self, expected):
        self.assertEqual(self.world.session.pending.operation, expected)
        self.assertEqual(self.world.step().operation, expected)

    @staticmethod
    def receipt(offer):
        return decode_receipt(encode_receipt(Receipt(**{f: getattr(offer, f) for f in Receipt.__dataclass_fields__})))

    @staticmethod
    def save_offer(offer):
        return SaveOffer(offer.name, offer.sha256, offer.size, offer.checkpoint_id)

    def offer_and_receive(self, peer, directory, slot=2):
        # The service authorizes the shared test token/slot, not this peer label.
        offer = decode_offer(encode_offer(self.adapter.begin(peer)))
        path = receive('127.0.0.1', self.service.port, self.token, slot,
                       self.save_offer(offer), self.root / directory, retries=0, timeout=3)
        payload = path.read_bytes()
        self.assertEqual(len(payload), offer.size)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), offer.sha256)
        self.assertEqual(payload, self.store.get(offer.checkpoint_id).path.read_bytes())
        return offer, payload

    def pretend_loaded(self, offer):
        """Test-only assertion: NO X4 process or actual load is observed."""
        self.world.mark_loaded(offer.world_epoch, offer.connection_handle, offer.baseline_id,
                               offer.load_generation, offer.checkpoint_id, offer.sha256,
                               trusted_confirmation=True)

    def test_three_fake_players_final_disconnect_and_later_download(self):
        a = self.adapter.attach('alice')
        self.step('pause'); self.step('save')
        old = self.adapter.begin('alice')
        first, _ = self.offer_and_receive('alice', 'alice-first', slot=1)
        with self.assertRaises(ValueError):
            self.adapter.observe_test_receipt('alice', self.receipt(old))
        with self.assertRaises(joinfiles.FetchError):
            receive('127.0.0.1', self.service.port, self.token, 1, self.save_offer(old),
                    self.root / 'withdrawn-old', retries=0, timeout=3)
        self.pretend_loaded(first)
        with self.assertRaises(ValueError):
            self.adapter.observe_test_receipt('alice', self.receipt(first))
        self.step('resume'); self.engine.advance(2)

        b = self.adapter.attach('bob'); c = self.adapter.attach('carol')
        self.step('pause'); self.step('save')
        bob, bob_bytes = self.offer_and_receive('bob', 'bob')
        carol, carol_bytes = self.offer_and_receive('carol', 'carol')
        self.assertEqual(bob_bytes, carol_bytes)
        self.assertEqual(gzip.decompress(bob_bytes), b'<savegame><tick>2</tick></savegame>')
        self.assertEqual((bob.checkpoint_id, bob.sha256), (carol.checkpoint_id, carol.sha256))
        with self.assertRaises(ValueError):
            self.adapter.observe_test_receipt('bob', self.receipt(carol))
        self.pretend_loaded(bob)
        self.assertEqual(self.world.session.state, 'paused')
        self.assertIsNone(self.world.session.pending)
        self.pretend_loaded(carol); self.step('resume')
        self.assertEqual({h for h, _ in self.world.session.ready_players}, {a, b, c})

        self.adapter.disconnect('alice'); self.adapter.disconnect('carol')
        self.assertEqual(self.world.session.state, 'running')
        self.assertEqual(self.world.session.ready_players, ((b, 'bob'),))
        self.assertIsNone(self.world.session.pending)
        self.engine.advance(7)
        self.adapter.disconnect('bob')
        self.step('pause'); self.step('save')
        self.assertEqual(self.world.session.state, 'paused')
        self.assertEqual(self.world.session.players, ())
        saved = CheckpointStore(self.store_path).latest_confirmed()
        self.assertNotEqual(saved.checkpoint_id, bob.checkpoint_id)
        self.assertEqual(gzip.decompress(saved.path.read_bytes()), b'<savegame><tick>9</tick></savegame>')
        self.assertEqual(self.engine.actions, ['pause', 'save', 'resume', 'pause', 'save',
                                               'resume', 'pause', 'save'])
        self.assertTrue(self.engine.paused)

        # Same in-memory fake engine, later connection: not process restart or native load.
        a2 = self.adapter.attach('alice')
        self.assertNotEqual(a2, a)
        with self.assertRaises(ValueError):
            self.adapter.observe_test_receipt('alice', self.receipt(first))
        later, later_bytes = self.offer_and_receive('alice', 'alice-later', slot=1)
        self.assertEqual((later.checkpoint_id, later.sha256, later.size),
                         (saved.checkpoint_id, saved.sha256, saved.size))
        self.assertEqual(gzip.decompress(later_bytes), b'<savegame><tick>9</tick></savegame>')
        self.pretend_loaded(later); self.step('resume')
        self.assertEqual(self.engine.tick, 9)
        self.assertFalse(self.engine.paused)
        self.assertEqual(self.participants.actions, [('resume', (a,)), ('pause', (a,)),
                                                     ('resume', (a, b, c)), ('resume', (a2,))])
        self.assertEqual(self.service.offered, {})

    def test_synthetic_receipt_never_admits_and_last_unready_disconnect_does_not_resave(self):
        self.adapter.attach('alice')
        self.step('pause'); self.step('save')
        checkpoint = self.store.latest_confirmed()
        offer, _ = self.offer_and_receive('alice', 'unready', slot=1)
        observed = self.adapter.observe_test_receipt('alice', self.receipt(offer))
        self.assertFalse(observed.native_load_proven)
        self.assertFalse(observed.authenticated)
        self.assertFalse(observed.admitted)
        self.assertEqual(self.world.session.ready_players, ())
        self.assertEqual(self.world.session.state, 'paused')
        self.assertIsNone(self.world.session.pending)
        self.adapter.disconnect('alice')
        self.assertEqual(self.world.session.state, 'paused')
        self.assertIsNone(self.world.session.pending)
        self.assertEqual(self.engine.actions, ['pause', 'save'])
        self.assertEqual(self.store.latest_confirmed(), checkpoint)
        self.assertEqual(self.service.offered, {})


if __name__ == '__main__': unittest.main()
