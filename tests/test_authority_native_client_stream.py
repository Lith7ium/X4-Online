"""Bounded source queue and real playback worker; no X4 process is started."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
import authority_native_client_playback as playback
from authority_native_client_stream import LiveSourceInput
from tests import test_authority_native_client_playback as existing


def source(**limits):
    return LiveSourceInput(epoch=playback.EPOCH, index=1318, sector_macro=playback.SECTOR, **limits)


def sample(sequence=17, source_time=421.2, **changes):
    value = dict(version=1, epoch=playback.EPOCH, generation='9'*32, index=1318,
                 sequence=sequence, sector_macro=playback.SECTOR, source_time=source_time,
                 x=1.25, y=2, z=3, velocity=None)
    value.update(changes)
    return value


class SourceInputTests(unittest.TestCase):
    def test_ready_detachment_acceptance_and_explicit_eof(self):
        stream = source()
        initial = dict(x=0, y=0, z=0)
        stream._ready(initial)
        initial['x'] = 999
        received = stream.wait_ready(.1)
        received['x'] = 888
        self.assertEqual(stream.wait_ready(.1)['x'], 0)
        value = sample()
        self.assertTrue(stream.accept_motion(value, False))
        value['x'] = 900
        value2 = sample(23, 421.45, velocity=dict(x=2, y=0, z=0))
        stream.submit(value2, received_at=time.monotonic())
        value2['velocity']['x'] = 900
        stream.finish()
        arguments = dict(guard=lambda: True, abort=threading.Event(), deadline=time.monotonic()+1)
        first, _ = stream._next(**arguments)
        second, _ = stream._next(**arguments)
        self.assertEqual(first['x'], 1.25)
        self.assertIsNone(first['velocity'])
        self.assertEqual(second['velocity']['x'], 2)
        self.assertIsNone(stream._next(**arguments))
        with self.assertRaises(AttributeError):
            stream.identity = ('different', 1, 'frame')
        with self.assertRaisesRegex(ValueError, 'invalid_eof'):
            stream.finish()

    def test_wrong_identity_numbers_receipts_regression_and_overflow_are_sticky(self):
        cases = [dict(epoch='0'*32), dict(index=1), dict(sector_macro='other'),
                 dict(x=float('nan')), dict(source_time=float('inf'))]
        for change in cases:
            with self.subTest(change=change):
                stream = source(); stream._ready({})
                with self.assertRaises(ValueError):
                    stream.accept_motion(sample(**change), False)
                with self.assertRaises(ValueError):
                    stream.accept_motion(sample(), False)
        for receipt in (time.monotonic()+60, time.monotonic()-60, float('nan')):
            stream = source(); stream._ready({})
            with self.assertRaisesRegex(ValueError, 'invalid_receipt'):
                stream.submit(sample(), received_at=receipt)
        for change in (dict(sequence=17), dict(source_time=421.2), dict(generation='8'*32)):
            stream = source(); stream._ready({}); stream.accept_motion(sample(), False)
            value = sample(23, 421.45); value.update(change)
            with self.assertRaisesRegex(ValueError, 'regressed'):
                stream.accept_motion(value, False)
        stream = source(capacity=1); stream._ready({}); stream.accept_motion(sample(), False)
        with self.assertRaisesRegex(ValueError, 'overflow'):
            stream.accept_motion(sample(23, 421.45), False)
        stream = source(max_samples=2); stream._ready({})
        arguments = dict(guard=lambda: True, abort=threading.Event(), deadline=time.monotonic()+1)
        for sequence in (1, 2):
            stream.accept_motion(sample(sequence, 400+sequence), False); stream._next(**arguments)
        with self.assertRaisesRegex(ValueError, 'limit_exceeded'):
            stream.accept_motion(sample(3, 403), False)

    def test_bad_lifecycle_stale_consume_and_cooperative_wait(self):
        for operation in ('not_ready', 'despawn', 'eof', 'failure'):
            stream = source()
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                if operation == 'not_ready': stream.accept_motion(sample(), False)
                elif operation == 'despawn': stream.accept_motion(sample(), True)
                elif operation == 'eof': stream.finish()
                else: stream.fail(); stream.wait_ready(.1)
        stream = source(receipt_max_age=.01); stream._ready({}); stream.accept_motion(sample(), False)
        time.sleep(.02)
        with self.assertRaisesRegex(ValueError, 'invalid_receipt'):
            stream._next(guard=lambda: True, abort=threading.Event(), deadline=time.monotonic()+1)
        stream = source(); stream._ready({})
        abort, errors = threading.Event(), []
        checks = Mock(return_value=True)
        def consume():
            try: stream._next(guard=checks, abort=abort, deadline=time.monotonic()+1)
            except RuntimeError as error: errors.append(error)
        thread = threading.Thread(target=consume)
        thread.start(); time.sleep(.07); abort.set(); thread.join(.3)
        self.assertFalse(thread.is_alive())
        self.assertGreaterEqual(checks.call_count, 2)
        self.assertEqual(str(errors[0]), 'stream_consumer_fenced')


class WorkerStreamTests(unittest.TestCase):
    def exercise(self, *, producer_failure=False, first_offset=False, late_failure=False, ipc_failure=False):
        fixtures = existing.PlaybackTests()
        stream = source()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            controller = fixtures.controller(root, driver=stream)
            packets, events, producer_errors = [], [], []
            producer_done = threading.Event()
            controller.log.write_bytes(fixtures.records().splitlines(keepends=True)[0])
            class FakeIPC:
                def __init__(self, sock, **options): self.guard = options['guard']
                def wait_ready(self): self.guard(); events.append('ready')
                def __call__(self, packet, despawn):
                    self.guard(); packets.append(copy.deepcopy(packet))
                    if ipc_failure and len(packets) == 2:
                        producer_done.wait(1)
                        raise RuntimeError('motion IPC socket failure')
                    if len(packets) == 3: controller.log.write_bytes(fixtures.records())
                    return True
                def stop_remote(self):
                    self.guard(); events.append('stop')
                    controller.log.write_bytes(fixtures.records(stopped=True))
                    return True
                def close(self): events.append('close')
            def produce():
                try:
                    initial = stream.wait_ready(1)
                    self.assertEqual(initial['x'], 0)
                    if producer_failure:
                        time.sleep(.07); stream.fail(); return
                    stream.accept_motion(sample(x=51 if first_offset else 1.25), False)
                    stream.accept_motion(sample(23, 421.45, x=2.5, velocity=dict(x=5, y=-1, z=0)), False)
                    stream.finish()
                except BaseException as error: producer_errors.append(error)
                finally: producer_done.set()
            producer = threading.Thread(target=produce)
            checked = Mock()
            with patch.object(playback, 'ExperimentalParticipantMotionIPC', FakeIPC), \
                    patch.object(playback, 'check_process', checked):
                producer.start(); controller.start(dict(pid=1), {})
                try:
                    deadline = time.monotonic()+4
                    while not controller.stopped.is_set() and controller.thread.is_alive() and time.monotonic()<deadline:
                        time.sleep(.01)
                    producer.join(1)
                    self.assertFalse(producer.is_alive()); self.assertFalse(producer_errors)
                    if producer_failure or first_offset or ipc_failure:
                        controller.thread.join(1)
                        self.assertFalse(controller.thread.is_alive())
                        with self.assertRaisesRegex(RuntimeError, 'worker_failed'): controller.poll()
                        expected = ('stream_producer_failed' if producer_failure else
                                    'ipc_socket_failed' if ipc_failure else 'stream_initial_offset_exceeded')
                        self.assertEqual(controller.evidence['failure_code'], expected)
                        self.assertEqual(len(packets), 2 if ipc_failure else 1)
                        if ipc_failure:
                            partial = controller.evidence['live_source']['samples']
                            self.assertEqual(len(partial), 1)
                            self.assertEqual(partial[0]['delivery_status'], 'dispatch_started')
                            self.assertFalse(controller.evidence['live_source']['input_complete'])
                        self.assertNotIn('stop', events)
                    else:
                        self.assertTrue(controller.poll())
                        evidence = controller.finish()['live_source']
                        self.assertEqual([row['sequence'] for row in packets], [1,2,3])
                        self.assertEqual([row['source_time'] for row in packets[1:]], [421.2,421.45])
                        self.assertEqual([row['x'] for row in packets[1:]], [1.25,2.5])
                        self.assertIsNone(packets[1]['velocity'])
                        self.assertEqual(packets[2]['velocity'], dict(x=5,y=-1,z=0))
                        self.assertTrue(all(row['generation']=='c'*32 for row in packets))
                        self.assertEqual([row['sequence'] for row in evidence['samples']], [17,23])
                        self.assertEqual([row['wire_sequence'] for row in evidence['samples']], [2,3])
                        self.assertEqual(evidence['samples'][0]['source_generation_sha256'], hashlib.sha256(('9'*32).encode()).hexdigest())
                        self.assertFalse(evidence['arbitrary_clock_equivalence_proven'])
                        self.assertEqual(events.count('stop'), 1)
                        self.assertGreater(checked.call_count, 3)
                        self.assertTrue(controller.thread.is_alive())  # Remains owned until native fence.
                        if late_failure:
                            stream.fail()
                            with self.assertRaisesRegex(RuntimeError, 'worker_failed'): controller.finish()
                            self.assertEqual(controller.evidence['failure_code'], 'stream_producer_failed')
                    with self.assertRaisesRegex(RuntimeError, 'native_fence_required'):
                        controller.close(native_stopped=False)
                finally:
                    controller.close(native_stopped=True)
            self.assertFalse(controller.thread.is_alive())
            self.assertEqual(controller.sock.fileno(), -1)
            controller.installation.redact.assert_called_once()

    def test_actual_worker_preserves_source_and_clean_eof_stops(self): self.exercise()
    def test_producer_fault_is_visible_and_requires_fenced_cleanup(self): self.exercise(producer_failure=True)
    def test_actual_first_position_is_rejected_without_alignment(self): self.exercise(first_offset=True)
    def test_late_failure_after_stop_remains_visible_before_worker_release(self): self.exercise(late_failure=True)
    def test_uncertain_ipc_dispatch_retains_original_partial_provenance(self): self.exercise(ipc_failure=True)

    def test_illegal_post_eof_input_prevents_pending_success_publication(self):
        for action in ('submit', 'finish'):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as directory:
                stream = source(); stream._ready({})
                stream.accept_motion(sample(), False)
                stream.accept_motion(sample(23, 421.45), False); stream.finish()
                with self.assertRaises(ValueError):
                    if action == 'submit': stream.accept_motion(sample(24, 421.5), False)
                    else: stream.finish()
                controller = existing.PlaybackTests().controller(Path(directory), driver=stream)
                controller.messages.put_nowait(dict(stopped_confirmed=True))
                with self.assertRaisesRegex(RuntimeError, 'worker_failed'): controller.poll()
                self.assertFalse((Path(directory)/'playback-stopped.json').exists())
                controller.close(native_stopped=True)

    def test_config_accepts_exact_pinned_stream_without_changing_callable_path(self):
        fixtures = existing.PlaybackTests()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'config'; path.write_text(json.dumps(fixtures.config()))
            self.assertEqual(set(playback.read_config(path, fixtures.args(), source())), set(playback.SCRIPT_PINS))
            wrong = LiveSourceInput(epoch='0'*32,index=1318,sector_macro=playback.SECTOR)
            with self.assertRaisesRegex(ValueError, 'foreign_identity'):
                playback.read_config(path, fixtures.args(), wrong)
