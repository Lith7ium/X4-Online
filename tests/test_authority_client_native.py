"""Offline native-client orchestration/receipts and real UDP; never launch X4."""
from contextlib import contextmanager, ExitStack
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
import authority_client_native as native


class NativeClientTests(unittest.TestCase):
    def ticket(self):
        return dict(world_epoch='a'*32, connection_handle=1, baseline_id=1, load_generation=1,
            checkpoint_id='checkpoint-'+'b'*32, sha256=hashlib.sha256(b'save').hexdigest(),
            attempt_id='c'*32, slot='save_009')

    def log_bytes(self):
        watch = native.download.ReceiptWatch(None, self.ticket())
        return (native.download.TAG+watch.expected[0]+b'\nAUTH_MARKER load INSPECTED '+b'd'*32+b'\n'+
                native.download.TAG+watch.expected[1]+b'\n')

    def test_rejected_native_evidence_never_claims_or_enrolls(self):
        ticket = self.ticket()
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory)/'engine-output.log'
            good = self.log_bytes()
            for bad in (good.replace(b'd'*32, b'e'*32), good+b'AUTH_MARKER load ERROR\n',
                        good.replace(b'AUTH_MARKER load INSPECTED '+b'd'*32+b'\n', b'')):
                log.write_bytes(bad)
                owner = SimpleNamespace(poll=lambda: None, load_requested=lambda attempt: self.fail('false load assertion'))
                participant = SimpleNamespace(enroll=lambda *args: self.fail('false enrollment'))
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    native.observe_and_activate(owner, participant, native.download.ReceiptWatch(log, ticket),
                        ticket, 'd'*32, lambda **kwargs: True, lambda: None, {})

    def test_real_udp_receipts_count_only_server_control_and_do_not_reenter_owner(self):
        owner = SimpleNamespace(poll=lambda: self.fail('active controller must not poll owner'))
        participant = native.NativeParticipant(owner, time.monotonic()+5, lambda **kwargs: True)
        peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            participant.loading = False
            participant.server_control = True
            participant.epoch, participant.handle = 'a'*32, 1
            peer.connect(participant.sock.getsockname())
            participant.peer = peer.getsockname()
            executable = Path('/proc/self/exe').stat()
            participant.process = dict(pid=os.getpid(), start_ticks=native.live.start_ticks(os.getpid()),
                exe_dev=executable.st_dev, exe_ino=executable.st_ino)
            def respond():
                data = peer.recv(769)
                peer.send(b'RECEIPT|'+data.split(b'|', 1)[1]+b'|confirmed')
            thread = threading.Thread(target=respond)
            thread.start()
            self.assertTrue(participant.resume((1,)))
            thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(participant.confirmations, {'pause': 0, 'resume': 1})
        finally:
            participant.close()
            peer.close()

    def test_launch_failure_stops_owned_process_before_connection_and_lock_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events = []
            library = root/'net.so'; library.write_bytes(b'library')
            ticket = self.ticket()
            bound = SimpleNamespace(offer=SimpleNamespace(**{k: v for k, v in ticket.items() if k != 'slot'}), marker='d'*32)
            class Owner:
                def request_offer(self): return bound
                def download(self, directory):
                    directory.mkdir(); path = directory/'save.xml.gz'; path.write_bytes(b'save'); return path
                def verify_staged(self, path): pass
                def copy_to_new_slot(self, source, target): target.write_bytes(source.read_bytes())
            @contextmanager
            def connection(**options):
                try: yield Owner()
                finally: events.append('connection_closed')
            def prepare(out, game, home):
                case = out/'case'; profile = case/'home/.config/EgoSoft/X4/45841'
                (profile/'save').mkdir(parents=True)
                (profile/'config.xml').write_text('config'); (profile/'content.xml').write_text('content')
                lab = case/'extensions/x4_lan_lab'
                for name in ('ui', 'md', 'native'): (lab/name).mkdir(parents=True)
                (lab/'ui/config.lua').write_text('X4LAN_CONFIG = {}\n')
                (lab/'ui/native_gate_snapshot.lua').write_text('old')
                (lab/'md/native_gate_battle.xml').write_text('old')
                return case, profile, [], case/'lock'
            def spawn(command, log, processes):
                processes.append([SimpleNamespace(), 1]); events.append('launch_registered')
                raise OSError('PRIVATE launch detail')
            def stop(services, processes, result, errors):
                events.append('native_stopped'); result['owned_cleanup_confirmed'] = True
                return True
            def finish(fd, st, stopped, errors):
                self.assertTrue(stopped); events.append('lock_released')
            args = SimpleNamespace(timeout=10, active_seconds=1, host='host', port=1, fingerprint='0'*64,
                slot=1, keepalive_interval=None, display=':1', seed=1, native_library_sha256=hashlib.sha256(b'library').hexdigest(),
                shared_key_file=root/'key', file_token_file=root/'token', archived_identity_fixture=None,
                archived_identity_fixture_sha256=None, expected_content_sha256=None)
            args.shared_key_file.write_text('a'*64); args.file_token_file.write_text('b'*32)
            out = root/'new'
            environment = (out, root, root/'auth', library, SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid(), pw_name='test'), root, 'steam')
            with ExitStack() as stack:
                for target, name, replacement in (
                    (native, 'validate_environment', lambda args: environment),
                    (native, 'client_connection', connection),
                    (native.snapshot, 'prepare_case', prepare),
                    (native.load, 'readonly_save_command', lambda *args: ['bwrap', '--die-with-parent']),
                    (native.load, 'spawn_owned_gated', spawn),
                    (native.download, 'create_owned_lock', lambda uid, gid, locks: locks.append((1, 2))),
                    (native.download, 'stop_owned_resources', stop),
                    (native.download, 'finish_owned_lock', finish),
                    (native.live, 'steam_identity', lambda *args: 'steam')):
                    stack.enter_context(patch.object(target, name, side_effect=replacement))
                previous = signal.getsignal(signal.SIGINT)
                result = native.run(args)
                self.assertIs(signal.getsignal(signal.SIGINT), previous)
                self.assertFalse(result['success'])
                self.assertEqual(result['failure_phase'], 'launch')
                self.assertEqual(result['error_type'], 'OSError')
                self.assertNotIn('PRIVATE', json.dumps(result))
                self.assertEqual(events, ['launch_registered', 'native_stopped', 'connection_closed', 'lock_released'])
                events.clear()
                @contextmanager
                def failed_connection(**options):
                    raise RuntimeError('tls_startup_failed')
                    yield  # Context entry must fail before the native body starts.
                startup_environment = (root/'startup-failure', *environment[1:])
                with patch.object(native, 'validate_environment', return_value=startup_environment), \
                        patch.object(native, 'client_connection', failed_connection), \
                        patch.object(native.download, 'stop_owned_resources', side_effect=stop) as stop_empty:
                    failed_result = native.run(args)
                self.assertEqual(stop_empty.call_args.args[1], [])
                self.assertEqual(events, ['native_stopped', 'lock_released'])
                self.assertEqual(failed_result['failure_phase'], 'connect')
                self.assertEqual(failed_result['error_code'], 'tls_startup_failed')
                self.assertTrue(failed_result['owned_cleanup_confirmed'])
                self.assertIs(signal.getsignal(signal.SIGINT), previous)


if __name__ == '__main__':
    unittest.main()
