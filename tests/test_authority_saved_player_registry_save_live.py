"""Focused offline checks for the opt-in registered fixture save."""
import argparse
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
from authority.checkpoints import Checkpoint
import authority_player_registry_checkpoint_bridge as bridge_module
import authority_saved_player_registry_save_live as subject


class RegistryCheckpointTest(unittest.TestCase):
    def test_save_uses_owned_bridge_then_verifies_published_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / 'game'
            game.mkdir()
            (game / 'X4').write_bytes(b'fixture')
            profile = root / 'profile'
            profile.mkdir()
            output = root / 'out'
            output.mkdir()
            lease, epoch = 'a' * 32, 'b' * 32
            calls = []
            checkpoint = SimpleNamespace(checkpoint_id='checkpoint', sha256='c' * 64)
            class FakeSocket:
                def recvfrom(self, _size):
                    return f'HELLO|{lease}|{epoch}'.encode(), ('127.0.0.1', 1234)
                def getsockname(self):
                    return ('127.0.0.1', 4321)
            class FakeBridge:
                pending_marker = 'd' * 32
                def __init__(self, **_kwargs): pass
                def pause(self): calls.append('pause')
                def save_fixture_experiment(self, *, enabled):
                    calls.append(('save', enabled))
                    return profile / 'save_009.xml.gz'
                def checkpoint_published(self, value):
                    calls.append(('verify', value))
                    return True
            class FakeStore:
                def __init__(self, _path): pass
                def publish(self, path, *, marker):
                    calls.append(('publish', path, marker))
                    return checkpoint
            state = {'save_attempted': False, 'verified': None}
            with patch.object(subject, 'socket_owner', return_value=True), \
                 patch.object(subject.fixture_log, 'capture', return_value=(b'\n', (), True)), \
                 patch.object(subject.seat, 'check_control_log'), \
                 patch.object(subject.registry, 'check_registry_log'), \
                 patch.object(subject, 'PlayerRegistryCheckpointBridge', FakeBridge), \
                 patch.object(subject, 'CheckpointStore', FakeStore):
                result = subject.save_registered_fixture(profile=profile, out=output, game=game,
                    identity=(1, 2), deadline=time.monotonic() + 10, guard=lambda: None,
                    control_socket=FakeSocket(), lease=lease, world_epoch=epoch, state=state)
            self.assertEqual(calls, ['pause', ('save', True),
                ('publish', profile / 'save_009.xml.gz', 'd' * 32), ('verify', checkpoint)])
            self.assertTrue(state['save_attempted'])
            self.assertEqual(state['verified'][1], checkpoint)
            self.assertTrue(result['saved_fixture_registry_mapping_checked'])
            self.assertFalse(result['checkpoint_confirmed'])

    def test_mapping_checked_before_native_verify_and_failure_fences_bridge(self):
        with tempfile.TemporaryDirectory() as directory, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            profile = Path(directory) / '45841'
            (profile / 'save').mkdir(parents=True)
            sock.bind(('127.0.0.1', 0))
            marker, epoch = 'b' * 32, 'a' * 32
            checkpoint = Checkpoint('checkpoint-' + 'd' * 32, profile / 'save/save_009.xml.gz', 'e' * 64, 10, marker)
            info = SimpleNamespace(checkpoint_id=checkpoint.checkpoint_id, sha256=checkpoint.sha256,
                                   size=checkpoint.size, save_name=f'X4 Authority {epoch} 7')
            bridge = bridge_module.PlayerRegistryCheckpointBridge(
                enabled=True, sock=sock, peer=('127.0.0.1', 1234), lease='f' * 32, world_epoch=epoch,
                profile=profile, store=SimpleNamespace(get=lambda _: checkpoint), marker_required=True,
                verify_checkpoint=lambda *args: info, fixture_epoch='c' * 32)
            bridge._pending_save, bridge._pending_marker = 7, marker
            with patch.object(bridge_module.fixture, 'verify', return_value={'saved_slots_checked': 2,
                    'saved_owner_class_sector_checked': True, 'saved_registry_slot_mapping_checked': False}) as verify, \
                    patch.object(bridge, '_exchange') as exchange:
                with self.assertRaisesRegex(ValueError, 'registry mapping'):
                    bridge.checkpoint_published(checkpoint)
                verify.assert_called_once_with(checkpoint, 'c' * 32, marker, registry_count=4, fixture_indices=(3, 4))
                exchange.assert_not_called()
                self.assertTrue(bridge._poisoned)

    def test_confirmation_only_after_clean_runner_and_uncertainty_recorded(self):
        for failure in (False, True):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                calls = []
                class Store:
                    def confirm(self, checkpoint):
                        calls.append(('confirm', checkpoint))
                        if failure:
                            raise OSError('fsync failed')
                def run_registry(args):
                    self.assertEqual(calls, [])
                    callback = subject.recovery.observation_callback
                    with patch.object(subject, 'save_registered_fixture', side_effect=lambda **kw:
                            (kw['state'].update(verified=(Store(), 'checkpoint'), save_attempted=True) or
                             {'checkpoint_confirmed': False})):
                        experiment = callback()
                    calls.append(('runner returned', None))
                    return {'success': True, 'experiment': experiment}
                args = argparse.Namespace(out=output)
                original = subject.recovery.observation_callback
                with patch.object(subject.registry, 'run', side_effect=run_registry):
                    result = subject.run(args)
                self.assertIs(subject.recovery.observation_callback, original)
                self.assertEqual(calls, [('runner returned', None), ('confirm', 'checkpoint')])
                self.assertEqual(result['checkpoint_confirmed'], not failure)
                self.assertEqual(result['success'], not failure)
                self.assertEqual(result['checkpoint_confirmation_uncertain'], failure)

    def test_concrete_installer_keeps_saved_scripts_and_one_update_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory) / 'case'
            profile = case / 'profile'
            lab = case / 'extensions/x4_lan_lab'
            ui, md = lab / 'ui', lab / 'md'
            ui.mkdir(parents=True); md.mkdir(); (lab / 'native').mkdir(); (profile / 'save').mkdir(parents=True)
            for path in (ui / 'native_gate_snapshot.lua', md / 'native_gate_battle.xml', ui / 'config.lua'):
                path.write_text('test')
            source = subject.seat.fixture_source
            scripts = {name: (source.fixture_save.historical_registry() if name == 'authority_ship_registry.xml'
                              else ROOT / 'tools/dev' / name).read_bytes() for name in source.SAVED_SCRIPTS}
            config, protected = subject.install_save_bridge(case, profile, scripts, port=1234,
                lease='a' * 32, world_epoch='b' * 32, registry_installer=subject.registry.install,
                slot=1, nonce='c' * 32, timeout=60, seat_installer=subject.seat.install,
                recovery_installer=subject.recovery.install_probe, registry_nonce='d' * 32)
            for name, contents in scripts.items():
                self.assertEqual((md / name).read_bytes(), contents)
            self.assertIn('authority_marker_required=true', config.read_text())
            self.assertIn(lab / 'native/x4lan_net.so', protected)
            self.assertEqual((ui / 'authority_recovery_probe.lua').read_text().count("SetScript('onUpdate'"), 1)
            self.assertNotIn("SetScript('onUpdate'", (ui / 'authority_world_bridge_probe.lua').read_text())
            self.assertIn('X4LAN_REGISTRY_SAVE_READY()', (ui / 'authority_world_bridge_probe.lua').read_text())
            if shutil.which('luajit') is None:
                self.skipTest('LuaJIT required for long-running seat guard')
            library = Path(directory) / 'fake-x4.so'
            subprocess.run(['cc', '-shared', '-fPIC', 'tests/lua/authority_player_control_fake_x4.c',
                            '-o', str(library)], cwd=ROOT, check=True, capture_output=True, timeout=10)
            control = ui / 'authority_player_control_once.lua'
            source_lua = (ROOT / 'tests/authority_saved_player_control_x4.lua').read_text()
            source_lua = source_lua.replace('function GetCurRealTime() return 1 end',
                                            'local now=1\nfunction GetCurRealTime() return now end')
            source_lua = source_lua.replace("dofile('tools/dev/authority_player_control_live_owner.lua')",
                                            'dofile(assert(arg[4]))')
            source_lua = source_lua.replace("dofile('tools/dev/authority_saved_player_control_owner.lua')",
                                            'dofile(assert(arg[5]))')
            source_lua = source_lua.replace('X4LAN_AUTHORITY_RECOVERY_EXPERIMENT_TICK',
                                            'X4LAN_AUTHORITY_RECOVERY_SEAT_TICK')
            long_save = Path(directory) / 'long-save.lua'
            long_save.write_text(source_lua + "\nnow=1000\nassert(X4LAN_REGISTRY_SAVE_READY())\n"
                "assert(pcall(X4LAN_AUTHORITY_RECOVERY_SEAT_TICK))\nfake.TestRogue()\n"
                "assert(not pcall(X4LAN_AUTHORITY_RECOVERY_SEAT_TICK))\n")
            subprocess.run(['luajit', str(long_save), str(library), str(control), 'normal',
                            str(ui / 'authority_player_control_live_owner.lua'),
                            str(ui / 'authority_saved_player_control_owner.lua')],
                           cwd=ROOT, check=True, capture_output=True, timeout=5)
            early_timeout = Path(directory) / 'early-timeout.lua'
            early_timeout.write_text(source_lua.replace(
                "assert(requests[#requests][2]=='Create' and requests[#requests][3].slot==2)",
                "do now=1000\nassert(not X4LAN_REGISTRY_SAVE_READY())\n"
                "assert(not pcall(X4LAN_AUTHORITY_RECOVERY_SEAT_TICK));return end"))
            subprocess.run(['luajit', str(early_timeout), str(library), str(control), 'normal',
                            str(ui / 'authority_player_control_live_owner.lua'),
                            str(ui / 'authority_saved_player_control_owner.lua')],
                           cwd=ROOT, check=True, capture_output=True, timeout=5)
            marker_test = Path(directory) / 'marker-test.lua'
            marker_test.write_text("""
local events, errors = {}, 0
X4LAN_CONFIG = {authority_marker_phase='load'}
function RegisterEvent(name, fn) events[name]=fn end
function DebugError(text) if text:match(' ERROR$') then errors=errors+1 end end
function GetCurRealTime() return 1 end
function AddUITriggeredEvent() end
dofile(arg[1])
assert(not X4LAN_AUTHORITY_MARKER_READY())
local stored=events['X4AuthorityPlayerFixtureMarker.Stored']
if arg[2]=='early' then
 stored(nil, string.rep('a',32))
 assert(errors==1 and not pcall(X4LAN_AUTHORITY_MARKER_READY))
else
 events['X4AuthorityPlayerFixtureMarker.Inspected'](nil, string.rep('b',32))
 assert(X4LAN_AUTHORITY_MARKER_READY())
 stored(nil, string.rep('a',32))
 assert(errors==0 and X4LAN_AUTHORITY_MARKER_READY())
end
""")
            for scenario in ('early', 'completed'):
                subprocess.run(['luajit', str(marker_test), str(ui / 'authority_checkpoint_marker_probe.lua'),
                                scenario], cwd=ROOT, check=True, capture_output=True, timeout=5)


if __name__ == '__main__':
    unittest.main()
