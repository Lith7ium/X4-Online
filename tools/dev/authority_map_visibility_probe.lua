-- Opt-in map visibility probe (Cobalt, disposable Windows profile only).
--
-- Question: does GetMapRenderedComponents still list a known, radar-visible NPC after the
-- player pans the map so that the NPC's icon is offscreen?
--
-- Order, all in one X4 process started by authority_map_visibility_windows.py:
--   start menu -> NewGame(cfg.gamestart) -> player valid -> pick one NPC ship in the player's
--   sector (known, radar-visible, not player-owned, cfg.min_m..cfg.max_m from the player) ->
--   Pause() -> open the map without a focus parameter (no selection) -> three views:
--     onscreen   camera centred on the player at cfg.distance
--     offscreen  same distance, camera offset moved by cfg.pan_factor * cfg.distance along X
--                (fallback when that is not reached: focus a far station in the same sector)
--     back       the onscreen state again
--   For every view: settle, read camera/focus/selection, sample the raw renderer list, ask the
--   runner for a screenshot (log row SHOT), wait for its ack file, sample the list again.
-- Writes nothing but log rows and map UI state. No save, order, position or subscription change.
-- X4's UI Lua has no io library; the runner answers through ./extensions/<ext>/ack_<n>.lua (loadfile).
local cfg = X4COBALT_MAPVIS
if type(cfg) ~= 'table' or cfg.enabled ~= true then return end

local ffi = require('ffi')
local C = ffi.C
local function declare(text) pcall(ffi.cdef, text) end  -- the stock map may already declare these
declare('typedef uint64_t UniverseID;')
declare('typedef struct { float x; float y; float z; float yaw; float pitch; float roll; } UIPosRot;')
declare('typedef struct { UIPosRot offset; float cameradistance; } HoloMapState;')
for _, text in ipairs({
	'const char* GetGameStartName(void);', 'bool IsStartmenu(void);', 'bool IsPlayerValid(void);',
	'bool IsGamePaused(void);', 'const char* GetSaveFolderPath(void);', 'double GetCurrentGameTime(void);',
	'UniverseID GetPlayerOccupiedShipID(void);', 'UniverseID GetPlayerObjectID(void);',
	'UniverseID GetContextByClass(UniverseID componentid, const char* classname, bool includeself);',
	'bool IsComponentClass(UniverseID componentid, const char* classname);',
	'bool IsComponentOperational(UniverseID componentid);',
	'UIPosRot GetObjectPositionInSector(UniverseID objectid);',
	'uint32_t GetNumAllFactions(bool includehidden);',
	'uint32_t GetAllFactions(const char** result, uint32_t resultlen, bool includehidden);',
	'void GetMapState(UniverseID holomapid, HoloMapState* state);',
	'void SetMapState(UniverseID holomapid, HoloMapState state);',
	'UniverseID GetMapFocusComponent(UniverseID holomapid);',
	'void SetFocusMapComponent(UniverseID holomapid, UniverseID componentid, bool resetplayerpan);',
	'uint32_t GetNumMapSelectedComponents(UniverseID holomapid);',
}) do declare(text) end

local EXT_DIR = './extensions/' .. tostring(cfg.extension_id or 'x4_cobalt_mapvis') .. '/'
local SETTLE_STEP, SETTLE_SAMPLES, SETTLE_TIMEOUT, ACK_TIMEOUT = 0.25, 3, 10.0, 60.0

local function log(text) DebugError('[X4LAN] AUTH_MAPVIS ' .. text) end
local function id_text(value) return (tostring(ffi.cast('UniverseID', value)):gsub('ULL$', '')) end
local function id64(value) return ConvertStringTo64Bit(tostring(value)) end
local function now() return getElapsedTime() end
local function num(value) return ('%.17g'):format(value) end

local function check_profile()
	local path = C.GetSaveFolderPath()
	assert(path ~= nil and path ~= ffi.NULL, 'save folder unavailable')
	local text = ffi.string(path):gsub('\\', '/'):gsub('/+$', '')
	assert(text:match('/' .. cfg.profile .. '/save$'), 'not the disposable profile ' .. cfg.profile)
end

local function player_ship()
	local ship = C.GetPlayerOccupiedShipID()
	if ship == 0 then ship = C.GetPlayerObjectID() end
	return ship
end

local function distance(a, b)
	local dx, dy, dz = a.x - b.x, a.y - b.y, a.z - b.z
	return math.sqrt(dx * dx + dy * dy + dz * dz)
end

local function factions()
	local count = C.GetNumAllFactions(true)
	local buffer = ffi.new('const char*[?]', math.max(count, 1))
	count = C.GetAllFactions(buffer, count, true)
	local list = {}
	for index = 0, count - 1 do list[#list + 1] = ffi.string(buffer[index]) end
	return list
end

-- The nearest known, radar-visible, operational NPC ship in the player's sector, cfg.min_m..cfg.max_m away.
local function pick_npc(sector, player)
	local origin = C.GetObjectPositionInSector(player)
	local sector_text, player_text = id_text(sector), id_text(player)
	local sector_lua = ConvertStringToLuaID(sector_text)
	local best, best_m, candidates = nil, nil, 0
	for _, faction in ipairs(factions()) do
		if faction ~= 'player' then
			for _, object in ipairs(GetContainedObjectsByOwner(faction, sector_lua) or {}) do
				local ship = id64(object)
				if ship and id_text(ship) ~= '0' and id_text(ship) ~= player_text and C.IsComponentClass(ship, 'ship') and
					id_text(C.GetContextByClass(ship, 'sector', false)) == sector_text then
					local known, radar = GetComponentData(object, 'isknown', 'isradarvisible')
					local metres = distance(origin, C.GetObjectPositionInSector(ship))
					if known and radar and C.IsComponentOperational(ship) and metres >= cfg.min_m and
						metres <= cfg.max_m then
						candidates = candidates + 1
						if not best_m or metres < best_m then best, best_m = ship, metres end
					end
				end
			end
		end
	end
	return best, best_m, candidates
end

local function find_map()
	for _, menu in ipairs(Menus or {}) do
		if type(menu) == 'table' and menu.name == 'MapMenu' and menu.shown == true and menu.holomap and
			menu.holomap ~= 0 then
			return menu, ffi.cast('UniverseID', menu.holomap)
		end
	end
end

local function read_state(map)
	local state = ffi.new('HoloMapState')
	C.GetMapState(map, state)
	local o = state.offset
	return {x = o.x, y = o.y, z = o.z, yaw = o.yaw, pitch = o.pitch, roll = o.roll, distance = state.cameradistance}
end

local function same_state(a, b, tolerance)
	for _, key in ipairs({'x', 'y', 'z', 'distance'}) do
		if math.abs(a[key] - b[key]) > tolerance then return false end
	end
	for _, key in ipairs({'yaw', 'pitch', 'roll'}) do
		if math.abs(a[key] - b[key]) > 1e-3 then return false end
	end
	return true
end

local function write_state(map, target)
	local state = ffi.new('HoloMapState')
	state.offset.x, state.offset.y, state.offset.z = target.x, target.y, target.z
	state.offset.yaw, state.offset.pitch, state.offset.roll = target.yaw, target.pitch, target.roll
	state.cameradistance = target.distance
	C.SetMapState(map, state)
end

local function state_fields(prefix, s)
	return ('%s_x=%s %s_y=%s %s_z=%s %s_yaw=%s %s_pitch=%s %s_roll=%s %s_distance=%s'):format(
		prefix, num(s.x), prefix, num(s.y), prefix, num(s.z), prefix, num(s.yaw), prefix, num(s.pitch),
		prefix, num(s.roll), prefix, num(s.distance))
end

local probe = {stage = 'initial', views = {}, seq = 0}
X4COBALT_MAPVIS_PROBE = probe  -- offline tests reach it

local sampler
local function sample_list()
	local observation, reason = sampler:sample()
	if not observation then return nil, reason end
	local set = {}
	for _, id in ipairs(observation.component_ids) do set[id] = true end
	return observation, set
end

-- One view: target camera (or a focus fallback) -> settle -> record -> screenshot -> record again.
local function begin_view(name, target, focus)
	probe.view = {name = name, target = target, focus = focus, started = now(), samples = {}, stage = 'settling'}
	if focus then
		C.SetFocusMapComponent(probe.map, focus, true)
	end
	if target then write_state(probe.map, target) end
	probe.stage = 'view'
end

local function record_view(view, phase)
	local observation, set = sample_list()
	if not observation then error('list ' .. tostring(set)) end
	local s = read_state(probe.map)
	local npc_pos = C.GetObjectPositionInSector(probe.npc)
	local player_pos = C.GetObjectPositionInSector(probe.player)
	local known, radar = GetComponentData(ConvertStringToLuaID(probe.npc_id), 'isknown', 'isradarvisible')
	log(('VIEW view=%s phase=%s npc=%s npc_listed=%s player=%s player_listed=%s raw_count=%d focus=%s selected=%d ' ..
		'paused=%s game_time=%s npc_known=%s npc_radar=%s npc_player_m=%s reached=%s control=%s %s%s'):format(
		view.name, phase, probe.npc_id, tostring(set[probe.npc_id] == true), probe.player_id,
		tostring(set[probe.player_id] == true), observation.raw_count, id_text(C.GetMapFocusComponent(probe.map)),
		C.GetNumMapSelectedComponents(probe.map), tostring(C.IsGamePaused()), num(C.GetCurrentGameTime()),
		tostring(known == true), tostring(radar == true), num(distance(npc_pos, player_pos)),
		tostring(view.reached), view.control, state_fields('camera', s),
		view.target and (' ' .. state_fields('target', view.target)) or ''))
	log(('LIST view=%s phase=%s ids=%s'):format(view.name, phase, table.concat(observation.component_ids, ',')))
end

local function settle()
	local view = probe.view
	local s = read_state(probe.map)
	local last = view.samples[#view.samples]
	if last and same_state(last, s, 0.01) then
		view.samples[#view.samples + 1] = s
	else
		view.samples = {s}
	end
	local stable = #view.samples >= SETTLE_SAMPLES
	if not stable and now() - view.started < SETTLE_TIMEOUT then return false end
	local tolerance = math.max(1.0, 0.01 * cfg.distance)
	view.reached = stable and
		(not view.focus or id_text(C.GetMapFocusComponent(probe.map)) == id_text(view.focus)) and
		(not view.target or same_state(s, view.target, tolerance))
	view.stable = stable
	return true
end

local function frame()
	local stage = probe.stage
	if stage == 'done' or stage == 'failed' then return end
	if stage == 'initial' then
		check_profile()
		if C.IsStartmenu() then
			log('NEWGAME gamestart=' .. cfg.gamestart)
			probe.stage = 'starting'
			Helper.addDelayedOneTimeCallbackOnUpdate(function() NewGame(cfg.gamestart) end, true, now() + 3)
			return
		end
		if not C.IsPlayerValid() or ffi.string(C.GetGameStartName()) ~= cfg.gamestart then return end
		probe.loaded_at = probe.loaded_at or now()
		if now() - probe.loaded_at < cfg.warmup_s then return end
		probe.player = player_ship()
		probe.player_id = id_text(probe.player)
		probe.sector = C.GetContextByClass(probe.player, 'sector', false)
		local npc, metres, candidates = pick_npc(probe.sector, probe.player)
		log(('PICK player=%s sector=%s npc=%s npc_player_m=%s candidates=%d'):format(
			probe.player_id, id_text(probe.sector), npc and id_text(npc) or 'none', metres and num(metres) or 'none',
			candidates))
		if not npc then error('no known radar-visible NPC ship in range') end
		probe.npc, probe.npc_id = npc, id_text(npc)
		Pause()
		probe.stage = 'pausing'
		return
	end
	if stage == 'starting' then return end
	if stage == 'pausing' then
		if not C.IsGamePaused() then return end
		sampler = assert(X4LAN_MAP_RENDER_OBSERVATION.new_x4({enabled = true}))
		OpenMenu('MapMenu', {0, 0, true}, nil)
		probe.opened_at = now()
		probe.stage = 'opening'
		return
	end
	if stage == 'opening' then
		local menu, map = find_map()
		if not menu then
			if now() - probe.opened_at > 15 then error('map did not open') end
			return
		end
		if now() - probe.opened_at < cfg.map_settle_s then return end
		probe.map = map
		local initial = read_state(map)
		log('MAP_OPEN ' .. state_fields('camera', initial))
		probe.home = {x = initial.x, y = initial.y, z = initial.z, yaw = initial.yaw, pitch = initial.pitch,
			roll = initial.roll, distance = cfg.distance}
		probe.plan = {'onscreen', 'offscreen', 'back'}
		begin_view('onscreen', probe.home)
		probe.view.control = 'set_map_state'
		return
	end
	if stage == 'view' then
		if now() - (probe.view.last_step or 0) < SETTLE_STEP then return end
		probe.view.last_step = now()
		if not settle() then return end
		local view = probe.view
		if view.name == 'offscreen' and not view.reached and not view.fallback_tried and cfg.far_station then
			-- SetMapState did not reach the pan target: record it, then try the focus fallback once.
			record_view(view, 'pan_failed')
			view.fallback_tried = true
			local far = cfg.far_station(probe)
			if far then
				view.focus, view.target, view.control = far, nil, 'focus_far_station'
				view.samples, view.started = {}, now()
				C.SetFocusMapComponent(probe.map, far, true)
				return
			end
		end
		record_view(view, 'before_shot')
		probe.seq = probe.seq + 1
		view.seq, view.shot_at = probe.seq, now()
		log(('SHOT view=%s seq=%d'):format(view.name, view.seq))
		probe.stage = 'shot'
		return
	end
	if stage == 'shot' then
		local view = probe.view
		local ok, chunk = pcall(loadfile, EXT_DIR .. 'ack_' .. view.seq .. '.lua')
		if not (ok and chunk) then
			if now() - view.shot_at > ACK_TIMEOUT then error('no screenshot ack for ' .. view.name) end
			return
		end
		local ack = chunk()
		assert(type(ack) == 'table' and ack.seq == view.seq, 'wrong screenshot ack')
		record_view(view, 'after_shot')
		probe.views[#probe.views + 1] = view
		table.remove(probe.plan, 1)
		local next_name = probe.plan[1]
		if next_name == 'offscreen' then
			local home = probe.home
			begin_view('offscreen', {x = home.x + cfg.pan_factor * cfg.distance, y = home.y, z = home.z, yaw = home.yaw,
				pitch = home.pitch, roll = home.roll, distance = home.distance})
			probe.view.control = 'set_map_state'
		elseif next_name == 'back' then
			begin_view('back', probe.home, probe.views[2].focus and probe.player or nil)
			probe.view.control = probe.views[2].focus and 'focus_player_then_set_map_state' or 'set_map_state'
		else
			probe.stage = 'done'
			log('DONE views=' .. #probe.views)
		end
		return
	end
end

-- Fallback pan: the station in the player's sector farthest from the NPC, at least 3 view distances away.
cfg.far_station = cfg.far_station or function(p)
	local origin = C.GetObjectPositionInSector(p.npc)
	local sector_lua = ConvertStringToLuaID(id_text(p.sector))
	local best, best_m
	for _, faction in ipairs(factions()) do
		for _, object in ipairs(GetContainedStationsByOwner(faction, sector_lua) or {}) do
			local station = id64(object)
			local metres = distance(origin, C.GetObjectPositionInSector(station))
			if metres >= 3 * cfg.distance and (not best_m or metres > best_m) then best, best_m = station, metres end
		end
	end
	if best then log(('FALLBACK station=%s npc_station_m=%s'):format(id_text(best), num(best_m))) end
	return best
end

SetScript('onUpdate', function()
	local ok, err = pcall(frame)
	if not ok and probe.stage ~= 'failed' then
		probe.stage = 'failed'
		log('ERROR ' .. tostring(err):gsub('%s+', ' '))
	end
end)
