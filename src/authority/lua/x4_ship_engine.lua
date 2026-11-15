-- X4 LuaJIT bindings. Construction is explicit and performs no game mutation.
-- Requires a loaded X4 UI environment and the corresponding exported functions.
local M = {}
function M.new()
 local ffi = require('ffi')
 if not pcall(ffi.typeof, 'UniverseID') then ffi.cdef('typedef uint64_t UniverseID;') end
 if not pcall(ffi.typeof, 'UIPosRot') then ffi.cdef('typedef struct { float x,y,z,yaw,pitch,roll; } UIPosRot;') end
 ffi.cdef[[
 uint32_t GetAllFactions(const char**,uint32_t,bool);
 uint32_t GetNumAllFactionShips(const char*);
 uint32_t GetAllFactionShips(UniverseID*,uint32_t,const char*);
 bool IsComponentOperational(UniverseID);
 bool IsComponentClass(UniverseID,const char*);
 UniverseID GetContextByClass(UniverseID,const char*,bool);
 UIPosRot GetObjectPositionInSector(UniverseID);
 ]]
 local C = ffi.C
 -- Resolve exports eagerly so a missing export fails before sampling.
 local allf, count, allships = C.GetAllFactions, C.GetNumAllFactionShips, C.GetAllFactionShips
 local operational, isclass, context, position = C.IsComponentOperational, C.IsComponentClass, C.GetContextByClass, C.GetObjectPositionInSector
 return {
  factions=function(cap)
   local buffer=ffi.new('const char*[?]',cap)
   local n=tonumber(allf(buffer,cap,true)); if n >= cap then return {},true,n end
   local result={}; for i=0,n-1 do if buffer[i]==nil then error('null faction name') end; result[#result+1]=ffi.string(buffer[i]) end
   return result,false
  end,
  fleet_count=function(faction) return tonumber(count(faction)) end,
  fleet=function(faction,cap)
   local buffer=ffi.new('UniverseID[?]',cap)
   local n=tonumber(allships(buffer,cap,faction)); if n >= cap then return {},true end
   local result={}; for i=0,n-1 do result[#result+1]=buffer[i] end
   return result,false
  end,
  key=function(handle) if handle==nil or handle==0 then return '' end; return tostring(handle) end,
  operational=function(ship) return operational(ship) end,
  is_ship=function(ship) return isclass(ship,'ship') end,
  sector=function(ship) local result=context(ship,'sector',false); if result==0 then return nil end; return result end,
  pose=function(ship) local p=position(ship); return {x=tonumber(p.x),y=tonumber(p.y),z=tonumber(p.z),yaw=tonumber(p.yaw),pitch=tonumber(p.pitch),roll=tonumber(p.roll)} end,
 }
end
X4LAN_AUTHORITY_SHIP_ENGINE = M
return M
