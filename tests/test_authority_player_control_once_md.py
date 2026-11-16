"""Static safety contract for the optional private-world control experiment.

These checks are not an X4 gameplay, MD expression, or seat-control test.
"""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'tools/dev/authority_player_control_once.xml'


class PlayerControlOnceMDTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ET.parse(PATH).getroot()
        cls.cues = {cue.get('name'): cue for cue in cls.root.findall('./cues/cue')}

    def test_only_explicit_one_shot_mutations(self):
        self.assertEqual(self.root.get('name'), 'X4AuthorityPlayerControlOnce')
        self.assertEqual(set(self.cues), {'State', 'Teleport', 'Read'})
        self.assertIsNone(self.cues['State'].get('instantiate'))
        for name, control in [('State', 'Create'), ('Teleport', 'Teleport'), ('Read', 'Read')]:
            trigger = self.cues[name].find('./conditions/event_ui_triggered')
            self.assertEqual(trigger.get('screen'), "'X4AuthorityPlayerControlOnce'")
            self.assertEqual(trigger.get('control'), "'%s'" % control)
        self.assertEqual(len(list(self.root.iter('create_ship'))), 1)
        teleport = list(self.root.iter('teleport_player'))
        self.assertEqual(len(teleport), 1)
        self.assertEqual(teleport[0].attrib, {'object': 'State.$ship', 'control': 'true',
                                              'instant': 'true', 'force': 'true'})
        self.assertFalse(list(self.root.iter('save_game')))
        self.assertFalse(list(self.root.iter('debug_text')))

    def test_create_requires_live_registry_and_two_distinct_references(self):
        cue = self.cues['State']
        guard = cue.find('./actions/do_if').get('value')
        for value in ("player.module == 'custom_creative'", 'not md.X4AuthorityShipRegistry.State.$faulted',
                      '$v.$epoch == md.X4AuthorityShipRegistry.State.$epoch',
                      'md.X4AuthoritySectorReferenceFixture.State.$ship1 != md.X4AuthoritySectorReferenceFixture.State.$ship2',
                      'md.X4AuthoritySectorReferenceFixture.State.$sector1 != md.X4AuthoritySectorReferenceFixture.State.$sector2',
                      '@md.X4AuthorityShipRegistry.State.$byship.{md.X4AuthoritySectorReferenceFixture.State.$ship1}',
                      '@md.X4AuthorityShipRegistry.State.$byship.{md.X4AuthoritySectorReferenceFixture.State.$ship2}'):
            self.assertIn(value, guard)
        create = cue.find('.//create_ship')
        self.assertEqual(create.get('macro'), 'macro.ship_arg_s_fighter_01_a_macro')
        self.assertEqual(create.find('owner').get('exact'), 'faction.player')
        self.assertIsNotNone(create.find('safepos'))
        created_guard = cue.find('./actions/do_if/do_if').get('value')
        for value in ('$ship.owner == faction.player', '$ship.sector == $sector',
                      '$ship != player.ship', '$ship != player.occupiedship',
                      '$ship != player.container', '$ship != md.X4AuthoritySectorReferenceFixture.State.$ship1',
                      '$ship != md.X4AuthoritySectorReferenceFixture.State.$ship2', 'not $ship.dock.exists', 'not $ship.isinternallystored'):
            self.assertIn(value, created_guard)
        self.assertNotIn('pilot', ET.tostring(cue, encoding='unicode'))
        actions = list(cue.find('./actions/do_if'))
        self.assertLess(next(i for i, e in enumerate(actions) if e.get('name') == '$pending' and e.get('exact') == 'true'),
                        next(i for i, e in enumerate(actions) if e.tag == 'create_ship'))

    def test_teleport_is_guarded_and_marks_attempt_before_dispatch(self):
        branch = self.cues['Teleport'].find('./actions/do_if')
        guard = branch.get('value')
        for value in ('State.$request_id?', '$v.$request_id == State.$request_id', 'not State.$attempted', 'State.$next == 1', 'not State.$pending',
                      'not State.$faulted', 'State.$ship.owner == faction.player',
                      'State.$ship != player.ship', 'State.$ship != player.occupiedship',
                      'State.$ship != player.container', 'not State.$ship.dock.exists',
                      'not State.$ship.isinternallystored'):
            self.assertIn(value, guard)
        steps = list(branch)
        self.assertEqual([(x.tag, x.get('name'), x.get('exact')) for x in steps[:2]],
                         [('set_value', 'State.$pending', 'true'), ('set_value', 'State.$attempted', 'true')])
        self.assertEqual(steps[2].tag, 'teleport_player')
        self.assertEqual(steps[3].get('name'), 'State.$pending')
        self.assertEqual(steps[3].get('exact'), 'false')
        self.assertEqual(steps[4].get('name'), "'X4AuthorityPlayerControlOnce.Dispatched'")
        self.assertEqual(steps[4].get('param'), "'%s|%s'.[$v.$request_id,State.$epoch]")

    def test_correlated_read_sequence_and_observation_only_flags(self):
        branch = self.cues['Read'].find('./actions/do_if')
        guard = branch.get('value')
        for value in ('State.$request_id?', '$v.$request_id == State.$request_id', '@$v.$seq == State.$next', 'if $v.$seq == 0 then not State.$attempted',
                      '$v.$seq == 1 or $v.$seq == 2', 'and State.$attempted',
                      'not State.$pending', 'not State.$faulted',
                      'State.$ship.owner == faction.player', 'State.$ship.sector == State.$sector'):
            self.assertIn(value, guard)
        advance, result = list(branch)
        self.assertEqual((advance.get('name'), advance.get('exact')), ('State.$next', 'State.$next + 1'))
        self.assertEqual(result.get('name'), "'X4AuthorityPlayerControlOnce.ReadResult'")
        for part in ('$v.$request_id,State.$epoch,$v.$seq,State.$ship,State.$sector',
                     'if player.ship == State.$ship then 1 else 0',
                     'if player.occupiedship == State.$ship then 1 else 0',
                     'if player.controlled == State.$ship then 1 else 0',
                     'if player.sector == State.$sector then 1 else 0',
                     'if State.$ship.owner == faction.player then 1 else 0,State.$ship.owner.id'):
            self.assertIn(part, result.get('param'))
        self.assertEqual(result.get('param').split("'.[")[0].count('%s'), 11)

    def test_attention_boundary_keeps_full_guard_only_before_transfer(self):
        teleport_guard = self.cues['Teleport'].find('./actions/do_if').get('value')
        self.assertIn('md.X4AuthoritySectorReferenceFixture.State.$ship1.isoperational', teleport_guard)
        self.assertIn('md.X4AuthoritySectorReferenceFixture.State.$ship2.isoperational', teleport_guard)
        read_guard = self.cues['Read'].find('./actions/do_if').get('value')
        phases = read_guard.split('if @$v.$seq == 0 then ', 1)[1]
        before, after = phases.split(' else ', 1)
        self.assertIn('md.X4AuthoritySectorReferenceFixture.State.$ship1.isoperational', before)
        self.assertIn('md.X4AuthoritySectorReferenceFixture.State.$ship2.isoperational', before)
        after = after.split(') and @State.$ship.isoperational', 1)[0]
        self.assertNotIn('State.$ship1', after)
        self.assertNotIn('State.$ship2', after)
        for part in ('not md.X4AuthorityShipRegistry.State.$faulted',
                     'md.X4AuthoritySectorReferenceFixture.State.$sector1.isclass.sector',
                     'md.X4AuthoritySectorReferenceFixture.State.$sector2.isclass.sector'):
            self.assertIn(part, after)

    def test_failure_paths_reply_refused(self):
        for cue in self.cues.values():
            self.assertTrue(cue.findall('.//raise_lua_event[@name="\'X4AuthorityPlayerControlOnce.Refused\'"]'))
        self.assertEqual(self.cues['State'].find('./actions/set_value[@name="$faulted"]').get('exact'), 'true')


if __name__ == '__main__':
    unittest.main()
