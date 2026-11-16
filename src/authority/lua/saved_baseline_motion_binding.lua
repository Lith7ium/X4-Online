-- Opt-in read-only saved-registry binding. Does not establish checkpoint or
-- cross-process identity; the caller owns the load/process fence and event hook.
local M={}
local MAX=9007199254740991
local function integer(v)return type(v)=='number' and v==v and v>=1 and v<=MAX and v%1==0 end
local function token(v)return type(v)=='string' and #v==32 and v:match('^[0-9a-f]+$')~=nil end
function M.new_x4(o)
 if type(o)~='table' or o.enabled~=true then return nil,'disabled' end
 assert(token(o.epoch) and token(o.generation) and token(o.nonce))
 assert(integer(o.baseline) and integer(o.index) and o.index<=o.baseline)
 assert(type(o.replica)=='table' and type(o.replica.new_saved_baseline_x4)=='function')
 assert(type(o.guard)=='function' and type(o.saved_baseline_guard)=='function' and type(o.complete)=='function')
 local c={};for k,v in pairs(o)do c[k]=v end
 local complete=c.complete
 c.complete=function(r)
  local out={epoch=r.epoch,generation=r.generation,index=r.index,sequence=r.sequence,sector_macro=r.sector_macro,
   evidence='local_saved_registry',checkpoint_identity_proven=false,cross_process_identity_proven=false}
  if complete(out)~=true or getmetatable(out)~=nil then return false end
  if out.epoch~=r.epoch or out.generation~=r.generation or out.index~=r.index or out.sequence~=r.sequence or
     out.sector_macro~=r.sector_macro or out.evidence~='local_saved_registry' or
     out.checkpoint_identity_proven~=false or out.cross_process_identity_proven~=false then return false end
  for k in pairs(out)do
   if k~='epoch' and k~='generation' and k~='index' and k~='sequence' and k~='sector_macro' and
      k~='evidence' and k~='checkpoint_identity_proven' and k~='cross_process_identity_proven' then return false end
  end
  return true
 end
 return c.replica.new_saved_baseline_x4(c)
end
X4LAN_SAVED_BASELINE_MOTION_BINDING=M
return M
