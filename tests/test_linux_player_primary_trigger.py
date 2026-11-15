"""Focused native adapter/closure/receipt tests; no native game execution."""
import hashlib
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest
from unittest import mock

import linux_player_primary_trigger as primary
import linux_primary_trigger_bundle as bundle

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'src/native/engine/linux'


class PrimaryTriggerTests(unittest.TestCase):
    def options(self):
        return dict(player_primary_trigger_experiment=True, worker_dispatch=True,
                    player_startup_phases='v1-t40', player_ui_session_frames=180,
                    independent_keyboard_frames=180)

    def test_options_and_immutable_environment_default(self):
        self.assertFalse(primary.enabled({}))
        self.assertTrue(primary.enabled(self.options()))
        for key, value in [('worker_dispatch', False), ('player_primary_trigger_experiment', 1),
                           ('player_ui_session_frames', 179), ('player_ui_session_frames', 901),
                           ('player_startup_phases', None), ('independent_keyboard_frames', 181)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                primary.enabled(dict(self.options(), **{key: value}))
        env = {'X4_DEV_PRIMARY_TRIGGER': 'unsafe', 'KEEP': '1'}
        self.assertEqual(primary.environment(env, False), {'KEEP': '1'})
        self.assertEqual(primary.environment(env, True), {'X4_DEV_PRIMARY_TRIGGER': 'script-v1', 'KEEP': '1'})

    def test_actual_adapter_and_existing_callers(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ('test_gate_player_primary_trigger', 'test_player_physics_network',
                         'test_stock_keyboard_replay_adapter'):
                binary = Path(directory) / name
                subprocess.run(['cc', '-UNDEBUG', '-std=gnu11', '-O2' if name == 'test_gate_player_primary_trigger' else '-O0', '-Wall', '-Wextra', '-Werror',
                                *(['-Wno-unused-function'] if name == 'test_stock_keyboard_replay_adapter' else []),
                                '-I', str(NATIVE.parent), str(NATIVE / (name + '.c')), '-lm', '-o', str(binary)], check=True, timeout=30)
                cases = ['independent_view_ready_ok', 'independent_slot1', 'independent_slot2',
                         'independent_empty', 'independent_p2_failure'] if name == 'test_stock_keyboard_replay_adapter' else [None]
                for case in cases:
                    result = subprocess.run([str(binary)] + ([case] if case else []), capture_output=True,
                                            text=True, check=True, timeout=10)
                if name == 'test_gate_player_primary_trigger':
                    self.assertIn('20 refusals', result.stdout)
                    self.assertIn('tick=70 worker=77 script=1', result.stderr)
                    self.assertIn('tick=76 worker=77 script=0', result.stderr)

    def test_exact_sequence_hash_worker_burst_and_raw_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stderr'
            original = [f'{primary.PREFIX}v=1 tick={tick} worker=77 script={int(70 <= tick < 76)} p1=1 p2=1 firing1=0 firing2=0 terminate_only=1\n'
                        for tick in range(40, 220)]
            physics = {'pass': True, 'frames': [dict(tick=tick, worker_thread=77) for tick in range(40, 220)]}
            def proof(rows):
                path.write_text(''.join(rows))
                physics['stderr_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
                return primary.collect(path, physics, self.options())
            self.assertTrue(proof(original)['pass'])
            for rows in (original[:-1], original + original[:1], original[::-1],
                         [line.replace('worker=77', 'worker=78') for line in original],
                         [line.replace('script=1', 'script=0') for line in original],
                         [line.replace('p1=1', 'p1=0') for line in original]):
                with self.subTest(first=rows[0]):
                    result = proof(rows)
                    self.assertFalse(result['pass'])
                    self.assertEqual(len(result['raw_receipts']), len(rows))
            proof(original)
            physics['stderr_sha256'] = '0' * 64
            self.assertFalse(primary.collect(path, physics, self.options())['pass'])
            self.assertFalse(primary.collect(path, physics, {})['pass'])

    def test_source_closure_sealed_and_previous_version_preserved(self):
        self.assertEqual(len(bundle.source_paths(ROOT)), len(bundle.SOURCES))
        self.assertTrue(set(primary.SOURCES) <= set(bundle.SOURCES))
        with mock.patch.object(bundle.previous, 'validate_bundle', return_value='legacy') as previous:
            self.assertEqual(bundle.validate_bundle(ROOT, {'view_query_source_version': 18}, False), 'legacy')
            previous.assert_called_once()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = primary.SOURCES + ('tools/dev/linux_primary_trigger_bundle.py',)
            inventory = {}
            for name in names:
                path = root / 'source-receipts' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((ROOT / name).read_bytes())
                inventory['source-receipts/' + name] = hashlib.sha256(path.read_bytes()).hexdigest()
            helper = root / primary.HELPERS[0]
            helper.write_bytes((ROOT / 'tools/dev' / helper.name).read_bytes())
            inventory[helper.name] = hashlib.sha256(helper.read_bytes()).hexdigest()
            manifest = dict(self.options(), view_query_source_version=19, files=inventory)
            with mock.patch.object(bundle, 'SOURCES', names), mock.patch.object(bundle, 'HELPERS', primary.HELPERS), \
                    mock.patch.object(bundle.previous, 'validate_bundle', return_value=True):
                self.assertTrue(bundle.validate_bundle(root, manifest, True))
                (root / 'source-receipts' / names[0]).write_text('changed')
                with self.assertRaisesRegex(ValueError, 'changed primary trigger source'):
                    bundle.validate_bundle(root, manifest, True)

    def test_runner_wiring_and_native_pin_shapes(self):
        live = (ROOT / 'tools/dev/linux_gate_live.py').read_text()
        self.assertIn("b.add_argument('--player-primary-trigger-experiment'", live)
        self.assertIn('primary_trigger.environment(env, primary_trigger_enabled, primary_trigger.human_enabled(manifest))', live)
        self.assertIn('primary_trigger.collect(', live)
        source = (NATIVE / 'gate_player_primary_trigger.h').read_text()
        pins = re.findall(r'\{"primary-[^"]+", (0x[0-9a-f]+), ([0-9]+), "([0-9a-f]+)"\}', source)
        self.assertEqual(len(pins), 13)
        self.assertTrue(all(len(sha) == 64 for _, _, sha in pins))
