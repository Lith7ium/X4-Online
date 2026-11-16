"""Exercise the recovered motion chain, with simulated X4, MD and checkpoints.

This uses the real probe, TCP host, worker and Lua motion owners. It does not
exercise native X4, the outer recovery supervisor, save/load or rendered motion.
"""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev'), str(ROOT/'tests')]
from authority.experimental_client_load import HonestClientLoadClaim
from authority.load_messages import Receipt
from authority.trusted_load_messages import encode_load_claim
from authority_helper_lifecycle import OwnedHelper
from authority_tcp_native_live import TCPMarkedParticipant
from authority_tcp_native_worker import check_process, read_line
from authority_recovered_server_client import ClientMotionErrorWatch
import authority_recovered_source_probe as probe
import test_authority_experimental_tcp_participants as fixtures


def process_identity(process):
    proc = Path('/proc')/str(process.pid)
    image = (proc/'exe').stat()
    fields = (proc/'stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': process.pid, 'start_ticks': int(fields[19]),
            'exe_dev': image.st_dev, 'exe_ino': image.st_ino}


@unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('cc') and shutil.which('luajit')
                     and hasattr(os, 'pidfd_open'), 'Linux, pidfd, LuaJIT and C compiler required')
class RecoveredSourceWorkerChain(unittest.TestCase):
    def test_source_probe_delivers_two_samples_then_stops_both_owners(self):
        case = fixtures.ParticipantTCPTest('test_adapter_refuses_use_outside_active_host_operation')
        case.setUp()
        sockets, children, helpers = [], [], []
        stop_engine = threading.Event()
        engine_errors = []
        engine_thread = None
        participant = None
        try:
            with tempfile.TemporaryDirectory() as directory:
                directory = Path(directory)
                net, abi = directory/'net.so', directory/'abi.so'
                for source, output, flags in (
                    ('src/native/net.c', net, ['-ldl']),
                    ('tests/fixtures/replica_motion_binding_abi.c', abi, []),
                ):
                    subprocess.run(['cc', '-O2', '-shared', '-fPIC', source, *flags, '-o', str(output)],
                                   cwd=ROOT, check=True, capture_output=True)
                def udp():
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.bind(('127.0.0.1', 0)); sockets.append(sock)
                    return sock
                source_sock, motion_sock, control_sock, engine = udp(), udp(), udp(), udp()
                parent, child = socket.socketpair(); sockets.extend((parent, child))
                source_env = dict(os.environ, TEST_NET_LIB=str(net), TEST_NET_PORT=str(source_sock.getsockname()[1]))
                client_env = dict(os.environ, LD_PRELOAD=str(abi), TEST_NET_LIB=str(net),
                                  TEST_NET_PORT=str(motion_sock.getsockname()[1]), TEST_MOTION_STOP='ok')
                source = subprocess.Popen(['luajit', 'tests/authority_recovered_source_worker_fake_x4.lua'],
                                          cwd=ROOT, env=source_env, stderr=subprocess.PIPE)
                children.append(source)
                client_game = subprocess.Popen(['luajit', 'tests/authority_recovered_worker_client_fake_x4.lua'],
                                               cwd=ROOT, env=client_env, stderr=subprocess.PIPE)
                children.append(client_game)
                source_id, client_id = process_identity(source), process_identity(client_game)
                tcp = case.connect(); case.offer_and_claim(tcp)
                case.control.poll(.1)  # Flush the queued acceptance before handing off TCP.
                self.assertEqual(json.loads(tcp.recv(4096))['kind'], 'accepted')
                deadline = time.monotonic()+25
                receipt = Receipt('a'*32, 1, 1, 1, '8'*32, 'checkpoint-'+'6'*32, '5'*64, 10)
                config = {'version': 1, 'claim': encode_load_claim(HonestClientLoadClaim(receipt, '4'*32, True, True)).decode(),
                          'epoch': 'a'*32, 'handle': 1, 'lease': '9'*32,
                          'udp_peer': list(engine.getsockname()), 'udp_next_id': 1,
                          'deadline': deadline, 'controller_timeout': 8, 'client_process': client_id,
                          'already_admitted': True,
                          'motion': {'lease': '7'*32, 'attempt': 'b'*32, 'epoch': 'c'*32,
                                     'generation': 'd'*32, 'timeout': 2}}
                descriptors = [tcp.fileno(), control_sock.fileno(), child.fileno(), motion_sock.fileno()]
                helper = OwnedHelper([sys.executable, str(ROOT/'tools/dev/authority_tcp_native_worker.py'),
                                      *(str(fd) for fd in descriptors)], registry=helpers, pass_fds=tuple(descriptors))
                for sock in (tcp, control_sock, child, motion_sock): sock.close()
                parent.sendall(json.dumps(config).encode()+b'\n'); helper.release()
                self.assertEqual(json.loads(read_line(parent, 512, deadline)), {'event': 'active'})
                engine.settimeout(.1)
                def respond():
                    try:
                        while not stop_engine.is_set():
                            try: data, peer = engine.recvfrom(1024)
                            except socket.timeout: continue
                            row = data.decode().split('|')
                            if len(row) != 5 or row[0] != 'CMD': raise ValueError('unexpected control packet')
                            engine.sendto('|'.join(('RECEIPT', *row[1:], 'confirmed')).encode(), peer)
                    except BaseException as error:
                        if not stop_engine.is_set(): engine_errors.append(error)
                engine_thread = threading.Thread(target=respond); engine_thread.start()
                case.host.tick(.1)
                self.assertEqual(case.world.session.state, 'running')
                baseline = object(); case.world._baseline = (7, baseline)
                participant = TCPMarkedParticipant(deadline, first_resume_only=True, keep_worker=True)
                participant.ipc = parent; participant.helpers = helpers
                participant.motion_worker_config = config['motion']
                participant._pin_motion_ipc()
                log = directory/'client.log'; log.write_text('simulated client started\n')
                log_watch = ClientMotionErrorWatch(log); log_watch.poll()
                def active_context():
                    check_process(client_id)
                    log_watch.poll()
                    return not engine_errors
                participant._active_check = lambda **_: helper.proc.poll() is None and active_context()
                participant._pin_motion_stop(helper, active_context, deadline)
                guard_stops = []
                guard = SimpleNamespace(status=('ready', 'c'*32, 10054, 'e'*64), deadline=deadline,
                                        check=lambda: not guard_stops,
                                        stop=lambda: guard_stops.append('stopped') or True)
                pump = SimpleNamespace(activate=lambda **_: None)
                result = probe.run(sock=source_sock,
                    settings={'lease':'1'*32, 'attempt':'2'*32, 'epoch':'c'*32,
                              'generation':'d'*32, 'baseline':10054},
                    index=42, baseline=baseline, guard=guard, pump=pump,
                    active=SimpleNamespace(participant=participant), host=case.host, world=case.world,
                    identity=(source_id['pid'], source_id['start_ticks']),
                    verify=lambda: check_process(source_id), verify_process=lambda: check_process(source_id),
                    verify_stopped=lambda: check_process(source_id), client_motion=True, timeout=20)
                self.assertTrue(result['client_motion_receipts_confirmed'])
                self.assertTrue(result['client_worker_stop_confirmed'])
                self.assertEqual(result['samples'][1]['velocity'], {'x':2, 'y':0, 'z':0})
                self.assertEqual(len(result['client_receipt_sample_sha256']), 2)
                self.assertFalse(result['client_motion_visible_proven'])
                self.assertFalse(result['cross_process_identity_proven'])
                self.assertEqual(guard_stops, ['stopped'])
                self.assertEqual(helper.proc.returncode, 0)
                self.assertTrue(participant.check_motion_stopped())
                self.assertIsNone(source.poll()); self.assertIsNone(client_game.poll())
                log_watch.poll()
                self.assertEqual(engine_errors, [])
        finally:
            cleanup_errors = []
            def clean(action):
                try: action()
                except BaseException as error: cleanup_errors.append(error)
            stop_engine.set()
            if engine_thread is not None:
                clean(lambda: engine_thread.join(3))
                if engine_thread.is_alive(): cleanup_errors.append(RuntimeError('control responder did not stop'))
            for helper in reversed(helpers): clean(helper.stop)
            for sock in sockets: clean(sock.close)
            if participant is not None: clean(participant.sock.close)
            def reap(child):
                if child.poll() is None: child.terminate()
                try: _, error = child.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill(); child.communicate(timeout=3)
                    raise
                if error: raise RuntimeError('simulated X4 owner reported an error: '+error.decode(errors='replace'))
            for child in children: clean(lambda child=child: reap(child))
            clean(case.doCleanups)
            if cleanup_errors: raise BaseExceptionGroup('test cleanup failed', cleanup_errors)


if __name__ == '__main__': unittest.main()
