"""Exercise the real supervisor option gate without starting X4."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
import authority_recovered_loopback_server as server


class QuickGuardGateTests(unittest.TestCase):
    def run_gate(self, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / 'game'
            (game / 'extensions').mkdir(parents=True)
            auth = root / 'xauthority'
            auth.write_bytes(b'private')
            source = root / 'source/checkpoints'
            source.mkdir(parents=True)
            args = dict(game=game, out=root/'output', store=source, display=':42', timeout=30,
                        seed=1, fixture_overlap=True, diagnostic_overlap=True,
                        fixture_player_source_sectors=['cluster_33_sector001_macro', 'cluster_45_sector001_macro'],
                        fixture_player_source_quick_guards=True, fixture_player_source_latest_cache=True)
            args.update(overrides)
            with patch.object(server.snapshot, 'output_path', side_effect=lambda path:path), \
                 patch.object(server.load, 'local_directory', return_value=source), \
                 patch.object(server, 'CheckpointStore', return_value=SimpleNamespace(directory=source)), \
                 patch.object(server.live, 'sha', return_value=server.live.EXE_SHA), \
                 patch.object(server.live, 'x4_executables', return_value=[]), \
                 patch.object(server.live, 'steam_identity', return_value='steam'), \
                 patch.object(server.shutil, 'which', return_value='/usr/bin/bwrap'), \
                 patch.dict(os.environ, {'XAUTHORITY':str(auth)}), \
                 patch.object(server.snapshot, 'prepare_case', side_effect=RuntimeError('case preparation sentinel')) as prepare:
                result = server.run(SimpleNamespace(**args))
            return result, prepare.call_count

    def test_real_fixture_combination_reaches_case_preparation(self):
        result, calls = self.run_gate()
        self.assertEqual(calls, 1)
        self.assertEqual(result['error'], 'case preparation sentinel')
        self.assertEqual(result['fixture_save_guard']['mode'], 'pinned_metadata_between_digest_boundaries')

    def test_default_mode_stays_strict_and_needs_no_cache(self):
        result, calls = self.run_gate(fixture_player_source_quick_guards=False,
                                      fixture_player_source_latest_cache=False)
        self.assertEqual(calls, 1)
        self.assertNotIn('fixture_save_guard', result)

    def test_quick_mode_refuses_missing_fixture_or_tls(self):
        result, calls = self.run_gate(fixture_player_source_sectors=None,
                                      fixture_player_source_latest_cache=False)
        self.assertEqual(calls, 0)
        self.assertIn('quick guards require', result['error'])
        result, calls = self.run_gate(diagnostic_tls_certificate=Path('/test/cert'),
                                      diagnostic_tls_private_key=Path('/test/key'))
        self.assertEqual(calls, 0)
        self.assertIn('quick guards are limited', result['error'])


if __name__ == '__main__':
    unittest.main()
