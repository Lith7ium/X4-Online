"""Private wreck-run option and evidence redaction; no native game launch."""
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/dev'))
import linux_gate_live as live  # noqa: E402


class WreckPrivateRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.root.chmod(0o700)
        self.ident = '0123456789abcdef'
        self.file = self.root / 'enrollment'
        self.file.write_text(self.ident + '\n')
        self.file.chmod(0o600)
        self.manifest = {'authority_fixture_scan': True}

    def load(self, path=None, manifest=None):
        return live.load_authority_wreck_id(path or self.file, manifest or self.manifest, self.root, os.getuid())

    def test_explicit_private_file_and_opt_in(self):
        self.assertEqual(self.load(), self.ident)
        self.assertIsNone(live.load_authority_wreck_id(None, {}, self.root, os.getuid()))
        with self.assertRaisesRegex(ValueError, 'requires the authority fixture scan'):
            self.load(manifest={'authority_fixture_scan': False})
        self.root.chmod(0o755)
        with self.assertRaisesRegex(ValueError, '0700'):
            self.load()
        self.root.chmod(0o700)
        self.file.chmod(0o644)
        with self.assertRaisesRegex(ValueError, '0600'):
            self.load()

    def test_rejects_symlinks_fifo_noncanonical_and_zero(self):
        link = self.root/'link'; link.symlink_to(self.file)
        with self.assertRaisesRegex(ValueError, 'cannot open'):
            self.load(path=link)
        fifo = self.root/'pipe'; os.mkfifo(fifo, 0o600)
        with self.assertRaisesRegex(ValueError, 'regular file'):
            self.load(path=fifo)
        for data in ('0'*16, self.ident.upper(), ' '+self.ident, self.ident+'\n\n',
                     self.ident+'0', self.ident[:15], 'x'*40):
            with self.subTest(data=data):
                self.file.write_text(data)
                with self.assertRaisesRegex(ValueError, '16-hex'):
                    self.load()
        self.file.write_text(self.ident)
        runs = self.root/'runs'; runs.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'ordinary runs'):
            self.load()

    def test_private_config_cleanup_and_failed_cleanup_safe_export(self):
        config = self.root/'config.lua'; config.write_text('X4LAN_CONFIG.enabled = true\n')
        config.chmod(0o644)
        live.append_authority_wreck_config(config, self.load())
        self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)
        self.assertIn(self.ident, config.read_text())
        # If write cleanup fails, the case still contains the private field;
        # evidence export must independently redact it even for a scan-only run.
        with mock.patch.object(Path, 'write_text', side_effect=OSError('injected failure')):
            with self.assertRaises(OSError):
                live.cleanup_private_config(config)
        self.assertIn(self.ident, config.read_text())
        run = self.root/'run'; case = run/'case1'; profile = case/'home/profile'
        profile.mkdir(parents=True)
        (profile/'engine-output.log').write_text('[X4LAN] NATIVE_GATE harmless\n')
        target = case/'extensions/x4_lan_lab/ui/config.lua'; target.parent.mkdir(parents=True)
        target.write_text(config.read_text())
        with mock.patch.object(live, 'validate_evidence', return_value={}):
            live.collect_run_evidence(run, [1], [(case, profile)], 60, {'stride': 1}, True)
        exported = run/'client1/installed/x4_lan_lab-config.lua'
        self.assertNotIn(self.ident, exported.read_text())
        self.assertIn('X4LAN_CONFIG.enabled = true', exported.read_text())
        live.cleanup_private_config(config)
        self.assertNotIn(self.ident, config.read_text())
        self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)

    def test_ambiguous_private_field_removes_stale_export_and_refuses(self):
        source = self.root/'source'; destination = self.root/'export'
        for partial in (f'X4LAN_CONFIG.native_gate_authority_wreck_saved = "{self.ident}',
                        'X4LAN_CONFIG.native_gate_authority_wreck_saved =\n"'+self.ident+'"\n',
                        'prefix X4LAN_CONFIG.native_gate_authority_wreck_saved = "'+self.ident+'"\n'):
            with self.subTest(partial=partial):
                source.write_text(partial); destination.write_text('old')
                with self.assertRaisesRegex(ValueError, 'safely redact'):
                    live.retain_wire_safe_config(source, destination)
                self.assertFalse(destination.exists())

    def test_identity_is_redacted_from_result_or_error_text(self):
        text = 'fatal:' + self.ident + ' again=' + self.ident
        self.assertNotIn(self.ident, live.redact_wreck_output(text, self.ident))
        self.assertEqual(live.redact_wreck_output(text, None), text)
        numeric = '1234567890123456'
        encoded = live.redacted_wreck_json({'id': int(numeric), 'nested': [numeric]}, numeric)
        self.assertNotIn(numeric, encoded)
        self.assertEqual(json.loads(encoded), {'id': '[private]', 'nested': ['[private]']})

    def test_identity_refused_in_bundle_config(self):
        config=self.root/'extension/x4_lan_lab/ui/config.lua';config.parent.mkdir(parents=True)
        config.write_text(f'X4LAN_CONFIG.native_gate_authority_wreck_saved = "{self.ident}"\n')
        with self.assertRaisesRegex(ValueError, 'individual run'):
            live.validate_authority_scan_bundle(self.root, {'authority_fixture_scan': False})


if __name__ == '__main__':
    unittest.main()
