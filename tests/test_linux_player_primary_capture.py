"""Capture adapter, strict receipts and opt-in sealing; no native game."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import linux_player_primary_capture as capture
import linux_primary_capture_bundle as bundle

ROOT = Path(__file__).resolve().parents[1]


class PrimaryCaptureTests(unittest.TestCase):
    def options(self):
        return dict(player_primary_capture=True, worker_dispatch=True,
                    player_startup_phases='v1-t40', player_ui_session_frames=180,
                    independent_keyboard_frames=180, player_cursor_active_flight=True)

    def test_actual_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'adapter'
            subprocess.run(['cc', '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-Wno-unused-function', str(ROOT / 'src/native/engine/linux/test_gate_player_primary_capture.c'),
                            '-lm', '-o', str(binary)], check=True, timeout=30)
            result = subprocess.run([str(binary)], capture_output=True, text=True, check=True, timeout=10)
            self.assertIn('24 terminal refusals', result.stdout)
            self.assertIn('native_forward=0', result.stderr)
            diagnostics = [line for line in result.stderr.splitlines() if ' terminal reason=' in line]
            self.assertEqual(len(diagnostics), 24)
            self.assertTrue(all(len(line) <= 116 for line in diagnostics))
            self.assertIn('X4LAN PRIMARY_CAPTURE terminal reason=fire_capture_tree', diagnostics)
            snapshots = [line for line in result.stderr.splitlines() if ' tree_v=1 ' in line]
            summaries = [line for line in snapshots if 'reason=registration ' not in line]
            for reason in ('census', 'owner', 'unknown_handler', 'duplicate', 'missing'):
                self.assertTrue(any('reason=' + reason + ' ' in line for line in summaries))
            self.assertTrue(any(' selected=0000000000000028 shown=0000000000000020 omitted=0000000000000008' in line for line in summaries))
            emitted = 0
            for line in snapshots:
                self.assertLessEqual(len(line), 511)
                if 'reason=registration ' in line:
                    emitted += 1
                    self.assertLessEqual(emitted, 32)
                    self.assertIn(' node=', line)
                    self.assertIn(' handler=', line)
                else:
                    emitted = 0
            self.assertTrue(any('handler=0000000000abcdef' in line for line in snapshots))

    def test_explicit_environment_and_admission(self):
        self.assertEqual(capture.environment({'X4_DEV_PRIMARY_CAPTURE': 'capture-v1'}, False), {})
        self.assertEqual(capture.environment({}, True), {'X4_DEV_PRIMARY_CAPTURE': 'capture-v1'})
        self.assertTrue(capture.enabled(self.options()))
        for delta in ({'worker_dispatch': False}, {'player_primary_trigger_experiment': True},
                      {'player_cursor_active_flight': False}, {'player_ui_session_frames': 901},
                      {'player_primary_capture': 1}):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                capture.enabled(self.options() | delta)

    def test_complete_order_hash_and_raw_predicates(self):
        rows = [f'{capture.PREFIX}v=1 stage=held tick={tick} slot=1 focused=1 context=1 held=0 edges=0 banks_neutral=1 wire_fire=0 native_forward=0\n'
                for tick in range(38, 218)]
        edge = f'{capture.PREFIX}v=1 stage=edge tick=38 index=0 family=0 kind=2 id=17 raw=38d1b717 held=1 primary=1 focused=1 context=1 native_forward=0\n'
        physics = dict(pass_=True, frames=[{'tick': tick} for tick in range(40, 220)]) | {'pass': True}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stderr'
            def proof(lines, options=None):
                path.write_text(''.join(lines))
                physics['stderr_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
                return capture.collect(path, physics, self.options() if options is None else options, 1)
            self.assertTrue(proof(rows)['pass'])
            valid_edge = [edge, rows[0].replace('edges=0', 'edges=1')] + rows[1:]
            self.assertTrue(proof(valid_edge)['pass'])
            for bad in (rows[:-1], rows + rows[:1], rows[::-1],
                        [row.replace('slot=1', 'slot=2') for row in rows],
                        [edge] + rows,
                        [edge.replace('held=1', 'held=0')] + valid_edge[1:],
                        [edge.replace('38d1b717', '7fc00000')] + valid_edge[1:],
                        [edge.replace('id=17', 'id=24')] + valid_edge[1:]):
                with self.subTest(first=bad[0]):
                    result = proof(bad)
                    self.assertFalse(result['pass'])
                    self.assertEqual(len(result['raw_receipts']), len(bad))
            self.assertFalse(proof(rows, {})['pass'])
            proof(rows)
            physics['stderr_sha256'] = '0' * 64
            self.assertFalse(capture.collect(path, physics, self.options(), 1)['pass'])

    def test_runner_wiring(self):
        runner = (ROOT / 'tools/dev/linux_gate_live.py').read_text()
        self.assertIn("b.add_argument('--player-primary-capture'", runner)
        self.assertIn("'player_primary_capture': primary_capture_enabled", runner)
        self.assertIn('primary_capture.environment(env, primary_capture_enabled)', runner)
        self.assertIn('primary_capture.collect(', runner)
        self.assertIn('import linux_human_primary_bundle as semaphore_bundle', runner)

    def test_current_closure_and_old_validation(self):
        self.assertEqual(len(bundle.source_paths(ROOT)), len(bundle.SOURCES))
        self.assertTrue(set(capture.SOURCES) <= set(bundle.SOURCES))
        with mock.patch.object(bundle.previous, 'validate_bundle', return_value='v19'):
            self.assertEqual(bundle.validate_bundle(ROOT, {'view_query_source_version': 19}, True), 'v19')
            with self.assertRaises(ValueError):
                bundle.validate_bundle(ROOT, self.options() | {'view_query_source_version': 19}, True)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {}
            for name in bundle.SOURCES:
                target = root / 'source-receipts' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / name).read_bytes())
                files['source-receipts/' + name] = hashlib.sha256(target.read_bytes()).hexdigest()
            for name in bundle.HELPERS:
                target = root / name
                target.write_bytes((ROOT / 'tools/dev' / name).read_bytes())
                files[name] = hashlib.sha256(target.read_bytes()).hexdigest()
            manifest = self.options() | {'view_query_source_version': 20, 'files': files}
            with mock.patch.object(bundle.previous, 'validate_bundle', return_value=True):
                self.assertTrue(bundle.validate_bundle(root, manifest, True))
                (root / 'linux_player_primary_capture.py').write_text('changed')
                with self.assertRaises(ValueError):
                    bundle.validate_bundle(root, manifest, True)
