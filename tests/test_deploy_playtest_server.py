"""Pure deployment-plan checks; no SSH or remote command is executed."""
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('deploy_playtest_server',
    ROOT / 'tools/deploy_playtest_server.py')
deploy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deploy)


class DeploymentPlanTests(unittest.TestCase):
    def setUp(self):
        self.values = {'ssh_target': 'root@192.0.2.10', 'user': 'x4server',
                       'folder': '/home/x4server/lockstep-lobby', 'service': 'x4mp-lobby',
                       'server': {'host': '192.0.2.10', 'port': 47000},
                       'manifest': {'commit': 'a' * 40}, 'name_time': '20261120-161500'}

    def test_default_plan_quotes_remote_paths_and_sets_private_extract_umask(self):
        plan = deploy.deployment_plan(**self.values)
        self.assertEqual(plan['ssh'], ['ssh', '-o', 'BatchMode=yes', '--', 'root@192.0.2.10'])
        self.assertTrue(plan['extract'].startswith('umask 077; mkdir -p -- '))
        self.assertIn('tar xzf - --no-same-owner --no-same-permissions -C ', plan['extract'])
        self.assertIn('chmod 600 -- ', plan['remote'])
        self.assertIn('ufw allow 47001/tcp', plan['remote'])
        self.assertIn('User=x4server\n', plan['remote'])
        self.assertNotIn('\nUNIT\n', deploy.UNIT.format(user='x4server',
            dir='/home/x4server/lockstep-lobby'))

    def test_invalid_inputs_refuse_before_deployment(self):
        cases = ({'manifest': {'commit': 'short'}}, {'ssh_target': '-option'},
                 {'user': 'Bad Name'}, {'folder': '/home/invalid path'},
                 {'service': 'Bad Name'}, {'server': {'host': '192.0.2.10', 'port': 65535}},
                 {'server': {'host': '192.0.2.10', 'port': True}},
                 {'server': {'host': 'not-an-ip', 'port': 47000}})
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ValueError):
                deploy.deployment_plan(**{**self.values, **change})

    def test_archive_keeps_server_key_private_and_refuses_links(self):
        with tempfile.TemporaryDirectory() as folder:
            kit = Path(folder)
            (kit / 'repo').mkdir()
            (kit / 'overlay').mkdir()
            (kit / 'server.json').write_text('{"key":"test"}')
            with tarfile.open(fileobj=io.BytesIO(deploy.pack(kit)), mode='r:gz') as archive:
                self.assertEqual(archive.getmember('server.json').mode, 0o600)
            (kit / 'repo/link').symlink_to('elsewhere')
            with self.assertRaises(ValueError):
                deploy.pack(kit)


if __name__ == '__main__':
    unittest.main()
