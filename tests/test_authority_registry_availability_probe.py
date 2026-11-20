"""Structural and shipped-schema checks; MD behavior still needs native proof."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / 'tools/dev/authority_registry_availability_probe.xml'
OWNER = ROOT / 'tools/dev/authority_registry_availability_probe.lua'


class RegistryAvailabilityProbeMD(unittest.TestCase):
    def setUp(self):
        self.root = ET.parse(MD).getroot()
        self.cues = {cue.get('name'): cue for cue in self.root.find('cues')}

    def test_saved_state_has_versioned_bounded_observation_tables(self):
        state = self.cues['State']
        actions = state.find('actions')
        saved = {node.get('name'): node.get('exact') for node in actions.iter('set_value')
                 if node.get('name', '').startswith('State.')}
        expected = {
            'State.$format': '1', 'State.$epoch': '$request.$epoch',
            'State.$run_id': '$request.$run_id',
            'State.$issued_count': 'md.X4AuthorityShipRegistry.State.$last',
            'State.$count': '0', 'State.$sealed': 'false', 'State.$faulted': 'false',
            'State.$forward_present': 'table[]', 'State.$object_exists': 'table[]',
            'State.$is_ship': 'table[]', 'State.$is_operational': 'table[]',
            'State.$reverse_matches': 'table[]',
        }
        self.assertEqual(saved, expected)
        init_guard = next(node.get('value', '') for node in actions.iter('do_if'))
        self.assertIn('not State.$format?', init_guard)
        self.assertIn('$request.$epoch == md.X4AuthorityShipRegistry.State.$epoch', init_guard)
        self.assertIn('md.X4AuthorityShipRegistry.State.$last ge 1', init_guard)
        self.assertIn('md.X4AuthorityShipRegistry.State.$last le 200000', init_guard)
        self.assertIn('md.X4AuthorityShipRegistry.State.$last == (md.X4AuthorityShipRegistry.State.$last)i', init_guard)

    def test_initialize_response_has_lua_owners_expected_five_fields(self):
        init = self.cues['State'].find('actions')
        response = next(node.get('param', '') for node in init.iter('raise_lua_event')
                        if '|Initialize|Initialized|' in node.get('param', ''))
        format_string = response.split("'.[", 1)[0].lstrip("'")
        self.assertEqual(len(format_string.split('|')), 5)
        owner = OWNER.read_text()
        self.assertIn("if request.action == 'Initialize' then", owner)
        self.assertIn('#fields ~= 5', owner)
        self.assertIn("fields[4] ~= 'Initialized'", owner)
        self.assertIn('fields[5] ~= format_integer(config.issued_count)', owner)

    def test_capture_is_bounded_unique_and_stores_false_as_zero(self):
        actions = self.cues['Capture'].find('actions')
        guards = [node.get('value', '') for node in actions.iter('do_if')]
        guard = next(value for value in guards if 'State.$count lt 16' in value)
        self.assertIn('not State.$sealed', guard)
        self.assertIn('not State.$forward_present.{$index}?', guard)
        self.assertIn('$index le State.$issued_count', guard)
        self.assertIn('State.$format == 1', guard)
        stores = {node.get('name'): node.get('exact') for node in actions.iter('set_value')}
        for table, local in (
            ('$forward_present', '$forward'), ('$object_exists', '$exists'),
            ('$is_ship', '$is_ship'), ('$is_operational', '$operational'),
            ('$reverse_matches', '$reverse'),
        ):
            self.assertEqual(stores[f'State.{table}.{{$index}}'], local)
        self.assertTrue(all('else 0' in expr for expr in stores.values()
                            if expr and expr.startswith('if ')))

    def test_inspect_only_reads_saved_observation_tables(self):
        actions = self.cues['Inspect'].find('actions')
        writes = [node.get('name', '') for node in actions.iter('set_value')]
        self.assertFalse(any(name.startswith('State.$') for name in writes))
        result = next(node.get('param', '') for node in actions.iter('raise_lua_event')
                      if 'X4AuthorityRegistryAvailabilityProbe.Result' in node.get('name', '')
                      and '|Inspect|%s|Inspected|' in node.get('param', ''))
        for name in ('forward_present', 'object_exists', 'is_ship', 'is_operational', 'reverse_matches'):
            self.assertIn(f'State.${name}.{{$index}}', result)
        self.assertIn('$fresh_forward', result)
        self.assertIn('$fresh_reverse', result)

    def test_all_entry_points_are_explicit_ui_triggers_and_registry_is_read_only(self):
        self.assertEqual(set(self.cues), {'State', 'Capture', 'Inspect', 'Seal'})
        for cue in self.cues.values():
            trigger = cue.find('./conditions/event_ui_triggered')
            self.assertIsNotNone(trigger)
            self.assertEqual(trigger.get('screen'), "'X4AuthorityRegistryAvailabilityProbe'")
        serialized = ET.tostring(self.root, encoding='unicode')
        self.assertNotIn('<destroy_object', serialized)
        self.assertNotIn('<set_value name="md.X4AuthorityShipRegistry.State.', serialized)
        seal_guard = next(node.get('value', '') for node in self.cues['Seal'].iter('do_if'))
        self.assertIn('State.$count ge 1', seal_guard)
        self.assertIn('State.$count le 16', seal_guard)
        for cue_name in ('Capture', 'Inspect', 'Seal'):
            predicate = next(node.get('value', '') for node in self.cues[cue_name].iter('do_if'))
            self.assertIn('State.$format == 1', predicate)
            self.assertIn('md.X4AuthorityShipRegistry.State.$last == State.$issued_count', predicate)


if __name__ == '__main__':
    unittest.main()
