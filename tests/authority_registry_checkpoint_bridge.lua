-- Synthetic integration: generated installer output + real snapshot/gate/control
-- owners. The engine, MD responses and transport are fakes, not native evidence.
local ui, scenario = assert(arg[1]), assert(arg[2])
local lease, world_epoch = string.rep('a', 32), string.rep('b', 32)
local current_run = string.rep('d', 32)
local real_time, game_time, paused = 0, 100, true
local handlers, callbacks, incoming, sent, logs, saves = {}, {}, {}, {}, {}, {}
local frame, stored_marker, sealed_run
local capture_number = 0
local binding_bits, operational_bits = '110', '100'

package.loaded.ffi = {cdef=function() end, C={
    IsPlayerValid=function() return true end,
    IsGamePaused=function() return paused end,
    ReloadSaveList=function() end,
    IsSaveListLoadingComplete=function() return true end,
}}
local socket = {
    send=function(_, packet) sent[#sent + 1] = packet; return true end,
    pending=function() return #incoming > 0 end,
    receive=function() return table.remove(incoming, 1) end,
}
package.loadlib = function()
    return function() return {open=function() return socket end} end
end
function GetCurRealTime() return real_time end
function GetSaveList() return {} end
function DebugError(message) logs[#logs + 1] = message end
function RegisterEvent(event, callback)
    assert(not handlers[event], 'duplicate event handler')
    handlers[event] = callback
end
function SetScript(name, callback) assert(name == 'onUpdate'); frame = callback end
function X4LAN_AUTHORITY_RECOVERY_READY() return true end
function X4LAN_AUTHORITY_RECOVERY_UPDATE() end

local function queue_event(event, value)
    callbacks[#callbacks + 1] = function() assert(handlers[event], event)(nil, value) end
end
function AddUITriggeredEvent(screen, action, request)
    if screen == 'X4AuthorityCheckpointMarker' then
        assert(action == 'Store' and request.marker == sealed_run,
            'marker stored before complete fresh capture')
        stored_marker = request.marker
        queue_event('X4AuthorityCheckpointMarker.Stored', stored_marker)
        return true
    end
    assert(screen == 'X4AuthorityRegistryAvailabilitySnapshot')
    local prefix = request.request_id..'|'..request.run_id..'|'..action..'|'
    local response
    if action == 'Inspect' then
        assert(request.run_id == current_run and request.first == 1 and request.count == 3)
        local fresh = scenario == 'bad_reload' and '100' or binding_bits
        response = prefix..'1|3|Inspected|'..binding_bits..'|'..fresh..'|'
            ..operational_bits..'|'..operational_bits
    elseif action == 'BeginNext' then
        assert(request.previous_run_id == current_run and request.run_id ~= current_run)
        assert(request.issued_count == 3)
        current_run, sealed_run = request.run_id, nil
        capture_number = capture_number + 1
        if capture_number == 2 then binding_bits = '100' end
        response = prefix..'Initialized|3'
    elseif action == 'Capture' then
        assert(request.run_id == current_run and request.first == 1 and request.count == 3)
        local available = select(2, binding_bits:gsub('1', ''))
        response = prefix..'1|3|Captured|'..available..'|'..(3 - available)..'|1|'
            ..binding_bits..'|'..operational_bits
    elseif action == 'Seal' then
        local available = select(2, binding_bits:gsub('1', ''))
        sealed_run = request.run_id
        response = prefix..'Sealed|3|'..available..'|'..(3 - available)..'|1'
        if scenario == 'pause_lost' then paused = false end
    else error('unexpected action '..action) end
    queue_event('X4AuthorityRegistryAvailabilitySnapshot.Result', response)
    return true
end

local engine = {
    ready=function() return true end,
    is_paused=function() return paused end,
    game_time=function() return game_time end,
    real_time=function() return real_time end,
    pause=function() paused = true end,
    resume=function() paused = false end,
    saving_possible=function() return true end,
    save=function(slot, title)
        assert(paused and sealed_run == current_run and stored_marker == current_run)
        saves[#saves + 1] = {run_id=current_run, slot=slot, title=title}
        queue_event('gameSaved', true)
    end,
}
X4LAN_AUTHORITY_X4_CONTROL_ENGINE = {
    new=function() return engine end,
    register_save_event=function(_, state, register)
        register('gameSaved', function(_, success) assert(state:on_game_saved(success)) end)
        return true
    end,
}
dofile('src/authority/lua/control_state.lua')
dofile('src/authority/lua/local_control_bridge.lua')
dofile(ui..'/registry_availability_snapshot.lua')
dofile(ui..'/registry_checkpoint_gate.lua')
dofile(ui..'/config.lua')
dofile(ui..'/authority_world_bridge_probe.lua')

local function step()
    real_time = real_time + .05
    if not paused then game_time = game_time + .05 end
    local delivered = callbacks
    callbacks = {}
    for _, callback in ipairs(delivered) do callback() end
    frame()
end
local function saw(expected)
    for _, packet in ipairs(sent) do if packet == expected then return true end end
    return false
end
local function until_packet(expected)
    for _ = 1, 160 do
        step()
        if saw(expected) then return end
    end
    error('missing packet '..expected..'\n'..table.concat(logs, '\n'))
end
local function command(number, operation, marker)
    incoming[#incoming + 1] = 'CMD|'..lease..'|'..world_epoch..'|'..number..'|'..operation
        ..(marker and '|'..marker or '')
end
local function receipt(number, operation, status)
    return 'RECEIPT|'..lease..'|'..world_epoch..'|'..number..'|'..operation..'|'..status
end
local ready = 'RECOVERY_READY|'..lease..'|'..world_epoch
if scenario == 'bad_reload' then
    for _ = 1, 100 do step() end
    assert(not saw(ready) and #saves == 0 and stored_marker == nil)
    assert(table.concat(logs, '\n'):find('|ERROR|', 1, true))
    return
end
until_packet(ready)
incoming[#incoming + 1] = 'ACTIVATE|'..lease..'|'..world_epoch
until_packet('ACTIVATED|'..lease..'|'..world_epoch)
command(1, 'pause')
until_packet(receipt(1, 'pause', 'confirmed'))
command(2, 'save', string.rep('f', 32))
if scenario == 'pause_lost' then
    for _ = 1, 30 do step() end
    assert(#saves == 0 and stored_marker == nil)
    assert(table.concat(logs, '\n'):find('|ERROR|', 1, true))
    return
end
until_packet(receipt(2, 'save', 'native_event_only'))
assert(#saves == 1 and saves[1].run_id == string.rep('f', 32))
incoming[#incoming + 1] = 'VERIFY|'..lease..'|'..world_epoch..'|2'
until_packet('VERIFIED|'..lease..'|'..world_epoch..'|2')
command(3, 'resume')
until_packet(receipt(3, 'resume', 'confirmed'))
for _ = 1, 5 do step() end
command(4, 'pause')
until_packet(receipt(4, 'pause', 'confirmed'))
command(5, 'save', string.rep('1', 32))
until_packet(receipt(5, 'save', 'native_event_only'))
assert(#saves == 2 and capture_number == 2 and saves[2].run_id == string.rep('1', 32))
incoming[#incoming + 1] = 'VERIFY|'..lease..'|'..world_epoch..'|5'
until_packet('VERIFIED|'..lease..'|'..world_epoch..'|5')
command(6, 'save', string.rep('f', 32))
for _ = 1, 20 do step() end
assert(#saves == 2 and capture_number == 2, 'replayed marker started another capture/save')
assert(table.concat(logs, '\n'):find('|ERROR|', 1, true))
