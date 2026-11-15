"""Synthetic lifecycle tests; no transfer, save, load or X4 process is run."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from authority.session import SessionCoordinator


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.session = SessionCoordinator('world-1')

    def finish(self, operation, success=True):
        request = self.session.pending
        self.assertIsNotNone(request)
        self.assertEqual(request.operation, operation)
        self.session.complete(request.world_epoch, request.request_id, success)
        return request

    def ready(self, handle):
        baseline = self.session.baseline_id
        generation = self.session.begin_load(handle, baseline)
        self.session.mark_ready('world-1', handle, generation, baseline)

    def start_running(self):
        handle = self.session.join('player-a')
        self.finish('pause')
        self.finish('save')
        self.ready(handle)
        self.finish('resume')
        self.assertEqual(self.session.state, 'running')
        return handle

    def test_connection_alone_cannot_resume_or_run(self):
        self.finish('pause')
        a = self.session.join('a')
        self.assertEqual(self.session.players, ((a, 'a'),))
        self.assertEqual(self.session.ready_players, ())
        self.finish('save')
        self.assertEqual(self.session.state, 'paused')
        self.ready(a)
        self.assertEqual(self.session.pending.operation, 'resume')
        self.finish('resume')
        self.session.disconnect(a)
        self.finish('pause')
        self.finish('save')
        self.assertEqual(self.session.state, 'paused')
        self.assertIsNone(self.session.pending)

    def test_new_join_pauses_saves_and_waits_for_loading(self):
        a = self.start_running()
        b = self.session.join('b')
        self.assertEqual(self.session.pending.operation, 'pause')
        self.finish('pause')
        save = self.finish('save')
        self.assertEqual(self.session.baseline_id, save.request_id)
        self.assertEqual(self.session.ready_players, ((a, 'player-a'),))
        self.assertEqual(self.session.state, 'paused')
        self.ready(b)
        self.finish('resume')
        self.assertEqual(self.session.state, 'running')
        self.assertIsNone(self.session.baseline_id)

    def test_join_during_save_shares_confirmed_baseline_and_waits_for_all(self):
        self.start_running()
        b = self.session.join('b')
        self.finish('pause')
        c = self.session.join('c')
        with self.assertRaises(ValueError):
            self.session.begin_load(b, self.session.pending.request_id)
        save = self.finish('save')
        self.assertEqual(self.session.baseline_id, save.request_id)
        self.ready(b)
        self.assertEqual(self.session.state, 'paused')
        self.ready(c)
        self.finish('resume')

    def test_pending_join_aborts_uses_existing_save_and_resumes_ready_player(self):
        self.start_running()
        b = self.session.join('b')
        self.finish('pause')
        self.finish('save')
        self.session.disconnect(b)
        self.finish('resume')
        self.assertEqual(self.session.state, 'running')

    def test_last_ready_disconnect_with_pending_join_saves_but_waits(self):
        a = self.start_running()
        b = self.session.join('b')
        self.session.disconnect(a)
        self.finish('pause')
        self.finish('save')
        self.assertEqual(self.session.state, 'paused')
        self.assertEqual(self.session.ready_players, ())
        self.ready(b)
        self.finish('resume')

    def test_disconnect_during_resume_requires_pause_and_save(self):
        a = self.session.join('a')
        self.finish('pause')
        self.finish('save')
        self.ready(a)
        self.session.disconnect(a)
        self.finish('resume')
        self.finish('pause')
        self.finish('save')
        self.assertEqual(self.session.state, 'paused')

    def test_join_during_resume_forces_new_baseline(self):
        a = self.session.join('a')
        self.finish('pause')
        old = self.finish('save').request_id
        self.ready(a)
        b = self.session.join('b')
        self.finish('resume')
        self.finish('pause')
        new = self.finish('save').request_id
        self.assertNotEqual(old, new)
        with self.assertRaises(ValueError):
            self.session.begin_load(b, old)
        self.ready(b)
        self.finish('resume')

    def test_stale_load_callbacks_and_disconnect_handles_are_rejected(self):
        a = self.session.join('a')
        b = self.session.join('b')
        self.finish('pause')
        baseline = self.finish('save').request_id
        first = self.session.begin_load(a, baseline)
        second = self.session.begin_load(a, baseline)
        for epoch, handle, generation, saved in [
            ('world-1', a, first, baseline), ('old-world', a, second, baseline),
            ('world-1', a, second, baseline + 1),
        ]:
            with self.assertRaises(ValueError):
                self.session.mark_ready(epoch, handle, generation, saved)
        self.session.mark_ready('world-1', a, second, baseline)
        self.session.disconnect(b)
        self.finish('resume')
        with self.assertRaises(ValueError):
            self.session.disconnect(b)
        with self.assertRaises(ValueError):
            self.session.mark_ready('world-1', b, second, baseline)

    def test_engine_failure_requires_fence_and_recovery(self):
        a = self.start_running()
        self.session.disconnect(a)
        failed = self.finish('pause', False)
        b = self.session.join('b')
        self.assertEqual(self.session.state, 'faulted')
        self.assertTrue(self.session.save_required)
        with self.assertRaises(ValueError):
            self.session.complete(failed.world_epoch, failed.request_id, True)
        with self.assertRaises(ValueError):
            self.session.retry(engine_fenced=False)
        self.session.retry(engine_fenced=True)
        self.finish('pause')
        self.finish('save', False)
        self.assertTrue(self.session.save_required)
        self.session.retry(engine_fenced=True)
        self.finish('pause')
        self.finish('save')
        self.ready(b)
        self.finish('resume')

    def test_invalid_callbacks_do_not_consume_pending_request(self):
        request = self.session.pending
        for result in (None, 0, 1, 'yes'):
            with self.assertRaises(ValueError):
                self.session.complete(request.world_epoch, request.request_id, result)
            self.assertIs(self.session.pending, request)
        with self.assertRaises(ValueError):
            self.session.retry(engine_fenced=True)
        with self.assertRaises(ValueError):
            self.session.complete('old-world', request.request_id, True)
        self.finish('pause')


if __name__ == '__main__':
    unittest.main()
