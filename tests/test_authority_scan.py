import os
import gzip
import hashlib
import json
import tempfile
import sys
import contextlib
import io
from unittest import mock
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
LUAJIT = shutil.which('luajit')

FIXTURE = r'''
local scan = assert(loadfile('src/authority/lua/ship_scan.lua'))()
local calls = 0
local data = {a={'a1','a2'}, b={'b1'}}
local e = {
 factions=function(cap) return {'a','b'},false end,
 fleet_count=function(f) return #data[f] end,
 fleet=function(f,cap) local out={} for _,v in ipairs(data[f]) do out[#out+1]=v end return out,false end,
 key=function(h) return h or '' end,
 operational=function(h) return true end,
 is_ship=function(h) return true end,
 sector=function(h) return 'sector' end,
 pose=function(h) return {x=1,y=2,z=3,yaw=.1,pitch=.2,roll=.3} end,
}
local ids = {ship=function(h) return 'ship:'..h end, sector=function(h) return 'save:sector' end}
'''

@unittest.skipUnless(LUAJIT, 'LuaJIT is required')
class ShipScanTests(unittest.TestCase):
    def run_lua(self, body):
        p = subprocess.run([LUAJIT, '-'], input=FIXTURE + body, text=True, cwd=ROOT,
                           capture_output=True, env=os.environ.copy())
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_success_returns_only_explicit_identities_and_pose(self):
        self.run_lua('''
local r, err=scan.scan(e,ids)
assert(r,err); assert(r.consistency=='membership_rechecked_non_atomic' and #r.rows==3)
assert(r.rows[1].id=='ship:a1' and r.rows[1].sector=='save:sector')
assert(r.rows[1].pose.x==1 and r.rows[1].pose.roll==.3 and r.rows[1].object==nil)
''')

    def test_rejects_incomplete_and_changing_membership(self):
        self.run_lua('''
local original=e.factions
 e.factions=function(cap) return {'a','b'},true end
local r,err=scan.scan(e,ids); assert(not r and err:find('incomplete'))
e.factions=original
local fleet=e.fleet
e.fleet=function(f,cap) calls=calls+1; if calls==3 then return {'different','a2'},false end; return fleet(f,cap) end
r,err=scan.scan(e,ids); assert(not r and err:find('membership changed'))
''')

    def test_bad_fleet_object_reports_test_position_and_rejects_without_handle(self):
        self.run_lua('''
local calls=0
e.operational=function(h) return h~='a2' end
e.is_ship=function(h) calls=calls+1; return true end
local r,err=scan.scan(e,ids)
assert(not r and err:find('ship not operational',1,true))
assert(err:find('faction_index=1/2 ship_index=2/2 scanned=1',1,true))
assert(not err:find('a2',1,true) and calls==1)
e.operational=function() return true end
e.is_ship=function(h) return h~='b1' end
r,err=scan.scan(e,ids)
assert(not r and err:find('enumerated object not ship class',1,true))
assert(err:find('faction_index=2/2 ship_index=1/1 scanned=2',1,true))
assert(not err:find('b1',1,true))
''')

    def test_nonoperational_diagnostic_is_opt_in_and_cannot_change_failure(self):
        self.run_lua('''
e.operational=function(h) return h~='a2' end
local observed
local r,err=scan.scan(e,ids,{on_nonoperational=function(h,f,s)
 observed={h,f,s}; error('private diagnostic failure')
end})
assert(not r and err:find('ship not operational',1,true))
assert(not err:find('private diagnostic failure',1,true) and not err:find('a2',1,true))
assert(observed[1]=='a2' and observed[2]==1 and observed[3]==2)
''')

    def test_truncated_faction_count_and_capacity_are_diagnostic(self):
        self.run_lua('''
e.factions=function(cap) return {},true,cap end
local r,err=scan.scan(e,ids,{max_factions=1024})
assert(not r and err:find('returned=1024 capacity=1024',1,true))
''')

    def test_limits_counts_and_duplicates_fail_closed(self):
        self.run_lua('''
local r,err=scan.scan(e,ids,{max_ships=2}); assert(not r and err:find('ship limit'))
r,err=scan.scan(e,ids,{max_factions=2}); assert(not r and err:find('incomplete'))
local original=e.fleet_count; local n=0
e.fleet_count=function(f) n=n+1; if n==2 then return 3 end return original(f) end
r,err=scan.scan(e,ids); assert(not r and err:find('fleet enumeration changed'))
e.fleet_count=original
ids.ship=function() return 'same' end
r,err=scan.scan(e,ids); assert(not r and err:find('duplicate portable'))
''')

    def test_bad_pose_parent_or_identity_never_returns_partial_rows(self):
        self.run_lua('''
local pose=e.pose
e.pose=function(h) local p=pose(h); if h=='a2' then p.x=0/0 end return p end
local r,err=scan.scan(e,ids); assert(not r and err:find('invalid pose'))
e.pose=pose; local n=0
e.sector=function(h) n=n+1; if n==2 then return 'other' end return 'sector' end
r,err=scan.scan(e,ids); assert(not r and err:find('changed while sampled'))
e.sector=function() return 'sector' end
ids.ship=function() return nil end
r,err=scan.scan(e,ids); assert(not r and err:find('portable ship identity'))
''')

    def test_time_budget_checkpoint_aborts_without_partial_result(self):
        self.run_lua('''
local n=0
local r,err=scan.scan(e,ids,{checkpoint=function() n=n+1; if n==5 then error('budget exceeded') end end})
assert(not r and err:find('budget exceeded'))
''')

    def test_fixture_probe_is_default_off_and_runs_once_with_local_ids(self):
        self.run_lua('''
package.loaded.ffi={cdef=function() end, new=function(_,v) return v end,
 C={GetSaveFolderPath=function() return '/private/45841/save' end}, string=function(s) return s end}
GetCurRealTime=function() return 10 end
X4LAN_AUTHORITY_SHIP_SCAN=scan; X4LAN_AUTHORITY_SHIP_ENGINE={new=function() return e end}
local probe=assert(loadfile('src/authority/lua/fixture_scan_probe.lua'))()
local logs={}; local log=function(s) logs[#logs+1]=s end
local cfg={native_gate_hash='battle',native_gate_snapshot_fixture={},test_profile='45841'}
for i=1,12 do cfg.native_gate_snapshot_fixture[i]=i end
probe.sample(cfg,30,{'a1'},log); assert(#logs==0)
cfg.native_gate_authority_scan=true
probe.sample(cfg,29,{'a1'},log); assert(#logs==0)
probe.sample(cfg,30,{'a1'},log); probe.sample(cfg,31,{'a1'},log)
assert(#logs==2 and logs[1]:find('AUTHORITY_FIXTURE_READ') and logs[2]:find('AUTHORITY_SCAN_FIXTURE'))
assert(logs[2]:find('test%-only%-fixture%-1') and logs[2]:find('ships=3') and not logs[2]:find('a1'))
''')

    def test_fixture_read_survives_fleet_failure_without_unknown_position_read(self):
        self.run_lua('''
package.loaded.ffi={cdef=function() end, new=function(_,v) return v end,
 C={GetSaveFolderPath=function() return '/private/45841/save' end}, string=function(s) return s end}
GetCurRealTime=function() return 10 end
local reads={}; local original=e.pose
e.pose=function(ship) reads[#reads+1]=ship; return original(ship) end
e.operational=function(ship) return ship~='a2' end
X4LAN_AUTHORITY_SHIP_SCAN=scan; X4LAN_AUTHORITY_SHIP_ENGINE={new=function() return e end}
local probe=assert(loadfile('src/authority/lua/fixture_scan_probe.lua'))()
local cfg={native_gate_authority_scan=true,native_gate_hash='battle',native_gate_snapshot_fixture={},test_profile='45841'}
for i=1,12 do cfg.native_gate_snapshot_fixture[i]=i end
local logs={};probe.sample(cfg,30,{'a1'},function(s) logs[#logs+1]=s end)
assert(#logs==3 and logs[1]:find('AUTHORITY_FIXTURE_READ') and logs[2]:find('AUTHORITY_NONOP_DIAG') and logs[3]:find('AUTHORITY_SCAN_ERROR'))
assert(logs[2]:find('operational_recheck=false',1,true) and not logs[2]:find('a2',1,true))
assert(logs[2]:find('same_fleet_recheck=true',1,true))
assert(logs[3]:find('ship not operational',1,true))
assert(#reads==2 and reads[1]=='a1' and reads[2]=='a1')
''')

    def test_fixture_probe_uses_real_ffi_new_without_extra_assert_arguments(self):
        self.run_lua('''
local nativeffi=require('ffi')
nativeffi.cdef('typedef uint64_t UniverseID;')
assert(not pcall(function() nativeffi.new('UniverseID',1,'too many') end))
package.loaded.ffi={cdef=function() end, new=nativeffi.new,
 C={GetSaveFolderPath=function() return '/private/45841/save' end}, string=function(s) return s end}
GetCurRealTime=function() return 10 end
local engine={
 key=function(h) return tostring(h) end,
 operational=function() return true end,
 is_ship=function() return true end,
 sector=function() return nativeffi.new('UniverseID',2) end,
 pose=function() return {x=1,y=2,z=3,yaw=0,pitch=0,roll=0} end,
}
X4LAN_AUTHORITY_SHIP_ENGINE={new=function() return engine end}
X4LAN_AUTHORITY_SHIP_SCAN={scan=function(_,identities)
 return {rows={{id=identities.ship(nativeffi.new('UniverseID',1)),
                sector=identities.sector(nativeffi.new('UniverseID',2)),
                pose=engine.pose()}}, consistency='membership_rechecked_non_atomic'}
end}
local probe=assert(loadfile('src/authority/lua/fixture_scan_probe.lua'))()
local cfg={native_gate_authority_scan=true,native_gate_hash='battle',native_gate_snapshot_fixture={},test_profile='45841'}
for i=1,12 do cfg.native_gate_snapshot_fixture[i]=i end
local logs={};probe.sample(cfg,30,{1},function(s) logs[#logs+1]=s end)
assert(#logs==2 and logs[1]:find('AUTHORITY_FIXTURE_READ') and logs[2]:find('AUTHORITY_SCAN_FIXTURE'), logs[1] or 'missing receipt')
''')

    def test_recheck_is_diagnostic_only_even_if_status_changes_or_throws(self):
        self.run_lua('''
package.loaded.ffi={cdef=function() end, new=function(_,v) return v end,
 C={GetSaveFolderPath=function() return '/private/45841/save' end}, string=function(s) return s end}
GetCurRealTime=function() return 10 end
X4LAN_AUTHORITY_SHIP_SCAN=scan; X4LAN_AUTHORITY_SHIP_ENGINE={new=function() return e end}
local cfg={native_gate_authority_scan=true,native_gate_hash='battle',native_gate_snapshot_fixture={},test_profile='45841'}
for i=1,12 do cfg.native_gate_snapshot_fixture[i]=i end
for _,status in ipairs({'true','unknown'}) do
 local calls=0
 e.operational=function(h)
  if h~='a2' then return true end
  calls=calls+1
  if calls==1 then return false end
  if status=='unknown' then error('private failure') end
  return true
 end
 local logs={};local probe=assert(loadfile('src/authority/lua/fixture_scan_probe.lua'))()
 probe.sample(cfg,30,{'a1'},function(s) logs[#logs+1]=s end)
 assert(#logs==3 and logs[2]:find('operational_recheck='..status,1,true))
 assert(logs[3]:find('ship not operational',1,true) and not logs[3]:find('private failure',1,true))
 assert(not logs[2]:find('a2',1,true))
end
''')

    def test_game_binding_load_has_no_engine_calls(self):
        self.run_lua("assert(loadfile('src/authority/lua/x4_ship_engine.lua'))()")

    def test_nonoperational_details_are_gated_by_membership_and_validity(self):
        self.run_lua('''
package.loaded.ffi={cdef=function() end, new=function(_,v) return v end,
 C={GetSaveFolderPath=function() return '/private/45841/save' end}, string=function(s) return s end}
GetCurRealTime=function() return 10 end
X4LAN_AUTHORITY_SHIP_SCAN=scan; X4LAN_AUTHORITY_SHIP_ENGINE={new=function() return e end}
local cfg={native_gate_authority_scan=true,native_gate_hash='battle',native_gate_snapshot_fixture={},test_profile='45841'}
for i=1,12 do cfg.native_gate_snapshot_fixture[i]=i end
local calls=0
local originalfleet=e.fleet
e.operational=function(h) return h~='2' end
data.a={'a1','2'}
e.valid=function(h) calls=calls+1; return false end
IsComponentConstruction=function(h) error('construction on invalid component') end
ConvertStringTo64Bit=function(h) return h end
e.is_ship=function(h) assert(h~='2','class on invalid component'); return true end
local gate={saved_identity=function(h) assert(h=='2'); return '0000000000001234' end}
local function run()
 local logs={}; local probe=assert(loadfile('src/authority/lua/fixture_scan_probe.lua'))()
 probe.sample(cfg,30,{'a1'},function(s) logs[#logs+1]=s end,gate)
 assert(#logs==3 and logs[3]:find('ship not operational',1,true))
 return logs[2]
end
local diag=run()
assert(diag:find('valid=false',1,true) and diag:find('construction=unknown',1,true))
assert(diag:find('wreck_ui=unknown',1,true) and diag:find('saved_private=0000000000001234',1,true))
assert(calls==1)
e.valid=function() return true end
e.is_ship=function() return true end
IsComponentConstruction=function(h) assert(h=='2'); return true end
diag=run(); assert(diag:find('valid=true',1,true) and diag:find('construction=true',1,true))
assert(diag:find('wreck_ui=false',1,true))
IsComponentConstruction=function() return false end
diag=run(); assert(diag:find('construction=false',1,true) and diag:find('wreck_ui=true',1,true))
e.is_ship=function(h) return h~='2' end
diag=run(); assert(diag:find('ship_class=false',1,true) and diag:find('wreck_ui=unknown',1,true))
e.fleet=function(f,cap) calls=calls+1; if calls==2 then return {},true end; return originalfleet(f,cap) end
calls=0; e.valid=function() error('validity checked despite absent membership') end
gate.saved_identity=function() error('identity checked despite absent membership') end
diag=run(); assert(diag:find('same_fleet_recheck=unknown',1,true) and diag:find('valid=unknown',1,true))
assert(diag:find('construction=unknown',1,true) and diag:find('wreck_ui=unknown',1,true))
''')

    def test_membership_recheck_absence_or_failure_does_not_complete_scan(self):
        self.run_lua('''
package.loaded.ffi={cdef=function() end, new=function(_,v) return v end,
 C={GetSaveFolderPath=function() return '/private/45841/save' end}, string=function(s) return s end}
GetCurRealTime=function() return 10 end
X4LAN_AUTHORITY_SHIP_SCAN=scan; X4LAN_AUTHORITY_SHIP_ENGINE={new=function() return e end}
local cfg={native_gate_authority_scan=true,native_gate_hash='battle',native_gate_snapshot_fixture={},test_profile='45841'}
for i=1,12 do cfg.native_gate_snapshot_fixture[i]=i end
local original_fleet=e.fleet
for _,status in ipairs({'false','unknown'}) do
 data.a={'a1','a2'}
 local calls=0
 e.fleet=function(f,cap)
  calls=calls+1
  if calls==2 and status=='unknown' then error('private failure') end
  return original_fleet(f,cap)
 end
 e.operational=function(h)
  if h=='a2' and status=='false' then data.a={'a1'} end
  return h~='a2'
 end
 local logs={};local probe=assert(loadfile('src/authority/lua/fixture_scan_probe.lua'))()
 probe.sample(cfg,30,{'a1'},function(s) logs[#logs+1]=s end)
 assert(#logs==3 and logs[2]:find('same_fleet_recheck='..status,1,true))
 assert(logs[3]:find('ship not operational',1,true) and not logs[3]:find('private failure',1,true))
 assert(not logs[2]:find('a2',1,true))
end
''')

class OverlayIntegrationTests(unittest.TestCase):
    def test_fixture_receipt_is_independent_and_strict(self):
        sys.path.insert(0,str(ROOT/'tools/dev'))
        import linux_gate_live as live
        line=('[X4LAN] NATIVE_GATE AUTHORITY_FIXTURE_READ tick=30 identity=test-only-fixture-1 '
              'operational=1 sector_present=1 x=1 y=2 z=3 yaw=0 pitch=0 roll=0')
        scan_error='[X4LAN] NATIVE_GATE AUTHORITY_SCAN_ERROR tick=30 why=ship not operational'
        result=live.parse_authority_fixture_read([line,scan_error],60)
        self.assertTrue(result['pass']);self.assertEqual(result['pose']['x'],1)
        self.assertFalse(live.parse_authority_scan([line,scan_error],60)['pass'])
        for lines in ([], [line,line], [line.replace('x=1','x=nan')],
                      ['[X4LAN] NATIVE_GATE AUTHORITY_FIXTURE_ERROR tick=30 why=bad']):
            self.assertFalse(live.parse_authority_fixture_read(lines,60)['pass'])

    def test_receipt_is_required_strict_and_separate_from_simulation(self):
        sys.path.insert(0,str(ROOT/'tools/dev'))
        import linux_gate_live as live
        line = ('[X4LAN] NATIVE_GATE AUTHORITY_SCAN_FIXTURE tick=30 identity=test-only-fixture-1 '
                'sector=test-only-sector-1 ships=3 consistency=membership_rechecked_non_atomic '
                'x=1 y=2 z=3 yaw=0 pitch=0 roll=0 read_x=2 read_y=2 read_z=3 '
                'read_yaw=0 read_pitch=0 read_roll=0')
        observation=live.parse_authority_scan([line],60)
        self.assertTrue(observation['pass']); self.assertEqual(observation['position_readback_delta_m'],1)
        for lines in ([], [line,line], [line.replace('x=1','x=nan',1)],
                      ['[X4LAN] NATIVE_GATE AUTHORITY_SCAN_ERROR tick=30 why=bad']):
            self.assertFalse(live.parse_authority_scan(lines,60)['pass'])

    def test_default_off_and_explicit_option_packaged_and_sealed(self):
        refs = ''.join(f'<value type="component" value="[0x{i:x}]"/>' for i in range(256,268))
        ships = ''.join(f'<component id="[0x{i:x}]" class="ship_s" '
                        f'macro="ship_{"arg" if i<262 else "xen"}_s_fighter_01_a_macro" '
                        f'owner="{"argon" if i<262 else "xenon"}"><movement class="navigation"/></component>'
                        for i in range(256,268))
        save = gzip.compress((f'<savegame><info><game seed="1"/></info><md><script name="X4LAN_NativeGate">'
          f'<cue name="Spawn" state="complete"><vars><value name="$ships" type="list" value="42"/></vars>'
          f'</cue></script></md><script><refs type="list"><ref id="42">{refs}</ref></refs></script>'
          f'<universe>{ships}</universe></savegame>').encode())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); gate=root/'gate.so'; gate.write_bytes(b'fake'); snapshot=root/'save.gz'; snapshot.write_bytes(save)
            for enabled in (False, True):
                out=root/('on' if enabled else 'off')
                cmd=['python',str(ROOT/'tools/dev/build_native_gate_overlay.py'),'--gate-so',str(gate),'--snapshot',str(snapshot),
                     '--out',str(out),'--mode','battle','--snapshot-prebind','--world-identities','--serial-pathing']
                if enabled: cmd.append('--authority-fixture-scan')
                result=subprocess.run(cmd,capture_output=True,text=True,cwd=ROOT)
                self.assertEqual(result.returncode,0,result.stderr)
                config=(out/'ui/config.lua.append').read_text(); files=(out/'ui.xml.files').read_text().splitlines()
                self.assertEqual('native_gate_authority_scan = true' in config,enabled)
                self.assertEqual('native_gate_battle_engage = false' in config,enabled)
                for name in ('ship_scan.lua','x4_ship_engine.lua','fixture_scan_probe.lua'):
                    path=out/'ui'/name
                    self.assertEqual(path.exists(),enabled)
                    if enabled:
                        self.assertLess(files.index('ui/'+name),files.index('ui/native_gate_probe.lua'))
                        manifest=json.loads((out/'x4lane-manifest.json').read_text())
                        self.assertEqual(manifest['ui/'+name],hashlib.sha256(path.read_bytes()).hexdigest())
            sys.path.insert(0,str(ROOT/'tools/dev'))
            import linux_gate_live as live
            import build_native_gate_overlay as builder
            bundle = root/'bundle'; forwarded=[]
            def command(arguments, **kwargs):
                if 'build_native_gate_linux.py' in str(arguments[1]):
                    (bundle/'.build/x4lan_gate.so').write_bytes(b'fake')
                elif 'build_native_gate_overlay.py' in str(arguments[1]):
                    forwarded.extend(arguments)
                    with mock.patch.object(sys,'argv',arguments[1:]): builder.main()
                return mock.Mock(stdout='synthetic-commit\n' if 'rev-parse' in arguments else '',returncode=0)
            with mock.patch.object(live.subprocess,'run',side_effect=command), contextlib.redirect_stdout(io.StringIO()):
                live.main(['bundle','--zig','/unused','--snapshot',str(snapshot),'--out',str(bundle),
                           '--ticks','60','--battle','--serial-pathing','--path-determinism','1','--authority-fixture-scan'])
            self.assertIn('--authority-fixture-scan',forwarded)
            manifest=json.loads((bundle/'manifest.json').read_text())
            self.assertTrue(manifest['authority_fixture_scan'])
            live.validate_authority_scan_bundle(bundle,manifest)
            manifest['authority_fixture_scan']=False
            with self.assertRaisesRegex(ValueError,'config differs'): live.validate_authority_scan_bundle(bundle,manifest)

            bundle = root/'wire-bundle'; forwarded.clear()
            original_command = command
            def wire_command(arguments, **kwargs):
                if len(arguments)>1 and arguments[1]=='cc':
                    Path(arguments[arguments.index('-o')+1]).write_bytes(b'fake net')
                    return mock.Mock(stdout='',returncode=0)
                return original_command(arguments, **kwargs)
            with mock.patch.object(live.subprocess,'run',side_effect=wire_command), contextlib.redirect_stdout(io.StringIO()):
                live.main(['bundle','--zig','/unused','--snapshot',str(snapshot),'--out',str(bundle),
                           '--ticks','60','--battle','--serial-pathing','--path-determinism','1',
                           '--authority-fixture-scan','--authority-fixture-wire'])
            self.assertIn('--authority-fixture-wire',forwarded)
            manifest=json.loads((bundle/'manifest.json').read_text())
            self.assertTrue(manifest['authority_fixture_wire'])
            live.validate_authority_scan_bundle(bundle,manifest)
            for name in ('fixture_wire.lua','fixture_wire_probe.lua'):
                self.assertIn('extension/x4_lan_lab/ui/'+name, manifest['files'])
            self.assertIn('extension/x4_lan_lab/native/x4lan_net.so', manifest['files'])
            self.assertNotIn('native_gate_authority_wire_lease',
                             (bundle/'extension/x4_lan_lab/ui/config.lua').read_text())
            manifest['authority_fixture_wire']=False
            with self.assertRaisesRegex(ValueError,'wire config differs'): live.validate_authority_scan_bundle(bundle,manifest)

if __name__ == '__main__':
    unittest.main()
