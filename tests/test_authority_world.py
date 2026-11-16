"""Synthetic end-to-end world orchestration; no X4 process or real save load."""
import gzip
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import authority.checkpoints as checkpoints
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


class FakeParticipants:
    def __init__(self):
        self.actions = []

    def pause(self, handles):
        self.actions.append(('pause', handles))
        return True

    def resume(self, handles):
        self.actions.append(('resume', handles))
        return True


class WorldTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store_path = self.root / 'store'
        self.store_path.mkdir()
        self.store = CheckpointStore(self.store_path)
        self.engine = FakeEngine(self.root)
        self.participants = FakeParticipants()
        self.service = joinfiles.FileService('a' * 32, slots=(1, 2)).start()
        self.addCleanup(self.service.close)
        self.world = WorldCoordinator('world-1', self.engine, self.store, SaveOffers(self.service, self.store),
                                      participants=self.participants)

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
        self.assertEqual(CheckpointStore(self.store_path).latest_confirmed(), latest)
        self.assertEqual(self.engine.actions,
                         ['pause', 'save', 'resume', 'pause', 'save', 'resume', 'pause', 'save'])
        self.assertEqual(self.participants.actions,
                         [('resume', (a,)), ('pause', (a,)), ('resume', (a, b))])

    def test_existing_client_pause_failure_prevents_save(self):
        a = self.world.join('a')
        self.step('pause'); self.step('save')
        self.confirm(self.world.offer_load(a)); self.step('resume')
        self.world.join('b')
        self.participants.pause = lambda _handles: False
        with self.assertRaisesRegex(RuntimeError, 'client pause was not confirmed'):
            self.world.step()
        self.assertEqual(self.world.session.state, 'faulted')
        self.assertTrue(self.engine.paused)
        self.assertEqual(self.engine.actions, ['pause', 'save', 'resume', 'pause'])

    def test_no_client_controller_does_not_start_server_resume(self):
        a = self.world.join('a')
        self.step('pause'); self.step('save')
        self.confirm(self.world.offer_load(a))
        self.world._participants = None
        with self.assertRaisesRegex(RuntimeError, 'client pause/resume control is unavailable'):
            self.world.step()
        self.assertEqual(self.world.session.state, 'faulted')
        self.assertTrue(self.engine.paused)
        self.assertEqual(self.engine.actions, ['pause', 'save'])

    def test_failed_client_resume_pauses_server_and_faults(self):
        a = self.world.join('a')
        self.step('pause'); self.step('save')
        self.confirm(self.world.offer_load(a))
        self.participants.resume = lambda _handles: False
        with self.assertRaisesRegex(RuntimeError, 'client resume was not confirmed'):
            self.world.step()
        self.assertEqual(self.world.session.state, 'faulted')
        self.assertTrue(self.engine.paused)
        self.assertEqual(self.engine.actions, ['pause', 'save', 'resume', 'pause'])
        self.assertIsNone(self.world.session.baseline_id)

    def test_interrupted_client_resume_pauses_server_and_preserves_interruption(self):
        a = self.world.join('a')
        self.step('pause'); self.step('save')
        self.confirm(self.world.offer_load(a))
        failure = KeyboardInterrupt('participant resume interrupted')
        def interrupt(_handles): raise failure
        self.participants.resume = interrupt
        with self.assertRaises(KeyboardInterrupt) as caught:
            self.world.step()
        self.assertIs(caught.exception, failure)
        self.assertTrue(self.engine.paused)
        self.assertEqual(self.engine.actions, ['pause', 'save', 'resume', 'pause'])
        self.assertEqual(self.world.session.state, 'faulted')
        self.assertIsNone(self.world.session.baseline_id)

    def test_failed_repause_after_interrupted_resume_faults_with_both_errors(self):
        a = self.world.join('a')
        self.step('pause'); self.step('save')
        self.confirm(self.world.offer_load(a))
        interruption = KeyboardInterrupt('participant resume interrupted')
        repause_failure = SystemExit('server pause interrupted')
        def interrupt(_handles): raise interruption
        def fail_pause():
            self.engine.actions.append('pause-attempt')
            raise repause_failure
        self.participants.resume = interrupt
        self.engine.pause = fail_pause
        with self.assertRaisesRegex(RuntimeError, 'server pause is uncertain') as caught:
            self.world.step()
        self.assertIs(caught.exception.__cause__, repause_failure)
        self.assertIs(repause_failure.__context__, interruption)
        self.assertEqual(self.engine.actions, ['pause', 'save', 'resume', 'pause-attempt'])
        self.assertFalse(self.engine.paused)  # pause was attempted, not confirmed
        self.assertEqual(self.world.session.state, 'faulted')
        self.assertIsNone(self.world.session.baseline_id)

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

    def test_replaced_and_disconnected_offers_are_withdrawn_individually(self):
        a, b = self.world.join('a'), self.world.join('b')
        self.step('pause'); self.step('save')
        old = self.world.offer_load(a)
        other = self.world.offer_load(b)
        replacement = self.world.offer_load(a)
        with self.assertRaises(joinfiles.FetchError):
            receive('127.0.0.1', self.service.port, 'a' * 32, 2, old.save,
                    self.root / 'old', retries=0, timeout=3)
        current = receive('127.0.0.1', self.service.port, 'a' * 32, 2, other.save,
                          self.root / 'other', retries=0, timeout=3)
        self.assertEqual(current.read_bytes(), self.store.latest().path.read_bytes())
        self.world.disconnect(a)
        with self.assertRaises(joinfiles.FetchError):
            receive('127.0.0.1', self.service.port, 'a' * 32, 2, replacement.save,
                    self.root / 'disconnected', retries=0, timeout=3)
        current = receive('127.0.0.1', self.service.port, 'a' * 32, 2, other.save,
                          self.root / 'other-again', retries=0, timeout=3)
        self.assertEqual(current.read_bytes(), self.store.latest().path.read_bytes())
        self.confirm(other)
        with self.assertRaises(joinfiles.FetchError):
            receive('127.0.0.1', self.service.port, 'a' * 32, 2, other.save,
                    self.root / 'confirmed', retries=0, timeout=3)

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

    def test_directory_sync_failure_after_current_replacement_faults_world(self):
        self.engine.checkpoint_published = mock.Mock(return_value=True)
        first_player = self.world.join('a')
        self.step('pause')
        self.step('save')
        previous_confirmed = self.store.latest_confirmed()
        old_pointer = (self.store_path / 'CURRENT').read_bytes()
        self.confirm(self.world.offer_load(first_player))
        self.step('resume')
        joining_player = self.world.join('b')
        self.step('pause')
        self.engine.checkpoint_published.reset_mock()

        sync_directory = checkpoints._sync_dir
        observed_failed_syncs = []

        def fail_after_current_replace(path):
            if Path(path) == self.store.directory and (self.store_path / 'CURRENT').read_bytes() != old_pointer:
                observed_failed_syncs.append(True)
                raise OSError('directory sync failed after CURRENT replacement')
            return sync_directory(path)

        with mock.patch.object(checkpoints, '_sync_dir', side_effect=fail_after_current_replace):
            with self.assertRaisesRegex(OSError, 'directory sync failed after CURRENT replacement'):
                self.world.step()

        self.assertEqual(observed_failed_syncs, [True])
        # A replaced pointer is visible in this running process, but its crash
        # durability is unknown after the failed directory sync.
        self.assertNotEqual(self.store.latest().checkpoint_id, previous_confirmed.checkpoint_id)
        self.assertEqual(self.store.latest_confirmed(), previous_confirmed)
        self.engine.checkpoint_published.assert_not_called()
        self.assertTrue(self.engine.paused)
        self.assertEqual(self.world.session.state, 'faulted')
        self.assertIsNone(self.world.session.baseline_id)
        with self.assertRaises(ValueError):
            self.world.offer_load(joining_player)

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
        self.assertEqual(CheckpointStore(self.store_path).latest_confirmed(), seen[0])
        self.assertEqual(self.world.offer_load(a).save.checkpoint_id, seen[0].checkpoint_id)

    def test_failed_controller_confirmation_retains_previous_confirmed_checkpoint(self):
        self.engine.checkpoint_published=lambda _checkpoint: True
        a=self.world.join('a');self.step('pause');self.step('save')
        previous=self.store.latest_confirmed()
        self.confirm(self.world.offer_load(a));self.step('resume')
        self.world.join('b');self.step('pause')
        self.engine.checkpoint_published=mock.Mock(side_effect=RuntimeError('confirmation unavailable'))
        with self.assertRaisesRegex(RuntimeError, 'confirmation unavailable'):
            self.world.step()
        restarted=CheckpointStore(self.store_path)
        self.assertNotEqual(restarted.latest(), previous)
        self.assertEqual(restarted.latest_confirmed(), previous)
        self.assertEqual(self.world.session.state, 'faulted')
        self.assertIsNone(self.world.session.baseline_id)

    def test_confirm_pointer_failure_faults_after_controller_confirmation(self):
        self.engine.checkpoint_published=mock.Mock(return_value=True)
        self.world.join('a');self.step('pause')
        with mock.patch.object(self.store, 'confirm', side_effect=OSError('pointer failure')):
            with self.assertRaisesRegex(OSError, 'pointer failure'):
                self.world.step()
        self.engine.checkpoint_published.assert_called_once()
        self.assertEqual(self.world.session.state, 'faulted')
        self.assertIsNone(self.world.session.baseline_id)
        with self.assertRaises(FileNotFoundError):
            self.store.latest_confirmed()

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
