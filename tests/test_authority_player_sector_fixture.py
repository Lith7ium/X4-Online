"""Offline fixture contracts; no game execution or native spawn assertion."""
import gzip
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_player_sector_evidence as evidence
from authority.checkpoints import Checkpoint
EPOCH='a'*32; MARKER='b'*32


def document():
    return f'''<savegame><universe>
<component class="sector" id="[0xa]"><component class="zone" id="[0xc]"><component class="ship_s" macro="ship_arg_s_fighter_01_a_macro" owner="player" connection="space" id="[0x1]"/></component></component>
<component class="sector" id="[0xb]"><component class="zone" id="[0xd]"><component class="ship_s" macro="ship_arg_s_fighter_01_a_macro" owner="player" connection="space" id="[0x2]"/></component></component>
</universe><script><refs type="string"><ref id="1" string="{EPOCH}"/><ref id="2" string="{MARKER}"/></refs></script><md>
<script name="X4AuthorityPlayerFixtureMarker"><cue name="MarkerState"><vars><value name="$marker" type="string" value="2"/><value name="$loaded" type="integer"/></vars></cue></script>
<script name="X4AuthoritySectorReferenceFixture"><cue name="State"><vars><value name="$epoch" type="string" value="1"/><value name="$sector1" type="component" value="[0xa]"/><value name="$sector2" type="component" value="[0xb]"/></vars></cue></script>
<script name="X4AuthorityPlayerSectorFixture"><cue name="State"><vars><value name="$epoch" type="string" value="1"/><value name="$sector1" type="component" value="[0xa]"/><value name="$sector2" type="component" value="[0xb]"/><value name="$ship1" type="component" value="[0x1]"/><value name="$ship2" type="component" value="[0x2]"/><value name="$ready" type="integer" value="1"/><value name="$pending" type="integer"/><value name="$faulted" type="integer"/></vars></cue></script>
</md></savegame>'''

def registered_document():
    tables = '''<refs type="table"><ref id="3">
<key type="integer" value="1"/><value type="component" value="[0x1]"/>
<key type="integer" value="2"/><value type="component" value="[0x2]"/></ref>
<ref id="4"><key type="component" value="[0x1]"/><value type="integer" value="1"/>
<key type="component" value="[0x2]"/><value type="integer" value="2"/></ref></refs>'''
    state = '''<script name="X4AuthorityShipRegistry"><cue name="State"><vars>
<value name="$ships" type="table" value="3"/><value name="$byship" type="table" value="4"/>
<value name="$last" type="integer" value="2"/><value name="$epoch" type="string" value="1"/>
<value name="$faulted" type="integer"/></vars></cue></script>'''
    return document().replace('</refs></script><md>', '</refs>'+tables+'</script><md>').replace('</md>', state+'</md>')

class FixtureTest(unittest.TestCase):
    def check(self,text,**options):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'save.gz'; data=gzip.compress(text.encode());path.write_bytes(data)
            cp=Checkpoint('checkpoint-'+'c'*32,path,hashlib.sha256(data).hexdigest(),len(data),MARKER)
            return evidence.verify(cp,EPOCH,MARKER,**options)

    def test_md_has_only_two_unpiloted_safepos_spawns_and_one_shot_trigger(self):
        root=ET.parse(ROOT/'tools/dev/authority_player_sector_fixture.xml').getroot()
        cues=root.findall('./cues/cue');self.assertEqual(len(cues),1)
        self.assertNotEqual(cues[0].get('instantiate'),'true')
        self.assertEqual(cues[0].find('./conditions/event_ui_triggered').get('control'),"'Create'")
        ships=root.findall('.//create_ship');self.assertEqual(len(ships),2)
        self.assertEqual([ship.get('sector') for ship in ships],['$sector1','$sector2'])
        for ship in ships:
            self.assertIsNone(ship.find('pilot'));self.assertIsNone(ship.find('position'))
            self.assertEqual(ship.find('owner').get('exact'),'faction.player')
            self.assertEqual(ship.find('safepos').get('includeplotbox'),'true')
        guards=' '.join(node.get('value','') for node in root.iter('do_if'))
        for term in ("player.module == 'custom_creative'",'$ship1.pilot == null','$ship2.pilot == null','$ship2 != $ship1',
                     '$ship1.sector == $sector1','$ship2.sector == $sector2'):
            self.assertIn(term,guards)

    def test_verified_references_are_distinct_player_owned_undocked_and_in_saved_sector(self):
        result=self.check(document());self.assertTrue(result['saved_owner_class_sector_checked'])
        self.assertFalse(result['runtime_seat_proven']);self.assertFalse(result['collision_free_proven'])
        self.assertFalse(result['saved_registry_slot_mapping_checked'])

    def test_fixture_registry_slots_are_verified_without_returning_component_ids(self):
        result=self.check(registered_document(),registry_count=2,fixture_indices=(1,2))
        self.assertTrue(result['saved_registry_slot_mapping_checked'])
        self.assertEqual(set(result), {'saved_slots_checked', 'saved_owner_class_sector_checked',
            'saved_registry_slot_mapping_checked', 'runtime_seat_proven', 'positions_proven',
            'collision_free_proven', 'exact_loaded_file_proven'})
        self.assertEqual(result['saved_slots_checked'],2)

    def test_registry_mapping_requires_correct_slot_order_and_valid_reverse_table(self):
        source=registered_document()
        with self.assertRaises(evidence.registry.RegistryEvidenceError):
            self.check(source,registry_count=2,fixture_indices=(2,1))
        broken=source.replace('<key type="component" value="[0x2]"/><value type="integer" value="2"/>',
                              '<key type="component" value="[0x2]"/><value type="integer" value="1"/>')
        with self.assertRaises(evidence.registry.RegistryEvidenceError):
            self.check(broken,registry_count=2,fixture_indices=(1,2))
        with self.assertRaises(evidence.registry.RegistryEvidenceError):
            self.check(document(),registry_count=2,fixture_indices=(1,2))

    def test_registry_mapping_arguments_must_be_complete_distinct_exact_indices(self):
        for options in ({'registry_count':2}, {'fixture_indices':(1,2)},
                        {'registry_count':2,'fixture_indices':(1,1)},
                        {'registry_count':2,'fixture_indices':(True,2)},
                        {'registry_count':2,'fixture_indices':(1,3)}):
            with self.subTest(options=options), self.assertRaises(evidence.PlayerFixtureEvidenceError):
                self.check(registered_document(),**options)

    def test_rejects_partial_faulted_wrong_owner_duplicate_or_docked_ships(self):
        text=document()
        bad=(text.replace('name="$ready" type="integer" value="1"','name="$ready" type="integer"'),
             text.replace('name="$faulted" type="integer"','name="$faulted" type="integer" value="1"'),
             text.replace('owner="player"','owner="argon"',1),
             text.replace('id="[0x2]"','id="[0x1]"',1),
             text.replace('connection="space"','connection="dock"',1),
             text.replace('class="zone" id="[0xc]"','class="dockingbay" id="[0xc]"'))
        for item in bad:
            with self.subTest():
                with self.assertRaises(evidence.PlayerFixtureEvidenceError): self.check(item)

    def test_rejects_wrong_source_sector_epoch_and_duplicate_fields(self):
        text=document()
        bad=(text.replace('name="$sector2" type="component" value="[0xb]"','name="$sector2" type="component" value="[0xa]"',1),
             text.replace(f'string="{EPOCH}"','string="'+'f'*32+'"'),
             text.replace('name="$ship1" type="component" value="[0x1]"','name="$ship1" type="component" value="[0x1]"/><value name="$ship1" type="component" value="[0x1]"'))
        for item in bad:
            with self.subTest():
                with self.assertRaises(evidence.PlayerFixtureEvidenceError): self.check(item)

    def test_rejects_wrong_saved_marker(self):
        with self.assertRaises(ValueError):
            self.check(document().replace(f'string="{MARKER}"','string="'+'e'*32+'"'))
        with self.assertRaises(ValueError):
            self.check(document().replace('X4AuthorityPlayerFixtureMarker','X4AuthorityCheckpointMarker'))

if __name__=='__main__':unittest.main()
