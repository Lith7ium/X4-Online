-- Opt-in, read-only inventory of entries returned by faction ship APIs.
-- Runs only in the disposable fixture profile. The collision audit can log
-- saved identities and faction names privately; no component pose is logged.
local M={}
local attempted=false
-- A single already-observed collision only; no component getters. The two
-- faction prefixes are checked with bounded buffers and separate failure codes.
local function duplicate_probe(engine,gate,tick,log,first,first_index,repeated,repeated_index,ship)
 local ok,why=pcall(function()
  local function fail(reason) error(reason,0) end
  local function clock()
   local success,now=pcall(GetCurRealTime)
   if not success or type(now)~='number' or now~=now or now==math.huge or now==-math.huge then fail('clock_unavailable') end
   return now
  end
  local started=clock()
  local function budget()
   local now=clock()
   if now<started or now-started>3 then fail('clock_budget') end
  end
  local function faction_label(value)
   if type(value)~='string' or #value==0 or #value>64 or not value:match('^[A-Za-z0-9_%-]+$') then fail('faction_label_unavailable') end
   return value
  end
  first,repeated=faction_label(first),faction_label(repeated)
  local function saved_id()
   budget()
   local decimal=tostring(ship):gsub('ULL$','')
   if not decimal:match('^%d+$') then fail('runtime_identity_unavailable') end
   local success,saved=pcall(gate.saved_identity,decimal)
   budget()
   if not success or type(saved)~='string' or #saved~=16 or not saved:match('^[0-9a-f]+$') or saved=='0000000000000000' then
    fail('saved_identity_unavailable')
   end
   return saved
  end
  local success,original=pcall(engine.key,ship)
  if not success or type(original)~='string' or original=='' then fail('original_key_unavailable') end
  local before_id=saved_id()
  local function verify(faction,index,label)
   budget()
   if type(index)~='number' or index~=math.floor(index) or index<1 or index>200000 then fail(label..'_index_invalid') end
   local count_ok,before=pcall(engine.fleet_count,faction)
   budget()
   if not count_ok or type(before)~='number' or before~=math.floor(before) or before<0 or before>200000 then fail(label..'_count_unavailable') end
   if before<index then fail(label..'_index_missing') end
   local member_ok,member=pcall(engine.member_at,faction,index)
   budget()
   if not member_ok then fail(label..'_prefix_error') end
   if not member then fail(label..'_entry_missing') end
   local after_ok,after=pcall(engine.fleet_count,faction)
   budget()
   if not after_ok or type(after)~='number' then fail(label..'_recount_unavailable') end
   if after~=before then fail(label..'_count_changed') end
   local key_ok,key=pcall(engine.key,member)
   if not key_ok or type(key)~='string' or key=='' then fail(label..'_key_unavailable') end
   if key~=original then fail(label..'_handle_changed') end
  end
  verify(first,first_index,'first')
  verify(repeated,repeated_index,'repeated')
  if saved_id()~=before_id then fail('saved_identity_changed') end
  log(string.format('AUTHORITY_DUPLICATE_TARGET_PRIVATE tick=%d first_index=%d repeated_index=%d first_faction_private=%s repeated_faction_private=%s saved_private=%s consistency=target_rechecked_non_atomic',
   tick,first_index,repeated_index,first,repeated,before_id))
 end)
 if not ok then
  -- Error codes are fixed by this routine, never forwarded from a getter.
  local allowed={clock_unavailable=true,clock_budget=true,faction_label_unavailable=true,runtime_identity_unavailable=true,
   saved_identity_unavailable=true,saved_identity_changed=true,original_key_unavailable=true}
  for _,side in ipairs({'first','repeated'}) do
   for _,suffix in ipairs({'index_invalid','count_unavailable','index_missing','prefix_error','entry_missing',
    'recount_unavailable','count_changed','key_unavailable','handle_changed'}) do allowed[side..'_'..suffix]=true end
  end
  log('AUTHORITY_DUPLICATE_TARGET_ERROR tick='..tostring(tick)..' reason='..(allowed[why] and why or 'probe_error'))
 end
end
function M.sample(cfg,tick,log,gate)
 if not cfg.native_gate_authority_inventory or attempted or tick<30 then return end
 attempted=true
 local ok=pcall(function()
  assert(cfg.native_gate_authority_inventory==true and cfg.native_gate_authority_scan==true, 'inventory not explicitly enabled')
  assert(cfg.native_gate_hash=='battle' and cfg.native_gate_snapshot_fixture and #cfg.native_gate_snapshot_fixture==12,
   'saved battle fixture required')
  local ffi=require('ffi')
  ffi.cdef[[const char* GetSaveFolderPath(void);]]
  local path=ffi.string(ffi.C.GetSaveFolderPath()):gsub('\\','/'):gsub('/+$','')
  assert(cfg.test_profile=='45841' and path:sub(-#'/45841/save')=='/45841/save', 'isolated profile required')
  assert(type(gate)=='table' and type(gate.saved_identity)=='function', 'saved identity table required')
  assert(type(GetCurRealTime)=='function', 'real-time clock unavailable')
  local started=GetCurRealTime()
  assert(type(started)=='number' and started==started and started~=math.huge and started~=-math.huge, 'invalid clock')
  local function saved_identity(object)
   local decimal=tostring(object):gsub('ULL$','')
   if not decimal:match('^%d+$') then return nil end
   local value=gate.saved_identity(decimal)
   if type(value)~='string' or #value~=16 or not value:match('^[0-9a-f]+$') or value=='0000000000000000' then return nil end
   return value
  end
  local scanner=assert(X4LAN_AUTHORITY_SHIP_SCAN, 'inventory scanner missing')
  local engine=assert(X4LAN_AUTHORITY_SHIP_ENGINE, 'inventory engine missing').new()
  local result,why=scanner.inventory(engine,{ship=saved_identity,sector=saved_identity},
   {identity_scope='isolated-snapshot-local-diagnostic',max_factions=1024,max_ships=200000,max_fleet=200000,max_memberships=1000000,
    on_duplicate=function(first,first_index,repeated,repeated_index,ship)
     duplicate_probe(engine,gate,tick,log,first,first_index,repeated,repeated_index,ship)
    end,
    checkpoint=function()
     local now=GetCurRealTime()
     assert(type(now)=='number' and now==now and now>=started and now-started<=12, 'inventory time budget exceeded')
    end})
  if not result then
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
  log(string.format('AUTHORITY_INVENTORY tick=%d enumerated=%d memberships=%d objects=%d repeated_memberships=%d position_observed=%d not_confirmed_operational=%d unavailable=%d unresolved_identity=%d operational_unknown=%d ship_class_not_confirmed=%d ship_class_unknown=%d sector_unavailable=%d ship_identity_unavailable=%d sector_identity_unavailable=%d pose_unavailable=%d coverage=unknown positions_complete=false',
   tick,c.enumerated,c.memberships,c.objects,c.repeated_memberships,c.position_observed,c.not_confirmed_operational,c.unavailable,c.unresolved_identity,
   r.operational_unknown or 0,r.ship_class_not_confirmed or 0,r.ship_class_unknown or 0,r.sector_unavailable or 0,
   r.ship_identity_unavailable or 0,r.sector_identity_unavailable or 0,r.pose_unavailable or 0))
 end)
 if not ok then log('AUTHORITY_INVENTORY_ERROR tick='..tostring(tick)..' reason=probe') end
end
X4LAN_AUTHORITY_FIXTURE_INVENTORY_PROBE=M
return M
