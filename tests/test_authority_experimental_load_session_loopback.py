"""One local TCP byte-transfer integration; no X4, admission, WAN or security claim."""
from dataclasses import fields
import gzip
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from authority.checkpoints import CheckpointStore
from authority.experimental_load_session import ExperimentalLoadSession
from authority.load_messages import Receipt, decode_offer, decode_receipt, encode_offer, encode_receipt
from authority.save_transfer import SaveOffers, receive
from authority.world import WorldCoordinator
from lockstep.launcher import joinfiles


class FakeEngine:
    def __init__(self, root): self.root = root; self.calls = []
    def pause(self): self.calls.append('pause')
    def save(self):
        self.calls.append('save')
        path = self.root / 'fake-save.gz'
        path.write_bytes(gzip.compress(b'<savegame><fixture>loopback</fixture></savegame>'))
        return path
    def resume(self): raise AssertionError('synthetic receipt must not resume the world')


class LoopbackLoadSessionTest(unittest.TestCase):
    def test_loopback_transfer_and_test_receipt_withdraw_the_offer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'store').mkdir()
            store = CheckpointStore(root / 'store'); engine = FakeEngine(root)
            token = 'a' * 32  # disposable local test value
            service = joinfiles.FileService(token, bind='127.0.0.1', port=0, slots=(1,)).start()
            try:
                world = WorldCoordinator('loopback-epoch', engine, store, SaveOffers(service, store))
                adapter = ExperimentalLoadSession(world)
                handle = adapter.attach('test-peer')
                world.step(); world.step()
                offered = adapter.begin('test-peer')
                decoded = decode_offer(encode_offer(offered))
                self.assertEqual(decoded, offered)
                save = world._load_offers[handle].save
                self.assertEqual((decoded.name, decoded.checkpoint_id, decoded.sha256, decoded.size),
                                 (save.name, save.checkpoint_id, save.sha256, save.size))
                downloaded = receive('127.0.0.1', service.port, token, 1, save, root / 'received',
                                     retries=0, timeout=3)
                data = downloaded.read_bytes()
                self.assertEqual(len(data), decoded.size)
                self.assertEqual(hashlib.sha256(data).hexdigest(), decoded.sha256)
                self.assertEqual(data, world._baseline[1].path.read_bytes())
                test_receipt = Receipt(**{field.name: getattr(decoded, field.name) for field in fields(Receipt)})
                observation = adapter.observe_test_receipt('test-peer', decode_receipt(encode_receipt(test_receipt)))
                self.assertFalse(observation.native_load_proven)
                self.assertFalse(observation.authenticated)
                self.assertFalse(observation.admitted)
                self.assertEqual(world.session.ready_players, ())
                self.assertEqual(world.session.state, 'paused')
                self.assertEqual(engine.calls, ['pause', 'save'])
                with service.lock:
                    self.assertNotIn(save.name, service.offered)
                with self.assertRaises(joinfiles.FetchError):
                    receive('127.0.0.1', service.port, token, 1, save, root / 'after-withdrawal',
                            retries=0, timeout=3)
                with self.assertRaises(ValueError):
                    adapter.observe_test_receipt('test-peer', test_receipt)
            finally:
                service.close()
                service.thread.join(timeout=3)
            self.assertFalse(service.thread.is_alive(), 'owned loopback server did not terminate')


if __name__ == '__main__': unittest.main()
