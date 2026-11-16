"""Structural contract checks; not an MD interpreter or native evidence."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DEV = ROOT / 'tools/dev'

class CensusReplicaMDTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receiver = ET.parse(DEV / 'authority_census_replica_receiver.xml').getroot()
        cls.inspector = ET.parse(DEV / 'authority_census_replica_inspect.xml').getroot()

    def test_exclusive_entrypoints_and_no_extra_mutation(self):
        self.assertEqual(self.receiver.get('name'), 'X4AuthorityCensusReplica')
        self.assertEqual(self.inspector.get('name'), 'X4AuthorityCensusReplicaInspect')
        self.assertEqual([x.get('control') for x in self.receiver.iter('event_ui_triggered')], ["'Initialize'", "'Create'"])
        self.assertEqual([x.get('control') for x in self.inspector.iter('event_ui_triggered')], ["'Inspect'"])
        self.assertEqual(len(list(self.receiver.iter('create_ship'))), 1)
        self.assertFalse(list(self.inspector.iter('create_ship')))
        for root in (self.receiver, self.inspector):
            for tag in ('destroy_object', 'remove_object', 'save_game', 'signal_cue'):
                self.assertFalse(list(root.iter(tag)))

    def test_baseline_pending_and_serialized_replay(self):
        init, create = self.receiver.findall('./cues/cue')
        self.assertIsNone(init.get('instantiate'))
        self.assertEqual(create.get('instantiate'), 'true')
        init_guard = init.find('./actions/do_if').get('value')
        for part in ('$last == 10054', '$ships.{10055}', 'not State.$epoch?', 'not State.$receipt?', '$v.$epoch ==', 'not md.X4AuthorityShipRegistry.State.$faulted'):
            self.assertIn(part, init_guard)
        outer = create.find('./actions/do_if')
        for part in ('$v.$index == 10055', '$v.$seed == 7183', 'not State.$pending', 'not State.$faulted', '$v.$x ge -10000000', '$v.$z le 10000000'):
            self.assertIn(part, outer.get('value'))
        text = ET.tostring(create, encoding='unicode')
        self.assertLess(text.index('name="State.$pending" exact="true"'), text.index('<create_ship '))
        self.assertLess(text.index('<create_ship '), text.index('name="State.$receipt" exact="$ship"'))
        self.assertIn('State.$phase == 0', text)
        self.assertIn('State.$phase == 2', text)
        self.assertIn('name="State.$phase" exact="1"', text)
        self.assertIn('name="State.$phase" exact="3"', text)
        replay = next(x for x in create.iter('do_elseif') if 'State.$phase == 2' in x.get('value', ''))
        self.assertFalse(list(replay.iter('create_ship')))
        for f in ('macro', 'faction', 'sector_macro', 'seed', 'x', 'y', 'z', 'witness_index'):
            self.assertIn('State.$' + f, replay.get('value'))
        self.assertIn('State.$receipt == $ship', ET.tostring(replay, encoding='unicode'))

    def test_witness_resolved_locally_for_create_and_inspection(self):
        for root in (self.receiver, self.inspector):
            finds = list(root.iter('find_sector'))
            self.assertEqual(len(finds), 1)
            self.assertEqual(finds[0].get('multiple'), 'true')
            self.assertEqual(finds[0].get('macro'), 'macro.{$v.$sector_macro}')
            conditions = '\n'.join(x.get('value', '') for x in root.iter('do_if'))
            for part in ('$matches.count == 1', '$witness_index ge 1', '$witness_index le 10054', '$byship.{$witness} == $v.$witness_index', '$witness.sector == $matches.{1}', 'not $witness.dock.exists', 'not $witness.isinternallystored'):
                self.assertIn(part, conditions)
            self.assertNotIn('X4AuthoritySectorReferenceFixture', ET.tostring(root, encoding='unicode'))

    def test_inspector_requires_receipt_and_descriptor_for_each_phase(self):
        text = ET.tostring(self.inspector, encoding='unicode')
        for f in ('macro', 'faction', 'sector_macro', 'seed', 'x', 'y', 'z', 'witness_index'):
            self.assertIn('State.$' + f + ' == $v.$' + f, text)
        for part in ('State.$phase == 1', 'State.$phase == 3', '$last == 10055', '$byship.{$ship} == 10055', '$receipt == $ship', '$ship.sector == $sector', '$ship.macro.id == $v.$macro', '$ship.owner.id == $v.$faction', '$v.$request_id,$v.$epoch,$v.$index,$ship,$sector,$sector.macro.id'):
            self.assertIn(part, text)
        self.assertIn('State.$phase + 1', text)
        self.assertIn("'X4AuthorityCensusReplica.Refused'", text)

if __name__ == '__main__':
    unittest.main()
