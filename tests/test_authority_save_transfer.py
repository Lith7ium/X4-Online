import gzip
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from authority.checkpoints import Checkpoint, CheckpointStore  # noqa: E402
from authority.save_transfer import SaveOffer, SaveOffers, receive  # noqa: E402
from lockstep.launcher import joinfiles  # noqa: E402


class TransferTests(unittest.TestCase):
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
