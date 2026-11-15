"""Fast checks for the disposable registry census harness; never launches X4."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('authority_registry_census_live', ROOT/'tools/dev/authority_registry_census_live.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RegistryCensusTests(unittest.TestCase):
    def test_receipt_counts_and_complete_order(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'log'
            tag = '[X4LAN] AUTH_REGISTRY save '
            path.write_text('\n'.join(tag+row for row in (
                'PAUSED', 'EPOCH '+('a'*32),
                'INVENTORY selected=2 eligible=2 distinct=3 enumerated=4 unconfirmed=1 unlocated=0 observed_sectors=2 truncated=false coverage=unknown',
                'ROW 1 ship_a', 'ROW 2 ship_b',
                'DONE count=2 coverage=unknown independent_identity=false'))+'\n')
            self.assertEqual(MODULE.observations(path, 'save', 20, 'a'*32), ([(1, 'ship_a'), (2, 'ship_b')], 2))
            with self.assertRaises(ValueError): MODULE.observations(path, 'save', 20, 'b'*32)
            path.write_text(path.read_text().replace('ROW 2 ship_b', 'ROW 1 ship_b'))
            with self.assertRaises(ValueError): MODULE.observations(path, 'save', 20, 'a'*32)

    def test_injection_places_census_after_marker_gate_and_keeps_client_epoch_private(self):
        for phase in ("save", "load"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as d:
                lab = Path(d)/"extensions/x4_lan_lab"
                (lab/"ui").mkdir(parents=True)
                (lab/"md").mkdir()
                (lab/"ui/config.lua").write_text("X4LAN_CONFIG = {}\n")
                (lab/"ui.xml").write_text('    <file name="ui/authority_checkpoint_marker_probe.lua" />\n')
                name = "authority_world_bridge_probe.lua" if phase == "save" else "authority_download_load_probe.lua"
                line = (" if not started and now-loaded_at>=3 and not X4LAN_AUTHORITY_MARKER_READY() then return end\n"
                        if phase == "save" else "  if not X4LAN_AUTHORITY_MARKER_READY() then return end\n")
                (lab/"ui"/name).write_text(line)
                MODULE.inject(Path(d), phase, "a"*32, 200000)
                probe = (lab/"ui"/name).read_text()
                self.assertLess(probe.index("X4LAN_AUTHORITY_MARKER_READY"), probe.index("X4LAN_AUTHORITY_REGISTRY_CENSUS_READY"))
                config = (lab/"ui/config.lua").read_text()
                self.assertIn("authority_registry_deadline=3600", config)
                self.assertEqual('authority_registry_epoch=' in config, phase == "save")

    def test_lua_probe_enrolls_resolves_and_reenrolls_after_load(self):
        script = r'''
local callbacks={}; local log={}; local saved={}; local ids={}; local epoch='aabb'
local paused=false
package.loaded.ffi={cdef=function() end,C={IsGamePaused=function() return paused end}}
function Pause() paused=true end
function DebugError(s) log[#log+1]=s end
function GetCurRealTime() return 1 end
function RegisterEvent(n,f) callbacks[n]=f end
function ConvertIDTo64Bit(v) return tonumber(v) end
function ConvertStringToLuaID(v) return tonumber(v) end
function GetComponentData(id,name) return 'ship_'..id end
X4LAN_AUTHORITY_SHIP_ENGINE={new=function() return {
 factions=function() return {'a','b'},false end,
 fleet_count=function(f) return 2 end,
 fleet=function(f) if f=='a' then return {1,2},false else return {2,3},false end end,
 key=function(v) return tostring(v) end, operational=function() return true end,
 is_ship=function() return true end,sector=function(ship) return ship==1 and 10 or 20 end,
} end}
local S='X4AuthorityShipRegistry'
function AddUITriggeredEvent(screen,op,args)
 assert(screen==S)
 if op=='Initialize' then epoch=args.epoch;callbacks[S..'.Initialized'](nil,epoch)
 elseif op=='Status' then callbacks[S..'.Epoch'](nil,epoch);callbacks[S..'.Count'](nil,#saved)
 elseif op=='Enroll' then
  assert(args.epoch==epoch)
  local id=ids[args.ship]
  if not id then id=#saved+1;saved[id]=args.ship;ids[args.ship]=id end
  callbacks[S..'.Enrolled'](nil,id)
 elseif op=='Resolve' then assert(args.epoch==epoch);callbacks[S..'.Actor'](nil,saved[args.index])
 else error(op) end
end
for _,phase in ipairs({'save','load'}) do
 paused=false
 X4LAN_CONFIG={authority_registry_phase=phase,authority_registry_limit=10,authority_registry_deadline=100}
 if phase=='save' then X4LAN_CONFIG.authority_registry_epoch=string.rep('a',32) end
 assert(loadfile('tools/dev/authority_registry_census_probe.lua'))()
 local done=false
 for i=1,40 do if X4LAN_AUTHORITY_REGISTRY_CENSUS_READY() then done=true;break end end
 assert(done)
end
assert(#saved==3)
for _,line in ipairs(log) do print(line) end
'''
        result = subprocess.run(['luajit', '-e', script], cwd=ROOT, text=True, capture_output=True, check=True)
        self.assertIn('save DONE count=3', result.stdout)
        self.assertIn('load DONE count=3', result.stdout)
        self.assertIn('observed_sectors=2', result.stdout)


if __name__ == '__main__': unittest.main()
