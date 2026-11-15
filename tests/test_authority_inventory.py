import os
import contextlib
import gzip
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
LUAJIT = shutil.which('luajit')
FIXTURE = r'''
local scan=assert(loadfile('src/authority/lua/ship_scan.lua'))()
local data={a={'a1','a2','a3','a4','a5','a6','a7','a8'}}
local e={
 factions=function() return {'a'},false end,
 fleet_count=function(f) return #data[f] end,
 fleet=function(f) local copy={} for _,v in ipairs(data[f]) do copy[#copy+1]=v end return copy,false end,
 key=function(h) return h end,
 operational=function(h) if h=='a2' then return false elseif h=='a3' then return nil end return true end,
 is_ship=function(h) return h~='a4' end,
 sector=function(h) if h=='a6' then return nil elseif h=='a7' then return 'unknown_sector' else return 's1' end end,
 pose=function(h) if h=='a8' then return {x=0/0} end return {x=1,y=2,z=3,yaw=4,pitch=5,roll=6} end,
}
local ids={ship=function(h) if h=='a5' then return nil end return 'ship:'..h end,
 sector=function(h) if h=='unknown_sector' then return nil end return 'sector:'..h end}
local opts={identity_scope='fixture-generation-1'}
'''


@unittest.skipUnless(LUAJIT, 'LuaJIT is required')
class InventoryTests(unittest.TestCase):
    def run_lua(self, body):
        p = subprocess.run([LUAJIT, '-'], input=FIXTURE + body, text=True, cwd=ROOT,
                           capture_output=True, env=os.environ.copy())
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_every_enumerated_entry_has_one_explicit_outcome(self):
        self.run_lua('''
local r,err=scan.inventory(e,ids,opts);assert(r,err)
assert(#r.rows==8 and r.counts.enumerated==8)
assert(r.counts.position_observed==1 and r.counts.not_confirmed_operational==1 and r.counts.unavailable==6)
assert(r.counts.unresolved_identity==1 and r.counts.enumerated==r.counts.position_observed+r.counts.not_confirmed_operational+r.counts.unavailable)
assert(r.identity_scope=='fixture-generation-1' and r.universe_coverage=='unknown' and r.positions_complete==false)
assert(r.enumeration=='faction_lists_rechecked_non_atomic')
assert(r.rows[1].status=='position_observed' and r.rows[1].identity=='ship:a1' and r.rows[1].pose.z==3)
assert(r.rows[2].status=='not_confirmed_operational' and not r.rows[2].pose)
local reasons={'operational_unknown','ship_class_not_confirmed','ship_identity_unavailable','sector_unavailable','sector_identity_unavailable','pose_unavailable'}
for i,reason in ipairs(reasons) do
 local row=r.rows[i+2];assert(row.ordinal==i+2 and row.status=='unavailable' and row.reason==reason and not row.pose)
 assert(r.unavailable_reasons[reason]==1)
end
assert(not r.rows[5].identity)
''')

    def test_membership_identity_operational_and_sector_changes_fail_closed(self):
        self.run_lua('''
data.a={'a1','a2'}
local oldfleet=e.fleet;local calls=0
e.fleet=function(f) calls=calls+1; if calls==2 then return {'a1','new'},false end;return oldfleet(f) end
local r,err=scan.inventory(e,ids,opts);assert(not r and err:find('membership changed'))
e.fleet=oldfleet
local oldid=ids.ship;calls=0
ids.ship=function(h) if h=='a1' then calls=calls+1;if calls>1 then return 'changed' end end return oldid(h) end
r,err=scan.inventory(e,ids,opts);assert(not r and err:find('identity or operational state changed'))
ids.ship=oldid;calls=0
e.operational=function(h) if h=='a1' then calls=calls+1;return calls==1 end return false end
r,err=scan.inventory(e,ids,opts);assert(not r and err:find('identity or operational state changed'))
e.operational=function(h) return h=='a1' end;calls=0
e.sector=function(h) calls=calls+1;if calls>1 then return 's2' end return 's1' end
r,err=scan.inventory(e,ids,opts);assert(not r and err:find('sector state changed'))
''')

    def test_duplicate_identity_or_truncated_inputs_never_produce_rows(self):
        self.run_lua('''
data.a={'a1','a2'}
ids.ship=function() return 'duplicate' end
local r,err=scan.inventory(e,ids,opts);assert(not r and err:find('duplicate supplied identity'))
ids.ship=function(h) return h end
e.fleet=function() return {},true end
r,err=scan.inventory(e,ids,opts);assert(not r and err:find('enumeration changed or incomplete'))
e.factions=function() return {'a'},true end
r,err=scan.inventory(e,ids,opts);assert(not r and err:find('faction enumeration incomplete'))
''')

    def test_getter_failures_are_counted_and_do_not_expose_error_text(self):
        self.run_lua('''
data.a={'a1','a2'}
e.operational=function(h) if h=='a1' then error('private component handle') end return false end
ids.ship=function() error('private identity') end
local r,err=scan.inventory(e,ids,opts);assert(r,err)
assert(r.counts.unavailable==1 and r.counts.not_confirmed_operational==1 and r.counts.unresolved_identity==2)
assert(r.unavailable_reasons.operational_unknown==1)
for _,row in ipairs(r.rows) do assert(not tostring(row.reason):find('private')) end
opts.checkpoint=function() error('private checkpoint') end
r,err=scan.inventory(e,ids,opts);assert(not r and err:find('checkpoint failed') and not err:find('private'))
''')

    def test_no_silent_default_and_identity_scope_required(self):
        self.run_lua('''
local r,err=scan.inventory(e,ids);assert(not r and err:find('identity scope'))
data.a={'a1','a2'}
r,err=scan.scan(e,ids);assert(not r and err:find('ship not operational'))
''')

    def test_ten_thousand_entries_remain_distinct(self):
        self.run_lua('''
data.a={};for i=1,10000 do data.a[i]='ship'..i end
e.operational=function(h) return tonumber(h:sub(5))%2==0 end
e.is_ship=function() return true end
e.sector=function() return 's1' end
e.pose=function() return {x=1,y=2,z=3,yaw=0,pitch=0,roll=0} end
ids.ship=function(h) return 'saved:'..h end
local r,err=scan.inventory(e,ids,opts);assert(r,err)
assert(#r.rows==10000 and r.counts.enumerated==10000 and r.counts.position_observed==5000)
assert(r.counts.not_confirmed_operational==5000 and r.counts.unavailable==0)
assert(r.universe_coverage=='unknown' and r.positions_complete==false)
''')

    def test_native_fixture_probe_is_separately_opt_in_and_logs_counts_only(self):
        self.run_lua('''
package.loaded.ffi={cdef=function() end, C={GetSaveFolderPath=function() return '/private/45841/save' end}, string=function(x) return x end}
GetCurRealTime=function() return 10 end
data.a={'1','2','3'}
e.operational=function(h) if h=='2' then return false elseif h=='3' then return nil end return true end
e.is_ship=function() return true end
e.sector=function() return '4' end
e.pose=function() return {x=11,y=22,z=33,yaw=0,pitch=0,roll=0} end
X4LAN_AUTHORITY_SHIP_SCAN=scan;X4LAN_AUTHORITY_SHIP_ENGINE={new=function() return e end}
local gate={saved_identity=function(h) if h=='3' then return '0000000000000000' end return '000000000000000'..h end}
local cfg={native_gate_authority_scan=true,native_gate_hash='battle',test_profile='45841',native_gate_snapshot_fixture={}}
for i=1,12 do cfg.native_gate_snapshot_fixture[i]=i end
local logs={};local probe=assert(loadfile('src/authority/lua/fixture_inventory_probe.lua'))()
local function log(s) logs[#logs+1]=s end
probe.sample(cfg,30,log,gate);assert(#logs==0)
cfg.native_gate_authority_inventory=true
probe.sample(cfg,29,log,gate);assert(#logs==0)
probe.sample(cfg,30,log,gate);probe.sample(cfg,31,log,gate)
assert(#logs==1 and logs[1]:find('AUTHORITY_INVENTORY ',1,true))
for _,fragment in ipairs({'enumerated=3','position_observed=1','not_confirmed_operational=1','unavailable=1',
 'unresolved_identity=1','operational_unknown=1','coverage=unknown','positions_complete=false'}) do
 assert(logs[1]:find(fragment,1,true),fragment)
end
assert(not logs[1]:find('0000000000000001',1,true) and not logs[1]:find('x=11',1,true))
''')

    def test_native_fixture_probe_does_not_run_outside_isolation(self):
        self.run_lua('''
package.loaded.ffi={cdef=function() end, C={GetSaveFolderPath=function() return '/real/unknown/save' end}, string=function(x) return x end}
GetCurRealTime=function() return 10 end
X4LAN_AUTHORITY_SHIP_SCAN=scan;X4LAN_AUTHORITY_SHIP_ENGINE={new=function() error('must not call engine') end}
local cfg={native_gate_authority_inventory=true,native_gate_authority_scan=true,native_gate_hash='battle',test_profile='45841',native_gate_snapshot_fixture={}}
for i=1,12 do cfg.native_gate_snapshot_fixture[i]=i end
local logs={};local probe=assert(loadfile('src/authority/lua/fixture_inventory_probe.lua'))()
probe.sample(cfg,30,function(s) logs[#logs+1]=s end,{saved_identity=function() error('must not resolve') end})
assert(#logs==1 and logs[1]:find('AUTHORITY_INVENTORY_ERROR',1,true))
''')

    def test_inventory_budget_failure_is_a_diagnostic_not_partial_counts(self):
        self.run_lua('''
package.loaded.ffi={cdef=function() end, C={GetSaveFolderPath=function() return '/private/45841/save' end}, string=function(x) return x end}
local calls=0;GetCurRealTime=function() calls=calls+1;if calls>1 then return 100 end return 10 end
X4LAN_AUTHORITY_SHIP_SCAN=scan;X4LAN_AUTHORITY_SHIP_ENGINE={new=function() return e end}
local cfg={native_gate_authority_inventory=true,native_gate_authority_scan=true,native_gate_hash='battle',test_profile='45841',native_gate_snapshot_fixture={}}
for i=1,12 do cfg.native_gate_snapshot_fixture[i]=i end
local logs={};local probe=assert(loadfile('src/authority/lua/fixture_inventory_probe.lua'))()
probe.sample(cfg,30,function(s) logs[#logs+1]=s end,{saved_identity=function() return '0000000000000000' end})
assert(#logs==1 and logs[1]:find('AUTHORITY_INVENTORY_ERROR tick=30 reason=checkpoint',1,true))
assert(not logs[1]:find('enumerated=',1,true))
''')

    def test_collision_diagnostic_reports_indices_without_handles(self):
        self.run_lua('''
package.loaded.ffi={cdef=function() end, C={GetSaveFolderPath=function() return '/private/45841/save' end}, string=function(x) return x end}
GetCurRealTime=function() return 10 end
data.a={'1'};data.b={'1'}
e.factions=function() return {'a','b'},false end
e.operational=function() return true end;e.is_ship=function() return true end
e.sector=function() return '4' end
e.pose=function() return {x=1,y=2,z=3,yaw=0,pitch=0,roll=0} end
X4LAN_AUTHORITY_SHIP_SCAN=scan;X4LAN_AUTHORITY_SHIP_ENGINE={new=function() return e end}
local cfg={native_gate_authority_inventory=true,native_gate_authority_scan=true,native_gate_hash='battle',test_profile='45841',native_gate_snapshot_fixture={}}
for i=1,12 do cfg.native_gate_snapshot_fixture[i]=i end
local logs={};local probe=assert(loadfile('src/authority/lua/fixture_inventory_probe.lua'))()
probe.sample(cfg,30,function(s) logs[#logs+1]=s end,{saved_identity=function(h) return '000000000000000'..h end})
assert(#logs==1 and logs[1]:find('reason=duplicate_object first_faction=1 first_index=1 repeated_faction=2 repeated_index=1',1,true))
assert(not logs[1]:find('0000000000000001',1,true) and not logs[1]:find('enumerated=',1,true))
''')

    def test_fixture_error_categories_do_not_conflate_faction_and_membership(self):
        self.run_lua('''
package.loaded.ffi={cdef=function() end, C={GetSaveFolderPath=function() return '/private/45841/save' end}, string=function(x) return x end}
GetCurRealTime=function() return 10 end
X4LAN_AUTHORITY_SHIP_ENGINE={new=function() return e end}
local cfg={native_gate_authority_inventory=true,native_gate_authority_scan=true,native_gate_hash='battle',test_profile='45841',native_gate_snapshot_fixture={}}
for i=1,12 do cfg.native_gate_snapshot_fixture[i]=i end
for _,item in ipairs({{'inventory faction membership changed','faction_set_changed'},
 {'inventory faction enumeration incomplete','faction_enumeration_incomplete'},
 {'inventory duplicate supplied identity','duplicate_identity'},
 {'inventory object membership changed','object_set_changed'},
 {'inventory fleet enumeration changed or incomplete','fleet_enumeration_changed'},
 {'untrusted private error','other'}}) do
 X4LAN_AUTHORITY_SHIP_SCAN={inventory=function() return nil,item[1] end}
 local logs={};local probe=assert(loadfile('src/authority/lua/fixture_inventory_probe.lua'))()
 probe.sample(cfg,30,function(s) logs[#logs+1]=s end,{saved_identity=function() return '0000000000000000' end})
 assert(#logs==1 and logs[1]:find('reason='..item[2],1,true) and not logs[1]:find('private',1,true))
end
''')


class InventoryHarnessTests(unittest.TestCase):
    def test_receipt_is_count_checked_and_never_implies_completeness(self):
        sys.path.insert(0, str(ROOT/'tools/dev'))
        import linux_gate_live as live
        from linux_gate_evidence import is_fatal_gate_message
        line=('[X4LAN] NATIVE_GATE AUTHORITY_INVENTORY tick=30 enumerated=3 position_observed=1 '
              'not_confirmed_operational=1 unavailable=1 unresolved_identity=1 operational_unknown=1 '
              'ship_class_not_confirmed=0 ship_class_unknown=0 sector_unavailable=0 ship_identity_unavailable=0 '
              'sector_identity_unavailable=0 pose_unavailable=0 coverage=unknown positions_complete=false')
        receipt=live.parse_authority_inventory([line],60)
        self.assertTrue(receipt['valid_receipt'])
        self.assertEqual(receipt['counts']['enumerated'],3)
        self.assertEqual(receipt['universe_coverage'],'unknown')
        self.assertFalse(receipt['positions_complete'])
        self.assertNotIn('pass',receipt)
        failure='[X4LAN] NATIVE_GATE AUTHORITY_INVENTORY_ERROR tick=30 reason=checkpoint'
        self.assertFalse(is_fatal_gate_message(failure))
        for lines in ([],[line,line],[failure],[line.replace('enumerated=3','enumerated=4')],
                      [line.replace('operational_unknown=1','operational_unknown=0')],
                      [line.replace('positions_complete=false','positions_complete=true')],
                      [line+' secret=1']):
            self.assertFalse(live.parse_authority_inventory(lines,60)['valid_receipt'])

    def test_bundle_requires_explicit_scan_and_freezes_inventory_module(self):
        sys.path.insert(0, str(ROOT/'tools/dev'))
        import linux_gate_live as live
        import build_native_gate_overlay as builder
        refs=''.join(f'<value type="component" value="[0x{i:08x}]"/>' for i in range(256,268))
        ships=''.join(f'<component id="[0x{i:08x}]" class="ship_s" '
                      f'macro="ship_{"arg" if i<262 else "xen"}_s_fighter_01_a_macro" '
                      f'owner="{"argon" if i<262 else "xenon"}"><movement class="navigation"/></component>'
                      for i in range(256,268))
        save=gzip.compress((f'<savegame><info><game seed="1"/></info><md><script name="X4LAN_NativeGate">'
          f'<cue name="Spawn" state="complete"><vars><value name="$ships" type="list" value="42"/></vars>'
          f'</cue></script></md><script><refs type="list"><ref id="42">{refs}</ref></refs></script>'
          f'<universe>{ships}</universe></savegame>').encode())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);snapshot=root/'save.gz';snapshot.write_bytes(save)
            bundle=root/'bundle';forwarded=[]
            with self.assertRaisesRegex(SystemExit,'inventory requires --authority-fixture-scan'):
                live.main(['bundle','--zig','/unused','--snapshot',str(snapshot),'--out',str(root/'refused'),
                           '--ticks','60','--battle','--serial-pathing','--path-determinism','1',
                           '--authority-fixture-inventory'])
            self.assertFalse((root/'refused').exists())
            def command(arguments,**kwargs):
                if 'build_native_gate_linux.py' in str(arguments[1]):
                    (bundle/'.build/x4lan_gate.so').write_bytes(b'fake')
                elif 'build_native_gate_overlay.py' in str(arguments[1]):
                    forwarded.extend(arguments)
                    with mock.patch.object(sys,'argv',arguments[1:]):builder.main()
                return mock.Mock(stdout='synthetic-commit\n' if 'rev-parse' in arguments else '',returncode=0)
            with mock.patch.object(live.subprocess,'run',side_effect=command),contextlib.redirect_stdout(io.StringIO()):
                live.main(['bundle','--zig','/unused','--snapshot',str(snapshot),'--out',str(bundle),
                           '--ticks','60','--battle','--serial-pathing','--path-determinism','1',
                           '--authority-fixture-scan','--authority-fixture-inventory'])
            self.assertIn('--authority-fixture-inventory',forwarded)
            manifest=json.loads((bundle/'manifest.json').read_text())
            self.assertTrue(manifest['authority_fixture_inventory'])
            self.assertEqual(bundle.stat().st_mode & 0o077,0)
            live.validate_authority_scan_bundle(bundle,manifest)
            self.assertIn('extension/x4_lan_lab/ui/fixture_inventory_probe.lua',manifest['files'])
            manifest['authority_fixture_inventory']=False
            with self.assertRaisesRegex(ValueError,'inventory config differs'): live.validate_authority_scan_bundle(bundle,manifest)

    def test_enabled_inventory_requires_each_receipt_without_overriding_strict_failure(self):
        sys.path.insert(0, str(ROOT/'tools/dev'))
        import linux_gate_live as live
        line=('[X4LAN] NATIVE_GATE AUTHORITY_INVENTORY tick=30 enumerated=1 position_observed=0 '
              'not_confirmed_operational=1 unavailable=0 unresolved_identity=0 operational_unknown=0 '
              'ship_class_not_confirmed=0 ship_class_unknown=0 sector_unavailable=0 ship_identity_unavailable=0 '
              'sector_identity_unavailable=0 pose_unavailable=0 coverage=unknown positions_complete=false\n')
        with tempfile.TemporaryDirectory() as tmp:
            profiles=[Path(tmp)/'one',Path(tmp)/'two']
            for profile in profiles: profile.mkdir()
            (profiles[0]/'engine-output.log').write_text(line)
            (profiles[1]/'engine-output.log').write_text('[X4LAN] NATIVE_GATE AUTHORITY_INVENTORY_ERROR tick=30 reason=checkpoint\n')
            games=[(None,p) for p in profiles]
            result={'pass':True}
            live.collect_authority_inventory(result,[1,2],games,60)
            self.assertFalse(result['pass'])
            self.assertTrue(result['authority_inventory_evidence']['1']['valid_receipt'])
            self.assertFalse(result['authority_inventory_evidence']['2']['valid_receipt'])
            (profiles[1]/'engine-output.log').write_text(line)
            result={'pass':False}
            live.collect_authority_inventory(result,[1,2],games,60)
            self.assertFalse(result['pass'])
            self.assertFalse(result['authority_inventory_evidence']['1']['positions_complete'])
            result={'pass':True}
            live.collect_authority_inventory(result,[1,2],games,60)
            self.assertTrue(result['pass'])
            (profiles[1]/'engine-output.log').unlink()
            result={'pass':True}
            live.collect_authority_inventory(result,[1,2],games,60)
            self.assertFalse(result['pass'])
            result={'pass':True}
            live.collect_authority_inventory(result,[1,2],games[:1],60)
            self.assertFalse(result['pass'])
