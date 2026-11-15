"""Real anonymous-pipe/namespace children and the runner's cancellation cleanup."""
import ast
import inspect
import os
from pathlib import Path
import select
import subprocess
import sys
import time
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/dev'))
import linux_gate_live as live
import linux_local_stop as stop


CHILD = r'''
import fcntl, os, stat, sys, time
fd_text = os.environ['X4_DEV_PLAYER_STOP_FD']
fd = int(fd_text)
assert str(fd) == fd_text and fd >= 3
flags = fcntl.fcntl(fd, fcntl.F_GETFL)
assert flags & os.O_ACCMODE == os.O_RDONLY and flags & os.O_NONBLOCK
identity = os.fstat(fd)
assert stat.S_ISFIFO(identity.st_mode)
for entry in os.listdir('/proc/self/fd'):
    other = int(entry)
    try:
        info = os.fstat(other)
    except OSError:
        continue
    if stat.S_ISFIFO(info.st_mode) and info.st_ino == identity.st_ino:
        assert fcntl.fcntl(other, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
    if len(sys.argv) > 1:
        assert info.st_ino != int(sys.argv[1])
print('READY', flush=True)
while True:
    try:
        value = os.read(fd, 2)
    except BlockingIOError:
        time.sleep(.005)
        continue
    assert value in (b'S', b'')
    sys.exit(225)
'''


class LocalStopTests(unittest.TestCase):
    def setUp(self):
        self.processes = []
        self.channels = []

    def tearDown(self):
        for channel in self.channels:
            channel.close()
        for process in self.processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()

    def launch(self, slot=1, *, namespace=False, forbidden=None, responsive=True):
        def command(environment):
            if not responsive:
                return ['/usr/bin/python3', '-u', '-c',
                        "import time; print('READY', flush=True); time.sleep(30)"]
            program = ['/usr/bin/python3', '-u', '-c', CHILD]
            if forbidden is not None:
                program.append(str(forbidden))
            if namespace:
                # Exercise both bwrap's environment reset and another exec boundary.
                exec_script = 'import os,sys; os.execve(sys.argv[1],sys.argv[1:],os.environ)'
                program = ['/usr/bin/python3', '-c', exec_script, *program]
                return ['bwrap', '--ro-bind', '/', '/', '--proc', '/proc', '--dev', '/dev',
                        '--die-with-parent', '--clearenv', '--setenv', stop.STOP_FD_ENV,
                        environment[stop.STOP_FD_ENV], '--', *program]
            return program

        def launch(command, **options):
            if not namespace:
                options['env'] = environment_seen[0]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       start_new_session=True, **options)
            self.processes.append(process)
            return process

        environment_seen = []
        def factory(environment):
            environment_seen.append(environment)
            return command(environment)
        process, channel = stop.launch_game(slot, {}, factory, launch, True)
        self.channels.append(channel)
        ready, _, _ = select.select([process.stdout], [], [], 4)
        self.assertTrue(ready, 'child did not report readiness')
        line = process.stdout.readline()
        if line != b'READY\n':
            process.wait(timeout=3)
            self.fail(f'child startup: {line!r}, {process.stderr.read()!r}')
        self.assertIsNone(channel.read_fd)
        self.assertFalse(os.get_inheritable(channel.write_fd))
        return process, channel

    def test_bwrap_exec_readonly_nonblocking_and_other_game_isolation(self):
        first, first_channel = self.launch(slot=1)
        first_inode = os.fstat(first_channel.write_fd).st_ino
        second, second_channel = self.launch(slot=2, namespace=True, forbidden=first_inode)
        evidence = stop.cooperative_stop([second_channel])
        self.assertEqual(set(evidence), {'2'})
        self.assertEqual(evidence['2']['returncode_before_fallback'], 225)
        self.assertTrue(evidence['2']['request_written'])
        self.assertTrue(evidence['2']['exit225_observed'])
        self.assertFalse(evidence['2']['fallback_needed'])
        self.assertIsNone(first.poll(), 'guest cleanup affected another local game')
        self.assertEqual(stop.cooperative_stop([first_channel])['1']['returncode_before_fallback'], 225)

    def test_eof_closes_child_without_claiming_sent_request(self):
        process, channel = self.launch()
        channel.close()
        self.assertEqual(process.wait(timeout=3), 225)
        evidence = stop.cooperative_stop([channel])['1']
        self.assertFalse(evidence['requested'])
        self.assertFalse(evidence['request_written'])
        self.assertTrue(evidence['exit225_observed'])

    def test_disabled_launch_has_no_pipe_or_inherited_environment(self):
        launch = mock.Mock(return_value='process')
        factory = mock.Mock(return_value=['fixture'])
        with mock.patch.object(os, 'pipe2', side_effect=AssertionError('unexpected pipe')):
            self.assertEqual(stop.launch_game(1, {stop.STOP_FD_ENV: '55', 'KEEP': 'yes'},
                                             factory, launch, False), ('process', None))
        factory.assert_called_once_with({'KEEP': 'yes'})
        launch.assert_called_once_with(['fixture'])

    def test_launch_failure_closes_both_descriptors_preserves_original(self):
        failure = RuntimeError('original launch error')
        descriptors = []
        def command(environment):
            descriptors.append(int(environment[stop.STOP_FD_ENV]))
            return ['fixture']
        original_pipe = os.pipe2
        def pipe(flags):
            ends = original_pipe(flags)
            descriptors.extend(ends)
            return ends
        with mock.patch.object(os, 'pipe2', side_effect=pipe):
            with self.assertRaises(RuntimeError) as raised:
                stop.launch_game(1, {}, command, mock.Mock(side_effect=failure), True)
        self.assertIs(raised.exception, failure)
        for descriptor in descriptors:
            with self.assertRaises(OSError):
                os.fstat(descriptor)

    def cleanup_runner_prefix(self, processes, channels, result, fallback):
        # Compile the actual run() finally prefix, including cooperative/fallback order.
        tree = ast.parse(inspect.getsource(live.run))
        body = next(node.finalbody for node in ast.walk(tree)
                    if isinstance(node, ast.Try) and any(
                        isinstance(child, ast.Assign) and any(
                            isinstance(target, ast.Subscript) and
                            isinstance(target.slice, ast.Constant) and
                            target.slice.value == 'owned_processes_remaining'
                            for target in child.targets) for child in node.finalbody))
        prefix = []
        for node in body:
            if isinstance(node, ast.Assign):
                break
            prefix.append(node)
        namespace = {'local_stop_enabled': True, 'result': result,
                     'local_stop': stop, 'local_stop_channels': channels,
                     'procs': processes, 'starts': {p.pid: live.start_ticks(p.pid) for p in processes},
                     'stop_owned_process': fallback, 'subprocess': subprocess}
        exec(compile(ast.Module(body=prefix, type_ignores=[]), '<actual run cleanup>', 'exec'), namespace)

    def test_actual_runner_cancel_cooperative_then_fallback_preserves_error(self):
        cooperative, channel = self.launch(slot=2)
        stubborn, stubborn_channel = self.launch(slot=3, responsive=False)
        original_error = 'cancelled: original failure'
        result = {'error': original_error}
        seen = []
        def fallback(process, started):
            seen.append(process.pid)
            self.assertIsNone(channel.write_fd)
            self.assertIsNone(stubborn_channel.write_fd)
            live.stop_owned_process(process, started)
        original_stop = stop.cooperative_stop
        started = time.monotonic()
        with mock.patch.object(stop, 'cooperative_stop',
                               side_effect=lambda channels: original_stop(channels, timeout=.06)):
            self.cleanup_runner_prefix([cooperative, stubborn], [channel, stubborn_channel], result, fallback)
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(result['error'], original_error)
        self.assertEqual(seen, [stubborn.pid, cooperative.pid])
        clients = result['local_stop']['clients']
        self.assertEqual(clients['2']['returncode_before_fallback'], 225)
        self.assertFalse(clients['2']['fallback_attempted'])
        self.assertIsNone(clients['3']['returncode_before_fallback'])
        self.assertTrue(clients['3']['fallback_needed'])
        self.assertTrue(clients['3']['fallback_attempted'])
        self.assertNotEqual(clients['3']['returncode_after_fallback'], 225)

    def test_broken_pipe_is_recorded_and_closed(self):
        channel = stop.LocalStopChannel(1)
        self.channels.append(channel)
        channel.process = mock.Mock()
        channel.process.poll.return_value = None
        channel.close_read()
        evidence = stop.cooperative_stop([channel], timeout=0)['1']
        self.assertTrue(evidence['requested'])
        self.assertFalse(evidence['request_written'])
        self.assertIn('write_error', evidence)
        self.assertTrue(evidence['fallback_needed'])
        self.assertIsNone(channel.write_fd)

    def test_actual_runner_launch_passes_only_requested_read_descriptor(self):
        tree = ast.parse(inspect.getsource(live.run))
        function = next(node for node in ast.walk(tree)
                        if isinstance(node, ast.FunctionDef) and node.name == 'launch')
        with tempfile.TemporaryDirectory() as directory:
            logs = []
            starts, processes = {}, []
            process = mock.Mock(pid=1234)
            popen = mock.Mock(return_value=process)
            namespace = {'run_dir': Path(directory), 'logs': logs, 'starts': starts,
                         'procs': processes, 'os': os, 'ctypes': live.ctypes,
                         'signal': live.signal, 'subprocess': SimpleNamespace(
                             Popen=popen, DEVNULL=subprocess.DEVNULL, STDOUT=subprocess.STDOUT),
                         'user': SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid()),
                         'start_ticks': mock.Mock(return_value=99)}
            exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual run launch>', 'exec'), namespace)
            try:
                namespace['launch']('game1', ['fixture'], pass_fds=(51,))
                self.assertEqual(popen.call_args.kwargs['pass_fds'], (51,))
                self.assertEqual(starts, {1234: 99})
                self.assertEqual(processes, [process])
                namespace['launch']('relay', ['fixture'])
                self.assertNotIn('pass_fds', popen.call_args.kwargs)
            finally:
                for log in logs:
                    log.close()

    def test_option_requires_worker_dispatch_and_is_explicit(self):
        for manifest in ({}, {'worker_dispatch': False}, {'worker_dispatch': 1}):
            self.assertRaises(ValueError, stop.validate_option, True, manifest)
        self.assertTrue(stop.validate_option(True, {'worker_dispatch': True}))
        self.assertFalse(stop.validate_option(False, {}))
        with mock.patch.object(live, 'run') as run:
            live.main(['run', '--root', '/unused'])
            self.assertFalse(run.call_args.args[0].local_stop)
            live.main(['run', '--root', '/unused', '--local-stop'])
            self.assertTrue(run.call_args.args[0].local_stop)


if __name__ == '__main__':
    unittest.main()
