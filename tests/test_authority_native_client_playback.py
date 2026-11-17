"""Focused pinned-config, real local UDP and readback tests; never start X4."""
import copy
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
import authority_native_client_playback as subject
import authority_client_native as native


class PlaybackTests(unittest.TestCase):
    def args(self):
        return SimpleNamespace(archived_identity_fixture=None, archived_identity_fixture_sha256=None,
                               expected_content_sha256=None)

    def config(self):
        scripts = {}
        for name, pin in subject.SCRIPT_PINS.items():
            path = ROOT/('src/authority/md/checkpoint_marker.xml' if name == 'authority_checkpoint_marker.xml' else 'tools/dev/'+name)
            scripts[name] = dict(path=str(path), sha256=pin)
        return dict(version=1, fixture='recovery_enh_870', checkpoint_sha256=subject.SAVE_SHA,
                    registry_status=list(subject.STATUS), content_sha256=subject.CONTENT_SHA, scripts=scripts)

    def records(self, *, stopped=False):
        common = dict(version=1, epoch=subject.EPOCH, index=1318, sector=subject.SECTOR)
        def row(kind, **fields):
            return subject.TAG+kind.encode()+b' '+b' '.join(
                (key+'='+str(value)).encode() for key, value in {**common, **fields}.items())+b'\n'
        initial = row('INITIAL', source_sequence=1, local_time=1, game_time=10, x=0, y=0, z=0)
        fields = dict(report=1, samples=3, observations=3, readbacks=2, source_sequence=3,
            phase='frozen', local_time=2, game_time=11, actual_x=1, actual_y=0, actual_z=0,
            target_x=1, target_y=0, target_z=0, error=0)
        result = initial+row('SUMMARY', **fields)
        if stopped:
            result += row('STOPPED', **fields, uncertain=0, drained=1)
        return result

    def controller(self, root, *, driver=None):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('127.0.0.1', 0))
        settings = dict(lease='a'*32, attempt='b'*32, generation='c'*32)
        installation = SimpleNamespace(redact=Mock())
        return subject.Playback(sock, settings, installation, 'd'*32, {}, subject.MARKER,
            driver, time.monotonic()+10, root/'log', root, [])

    def test_strict_pinned_config_default_and_conflicts(self):
        self.assertIsNone(subject.read_config(None, self.args(), None))
        with self.assertRaisesRegex(ValueError, 'config_required'):
            subject.read_config(None, self.args(), lambda initial: [])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'config'
            config = self.config()
            path.write_text(json.dumps(config))
            scripts = subject.read_config(path, self.args(), lambda initial: [])
            self.assertEqual(set(scripts), set(subject.SCRIPT_PINS))
            with self.assertRaisesRegex(ValueError, 'python_driver'):
                subject.read_config(path, self.args(), None)
            for field, value in (('extra', True), ('version', True), ('checkpoint_sha256', '0'*64),
                                 ('registry_status', ['ready', subject.EPOCH, 4, subject.STATUS[3]])):
                bad = copy.deepcopy(config); bad[field] = value
                path.write_text(json.dumps(bad))
                with self.subTest(field=field), self.assertRaises(ValueError):
                    subject.read_config(path, self.args(), lambda initial: [])
            path.write_text(json.dumps(config))
            args = self.args(); args.expected_content_sha256 = subject.CONTENT_SHA
            with self.assertRaisesRegex(ValueError, 'conflict'):
                subject.read_config(path, args, lambda initial: [])
            bad = copy.deepcopy(config)
            bad['scripts']['authority_ship_registry.xml']['sha256'] = '0'*64
            path.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError, 'scripts'):
                subject.read_config(path, self.args(), lambda initial: [])
            path.write_text('{"version":1,"version":1}')
            with self.assertRaisesRegex(ValueError, 'config'):
                subject.read_config(path, self.args(), lambda initial: [])

    def test_real_installers_combine_marked_registry_and_optional_playback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); case = root/'case'
            profile = case/'home/.config/EgoSoft/X4/45841'
            (profile/'save').mkdir(parents=True)
            ids = ('ego_dlc_boron', 'ego_dlc_mini_01', 'ego_dlc_mini_02', 'ego_dlc_pirate',
                   'ego_dlc_split', 'ego_dlc_terran', 'ego_dlc_timelines', 'ego_dlc_ventures', 'x4_lan_lab')
            (profile/'content.xml').write_text('<?xml version="1.0"?><content>'+''.join(
                '<extension id="'+name+'" enabled="true" />' for name in ids)+'</content>\n')
            self.assertEqual(hashlib.sha256((profile/'content.xml').read_bytes()).hexdigest(), subject.CONTENT_SHA)
            lab = case/'extensions/x4_lan_lab'
            for name in ('ui', 'md', 'native'):
                (lab/name).mkdir(parents=True)
            (lab/'ui/config.lua').write_text('X4LAN_CONFIG = {}\n')
            (lab/'ui/native_gate_snapshot.lua').write_text('old')
            (lab/'md/native_gate_battle.xml').write_text('old')
            ticket = dict(world_epoch='1'*32, connection_handle=1, baseline_id=1, load_generation=1,
                checkpoint_id='checkpoint-'+'2'*32, sha256=subject.SAVE_SHA, attempt_id='3'*32, slot='save_009')
            participant = native.NativeParticipant(SimpleNamespace(), time.monotonic()+10, lambda **kwargs: True)
            library = root/'net.so'; library.write_bytes(b'never loaded')
            participant.server_library = library
            controller = None
            try:
                native.download.install_probe(case, profile, ticket)
                participant.install(case, include_identity=False)
                native.marked.install_marked_load_probe(case)
                bound = SimpleNamespace(offer=SimpleNamespace(sha256=subject.SAVE_SHA, size=26183913), marker=subject.MARKER)
                scripts = {name: Path(record['path']).read_bytes() for name, record in self.config()['scripts'].items()}
                controller = subject.install(case, profile, bound, ticket, participant, scripts,
                    lambda initial: [], time.monotonic()+10, root)
                cfg = (lab/'ui/config.lua').read_text()
                self.assertIn('authority_client_motion_saved_playback_fixture="recovery_enh_870"', cfg)
                self.assertNotIn('authority_client_motion_saved_apply_fixture=', cfg)
                probe = (lab/'ui/authority_download_load_probe.lua').read_text()
                self.assertIn('X4LAN_AUTHORITY_MARKER_READY()', probe)
                self.assertNotIn('X4LAN_IDENTITY_READY', probe)
                self.assertIn('X4LAN_RECOVERED_CLIENT_LOAD_READY', probe)
                self.assertTrue(set(lab/'md'/name for name in subject.SCRIPT_PINS) <= set(controller.paths))
                watch = native.download.ReceiptWatch(None, ticket)
                status = (controller.registry_nonce+'|startup|'+subject.EPOCH+'|10082').encode()
                controller.log.write_bytes(native.download.TAG+watch.expected[0]+b'\nAUTH_MARKER load INSPECTED '+
                    subject.MARKER.encode()+b'\n[X4LAN] AUTH_RECOVERY_REGISTRY '+status+b'\n'+native.download.TAG+watch.expected[1]+b'\n')
                self.assertTrue(controller.verify_registry())
            finally:
                if controller is not None:
                    controller.close(native_stopped=True)
                participant.close()

    def test_parser_rejects_faults_duplicates_wrong_context_and_uncertain_stop(self):
        good = self.records(stopped=True)
        initial, summaries, stopped = subject.parse_records(good)
        self.assertEqual(initial['x'], 0)
        self.assertEqual(len(summaries), 1)
        self.assertEqual(stopped['drained'], '1')
        cases = (good.replace(b'uncertain=0', b'uncertain=1'), good.replace(b'drained=1', b'drained=0'),
            good+good.splitlines(keepends=True)[-1], good.replace(subject.EPOCH.encode(), b'0'*32),
            good.replace(b'actual_x=1', b'actual_x=nan'), good.replace(b'local_time=2', b'local_time=0'),
            good.replace(b'report=1', b'report=2'), good.replace(b' x=0', b' x=0 x=0'),
            good+b'[X4LAN] AUTH_RECOVERED_CLIENT_MOTION ERROR\n', good[:-1])
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ValueError):
                subject.parse_records(data)

    def test_log_identity_and_content_history_are_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); controller = self.controller(root)
            try:
                controller.log.write_bytes(self.records())
                controller.records()
                other = root/'replacement'; other.write_bytes(self.records(stopped=True))
                other.replace(controller.log)
                with self.assertRaisesRegex(ValueError, 'replaced'):
                    controller.records()
            finally:
                controller.close(native_stopped=True)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); controller = self.controller(root)
            try:
                controller.log.write_bytes(self.records())
                controller.records()
                controller.log.write_bytes(b'other log\n')
                with self.assertRaisesRegex(ValueError, 'rewritten'):
                    controller.records()
            finally:
                controller.close(native_stopped=True)

    def test_finite_driver_bounds_and_detaches_values(self):
        initial = subject.parse_records(self.records())[0]
        good = dict(after=.1, x=.5, y=0, z=0, velocity=dict(x=5, y=0, z=0))
        plan = [good, dict(good, after=.2)]
        copied = subject.validate_plan(initial, lambda initial: plan)
        plan[0]['velocity']['x'] = 999
        self.assertEqual(copied[0]['velocity']['x'], 5)
        for bad in ([], [good], [dict(good, after=-1), good], [dict(good, x=100), good],
                    [dict(good, after=float('nan')), good], [good]*65):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                subject.validate_plan(initial, lambda initial: bad)

    def test_pause_refuses_active_worker_and_cleanup_requires_native_fence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); controller = self.controller(root)
            with self.assertRaisesRegex(RuntimeError, 'requires_playback_stopped'):
                controller.before_pause()
            with self.assertRaisesRegex(RuntimeError, 'native_fence_required'):
                controller.close(native_stopped=False)
            self.assertFalse(controller.sock.fileno() == -1)
            controller.close(native_stopped=True)
            self.assertTrue(controller.evidence['worker_joined'])
            controller.installation.redact.assert_called_once()

    def test_only_live_appends_are_retryable_not_fault_or_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); controller = self.controller(root)
            try:
                initial = self.records().splitlines(keepends=True)[0]
                controller.log.write_bytes(initial)
                controller.records()
                with controller.log.open('ab') as stream:
                    stream.write(b'[X4LAN] AUTH_CLIENT_PLAYBACK SUM')
                with self.assertRaises(subject.PlaybackLogPending):
                    controller.records()
                controller.log.write_bytes(initial+b'[X4LAN] AUTH_RECOVERED_CLIENT_MOTION ERROR')
                with self.assertRaisesRegex(ValueError, 'faulted'):
                    controller.records()
            finally:
                controller.close(native_stopped=True)

    def test_failed_ready_is_reported_and_worker_cleanup_waits_for_native_fence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); controller = self.controller(root, driver=lambda initial: [])
            peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            peer.connect(controller.sock.getsockname())
            try:
                peer.send(b'foreign ready')
                with patch.object(subject, 'check_process'), patch.object(subject, 'socket_owner', return_value=True):
                    controller.start(dict(pid=1, start_ticks=2, exe_dev=3, exe_ino=4), {})
                    controller.thread.join(2)
                self.assertFalse(controller.thread.is_alive())
                with self.assertRaisesRegex(RuntimeError, 'worker_failed'):
                    controller.poll()
                self.assertEqual(controller.evidence['failure_phase'], 'ready')
                self.assertEqual(controller.evidence['failure_type'], 'ValueError')
                self.assertFalse((root/'playback-stopped.json').exists())
                with self.assertRaisesRegex(RuntimeError, 'native_fence_required'):
                    controller.close(native_stopped=False)
                with self.assertRaisesRegex(RuntimeError, 'worker_failed'):
                    controller.close(native_stopped=True)
                self.assertTrue(controller.evidence['worker_joined'])
            finally:
                peer.close(); controller.sock.close()

    def test_real_udp_worker_enrollment_path_stop_and_main_thread_polling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            driver_threads = []
            def driver(initial):
                driver_threads.append(threading.get_ident())
                return [dict(after=seconds, x=seconds, y=0, z=0, velocity=dict(x=1, y=0, z=0))
                        for seconds in (.02, .04)]
            controller = self.controller(root, driver=driver)
            controller.log.write_bytes(self.records().splitlines(keepends=True)[0])
            peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            peer.settimeout(5)
            peer.connect(controller.sock.getsockname())
            process = dict(pid=123, start_ticks=456, exe_dev=7, exe_ino=8)
            captured = []
            packets, peer_errors = [], []
            def respond():
                try:
                    peer.send(b'R|'+b'a'*32+b'|'+b'b'*32+b'|READY|'+subject.EPOCH.encode()+b'|'+b'c'*32)
                    for index in range(3):
                        packet = peer.recv(769).split(b'|'); packets.append(packet)
                        self.assertEqual(packet[3], b'BIND')
                        peer.send(b'|'.join([b'R', packet[1], packet[2], b'BOUND', *packet[4:11]]))
                    controller.log.write_bytes(self.records())
                    packet = peer.recv(769).split(b'|')
                    self.assertEqual(packet[3], b'STOP')
                    peer.send(b'|'.join([b'R', packet[1], packet[2], b'STOPPED', *packet[4:]]))
                    time.sleep(.03)
                    with controller.log.open('ab') as stream:
                        final = self.records(stopped=True).splitlines(keepends=True)[-1]
                        stream.write(final[:-1]); stream.flush()
                        time.sleep(.03); stream.write(b'\n')
                except BaseException as error:
                    peer_errors.append(error)
            thread = threading.Thread(target=respond)
            with patch.object(subject, 'check_process', side_effect=lambda value: captured.append(dict(value))), \
                    patch.object(subject, 'socket_owner', return_value=True):
                thread.start()
                controller.start(process, {})
                process['pid'] = 999  # The worker retains its own immutable snapshot.
                polls = 0
                try:
                    deadline = time.monotonic()+6
                    while not controller.stopped.is_set() and time.monotonic() < deadline:
                        controller.poll(); polls += 1; time.sleep(.02)
                    self.assertTrue(controller.poll())
                    self.assertGreater(polls, 2)
                    self.assertTrue(controller.finish()['native_position_changed'])
                    published = json.loads((root/'playback-stopped.json').read_text())
                    self.assertTrue(published['stopped_confirmed'])
                    self.assertEqual(published['stopped']['drained'], '1')
                    self.assertEqual(packets[0][11:15], [b'0', b'0', b'0', b'0'])
                    self.assertTrue(all(value['pid'] == 123 for value in captured))
                    self.assertEqual(driver_threads, [controller.thread.ident])
                    self.assertNotEqual(driver_threads[0], threading.get_ident())
                    controller.before_pause()
                finally:
                    controller.close(native_stopped=True)
                    peer.close(); thread.join(2)
            self.assertFalse(peer_errors, peer_errors)
            self.assertFalse(thread.is_alive())
            self.assertTrue(controller.evidence['worker_joined'])


if __name__ == '__main__':
    unittest.main()
