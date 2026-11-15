"""Synthetic checks only: these tests never start X4."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/dev'))
import authority_fixture_velocity_live as h


class VelocityTests(unittest.TestCase):
    def test_md_targets_same_guarded_fixture_and_zero_reset(self):
        root=ET.parse(ROOT/'tools/dev/authority_fixture_velocity.xml').getroot()
        cues=root.findall('.//cue');self.assertEqual([x.get('name') for x in cues],['Start','Stop'])
        actions=root.findall('.//set_object_velocity');self.assertEqual(len(actions),2)
        for action in actions:
            self.assertEqual(action.get('object'),'$ship')
        self.assertEqual([a.get('constantvel') for a in actions],['true','false'])
        self.assertEqual(actions[0].find('linear').get('x'),'10m / 1s')
        self.assertEqual(actions[1].find('linear').get('x'),'0m / 1s')
        text=(ROOT/'tools/dev/authority_fixture_velocity.xml').read_text()
        for guard in ('Spawn.$ships.{1}','$ship == $v.$ship','$ship.parent == $v.$parent',
                      '$ship.sector == $v.$sector','player.ship','player.occupiedship','player.container',
                      'not $ship.dock.exists','not $ship.isinternallystored'):
            self.assertEqual(text.count(guard),2)

    def test_order_movement_and_reset_are_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'log'
            def sample(pos='20',stop='20',elapsed='2.1'):
                rows=['LOAD_ARMED','LOAD_REQUEST','LOADED','BEFORE x=0 y=0 z=0',
                      'BASE x=0 y=0 z=0 elapsed=1.1','REQUEST_START','ACK_START',
                      'MOVING1 x=10 y=0 z=0 elapsed=1.1',f'MOVING2 x={pos} y=0 z=0 elapsed=2.1',
                      'REQUEST_STOP','ACK_STOP','STOP1 x=20 y=0 z=0 elapsed=1.1',
                      f'STOP2 x={stop} y=0 z=0 elapsed={elapsed}']
                path.write_text(''.join('[X4LAN] AUTH_VELOCITY '+x+'\n' for x in rows))
                watch=h.VelocityWatch(path);self.assertTrue(watch.poll());return watch
            result=h.check_measurements(sample());self.assertEqual(result['second_motion_displacement_m'],10)
            for args in ({'pos':'10'},{'stop':'25'},{'elapsed':'1.3'},{'stop':'nan'}):
                with self.subTest(args=args),self.assertRaises(ValueError):h.check_measurements(sample(**args))
            path.write_text('[X4LAN] AUTH_VELOCITY REQUEST_START\n')
            with self.assertRaises(ValueError):h.VelocityWatch(path).poll()

    @unittest.skipUnless(shutil.which('luajit'),'requires LuaJIT')
    def test_lua_flow_requests_each_action_once(self):
        script=r'''
local menu=true;local valid=false;local x=0;local now=1;local update;local event={};local logs={};local starts=0;local stops=0
X4LAN_CONFIG={authority_fixture_velocity=true,test_profile='45841',authority_fixture_save_path='/p/45841/save'}
package.loaded.ffi={NULL={},cdef=function() end,typeof=function()return true end,new=function(_,v)return v end,string=function(v)return v end,C={
 IsStartmenu=function()return menu end,IsPlayerValid=function()return valid end,IsSaveListLoadingComplete=function()return true end,
 ReloadSaveList=function()end,GetSaveFolderPath=function()return '/p/45841/save' end,
 IsValidComponent=function()return true end,IsComponentOperational=function()return true end,IsComponentClass=function()return true end,
 GetContextByClass=function(v,k)if v==42 and k=='sector' then return 2 elseif v==42 and k=='zone' then return 3 elseif v==11 and k=='ship' then return 11 else return 0 end end,
 GetObjectPositionInSector=function()return {x=x,y=0,z=0}end,
 GetPlayerControlledShipID=function()return 11 end,GetPlayerOccupiedShipID=function()return 11 end,GetPlayerContainerID=function()return 11 end}}
ConvertStringToLuaID=tonumber;ConvertIDTo64Bit=function(v)return v end
GetComponentData=function()return false,false,false end;GetCurRealTime=function()return now end
GetSaveList=function()return {{filename='save_009'}}end;LoadGame=function(s)assert(s=='save_009')end
RegisterEvent=function(n,f)event[n]=f end;DebugError=function(s)logs[#logs+1]=s end;SetScript=function(_,f)update=f end
AddUITriggeredEvent=function(screen,op,p)
 if op=='RestoreActors' then event['X4LAN_NativeGate.Actor1'](nil,42);event['X4LAN_NativeGate.Restored'](nil,1)
 else assert(p.ship==42 and p.sector==2 and p.parent==3)
  if op=='Start' then starts=starts+1 else assert(op=='Stop');stops=stops+1 end
  event['X4LAN_FixtureVelocity.'..op](nil,'applied')
 end
end
assert(loadfile('tools/dev/authority_fixture_velocity_probe.lua'))();update();update()
menu=false;valid=true;event={};assert(loadfile('tools/dev/authority_fixture_velocity_probe.lua'))()
update();update();now=2.1;update();x=10;now=3.2;update();x=20;now=4.2;update();now=5.3;update();now=6.3;update();update()
assert(starts==1 and stops==1 and #logs==13);assert(logs[13]:find('STOP2',1,true))
'''
        result=subprocess.run(['luajit','-'],input=script,text=True,cwd=ROOT,capture_output=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
