"""Synthetic saved-XML checks; no X4 game or user save is used."""
import gzip
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('sector_evidence', ROOT/'tools/dev/authority_sector_reference_evidence.py')
M = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(M)
EPOCH = 'a'*32


def document():
    return f'''<savegame><universe>
<component class="sector" id="[0xa]"><component class="zone" id="[0xc]"><component class="ship_s" macro="ship_a" id="[0x1]"/></component></component>
<component class="sector" id="[0xb]"><component class="zone" id="[0xd]"><component class="ship_l" macro="ship_b" id="[0x2]"/></component></component>
</universe><script><refs type="string"><ref id="1" string="{EPOCH}"/></refs><refs type="table">
<ref id="2"><key type="integer" value="1"/><value type="component" value="[0x1]"/><key type="integer" value="2"/><value type="component" value="[0x2]"/></ref>
<ref id="3"><key type="component" value="[0x1]"/><value type="integer" value="1"/><key type="component" value="[0x2]"/><value type="integer" value="2"/></ref>
</refs></script><md><script name="X4AuthorityShipRegistry"><cue name="State"><vars>
<value name="$ships" type="table" value="2"/><value name="$byship" type="table" value="3"/><value name="$last" type="integer" value="2"/><value name="$epoch" type="string" value="1"/><value name="$faulted" type="integer"/>
</vars></cue></script><script name="X4AuthoritySectorReferenceFixture"><cue name="State"><vars>
<value name="$epoch" type="string" value="1"/><value name="$index1" type="integer" value="1"/><value name="$index2" type="integer" value="2"/>
<value name="$ship1" type="component" value="[0x1]"/><value name="$ship2" type="component" value="[0x2]"/>
<value name="$sector1" type="component" value="[0xa]"/><value name="$sector2" type="component" value="[0xb]"/>
</vars></cue></script></md></savegame>'''


class SectorEvidenceTest(unittest.TestCase):
    def check(self, text, epoch=EPOCH):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'save.xml.gz'; path.write_bytes(gzip.compress(text.encode()))
            raw = path.read_bytes()
            cp = M.registry.Checkpoint('checkpoint-'+'a'*32, path, hashlib.sha256(raw).hexdigest(), len(raw))
            return M.verify(cp, epoch)

    def test_matching_slots(self):
        result = self.check(document())
        self.assertEqual(result['slots_checked'], 2)
        self.assertTrue(result['saved_ship_sector_ancestry_matches'])
        self.assertFalse(result['runtime_binding_proven'])

    def test_native_largefloat_indices_and_fraction_rejection(self):
        text = document().replace('name="$index1" type="integer"', 'name="$index1" type="largefloat"').replace('name="$index2" type="integer"', 'name="$index2" type="largefloat"')
        self.assertTrue(self.check(text)['saved_ship_sector_ancestry_matches'])
        with self.assertRaises(M.SectorEvidenceError):
            self.check(text.replace('name="$index1" type="largefloat" value="1"', 'name="$index1" type="largefloat" value="1.5"'))

    def test_crossed_sector_slots_are_refused(self):
        text = document().replace('name="$sector1" type="component" value="[0xa]"', 'name="$sector1" type="component" value="[0xb]"').replace('name="$sector2" type="component" value="[0xb]"', 'name="$sector2" type="component" value="[0xa]"')
        with self.assertRaises(M.SectorEvidenceError): self.check(text)

    def test_nested_carrier_and_dockingbay_keep_sector_ancestor(self):
        ship = '<component class="ship_l" macro="ship_b" id="[0x2]"/>'
        nested = ('<component class="ship_xl" macro="carrier" id="[0xe]">'
                  '<component class="dockingbay" id="[0xf]">' + ship + '</component></component>')
        result = self.check(document().replace(ship, nested))
        self.assertTrue(result['saved_ship_sector_ancestry_matches'])

    def test_duplicate_sector_or_registry_mismatch_is_refused(self):
        with self.assertRaises(M.SectorEvidenceError):
            self.check(document().replace('name="$sector2" type="component" value="[0xb]"', 'name="$sector2" type="component" value="[0xa]"'))
        with self.assertRaises(M.SectorEvidenceError):
            self.check(document().replace('name="$index1" type="integer" value="1"', 'name="$index1" type="integer" value="2"').replace('name="$index2" type="integer" value="2"', 'name="$index2" type="integer" value="1"'))

    def test_missing_and_duplicate_components_are_refused(self):
        with self.assertRaises(M.SectorEvidenceError):
            self.check(document().replace('id="[0xb]"', 'id="[0xe]"', 1))
        with self.assertRaises(M.SectorEvidenceError):
            self.check(document().replace('</universe>', '<component class="sector" id="[0xa]"/></universe>'))

    def test_fixture_epoch_and_fields_must_be_unambiguous(self):
        with self.assertRaises(M.SectorEvidenceError):
            self.check(document().replace('name="$sector1" type="component" value="[0xa]"', 'name="$sector1" type="component" value="[0xa]"/><value name="$sector1" type="component" value="[0xa]"'))
        with self.assertRaises(M.SectorEvidenceError):
            self.check(document().replace('name="$epoch" type="string" value="1"/><value name="$index1"', 'name="$epoch" type="string" value="4"/><value name="$index1"'))


if __name__ == '__main__': unittest.main()
