"""Structural contract checks; these do not execute the X4 MD interpreter."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tools/dev/authority_sector_reference_fixture.xml'


class SectorReferenceFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ET.parse(FIXTURE).getroot()
        cls.state = cls.root.find("./cues/cue[@name='State']")
        cls.verify = cls.root.find("./cues/cue[@name='Verify']")

    def test_only_fixture_state_and_events_are_written(self):
        self.assertEqual({node.tag for node in self.root.iter()},
                         {'mdscript', 'cues', 'cue', 'conditions', 'event_ui_triggered',
                          'actions', 'set_value', 'do_if', 'do_else', 'raise_lua_event'})
        for action in self.root.iter('set_value'):
            self.assertTrue(action.attrib['name'].startswith('$'))
        self.assertEqual(self.state.attrib.get('namespace'), 'this')

    def test_initialize_requires_distinct_valid_sector_and_ship_references(self):
        guards = [node.attrib['value'] for node in self.state.iter('do_if')]
        self.assertEqual(len(guards), 2)
        for term in ('$v.$epoch == md.X4AuthorityShipRegistry.State.$epoch',
                     'not md.X4AuthorityShipRegistry.State.$faulted', '$i1 != $i2'):
            self.assertIn(term, guards[0].split(' and '))
        for term in ('$s1 != $s2', '@$s1.isoperational', '@$s2.isoperational',
                     '$s1.isclass.ship', '$s2.isclass.ship',
                     '@$s1.sector.isclass.sector', '@$s2.sector.isclass.sector',
                     '$s1.sector != $s2.sector',
                     '@md.X4AuthorityShipRegistry.State.$byship.{$s1} == $i1',
                     '@md.X4AuthorityShipRegistry.State.$byship.{$s2} == $i2'):
            self.assertIn(term, guards[1].split(' and '))
        saved = {node.attrib['name']: node.attrib['exact'] for node in self.state.iter('set_value')}
        self.assertEqual(saved['$sector1'], '$s1.sector')
        self.assertEqual(saved['$sector2'], '$s2.sector')
        self.assertEqual(saved['$ship1'], '$s1')
        self.assertEqual(saved['$ship2'], '$s2')

    def test_verify_checks_saved_relationships_and_registry_both_ways(self):
        guard = self.verify.find('./actions/do_if').attrib['value'].split(' and ')
        for term in ('$v.$epoch == State.$epoch',
                     'State.$epoch == md.X4AuthorityShipRegistry.State.$epoch',
                     'not md.X4AuthorityShipRegistry.State.$faulted',
                     'State.$index1 != State.$index2', 'State.$ship1 != State.$ship2',
                     '@State.$sector1.isclass.sector', '@State.$sector2.isclass.sector',
                     'State.$sector1 != State.$sector2',
                     'State.$ship1.sector == State.$sector1',
                     'State.$ship2.sector == State.$sector2'):
            self.assertIn(term, guard)
        for i in (1, 2):
            self.assertIn(f'@State.$ship{i}.isoperational', guard)
            self.assertIn(f'State.$ship{i}.isclass.ship', guard)
            self.assertIn(f'@md.X4AuthorityShipRegistry.State.$ships.{{State.$index{i}}} == State.$ship{i}', guard)
            self.assertIn(f'@md.X4AuthorityShipRegistry.State.$byship.{{State.$ship{i}}} == State.$index{i}', guard)
        self.assertEqual([node.attrib['name'] for node in self.verify.iter('raise_lua_event')],
                         ["'X4AuthoritySectorReferenceFixture.Verified'",
                          "'X4AuthoritySectorReferenceFixture.Refused'"])


if __name__ == '__main__':
    unittest.main()
