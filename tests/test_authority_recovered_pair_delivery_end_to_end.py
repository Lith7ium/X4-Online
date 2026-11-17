"""One synthetic X4 pair through real source UDP, TCP and client Lua buffer.

This exercises local protocol owners; it does not start X4 or prove gameplay.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests'), str(ROOT / 'tools/dev')]
from authority.experimental_participant_motion_ipc import ExperimentalParticipantMotionIPC
from authority.experimental_source_motion_ipc import ExperimentalSourceMotionIPC
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import ExperimentalTCPMotion, motion_digest
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient
from authority_source_job_bind import bind_running_source
from authority_tcp_job_client_live import socket_owner
from authority_tcp_native_worker import check_process
import test_authority_experimental_tcp_participants as fixture


class Controller:
    def pause(self, _): return True
    def resume(self, _): return True


def process_identity(process):
    executable = os.stat(f'/proc/{process.pid}/exe')
    fields = Path(f'/proc/{process.pid}/stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': process.pid, 'start_ticks': int(fields[19]),
            'exe_dev': executable.st_dev, 'exe_ino': executable.st_ino}


@unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('cc') and shutil.which('luajit'),
                     'Linux, LuaJIT and a C compiler required')
class RecoveredPairDeliveryEndToEnd(unittest.TestCase):
    def setUp(self):
        fixture.ParticipantTCPTest.setUp(self)

    def test_second_pair_sample_reaches_client_buffer_and_receipt_before_source_stop(self):
        stop = threading.Event()
        ready = threading.Event()
        errors = []
        participant_thread = None
        children = []
        sockets = []
        bridge = None
        try:
            with tempfile.TemporaryDirectory() as directory:
                net = Path(directory) / 'net.so'
                abi = Path(directory) / 'client-abi.so'
                subprocess.run(['cc', '-std=c11', '-O2', '-shared', '-fPIC', 'src/native/net.c',
                                '-ldl', '-o', str(net)], cwd=ROOT, check=True, capture_output=True)
                subprocess.run(['cc', '-O2', '-shared', '-fPIC',
                                'tests/fixtures/replica_motion_binding_abi.c', '-o', str(abi)],
                               cwd=ROOT, check=True, capture_output=True)
                tcp = fixture.ParticipantTCPTest.connect(self)
                fixture.ParticipantTCPTest.offer_and_claim(self, tcp)
                client_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                source_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sockets.extend((client_udp, source_udp))
                client_udp.bind(('127.0.0.1', 0))
                source_udp.bind(('127.0.0.1', 0))
                client_env = dict(os.environ, LD_PRELOAD=str(abi), TEST_NET_LIB=str(net),
                                  TEST_NET_PORT=str(client_udp.getsockname()[1]))
                client_process = subprocess.Popen(
                    ['luajit', 'tests/authority_saved_motion_pair_client_fake_x4.lua'],
                    cwd=ROOT, env=client_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                children.append(client_process)
                client_identity = process_identity(client_process)
                source_env = dict(os.environ, TEST_NET_LIB=str(net),
                                  TEST_NET_PORT=str(source_udp.getsockname()[1]))
                source_process = subprocess.Popen(
                    ['luajit', 'tests/authority_recovered_pair_delivery_fake_source.lua'],
                    cwd=ROOT, env=source_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                children.append(source_process)
                source_identity = process_identity(source_process)

                def participant():
                    client_bridge = adapter = None
                    try:
                        tcp.settimeout(3)
                        frame = b''
                        while not frame.endswith(b'\n'):
                            chunk = tcp.recv(1)
                            if not chunk:
                                raise RuntimeError('missing participant admission')
                            frame += chunk
                        if json.loads(frame)['kind'] != 'accepted':
                            raise RuntimeError('participant admission refused')
                        destination = client_udp.getsockname()
                        client_bridge = ExperimentalParticipantMotionIPC(
                            client_udp, enabled=True, lease='a' * 32, attempt='b' * 32,
                            epoch='c' * 32, generation='d' * 32,
                            guard=lambda: client_process.poll() is None,
                            validate_peer=lambda peer: socket_owner(peer, destination, client_identity), timeout=3)
                        client_bridge.wait_ready()
                        adapter = ExperimentalTCPParticipantClient(
                            tcp, Controller(), enabled=True, epoch='a' * 32, handle=1,
                            timeout=4, apply_motion=client_bridge)
                        ready.set()
                        while not stop.is_set():
                            adapter.poll(.05)
                    except BaseException as error:
                        if not stop.is_set():
                            errors.append(error)
                    finally:
                        for owned in (adapter, client_bridge):
                            try:
                                if owned is adapter and owned and not owned._failed and not owned._closed:
                                    owned.close()
                                if owned is client_bridge and owned and owned.state not in ('closed', 'failed'):
                                    owned.close()
                            except BaseException as error:
                                errors.append(error)

                participant_thread = threading.Thread(target=participant)
                participant_thread.start()
                self.host.tick(.1)
                self.assertTrue(ready.wait(3), 'client owner did not become ready')
                self.assertEqual(errors, [])
                self.assertEqual(self.world.session.state, 'running')
                destination = source_udp.getsockname()

                def both_processes_alive():
                    check_process(client_identity)
                    check_process(source_identity)
                    return client_process.poll() is None and source_process.poll() is None

                source_udp = bind_running_source(
                    source_udp, process=source_identity, lease='1' * 32, attempt='2' * 32,
                    epoch='c' * 32, generation='d' * 32, world=self.world,
                    client_guard=both_processes_alive, timeout=3)
                delivery = ExperimentalTCPJobDelivery(self.host, enabled=True, timeout=3)
                motion = ExperimentalTCPMotion(delivery, enabled=True)
                staged = []
                bridge = ExperimentalSourceMotionIPC(
                    source_udp, motion, enabled=True, lease='1' * 32, attempt='2' * 32,
                    epoch='c' * 32, generation='d' * 32, guard=both_processes_alive,
                    validate_peer=lambda peer: socket_owner(peer, destination, source_identity),
                    timeout=5, saved_baseline=10054,
                    saved_guard=lambda epoch, count: epoch == 'c' * 32 and count == 10054,
                    validate_sample=lambda sample: staged.append(sample.copy()) or True,
                    stop_enabled=True)
                self.assertTrue(bridge.register_saved(42))
                sample = bridge.pull()
                expected = {'version': 1, 'epoch': 'c' * 32, 'generation': 'd' * 32,
                            'index': 42, 'sequence': 2, 'sector_macro': 'sector_a',
                            'source_time': 1.5, 'x': 2.0, 'y': 2.0, 'z': 3.0,
                            'velocity': {'x': 2.0, 'y': 0.0, 'z': 0.0}}
                self.assertEqual(sample, expected)
                self.assertEqual(staged, [expected])
                receipt = (2, motion_digest(expected))
                track = motion._tracks[('c' * 32, 'd' * 32, 42)]
                self.assertIn(receipt, track['peer_samples'].values())
                # The real Lua fake checks pose/time/rate in push before it sends BOUND.
                self.assertTrue(bridge.stop_remote())
                bridge.close()
                bridge = None
                self.assertTrue(both_processes_alive())
                self.assertEqual(errors, [])
        finally:
            original_error = sys.exception()
            stop.set()
            cleanup_errors = []
            if participant_thread:
                participant_thread.join(3)
                if participant_thread.is_alive():
                    cleanup_errors.append(RuntimeError('participant thread did not stop'))
            if bridge is not None and bridge.state not in ('closed', 'failed'):
                try:
                    bridge.close()
                except BaseException as error:
                    cleanup_errors.append(error)
            for child in children:
                if child.poll() is not None:
                    cleanup_errors.append(RuntimeError('synthetic Lua owner exited before cleanup'))
                try:
                    if child.poll() is None:
                        child.terminate()
                except BaseException as error:
                    cleanup_errors.append(error)
                try:
                    _, stderr = child.communicate(timeout=3)
                    if stderr:
                        cleanup_errors.append(RuntimeError('synthetic Lua owner emitted errors: ' + stderr.decode(errors='replace')))
                    if child.returncode != -signal.SIGTERM:
                        cleanup_errors.append(RuntimeError('synthetic Lua owner did not terminate as expected'))
                except BaseException as error:
                    cleanup_errors.append(error)
                    try:
                        if child.poll() is None:
                            child.kill()
                    except BaseException as kill_error:
                        cleanup_errors.append(kill_error)
                    try:
                        child.communicate(timeout=3)
                    except BaseException as reap_error:
                        cleanup_errors.append(reap_error)
            for owned_socket in sockets:
                try:
                    owned_socket.close()
                except BaseException as error:
                    cleanup_errors.append(error)
            cleanup_errors.extend(errors)
            if cleanup_errors:
                cleanup_failure = BaseExceptionGroup('test cleanup failed', cleanup_errors)
                if original_error is None:
                    raise cleanup_failure
                original_error.add_note('Test cleanup failures: ' + ', '.join(repr(error) for error in cleanup_errors))


if __name__ == '__main__':
    unittest.main()
