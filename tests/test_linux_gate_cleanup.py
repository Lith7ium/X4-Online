"""Offline ownership and cleanup checks; no game process is launched."""
import importlib.util
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

DEV = Path(__file__).resolve().parents[1] / 'tools/dev'
sys.path.insert(0, str(DEV))
spec = importlib.util.spec_from_file_location('linux_gate_live_cleanup_test', DEV / 'linux_gate_live.py')
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


@unittest.skipUnless(sys.platform == 'linux', 'Linux-only process isolation')
class CleanupTests(unittest.TestCase):
    def forked_game(self, root, different_home=False, ignore_term=False):
        # Adopt test orphans so the actual fork regression leaves no zombies.
        libc = ctypes.CDLL(None)
        previous = ctypes.c_int()
        self.assertEqual(libc.prctl(37, ctypes.byref(previous), 0, 0, 0), 0)
        self.assertEqual(libc.prctl(36, 1, 0, 0, 0), 0)
        self.addCleanup(lambda: libc.prctl(36, previous.value, 0, 0, 0))
        script = r'''
import json, os, pathlib, sys, time
children = []
for index in range(2 if sys.argv[2] == 'two' else 1):
    pid = os.fork()
    if not pid:
        env = dict(os.environ)
        if index: env['HOME'] += '/other'
        code = "import pathlib,signal,sys,time; "
        if sys.argv[3] == 'ignore': code += "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        code += "pathlib.Path(sys.argv[1]).touch(); time.sleep(60)"
        os.execve(sys.executable, [sys.executable, '-c', code, sys.argv[1] + '/ready' + str(index)], env)
    children.append(pid)
print(json.dumps(children), flush=True)
sys.stdin.readline()
'''
        process = subprocess.Popen([sys.executable, '-u', '-c', script, str(root),
                                    'two' if different_home else 'one', 'ignore' if ignore_term else 'normal'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=dict(os.environ, HOME=str(root / 'home')), start_new_session=True, text=True)
        children = json.loads(process.stdout.readline())
        launch = live.record_owned_game(process, live.start_ticks(process.pid), root / 'home',
                                        Path(sys.executable), os.getuid())
        fds = [os.pidfd_open(pid) for pid in children]
        def finish():
            process.stdin.close() if not process.stdin.closed else None
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
            for pid, fd in zip(children, fds):
                try:
                    live.signal.pidfd_send_signal(fd, live.signal.SIGKILL)
                except ProcessLookupError:
                    pass
                finally:
                    os.close(fd)
                try:
                    os.waitpid(pid, 0)
                except ChildProcessError:
                    pass
            process.stdout.close()
            process.stderr.close()
        self.addCleanup(finish)
        deadline = time.monotonic() + 3
        for index in range(len(children)):
            while not (root / f'ready{index}').exists():
                self.assertLess(time.monotonic(), deadline, 'forked child did not exec')
                time.sleep(.01)
        process.stdin.write('exit\n')
        process.stdin.flush()
        self.assertEqual(process.wait(timeout=3), 0)
        return process, children, launch

    def test_orphan_game_is_stopped_after_leader_was_reaped(self):
        with tempfile.TemporaryDirectory() as directory:
            process, children, launch = self.forked_game(Path(directory))
            # Preserve the existing leader-only guard, then clean its orphan.
            live.stop_owned_process(process, launch['start'])
            self.assertNotEqual(live.owned_process_identity(children[0])['state'], 'Z')
            evidence = live.stop_owned_game_descendants(launch, timeout=.2)
            self.assertFalse(evidence['refused'])
            self.assertEqual(evidence['processes'][0]['signals'], ['SIGTERM'])
            self.assertEqual(evidence['processes'][0]['outcome'], 'exited')
            os.waitpid(children[0], 0)

    def test_stubborn_owned_orphan_uses_pidfd_kill_after_term(self):
        with tempfile.TemporaryDirectory() as directory:
            process, children, launch = self.forked_game(Path(directory), ignore_term=True)
            evidence = live.stop_owned_game_descendants(launch, timeout=.05)
            self.assertFalse(evidence['refused'])
            self.assertEqual(evidence['processes'][0]['signals'], ['SIGTERM', 'SIGKILL'])
            self.assertEqual(evidence['processes'][0]['outcome'], 'exited')
            os.waitpid(children[0], 0)

    def test_same_group_wrong_home_and_unrelated_session_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process, children, launch = self.forked_game(root, different_home=True)
            outsider = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                env=dict(os.environ, HOME=launch['home']), start_new_session=True)
            try:
                # Even a caller accidentally offering another session's PID
                # cannot make the authenticated pidfd path signal it.
                with mock.patch.object(live, 'owned_group_members', return_value=[*children, outsider.pid]):
                    evidence = live.stop_owned_game_descendants(launch, timeout=.2)
                refused = {row['pid']: row for row in evidence['refused']}
                self.assertIn('HOME mismatch', refused[children[1]]['reason'])
                self.assertIn('launch identity changed', refused[outsider.pid]['reason'])
                self.assertNotEqual(live.owned_process_identity(children[1])['state'], 'Z')
                self.assertIsNone(outsider.poll())
                self.assertEqual(os.waitpid(children[0], 0)[0], children[0])
            finally:
                outsider.kill()
                outsider.wait(timeout=3)

    def test_candidate_start_drift_and_reused_leader_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            process, children, launch = self.forked_game(Path(directory))
            original = live.owned_process_identity
            reads = 0
            def changed_start(pid):
                nonlocal reads
                value = original(pid)
                if pid == children[0]:
                    reads += 1
                    if reads >= 3:
                        value['start'] += 1
                return value
            with mock.patch.object(live, 'owned_process_identity', side_effect=changed_start), \
                 mock.patch.object(live.signal, 'pidfd_send_signal') as send:
                evidence = live.stop_owned_game_descendants(launch, timeout=0)
            send.assert_not_called()
            self.assertTrue(evidence['refused'])
            # Simulate reuse of the absent session leader before any effect.
            def reused_leader(pid):
                if pid == launch['leader']:
                    return dict(pid=pid, start=launch['start'] + 1, group=pid, session=pid)
                return original(pid)
            with mock.patch.object(live, 'owned_process_identity', side_effect=reused_leader), \
                 mock.patch.object(live.signal, 'pidfd_send_signal') as send:
                evidence = live.stop_owned_game_descendants(launch, timeout=0)
            send.assert_not_called()
            self.assertIn('leader identity changed', evidence['refused'][0]['reason'])
            wrong_image = dict(launch, inode=launch['inode'] + 1)
            with mock.patch.object(live.signal, 'pidfd_send_signal') as send:
                evidence = live.stop_owned_game_descendants(wrong_image, timeout=0)
            send.assert_not_called()
            self.assertIn('executable mismatch', evidence['refused'][0]['reason'])

    def test_lock_refuses_existing_file_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'lock'
            target.write_text('existing')
            with self.assertRaises(FileExistsError):
                live.create_lock_target(target, os.getuid(), os.getgid())
            self.assertEqual(target.read_text(), 'existing')
            target.unlink()
            target.symlink_to(root / 'missing')
            with self.assertRaises(FileExistsError):
                live.create_lock_target(target, os.getuid(), os.getgid())
            self.assertTrue(target.is_symlink())

    def test_lock_releases_only_original_inode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'lock'
            fd, stat = live.create_lock_target(path, os.getuid(), os.getgid())
            path.unlink()
            path.write_text('replacement')
            with self.assertRaisesRegex(RuntimeError, 'replaced'):
                live.release_lock_target(path, fd, stat)
            self.assertEqual(path.read_text(), 'replacement')
            path.unlink()
            fd, stat = live.create_lock_target(path, os.getuid(), os.getgid())
            live.release_lock_target(path, fd, stat)
            self.assertFalse(path.exists())

    def test_reused_or_reaped_leader_never_signalled(self):
        proc = mock.Mock(pid=12345)
        proc.poll.return_value = None
        with mock.patch.object(live, 'start_ticks', return_value=11), \
             mock.patch.object(live.os, 'killpg') as kill:
            live.stop_owned_process(proc, 10)
        kill.assert_not_called()
        proc.poll.return_value = 0
        with mock.patch.object(live.os, 'killpg') as kill:
            live.stop_owned_process(proc, 10)
        kill.assert_not_called()

    def test_kill_rechecks_identity_after_timeout(self):
        proc = mock.Mock(pid=12345)
        proc.poll.return_value = None
        proc.wait.side_effect = subprocess.TimeoutExpired('fake', 15)
        with mock.patch.object(live, 'start_ticks', side_effect=[10, 11]), \
             mock.patch.object(live.os, 'killpg') as kill:
            live.stop_owned_process(proc, 10)
        kill.assert_called_once_with(12345, live.signal.SIGTERM)

    def test_survivors_are_reported_after_bounded_wait(self):
        with mock.patch.object(live, 'owned_group_members', return_value=[12346]), \
             mock.patch.object(live.time, 'monotonic', side_effect=[0, 6]):
            self.assertEqual(live.wait_owned_groups({12345: 10}), {12345: [12346]})

    def test_gate_log_includes_rows_written_during_teardown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'engine-output.log'
            retained = root / 'retained.log'
            extracted = root / 'game1.log'
            script = """
import signal
import sys
import time

log_path = sys.argv[1]
def finish(*unused):
    with open(log_path, 'a') as output:
        output.write('[=ERROR=] 2.0 [X4LAN] NATIVE_GATE FINAL restored=1\\n')
    raise SystemExit(0)
signal.signal(signal.SIGTERM, finish)
with open(log_path, 'w') as output:
    output.write('[=ERROR=] 1.0 [X4LAN] NATIVE_GATE STOP completed=600\\n')
print('ready', flush=True)
while True:
    time.sleep(1)
"""
            process = subprocess.Popen(
                [sys.executable, '-c', script, str(source)],
                stdout=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            try:
                self.assertEqual(process.stdout.readline().strip(), 'ready')
                original_before_stop = source.read_text()
                with self.assertRaisesRegex(RuntimeError, 'writers may still run'):
                    live.retain_gate_log(source, retained, extracted, writers_closed=False)
                self.assertFalse(extracted.exists())
                started = live.start_ticks(process.pid)
                live.stop_owned_process(process, started)
                self.assertEqual(live.wait_owned_groups({process.pid: started}), {})
                self.assertNotEqual(source.read_text(), original_before_stop)
                live.retain_gate_log(source, retained, extracted, writers_closed=True)
                self.assertEqual(retained.read_text(), source.read_text())
                self.assertEqual(extracted.read_text(),
                                 '[X4LAN] NATIVE_GATE STOP completed=600\n'
                                 '[X4LAN] NATIVE_GATE FINAL restored=1\n')
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                process.stdout.close()

    def test_missing_engine_log_refuses_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(RuntimeError, 'engine log missing'):
                live.retain_gate_log(root / 'missing', root / 'raw', root / 'game1.log', True)
            self.assertFalse((root / 'game1.log').exists())

    def test_settled_groups_do_not_fail(self):
        with mock.patch.object(live, 'owned_group_members', side_effect=[[12346], []]), \
             mock.patch.object(live.time, 'sleep'):
            self.assertEqual(live.wait_owned_groups({12345: 10}), {})


if __name__ == '__main__':
    unittest.main()
