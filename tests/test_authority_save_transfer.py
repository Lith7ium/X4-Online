import gzip
import base64
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from authority.checkpoints import Checkpoint, CheckpointStore  # noqa: E402
from authority.save_transfer import SaveOffer, SaveOffers, receive  # noqa: E402
from lockstep.launcher import joinfiles  # noqa: E402


class TransferTests(unittest.TestCase):
    def test_interrupted_publication_tracks_and_withdraws_its_own_offer(self):
        for withdrawal_fails in (False, True):
            with self.subTest(withdrawal_fails=withdrawal_fails), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / 'source.xml.gz'
                source.write_bytes(gzip.compress(b'<savegame><world/></savegame>'))
                (root / 'store').mkdir()
                store = CheckpointStore(root / 'store')
                checkpoint = store.publish(source)
                service = joinfiles.FileService('a' * 32, slots=(2,)).start()
                try:
                    other = SaveOffers(service, store).offer(checkpoint)
                    offers = SaveOffers(service, store)
                    actual_offer = service.offer
                    interrupted = KeyboardInterrupt('publication interrupted')
                    published_name = []

                    def publish_then_interrupt(name, path, sha):
                        self.assertIn(name, offers.names)
                        actual_offer(name, path, sha)
                        published_name.append(name)
                        raise interrupted

                    with patch.object(service, 'offer', side_effect=publish_then_interrupt):
                        if withdrawal_fails:
                            with patch.object(service, 'withdraw', side_effect=OSError('withdraw failed')):
                                with self.assertRaises(KeyboardInterrupt) as caught:
                                    offers.offer(checkpoint)
                        else:
                            with self.assertRaises(KeyboardInterrupt) as caught:
                                offers.offer(checkpoint)
                    self.assertIs(caught.exception, interrupted)
                    name, = published_name
                    self.assertNotEqual(name, other.name)
                    self.assertIn(other.name, service.offered)
                    if withdrawal_fails:
                        self.assertIn(name, service.offered)
                        self.assertIn(name, offers.names)
                        self.assertTrue(any('withdrawal failed' in note for note in interrupted.__notes__))
                        offers.invalidate()
                    self.assertNotIn(name, service.offered)
                    self.assertNotIn(name, offers.names)
                    self.assertIn(other.name, service.offered)
                finally:
                    service.close()

    def test_withdraw_interrupts_started_download_and_keeps_other_offers(self):
        for operation in ('revoke', 'invalidate', 'replace'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / 'original.xml.gz'
                source.write_bytes(gzip.compress(b'<savegame>' + base64.b64encode(os.urandom(100_000)) + b'</savegame>'))
                (root / 'store').mkdir()
                store = CheckpointStore(root / 'store')
                checkpoint = store.publish(source)
                service = joinfiles.FileService('a' * 32, slots=(2,))
                first_chunk, release = threading.Event(), threading.Event()
                original_handle = service.handle

                class GatedSocket:
                    def __init__(self, conn):
                        self.conn = conn
                        self.gated = False

                    def __getattr__(self, name):
                        return getattr(self.conn, name)

                    def sendall(self, data):
                        self.conn.sendall(data)
                        if not self.gated and not data.startswith(b'OK|'):
                            self.gated = True
                            first_chunk.set()
                            if not release.wait(5):
                                raise OSError('test gate timed out')

                service.handle = lambda conn, addr: original_handle(GatedSocket(conn), addr)
                service.start()
                try:
                    offers = SaveOffers(service, store)
                    target = offers.offer(checkpoint)
                    other = SaveOffers(service, store).offer(checkpoint)
                    with patch.object(joinfiles, 'CHUNK', 4096), ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(receive, '127.0.0.1', service.port, 'a' * 32, 2,
                                             target, root / 'client', retries=0, timeout=5)
                        try:
                            self.assertTrue(first_chunk.wait(5), 'download never reached its first chunk')
                            if operation == 'revoke':
                                offers.revoke(target)
                            elif operation == 'invalidate':
                                offers.invalidate()
                            else:
                                service.offer(target.name, checkpoint.path, checkpoint.sha256)
                        finally:
                            release.set()
                        with self.assertRaises(joinfiles.FetchError):
                            future.result(timeout=5)
                        self.assertFalse((root / 'client' / 'save.xml.gz').exists())
                        part = root / 'client' / 'save.xml.gz.part'
                        self.assertLess(part.stat().st_size, target.size)
                        if operation != 'replace':
                            with self.assertRaises(joinfiles.FetchError):
                                joinfiles.fetch('127.0.0.1', service.port, 'a' * 32, 2,
                                                target.name, root / 'client' / 'save.xml.gz',
                                                expect_sha=target.sha256, retries=0, timeout=5, offer_wait_s=0)
                            self.assertFalse((root / 'client' / 'save.xml.gz').exists())
                        downloaded = receive('127.0.0.1', service.port, 'a' * 32, 2, other,
                                             root / 'other', retries=0, timeout=5)
                        self.assertEqual(downloaded.read_bytes(), source.read_bytes())
                finally:
                    release.set()
                    service.close()

    def test_checkpoint_over_existing_tcp_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'original.xml.gz'
            source.write_bytes(gzip.compress(b'<savegame><world/></savegame>'))
            (root / 'store').mkdir()
            store = CheckpointStore(root / 'store')
            checkpoint = store.publish(source)
            service = joinfiles.FileService('a' * 32, slots=(2,)).start()
            try:
                offers = SaveOffers(service, store)
                offer = offers.offer(checkpoint)
                self.assertNotEqual(SaveOffers(service, store).offer(checkpoint).name, offer.name)
                forged = Checkpoint(checkpoint.checkpoint_id, source, checkpoint.sha256, checkpoint.size)
                with self.assertRaises(ValueError):
                    offers.offer(forged)
                target = receive('127.0.0.1', service.port, 'a' * 32, 2, offer,
                                 root / 'client', retries=0, timeout=3)
                self.assertEqual(target.read_bytes(), source.read_bytes())
                with self.assertRaises(FileExistsError):
                    receive('127.0.0.1', service.port, 'a' * 32, 2, offer,
                            root / 'client', retries=0, timeout=3)
                wrong_size = SaveOffer(offer.name, offer.sha256, offer.size + 1, offer.checkpoint_id)
                with self.assertRaises(joinfiles.FetchError):
                    receive('127.0.0.1', service.port, 'a' * 32, 2, wrong_size,
                            root / 'bad-size', retries=0, timeout=3)
                self.assertEqual(list((root / 'bad-size').iterdir()), [])
                offers.invalidate()
                with self.assertRaises(joinfiles.FetchError):
                    receive('127.0.0.1', service.port, 'a' * 32, 2, offer,
                            root / 'withdrawn', retries=0, timeout=3)
            finally:
                service.close()

    def test_offer_validation_rejects_bad_fields(self):
        with self.assertRaises(ValueError):
            SaveOffer('../save', 'a' * 64, 1, 'checkpoint-' + 'b' * 32)
        with self.assertRaises(ValueError):
            SaveOffer('j1.xml.gz', 'bad', 1, 'checkpoint-' + 'b' * 32)
        with self.assertRaises(ValueError):
            SaveOffer('j1.xml.gz', 'a' * 64, 0, 'checkpoint-' + 'b' * 32)

    def test_local_host_client_can_download_only_when_slot_one_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'original.xml.gz'
            source.write_bytes(gzip.compress(b'<savegame><world/></savegame>'))
            (root / 'store').mkdir()
            store = CheckpointStore(root / 'store')
            checkpoint = store.publish(source)
            for slots, accepted in (((1, 2), True), ((), False)):
                with self.subTest(slots=slots):
                    service = joinfiles.FileService('a' * 32, slots=slots).start()
                    try:
                        offer = SaveOffers(service, store).offer(checkpoint)
                        target = root / ('explicit' if accepted else 'legacy')
                        if accepted:
                            received = receive('127.0.0.1', service.port, 'a' * 32, 1,
                                               offer, target, retries=0, timeout=3)
                            self.assertEqual(received.read_bytes(), source.read_bytes())
                        else:
                            with self.assertRaises(joinfiles.FetchError):
                                receive('127.0.0.1', service.port, 'a' * 32, 1,
                                        offer, target, retries=0, timeout=3)
                    finally:
                        service.close()


if __name__ == '__main__':
    unittest.main()
