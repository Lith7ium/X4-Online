"""Static contract only: these tests do not execute X4 or its MD expressions."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'tools/dev/authority_player_flight_observer.xml'
CONTROL = 'md.X4AuthorityPlayerControlOnce.State.'
SECTORS = 'md.X4AuthoritySectorReferenceFixture.State.'
REGISTRY = 'md.X4AuthorityShipRegistry.State.'
REFUSED = "'X4AuthorityPlayerFlightObserver.Refused'"


class PlayerFlightObserverMDTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ET.parse(PATH).getroot()
        cls.cue = cls.root.find('./cues/cue')

    def test_explicit_event_and_read_only_actions(self):
        self.assertEqual(self.root.get('name'), 'X4AuthorityPlayerFlightObserver')
        self.assertEqual(len(self.root.findall('./cues/cue')), 1)
        self.assertEqual(self.cue.attrib, {'name': 'Read', 'instantiate': 'true'})
        self.assertEqual(self.cue.find('./conditions/event_ui_triggered').attrib, {
            'screen': "'X4AuthorityPlayerFlightObserver'", 'control': "'Read'"})
        self.assertEqual({e.tag for e in self.root.iter()}, {
            'mdscript', 'cues', 'cue', 'conditions', 'event_ui_triggered',
            'actions', 'set_value', 'do_if', 'do_else', 'raise_lua_event'})
        setters = list(self.root.iter('set_value'))
        self.assertEqual(len(setters), 1)
        self.assertEqual(setters[0].attrib, {'name': '$v', 'exact': 'event.param3'})

    def test_guard_chain_and_one_refusal_per_failed_guard(self):
        actions = self.cue.find('./actions')
        self.assertEqual(actions[0].tag, 'set_value')
        current = actions
        expressions = []
        while True:
            children = list(current)
            branches = [i for i, child in enumerate(children) if child.tag == 'do_if']
            if not branches:
                break
            self.assertEqual(len(branches), 1)
            index = branches[0]
            self.assertEqual(index + 2, len(children))
            branch, failure = children[index:index + 2]
            self.assertEqual(failure.tag, 'do_else')
            self.assertEqual(len(failure), 1)
            self.assertEqual(failure[0].tag, 'raise_lua_event')
            self.assertEqual(failure[0].attrib, {'name': REFUSED})
            expression = branch.get('value')
            self.assertLessEqual(expression.count(' and ') + expression.count(' or ') + 1, 8)
            expressions.append(expression)
            current = branch

        self.assertEqual(len(expressions), 6)
        guards = [part for expression in expressions for part in expression.split(' and ')]
        for term in (
            '@$v.$request_id', '@$v.$epoch', '(@$v.$seq == 1 or @$v.$seq == 2 or @$v.$seq == 3)',
            *(CONTROL + '$' + name + '?' for name in ('ready', 'faulted', 'pending', 'attempted', 'next', 'epoch', 'ship', 'sector')),
            CONTROL + '$ready', 'not ' + CONTROL + '$faulted', 'not ' + CONTROL + '$pending',
            CONTROL + '$attempted', CONTROL + '$next == 3',
            SECTORS + '$epoch?', REGISTRY + '$epoch?', REGISTRY + '$faulted?', 'not ' + REGISTRY + '$faulted',
            '$v.$epoch == ' + CONTROL + '$epoch', '$v.$epoch == ' + SECTORS + '$epoch', '$v.$epoch == ' + REGISTRY + '$epoch',
            '@' + CONTROL + '$ship.isoperational', CONTROL + '$ship.isclass.ship',
            CONTROL + '$ship.owner == faction.player', CONTROL + '$ship.sector == ' + CONTROL + '$sector',
            'player.sector == ' + CONTROL + '$sector', CONTROL + '$ship == player.ship',
            CONTROL + '$ship == player.occupiedship', CONTROL + '$ship == player.controlled',
            '@' + CONTROL + '$ship.parent.isclass.zone', 'not ' + CONTROL + '$ship.dock.exists',
            'not ' + CONTROL + '$ship.isinternallystored',
        ):
            self.assertIn(term, guards)
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0].tag, 'raise_lua_event')
        self.assertEqual(current[0].attrib, {
            'name': "'X4AuthorityPlayerFlightObserver.Result'",
            'param': "'%s|%s|%s|%s|%s|%s|%s'.[$v.$request_id,$v.$epoch,$v.$seq,"
                     + CONTROL + '$ship,' + CONTROL + '$sector,' + CONTROL + '$ship.parent,'
                     + CONTROL + '$ship.owner.id]',
        })


if __name__ == '__main__':
    unittest.main()
