import os
import shutil
import subprocess
import unittest
from pathlib import Path


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
