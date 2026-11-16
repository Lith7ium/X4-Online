"""Structural checks only; MD execution and actor formatting still need X4."""
from collections import Counter
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / 'tools/dev/authority_ship_registry.xml'


class CorrelatedRegistryMD(unittest.TestCase):
    def test_every_legacy_response_has_a_matching_correlated_branch(self):
        root = ET.parse(MD).getroot()
        seen = Counter()
        for parent in root.iter():
            children = list(parent)
            for i, child in enumerate(children):
                if child.tag != 'do_if' or child.get('value') != 'event.param3.$request_id?':
                    continue
                self.assertLess(i + 1, len(children))
                legacy = children[i + 1]
                self.assertEqual(legacy.tag, 'do_else')
                self.assertEqual(len(child), 1)
                self.assertEqual(len(legacy), 1)
                new_event, old_event = child[0], legacy[0]
                self.assertEqual(new_event.tag, 'raise_lua_event')
                self.assertEqual(old_event.tag, 'raise_lua_event')
                self.assertEqual(new_event.get('name'), "'X4AuthorityShipRegistry.Correlated'")
                old_name = old_event.get('name')
                self.assertTrue(old_name.startswith("'X4AuthorityShipRegistry."))
                kind = old_name.split('.')[-1].rstrip("'")
                expression = new_event.get('param')
                self.assertIn('|'+kind+'|', expression)
                self.assertIn('event.param3.$request_id', expression)
                old_param = old_event.get('param')
                if old_param is not None:
                    self.assertIn(','+old_param+']', expression)
                seen[kind] += 1
        self.assertEqual(seen, Counter({'Initialized':1, 'Faulted':1, 'Epoch':1,
                                        'Count':1, 'Uninitialized':1, 'Enrolled':2,
                                        'Refused':3, 'Actor':1, 'Unavailable':2}))

if __name__ == '__main__':
    unittest.main()
