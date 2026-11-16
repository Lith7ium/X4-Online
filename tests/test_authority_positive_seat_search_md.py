"""Static contract checks only: these do not execute X4 MD expressions."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'tools/dev/authority_positive_seat_search.xml'


class PositiveSeatSearchMDTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ET.parse(PATH).getroot()

    def test_opt_in_read_only_one_request_cue(self):
        self.assertEqual(self.root.get('name'), 'X4AuthorityPositiveSeatSearch')
        self.assertEqual({n.tag for n in self.root.iter()}, {
            'mdscript', 'cues', 'cue', 'conditions', 'event_ui_triggered',
            'actions', 'set_value', 'do_if', 'do_else', 'do_all', 'find_ship',
            'raise_lua_event',
        })
        cues = list(self.root.iter('cue'))
        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0].attrib, {'name': 'Read', 'instantiate': 'true'})
        triggers = list(self.root.iter('event_ui_triggered'))
        self.assertEqual([x.attrib for x in triggers], [{
            'screen': "'X4AuthorityPositiveSeatSearch'", 'control': "'Read'"}])
        self.assertTrue(all(n.get('name', '').startswith('$')
                            for n in self.root.iter('set_value')))

    def test_bounded_sorted_zone_search_and_defensive_loop_bound(self):
        finds = list(self.root.iter('find_ship'))
        self.assertEqual(len(finds), 1)
        self.assertEqual(finds[0].attrib, {
            'name': '$ships', 'space': '$zone', 'multiple': 'true',
            'required': 'false', 'sortbydistanceto': 'player.ship', 'sortlimit': '32',
        })
        bounded = [n for n in self.root.iter('do_if')
                   if n.get('value') == '$ships.count <= 32']
        self.assertEqual(len(bounded), 1)
        loops = list(bounded[0].iter('do_all'))
        self.assertEqual([n.attrib for n in loops], [{'exact': '$ships.count', 'counter': '$i'}])
        expressions = ' '.join(n.get('value', '') for n in self.root.iter('do_if'))
        for term in ('@$zone.isclass.zone', 'player.ship.zone == $zone',
                     '$ship.isoperational', '$ship.isclass.ship', '$ship.zone == $zone',
                     '$ship.sector.isclass.sector', '$ship != player.ship',
                     '$ship != player.occupiedship', '$ship != player.container',
                     'not $ship.dock.exists', 'not $ship.isinternallystored',
                     'not $found and not $invalidslot'):
            self.assertIn(term, expressions)

    def test_unsuppressed_getters_and_positive_only_result(self):
        values = [n.get('exact') for n in self.root.iter('set_value')]
        for getter in ('$ship.assignedpilot', '$ship.controlpostslot.{controlpost.aipilot}',
                       '$post.component.slotactor.{$post}'):
            self.assertIn(getter, values)
            self.assertNotIn('@' + getter, values)
        expressions = [n.get('value') for n in self.root.iter('do_if')]
        for required in ('$pilot', '$post and $post.component', '$reserved',
                         '$found and not $invalidslot'):
            self.assertIn(required, expressions)
        self.assertIn(('$invalidslot', 'true'),
                      [(n.get('name'), n.get('exact')) for n in self.root.iter('set_value')])

    def test_correlated_event_contract_and_fail_closed_context(self):
        expressions = ' '.join(n.get('value', '') for n in self.root.iter('do_if'))
        for term in ('md.X4AuthorityShipRegistry.State.$epoch?',
                     'not md.X4AuthorityShipRegistry.State.$faulted', '@$v.$epoch',
                     '@$v.$request_id', '$v.$epoch == md.X4AuthorityShipRegistry.State.$epoch'):
            self.assertIn(term, expressions)
        events = list(self.root.iter('raise_lua_event'))
        result = [n for n in events if n.get('name') == "'X4AuthorityPositiveSeatSearch.Result'"]
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].get('param'),
            "'%s|%s|%s|%s|%s|occupied'.[$v.$request_id,$v.$epoch,$chosen,$sector,$zone]")
        inconclusive = [n for n in events if n.get('name') == "'X4AuthorityPositiveSeatSearch.Inconclusive'"]
        self.assertTrue(inconclusive)
        self.assertTrue(all(n.get('param') == "'%s|%s|inconclusive'.[$v.$request_id,$v.$epoch]"
                            for n in inconclusive))
        refused = [n for n in events if n.get('name') == "'X4AuthorityPositiveSeatSearch.Refused'"]
        self.assertEqual(len(refused), 1)
        self.assertIsNone(refused[0].get('param'))
        self.assertEqual(len(events), len(result) + len(inconclusive) + len(refused))


if __name__ == '__main__':
    unittest.main()
