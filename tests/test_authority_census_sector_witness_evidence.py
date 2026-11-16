"""Synthetic gzip/XML evidence only; no archived census or X4 execution."""
import gzip
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
from authority.checkpoints import Checkpoint
import authority_census_sector_witness_evidence as subject

EPOCH='a'*32


def xml():
    return f'''<savegame><universe>
<component class="sector" id="[0xa]" macro="sector_a"><component class="zone" id="[0xb]">
<component class="ship_s" id="[0x1]" macro="ship_a"/>
<component class="ship_xl" id="[0xc]"><component class="dockingbay" id="[0xd]">
<component class="ship_l" id="[0x2]" macro="ship_b"/></component></component>
<component class="ship_s" id="[0x99]" macro="unregistered"/></component></component>
<component class="sector" id="[0xe]" macro="sector_b"><component class="zone" id="[0xf]">
<component class="ship_s" id="[0x3]" macro="ship_c"/></component></component></universe>
<script><refs type="string"><ref id="1" string="{EPOCH}"/></refs><refs type="table">
<ref id="2"><key type="integer" value="1"/><value type="component" value="[0x1]"/><key type="integer" value="2"/><value type="component" value="[0x2]"/><key type="integer" value="3"/><value type="component" value="[0x3]"/></ref>
<ref id="3"><key type="component" value="[0x1]"/><value type="integer" value="1"/><key type="component" value="[0x2]"/><value type="integer" value="2"/><key type="component" value="[0x3]"/><value type="integer" value="3"/></ref>
</refs></script><md><script name="X4AuthorityShipRegistry"><cue name="State"><vars>
<value name="$ships" type="table" value="2"/><value name="$byship" type="table" value="3"/><value name="$last" type="integer" value="3"/><value name="$epoch" type="string" value="1"/><value name="$faulted" type="integer"/>
</vars></cue></script></md></savegame>'''


class CensusWitness(unittest.TestCase):
    def checkpoint(self,content):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        path=Path(temp.name)/'save.gz';path.write_bytes(gzip.compress(content.encode()))
        raw=path.read_bytes();return Checkpoint('checkpoint-'+'a'*32,path,hashlib.sha256(raw).hexdigest(),len(raw))

    def extract(self,content,macro='sector_a'):
        checkpoint=self.checkpoint(content)
        return subject._extract(checkpoint,macro,3,sector_count=2)

    def test_selected_sector_and_saved_registry_indices(self):
        cp=self.checkpoint(xml())
        self.assertTrue(subject.registry.verify(cp,EPOCH,3)['forward_reverse_match'])
        result=subject._extract(cp,'sector_a',3,sector_count=2)
        self.assertEqual(result['sector_saved_component_ref'],'[0xa]')
        self.assertEqual(result['witnesses'],[
            {'index':1,'saved_under_dockingbay':False,'saved_immediate_parent_zone':True},
            {'index':2,'saved_under_dockingbay':True,'saved_immediate_parent_zone':False}])
        self.assertFalse(result['runtime_binding_proven'])
        self.assertFalse(result['cross_instance_frame_identity_proven'])
        self.assertEqual(self.extract(xml(),'sector_b')['witnesses'][0]['index'],3)

    def test_all_sectors_share_two_digest_checked_passes(self):
        cp=self.checkpoint(xml())
        with patch.object(subject,'_parse',wraps=subject._parse) as parse:
            result=subject._extract(cp,None,3,sector_count=2)
        self.assertEqual(parse.call_count,2)
        self.assertEqual([row['sector_macro'] for row in result['sectors']],['sector_a','sector_b'])
        self.assertEqual([[row['index'] for row in sector['witnesses']] for sector in result['sectors']],[[1,2],[3]])
        self.assertEqual(result['registry_entries_without_sector_witness'],0)
        self.assertFalse(result['cross_instance_frame_identity_proven'])

    def test_all_sectors_report_empty_and_unassigned_without_fabrication(self):
        ship='<component class="ship_s" id="[0x3]" macro="ship_c"/>'
        content=xml().replace(ship,'').replace('</universe>',ship+'</universe>')
        cp=self.checkpoint(content)
        self.assertTrue(subject.registry.verify(cp,EPOCH,3)['forward_reverse_match'])
        result=subject._extract(cp,None,3,sector_count=2)
        self.assertEqual(result['sectors'][1]['witnesses'],[])
        self.assertEqual(result['registry_entries_without_sector_witness'],1)

    def test_all_sectors_fail_closed_on_collision_and_resource_bound(self):
        variants=[
            xml().replace('id="[0x99]" macro="unregistered"','id="[0X0E]" macro="unregistered"'),
            xml().replace('id="[0x1]" macro="ship_a"','id="[0x1]" macro="ship_a"/><component class="station" id="[0X03]"'),
            xml().replace('macro="sector_b"','macro="SECTOR_A"'),
        ]
        for content in variants:
            with self.subTest(content=content),self.assertRaises(ValueError):
                subject._extract(self.checkpoint(content),None,3,sector_count=2)
        with patch.object(subject,'_MAX_SHIPS',3):
            with self.assertRaisesRegex(ValueError,'excessive saved ships'):
                subject._extract(self.checkpoint(xml()),None,3,sector_count=2)
        self.assertEqual(subject._component('[0x000a]'),'a')
        with self.assertRaises(ValueError):subject._component('[0x10000000000000000]')

    def test_verify_all_uses_one_provenance_check_and_one_all_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Path(tmp)/'checkpoints';path=store/subject.archive.CHECKPOINT_ID/'save.xml.gz'
            cp=Checkpoint(subject.archive.CHECKPOINT_ID,path,subject.archive.SHA256,subject.archive.SIZE)
            evidence={'checkpoint_id':cp.checkpoint_id,'sha256':cp.sha256,'registry_epoch':EPOCH}
            with patch.object(subject.archive,'fingerprints',return_value={}), \
                 patch.object(subject.archive,'verify',return_value=evidence) as provenance, \
                 patch.object(subject,'_pointer',return_value='same'), \
                 patch.object(subject,'CheckpointStore') as factory, \
                 patch.object(subject,'_extract',return_value={'sectors':[]}) as extract:
                factory.return_value.latest_confirmed.return_value=cp
                result=subject.verify_all(store)
            provenance.assert_called_once_with(store)
            extract.assert_called_once_with(cp,None,subject.archive.COUNT)
            self.assertEqual(result['registry_epoch'],EPOCH)

    def test_ambiguous_or_missing_sector_and_component_refs_fail(self):
        variants=[
            xml().replace('macro="sector_b"','macro="SECTOR_A"'),
            xml().replace('id="[0xe]" macro="sector_b"','id="[0x0a]" macro="sector_b"'),
            xml().replace('id="[0x99]" macro="unregistered"','id="[0xa]" macro="unregistered"'),
            xml().replace('id="[0x99]" macro="unregistered"','id="[0X0A]" macro="unregistered"'),
            xml().replace('id="[0x2]" macro="ship_b"','id="[0x1]" macro="ship_b"'),
            xml().replace('id="[0x3]" macro="ship_c"','id="[0x1]" macro="ship_c"'),
            xml().replace('id="[0x3]" macro="ship_c"','id="[0x3]" macro="ship_c"/><component class="station" id="[0X01]"'),
            xml().replace('macro="sector_b"','macro=""'),
            xml().replace('id="[0xa]" macro="sector_a"','id="[broken]" macro="sector_a"'),
            xml().replace('<value name="$ships" type="table" value="2"/>',''),
            xml().replace('<key type="integer" value="3"/><value type="component" value="[0x3]"/>',''),
            xml().replace('<key type="integer" value="3"/><value type="component" value="[0x3]"/>',
                          '<key type="integer" value="2"/><value type="component" value="[0x3]"/>'),
        ]
        for content in variants:
            with self.subTest(content=content),self.assertRaises(ValueError):self.extract(content)
        with self.assertRaises(ValueError):self.extract(xml(),'no_such_sector')
        content=xml().replace('macro="sector_b"','macro="sector_c"').replace('id="[0x3]" macro="ship_c"','id="[0x4]" macro="ship_c"')
        with self.assertRaisesRegex(ValueError,'no saved registry witness'):self.extract(content,'sector_c')

    def test_digest_change_rejected(self):
        cp=self.checkpoint(xml());cp.path.write_bytes(gzip.compress(xml().replace('ship_a','ship_z').encode()))
        with self.assertRaises(ValueError):subject._extract(cp,'sector_a',3,sector_count=2)

    def test_witness_collision_in_other_component_is_rejected_after_registry_verification(self):
        source=xml().replace('id="[0x3]" macro="ship_c"',
            'id="[0x3]" macro="ship_c"/><component class="station" id="[0X01]"')
        cp=self.checkpoint(source)
        self.assertTrue(subject.registry.verify(cp,EPOCH,3)['forward_reverse_match'])
        with self.assertRaisesRegex(ValueError,'witness component ID is ambiguous'):
            subject._extract(cp,'sector_a',3,sector_count=2)

    def test_verified_archive_is_required_before_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Path(tmp)/'checkpoints';store.mkdir()
            with patch.object(subject.archive,'fingerprints',return_value={}), \
                 patch.object(subject.archive,'verify',side_effect=ValueError('archive invalid')), \
                 patch.object(subject,'_extract') as extract:
                with self.assertRaisesRegex(ValueError,'archive invalid'):subject.verify(store,'sector_a')
                extract.assert_not_called()

if __name__=='__main__':unittest.main()
