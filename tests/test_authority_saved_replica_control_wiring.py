"""Explicit replica control wiring with disposable overlays; no native X4."""
import copy
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
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev'), str(ROOT / 'tests')]
from authority import client_motion_overlay as overlay
from authority import windows_fixture_session as windows
import authority_recovered_server_client as client
import authority_recovered_client_motion_install as linux_install
import authority_tcp_native_worker as worker
import test_authority_client_motion_overlay as shared_fixture
import test_authority_recovered_client_motion_install as linux_fixture
import test_authority_recovered_playback_worker_wiring as playback_fixture
import test_authority_recovered_setter_worker_wiring as worker_fixture
import test_authority_windows_fixture_overlay as windows_fixture

FIXTURE = overlay.RECOVERY_APPLY_FIXTURE
CONTROL = 'saved_replica_control_fixture'


class ReplicaControlWiring(unittest.TestCase):
    def settings(self):
        return {**shared_fixture.playback_settings(), CONTROL: FIXTURE}

    def test_control_requires_matching_playback_and_fixed_registry_actor(self):
        settings = self.settings()
        status = ('ready', overlay.RECOVERY_APPLY_EPOCH, 10082, 'a'*64)
        self.assertEqual(overlay.validate_motion_settings(status, settings).indices, (1318,))
        cases = [(settings | {CONTROL: value}, status) for value in (None, False, 'other')]
        without_playback = dict(settings)
        del without_playback['saved_playback_fixture']
        cases += [(without_playback, status), (settings | {'index': 1317}, status),
                  (settings | {'indices': [1318]}, status),
                  (settings, ('ready', 'c'*32, 10082, 'a'*64))]
        for config, registry in cases:
            with self.subTest(config=config, registry=registry), self.assertRaises(ValueError):
                overlay.validate_motion_settings(registry, config)

    def test_control_is_default_off_and_preserves_playback_source_order(self):
        settings = shared_fixture.playback_settings()
        modules, md_names = overlay.select_motion_sources(settings)
        self.assertNotIn(overlay.RECOVERY_REPLICA_CONTROL_MODULE, modules)
        self.assertNotIn(overlay.RECOVERY_REPLICA_CONTROL_MD, md_names)
        modules, md_names = overlay.select_motion_sources(self.settings())
        self.assertEqual(modules[-4:], (overlay.RECOVERY_APPLY_MODULE, overlay.RECOVERY_PLAYBACK_MODULE,
                                      overlay.RECOVERY_REPLICA_CONTROL_MODULE, overlay.MODULES[-1]))
        self.assertEqual(md_names, (*overlay.MD, overlay.RECOVERY_REPLICA_CONTROL_MD))

    def test_generated_playback_without_control_remains_default_off(self):
        linux = linux_fixture.Install()
        linux.setUp()
        self.addCleanup(linux.doCleanups)
        linux.prepare_playback()
        linux.install()
        windows_overlay = windows_fixture.FixtureOverlayTest()
        windows_overlay.setUp()
        self.addCleanup(windows_overlay.doCleanups)
        windows_overlay.install(
            registry_status=('ready', overlay.RECOVERY_APPLY_EPOCH, 10082, '9'*64),
            registry_nonce='6'*32, motion_settings=shared_fixture.playback_settings())
        for lab in (linux.lab, windows_overlay.view/'extensions/x4_lan_lab'):
            with self.subTest(lab=lab):
                self.assertFalse((lab/'ui/saved_replica_control.lua').exists())
                self.assertFalse((lab/'md/authority_saved_replica_control.xml').exists())
                self.assertNotIn('saved_replica_control', (lab/'ui.xml').read_text())
                self.assertNotIn('saved_replica_control', (lab/'ui/config.lua').read_text())
                self.assertNotIn('saved_replica_control_fixture=',
                                 (lab/'ui/authority_two_x4_participant_probe.lua').read_text())

    def test_windows_request_and_detached_settings_forward_both_options(self):
        request = dict(generation='3'*32, indices=[1318], timeout=5,
                       saved_playback_fixture=FIXTURE, saved_replica_control_fixture=FIXTURE)
        before = copy.deepcopy(request)
        windows.validate_motion_request(request, 30)
        bound = SimpleNamespace(offer=SimpleNamespace(world_epoch='a'*32, attempt_id='b'*32,
                                                     checkpoint_id='checkpoint-'+'c'*32))
        settings = windows._motion_settings(request,
            ('ready', overlay.RECOVERY_APPLY_EPOCH, 10082, 'a'*64), bound,
            SimpleNamespace(lease='d'*32), 'e'*32, 23456)
        self.assertEqual(request, before)
        self.assertEqual(settings[CONTROL], FIXTURE)
        self.assertEqual(settings['saved_playback_fixture'], FIXTURE)
        self.assertEqual(settings['index'], 1318)
        self.assertNotIn('indices', settings)
        missing = dict(request)
        del missing['saved_playback_fixture']
        for altered in (missing, request | {CONTROL: False}, request | {CONTROL: 'other'},
                        request | {'indices': [1317]}, request | {'indices': [1318, 1319]}):
            with self.subTest(request=altered), self.assertRaises(ValueError):
                windows.validate_motion_request(altered, 30)

    def test_linux_request_forwards_control_to_real_overlay_and_worker(self):
        fixture = playback_fixture.prepare_pinned_fixture(self)
        import time
        participant = client.ServerClient(time.monotonic()+5, fixture.case, keep_worker=True)
        self.addCleanup(participant.cleanup_diagnostic)
        request = dict(indices=[1318], generation='3'*32, timeout=2,
                       saved_playback_fixture=FIXTURE, saved_replica_control_fixture=FIXTURE)
        before = copy.deepcopy(request)
        paths = participant.prepare_client_motion(fixture.case, fixture.profile, fixture.status, request,
                                                 dict(world_epoch='e'*32, attempt_id='f'*32))
        self.assertEqual(request, before)
        self.assertEqual(participant.motion_worker_config[CONTROL], FIXTURE)
        self.assertIn(fixture.ui/'saved_replica_control.lua', paths)
        self.check_overlay(fixture.lab)
        participant.redact()

    def test_linux_missing_or_symlink_control_source_preserves_overlay(self):
        fixture = linux_fixture.Install()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.prepare_playback()
        fixture.settings[CONTROL] = FIXTURE
        original = {path.relative_to(fixture.lab): path.read_bytes()
                    for path in fixture.lab.rglob('*') if path.is_file()}
        source_names = (overlay.RECOVERY_REPLICA_CONTROL_MODULE[0],
                        'tools/dev/'+overlay.RECOVERY_REPLICA_CONTROL_MD)
        with tempfile.TemporaryDirectory() as temporary:
            source_root = Path(temporary)
            for name in source_names:
                source = source_root/name
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes((ROOT/name).read_bytes())
            for name in source_names:
                source = source_root/name
                data = source.read_bytes()
                for mode in ('missing', 'symlink'):
                    source.unlink()
                    if mode == 'symlink':
                        source.symlink_to(ROOT/name)
                    with self.subTest(source=name, mode=mode), patch.object(linux_install, 'ROOT', source_root):
                        with self.assertRaisesRegex(ValueError, 'saved replica control overlay source'):
                            fixture.install()
                        actual = {path.relative_to(fixture.lab): path.read_bytes()
                                  for path in fixture.lab.rglob('*') if path.is_file()}
                        self.assertEqual(actual, original)
                    if source.is_symlink():
                        source.unlink()
                    source.write_bytes(data)

    def test_linux_request_without_playback_fails_before_install_or_socket(self):
        import time
        participant = client.ServerClient(time.monotonic()+5, Path('/unused'), keep_worker=True)
        self.addCleanup(participant.cleanup_diagnostic)
        with patch('authority_recovered_client_motion_install.install') as install:
            with self.assertRaises(ValueError):
                participant.prepare_client_motion(Path('/unused'), Path('/unused'),
                    ('ready', overlay.RECOVERY_APPLY_EPOCH, 10082, 'a'*64),
                    dict(indices=[1318], generation='3'*32, timeout=2, saved_replica_control_fixture=FIXTURE),
                    dict(world_epoch='e'*32, attempt_id='f'*32))
            install.assert_not_called()
        self.assertIsNone(participant.motion_sock)

    def test_worker_config_preserves_control_and_rejects_missing_playback(self):
        config = worker_fixture.worker_config()
        config['motion'].update(saved_playback_fixture=FIXTURE, saved_replica_control_fixture=FIXTURE)
        with patch.object(worker, 'check_process'):
            self.assertEqual(worker.config_value(json.dumps(config).encode())[0], config)
            invalid = copy.deepcopy(config)
            del invalid['motion']['saved_playback_fixture']
            cases = [invalid]
            for change in ({CONTROL: False}, {CONTROL: 'other'}, {'epoch': 'c'*32}):
                altered = copy.deepcopy(config)
                altered['motion'].update(change)
                cases.append(altered)
            for altered in cases:
                with self.subTest(config=altered), self.assertRaises(ValueError):
                    worker.config_value(json.dumps(altered).encode())

    def test_generated_windows_overlay_installs_control_dependencies_and_pause_gate(self):
        fixture = windows_fixture.FixtureOverlayTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.install(registry_status=('ready', overlay.RECOVERY_APPLY_EPOCH, 10082, '9'*64),
                        registry_nonce='6'*32, motion_settings=self.settings())
        self.check_overlay(fixture.view/'extensions/x4_lan_lab')

    def check_overlay(self, lab):
        paths = [item.attrib['name'] for item in ET.parse(lab/'ui.xml').iter('file')]
        dependencies = ('saved_motion_apply.lua', 'motion_playback.lua', 'saved_replica_control.lua',
                        'authority_recovered_client_motion.lua')
        for before, after in zip(dependencies, dependencies[1:]):
            self.assertLess(paths.index('ui/'+before), paths.index('ui/'+after))
        self.assertEqual((lab/'ui/saved_replica_control.lua').read_bytes(),
                         (ROOT/'src/authority/lua/saved_replica_control.lua').read_bytes())
        self.assertEqual((lab/'md/authority_saved_replica_control.xml').read_bytes(),
                         (ROOT/'tools/dev/authority_saved_replica_control.xml').read_bytes())
        for name in overlay.MD:
            self.assertEqual((lab/'md'/name).read_bytes(), (ROOT/'tools/dev'/name).read_bytes())
        ET.parse(lab/'md/authority_saved_replica_control.xml')
        config = (lab/'ui/config.lua').read_text()
        self.assertIn('authority_client_motion_saved_replica_control_fixture="recovery_enh_870"', config)
        control_path = lab/'ui/authority_two_x4_participant_probe.lua'
        control = control_path.read_text()
        self.assertIn('saved_replica_control_fixture=cfg.authority_client_motion_saved_replica_control_fixture', control)
        self.assertLess(control.index('client playback STOP required before pause'),
                        control.index("assert(state:submit('isolated-client'"))
        for name in paths:
            compiled = subprocess.run(['luajit', '-b', str(lab/name), '/dev/null'], cwd=ROOT,
                                      capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout+compiled.stderr)
        with tempfile.TemporaryDirectory() as temporary:
            library = Path(temporary)/'abi.so'
            subprocess.run(['cc', '-O2', '-shared', '-fPIC', 'tests/fixtures/saved_motion_apply_abi.c',
                            '-o', str(library)], cwd=ROOT, check=True, capture_output=True)
            for mode in ('ready', 'stopped'):
                subprocess.run(['luajit', 'tests/authority_recovered_client_playback_pause.lua',
                                str(control_path), mode], cwd=ROOT, check=True, capture_output=True,
                               timeout=5, env=dict(os.environ, LD_PRELOAD=str(library)))


if __name__ == '__main__':
    unittest.main()
