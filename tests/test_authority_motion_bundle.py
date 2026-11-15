"""Opt-in movement stimulus cannot weaken the sealed fixture-wire contract."""
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/dev'))
import linux_gate_live as live


class MotionBundleTests(unittest.TestCase):
    def test_motion_bundle_requires_wire_scan_idle_and_sealed_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {}
            names = ('extension/x4_lan_lab/ui/ship_scan.lua',
                     'extension/x4_lan_lab/ui/x4_ship_engine.lua',
                     'extension/x4_lan_lab/ui/fixture_scan_probe.lua',
                     'extension/x4_lan_lab/ui/fixture_wire.lua',
                     'extension/x4_lan_lab/ui/fixture_wire_probe.lua',
                     'extension/x4_lan_lab/native/x4lan_net.so',
                     'fixture_udp.py', 'authority_fixture_wire_support.py')
            for name in names:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
                files[name] = 'stub'
            config = root / 'extension/x4_lan_lab/ui/config.lua'
            config.write_text('X4LAN_CONFIG.native_gate_authority_scan = true\n'
                              'X4LAN_CONFIG.native_gate_battle_engage = false\n'
                              'X4LAN_CONFIG.native_gate_authority_wire = true\n'
                              'X4LAN_CONFIG.native_gate_authority_motion = true\n')
            manifest = {'authority_fixture_scan': True, 'authority_fixture_wire': True,
                        'authority_fixture_motion': True, 'battle': True, 'ticks': 120,
                        'clients': 2, 'files': files}
            live.validate_authority_scan_bundle(root, manifest)
            for key, value in (('authority_fixture_motion', False),
                               ('authority_fixture_wire', False),
                               ('authority_fixture_scan', False), ('ticks', 119)):
                tampered = dict(manifest, **{key: value})
                with self.subTest(key=key), self.assertRaises(ValueError):
                    live.validate_authority_scan_bundle(root, tampered)
            config.write_text(config.read_text().replace('native_gate_battle_engage = false',
                                                         'native_gate_battle_engage = true'))
            with self.assertRaisesRegex(ValueError, 'idle battle fixture'):
                live.validate_authority_scan_bundle(root, manifest)

    def test_move_order_has_a_single_enrolled_target_and_no_combat_order(self):
        root = ET.parse(ROOT / 'tools/dev/native_gate_battle.xml').getroot()
        cues = [cue for cue in root.iter('cue') if cue.get('name') == 'AuthorityMoveFixture']
        self.assertEqual(len(cues), 1)
        orders = list(cues[0].iter('create_order'))
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].get('object'), '$ships.{1}')
        self.assertEqual(orders[0].get('id'), "'MoveWait'")
        self.assertEqual([p.get('name') for p in orders[0].iter('param')],
                         ['destination', 'precise', 'noattackresponse'])


if __name__ == '__main__':
    unittest.main()
