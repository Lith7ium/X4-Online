"""Synthetic one-shot MD fixture experiment checks; these never start X4."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/dev'))
import authority_fixture_warp_live as h


class WarpExperimentTests(unittest.TestCase):
    def test_one_md_target_and_required_in_cue_guards(self):
        root=ET.parse(ROOT/'tools/dev/authority_fixture_warp.xml').getroot()
        cues=root.findall('.//cue');self.assertEqual(len(cues),1)
        self.assertNotEqual(cues[0].get('instantiate'),'true')
        warps=root.findall('.//warp');self.assertEqual(len(warps),1)
        self.assertEqual(warps[0].get('object'),'$ship')
        self.assertEqual(root.findall('.//set_object_velocity'),[])
        text=(ROOT/'tools/dev/authority_fixture_warp.xml').read_text()
        for check in ('Spawn.$ships.{1}', '$ship == $v.$ship', '$ship.parent == $v.$parent',
                      '$ship.sector == $v.$sector', 'player.ship', 'player.occupiedship',
                      'player.container', 'not $ship.dock.exists', 'not $ship.isinternallystored'):
            self.assertIn(check,text)

    def test_log_order_bounds_and_delayed_position(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'log'
            def run(immediate='10',late='10',elapsed='1.1'):
                rows=['LOAD_ARMED','LOAD_REQUEST','LOADED','BEFORE x=0 y=0 z=0','REQUEST','ACK',
                      f'IMMEDIATE x={immediate} y=0 z=0',f'LATE x={late} y=0 z=0 elapsed={elapsed}']
                path.write_text(''.join('[X4LAN] AUTH_WARP '+x+'\n' for x in rows))
                watch=h.WarpWatch(path);self.assertTrue(watch.poll());return watch
            good=run();self.assertEqual(h.check_measurements(good)['late_displacement_m'],10)
            for pos in ('4','8.9','20','nan'):
                with self.subTest(pos=pos),self.assertRaises(ValueError):
                    h.check_measurements(run(immediate=pos))
            with self.assertRaises(ValueError):run(elapsed='.9')
            with self.assertRaises(ValueError):h.check_measurements(run(late='6.9'))
            path.write_text('[X4LAN] AUTH_WARP REQUEST\n')
            with self.assertRaises(ValueError):h.WarpWatch(path).poll()
            path.write_text('[X4LAN] AUTH_WARP LOAD_ARMED\n[X4LAN] AUTH_WARP ERROR\n')
            with self.assertRaises(ValueError):h.WarpWatch(path).poll()

    def test_only_private_fixture_overlay_and_snapshot_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);case=root/'case';lab=case/'extensions/x4_lan_lab'
            for folder in ('ui','md'):(lab/folder).mkdir(parents=True,exist_ok=True)
            (lab/'ui/config.lua').write_text('old');(lab/'ui/native_gate_snapshot.lua').write_text('old')
            (lab/'md/native_gate_battle.xml').write_text('<md/>')
            profile=root/'profile';(profile/'save').mkdir(parents=True)
            h.install_probe(case,profile)
            text=(lab/'ui.xml').read_text();self.assertIn('authority_fixture_warp_probe',text)
            self.assertNotIn('autostart',text);self.assertNotIn('native_gate_snapshot',text)
            self.assertTrue((lab/'md/native_gate_battle.xml').is_file())
            bundle=root/'bundle';(bundle/'snapshot').mkdir(parents=True)
            data=b'fake fixture gzip';(bundle/'snapshot'/h.snapshot.SLOT).write_bytes(data)
            digest=hashlib.sha256(data).hexdigest()
            manifest={'snapshot_sha256':digest,'files':{'snapshot/'+h.snapshot.SLOT:digest}}
            (bundle/'manifest.json').write_text(json.dumps(manifest))
            with patch.object(h.load,'local_directory',side_effect=lambda x:x),patch.object(h.builder,'snapshot_fixture',return_value=list(range(12))):
                target,actual,ids=h.stage_fixture(bundle,profile)
                self.assertEqual(actual,digest);self.assertEqual(target.read_bytes(),data);self.assertEqual(len(ids),12)
                with self.assertRaises(ValueError):h.stage_fixture(bundle,profile)
                target.unlink();(bundle/'snapshot'/h.snapshot.SLOT).write_bytes(b'changed')
                with self.assertRaises(ValueError):h.stage_fixture(bundle,profile)

    @unittest.skipUnless(shutil.which('luajit'),'requires LuaJIT')
    def test_lua_callback_order_and_exactly_one_request(self):
        script=r'''
local menu=true;local valid=false;local x=0;local now=1;local update;local event={};local logs={};local requests=0
X4LAN_CONFIG={authority_fixture_warp=true,test_profile='45841',authority_fixture_save_path='/p/45841/save'}
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
 else assert(op=='Once' and p.ship==42 and p.sector==2 and p.parent==3 and p.x==10);requests=requests+1;x=10;event['X4LAN_FixtureWarp.Result'](nil,'applied') end
end
assert(loadfile('tools/dev/authority_fixture_warp_probe.lua'))();update();update()
menu=false;valid=true;event={};assert(loadfile('tools/dev/authority_fixture_warp_probe.lua'))()
update();update();update();now=2.1;update();update()
assert(requests==1 and #logs==8);assert(logs[8]:find('LATE',1,true))
'''
        result=subprocess.run(['luajit','-'],input=script,text=True,cwd=ROOT,capture_output=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
