-- Default-off serialized owner for full registry availability snapshots.
-- Callers own event registration and tick scheduling; this module has no hooks.
local Snapshot = {}

local MAX_ISSUED_COUNT = 200000
local MAX_EVENT_LENGTH = 512
local SNAPSHOT_FORMAT = 3

local function token(value)
    return type(value) == 'string' and #value == 32
        and value:match('^[0-9a-f]+$') ~= nil
end

local function integer(value, low, high)
    return type(value) == 'number' and value == value
        and value % 1 == 0 and value >= low and value <= high
end

local function number_text(value)
    return string.format('%.0f', value)
end

local function fields(text)
    local result = {}
    for part in (text .. '|'):gmatch('(.-)|') do result[#result + 1] = part end
    return result
end

local function copy(value)
    if type(value) ~= 'table' then return value end
    local result = {}
    for key, item in pairs(value) do result[key] = copy(item) end
    return result
end

function Snapshot.new(options)
    assert(type(options) == 'table' and options.enabled == true,
        'availability snapshot is default-off')
    assert(options.mode == 'capture' or options.mode == 'inspect',
        'mode must be capture or inspect')
    assert(token(options.epoch) and token(options.run_id) and token(options.nonce),
        'epoch, run_id, and nonce must be 32 lowercase hex characters')
    assert(integer(options.issued_count, 1, MAX_ISSUED_COUNT),
        'issued_count is outside the supported range')
    local batch_size = options.batch_size == nil and 64 or options.batch_size
    assert(integer(batch_size, 1, 64), 'batch_size must be in [1, 64]')
    assert(type(options.timeout) == 'number' and options.timeout > 0
        and options.timeout <= 30, 'timeout must be in (0, 30] seconds')
    for _, name in ipairs({ 'clock', 'guard', 'issue', 'complete', 'fault' }) do
        assert(type(options[name]) == 'function', name .. ' callback is required')
    end

    local config = {
        enabled = options.enabled, mode = options.mode, epoch = options.epoch,
        run_id = options.run_id, nonce = options.nonce,
        issued_count = options.issued_count, batch_size = batch_size,
        timeout = options.timeout, clock = options.clock, guard = options.guard,
        issue = options.issue, complete = options.complete, fault = options.fault,
    }
    local api = {}
    local phase = config.mode == 'capture' and 'initialize' or 'inspect'
    local cursor, request_number = 1, 0
    local started, stopped, busy, issuing = false, false, false, false
    local pending, queued, previous_time = nil, nil, nil
    local binding_bits, operational_bits = {}, {}
    local saved_binding_bits, fresh_binding_bits = {}, {}
    local saved_operational_bits, fresh_operational_bits = {}, {}
    local covered = 0
    local available_total, unavailable_total, operational_total = 0, 0, 0
    local reported_fault = false

    local function fail(reason)
        if stopped then return end
        stopped, pending, queued, phase = true, nil, nil, 'refused'
        if not reported_fault then
            reported_fault = true
            pcall(config.fault, tostring(reason))
        end
    end
    local function enter()
        if busy then fail('reentrant start/tick call'); return false end
        busy = true
        return true
    end
    local function callback(fn, ...)
        local ok, result = pcall(fn, ...)
        if not ok then error('callback failed: ' .. tostring(result)) end
        if stopped then error('owner stopped during callback') end
        return result
    end
    local function now()
        local value = callback(config.clock)
        if type(value) ~= 'number' or value ~= value
            or value == math.huge or value == -math.huge then
            error('clock returned non-finite time')
        end
        if previous_time and value < previous_time then error('clock moved backwards') end
        previous_time = value
        return value
    end
    local function issue(action, first, count)
        request_number = request_number + 1
        local request_id = config.nonce .. '-' .. number_text(request_number)
        local payload = {
            request_id = request_id, run_id = config.run_id,
            epoch = config.epoch,
        }
        if action == 'Initialize' then payload.issued_count = config.issued_count end
        if first then payload.first, payload.count = first, count end
        pending = { request_id = request_id, action = action,
            first = first, count = count, deadline = now() + config.timeout }
        issuing = true
        local ok, accepted = pcall(callback, config.issue, action, copy(payload))
        issuing = false
        if not ok then error(accepted) end
        if accepted == false then
            error('issue callback refused request')
        end
    end
    local function next_request()
        if phase == 'initialize' then issue('Initialize'); return end
        if phase == 'seal' then issue('Seal'); return end
        local count = math.min(config.batch_size, config.issued_count - cursor + 1)
        issue(phase == 'capture' and 'Capture' or 'Inspect', cursor, count)
    end
    local function same_request(row, req)
        return row[1] == req.request_id and row[2] == config.run_id
            and row[3] == req.action
    end
    local function bit_string(value, count)
        return type(value) == 'string' and #value == count
            and value:match('^[01]+$') ~= nil
    end
    local function count_bits(value)
        local ones = select(2, value:gsub('1', ''))
        return ones, #value - ones
    end
    local function consume(response)
        local req, row = pending, fields(response)
        if not req or not same_request(row, req) then
            error('unexpected, duplicate, or late response')
        end
        if row[4] == 'Refused' then
            if #row ~= 4 then error('malformed Refused response') end
            error('request refused')
        end
        if req.action == 'Initialize' then
            if #row ~= 5 or row[4] ~= 'Initialized'
                or row[5] ~= number_text(config.issued_count) then
                error('Initialize response mismatch')
            end
            phase, cursor = 'capture', 1
        elseif req.action == 'Capture' then
            if #row ~= 11 or row[4] ~= number_text(req.first)
                or row[5] ~= number_text(req.count) or row[6] ~= 'Captured'
                or not bit_string(row[10], req.count)
                or not bit_string(row[11], req.count) then
                error('Capture response shape or bits mismatch')
            end
            for offset = 1, req.count do
                if row[11]:sub(offset, offset) == '1'
                    and row[10]:sub(offset, offset) ~= '1' then
                    error('operational bit exceeds binding bit')
                end
            end
            local ones, zeros = count_bits(row[10])
            local operational_ones = count_bits(row[11])
            local next_available, next_unavailable = available_total + ones, unavailable_total + zeros
            local next_operational = operational_total + operational_ones
            if row[7] ~= number_text(next_available) or row[8] ~= number_text(next_unavailable)
                or row[9] ~= number_text(next_operational)
                or req.first ~= covered + 1 then error('Capture totals or prefix mismatch') end
            binding_bits[#binding_bits + 1] = row[10]
            operational_bits[#operational_bits + 1] = row[11]
            covered, available_total, unavailable_total, operational_total = covered + req.count,
                next_available, next_unavailable, next_operational
            cursor = cursor + req.count
            phase = cursor > config.issued_count and 'seal' or 'capture'
        elseif req.action == 'Seal' then
            if #row ~= 8 or row[4] ~= 'Sealed'
                or row[5] ~= number_text(config.issued_count)
                or row[6] ~= number_text(available_total)
                or row[7] ~= number_text(unavailable_total)
                or row[8] ~= number_text(operational_total)
                or covered ~= config.issued_count then error('Seal response mismatch') end
            phase = 'complete'
        elseif req.action == 'Inspect' then
            if #row ~= 10 or row[4] ~= number_text(req.first)
                or row[5] ~= number_text(req.count) or row[6] ~= 'Inspected'
                or not bit_string(row[7], req.count)
                or not bit_string(row[8], req.count)
                or not bit_string(row[9], req.count)
                or not bit_string(row[10], req.count) then
                error('Inspect response shape or bits mismatch')
            end
            for offset = 1, req.count do
                local saved_binding = row[7]:sub(offset, offset)
                local fresh_binding = row[8]:sub(offset, offset)
                local saved_operational = row[9]:sub(offset, offset)
                local fresh_operational = row[10]:sub(offset, offset)
                if saved_operational == '1' and saved_binding ~= '1' then
                    error('saved operational bit exceeds binding bit')
                end
                if fresh_operational == '1' and fresh_binding ~= '1' then
                    error('fresh operational bit exceeds binding bit')
                end
                if saved_binding == '0' and fresh_binding == '1' then
                    error('binding availability cannot revive during inspect')
                end
            end
            saved_binding_bits[#saved_binding_bits + 1], fresh_binding_bits[#fresh_binding_bits + 1] = row[7], row[8]
            saved_operational_bits[#saved_operational_bits + 1], fresh_operational_bits[#fresh_operational_bits + 1] = row[9], row[10]
            local ones, zeros = count_bits(row[8])
            local operational_ones = count_bits(row[10])
            covered, available_total, unavailable_total, operational_total = covered + req.count,
                available_total + ones, unavailable_total + zeros, operational_total + operational_ones
            cursor = cursor + req.count
            phase = cursor > config.issued_count and 'complete' or 'inspect'
        else error('invalid owner phase') end
        pending = nil
    end

    function api:start()
        if not enter() then return false end
        local ok = pcall(function()
            if stopped or started then error('start repeated or terminal') end
            started = true
        end)
        busy = false
        if not ok then fail('invalid start'); return false end
        return true
    end
    -- Event callback only stores one bounded raw response. Synchronous delivery
    -- from issue() is supported; processing remains in tick().
    function api:event(response)
        if stopped then return false end
        if busy and not issuing then
            fail('event callback reentered owner outside issue')
            return false
        end
        if type(response) ~= 'string' or #response == 0 or #response > MAX_EVENT_LENGTH then
            fail('invalid or oversized event'); return false
        end
        if not started or not pending then fail('unsolicited event'); return false end
        if queued ~= nil then fail('duplicate queued event'); return false end
        queued = response
        return true
    end
    function api:tick()
        if not enter() then return false end
        local ok, reason = pcall(function()
            if stopped then return end
            if not started then error('owner has not started') end
            if callback(config.guard) ~= true then error('guard failed') end
            local time = now()
            if pending and time >= pending.deadline then error('request timed out') end
            if queued then
                local response = queued
                queued = nil
                consume(response)
            end
            if stopped then error('owner stopped while consuming response') end
            if not pending and phase ~= 'complete' then next_request() end
            if stopped then error('owner stopped while issuing request') end
            if phase == 'complete' then
                local result = {
                    format = SNAPSHOT_FORMAT, mode = config.mode, epoch = config.epoch, run_id = config.run_id,
                    issued_count = config.issued_count,
                }
                if config.mode == 'capture' then
                    result.availability_bits = table.concat(binding_bits)
                    result.operational_bits = table.concat(operational_bits)
                    result.available_count, result.unavailable_count = available_total, unavailable_total
                    result.operational_count = operational_total
                else
                    result.saved_bits, result.fresh_bits = table.concat(saved_binding_bits), table.concat(fresh_binding_bits)
                    result.saved_operational_bits = table.concat(saved_operational_bits)
                    result.fresh_operational_bits = table.concat(fresh_operational_bits)
                    result.available_count, result.unavailable_count = available_total, unavailable_total
                    result.operational_count = operational_total
                end
                callback(config.complete, copy(result))
                stopped = true
            end
        end)
        busy = false
        if not ok then fail(reason); return false end
        return true
    end
    function api:state()
        return { phase = phase, started = started, stopped = stopped,
            pending_request = copy(pending), queued_event = queued,
            covered = covered, available_count = available_total,
            unavailable_count = unavailable_total, operational_count = operational_total }
    end
    return api
end

X4LAN_AUTHORITY_REGISTRY_AVAILABILITY_SNAPSHOT = Snapshot
return Snapshot
