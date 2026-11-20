"""Structural contract checks for the default-off format-3 MD snapshot."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / 'tools/dev/authority_registry_availability_snapshot.xml'


class RegistryAvailabilitySnapshotMD(unittest.TestCase):
    def setUp(self):
        self.root = ET.parse(MD).getroot()
        self.cues = {cue.get('name'): cue for cue in self.root.find('cues')}

    @staticmethod
    def event_format(cue, marker):
        response = next(node.get('param', '') for node in cue.iter('raise_lua_event')
                        if marker in node.get('param', ''))
        return response.split("'.[", 1)[0].lstrip("'")

    def test_new_version_initializes_once_with_separate_complete_maps(self):
        self.assertEqual(self.root.get('name'), 'X4AuthorityRegistryAvailabilitySnapshot')
        state_actions = self.cues['State'].find('actions')
        writes = {node.get('name'): node.get('exact')
                  for node in state_actions.iter('set_value')
                  if node.get('name', '').startswith('State.')}
        self.assertEqual(writes, {
            'State.$format': '3', 'State.$epoch': '$request.$epoch',
            'State.$run_id': '$request.$run_id',
            'State.$issued_count': '(md.X4AuthorityShipRegistry.State.$last)i',
            'State.$cursor': '0', 'State.$available_count': '0',
            'State.$unavailable_count': '0', 'State.$sealed': 'false',
            'State.$operational_count': '0', 'State.$faulted': 'false',
            'State.$available': 'table[]', 'State.$operational': 'table[]',
            'State.$ships': 'table[]', 'State.$byship': 'table[]',
        })
        guard = next(n.get('value', '') for n in state_actions.iter('do_if'))
        for required in ('not State.$format?', 'State.$format', '$request.$run_id?',
                         '$request.$issued_count ge 1',
                         '$request.$issued_count le 200000',
                         '$request.$issued_count == ($request.$issued_count)i',
                         'not md.X4AuthorityShipRegistry.State.$faulted'):
            self.assertIn(required, guard)
        self.assertEqual(len(self.event_format(self.cues['State'], '|Initialize|Initialized|').split('|')), 5)

    def test_capture_is_contiguous_bounded_and_only_maps_available_actors(self):
        actions = self.cues['Capture'].find('actions')
        guard = next(n.get('value', '') for n in actions.iter('do_if')
                     if '$first == State.$cursor + 1' in n.get('value', ''))
        for required in ('not State.$sealed', 'not State.$faulted',
                         '$count ge 1', '$count le 64',
                         '$first + $count - 1 le State.$issued_count',
                         'md.X4AuthorityShipRegistry.State.$last == State.$issued_count'):
            self.assertIn(required, guard)
        loops = [n for n in actions.iter('do_all') if n.get('counter')]
        self.assertTrue(any(n.get('counter') == '$offset' and n.get('exact') == '$count' for n in loops))
        stores = [(n.get('name'), n.get('exact')) for n in actions.iter('set_value')]
        self.assertIn(('State.$available.{$index}', '0'), stores)
        self.assertIn(('State.$available.{$index}', '1'), stores)
        self.assertIn(('State.$operational.{$index}', '0'), stores)
        self.assertTrue(any(name == 'State.$operational.{$index}' and 'if $ship.isoperational' in expr
                            for name, expr in stores))
        self.assertIn(('State.$ships.{$index}', '$ship'), stores)
        self.assertIn(('State.$byship.{$ship}', '$index'), stores)
        registry_writes = [n.get('name', '') for n in self.root.iter('set_value')
                           if n.get('name', '').startswith('md.X4AuthorityShipRegistry.State.')]
        self.assertEqual(registry_writes, [])
        serialized = ET.tostring(self.root, encoding='unicode')
        self.assertIn('State.$faulted" exact="true"', serialized)
        self.assertIn('Availability snapshot capture fault at index %s: %s', serialized)
        # UI numbers arrive as largefloat. Validate before normalizing the
        # persisted count, cursor and reverse-map indices to MD integers.
        self.assertIn('name="$index" exact="($first + $offset - 1)i"', serialized)
        self.assertIn('name="State.$cursor" exact="($first + $count - 1)i"', serialized)
        capture = ET.tostring(self.cues['Capture'], encoding='unicode')
        self.assertIn('Availability capture row index %s existing %s ship %s real_ship %s operational %s reverse_matches %s snapshot_duplicate %s', capture)
        self.assertIn('Availability capture row index %s reason missing_forward', capture)
        self.assertIn('Availability capture row index %s reason duplicate_snapshot_index', capture)
        for flag in ('$existing_flag', '$ship_flag', '$real_ship_flag', '$operational_flag',
                     '$reverse_matches_flag', '$snapshot_duplicate_flag'):
            self.assertIn(f'name="{flag}"', capture)
        capture_guard = next(n.get('value', '') for n in actions.iter('do_if')
                             if '$ship.isrealclass.ship and' in n.get('value', ''))
        self.assertNotIn('$ship.isoperational', capture_guard)
        inspect_guards = [node.get('value', '') for node in self.cues['Inspect'].iter('do_if')]
        self.assertTrue(any('$ship.isrealclass.ship' in guard for guard in inspect_guards))
        self.assertFalse(any('$ship.isclass.ship' in guard for guard in inspect_guards))
        self.assertIn('or State.$operational.{$index}?', ET.tostring(self.cues['Capture'], encoding='unicode'))
        self.assertEqual(len(self.event_format(self.cues['Capture'], '|Capture|%s|%s|Captured|').split('|')), 11)

    def test_seal_requires_full_coverage_and_counts(self):
        actions = self.cues['Seal'].find('actions')
        guard = next(n.get('value', '') for n in actions.iter('do_if'))
        for required in ('State.$cursor == State.$issued_count',
                         'State.$available_count + State.$unavailable_count == State.$issued_count',
                         'State.$operational_count le State.$available_count',
                         'not State.$faulted', 'not State.$sealed'):
            self.assertIn(required, guard)
        self.assertEqual(len(self.event_format(self.cues['Seal'], '|Seal|Sealed|').split('|')), 8)

    def test_inspect_is_sealed_and_does_not_write_persisted_state(self):
        actions = self.cues['Inspect'].find('actions')
        writes = [n.get('name', '') for n in actions.iter('set_value')]
        self.assertFalse(any(name.startswith('State.$') for name in writes))
        guard = next(n.get('value', '') for n in actions.iter('do_if')
                     if 'State.$sealed and not State.$faulted' in n.get('value', ''))
        for required in ('State.$sealed', 'not State.$faulted', '$count le 64',
                         'State.$epoch == md.X4AuthorityShipRegistry.State.$epoch',
                         'State.$issued_count == md.X4AuthorityShipRegistry.State.$last'):
            self.assertIn(required, guard)
        body = ET.tostring(self.cues['Inspect'], encoding='unicode')
        self.assertIn('State.$available.{$index} == 1', body)
        self.assertIn('State.$available.{$index} == 0', body)
        self.assertIn('State.$operational.{$index} == 0 or State.$operational.{$index} == 1', body)
        self.assertIn('State.$operational.{$index} == 0 and not @$ship.exists', body)
        self.assertIn('State.$byship.{$ship}?', body)
        self.assertIn('State.$byship.{$saved_ship} == $index', body)
        self.assertIn("'saved_available_binding_missing'", body)
        self.assertIn("'availability_flag_not_binary'", body)
        self.assertIn('State.$available.{$index}', body)
        self.assertIn('State.$ships.{$index} == $ship', body)
        self.assertIn('State.$byship.{$ship} == $index', body)
        self.assertIn("$saved_binding_bits + '1'", body)
        self.assertIn("$fresh_binding_bits + '0'", body)
        self.assertIn("$fresh_binding_bits + '1'", body)
        self.assertIn("$saved_operational_bits", body)
        self.assertIn("$fresh_operational_bits", body)
        self.assertIn('Availability snapshot inspect fault at index %s: %s', body)
        self.assertEqual(len(self.event_format(self.cues['Inspect'], '|Inspect|%s|%s|Inspected|').split('|')), 10)
        inspect_response = next(n.get('param', '') for n in self.cues['Inspect'].iter('raise_lua_event')
                                if '|Inspect|%s|%s|Inspected|' in n.get('param', ''))
        for name in ('$saved_binding_bits', '$fresh_binding_bits',
                     '$saved_operational_bits', '$fresh_operational_bits'):
            self.assertIn(name, inspect_response)

    def test_all_actions_are_explicit_default_off_read_only_registry_triggers(self):
        self.assertEqual(set(self.cues), {'State', 'Capture', 'Seal', 'Inspect'})
        serialized = ET.tostring(self.root, encoding='unicode')
        self.assertNotIn('<destroy_object', serialized)
        self.assertNotIn('<set_value name="md.X4AuthorityShipRegistry.State.', serialized)
        for cue in self.cues.values():
            trigger = cue.find('./conditions/event_ui_triggered')
            self.assertIsNotNone(trigger)
            self.assertEqual(trigger.get('screen'), "'X4AuthorityRegistryAvailabilitySnapshot'")
        for action in ('Capture', 'Seal', 'Inspect'):
            guards = [n.get('value', '') for n in self.cues[action].iter('do_if')]
            self.assertTrue(any('State.$format == 3' in value for value in guards))


if __name__ == '__main__':
    unittest.main()
