"""Local UDP/fake-owner contract tests; no X4 or input event injection."""
from pathlib import Path
import json
import traceback
import socket
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_fixture_client_throttle_ipc as subject
import authority_recovered_loopback_server as runner


class ThrottleIPCTest(unittest.TestCase):
    def setUp(self):
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.sock.bind(('127.0.0.1',0))
        self.peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.peer.bind(('127.0.0.1',0))
        self.peer.connect(self.sock.getsockname());self.peer.settimeout(1)
        self.addCleanup(self.sock.close);self.addCleanup(self.peer.close)
        self.settings=dict(process={'pid':1},lease='a'*32,attempt='b'*32,epoch='c'*32,
                           generation='d'*32,nonce='e'*32,slot=2,guard=lambda:True,
                           running=lambda:True,pump=lambda:None,timeout=3)
        self.suffix='|'.join([self.settings[k] for k in ('lease','attempt','epoch','generation','nonce')]+['2']).encode()
        self.process=patch.object(subject,'check_process');self.process.start();self.addCleanup(self.process.stop)
        self.ownership=patch.object(subject,'socket_owner',return_value=True);self.ownership.start();self.addCleanup(self.ownership.stop)
    def worker(self, *, reply=True, stop_time=b'42.5'):
        self.peer.send(b'READY|'+self.suffix)
        def run():
            self.assertEqual(self.peer.recv(1024),b'GO|'+self.suffix)
            if reply:
                self.peer.send(b'STARTED|'+self.suffix);self.peer.send(b'STOPPED|'+self.suffix+b'|'+stop_time)
        thread=threading.Thread(target=run);thread.start();self.addCleanup(thread.join,1);return thread
    def test_correlated_one_shot(self):
        thread=self.worker();result=subject.pulse(self.sock,**self.settings);thread.join(1)
        self.assertTrue(result['start_acknowledged'] and result['stop_acknowledged'])
        self.assertEqual(result['stop_game_time'],42.5)
        self.assertFalse(result['movement_proven'] or result['human_input_proven'])
    def test_bad_stop_clock_never_confirms(self):
        for value in (b'nan', b'-1', b'1e999', b'', b'1000000000001'):
            with self.subTest(value=value):
                receiver=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); receiver.bind(('127.0.0.1',0))
                peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); peer.connect(receiver.getsockname())
                peer.send(b'READY|'+self.suffix)
                def respond():
                    peer.recv(1024)
                    peer.send(b'STARTED|'+self.suffix)
                    peer.send(b'STOPPED|'+self.suffix+b'|'+value)
                thread=threading.Thread(target=respond);thread.start()
                try:
                    with self.assertRaises(subject.ThrottleUnconfirmed) as caught:
                        subject.pulse(receiver,**self.settings)
                    self.assertTrue(caught.exception.attempted and caught.exception.started)
                    self.assertFalse(caught.exception.stopped)
                    self.assertEqual(caught.exception.phase, 'validating_stopped')
                    self.assertTrue(caught.exception.stopped_phase_datagram_received)
                finally:
                    thread.join(1);receiver.close();peer.close()
    def test_foreign_ready_and_owner_never_dispatch(self):
        self.peer.send(b'READY|foreign')
        with self.assertRaises(subject.ThrottleUnconfirmed) as caught:subject.pulse(self.sock,**self.settings)
        self.assertFalse(caught.exception.attempted)
    def test_after_dispatch_guard_failure_is_explicitly_uncertain(self):
        dispatched=threading.Event()
        self.settings['guard']=lambda:not dispatched.is_set()
        self.peer.send(b'READY|'+self.suffix)
        def peer_after_dispatch():
            self.peer.recv(1024)
            dispatched.set()
        thread=threading.Thread(target=peer_after_dispatch);thread.start();self.addCleanup(thread.join,1)
        with self.assertRaises(subject.ThrottleUnconfirmed) as caught:subject.pulse(self.sock,**self.settings)
        self.assertTrue(caught.exception.attempted)
        self.assertFalse(caught.exception.stopped)
    def test_duplicate_socket_owner_is_refused(self):
        with subject._LOCK:
            subject._OWNERS[self.sock]=True
        try:
            with self.assertRaisesRegex(ValueError,'already owned'):
                subject.pulse(self.sock,**self.settings)
        finally:
            with subject._LOCK: subject._OWNERS.pop(self.sock,None)
    def test_unowned_x4_peer_refuses_before_send(self):
        self.ownership.stop()
        with patch.object(subject,'socket_owner',return_value=False):
            self.peer.send(b'READY|'+self.suffix)
            with self.assertRaises(subject.ThrottleUnconfirmed) as caught:
                subject.pulse(self.sock,**self.settings)
            self.assertFalse(caught.exception.attempted)
    def test_started_packet_then_guard_failure_reports_observation_without_ack(self):
        go_received, started_sent = threading.Event(), threading.Event()
        self.peer.send(b'READY|' + self.suffix)
        def respond():
            self.peer.recv(1024)
            go_received.set()
            self.peer.send(b'STARTED|' + self.suffix)
            started_sent.set()
        thread = threading.Thread(target=respond)
        thread.start()
        self.addCleanup(thread.join, 1)
        # The packet must have been consumed before this guard fails.
        def guard():
            if go_received.is_set():
                if not started_sent.wait(1): raise RuntimeError('test sender stalled')
                return bool(subject.select.select([self.sock], [], [], 0)[0])
            return True
        self.settings['guard'] = guard
        with self.assertRaises(subject.ThrottleUnconfirmed) as caught:
            subject.pulse(self.sock, **self.settings)
        error = caught.exception
        self.assertTrue(error.attempted and error.started_phase_datagram_received)
        self.assertFalse(error.started or error.stopped or error.stopped_phase_datagram_received)
        self.assertEqual((error.phase, error.error_class), ('validating_started', 'runtime_error'))
        self.assertGreaterEqual(error.elapsed_ms, 0)

    def test_started_phase_wrong_packet_exposes_only_fixed_diagnostic(self):
        self.peer.send(b'READY|' + self.suffix)
        def respond():
            self.peer.recv(1024)
            self.peer.send(b'PRIVATE_PACKET_CONTENT')
        thread = threading.Thread(target=respond)
        thread.start()
        self.addCleanup(thread.join, 1)
        with self.assertRaises(subject.ThrottleUnconfirmed) as caught:
            subject.pulse(self.sock, **self.settings)
        error = caught.exception
        self.assertEqual((error.phase, error.error_class), ('validating_started', 'invalid_value'))
        self.assertTrue(error.attempted and error.started_phase_datagram_received)
        self.assertFalse(error.started or error.stopped)
        safe = {'phase':error.phase, 'error_class':error.error_class, 'elapsed_ms':error.elapsed_ms}
        self.assertNotIn('PRIVATE_PACKET_CONTENT', repr(safe))
        self.assertNotIn(self.settings['lease'], repr(safe))

    def test_post_dispatch_timeout_reports_fixed_class(self):
        go_received = threading.Event()
        self.peer.send(b'READY|' + self.suffix)
        def respond():
            self.peer.recv(1024)
            go_received.set()
        thread = threading.Thread(target=respond)
        thread.start()
        self.addCleanup(thread.join, 1)
        original = self.settings['guard']
        def guard():
            if go_received.is_set(): raise TimeoutError('SECRET SHOULD NOT BE EXPORTED')
            return original()
        self.settings['guard'] = guard
        with self.assertRaises(subject.ThrottleUnconfirmed) as caught:
            subject.pulse(self.sock, **self.settings)
        error = caught.exception
        self.assertTrue(error.attempted)
        self.assertFalse(error.started or error.stopped)
        self.assertIn(error.phase, ('sending_go', 'waiting_started'))
        self.assertEqual(error.error_class, 'timeout')
        self.assertNotIn('SECRET', repr((error.phase, error.error_class, error.elapsed_ms)))

    def test_runner_serialization_redacts_actual_ipc_exception(self):
        secret = 'PRIVATE_ERROR_' + self.settings['lease'] + '_' + self.settings['nonce']
        def bad_guard():
            raise RuntimeError(secret)
        self.settings['guard'] = bad_guard
        result = {'success': False, 'fixture_sample_write': {}}
        try:
            subject.pulse(self.sock, **self.settings)
            self.fail('guard error was not reported')
        except subject.ThrottleUnconfirmed as error:
            self.assertEqual(str(error), 'fixture throttle unconfirmed')
            self.assertNotIn(secret, ''.join(traceback.format_exception(error)))
            runner.record_fixture_throttle_uncertainty(result, error)
        result['error'] = 'fixture throttle unconfirmed'
        encoded = json.dumps(result)
        self.assertNotIn(secret, encoded)
        self.assertNotIn(self.settings['lease'], encoded)
        self.assertNotIn(self.settings['nonce'], encoded)
        diagnostic = result['fixture_sample_write']['throttle_uncertain']
        self.assertEqual(diagnostic['phase'], 'waiting_ready')
        self.assertEqual(diagnostic['error_class'], 'runtime_error')
        self.assertFalse(diagnostic['attempted'])
        self.assertFalse(diagnostic['started_phase_datagram_received'])

    def test_runner_refuses_nonfixed_diagnostic_fields(self):
        result = {'fixture_sample_write': {}}
        for field, value in (('phase', self.settings['nonce']),
                             ('error_class', self.settings['lease']),
                             ('elapsed_ms', -1), ('attempted', 'true')):
            error = subject.ThrottleUnconfirmed('ignored secret', attempted=False, started=False, stopped=False)
            setattr(error, field, value)
            with self.subTest(field=field), self.assertRaises(ValueError):
                runner.record_fixture_throttle_uncertainty(result, error)
            self.assertEqual(result, {'fixture_sample_write': {}})
            self.assertEqual(str(error), 'fixture throttle unconfirmed')

    def test_guard_budget_expires_before_queued_started_receipt_is_read(self):
        # Real UDP receiver and valid protocol, with deterministic logical time.
        now = [100.0]
        guards_after_go = [0]
        go_packets = []
        self.peer.send(b'READY|' + self.suffix)
        def guard():
            if subject.select.select([self.peer], [], [], 0)[0]:
                go_packets.append(self.peer.recv(1024))
                self.peer.send(b'STARTED|' + self.suffix)
                self.peer.send(b'STOPPED|' + self.suffix + b'|42.5')
            if go_packets:
                guards_after_go[0] += 1
                if guards_after_go[0] == 3:
                    now[0] += 3.25
            return True
        def owner(*args):
            now[0] += .01
            return True
        self.settings['guard'] = guard
        with patch.object(subject.time, 'monotonic', side_effect=lambda: now[0]), \
                patch.object(subject, 'socket_owner', side_effect=owner):
            with self.assertRaises(subject.ThrottleUnconfirmed) as caught:
                subject.pulse(self.sock, **self.settings)
        error = caught.exception
        self.assertTrue(error.attempted)
        self.assertFalse(error.started or error.stopped or error.started_phase_datagram_received)
        self.assertEqual((error.phase, error.error_class), ('waiting_started', 'timeout'))
        self.assertEqual(go_packets, [b'GO|' + self.suffix])
        self.assertFalse(subject.select.select([self.peer], [], [], 0)[0])
        self.assertEqual(self.sock.recvfrom(769, socket.MSG_PEEK)[0], b'STARTED|' + self.suffix)
        self.assertNotIn(self.sock, subject._OWNERS)
        timing = error.work_timing
        self.assertGreater(timing['external_guard']['calls'], 0)
        self.assertEqual(timing['external_guard']['elapsed_ms'], 3250)
        self.assertGreater(timing['socket_owner']['calls'], 0)
        self.assertGreater(timing['socket_owner']['elapsed_ms'], 0)
        self.assertEqual(timing['pump'], {'calls': 0, 'elapsed_ms': 0})
        result = {'fixture_sample_write': {}}
        runner.record_fixture_throttle_uncertainty(result, error)
        self.assertEqual(result['fixture_sample_write']['throttle_uncertain']['work_timing'], timing)

    def test_pump_budget_is_attributed_on_timeout(self):
        now = [100.0]
        go_packets = []
        self.peer.send(b'READY|' + self.suffix)
        def guard():
            if subject.select.select([self.peer], [], [], 0)[0]:
                go_packets.append(self.peer.recv(1024))
            return True
        def pump():
            now[0] += 3.25
        self.settings.update(guard=guard, pump=pump)
        with patch.object(subject.time, 'monotonic', side_effect=lambda: now[0]):
            with self.assertRaises(subject.ThrottleUnconfirmed) as caught:
                subject.pulse(self.sock, **self.settings)
        error = caught.exception
        self.assertTrue(error.attempted)
        self.assertEqual(go_packets, [b'GO|' + self.suffix])
        self.assertEqual(error.error_class, 'timeout')
        self.assertEqual(error.work_timing['pump'], {'calls': 1, 'elapsed_ms': 3250})
        self.assertEqual(error.work_timing['external_guard']['elapsed_ms'], 0)

    def test_timing_clock_failure_preserves_original_guard_exception(self):
        failed = [False]
        def clock():
            if failed[0]: raise ValueError('observer unavailable')
            return 100.0
        def guard():
            failed[0] = True
            raise RuntimeError('original private guard failure')
        self.settings['guard'] = guard
        with patch.object(subject.time, 'monotonic', side_effect=clock):
            with self.assertRaises(subject.ThrottleUnconfirmed) as caught:
                subject.pulse(self.sock, **self.settings)
        error = caught.exception
        self.assertEqual(error.error_class, 'runtime_error')
        self.assertEqual(error.work_timing['external_guard'], {'calls': 1, 'elapsed_ms': 0})
        self.assertEqual(error.elapsed_ms, 0)
        self.assertFalse(error.attempted)

    def test_runner_refuses_nonfixed_work_timing(self):
        for value in ({'secret': {}},
                      {name: {'calls': True, 'elapsed_ms': 0} for name in subject.TIMING_NAMES},
                      {name: {'calls': 1, 'elapsed_ms': -1} for name in subject.TIMING_NAMES}):
            error = subject.ThrottleUnconfirmed(attempted=False, started=False, stopped=False,
                                                work_timing=value)
            result = {'fixture_sample_write': {}}
            with self.subTest(value=value), self.assertRaises(ValueError):
                runner.record_fixture_throttle_uncertainty(result, error)
            self.assertEqual(result, {'fixture_sample_write': {}})

    def test_driver_path_without_x4(self):
        subprocess.run(['luajit','tests/authority_fixture_client_throttle_driver.lua'],cwd=ROOT,check=True,timeout=10)

if __name__=='__main__':unittest.main()
