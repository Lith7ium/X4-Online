"""Synthetic end-to-end world orchestration; no X4 process or real save load."""
import gzip
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from authority.checkpoints import CheckpointStore
from authority.save_transfer import SaveOffers, receive
from authority.world import WorldCoordinator
from lockstep.launcher import joinfiles


class FakeEngine:
    def __init__(self, directory):
        self.directory = directory
        self.actions = []
        self.paused = False
        self.sequence = 0

    def pause(self):
        self.actions.append('pause')
        self.paused = True

    def save(self):
        if not self.paused:
            raise AssertionError('cannot save a running fake engine')
        self.actions.append('save')
        self.sequence += 1
        path = self.directory / 'finished.xml.gz'
        path.write_bytes(gzip.compress(f'<savegame><tick>{self.sequence}</tick></savegame>'.encode()))
        return path

    def resume(self):
        if not self.paused:
            raise AssertionError('cannot resume an unpaused fake engine')
        self.actions.append('resume')
        self.paused = False


class WorldTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store_path = self.root / 'store'
        self.store_path.mkdir()
        self.store = CheckpointStore(self.store_path)
        self.engine = FakeEngine(self.root)
        self.service = joinfiles.FileService('a' * 32, slots=(1, 2)).start()
        self.addCleanup(self.service.close)
        self.world = WorldCoordinator('world-1', self.engine, self.store, SaveOffers(self.service, self.store))

    def step(self, operation):
        self.assertEqual(self.world.session.pending.operation, operation)
        self.assertEqual(self.world.step().operation, operation)

    def confirm(self, ticket):
        self.world.mark_loaded(ticket.world_epoch, ticket.connection_handle, ticket.baseline_id,
                               ticket.load_generation, ticket.save.checkpoint_id,
                               ticket.save.sha256, trusted_confirmation=True)

    def test_two_players_save_transfer_join_leave_and_store_restart(self):
        a = self.world.join('a')
        self.step('pause')
        self.step('save')
        first = self.world.offer_load(a)
        self.confirm(first)
        self.step('resume')
        self.assertNotIn(first.save.name, self.service.offered)
        b = self.world.join('b')
        self.step('pause')
        self.step('save')
        second = self.world.offer_load(b)
        self.assertNotEqual(first.save.checkpoint_id, second.save.checkpoint_id)
        downloaded = receive('127.0.0.1', self.service.port, 'a' * 32, 2, second.save,
                             self.root / 'client-b', retries=0, timeout=3)
        self.assertEqual(downloaded.read_bytes(), self.store.latest().path.read_bytes())
        self.assertEqual(self.world.session.state, 'paused')
        self.confirm(second)  # trusted fake confirmation, no game was loaded
        self.step('resume')
        self.assertNotIn(second.save.name, self.service.offered)
        self.world.disconnect(a)
        self.assertEqual(self.world.session.state, 'running')
        self.world.disconnect(b)
        self.step('pause')
        self.step('save')
        self.assertEqual(self.world.session.state, 'paused')
        latest = self.store.latest()
        self.assertNotEqual(latest.checkpoint_id, second.save.checkpoint_id)
        self.assertEqual(CheckpointStore(self.store_path).latest(), latest)
        self.assertEqual(self.engine.actions,
                         ['pause', 'save', 'resume', 'pause', 'save', 'resume', 'pause', 'save'])

    def test_forged_stale_or_untrusted_load_confirmation_rejected(self):
        a = self.world.join('a')
        self.step('pause')
        self.step('save')
        old = self.world.offer_load(a)
        ticket = self.world.offer_load(a)
        good = [ticket.world_epoch, ticket.connection_handle, ticket.baseline_id,
                ticket.load_generation, ticket.save.checkpoint_id, ticket.save.sha256]
        mutations = [(0, 'old-world'), (2, ticket.baseline_id + 1),
                     (3, old.load_generation), (4, 'checkpoint-' + 'f' * 32), (5, '0' * 64)]
        for index, value in mutations:
            args = good.copy()
            args[index] = value
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.world.mark_loaded(*args, trusted_confirmation=True)
        with self.assertRaises(ValueError):
            self.world.mark_loaded(*good, trusted_confirmation=False)
        self.assertEqual(self.world.session.state, 'paused')
        self.confirm(ticket)
        self.step('resume')
        with self.assertRaises(ValueError):
            self.confirm(ticket)

    def test_multiple_joiners_get_the_same_confirmed_checkpoint(self):
        a = self.world.join('a')
        self.step('pause')
        self.step('save')
        self.confirm(self.world.offer_load(a))
        self.step('resume')
        b = self.world.join('b')
        self.step('pause')
        c = self.world.join('c')
        self.step('save')
        offer_b = self.world.offer_load(b)
        offer_c = self.world.offer_load(c)
        self.assertEqual((offer_b.baseline_id, offer_b.save.checkpoint_id, offer_b.save.sha256),
                         (offer_c.baseline_id, offer_c.save.checkpoint_id, offer_c.save.sha256))
        self.confirm(offer_b)
        self.assertEqual(self.world.session.state, 'paused')
        self.confirm(offer_c)
        self.step('resume')
        self.assertNotIn(offer_b.save.name, self.service.offered)
        self.assertNotIn(offer_c.save.name, self.service.offered)

    def test_failed_publish_faults_without_acknowledging_save(self):
        self.world.join('a')
        self.step('pause')
        with mock.patch.object(self.store, 'publish', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                self.world.step()
        self.assertEqual(self.world.session.state, 'faulted')
        self.assertIsNone(self.world.session.baseline_id)
        with self.assertRaises(ValueError):
            self.world.offer_load(1)

    def test_native_controller_is_notified_after_checkpoint_publication(self):
        seen=[]
        def published(checkpoint):
            self.assertTrue(self.engine.paused)
            self.assertEqual(self.store.latest(), checkpoint)
            seen.append(checkpoint)
            return True
        self.engine.checkpoint_published=published
        a=self.world.join('a')
        self.step('pause');self.step('save')
        self.assertEqual(len(seen),1)
        self.assertEqual(self.world.offer_load(a).save.checkpoint_id, seen[0].checkpoint_id)

    def test_failed_publication_notification_faults_with_checkpoint_retained(self):
        self.world.join('a');self.step('pause')
        self.engine.checkpoint_published=mock.Mock(side_effect=RuntimeError('confirmation unavailable'))
        with self.assertRaisesRegex(RuntimeError,'confirmation unavailable'):
            self.world.step()
        self.assertEqual(self.world.session.state,'faulted')
        self.assertIsNone(self.world.session.baseline_id)
        self.assertTrue(self.store.latest().path.is_file())
        self.assertTrue(self.engine.paused)
        with self.assertRaises(ValueError):self.world.offer_load(1)

    def test_nonaffirmative_publication_notification_faults(self):
        self.world.join('a');self.step('pause')
        self.engine.checkpoint_published=lambda _checkpoint: None
        with self.assertRaisesRegex(ValueError,'did not confirm'):
            self.world.step()
        self.assertEqual(self.world.session.state,'faulted')
        self.assertIsNone(self.world.session.baseline_id)
        self.assertTrue(self.store.latest().path.is_file())

    def test_adapter_failure_faults_without_executing_next_action(self):
        self.world.join('a')
        with mock.patch.object(self.engine, 'pause', side_effect=RuntimeError('uncertain')):
            with self.assertRaises(RuntimeError):
                self.world.step()
        self.assertEqual(self.world.session.state, 'faulted')
        self.assertIsNone(self.world.step())
        self.assertEqual(self.engine.actions, [])

    def test_join_before_resume_dispatch_cancels_without_running_engine(self):
        a = self.world.join('a')
        self.step('pause')
        self.step('save')
        first = self.world.offer_load(a)
        self.confirm(first)
        old_request = self.world.session.pending
        b = self.world.join('b')
        self.assertIsNone(self.world.step())
        self.assertEqual(self.engine.actions, ['pause', 'save'])
        self.assertEqual(self.world.session.state, 'paused')
        second = self.world.offer_load(b)
        self.assertEqual(second.baseline_id, first.baseline_id)
        with self.assertRaises(ValueError):
            self.world.session.complete(old_request.world_epoch, old_request.request_id, True)
        self.confirm(second)
        self.step('resume')

    def test_last_disconnect_before_resume_dispatch_never_runs_engine(self):
        a = self.world.join('a')
        self.step('pause')
        self.step('save')
        self.confirm(self.world.offer_load(a))
        self.world.disconnect(a)
        self.assertIsNone(self.world.step())
        self.assertEqual(self.engine.actions, ['pause', 'save'])
        self.step('save')
        self.assertEqual(self.world.session.state, 'paused')
        self.assertNotIn('resume', self.engine.actions)


if __name__ == '__main__':
    unittest.main()
