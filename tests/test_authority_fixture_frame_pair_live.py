"""Offline receipt, isolation and wiring checks; this does not launch X4."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
import authority_fixture_frame_pair_live as frame

NONCE = 'a' * 32


def sample_log():
    lines = ['[X4LAN] AUTH_RECOVERY PAUSED']
    for slot in (1, 2):
        info = frame.comparison.FIXTURE_SECTORS[slot]
        lines.append(f'[X4LAN] AUTH_FIXTURE_FRAME_READ ROW {NONCE} {slot} ship SHP-1 ship_arg_s_fighter_01_a_macro player {info["sector"]} 10 0 0 0')
        for (code, (macro, owner)), pos in zip(info['stations'].items(), ((0,0,0),(2000,0,0),(0,2000,0))):
            lines.append(f'[X4LAN] AUTH_FIXTURE_FRAME_READ ROW {NONCE} {slot} station {code} {macro} {owner} {info["sector"]} 10 {pos[0]} {pos[1]} {pos[2]}')
        lines.append(f'[X4LAN] AUTH_FIXTURE_FRAME_READ DONE {NONCE} {slot} 3 10')
    return ('\n'.join(lines) + '\n').encode()


class ReceiptTests(unittest.TestCase):
    def test_lua_owner_correlates_both_sectors_and_fences_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory) / 'fake-x4.so'
            subprocess.run(['cc', '-shared', '-fPIC', '-O2',
                            str(ROOT/'tests/fixtures/authority_fixture_frame_fake_x4.c'), '-o', str(library)],
                           check=True, capture_output=True)
            for mode in ('normal', 'paused', 'clock', 'marker', 'reentrant', 'duplicate', 'bad_done'):
                with self.subTest(mode=mode):
                    completed = subprocess.run(['luajit', 'tests/authority_fixture_frame_read.lua', mode], cwd=ROOT,
                                               env=dict(os.environ, LD_PRELOAD=str(library)),
                                               check=True, capture_output=True, text=True, timeout=5)
                    if mode == 'normal':
                        raw = b'[X4LAN] AUTH_RECOVERY PAUSED\n' + completed.stdout.encode()
                        observed = frame.parse_log(raw, 'b' * 32, partial=False)
                        self.assertEqual([len(observed[slot]) for slot in (1, 2)], [3, 3])

    def test_ordered_two_sector_rows_feed_existing_comparator(self):
        rows = frame.parse_log(sample_log(), NONCE, partial=False)
        result = frame.comparison.compare(rows, copy.deepcopy(rows))
        self.assertEqual([sector['slot'] for sector in result['sectors']], [1, 2])
        self.assertFalse(result['universal_frame_identity_proven'])

    def test_partial_and_invalid_receipts_fail_closed(self):
        raw = sample_log()
        self.assertIsNone(frame.parse_log(raw.rsplit(b'\n', 2)[0] + b'\n', NONCE, partial=True))
        variants = [raw.replace(b'AUTH_RECOVERY PAUSED', b'not paused'),
                    raw.replace(b' DONE ' + NONCE.encode() + b' 1 3', b' DONE ' + NONCE.encode() + b' 1 4'),
                    raw.replace(b' ROW ' + NONCE.encode() + b' 2 ship', b' ROW ' + NONCE.encode() + b' 1 ship'),
                    raw.replace(b'ship_arg_s_fighter_01_a_macro player', b'other_macro player', 1),
                    raw.replace(b'ship_arg_s_fighter_01_a_macro player', b'ship_arg_s_fighter_01_a_macro xenon', 1),
                    raw.replace(b' 10 2000 0 0', b' nan 2000 0 0', 1),
                    raw + b'[X4LAN] AUTH_FIXTURE_FRAME_READ ERROR late\n',
                    raw.replace(NONCE.encode(), b'b' * 32, 1)]
        for value in variants:
            with self.subTest(value=value[:100]), self.assertRaises(ValueError):
                frame.parse_log(value, NONCE, partial=False)

    def test_xml_is_read_only_and_sector_queries_are_bounded(self):
        root = ET.parse(ROOT / 'tools/dev/authority_fixture_frame_read.xml').getroot()
        self.assertEqual(root.attrib['name'], 'X4AuthorityFixtureFrameRead')
        self.assertEqual(len(root.findall('.//find_station')), 1)
        self.assertEqual(root.findall('.//set_object_velocity'), [])
        self.assertEqual(root.findall('.//create_ship'), [])
        self.assertEqual(root.findall('.//save_game'), [])


class InstallAndPairTests(unittest.TestCase):
    def test_private_scope_manifest_pins_frame_runner(self):
        launcher = ROOT / '.local/authority_private_fixture_frame_scope_20261117.py'
        manifest = ROOT / '.local/private-fixture-frame-scope-candidate-manifest-20261117-01.json'
        if not launcher.is_file() or not manifest.is_file():
            self.skipTest('private scope candidate is not part of the tracked source tree')
        spec = importlib.util.spec_from_file_location('fixture_frame_scope', launcher)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        sources = module.reviewed_sources(manifest)
        self.assertEqual(sources['runner.py'], (ROOT/'tools/dev/authority_fixture_frame_pair_live.py').read_bytes())
        self.assertIn(b'two_sequential_native_reads', sources['coordinator.py'])

    def test_installer_uses_existing_recovery_update_and_protectable_files(self):
        with tempfile.TemporaryDirectory() as temp:
            case = Path(temp) / 'case'; profile = case / 'profile'
            lab = case / 'extensions/x4_lan_lab'; ui = lab / 'ui'; md = lab / 'md'
            ui.mkdir(parents=True); md.mkdir(); profile.mkdir()
            (ui/'authority_checkpoint_marker_probe.lua').write_text('X4AuthorityCheckpointMarker')
            (ui/'authority_recovery_probe.lua').write_text(" if state=='done' then return end\n")
            (lab/'ui.xml').write_text('    <file name="ui/authority_recovery_probe.lua" />\n')
            config = ui/'config.lua'; config.write_text('X4LAN_CONFIG = {}\n')
            scripts = {name:b'saved script' for name in frame.fixture_source.SAVED_SCRIPTS}
            result, paths = frame.install(case, profile, scripts, nonce=NONCE,
                                          original_install=lambda *_:config)
            self.assertEqual(result, config)
            self.assertTrue(all(path.is_file() and path.is_relative_to(case) for path in paths))
            self.assertIn('X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK', (ui/'authority_recovery_probe.lua').read_text())
            self.assertIn('X4AuthorityPlayerFixtureMarker', (ui/'authority_checkpoint_marker_probe.lua').read_text())
            self.assertIn('authority_fixture_frame_read.lua', (lab/'ui.xml').read_text())
            self.assertIn('authority_frame_nonce="' + NONCE, config.read_text())

    def test_pair_refuses_failed_cleanup_and_reused_process(self):
        rows = frame.parse_log(sample_log(), NONCE, partial=False)
        def child(pid):
            return {'success':True, 'owned_processes_remaining':[], 'checkpoint_id':frame.SOURCE_ID,
                    'sha256':frame.SOURCE_SHA, 'native_frame_read_observed':True,
                    'experiment':{'stations':copy.deepcopy(rows), 'x4_identity':[pid, 123]}}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); source=root/'source';source.mkdir()
            for name, children, expected in [('good',[child(10),child(11)],True),
                                              ('same',[child(10),child(10)],False),
                                              ('unclean',[{**child(10),'owned_processes_remaining':[10]}],False)]:
                args=SimpleNamespace(store=source,out=root/name)
                with patch.object(frame,'SOURCE',source), \
                     patch.object(frame.recovery.snapshot,'output_path',side_effect=lambda path:path), \
                     patch.object(frame,'run_one',side_effect=children) as invoke:
                    result=frame.run(args)
                self.assertEqual(result['success'], expected)
                self.assertEqual(invoke.call_count, len(children))
                self.assertEqual(json.loads((root/name/'result.json').read_text())['success'], expected)


if __name__ == '__main__': unittest.main()
