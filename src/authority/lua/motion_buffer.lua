-- Read-only motion reconstruction for a single explicitly identified fixture.
-- Adapted from the X4LAN_MOTION LAN-lab motion buffer.
-- No game API calls, object lookup, velocity writes or networking.
local M = {}
local MAX_SEQUENCE = 9007199254740991
local PI = math.pi
local function finite(n)
 return type(n)=='number' and n==n and n~=math.huge and n~=-math.huge
end
local function frame(v)
 return type(v)=='string' and #v>0 and #v<=128 and v:match('^[A-Za-z0-9_.%-]+$')~=nil
end
local function angle(a)
 return (a+PI)%(2*PI)-PI
end
local function vector(v, israte, dimensions)
 if type(v)~='table' or #v~=dimensions then return false end
 for i=1,dimensions do
  local limit=i<=3 and (israte and 100000 or 50000000) or 2*PI
  if not finite(v[i]) or math.abs(v[i])>limit then return false end
 end
 return true
end
local function copy(v)
 if not v then return nil end
 local out={};for i=1,#v do out[i]=v[i] end;return out
end
local function speed(v)
 if not v then return 0 end
 return math.sqrt(v[1]^2+v[2]^2+v[3]^2)
end
local function timestamp(t)
 return finite(t) and t>=0 and t<=1e12
end
local function valid_sample(s,dimensions)
 return type(s)=='table' and frame(s.frame) and type(s.sequence)=='number' and
  s.sequence%1==0 and s.sequence>=1 and s.sequence<=MAX_SEQUENCE and
  timestamp(s.source_time) and vector(s.pose,false,dimensions) and (s.rate==nil or vector(s.rate,true,dimensions))
end
-- A wrapped-Euler derivative is useful for extrapolation, but is not an engine
-- native angular-velocity vector. No derivative is returned across frames,
-- missing samples, zero/negative time, excessive gaps or out-of-bounds values.
function M.estimate(previous, sample, max_gap)
 local dimensions=type(sample)=='table' and type(sample.pose)=='table' and #sample.pose or 0
 if (dimensions~=3 and dimensions~=6) or not valid_sample(previous,dimensions) or not valid_sample(sample,dimensions) or previous.frame~=sample.frame or
    not finite(max_gap) or max_gap<=0 or max_gap>60 then return nil end
 local dt=sample.source_time-previous.source_time
 if dt<=.001 or dt>max_gap or sample.sequence<=previous.sequence then return nil end
 local rate={}
 for i=1,dimensions do
  local delta=sample.pose[i]-previous.pose[i]
  rate[i]=(i>3 and angle(delta) or delta)/dt
 end
 if not vector(rate,true,dimensions) then return nil end
 return rate
end
function M.new(options)
 options=options or {}
 assert(type(options)=='table', 'options must be a table')
 local known={delay=true,horizon=true,stale=true,teleport_distance=true,clock_leak=true,slew=true,dimensions=true,hold_only=true}
 for k in pairs(options) do assert(known[k], 'unknown motion option') end
 local cfg={delay=options.delay or .15,horizon=options.horizon or .35,
  stale=options.stale or .75,teleport_distance=options.teleport_distance or 10000,
  clock_leak=options.clock_leak or .002,slew=options.slew or .1}
 local dimensions=options.dimensions or 6
 assert(dimensions==3 or dimensions==6,'invalid motion dimensions')
 assert(options.hold_only==nil or type(options.hold_only)=='boolean','invalid hold mode')
 local hold_only=options.hold_only==true
 for k,v in pairs(cfg) do
  assert(finite(v) and v>=0, 'invalid motion option: '..k)
 end
 assert(cfg.delay<=60 and cfg.horizon<=60 and cfg.stale>0 and cfg.stale<=60 and
  cfg.teleport_distance<=50000000 and cfg.clock_leak<=1 and cfg.slew<=1, 'motion option out of bounds')
 local samples, offset, last_arrival, last_sequence, last_source = {}, nil, nil, 0, nil
 local lag, lag_at, last_render = nil, nil, nil
 local track={}
 function track:push(s,arrival)
  if not valid_sample(s,dimensions) or not timestamp(arrival) then return false,'invalid' end
  if s.sequence<=last_sequence or (last_source and s.source_time<=last_source) or
     (last_arrival and arrival<last_arrival) or (last_render and arrival<last_render) then return false,'stale' end
  local last=samples[#samples]
  local reason='append'
  if last and s.frame~=last.frame then
   reason='frame'
  elseif last and s.source_time-last.source_time>cfg.stale then
   reason='gap'
  elseif last then
   local d2=0
   for i=1,3 do d2=d2+(s.pose[i]-last.pose[i])^2 end
   local distance=math.sqrt(d2)
   local allowed=cfg.teleport_distance+speed(last.rate)*(s.source_time-last.source_time)
   if distance>allowed then reason='teleport' end
  end
  if reason~='append' then samples={} end
  if not hold_only then
   if offset and last_arrival and arrival>last_arrival then
    offset=offset+cfg.clock_leak*(arrival-last_arrival)
   end
   offset=math.min(offset or math.huge,arrival-s.source_time)
  end
  local rate=copy(s.rate)
  if reason~='append' then rate=nil end
  samples[#samples+1]={frame=s.frame,sequence=s.sequence,source_time=s.source_time,
                       pose=copy(s.pose),rate=rate}
  while #samples>16 do table.remove(samples,1) end
  last_arrival,last_sequence,last_source=arrival,s.sequence,s.source_time
  return true,reason
 end
 function track:render(now)
  if not timestamp(now) or (last_render and now<last_render) or
     (last_arrival and now<last_arrival) then return nil,'invalid-clock' end
  if #samples==0 then return nil,'empty' end
  last_render=now
  if hold_only then
   local last=samples[#samples]
   return {frame=last.frame,source_sequence=last.sequence,pose=copy(last.pose),phase='held-clock-unverified'}
  end
  local wanted=offset+cfg.delay
  -- d(source render time)/d(observer time). A snap or repeated clock value
  -- has no established derivative. A moving lag changes the displayed rate.
  local clock_factor
  if not lag or not lag_at or math.abs(wanted-lag)>1 then lag=wanted
  else
   local elapsed=now-lag_at
   local old_lag=lag;local step=cfg.slew*elapsed
   lag=wanted>lag and math.min(wanted,lag+step) or math.max(wanted,lag-step)
   if elapsed>0 then
    -- At a reached target, lag is locally constant on the forward side.
    if lag==wanted then clock_factor=1
    elseif wanted>old_lag then clock_factor=1-cfg.slew
    else clock_factor=1+cfg.slew end
   end
  end
  lag_at=now
  local target=now-lag
  local first,last=samples[1],samples[#samples]
  local out={frame=last.frame,source_sequence=last.sequence,pose={},phase='held'}
  if target<=first.source_time then
   out.pose=copy(first.pose);out.source_sequence=first.sequence;return out
  end
  for index=2,#samples do
   local a,b=samples[index-1],samples[index]
   if target<=b.source_time then
    local t=(target-a.source_time)/(b.source_time-a.source_time)
    for i=1,dimensions do
     local delta=b.pose[i]-a.pose[i]
     out.pose[i]=i>3 and angle(a.pose[i]+angle(delta)*t) or a.pose[i]+delta*t
    end
    out.phase='interpolated';out.source_sequence=b.sequence
    -- At a knot, adjacent segments may have different slopes. Never infer a
    -- native angular vector from wrapped Euler-coordinate rates.
    if clock_factor and target~=b.source_time then
     local v={};local valid=true
     for i=1,3 do
      v[i]=(b.pose[i]-a.pose[i])/(b.source_time-a.source_time)*clock_factor
      if not finite(v[i]) or math.abs(v[i])>100000 then valid=false end
     end
     if valid then out.linear_velocity=v end
    end
    return out
   end
  end
  local dt=math.min(cfg.horizon,math.max(0,target-last.source_time))
  if last.rate then
   for i=1,dimensions do
    local value=last.pose[i]+last.rate[i]*dt
    out.pose[i]=i>3 and angle(value) or value
   end
   if not vector(out.pose,false,dimensions) then return nil,'out-of-bounds' end
   out.phase=target-last.source_time<cfg.horizon and 'extrapolated' or 'frozen'
   if out.phase=='frozen' and clock_factor then out.linear_velocity={0,0,0}
   elseif clock_factor then
    local v={};local valid=true
    for i=1,3 do
     v[i]=last.rate[i]*clock_factor
     if not finite(v[i]) or math.abs(v[i])>100000 then valid=false end
    end
    if valid then out.linear_velocity=v end
   end
  else
   out.pose=copy(last.pose);out.phase='held-no-rate'
  end
  return out
 end
 return track
end
return M
