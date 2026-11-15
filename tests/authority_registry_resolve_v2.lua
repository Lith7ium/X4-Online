-- Synthetic driver only; no MD, X4, files, networking, or native actor bindings.
local module=assert(loadfile('tools/dev/authority_registry_resolve_v2.lua'))()
local epoch,id=string.rep('a',32),string.rep('b',32)
local function setup(overrides)
 local now=0;local sent={}
 local o={enabled=true,epoch=epoch,timeout=2,clock=function() return now end,
  issue=function(s,c,args) sent[#sent+1]={s,c,args};return true end,
  valid=function(v) return v=='actor' end,key=function(v) assert(v=='actor');return 'local-key' end}
 for k,v in pairs(overrides or {}) do o[k]=v end
 return assert(module.new(o)),sent,function(t) now=t end
end
local function row() return {request_id=id,epoch=epoch,index=7,actor='actor',status='ok'} end
do
 local c,sent=setup();assert(c:resolve(id,7));assert(sent[1][1]=='X4AuthorityRegistryResolveV2' and sent[1][2]=='Resolve')
 local ok,r=c:response(row());assert(ok and r.actor=='actor' and r.index==7 and r.local_key=='local-key')
 assert(c:state()=='idle');assert(not c:resolve(id,7) and c:state()=='failed')
end
for _,change in ipairs({
 function(r) r.request_id=string.rep('c',32) end,function(r) r.epoch=string.rep('c',32) end,
 function(r) r.index=8 end,function(r) r.actor='other' end,function(r) r.status='fault' end,
 function(r) r.extra=true end,
}) do
 local c=setup();assert(c:resolve(id,7));local r=row();change(r)
 assert(not c:response(r) and c:state()=='failed');assert(not c:response(row()))
end
do
 local c=setup();assert(c:resolve(id,7));local r=row();r.status='unavailable';r.actor=nil
 local ok,why=c:response(r);assert(not ok and why=='unavailable' and c:state()=='failed')
end
do
 local c,_,set_time=setup();assert(c:resolve(id,7));set_time(2)
 local ok,why=c:response(row());assert(not ok and why=='timeout' and c:state()=='failed')
end
do
 local c,set_time,called
 c,_,set_time=setup({valid=function() called=true;set_time(3);return true end})
 assert(c:resolve(id,7));local ok,why=c:response(row())
 assert(called and not ok and why=='timeout' and c:state()=='failed')
end
do
 local c;c=setup({issue=function() c:close();return true end})
 assert(not c:resolve(id,7) and c:state()=='closed')
end
do
 local c;c=setup({valid=function() c:close();return true end})
 assert(c:resolve(id,7));assert(not c:response(row()) and c:state()=='closed')
end
do
 local c=setup();assert(c:resolve(id,7));assert(c:response(row()))
 assert(not c:response(row()) and c:state()=='failed')
end
do
 local c=setup();assert(c:resolve(id,7));assert(c:response(row()))
 assert(c:resolve(string.rep('c',32),7))
 local ok,why=c:response(row());assert(not ok and why=='response_mismatch' and c:state()=='failed')
end
do
 local r=row();local c=setup({valid=function(actor) assert(actor=='actor');r.actor='other';return true end})
 assert(c:resolve(id,7));local ok,value=c:response(r)
 assert(ok and value.actor=='actor')
end
print('ResolveV2 synthetic contract passed')
