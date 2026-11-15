import gzip
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
from authority.checkpoints import CheckpointStore
from authority.save_transfer import SaveOffers
from authority.world import WorldCoordinator
from lockstep.launcher import joinfiles
import authority_two_x4_live as experiment


class TwoX4SupervisorTest(unittest.TestCase):
    def test_transfer_is_from_current_coordinator_checkpoint_without_admission(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'store').mkdir(); (root/'client/save').mkdir(parents=True)
            original = root/'server-save.gz'
            original.write_bytes(gzip.compress(b'<savegame><world/></savegame>'))
            class Server:
                def pause(self): pass
                def save(self): return original
                def resume(self): raise AssertionError('must stay paused')
            store = CheckpointStore(root/'store')
            service = joinfiles.FileService('a'*32, slots=(1,)).start()
            try:
                world = WorldCoordinator('a'*32, Server(), store, SaveOffers(service, store))
                handle = world.join('client')
                world.step(); world.step()
                ticket, staged = experiment.offer_and_download(world, service, handle, root, root/'client')
                self.assertEqual(staged.read_bytes(), original.read_bytes())
                self.assertEqual(ticket['checkpoint_id'], store.latest().checkpoint_id)
                self.assertEqual(world.session.state, 'paused')
                self.assertEqual(world.session.ready_players, ())
                self.assertEqual(staged.stat().st_mode & 0o777, 0o400)
            finally:
                service.close()

    @unittest.skipUnless(sys.platform == 'linux', 'Linux /proc required')
    def test_save_descriptor_sampling_uses_inode_and_reports_offset(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); save = root/'save'; other = root/'other'
            save.write_bytes(b'abcdefghij'); other.write_bytes(b'abcdefghij')
            with save.open('rb', buffering=0) as stream:
                stream.read(4)
                self.assertIn(4, experiment.observe_open_save(os.getpid(), save))
                self.assertEqual([], experiment.observe_open_save(os.getpid(), other))

if __name__ == '__main__': unittest.main()
