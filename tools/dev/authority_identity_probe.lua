-- This helper is included only in the disposable identity experiment overlay.
local cfg=X4LAN_CONFIG
if not cfg or not cfg.authority_identity_phase then return end
local phase=cfg.authority_identity_phase
assert(phase=='save' or phase=='load')
local actors={};local state='new';local failed=false;local named_at
local names={'Authority identity alpha 7181','Authority identity beta 7182'}
local function log(s) DebugError('[X4LAN] AUTH_IDENTITY '..phase..' '..s) end
local function fail(s) if not failed then failed=true;log('ERROR '..s) end end
for i=1,2 do
 RegisterEvent('X4AuthorityIdentity.Actor'..i,function(_,v)
  if state~='inspect' or actors[i] then fail('unexpected_actor');return end
  local id=ConvertIDTo64Bit(v);if not id or id==0 then fail('invalid_actor');return end
  actors[i]=tostring(id):gsub('ULL$','')
 end)
end
RegisterEvent('X4AuthorityIdentity.Spawned',function(_,count)
 if state~='spawn' or tonumber(count)~=2 then fail('spawn');return end
 state='inspect';AddUITriggeredEvent('X4AuthorityIdentity','Inspect',{})
end)
RegisterEvent('X4AuthorityIdentity.Missing',function() fail('missing_refs') end)
RegisterEvent('X4AuthorityIdentity.Inspected',function(_,count)
 if state~='inspect' or tonumber(count)~=2 or not actors[1] or not actors[2] or actors[1]==actors[2] then fail('inspect');return end
 for i=1,2 do
  if phase=='save' then SetComponentName(ConvertStringToLuaID(actors[i]),names[i]) end
 end
 state='named';named_at=GetCurRealTime()

end)
function X4LAN_IDENTITY_READY()
 if failed then error('identity experiment failed') end
 if state=='named' then
  local properties={}
  for i=1,2 do
   local name,macro=GetComponentData(ConvertStringToLuaID(actors[i]),'name','macro')
   if name~=names[i] or macro~='ship_arg_s_fighter_01_a_macro' then
    if GetCurRealTime()-named_at>10 then fail('properties_'..i);error('fixture properties unavailable') end
    return false
   end
   properties[i]={name=name,macro=macro}
  end
  for i=1,2 do
   log('ACTOR '..i..' id='..actors[i]..' name='..properties[i].name..' macro='..properties[i].macro)
  end
  state='done';log('READY')
 end
 if state=='new' then
  if phase=='save' then state='spawn';AddUITriggeredEvent('X4AuthorityIdentity','Spawn',{})
  else state='inspect';AddUITriggeredEvent('X4AuthorityIdentity','Inspect',{}) end
 end
 return state=='done'
end
