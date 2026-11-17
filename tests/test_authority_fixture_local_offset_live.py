"""Offline recovery wiring and evidence checks, without starting X4."""
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/dev'))
import authority_fixture_local_offset_live as live


class LocalOffsetLiveTest(unittest.TestCase):
    nonce = 'a' * 32

    def test_output_inside_source_is_refused_before_recovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            server = Path(temporary) / 'server'
            store = server / 'checkpoints'
            store.mkdir(parents=True)
            output = server / 'case' / 'unexpected'
            arguments = SimpleNamespace(slot=2, store=store, out=output)
            with patch.object(live.frames, 'SOURCE', store), \
                 patch.object(live.recovery.snapshot, 'output_path', side_effect=Path), \
                 patch.object(live.recovery, 'run') as recovery_run:
                with self.assertRaisesRegex(ValueError, 'outside the fixture source'):
                    live.run(arguments)
            self.assertFalse(output.exists())
            recovery_run.assert_not_called()

    def log(self, *, delta='0', x='110', index='3', prefix=b''):
        return (prefix + b'[X4LAN] AUTH_RECOVERY PAUSED\n' +
            f'[X4LAN] AUTH_FIXTURE_LOCAL_OFFSET WRITE_ENTERED {self.nonce}\n'.encode() +
            f'[X4LAN] AUTH_FIXTURE_LOCAL_OFFSET OBSERVED {self.nonce} {index} 100 20 30 {x} 20 30 {delta}\n'.encode())

    def test_result_requires_matching_offset_and_order(self):
        result = live.parse_log(self.log(), self.nonce, 1, partial=False)
        self.assertEqual(result['index'], 3)
        self.assertEqual(result['after'], [110, 20, 30])
        cases = (self.log(x='100', delta='10'), self.log(x='nan'), self.log(index='4'),
                 self.log(delta='-1'), self.log(prefix=b'[X4LAN] AUTH_RECOVERY PAUSED\n'),
                 self.log() + b'[X4LAN] AUTH_FIXTURE_LOCAL_OFFSET ERROR\n',
                 self.log() + self.log(), self.log().replace(b'AUTH_RECOVERY PAUSED', b'not-paused'))
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                live.parse_log(bad, self.nonce, 1, partial=False)
        incomplete = self.log().split(b'[X4LAN] AUTH_FIXTURE_LOCAL_OFFSET OBSERVED')[0]
        self.assertIsNone(live.parse_log(incomplete, self.nonce, 1, partial=True))
        with self.assertRaises(ValueError):
            live.parse_log(incomplete, self.nonce, 1, partial=False)

    def test_private_installer_wires_existing_recovery_owner(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = Path(temporary) / 'case'
            lab = case / 'extensions/x4_lan_lab'
            ui, md = lab / 'ui', lab / 'md'
            ui.mkdir(parents=True)
            md.mkdir()
            profile = case / 'home/.config/EgoSoft/X4/45841'
            (profile / 'save').mkdir(parents=True)
            scripts = {name: ('saved-' + name).encode() for name in live.fixture_source.SAVED_SCRIPTS}

            def original_install(_case, _profile):
                (ui / 'authority_checkpoint_marker_probe.lua').write_bytes(
                    (ROOT / 'tools/dev/authority_checkpoint_marker_probe.lua').read_bytes())
                (ui / 'authority_recovery_probe.lua').write_bytes(
                    (ROOT / 'tools/dev/authority_recovery_probe.lua').read_bytes())
                (lab / 'ui.xml').write_text('<ui>\n    <file name="ui/authority_recovery_probe.lua" />\n</ui>\n')
                config = ui / 'config.lua'
                config.write_text('X4LAN_CONFIG = {enabled=false}\n')
                return config

            config, protected = live.install(case, profile, scripts, nonce=self.nonce, slot=1,
                                             original_install=original_install)
            self.assertIn('authority_local_offset_enabled=true', config.read_text())
            self.assertIn('X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK()', (ui / 'authority_recovery_probe.lua').read_text())
            self.assertEqual((ui / 'authority_recovery_probe.lua').read_text().count("SetScript('onUpdate'"), 1)
            self.assertNotIn('X4AuthorityCheckpointMarker', (ui / 'authority_checkpoint_marker_probe.lua').read_text())
            self.assertIn('X4AuthorityPlayerFixtureMarker', (ui / 'authority_checkpoint_marker_probe.lua').read_text())
            self.assertIn('X4LAN_FIXTURE_LOCAL_OFFSET = M', (ui / 'authority_fixture_local_offset.lua').read_text())
            self.assertIn('authority_fixture_local_offset_bootstrap.lua', (lab / 'ui.xml').read_text())
            self.assertTrue(all(path.is_relative_to(case) and path.is_file() for path in protected))
            for name, content in scripts.items():
                self.assertEqual((md / name).read_bytes(), content)


if __name__ == '__main__':
    unittest.main()
