"""Static safety contract for private X4 control, not MD execution evidence."""
from pathlib import Path
import hashlib
import unittest
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'tools/dev/authority_player_control_once.xml'
REFUSED="'X4AuthorityPlayerControlOnce.Refused'"
# Digests are from the pre-staging ordered atomic guards; they prevent lost,
# reordered or added conditions even if individual statements remain present.
GUARDS={
 'create':(36,'7e720c58b97e6dd2206586d82eecc52492c9959577518a3837056428aa196e4f'),
 'created':(12,'5e9f9ecd342ec52285c21f0c7ee8b0cc0d743d66aee9e96498a1ce91d3cc7c11'),
 'teleport':(63,'d4f5511607d2babd1b77a0971c375395a04e1b33aa96301728336017d6dd8d7d'),
 'read_pre':(15,'18cac7fe67d3edb54ab6b938ffd9d4253f0a4e50445f3ff43177d54a8ccd3258'),
 'read_seq0':(34,'551e31aab708cbdf428f21eba3ad60fe619f9ef67162e341a9ac939068e5f35f'),
 'read_seq12':(11,'35f1c0b12e720585ce5af00291accdab46c3a41017fd389f04c8ea4dcef776db'),
 'read_after':(11,'3cfa4286dea1e41e7386dd651b59e0e00cca5ca11d29c34e631be539fcee2e39'),
}

def split_and(expr):
    items=[];depth=0;quote=None;start=0;i=0
    while i<len(expr):
        c=expr[i]
        if quote:
            if c==quote:quote=None
        elif c in "'\"":quote=c
        elif c=='(':depth+=1
        elif c==')':depth-=1
        elif depth==0 and expr[i:i+5]==' and ':
            items.append(expr[start:i]);i+=5;start=i;continue
        i+=1
    if depth or quote:raise AssertionError('unbalanced expression')
    return items+[expr[start:]]

class PlayerControlOnceMDTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=ET.parse(PATH).getroot()
        cls.cues={cue.get('name'):cue for cue in cls.root.findall('./cues/cue')}

    def chain(self,parent,name):
        count,digest=GUARDS[name];values=[];cur=parent
        for n in range((count+7)//8):
            children=list(cur);branch=next((x for x in children if x.tag=='do_if'),None)
            self.assertIsNotNone(branch,(name,n))
            idx=children.index(branch);self.assertLess(idx+1,len(children),(name,n))
            failure=children[idx+1];self.assertEqual(failure.tag,'do_else')
            self.assertEqual([(x.tag,x.get('name')) for x in failure], [('raise_lua_event',REFUSED)])
            group=split_and(branch.get('value'));self.assertLessEqual(len(group),8)
            values.extend(group);cur=branch
        self.assertEqual(len(values),count,name)
        self.assertEqual(hashlib.sha256('\n'.join(values).encode()).hexdigest(),digest,name)
        return cur

    def test_only_explicit_one_shot_mutations(self):
        self.assertEqual(self.root.get('name'),'X4AuthorityPlayerControlOnce')
        self.assertEqual(set(self.cues),{'State','Teleport','Read'})
        self.assertIsNone(self.cues['State'].get('instantiate'))
        for name,control in [('State','Create'),('Teleport','Teleport'),('Read','Read')]:
            trigger=self.cues[name].find('./conditions/event_ui_triggered')
            self.assertEqual(trigger.get('screen'),"'X4AuthorityPlayerControlOnce'")
            self.assertEqual(trigger.get('control'),"'"+control+"'")
        self.assertEqual(len(list(self.root.iter('create_ship'))),1)
        teleport=list(self.root.iter('teleport_player'));self.assertEqual(len(teleport),1)
        self.assertEqual(teleport[0].attrib,{'object':'State.$ship','control':'true','instant':'true','force':'true'})
        self.assertFalse(list(self.root.iter('save_game')))
        for branch in self.root.iter('do_if'):
            self.assertLessEqual(branch.get('value','').count(' and '),10)

    def test_create_order_and_exact_preexisting_guards(self):
        cue=self.cues['State'];self.assertEqual(cue.find('./actions/set_value[@name="$faulted"]').get('exact'),'true')
        innermost=self.chain(cue.find('./actions'),'create')
        children=list(innermost);ship=next(x for x in children if x.tag=='create_ship')
        self.assertEqual(ship.get('macro'),'macro.ship_arg_s_fighter_01_a_macro')
        self.assertEqual(ship.find('owner').get('exact'),'faction.player');self.assertIsNotNone(ship.find('safepos'))
        self.assertLess(next(i for i,x in enumerate(children) if x.get('name')=='$pending' and x.get('exact')=='true'),children.index(ship))
        verified=self.chain(innermost,'created')
        self.assertEqual([x.get('name') for x in verified if x.tag=='set_value'],['$next','$pending','$faulted','$ready'])
        self.assertEqual(verified.find('./raise_lua_event').get('name'),"'X4AuthorityPlayerControlOnce.Created'")
        self.assertNotIn('pilot',ET.tostring(cue,encoding='unicode'))

    def test_teleport_guards_flags_and_markers(self):
        branch=self.chain(self.cues['Teleport'].find('./actions'),'teleport')
        steps=list(branch)
        self.assertEqual([(x.tag,x.get('name'),x.get('exact')) for x in steps[:2]],[('set_value','State.$pending','true'),('set_value','State.$attempted','true')])
        self.assertEqual(steps[2].attrib,{'text':"'[X4LAN] AUTH_PLAYER_CONTROL_MD ACTION_BEGIN'"})
        self.assertEqual(steps[2].tag,'debug_text');self.assertEqual(steps[3].tag,'teleport_player')
        self.assertEqual(steps[4].tag,'debug_text');self.assertEqual(steps[4].get('text'),"'[X4LAN] AUTH_PLAYER_CONTROL_MD ACTION_RETURNED'")
        self.assertEqual((steps[5].get('name'),steps[5].get('exact')),('State.$pending','false'))
        self.assertEqual((steps[6].get('name'),steps[6].get('param')),("'X4AuthorityPlayerControlOnce.Dispatched'","'%s|%s'.[$v.$request_id,State.$epoch]"))
        self.assertEqual(len(steps),7)

    def test_read_before_and_after_teleport_have_exact_guards_and_common_result(self):
        pre=self.chain(self.cues['Read'].find('./actions'),'read_pre');children=list(pre)
        self.assertEqual((children[0].tag,children[0].get('name'),children[0].get('exact')),('set_value','$phase_ok','false'))
        select,other,gate=children[1:]
        self.assertEqual((select.tag,select.get('value')),('do_if','@$v.$seq == 0'))
        self.assertEqual(other.tag,'do_else')
        for name,parent in [('read_seq0',select),('read_seq12',other)]:
            branch=self.chain(parent,name);self.assertEqual([(x.tag,x.get('name'),x.get('exact')) for x in branch],[('set_value','$phase_ok','true')])
        self.assertEqual((gate.tag,gate.get('value')),('do_if','$phase_ok'))
        result=self.chain(gate,'read_after');steps=list(result)
        self.assertEqual(len(steps),2);self.assertEqual((steps[0].get('name'),steps[0].get('exact')),('State.$next','State.$next + 1'))
        self.assertEqual(steps[1].get('name'),"'X4AuthorityPlayerControlOnce.ReadResult'")
        for part in ('$v.$request_id,State.$epoch,$v.$seq,State.$ship,State.$sector',
                     'if player.ship == State.$ship then 1 else 0','if player.occupiedship == State.$ship then 1 else 0',
                     'if player.controlled == State.$ship then 1 else 0','if player.sector == State.$sector then 1 else 0',
                     'if State.$ship.owner == faction.player then 1 else 0,State.$ship.owner.id'):
            self.assertIn(part,steps[1].get('param'))
        self.assertEqual(steps[1].get('param').split("'.[")[0].count('%s'),11)

if __name__=='__main__':unittest.main()
