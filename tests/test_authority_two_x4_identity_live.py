import importlib.util
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('two_x4_identity_live', ROOT/'tools/dev/authority_two_x4_identity_live.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class TwoX4IdentityTest(unittest.TestCase):
    def make_case(self, root, phase):
        lab = root/'extensions/x4_lan_lab'
        (lab/'ui').mkdir(parents=True)
        (lab/'md').mkdir()
        (lab/'ui/config.lua').write_text('X4LAN_CONFIG = {enabled=false}\n')
        name = 'authority_world_bridge_probe.lua' if phase == 'save' else 'authority_download_load_probe.lua'
        shutil.copyfile(ROOT/'tools/dev'/name, lab/'ui'/name)
        m.inject(root, phase)
        return lab

    def test_fixture_hooks_precede_server_enrollment_and_client_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            server = self.make_case(root/'server', 'save')
            client = self.make_case(root/'client', 'load')
            a = (server/'ui/authority_world_bridge_probe.lua').read_text()
            b = (client/'ui/authority_download_load_probe.lua').read_text()
            self.assertLess(a.index('X4LAN_IDENTITY_READY()'), a.index("net:send('HELLO|"))
            self.assertLess(b.index('X4LAN_IDENTITY_READY()'), b.index('barrier.update()'))
            for lab, phase in ((server, 'save'), (client, 'load')):
                self.assertIn('authority_identity_phase="'+phase+'"', (lab/'ui/config.lua').read_text())
                self.assertTrue((lab/'md/authority_identity_fixture.xml').is_file())
                self.assertIn('authority_identity_probe.lua', (lab/'ui.xml').read_text())

    def test_compare_requires_two_distinct_ordered_expected_objects(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def write(path, phase, ids, names=('alpha 7181', 'beta 7182')):
                tag = '[X4LAN] AUTH_IDENTITY '+phase+' '
                path.write_text(''.join(tag+f'ACTOR {i+1} id={ids[i]} name=Authority identity {names[i]} macro=ship_arg_s_fighter_01_a_macro\n' for i in range(2))+tag+'READY\n')
            server, client = root/'server', root/'client'
            write(server, 'save', (123, 124))
            write(client, 'load', (223, 224))
            self.assertEqual(m.compare_observations(server, client)['runtime_ids_equal'], [False, False])
            write(client, 'load', (223, 223))
            with self.assertRaises(ValueError):
                m.compare_observations(server, client)
            write(client, 'load', (223, 224), ('beta 7182', 'alpha 7181'))
            with self.assertRaises(ValueError):
                m.compare_observations(server, client)

    def test_wrapper_uses_created_output_and_restores_installers(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)/'out'
            args = SimpleNamespace(out=out)
            originals = (m.base.server.install_probe, m.base.client.install_probe,
                         m.base.load.readonly_save_command)
            def checked_output(path):
                if path.exists(): raise ValueError('output already exists')
                return path
            def supervisor(_args):
                for side, phase, ids in (('server', 'save', (123, 124)), ('client', 'load', (223, 224))):
                    p = out/side/'case/home/.config/EgoSoft/X4/45841/engine-output.log'
                    p.parent.mkdir(parents=True)
                    tag = '[X4LAN] AUTH_IDENTITY '+phase+' '
                    p.write_text(''.join(tag+f'ACTOR {i+1} id={ids[i]} name=Authority identity {name} macro=ship_arg_s_fighter_01_a_macro\n' for i, name in enumerate(('alpha 7181', 'beta 7182')))+tag+'READY\n')
                return {'success': True}
            with patch.object(m.base.snapshot, 'output_path', side_effect=checked_output), patch.object(m.base, 'run', side_effect=supervisor):
                result = m.run(args)
            self.assertTrue(result['success'])
            self.assertTrue((out/'result.json').is_file())
            self.assertEqual(originals, (m.base.server.install_probe, m.base.client.install_probe,
                                         m.base.load.readonly_save_command))

if __name__ == '__main__':
    unittest.main()
