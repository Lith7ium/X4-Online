local M=dofile('tools/dev/authority_positive_seat_live_owner.lua');assert(M.new({enabled=false})==nil)
local function rig(kind)
 local t,g,paused=0,3,true;local logs={};local app
 local report={status=kind=='candidate' and 'candidate_observed' or 'inconclusive',seat_free_proven=false,
  player_control_proven=false,same_actor_proven=false,coverage_proven=false}
 local p={phase='idle'}
 function p:start()self.phase='waiting';return true end
 function p:tick()if kind=='timeout' then self.phase='done';return true,report end;return true end
 function p:response()self.phase='done';return true,report end
 function p:inconclusive()self.phase='done';return true,report end
 function p:state()return self.phase end
 local o={enabled=true,timeout=20,guard=function()assert(paused);return t,g,'1','2' end,make=function()return p end,
  log=function(s)logs[#logs+1]=s end}
 app=M.new(o);return app,logs,function(v)t=v end,function(v)paused=v end,function(v)g=v end
end
for _,kind in ipairs({'candidate','none','timeout'}) do
 local a,l=rig(kind);assert(a:tick());if kind=='candidate' then assert(a:response('v')) elseif kind=='none' then assert(a:inconclusive('v')) else assert(a:tick()) end
 assert(a:tick() and a:state()=='done');assert(table.concat(l,',')=='START,'..(kind=='candidate' and 'CANDIDATE' or 'INCONCLUSIVE')..',DONE')
 assert(not a:response('late') and l[#l]=='ERROR FAULT')
end
local a,l,_,pause=rig('candidate');assert(a:tick());pause(false);assert(not a:response('v') and l[#l]=='ERROR FAULT')
local b,_,clock=rig('candidate');assert(b:tick());clock(20);assert(not b:tick())
print('positive-seat owner state tests passed')
