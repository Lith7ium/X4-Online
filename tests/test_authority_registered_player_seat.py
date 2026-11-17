"""Private fixture join-seat tests with synthetic X4 and no game launch."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
import authority_fixture_checkpoint_source as fixture
import authority_registered_player_seat_install as seat
import authority_download_load_live as load


def saved_scripts():
    return {name: (fixture.fixture_save.historical_registry() if name == 'authority_ship_registry.xml'
                   else ROOT / 'tools/dev' / name).read_bytes() for name in fixture.SAVED_SCRIPTS}


class RegisteredPlayerSeatTest(unittest.TestCase):
    def test_installer_preserves_fixture_and_gates_load_before_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory) / 'case'
            profile = case / 'home/.config/EgoSoft/X4/45841'; profile.mkdir(parents=True)
            lab = case / 'extensions/x4_lan_lab'; ui = lab / 'ui'; md = lab / 'md'
            ui.mkdir(parents=True); md.mkdir()
            (ui / 'config.lua').write_text('X4LAN_CONFIG = {}\n')
            (ui / 'authority_checkpoint_marker_probe.lua').write_text(
                (ROOT / 'tools/dev/authority_checkpoint_marker_probe.lua').read_text())
            loader = (ROOT / 'tools/dev/authority_download_load_probe.lua').read_text()
            hook = " elseif state=='observing' then\n"
            loader = loader.replace(hook, hook + '  if not X4LAN_AUTHORITY_MARKER_READY() then return end\n')
            (ui / 'authority_download_load_probe.lua').write_text(loader)
            (lab / 'ui.xml').write_text('<files>\n    <file name="ui/authority_download_load_probe.lua" />\n</files>\n')
            scripts = saved_scripts()
            protected = seat.install(case, profile, slot=2, nonce='b'*32, epoch='a'*32, timeout=90, scripts=scripts)
            for name, data in scripts.items():
                self.assertEqual((md / name).read_bytes(), data)
                self.assertIn(md / name, protected)
            installed = (ui / 'authority_download_load_probe.lua').read_text()
            self.assertLess(installed.index('X4LAN_AUTHORITY_MARKER_READY()'), installed.index('X4LAN_REGISTERED_PLAYER_CONTROL_TICK()'))
            self.assertLess(installed.index('X4LAN_REGISTERED_PLAYER_CONTROL_TICK()'), installed.index('barrier.update()'))
            self.assertIn('engine.is_paused()', installed)
            self.assertEqual(installed.count("SetScript('onUpdate'"), 1)
            self.assertIn('X4AuthorityPlayerFixtureMarker', (ui / 'authority_checkpoint_marker_probe.lua').read_text())
            self.assertIn('slot=o.slot', (ui / 'authority_player_control_once.lua').read_text())
            cue = ET.parse(md / 'authority_registered_player_control.xml').getroot()
            xml = ET.tostring(cue, encoding='unicode')
            self.assertEqual(len(cue.findall('.//teleport_player')), 1)
            self.assertEqual(cue.findall('.//create_ship'), [])
            for expected in ('State.$ships', 'State.$byship', '$slot + 2', '$alreadycontrolled'):
                self.assertIn(expected, xml)

    def test_log_requires_correct_slot_order_and_seat_action(self):
        nonce, marker = 'b'*32, 'c'*32
        ticket = dict(world_epoch='a'*32, connection_handle=1, baseline_id=1, load_generation=1,
                      checkpoint_id='checkpoint-'+'d'*32, sha256='e'*64, attempt_id='f'*32, slot='save_009')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'engine-output.log'
            expected = load.ReceiptWatch(path, ticket).expected
            prefix = ['[X4LAN] AUTH_DOWNLOAD_LOAD ' + expected[0].decode(),
                      '[X4LAN] AUTH_MARKER load INSPECTED ' + marker]
            end = '[X4LAN] AUTH_DOWNLOAD_LOAD ' + expected[1].decode()
            def row(value): return seat.TAG.decode() + nonce + ' ' + value
            for slot, already in ((1, True), (2, False)):
                controls = (['START','CREATED','EXISTING','FIRST','CONTROLLED','DONE'] if already else
                            ['START','CREATED','BEFORE','INTENT_TELEPORT','LOCAL_CALL_RETURNED','DISPATCH','FIRST','CONTROLLED','DONE'])
                rows = [row(value) for value in controls]
                if not already:
                    rows[5:5] = [seat.ACTION_TAG.decode()+'ACTION_BEGIN', seat.ACTION_TAG.decode()+'ACTION_RETURNED']
                rows += [row(f'FENCED slot={slot} index={slot+2}')]
                path.write_text('\n'.join(prefix + rows + [end]) + '\n')
                result = seat.verify_log(path, nonce=nonce, slot=slot, ticket=ticket, marker=marker)
                self.assertTrue(result['local_control_observed'])
                self.assertEqual(result['already_controlled'], already)
                with self.assertRaises(ValueError):
                    seat.verify_log(path, nonce=nonce, slot=3-slot, ticket=ticket, marker=marker)
                path.write_text('\n'.join(prefix + rows[:-1] + [end]) + '\n')
                with self.assertRaises(ValueError):
                    seat.verify_log(path, nonce=nonce, slot=slot, ticket=ticket, marker=marker)

    @unittest.skipUnless(shutil.which('luajit') and shutil.which('cc'), 'LuaJIT and C compiler required')
    def test_existing_seat_and_one_time_takeover_on_synthetic_abi(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory) / 'fake.so'
            subprocess.run(['cc','-shared','-fPIC','tests/lua/authority_player_control_fake_x4.c','-o',str(library)],
                           cwd=ROOT, check=True, capture_output=True)
            control = Path(directory) / 'control.lua'
            control.write_text((ROOT / 'tools/dev/authority_player_control_once.lua').read_text().replace(
                'local args={epoch=o.epoch,request_id=o.nonce}', 'local args={epoch=o.epoch,request_id=o.nonce,slot=o.slot}'))
            for mode in ('existing', 'takeover'):
                subprocess.run(['luajit','tests/authority_registered_player_control_x4.lua',str(library),str(control),mode],
                               cwd=ROOT,check=True,capture_output=True,timeout=5)


if __name__ == '__main__':
    unittest.main()
