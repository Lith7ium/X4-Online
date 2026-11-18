package.path = './src/authority/lua/?.lua;' .. package.path
local observation = require('map_render_observation')

local function make_sampler(state, maximum)
	return assert(observation.new({
		max_components = maximum or 16,
		get_map = function()
			if not state.open then return nil, nil end
			return state.menu, state.handle
		end,
		handle_key = function(handle) return tostring(handle) end,
		get_count = function() return state.count end,
		get_components = function(_, capacity)
			local values = {}
			for index, value in ipairs(state.raw_ids) do values[index] = value end
			return values, state.filled_count or math.min(#values, capacity)
		end,
		component_id = function(value) return value end,
	}))
end

local state = {open = true, menu = {}, handle = 'map-1', count = 4,
	raw_ids = {'0', '9007199254740993', '77', '77'}}
local snapshot = assert(make_sampler(state):sample())
assert(snapshot.map_open and snapshot.raw_count == 4)
assert(table.concat(snapshot.component_ids, ',') == '0,9007199254740993,77,77')

state.open = false
snapshot = assert(make_sampler(state):sample())
assert(not snapshot.map_open and snapshot.raw_count == 0 and #snapshot.component_ids == 0)

state.open, state.count = true, 2
state.raw_ids = {'11', '12'}
state.filled_count = 3
local failed, reason = make_sampler(state):sample()
assert(failed == nil and reason == 'component_list_changed')

state.filled_count = nil
state.count = 2
state.raw_ids = {'11', '12'}
local reads = 0
local changing = assert(observation.new({
	max_components = 16,
	get_map = function()
		reads = reads + 1
		return state.menu, reads >= 3 and 'map-2' or 'map-1'
	end,
	handle_key = function(handle) return handle end,
	get_count = function() return 2 end,
	get_components = function() return {'11', '12'}, 2 end,
	component_id = function(value) return value end,
}))
failed, reason = changing:sample()
assert(failed == nil and reason == 'map_changed')

state.count = 17
failed, reason = make_sampler(state, 16):sample()
assert(failed == nil and reason == 'invalid_component_count')

state.count, state.raw_ids = 1, {'not-a-decimal-id'}
failed, reason = make_sampler(state):sample()
assert(failed == nil and reason == 'invalid_component_id')

local disabled, disabled_reason = observation.new_x4({enabled = false})
assert(disabled == nil and disabled_reason == 'disabled')

print('map renderer observation checks passed')
