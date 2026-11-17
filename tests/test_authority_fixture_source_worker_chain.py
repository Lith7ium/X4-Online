"""Real worker/TCP/UDP/Lua fixture chain; game components and MD are doubles."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]
from authority.experimental_client_load import HonestClientLoadClaim
from authority.load_messages import Receipt
from authority.trusted_load_messages import encode_load_claim
from test_authority_tcp_native_worker import line


def identity(pid):
    proc = Path('/proc') / str(pid)
    fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
    executable = (proc / 'exe').stat()
    return dict(pid=pid, start_ticks=int(fields[19]), exe_dev=executable.st_dev, exe_ino=executable.st_ino)


@unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('luajit') and shutil.which('cc'),
                     'Linux, LuaJIT and C compiler required')
class FixtureSourceWorkerChain(unittest.TestCase):
    def test_both_player_slots_deliver_position_and_velocity(self):
        with tempfile.TemporaryDirectory() as temporary:
            native = Path(temporary) / 'net.so'
            subprocess.run(['cc', '-std=c11', '-O2', '-shared', '-fPIC', 'src/native/net.c', '-ldl', '-o', str(native)],
                           cwd=ROOT, check=True, capture_output=True)
            for slot, latest in ((1, False), (2, False), (1, True), (2, True)):
                with self.subTest(slot=slot, latest=latest):
                    self.check_slot(slot, native, latest)

    def check_slot(self, slot, native, latest):
        sockets, children = [], []
        try:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sockets.append(listener); listener.bind(('127.0.0.1', 0)); listener.listen(1)
            client = socket.create_connection(listener.getsockname(), timeout=3); sockets.append(client)
            server, _ = listener.accept(); sockets.append(server); server.settimeout(10)
            participant = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sockets.append(participant); participant.bind(('127.0.0.1', 0))
            engine = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sockets.append(engine); engine.bind(('127.0.0.1', 0)); engine.settimeout(4)
            source = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sockets.append(source); source.bind(('127.0.0.1', 0))
            parent, child = socket.socketpair(); sockets.extend((parent, child)); parent.settimeout(10)
            environment = dict(os.environ, TEST_NET_LIB=str(native), TEST_NET_PORT=str(source.getsockname()[1]),
                               TEST_FIXTURE_SLOT=str(slot), TEST_LATEST_CACHE='1' if latest else '0')
            lua = subprocess.Popen(['luajit', 'tests/authority_fixture_player_source_worker_fake_x4.lua'], cwd=ROOT,
                                   env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            children.append(lua)
            descriptors = (client.fileno(), participant.fileno(), child.fileno(), source.fileno())
            helper = subprocess.Popen([sys.executable, str(ROOT / 'tools/dev/authority_tcp_native_worker.py'),
                                       *(str(fd) for fd in descriptors)], pass_fds=descriptors, cwd=ROOT,
                                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            children.append(helper)
            client.close(); participant.close(); child.close(); source.close()
            epoch, lease, attempt = 'a' * 32, 'b' * 32, 'c' * 32
            grant = dict(session_epoch=epoch, epoch='1' * 32, generation='2' * 32, index=slot+2,
                         sector_macro='sector_a', token='3' * 32, incarnation='4' * 32)
            receipt = Receipt(epoch, 1, 1, 1, attempt, 'checkpoint-' + 'd' * 32, 'e' * 64, 10)
            claim = encode_load_claim(HonestClientLoadClaim(receipt, 'f' * 32, True, True))
            cfg = dict(version=1, claim=claim.decode(), epoch=epoch, handle=1, lease=lease,
                       udp_peer=list(engine.getsockname()), udp_next_id=1, deadline=time.monotonic()+25,
                       controller_timeout=8, client_process=identity(lua.pid),
                       client_authority=dict(lease='5'*32, attempt='6'*32, grant=grant, fixture_slot=slot, timeout=1))
            parent.sendall(json.dumps(cfg).encode()+b'\n')
            self.assertEqual(line(server), claim)
            server.sendall(json.dumps(dict(version=1, kind='accepted', attempt_id=attempt)).encode()+b'\n')
            self.assertEqual(json.loads(line(parent)), {'event':'active'})
            command = dict(version=1, kind='participant_command', epoch=epoch,
                           connection_handle=1, request_id=1, operation='resume')
            server.sendall(json.dumps(command).encode()+b'\n')
            raw, peer = engine.recvfrom(1024)
            self.assertEqual(raw, f'CMD|{lease}|{epoch}|1|resume'.encode())
            engine.sendto(f'RECEIPT|{lease}|{epoch}|1|resume|confirmed'.encode(), peer)
            self.assertEqual(json.loads(line(server)), dict(command, kind='participant_receipt', status='confirmed'))
            samples = []
            for request_id in range(1, 40):
                request = dict(version=1, kind='authority_motion_pull', connection_handle=1, session_epoch=epoch,
                               incarnation=grant['incarnation'], request_id=request_id, grant=grant)
                server.sendall(json.dumps(request).encode()+b'\n')
                answer = json.loads(line(server))
                self.assertEqual(answer['kind'], 'authority_motion_result')
                if answer['sample'] is not None:
                    samples.append(answer['sample'])
                    if latest and len(samples) == 1:
                        # The fake clock advances ten times faster than wall time.
                        # A pull-driven sampler would lose its velocity baseline.
                        time.sleep(.25)
                if len(samples) == 2: break
                time.sleep(.02)
            self.assertEqual(len(samples), 2)
            self.assertEqual([sample['index'] for sample in samples], [slot+2, slot+2])
            self.assertIsNone(samples[0]['velocity'])
            self.assertAlmostEqual(samples[1]['velocity']['x'], 1.0, places=5)
            if latest:
                self.assertGreater(samples[1]['source_time'] - samples[0]['source_time'], 1)
                self.assertEqual([sample['sequence'] for sample in samples], [1, 2])
            self.assertEqual(samples[1]['orientation'], dict(yaw=.1, pitch=.2, roll=.3))
            parent.sendall(b'{"command":"stop"}\n')
            self.assertEqual(json.loads(line(parent)), {'event':'stopped'})
            self.assertEqual(helper.wait(timeout=3), 0)
        finally:
            for sock in sockets:
                sock.close()
            for process in reversed(children):
                if process.poll() is None: process.terminate()
                try: process.communicate(timeout=3)
                except subprocess.TimeoutExpired: process.kill(); process.communicate(timeout=3)


if __name__ == '__main__':
    unittest.main()
