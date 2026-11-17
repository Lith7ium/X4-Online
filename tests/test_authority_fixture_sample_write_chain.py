"""Real local UDP and Lua writer, with synthetic MD and X4 ABI."""
import os
import json
import threading
import time
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev'), str(ROOT / 'tests')]
from authority.experimental_tcp_motion import motion_digest
from authority_fixture_player_sample_write_ipc import FixturePlayerSampleWriteIPC
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient
import authority_fixture_player_source_observe as observer
import test_authority_experimental_tcp_participants as fixture


def process_identity(pid):
    process = Path('/proc') / str(pid)
    stat_fields = (process / 'stat').read_text().rsplit(')', 1)[1].split()
    executable = (process / 'exe').stat()
    return {'pid':pid, 'start_ticks':int(stat_fields[19]), 'exe_dev':executable.st_dev, 'exe_ino':executable.st_ino}


@unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('luajit') and shutil.which('cc'),
                     'Linux, LuaJIT and C compiler required')
class FixtureSampleChainTest(unittest.TestCase):
    def test_python_to_real_lua_owner(self):
        with tempfile.TemporaryDirectory() as temporary:
            native = Path(temporary) / 'net.so'
            subprocess.run(['cc', '-std=c11', '-O2', '-shared', '-fPIC', 'src/native/net.c', '-ldl', '-o', str(native)],
                           cwd=ROOT, check=True, capture_output=True)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(('127.0.0.1', 0))
            environment = dict(os.environ, TEST_NET_LIB=str(native), TEST_NET_PORT=str(sock.getsockname()[1]))
            process = subprocess.Popen(['luajit', 'tests/authority_fixture_sample_writer_fake_x4.lua'], cwd=ROOT,
                                       env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                grant = dict(session_epoch='s', epoch='a'*32, generation='b'*32, index=3,
                             sector_macro='cluster_33_sector001_macro', token='1'*32, incarnation='2'*32)
                sample = dict(version=2, epoch=grant['epoch'], generation=grant['generation'], index=3,
                              sequence=1, sector_macro=grant['sector_macro'], source_time=1.,
                              x=110., y=20., z=30., velocity=None,
                              orientation=dict(yaw=.1, pitch=.2, roll=.3), angular_rate=None)
                writer = FixturePlayerSampleWriteIPC(sock, enabled=True, lease='d'*32, attempt='e'*32,
                    grant=grant, process=process_identity(process.pid), guard=lambda: True,
                    grant_guard=lambda value: value == grant, timeout=5)
                try:
                    self.assertTrue(writer.wait_ready())
                    observed = writer.apply_once(sample)
                    self.assertEqual(observed['sample_sha256'], motion_digest(sample))
                    self.assertEqual(observed['before'], [100.,20.,30.])
                    self.assertEqual(observed['after'], [110.,20.,30.])
                    self.assertTrue(writer.write_confirmed)
                finally:
                    writer.close()
            finally:
                sock.close()
                process.terminate()
                _, stderr = process.communicate(timeout=5)
                if process.returncode not in (-15, 0):
                    self.fail(stderr.decode(errors='replace'))

    def test_real_tcp_sample_reaches_real_lua_writer_over_udp(self):
        case = fixture.ParticipantTCPTest('test_adapter_refuses_use_outside_active_host_operation')
        case.setUp()
        self.addCleanup(case.doCleanups)
        clients = [case.connect(), case.connect()]
        for client in clients:
            case.offer_and_claim(client)
        grants = {
            1: dict(session_epoch='a'*32, epoch='a'*32, generation='b'*32, index=3,
                    sector_macro='cluster_33_sector001_macro', token='1'*32, incarnation='2'*32),
            2: dict(session_epoch='a'*32, epoch='a'*32, generation='c'*32, index=4,
                    sector_macro='cluster_45_sector001_macro', token='3'*32, incarnation='4'*32),
        }
        stop = threading.Event()
        pulse_seen = threading.Event()
        threads, errors = [], []

        def serve(conn, handle):
            try:
                conn.settimeout(3)
                raw = b''
                while not raw.endswith(b'\n'):
                    raw += conn.recv(1)
                assert json.loads(raw)['kind'] == 'accepted'
                sequence = 0
                class Controller:
                    def pause(self, _handles): return True
                    def resume(self, _handles): return True
                def pull():
                    nonlocal sequence
                    sequence += 1
                    grant = grants[handle]
                    return dict(version=2, epoch=grant['epoch'], generation=grant['generation'],
                        index=grant['index'], sequence=sequence, sector_macro=grant['sector_macro'],
                        source_time=float(sequence), x=(110. if handle != 1 or pulse_seen.is_set() else 100.), y=20., z=30.,
                        velocity=None if sequence == 1 else dict(x=0., y=0., z=0.),
                        orientation=dict(yaw=.1, pitch=.2, roll=.3),
                        angular_rate=None if sequence == 1 else dict(yaw=0., pitch=0., roll=0.))
                client = ExperimentalTCPParticipantClient(conn, Controller(), enabled=True,
                    epoch='a'*32, handle=handle, timeout=2, authority_grant=grants[handle],
                    authority_guard=lambda candidate: candidate == grants[handle], pull_authority_motion=pull)
                while not stop.is_set(): client.poll(.05)
                client.close()
            except BaseException as error:
                if not stop.is_set(): errors.append(error)

        for handle, connection in enumerate(clients, 1):
            thread = threading.Thread(target=serve, args=(connection, handle))
            thread.start(); threads.append(thread)
        def close_clients():
            stop.set()
            for thread in threads: thread.join(2)
            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertEqual(errors, [])
        self.addCleanup(close_clients)
        case.host.tick(.1)
        with tempfile.TemporaryDirectory() as temporary:
            native = Path(temporary) / 'net.so'
            subprocess.run(['cc', '-std=c11', '-O2', '-shared', '-fPIC', 'src/native/net.c', '-ldl', '-o', str(native)],
                           cwd=ROOT, check=True, capture_output=True)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(('127.0.0.1', 0))
            environment = dict(os.environ, TEST_NET_LIB=str(native), TEST_NET_PORT=str(sock.getsockname()[1]))
            process = subprocess.Popen(['luajit', 'tests/authority_fixture_sample_writer_fake_x4.lua'], cwd=ROOT,
                                       env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            calls = []
            try:
                def write(handle, grant, sample):
                    calls.append((handle, sample['sequence']))
                    writer = FixturePlayerSampleWriteIPC(sock, enabled=True, lease='d'*32, attempt='e'*32,
                        grant=grant, process=process_identity(process.pid), guard=lambda: True,
                        grant_guard=lambda value: value == grants[handle], timeout=5)
                    try:
                        self.assertTrue(writer.wait_ready())
                        return writer.apply_once(sample)
                    finally:
                        writer.close()
                def pulse(handle, grant):
                    self.assertEqual((handle, grant), (1, grants[1]))
                    pulse_seen.set()
                    return {'start_dispatched':True, 'start_acknowledged':True, 'stop_acknowledged':True,
                            'movement_proven':False, 'human_input_proven':False, 'stationary_proven':False, 'stop_game_time':2.5}
                result = observer.observe(host=case.host, world=case.world, grants=grants, verify=lambda: True,
                    deadline=time.monotonic()+8, operation_timeout=3, enabled=True,
                    sample_write_slot=1, write_sample_once=write, pulse_client_once=pulse)
                self.assertEqual(calls, [(1, 4)])
                self.assertEqual(result['client_movement']['fence']['sequence'], 3)
                self.assertEqual(result['server_position_once']['before'], [100.,20.,30.])
                self.assertEqual(result['server_position_once']['after'], [110.,20.,30.])
                self.assertTrue(result['source_to_server_frame_assumed'])
                self.assertFalse(result['windows_frame_proven'])
                self.assertTrue(result['client_movement_proven'])
                self.assertEqual(result['client_movement']['baseline']['position'], [100.,20.,30.])
                self.assertEqual(result['client_movement']['moved']['position'], [110.,20.,30.])
                self.assertEqual(result['client_movement']['moved']['sample_sha256'], result['server_position_once']['sample_sha256'])
                self.assertFalse(result['server_x4_motion_applied'])
                self.assertTrue(result['server_x4_position_once_applied'])
            finally:
                sock.close()
                process.terminate()
                _, stderr = process.communicate(timeout=5)
                if process.returncode not in (-15, 0): self.fail(stderr.decode(errors='replace'))
