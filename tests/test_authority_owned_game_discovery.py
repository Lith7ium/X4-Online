"""Synchronous discovery batching: fake identity faults and real harmless helpers."""
from contextlib import ExitStack
import copy
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
import authority_download_load_live as download
import authority_owned_game_discovery as subject
import linux_gate_live as live


class Discovery(unittest.TestCase):
    def fixture(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        game = Path(directory)
        processes = [Mock(pid=10, poll=Mock(return_value=None)), Mock(pid=20, poll=Mock(return_value=None))]
        rows = {}
        for process in processes:
            for pid in (process.pid, process.pid+1):
                rows[pid] = dict(pid=pid, start=pid*10, uid=os.geteuid(), group=process.pid,
                                 session=process.pid, exe=(1, 2))
        identities = {process.pid:(process.pid+1, (process.pid+1)*10) for process in processes}
        discover = Mock(side_effect=lambda process, started, game: identities[process.pid])
        self.enterContext(patch.object(download, '_discover_game_identity', discover))
        self.enterContext(patch.object(subject.OwnedGameDiscovery, '_read', side_effect=lambda pid: copy.deepcopy(rows[pid])))
        self.enterContext(patch.object(subject.OwnedGameDiscovery, '_image', return_value=(1, 2)))
        declarations = tuple((process, process.pid*10, game, identities[process.pid]) for process in processes)
        scope = subject.OwnedGameDiscovery(declarations)
        discover.reset_mock()
        return scope, declarations, rows, identities, discover

    def test_nested_checks_discover_only_outer_entry_and_exit_and_restore_default(self):
        scope, declarations, _, _, discover = self.fixture()
        with scope.scope():
            for _ in range(5):
                for process, started, game, identity in declarations:
                    self.assertEqual(download.game_identity(process, started, game), identity)
            with scope.scope():
                self.assertEqual(download.game_identity(*declarations[0][:3]), declarations[0][3])
            self.assertEqual(discover.call_count, 2)
        self.assertEqual(discover.call_count, 4)
        self.assertIsNone(subject._active.get())
        download.game_identity(*declarations[0][:3])
        self.assertEqual(discover.call_count, 5)

    def test_exit_discovers_duplicate_and_preserves_body_error(self):
        for body_failure in (False, True):
            with self.subTest(body_failure=body_failure):
                scope, declarations, _, identities, _ = self.fixture()
                with self.assertRaises(BaseExceptionGroup if body_failure else RuntimeError) as caught:
                    with scope.scope():
                        identities[10] = None
                        if body_failure: raise ValueError('original guard failed')
                if body_failure:
                    self.assertIsInstance(caught.exception.exceptions[0], ValueError)
                    self.assertIsInstance(caught.exception.exceptions[1], RuntimeError)
                self.assertIsNone(subject._active.get())

    def test_targeted_checks_refuse_death_reuse_exec_group_and_session_change(self):
        scope, declarations, rows, _, _ = self.fixture()
        original = copy.deepcopy(rows)
        for pid in (10, 11):
            for field, changed in (('start', 999), ('exe', (9, 9)), ('group', 999), ('session',999), ('uid', -1)):
                with self.subTest(pid=pid, field=field):
                    with self.assertRaises(BaseExceptionGroup) as caught:
                        with scope.scope():
                            rows[pid][field] = changed
                            download.game_identity(*declarations[0][:3])
                    self.assertTrue(all(isinstance(error, RuntimeError) for error in caught.exception.exceptions))
                    rows.clear(); rows.update(copy.deepcopy(original))
                    self.assertIsNone(subject._active.get())
        with self.assertRaises(BaseExceptionGroup):
            with scope.scope():
                declarations[0][0].poll.return_value = 0
                download.game_identity(*declarations[0][:3])
        declarations[0][0].poll.return_value = None

    def test_undeclared_lookup_and_different_nested_scope_fail_closed(self):
        scope, declarations, _, _, _ = self.fixture()
        other = copy.copy(scope)
        with scope.scope():
            with self.assertRaises(RuntimeError): download.game_identity(Mock(pid=30), 300, declarations[0][2])
            with self.assertRaises(RuntimeError): download.game_identity(declarations[0][0], 999, declarations[0][2])
            with self.assertRaises(RuntimeError):
                with other.scope(): pass
        self.assertIsNone(subject._active.get())

    def test_retained_finish_exits_scope_before_client_teardown(self):
        from types import SimpleNamespace
        from authority_recovered_server_client import ActiveClient
        from authority_recovered_loopback_server import finish_source_diagnostic
        scope, declarations, _, _, discover = self.fixture()
        active_clients = []
        participant = object()
        def verify():
            with subject.retained_scope(scope.scope, active, active_clients):
                download.game_identity(*declarations[0][:3])
        def finish():
            self.assertEqual(active_clients, [])
            declarations[1][0].poll.return_value = 0
            verify()
            self.assertIsNone(subject._active.get())
            return {'finished': True}
        active = ActiveClient(participant, {}, finish)
        observation, result = finish_source_diagnostic(active, active_clients, [(None, None, None)],
            verify=verify, probe=lambda *_: {'source_stopped_before_disconnect': True})
        self.assertTrue(result['finished'])
        self.assertEqual(active_clients, [])
        self.assertIsNone(subject._active.get())
        with self.assertRaises(RuntimeError):
            with subject.retained_scope(scope.scope, active, [SimpleNamespace()]): pass

    def test_supervisor_retains_cancellation_and_scope_exit_failure_result(self):
        import json
        from types import SimpleNamespace
        import authority_recovered_loopback_server as supervisor
        scope, _, _, identities, _ = self.fixture()
        try:
            with scope.scope():
                identities[10] = None
                raise KeyboardInterrupt()
        except BaseExceptionGroup as error:
            failure = error
        with tempfile.TemporaryDirectory() as directory, ExitStack() as patches:
            root = Path(directory)
            game = root/'game'; (game/'extensions').mkdir(parents=True)
            auth = root/'auth'; auth.write_bytes(b'private test auth')
            out = root/'output'
            store = SimpleNamespace(directory=root/'source/checkpoints')
            args = SimpleNamespace(out=out, store=store.directory, game=game, display=':1', timeout=30, seed=1)
            patches.enter_context(patch.object(supervisor.snapshot, 'output_path', return_value=out))
            patches.enter_context(patch.object(supervisor, 'CheckpointStore', return_value=store))
            patches.enter_context(patch.object(supervisor.load, 'local_directory', return_value=store.directory))
            patches.enter_context(patch.object(supervisor.live, 'sha', return_value=supervisor.live.EXE_SHA))
            patches.enter_context(patch.object(supervisor.live, 'x4_executables', return_value=[]))
            patches.enter_context(patch.object(supervisor.live, 'steam_identity', return_value={}))
            patches.enter_context(patch.object(supervisor.shutil, 'which', return_value='/test/bwrap'))
            patches.enter_context(patch.dict(os.environ, {'XAUTHORITY':str(auth)}))
            patches.enter_context(patch.object(supervisor, 'diagnostic_process_measure_seconds', side_effect=failure))
            patches.enter_context(patch.object(supervisor, 'cleanup_diagnostics', return_value=True))
            patches.enter_context(patch.object(supervisor, 'stop_owned_processes', return_value=[]))
            result = supervisor.run(args)
            self.assertFalse(result['success'])
            self.assertEqual(result['error_types'], ['KeyboardInterrupt', 'RuntimeError'])
            self.assertEqual(json.loads((out/'result.json').read_text())['error_types'], result['error_types'])
        self.assertIsNone(subject._active.get())

    def test_real_harmless_owned_groups_and_repeated_targeted_reads(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as cleanup:
            game = Path(directory); (game/'X4').symlink_to(Path(sys.executable).resolve())
            declarations = []
            for _ in range(2):
                process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                    start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                def stop(process=process):
                    if process.poll() is None: process.terminate()
                    try: process.wait(timeout=3)
                    except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=3)
                cleanup.callback(stop)
                started = live.start_ticks(process.pid)
                declarations.append((process, started, game, (process.pid, started)))
            scope = subject.OwnedGameDiscovery(tuple(declarations))
            with patch.object(scope, 'discover', wraps=scope.discover) as discover:
                with scope.scope():
                    for _ in range(10):
                        for declaration in declarations:
                            self.assertEqual(download.game_identity(*declaration[:3]), declaration[3])
                self.assertEqual(discover.call_count, 4)
            self.assertIsNone(subject._active.get())
