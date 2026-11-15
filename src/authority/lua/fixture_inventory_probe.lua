-- Opt-in, read-only inventory of entries returned by faction ship APIs.
-- Runs only in the disposable fixture profile. No component pose is logged.
-- Checkpoints spread Lua processing across frames; each native fleet call and
-- its conversion remain synchronous and are not bounded by the frame budget.
local M={}
local attempted=false
local task=nil
local last_clock=nil
function M.sample(cfg,tick,log,gate)
 if not cfg.native_gate_authority_inventory or (attempted and not task) or tick<30 then return end
 local just_started=not attempted
 local ok=pcall(function()
  if not attempted then
  attempted=true
  assert(cfg.native_gate_authority_inventory==true and cfg.native_gate_authority_scan==true, 'inventory not explicitly enabled')
  assert(cfg.native_gate_hash=='battle' and cfg.native_gate_snapshot_fixture and #cfg.native_gate_snapshot_fixture==12,
   'saved battle fixture required')
  local ffi=require('ffi')
  ffi.cdef[[const char* GetSaveFolderPath(void);]]
  local path=ffi.string(ffi.C.GetSaveFolderPath()):gsub('\\','/'):gsub('/+$','')
  assert(cfg.test_profile=='45841' and path:sub(-#'/45841/save')=='/45841/save', 'isolated profile required')
  assert(type(gate)=='table' and type(gate.saved_identity)=='function', 'saved identity table required')
  assert(type(GetCurRealTime)=='function', 'real-time clock unavailable')
  local function saved_identity(object)
   local decimal=tostring(object):gsub('ULL$','')
   if not decimal:match('^%d+$') then return nil end
   local value=gate.saved_identity(decimal)
   if type(value)~='string' or #value~=16 or not value:match('^[0-9a-f]+$') or value=='0000000000000000' then return nil end
   return value
  end
  local scanner=assert(X4LAN_AUTHORITY_SHIP_SCAN, 'inventory scanner missing')
  local engine=assert(X4LAN_AUTHORITY_SHIP_ENGINE, 'inventory engine missing').new()
  task=assert(scanner.inventory_task(engine,{ship=saved_identity,sector=saved_identity},
   {identity_scope='isolated-snapshot-local-diagnostic',max_factions=1024,max_ships=200000,max_fleet=200000,max_memberships=1000000}))
 end
 local function clock()
  local now=GetCurRealTime()
  assert(type(now)=='number' and now==now and now~=math.huge and now~=-math.huge and
   (not last_clock or now>=last_clock), 'invalid clock')
  last_clock=now
  return now
 end
 local started=clock()
 local state,result,why=task.step(10000,function() return clock()-started>=0.004 end)
 if state=='running' then
  if just_started or tick%60==0 then
   log('AUTHORITY_CENSUS_PROGRESS tick='..tick..' status=in_progress consistency=non_atomic coverage=unknown')
  end
  return
 end
 task=nil
 if state=='error' then
   local reason='other'
   if type(why)=='string' then
    -- Never expose raw callback errors or IDs. Match known scanner failures to
    -- fixed labels; overlapping words such as "faction" and "membership"
    -- must not collapse distinct failures into a misleading diagnosis.
    for _,mapping in ipairs({
     {'inventory duplicate object first=','duplicate_object'},
     {'inventory duplicate supplied identity','duplicate_identity'},
     {'inventory faction enumeration incomplete','faction_enumeration_incomplete'},
     {'inventory duplicate faction','duplicate_faction'},
     {'inventory faction membership changed','faction_set_changed'},
     {'inventory object membership changed','object_set_changed'},
     {'inventory invalid fleet count','fleet_count_invalid'},
     {'inventory fleet enumeration changed or incomplete','fleet_enumeration_changed'},
     {'inventory identity or operational state changed','identity_or_operational_changed'},
     {'inventory sector state changed','sector_changed'},
     {'inventory class state changed','class_changed'},
     {'inventory checkpoint failed','checkpoint'},
     {'inventory ship limit exceeded','ship_limit'},
     {'inventory membership limit exceeded','membership_limit'},
     {'inventory local object key collision','object_key_collision'},
     {'invalid faction','invalid_faction'},
    }) do
     if why:find(mapping[1],1,true) then reason=mapping[2];break end
    end
   end
   local details=''
   if reason=='duplicate_object' then
    local a,b,c,d=why:match('inventory duplicate object first=(%d+):(%d+) repeated=(%d+):(%d+)')
    a,b,c,d=tonumber(a),tonumber(b),tonumber(c),tonumber(d)
    if a and b and c and d and a>=1 and a<=1024 and c>=1 and c<=1024 and b>=1 and b<=200000 and d>=1 and d<=200000 then
     details=string.format(' first_faction=%d first_index=%d repeated_faction=%d repeated_index=%d',a,b,c,d)
    end
   end
   log('AUTHORITY_INVENTORY_ERROR tick='..tick..' reason='..reason..details)
   return
  end
  local c,r=result.counts,result.unavailable_reasons
  assert(c.enumerated==c.memberships and c.memberships==c.objects+c.repeated_memberships, 'inventory membership count mismatch')
  assert(c.objects==c.position_observed+c.not_confirmed_operational+c.unavailable, 'inventory count mismatch')
  log(string.format('AUTHORITY_INVENTORY tick=%d enumerated=%d memberships=%d objects=%d repeated_memberships=%d position_observed=%d not_confirmed_operational=%d unavailable=%d unresolved_identity=%d operational_unknown=%d ship_class_not_confirmed=%d ship_class_unknown=%d sector_unavailable=%d ship_identity_unavailable=%d sector_identity_unavailable=%d pose_unavailable=%d consistency=non_atomic coverage=unknown positions_complete=false',
   tick,c.enumerated,c.memberships,c.objects,c.repeated_memberships,c.position_observed,c.not_confirmed_operational,c.unavailable,c.unresolved_identity,
   r.operational_unknown or 0,r.ship_class_not_confirmed or 0,r.ship_class_unknown or 0,r.sector_unavailable or 0,
   r.ship_identity_unavailable or 0,r.sector_identity_unavailable or 0,r.pose_unavailable or 0))
 end)
 if not ok then task=nil;attempted=true;log('AUTHORITY_INVENTORY_ERROR tick='..tostring(tick)..' reason=probe') end
end
X4LAN_AUTHORITY_FIXTURE_INVENTORY_PROBE=M
return M
