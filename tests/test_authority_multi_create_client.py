"""Experimental multi-create contracts; no real X4 or live networking."""
from pathlib import Path
import subprocess
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


class MultiCreate(unittest.TestCase):
    def test_serial_correlated_replay_and_failures(self):
        subprocess.run(['luajit','tests/authority_multi_create_client.lua'],cwd=ROOT,
                       check=True,capture_output=True,text=True,timeout=5)

    def test_receiver_correlates_every_response_and_inspects_bidirectional_binding(self):
        root=ET.parse(ROOT/'tools/dev/authority_multi_create_receiver.xml').getroot()
        self.assertEqual(root.get('name'),'X4AuthorityMultiCreateReceiver')
        cues={c.get('name'):c for c in root.findall('./cues/cue')}
        self.assertEqual(set(cues),{'State','Witness','Create','Inspect'})
        responses=root.findall('.//raise_lua_event')
        self.assertTrue(responses)
        for event in responses:
            self.assertEqual(event.get('name'),"'X4AuthorityMultiCreateReceiver.Result'")
            self.assertIn('$request_id',event.get('param'))
        xml=ET.tostring(root,encoding='unicode')
        for code in ('create_replay','create_pending_clear','create_registry','create_ship',
                     'create_pending_set','create_input','create_witness','create_index','create_state',
                     'inspect_binding','inspect_witness','inspect_descriptor'):
            self.assertIn(code,xml)
        self.assertEqual(xml.count('|Refused|'),10)
        checks=' '.join(node.get('value','') for node in cues['Inspect'].findall('.//do_if'))
        for part in ('State.$receipts','State.$byship','State.$macros','State.$sectors',
                     'State.$owners','State.$seeds','State.$xs','State.$ys','State.$zs'):
            self.assertIn(part,checks)
        self.assertIn('$v.$witness_index le State.$baseline',checks)
        self.assertIn('$ship.sector == $witness.sector',checks)
        self.assertIn('$witness.sector == $matches.{1}',checks)
        self.assertEqual(len(cues['Witness'].findall('.//find_sector')),1)
        self.assertFalse(cues['Witness'].findall('.//create_ship'))
        self.assertFalse(cues['Witness'].findall('.//remove_value'))
        witness_guards=[node.get('value') for node in cues['Witness'].findall('.//do_if')]
        create_guards=[node.get('value') for node in cues['Create'].findall('.//do_if')]
        for guard in create_guards:
            if '$req.$witness_index ge 1' in guard or 'not $witness.dock.exists' in guard or '$witness.sector == $matches.{1}' in guard:
                self.assertIn(guard,witness_guards)
        self.assertEqual(cues['Witness'].find('.//find_sector').attrib,cues['Create'].find('.//find_sector').attrib)
        for node in cues['Witness'].findall('.//set_value'):
            self.assertTrue(node.get('name').startswith('$'),node.get('name'))
        self.assertEqual(len(cues['Inspect'].findall('.//find_sector')),1)
        self.assertEqual(len(cues['Create'].findall('.//find_sector')),1)
        self.assertNotIn('X4AuthoritySectorReferenceFixture',ET.tostring(root,encoding='unicode'))
        self.assertEqual(len(cues['Create'].findall('.//create_ship')),1)
        self.assertFalse(cues['Inspect'].findall('.//create_ship'))
