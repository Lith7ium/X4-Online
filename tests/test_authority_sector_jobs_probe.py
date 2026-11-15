"""Structural checks only: these tests do not execute X4 MD expressions."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / 'tools/dev/authority_sector_jobs_probe.xml'


class SectorJobsProbeStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ET.parse(PROBE).getroot()
        cls.begin = cls.root.find("./cues/cue[@name='State']")
        cls.sample = cls.root.find("./cues/cue[@name='Sample']")

    def test_permission_change_is_exclusively_in_treatment_branch(self):
        changes = self.root.findall('.//set_space_jobs_allowed')
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].attrib, {'space': '$sector', 'allow': 'false'})
        branches = [node for node in self.begin.findall('.//do_if')
                    if node.get('value') == "$mode == 'treatment'"]
        self.assertEqual(len(branches), 1)
        self.assertIs(branches[0].find('set_space_jobs_allowed'), changes[0])
        self.assertFalse(self.sample.findall('.//set_space_jobs_allowed'))
        self.assertFalse(self.root.findall('.//reset_space_jobs_allowed'))

    def test_mode_registry_sector_pilot_and_sampled_order_state_guards(self):
        begin_guards = ' '.join(n.get('value', '') for n in self.begin.findall('.//do_if'))
        sample_guards = ' '.join(n.get('value', '') for n in self.sample.findall('.//do_if'))
        for part in ("$mode == 'control'", "$mode == 'treatment'", '$ship.sector == $sector',
                     'State.$ships.{$index} == $ship', 'State.$byship.{$ship} == $index',
                     '$ship.pilot.exists', '$ship.order.exists', 'orderstate.started', 'orderstate.critical'):
            self.assertIn(part, begin_guards)
        for part in ('State.$ready?', 'event.param3.$epoch == State.$epoch',
                     'State.$ship.sector == State.$sector', 'State.$ship.pilot == State.$pilot',
                     'State.$ship.order.id == State.$orderid',
                     'State.$ships.{State.$index} == State.$ship',
                     'State.$byship.{State.$ship} == State.$index',
                     'orderstate.started', 'orderstate.critical'):
            self.assertIn(part, sample_guards)
        self.assertGreaterEqual(len(self.begin.findall('.//do_else/raise_lua_event')), 2)
        self.assertIsNotNone(self.sample.find('.//do_else/raise_lua_event'))

    def test_no_ship_or_motion_mutation_and_order_type_ids_are_reported(self):
        allowed = {'mdscript', 'cues', 'cue', 'conditions', 'event_ui_triggered', 'actions',
                   'set_value', 'do_if', 'do_else', 'set_space_jobs_allowed', 'raise_lua_event'}
        self.assertEqual({element.tag for element in self.root.iter()} - allowed, set())
        began = self.begin.find(".//raise_lua_event[@name=\"'X4AuthoritySectorJobsProbe.Began'\"]")
        sampled = self.sample.find(".//raise_lua_event[@name=\"'X4AuthoritySectorJobsProbe.Sampled'\"]")
        self.assertEqual(began.get('param'), '$orderid')
        self.assertEqual(sampled.get('param'), 'State.$orderid')


if __name__ == '__main__':
    unittest.main()
