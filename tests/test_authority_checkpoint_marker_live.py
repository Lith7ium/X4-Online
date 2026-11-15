import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('marker_live', ROOT/'tools/dev/authority_checkpoint_marker_live.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class MarkerTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_probe_waits_for_receipt_and_client_is_not_given_marker(self):
        for phase, scenario in (('save', 'success'), ('load', 'success'), ('load', 'retry'),
                                ('load', 'timeout'), ('load', 'unanswered')):
            subprocess.run(['luajit', str(ROOT/'tests/authority_checkpoint_marker_peer.lua'), phase, scenario], cwd=ROOT, check=True)

    def test_receipts_require_matching_new_marker(self):
        nonce = 'a'*32
        ticket = dict(world_epoch='epoch', connection_handle=1, baseline_id=1, load_generation=1,
                      checkpoint_id='checkpoint-'+'f'*32, sha256='b'*64, attempt_id='d'*32, slot='save_009')
        server = '[X4LAN] AUTH_MARKER save STORED '+nonce+'\n'
        client = '[X4LAN] AUTH_MARKER load INSPECTED '+nonce+'\n'
        self.assertTrue(m.verify_receipts(server, client, nonce, ticket))
        for bad in (client.replace(nonce, 'c'*32), client+client, '', client+'AUTH_MARKER load ERROR\n'):
            with self.assertRaises(ValueError): m.verify_receipts(server, bad, nonce, ticket)
        with self.assertRaises(ValueError): m.verify_receipts(server, client, nonce, {})

    def test_hooks_fence_both_native_phases_and_keep_marker_out_of_client_config(self):
        for phase in ('save', 'load'):
            with tempfile.TemporaryDirectory() as folder:
                case = Path(folder); lab = case/'extensions/x4_lan_lab'; ui = lab/'ui'
                ui.mkdir(parents=True); (lab/'md').mkdir()
                (ui/'config.lua').write_text('X4LAN_CONFIG = {}\n')
                (lab/'ui.xml').write_text('    <file name="ui/authority_identity_probe.lua" />\n')
                name = 'authority_world_bridge_probe.lua' if phase == 'save' else 'authority_download_load_probe.lua'
                hook = ' if not started and now-loaded_at>=3 then\n' if phase == 'save' else " elseif state=='observing' then\n"
                (ui/name).write_text(hook)
                m.inject(case, phase, 'a'*32)
                self.assertIn('X4LAN_AUTHORITY_MARKER_READY()', (ui/name).read_text())
                self.assertEqual('authority_marker="' in (ui/'config.lua').read_text(), phase == 'save')
                self.assertTrue((lab/'md/authority_checkpoint_marker.xml').is_file())

if __name__ == '__main__': unittest.main()
