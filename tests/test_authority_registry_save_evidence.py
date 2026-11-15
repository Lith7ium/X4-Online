"""Structural evidence tests on generated gzip/XML, no game or existing saves."""
import gzip
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('authority_registry_save_evidence', ROOT/'tools/dev/authority_registry_save_evidence.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)
EPOCH='a'*32

def xml():
    return f'''<savegame><universe><component class="ship_s" id="[0x1]" macro="ship_a"/><component class="ship_l" id="[0x2]" macro="ship_b"/></universe>
<script><refs type="string"><ref id="1" string="{EPOCH}"/></refs><refs type="list"><ref id="2"/></refs>
<refs type="table"><ref id="2"><key type="integer" value="1"/><value type="component" value="[0x1]"/><key type="integer" value="2"/><value type="component" value="[0x2]"/></ref>
<ref id="3"><key type="component" value="[0x1]"/><value type="integer" value="1"/><key type="component" value="[0x2]"/><value type="integer" value="2"/></ref></refs></script>
<md><script name="X4AuthorityShipRegistry"><cue name="State"><vars><value name="$ships" type="table" value="2"/><value name="$byship" type="table" value="3"/><value name="$last" type="integer" value="2"/><value name="$epoch" type="string" value="1"/><value name="$faulted" type="integer"/></vars></cue></script></md></savegame>'''

class RegistryEvidenceTests(unittest.TestCase):
    def check(self,content,expected=EPOCH,rows=None):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'save.xml.gz';path.write_bytes(gzip.compress(content.encode()))
            raw=path.read_bytes(); checkpoint=M.Checkpoint('checkpoint-'+'a'*32,path,hashlib.sha256(raw).hexdigest(),len(raw))
            return M.verify(checkpoint,expected,2,expected_rows=rows)
    def test_valid(self):
        result=self.check(xml());self.assertEqual(result['unique_saved_components'],2)
        self.assertFalse(result['runtime_binding_proven'])
    def test_indexed_macros_must_match(self):
        result=self.check(xml(),rows=[(1,'ship_a'),(2,'ship_b')])
        self.assertTrue(result['macro_rows_checked'])
        with self.assertRaises(M.RegistryEvidenceError):
            self.check(xml(),rows=[(1,'ship_b'),(2,'ship_a')])
        with self.assertRaises(M.RegistryEvidenceError):
            self.check(xml(),rows=[(1,'ship_a'),(2,'wrong')])
    def test_wrong_epoch(self):
        with self.assertRaises(M.RegistryEvidenceError): self.check(xml(),'b'*32)
    def test_duplicate_component_and_bad_reverse(self):
        with self.assertRaises(M.RegistryEvidenceError):
            self.check(xml().replace('<value type="component" value="[0x2]"/>','<value type="component" value="[0x1]"/>',1))
        with self.assertRaises(M.RegistryEvidenceError):
            self.check(xml().replace('<key type="component" value="[0x2]"/><value type="integer" value="2"/>','<key type="component" value="[0x2]"/><value type="integer" value="1"/>'))
    def test_missing_or_wrong_class(self):
        with self.assertRaises(M.RegistryEvidenceError): self.check(xml().replace('class="ship_l"','class="station"'))
        with self.assertRaises(M.RegistryEvidenceError): self.check(xml().replace('id="[0x2]" macro="ship_b"','id="[0x3]" macro="ship_b"'))
    def test_ambiguous_duplicate_table_reference(self):
        with self.assertRaises(M.RegistryEvidenceError): self.check(xml().replace('</refs></script>', '<ref id="2"/></refs></script>'))

    def test_sector_ancestor_and_nested_dockingbay(self):
        source=xml().replace(
            '<component class="ship_s" id="[0x1]" macro="ship_a"/><component class="ship_l" id="[0x2]" macro="ship_b"/>',
            '<component class="sector" id="[0xa]" macro="sector_a"><component class="zone" id="[0xb]">'
            '<component class="ship_s" id="[0x1]" macro="ship_a"/>'
            '<component class="ship_xl" id="[0xc]"><component class="dockingbay" id="[0xd]">'
            '<component class="ship_l" id="[0x2]" macro="ship_b"/>'
            '</component></component></component></component>')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'save.xml.gz';path.write_bytes(gzip.compress(source.encode()))
            data=path.read_bytes(); checkpoint=M.Checkpoint('checkpoint-'+'a'*32,path,hashlib.sha256(data).hexdigest(),len(data))
            result=M.verify(checkpoint,EPOCH,2,include_sector_parents=True)
        self.assertEqual(result['saved_sector_ancestor_count'],1)
        self.assertEqual(result['ships_with_sector_ancestor'],2)
        self.assertEqual(result['ships_with_zone_ancestor'],2)
        self.assertEqual(result['ships_with_non_zone_component_parent'],1)
        self.assertEqual(result['ships_under_dockingbay'],1)
        self.assertFalse(result['sector_runtime_mapping_proven'])

    def test_missing_sector_is_reported_not_fabricated(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'save.xml.gz';path.write_bytes(gzip.compress(xml().encode()))
            data=path.read_bytes(); checkpoint=M.Checkpoint('checkpoint-'+'a'*32,path,hashlib.sha256(data).hexdigest(),len(data))
            result=M.verify(checkpoint,EPOCH,2,include_sector_parents=True)
        self.assertEqual(result['ships_without_sector_ancestor'],2)

if __name__=='__main__': unittest.main()
