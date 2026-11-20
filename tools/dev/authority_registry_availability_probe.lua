-- Default-off, read-only owner for serialized registry availability observations.
-- The caller owns MD event registration and tick scheduling. This module has
-- no global hooks and never changes registry or ship state.
local Probe = {}

local MAX_ISSUED_COUNT = 200000
local MAX_INDICES = 16
local MAX_EVENT_LENGTH = 512
local FLAGS = {
    'forward_present',
    'object_exists',
    'is_ship',
    'is_operational',
    'reverse_matches',
}

local function is_hex_token(value)
    return type(value) == 'string'
        and #value == 32
        and value:match('^[0-9a-f]+$') ~= nil
end

local function deep_copy(value)
    if type(value) ~= 'table' then
        return value
    end
    local result = {}
    for key, item in pairs(value) do
        result[key] = deep_copy(item)
    end
    return result
end

local function split_fields(value)
    local fields = {}
    for field in (value .. '|'):gmatch('(.-)|') do
        fields[#fields + 1] = field
    end
    return fields
end

local function format_integer(value)
    return string.format('%.0f', value)
end

function Probe.new(options)
    assert(type(options) == 'table' and options.enabled == true,
        'availability probe is default-off')
    assert(options.mode == 'capture' or options.mode == 'inspect',
        'mode must be capture or inspect')
    assert(is_hex_token(options.epoch), 'epoch must be 32 lowercase hex characters')
    assert(is_hex_token(options.run_id), 'run_id must be 32 lowercase hex characters')
    assert(is_hex_token(options.nonce), 'nonce must be 32 lowercase hex characters')
    assert(type(options.issued_count) == 'number'
        and options.issued_count % 1 == 0
        and options.issued_count >= 1
        and options.issued_count <= MAX_ISSUED_COUNT,
        'issued_count is outside the supported range')
    assert(type(options.indices) == 'table', 'indices must be a table')
    local index_count = 0
    for position in pairs(options.indices) do
        assert(type(position) == 'number' and position % 1 == 0
            and position >= 1 and position <= MAX_INDICES,
            'indices must be a dense sequence')
        index_count = index_count + 1
    end
    assert(index_count >= 1 and index_count <= MAX_INDICES,
        'indices must contain 1 to 16 entries')
    assert(type(options.clock) == 'function'
        and type(options.guard) == 'function'
        and type(options.issue) == 'function'
        and type(options.complete) == 'function'
        and type(options.fault) == 'function',
        'clock, guard, issue, complete, and fault callbacks are required')
    assert(type(options.timeout) == 'number'
        and options.timeout > 0
        and options.timeout <= 30,
        'timeout must be in (0, 30] seconds')

    -- Keep only validated values and copy the caller's mutable index list.
    local config = {
        enabled = options.enabled,
        mode = options.mode,
        epoch = options.epoch,
        run_id = options.run_id,
        nonce = options.nonce,
        issued_count = options.issued_count,
        timeout = options.timeout,
        clock = options.clock,
        guard = options.guard,
        issue = options.issue,
        complete = options.complete,
        fault = options.fault,
        indices = {},
    }
    local seen_indices = {}
    for position = 1, index_count do
        local index = options.indices[position]
        assert(type(index) == 'number'
            and index % 1 == 0
            and index >= 1
            and index <= config.issued_count,
            'each index must be an integer within issued_count')
        assert(not seen_indices[index], 'indices must be unique')
        seen_indices[index] = true
        config.indices[position] = index
    end

    local api = {}
    local phase = config.mode == 'capture' and 'initialize' or 'inspect'
    local cursor = 1
    local pending_request = nil
    local queued_event = nil
    local started = false
    local stopped = false
    local busy = false
    local request_counter = 0
    local previous_time = nil
    local captured_observations = {}
    local inspected_observations = {}
    local failure_reported = false

    local function fail(reason)
        if stopped then
            return
        end
        stopped = true
        pending_request = nil
        queued_event = nil
        phase = 'refused'
        if not failure_reported then
            failure_reported = true
            pcall(config.fault, tostring(reason))
        end
    end

    local function enter_api()
        if busy then
            fail('reentrant owner call')
            return false
        end
        busy = true
        return true
    end

    local function leave_api()
        busy = false
    end

    local function callback_result(callback, ...)
        local succeeded, result = pcall(callback, ...)
        if not succeeded then
            error('callback failed: ' .. tostring(result))
        end
        if stopped then
            error('owner stopped during callback')
        end
        return result
    end

    local function read_time()
        local current_time = callback_result(config.clock)
        if type(current_time) ~= 'number'
            or current_time ~= current_time
            or current_time == math.huge
            or current_time == -math.huge then
            error('clock returned a non-finite time')
        end
        if previous_time ~= nil and current_time < previous_time then
            error('clock moved backwards')
        end
        previous_time = current_time
        return current_time
    end

    local function issue_request(action, index)
        request_counter = request_counter + 1
        local request_id = config.nonce .. '-' .. format_integer(request_counter)
        local payload = {
            request_id = request_id,
            run_id = config.run_id,
            epoch = config.epoch,
            index = index,
        }
        pending_request = {
            request_id = request_id,
            action = action,
            index = index,
            deadline = read_time() + config.timeout,
        }
        local result = callback_result(config.issue, action, deep_copy(payload))
        if result == false then
            error('issue callback refused request')
        end
    end

    local function issue_for_current_phase()
        if phase == 'initialize' then
            issue_request('Initialize')
        elseif phase == 'capture' then
            issue_request('Capture', config.indices[cursor])
        elseif phase == 'seal' then
            issue_request('Seal')
        elseif phase == 'inspect' then
            issue_request('Inspect', config.indices[cursor])
        end
    end

    local function response_matches(fields, request)
        return fields ~= nil
            and fields[1] == request.request_id
            and fields[2] == config.run_id
            and fields[3] == request.action
    end

    local function read_flags(fields, first_position)
        local flags = {}
        for offset, flag_name in ipairs(FLAGS) do
            local value = fields[first_position + offset - 1]
            if value ~= '0' and value ~= '1' then
                error('response contains an invalid flag')
            end
            flags[flag_name] = value == '1'
        end
        return flags
    end

    local function consume_response(response)
        local request = pending_request
        local fields = split_fields(response)
        if not request or not response_matches(fields, request) then
            error('unexpected, duplicate, or late response')
        end
        if fields[4] == 'Refused' then
            if #fields ~= 4 then
                error('malformed Refused response')
            end
            error('request was refused')
        end

        if request.action == 'Initialize' then
            if #fields ~= 5
                or fields[4] ~= 'Initialized'
                or fields[5] ~= format_integer(config.issued_count) then
                error('Initialize response count mismatch')
            end
            phase = 'capture'
            cursor = 1
        elseif request.action == 'Capture' then
            if #fields ~= 10
                or fields[4] ~= format_integer(request.index)
                or fields[5] ~= 'Captured' then
                error('Capture response shape or index mismatch')
            end
            captured_observations[#captured_observations + 1] = {
                index = request.index,
                flags = read_flags(fields, 6),
            }
            cursor = cursor + 1
            phase = cursor > #config.indices and 'seal' or 'capture'
        elseif request.action == 'Seal' then
            if #fields ~= 5
                or fields[4] ~= 'Sealed'
                or fields[5] ~= format_integer(#config.indices)
                or #captured_observations ~= #config.indices then
                error('Seal response count mismatch')
            end
            phase = 'complete'
        elseif request.action == 'Inspect' then
            if #fields ~= 15
                or fields[4] ~= format_integer(request.index)
                or fields[5] ~= 'Inspected' then
                error('Inspect response shape or index mismatch')
            end
            inspected_observations[#inspected_observations + 1] = {
                index = request.index,
                saved = read_flags(fields, 6),
                fresh = read_flags(fields, 11),
            }
            cursor = cursor + 1
            phase = cursor > #config.indices and 'complete' or 'inspect'
        else
            error('invalid owner phase')
        end
        pending_request = nil
    end

    function api:start()
        if not enter_api() then
            return false
        end
        local succeeded = pcall(function()
            if stopped or started then
                error('start was repeated or owner is terminal')
            end
            started = true
        end)
        leave_api()
        if not succeeded then
            fail('invalid start')
            return false
        end
        return true
    end

    -- Event callbacks only enqueue a bounded raw response. Parsing and state
    -- changes happen in tick(), outside the MD callback.
    function api:event(response)
        if stopped then
            return false
        end
        if type(response) ~= 'string' or #response == 0 or #response > MAX_EVENT_LENGTH then
            fail('invalid or oversized event')
            return false
        end
        if not started or not pending_request then
            fail('unsolicited event')
            return false
        end
        if queued_event ~= nil then
            fail('multiple events queued for one request')
            return false
        end
        queued_event = response
        return true
    end

    function api:tick()
        if not enter_api() then
            return false
        end
        local succeeded, reason = pcall(function()
            if stopped then
                return
            end
            if not started then
                error('owner has not started')
            end
            if callback_result(config.guard) ~= true then
                error('guard failed')
            end
            local current_time = read_time()

            if pending_request ~= nil and current_time >= pending_request.deadline then
                error('request timed out')
            end
            if queued_event ~= nil then
                if pending_request == nil then
                    error('queued event has no pending request')
                end
                local response = queued_event
                queued_event = nil
                consume_response(response)
            end
            if stopped then
                error('owner stopped while processing response')
            end
            if pending_request == nil and phase ~= 'complete' then
                issue_for_current_phase()
            end
            if stopped then
                error('owner stopped while issuing request')
            end
            if phase == 'complete' then
                local result = {
                    mode = config.mode,
                    epoch = config.epoch,
                    run_id = config.run_id,
                    observations = deep_copy(config.mode == 'capture'
                        and captured_observations or inspected_observations),
                }
                callback_result(config.complete, deep_copy(result))
                stopped = true
            end
        end)
        leave_api()
        if not succeeded then
            fail(reason)
            return false
        end
        return true
    end

    function api:state()
        return {
            phase = phase,
            pending_request = deep_copy(pending_request),
            queued_event = queued_event,
            captured_observations = deep_copy(captured_observations),
            inspected_observations = deep_copy(inspected_observations),
            started = started,
            stopped = stopped,
        }
    end

    return api
end

X4LAN_AUTHORITY_REGISTRY_AVAILABILITY_PROBE = Probe
return Probe
