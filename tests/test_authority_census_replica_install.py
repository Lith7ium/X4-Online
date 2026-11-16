"""Private overlay composition and session wiring; no X4 execution."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'src')]
import authority_census_replica_install as m

class Install(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
    def test_client_session_single_owner_and_injected_modules(self):
        script='''
X4LAN_CONFIG={authority_census_pair=true,authority_census_role='client',authority_census_epoch=string.rep('a',32),authority_census_attempt=string.rep('b',32),authority_census_lease=string.rep('c',32),authority_census_nonce=string.rep('d',32),authority_census_port=1234,authority_census_timeout=300,authority_census_window=30,authority_load_save_path='/tmp/45841/save'}
X4LAN_CENSUS_JOB_OWNER={};X4LAN_CENSUS_JOB_OWNER_X4={};X4LAN_CENSUS_REPLICA_CLIENT={};X4LAN_CENSUS_REPLICA_CLIENT_X4={};X4LAN_AUTHORITY_JOB_REGISTRY_HOST={};X4LAN_AUTHORITY_JOB_REGISTRY_PROBE={};X4LAN_AUTHORITY_PAUSED_JOB_DESCRIPTOR={};X4LAN_AUTHORITY_JOB_DESCRIPTOR_PROBE={};X4LAN_SECTOR_WITNESS_RUNTIME={}
local calls,ticks=0,0
X4LAN_CENSUS_REPLICA_UDP={new_x4=function(c)
 calls=calls+1;assert(c.role=='client' and c.epoch==string.rep('a',32) and c.port==1234 and c.timeout==300)
 assert(c.base_adapter==X4LAN_CENSUS_JOB_OWNER_X4 and c.base_owner==X4LAN_CENSUS_JOB_OWNER and c.replica_adapter==X4LAN_CENSUS_REPLICA_CLIENT_X4 and c.replica_driver==X4LAN_CENSUS_REPLICA_CLIENT and c.witness==X4LAN_SECTOR_WITNESS_RUNTIME and c.guard()==true)
 return {tick=function()ticks=ticks+1;return true end}
end}
DebugError=function()error('unexpected error')end
dofile('tools/dev/authority_census_replica_session.lua');X4LAN_CENSUS_PAIR_TICK();X4LAN_CENSUS_PAIR_TICK();assert(calls==1 and ticks==2)
'''
        subprocess.run(['luajit','-e',script],cwd=ROOT,check=True,capture_output=True,timeout=5)

    def test_replica_installed_only_in_client_and_all_files_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for role in ('server','client'):
                case=Path(tmp)/role/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
                ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
                for p in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',lab/'content.xml',profile/'content.xml',profile/'config.xml'):p.write_text('test')
                ticket=dict(world_epoch='a'*32,connection_handle=1,baseline_id=1,load_generation=1,checkpoint_id=m.base.archive.CHECKPOINT_ID,sha256=m.base.archive.SHA256,attempt_id='b'*32,slot='save_009')
                cfg={'role':role,'epoch':m.base.archive.REGISTRY_EPOCH,'attempt':'c'*32,'lease':'d'*32,'port':12345}
                protected=m.install(case,profile,ticket,cfg,'e'*32,600,60)
                self.assertEqual((ui/'authority_download_load_probe.lua').read_text().count("SetScript('onUpdate'"),1)
                self.assertEqual((md/'authority_identity_fixture.xml').read_bytes(),(ROOT/'tools/dev/authority_identity_fixture.xml').read_bytes())
                for name in m._EXTRA_MD:
                    self.assertEqual((md/name).exists(),role=='client')
                    if role=='client':self.assertIn(md/name,protected)
                for name,_ in m._EXTRA_UI:
                    self.assertEqual((ui/name).exists(),role=='client')
                    if role=='client':self.assertIn(ui/name,protected)
                self.assertEqual((ui/'x4_ship_engine.lua').exists(),role=='client')
                if role=='client':
                    self.assertIn(ui/'x4_ship_engine.lua',protected)
                    self.assertEqual((ui/'authority_census_pair_session.lua').read_bytes(),(ROOT/'tools/dev/authority_census_replica_session.lua').read_bytes())
                    self.assertNotIn('authority_job_ship_events.xml',{p.name for p in md.iterdir()})
                else:
                    self.assertEqual((ui/'authority_census_pair_session.lua').read_bytes(),(ROOT/'tools/dev/authority_census_pair_session.lua').read_bytes())
                    self.assertIn('authority_job_ship_events.xml',{p.name for p in md.iterdir()})
                self.assertIn(ui/'authority_census_pair_session.lua',protected)
                self.assertIn(lab/'ui.xml',protected)

if __name__=='__main__':unittest.main()
