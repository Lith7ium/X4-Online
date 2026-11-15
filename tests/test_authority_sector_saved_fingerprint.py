"""Small synthetic saved-state checks; no game, source archive or processes."""
import gzip
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev'), str(ROOT/'tests')]
from authority.checkpoints import Checkpoint
from test_authority_sector_reference_evidence import document, EPOCH
import authority_sector_saved_fingerprint as subject


def sample():
    return (document().replace('class="sector" id="[0xa]"', 'class="sector" id="[0xa]" code="SEC-001" macro="sector_a"')
        .replace('class="sector" id="[0xb]"', 'class="sector" id="[0xb]" code="SEC-002" macro="sector_b"')
        .replace('class="ship_s" macro="ship_a"', 'class="ship_s" code="SHP-001" macro="ship_a"')
        .replace('class="ship_l" macro="ship_b"', 'class="ship_l" code="SHP-002" macro="ship_b"'))


class SavedFingerprintTest(unittest.TestCase):
    def read(self, text, epoch=EPOCH):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'save.gz'; path.write_bytes(gzip.compress(text.encode()))
            data = path.read_bytes()
            cp = Checkpoint('checkpoint-'+'a'*32, path, hashlib.sha256(data).hexdigest(), len(data))
            return subject.verify(cp, epoch)

    def test_fixture_fingerprints_and_limits(self):
        result = self.read(sample())
        self.assertEqual(result['slots'][0], {'index':1,'ship_saved_id':'1','sector_saved_id':'a',
            'ship_code':'SHP-001','ship_macro':'ship_a','sector_code':'SEC-001','sector_macro':'sector_a'})
        self.assertEqual(result['slots'][1]['sector_macro'],'sector_b')
        self.assertFalse(result['runtime_binding_proven'])
        self.assertFalse(result['cross_process_identity_proven'])

    def test_nested_ship_parent(self):
        ship = '<component class="ship_l" code="SHP-002" macro="ship_b" id="[0x2]"/>'
        nested = '<component class="ship_xl" id="[0xe]"><component class="dockingbay" id="[0xf]">'+ship+'</component></component>'
        self.assertEqual(self.read(sample().replace(ship,nested))['slots'][1]['sector_code'], 'SEC-002')

    def test_ambiguous_target_code_any_component_and_sector_macro(self):
        for text in (sample().replace('</universe>','<component class="station" code="shp-001"/></universe>'),
                     sample().replace('macro="sector_b"','macro="SECTOR_A"'),
                     sample().replace('code="SEC-001"','code=""'),
                     sample().replace('macro="ship_a"','macro="bad macro"')):
            with self.subTest(text=text):
                with self.assertRaises(ValueError): self.read(text)

    def test_existing_reference_checks_are_enforced(self):
        for text,epoch in ((sample(), 'b'*32),
            (sample().replace('name="$sector1" type="component" value="[0xa]"',
                              'name="$sector1" type="component" value="[0xb]"'),EPOCH)):
            with self.assertRaises(ValueError): self.read(text,epoch)


if __name__ == '__main__': unittest.main()
