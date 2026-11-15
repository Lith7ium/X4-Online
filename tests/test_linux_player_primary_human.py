"""Downstream primary wire/replay checks; no game execution."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import linux_player_primary_trigger as primary
from linux_player_network_evidence import decode_record
import linux_human_primary_bundle as bundle

ROOT = Path(__file__).resolve().parents[1]


class HumanPrimaryTest(unittest.TestCase):
    def options(self):
        return dict(player_primary_human=True, player_primary_capture=True,
                    player_cursor_active_flight=True, worker_dispatch=True,
                    player_startup_phases='v1-t40', player_ui_session_frames=180,
                    independent_keyboard_frames=180)

    def test_native_record_replay_and_controller_wants(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ('test_stock_keyboard_primary', 'test_gate_player_primary_trigger'):
                executable = Path(directory) / name
                subprocess.run(['cc', '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
                                '-I', str(ROOT / 'src/native/engine'),
                                str(ROOT / 'src/native/engine/linux' / (name + '.c')),
                                '-o', str(executable)], check=True, timeout=120)
                subprocess.run([str(executable)], stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE, check=True, timeout=20)

    def test_mode_and_wire_admission(self):
        self.assertTrue(primary.enabled(self.options()))
        primary.validate_local_mode(self.options(), False)
        with self.assertRaisesRegex(ValueError, 'remote capability'):
            primary.validate_local_mode(self.options(), True)
        for key, value in [('player_primary_trigger_experiment', True), ('player_primary_capture', False),
                           ('worker_dispatch', False), ('player_cursor_active_flight', False),
                           ('player_ui_session_frames', 901), ('player_primary_human', 1)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                primary.enabled(dict(self.options(), **{key: value}))
        self.assertEqual(primary.environment({}, True, True)['X4_DEV_PRIMARY_TRIGGER'], 'human-v1')
        row = bytearray(43); row[0] = 3; row[1] = 3 | 16; row[2] = 38
        self.assertEqual(decode_record(row.hex(), 40, 0, allow_cursor=True, allow_primary=True), 0)
        for flags, admitted in ((3 | 16, False), (3 | 32, True), (16, True)):
            row[1] = flags
            with self.assertRaises(ValueError):
                decode_record(row.hex(), 40, 0, allow_cursor=True, allow_primary=admitted)

    def test_receipts_bind_both_delayed_records_and_final_release(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stderr'
            records = {'1': [], '2': []}; lines = []
            for tick in range(40, 220):
                wants = [int(44 <= tick < 48), int(47 <= tick < 53)]
                for slot in (1, 2):
                    row = bytearray(43); row[0] = 3; row[1] = 3 | (16 if wants[slot-1] else 0)
                    row[2:4] = (tick-2).to_bytes(2, 'little'); records[str(slot)].append(row.hex())
                lines.append(f'{primary.HUMAN_PREFIX}v=1 tick={tick} worker=77 want1={wants[0]} want2={wants[1]} p1=2 p2=2 firing1=0 firing2=0 terminate_only=1\n')
            physics = {'pass': True, 'frames': [dict(tick=t, worker_thread=77) for t in range(40, 220)], 'slot_records': records}
            def proof(rows):
                path.write_text(''.join(rows)); physics['stderr_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
                return primary.collect(path, physics, self.options())
            self.assertTrue(proof(lines)['pass'])
            for rows in (lines[:-1], lines[::-1], [x.replace('worker=77','worker=78') for x in lines],
                         [x.replace('want1=1','want1=0') for x in lines]):
                self.assertFalse(proof(rows)['pass'])
            records['2'][-1] = records['2'][-1][:2] + '13' + records['2'][-1][4:]
            self.assertFalse(proof(lines)['pass'])

    def test_source_closure_and_legacy_admission(self):
        self.assertEqual(len(bundle.source_paths(ROOT)), len(bundle.SOURCES))
        self.assertIn('src/native/engine/linux/test_stock_keyboard_primary.c', bundle.SOURCES)
        with self.assertRaisesRegex(ValueError, 'source version 21'):
            bundle.validate_bundle(ROOT, dict(self.options(), view_query_source_version=20), True)


    def test_actual_bundle_path_human_mode_and_source_receipts(self):
        import linux_gate_live as live
        from test_linux_ui_render_lease_evidence import RenderLeaseAdmissionTests
        original = live.main
        freeze_sources = live.freeze_source_receipts
        active = False

        def freeze(repo, output, sources):
            if active:
                provider = Path(output) / 'semaphore_observer' / bundle.PROVIDER
                provider.parent.mkdir(parents=True, exist_ok=True)
                if not provider.exists():
                    provider.write_bytes(b'fixture semaphore provider')
            return freeze_sources(repo, output, sources)

        def build(arguments):
            nonlocal active
            active = '--player-ui-seat-correction' in arguments
            if active:
                cleaned = []
                skip = False
                for token in arguments:
                    if skip:
                        skip = False
                        continue
                    if token in ('--independent-keyboard-frames', '--player-ui-overlay-callbacks'):
                        skip = True
                        continue
                    if token != '--player-ui-overlay-probe':
                        cleaned.append(token)
                arguments = cleaned + ['--player-ui-session-frames', '180', '--ticks', '220',
                    '--player-startup-phases', 'v1-t40', '--player-cursor-active-flight',
                    '--semaphore-observer', '--worker-dispatch', '--serial-pathing', '--mass-traffic', 'sync', '--player-primary-capture', '--player-primary-human']
            result = original(arguments)
            output = Path(arguments[arguments.index('--out') + 1])
            manifest = json.loads((output / 'manifest.json').read_text())
            self.assertIs(manifest['player_primary_human'], active)
            self.assertIs(manifest['player_primary_capture'], active)
            self.assertIs(manifest['player_primary_trigger_experiment'], False)
            self.assertEqual(manifest['view_query_source_version'], 21)
            self.assertFalse(bundle.validate_bundle(output, manifest, True))
            for source in ('src/native/engine/linux/test_stock_keyboard_primary.c',
                           'src/native/engine/linux/player_primary_human.md'):
                receipt = 'source-receipts/' + source
                self.assertEqual(manifest['files'][receipt], live.sha(output / receipt))
            return result

        with mock.patch.object(live, 'main', side_effect=build), \
                mock.patch.object(live, 'freeze_source_receipts', side_effect=freeze):
            RenderLeaseAdmissionTests().test_mocked_bundle_forwarding_config_helper_and_source_inventory()
