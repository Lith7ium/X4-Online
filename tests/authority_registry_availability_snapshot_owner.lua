local Snapshot = assert(loadfile('tools/dev/authority_registry_availability_snapshot.lua'))()

local function fixture(mode, count, batch, issue_override, previous_run_id)
    local time, requests, result, fault = 0, {}, nil, nil
    local options = {
        enabled = true, mode = mode, epoch = string.rep('a', 32),
        run_id = string.rep('b', 32), nonce = string.rep('c', 32),
        previous_run_id = previous_run_id,
        issued_count = count, batch_size = batch, timeout = 2,
        clock = function() return time end,
        guard = function() return true end,
        issue = function(action, payload)
            requests[#requests + 1] = { action = action, payload = payload }
            if issue_override then return issue_override(action, payload) end
            return true
        end,
        complete = function(value) result = value end,
        fault = function(reason) fault = reason end,
    }
    local owner = Snapshot.new(options)
    assert(owner:start())
    return owner, requests, function(value) time = value end,
        function() return result end, function() return fault end, options
end

local function response(request, body)
    return table.concat({ request.payload.request_id, request.payload.run_id,
        request.action, body }, '|')
end
local function deliver(owner, request, body)
    assert(owner:event(response(request, body)))
    assert(owner:tick())
end

local function test_full_capture_and_chunked_remainder()
    local owner, requests, _, completed, fault = fixture('capture', 10082, 64)
    assert(owner:tick())
    assert(requests[1].action == 'Initialize')
    assert(requests[1].payload.issued_count == 10082)
    deliver(owner, requests[1], 'Initialized|10082')
    local total_available, total_unavailable, total_operational, cursor = 0, 0, 0, 1
    while cursor <= 10082 do
        local req = requests[#requests]
        assert(req.action == 'Capture' and req.payload.first == cursor)
        local count = math.min(64, 10082 - cursor + 1)
        assert(req.payload.count == count)
        local binding, operational = {}, {}
        for index = cursor, cursor + count - 1 do
            binding[#binding + 1] = index <= 10075 and '1' or '0'
            operational[#operational + 1] = index <= 10019 and '1' or '0'
        end
        local binding_chunk, operational_chunk = table.concat(binding), table.concat(operational)
        local available = select(2, binding_chunk:gsub('1', ''))
        local unavailable = #binding_chunk - available
        local operating = select(2, operational_chunk:gsub('1', ''))
        total_available, total_unavailable, total_operational = total_available + available,
            total_unavailable + unavailable, total_operational + operating
        deliver(owner, req, table.concat({ cursor, count, 'Captured',
            total_available, total_unavailable, total_operational,
            binding_chunk, operational_chunk }, '|'))
        cursor = cursor + count
    end
    local seal = requests[#requests]
    assert(seal.action == 'Seal')
    deliver(owner, seal, table.concat({ 'Sealed', 10082, 10075, 7, 10019 }, '|'))
    assert(completed() and fault() == nil)
    assert(completed().format == 3 and #completed().availability_bits == 10082)
    assert(completed().available_count == 10075 and completed().unavailable_count == 7)
    assert(completed().availability_bits == string.rep('1', 10075) .. string.rep('0', 7))
    assert(completed().operational_count == 10019)
    assert(completed().operational_bits == string.rep('1', 10019) .. string.rep('0', 63))
    assert(requests[#requests - 1].payload.first == 10049)
end

local function test_inspect_divergence_is_observation()
    local owner, requests, _, completed, fault = fixture('inspect', 70, 64)
    assert(owner:tick())
    assert(requests[1].action == 'Inspect' and requests[1].payload.first == 1
        and requests[1].payload.count == 64 and requests[1].payload.epoch == string.rep('a', 32))
    local saved, fresh = string.rep('1', 64), '0' .. string.rep('1', 63)
    local saved_operational, fresh_operational = string.rep('0', 64), '0' .. string.rep('1', 63)
    deliver(owner, requests[1], table.concat({ 1, 64, 'Inspected', saved, fresh,
        saved_operational, fresh_operational }, '|'))
    assert(owner:state().covered == 64)
    assert(owner:state().available_count == 63 and owner:state().unavailable_count == 1)
    assert(owner:state().operational_count == 63)
    local tail = requests[2]
    assert(tail.action == 'Inspect' and tail.payload.first == 65 and tail.payload.count == 6)
    deliver(owner, tail, '65|6|Inspected|000000|000000|000000|000000')
    assert(completed() and fault() == nil)
    assert(completed().saved_bits == saved .. '000000')
    assert(completed().fresh_bits == fresh .. '000000')
    assert(completed().available_count == 63 and completed().unavailable_count == 7)
    assert(completed().format == 3)
    assert(completed().saved_operational_bits == saved_operational .. '000000')
    assert(completed().fresh_operational_bits == fresh_operational .. '000000')
    assert(completed().operational_count == 63)
end

local function test_begin_next_correlates_completed_predecessor()
    local previous = string.rep('d', 32)
    local owner, requests, _, completed, fault = fixture('capture', 1, 1, nil, previous)
    assert(owner:tick())
    local begin = requests[1]
    assert(begin.action == 'BeginNext')
    assert(begin.payload.previous_run_id == previous and begin.payload.run_id ~= previous)
    assert(begin.payload.issued_count == 1)
    deliver(owner, begin, 'Initialized|1')
    local capture = requests[2]
    assert(capture.action == 'Capture' and capture.payload.first == 1)
    deliver(owner, capture, '1|1|Captured|1|0|0|1|0')
    local seal = requests[3]
    assert(seal.action == 'Seal')
    deliver(owner, seal, 'Sealed|1|1|0|0')
    assert(completed() and completed().run_id ~= previous and fault() == nil)

    local ok = pcall(function()
        fixture('inspect', 1, 1, nil, previous)
    end)
    assert(not ok, 'inspect must not accept a predecessor')
    ok = pcall(function()
        Snapshot.new({ enabled = true, mode = 'capture', epoch = previous,
            run_id = string.rep('b', 32), previous_run_id = previous,
            nonce = string.rep('c', 32), issued_count = 1, timeout = 1,
            clock = function() return 0 end, guard = function() return true end,
            issue = function() return true end, complete = function() end,
            fault = function() end })
    end)
    assert(not ok, 'previous run must differ from epoch')
end

local function test_sync_event_and_protocol_failures()
    local owner, synchronous_result, synchronous_fault
    owner = Snapshot.new({ enabled = true, mode = 'inspect', epoch = string.rep('a', 32),
        run_id = string.rep('b', 32), nonce = string.rep('c', 32), issued_count = 1,
        timeout = 2, clock = function() return 0 end, guard = function() return true end,
        issue = function(action, payload)
            assert(owner:event(table.concat({ payload.request_id, payload.run_id,
                action, '1|1|Inspected|1|1|0|1' }, '|')))
            return true
        end,
        complete = function(value) synchronous_result = value end,
        fault = function(reason) synchronous_fault = reason end })
    assert(owner:start())
    assert(owner:tick() and owner:tick() and synchronous_result and synchronous_fault == nil)

    local function malformed(body)
        local bad_owner, bad_requests, _, _, bad_fault = fixture('capture', 2, 2)
        assert(bad_owner:tick())
        deliver(bad_owner, bad_requests[1], 'Initialized|2')
        local req = bad_requests[2]
        assert(bad_owner:event(response(req, body)))
        local ok = bad_owner:tick()
        assert(not ok and bad_fault() ~= nil)
    end
    malformed('2|2|Captured|1|1|1|10|10') -- Capture must cover the contiguous prefix.
    malformed('1|2|Captured|1|1|1|1x|10')
    malformed('1|2|Captured|1|1|1|11|11') -- totals must reconcile
    malformed('1|2|Captured|1|1|1|10|01') -- operational cannot exceed binding.

    local inspect_bad, inspect_requests, _, _, inspect_fault = fixture('inspect', 1, 1)
    assert(inspect_bad:tick())
    assert(inspect_bad:event(response(inspect_requests[1], '1|1|Inspected|0|1|0|1')))
    assert(not inspect_bad:tick() and inspect_fault() ~= nil) -- Binding cannot revive.

    local inspect_good, good_requests, _, good_complete, good_fault = fixture('inspect', 1, 1)
    assert(inspect_good:tick())
    assert(inspect_good:event(response(good_requests[1], '1|1|Inspected|1|1|0|1')))
    assert(inspect_good:tick() and good_complete() and good_fault() == nil)
    assert(good_complete().fresh_operational_bits == '1') -- Operational may change while bound.
end

local function test_duplicate_late_and_deadline()
    local owner, requests, set_time, _, fault = fixture('inspect', 1, 1)
    assert(owner:tick())
    local answer = response(requests[1], '1|1|Inspected|1|1|0|0')
    assert(owner:event(answer) and not owner:event(answer) and fault() ~= nil)

    owner, requests, set_time = fixture('inspect', 1, 1)
    assert(owner:tick())
    local req = requests[1]
    assert(owner:event(response(req, '1|1|Inspected|1|1|0|0')))
    set_time(2)
    assert(not owner:tick())
    assert(owner:state().phase == 'refused')

    owner, requests = fixture('inspect', 1, 1)
    assert(owner:tick())
    req = requests[1]
    local stale = response(req, '1|1|Inspected|1|1|0|0')
    assert(owner:event(stale) and owner:tick())
    assert(not owner:event(stale))
end

local function test_reentry_rollback_config_copy_and_disabled()
    local owner
    local fault_reason
    local requests
    local base_owner, captured_requests, _, _, fault = fixture('inspect', 1, 1, function()
        owner:tick()
        return true
    end)
    owner, requests = base_owner, captured_requests
    assert(not owner:tick() and fault() ~= nil)
    assert(requests[1].action == 'Inspect')

    local time = 5
    local options = { enabled = true, mode = 'inspect', epoch = string.rep('a', 32),
        run_id = string.rep('b', 32), nonce = string.rep('c', 32), issued_count = 1,
        timeout = 2, clock = function() return time end, guard = function() return true end,
        issue = function() return true end, complete = function() end,
        fault = function(reason) fault_reason = reason end }
    owner = Snapshot.new(options)
    options.issued_count = 99
    assert(owner:start() and owner:tick())
    assert(owner:state().pending_request.count == 1)
    time = 4
    assert(not owner:tick() and fault_reason ~= nil)
    assert(not pcall(function() Snapshot.new({ enabled = false }) end))
end

local function test_non_issue_callbacks_cannot_enqueue_events()
    for _, callback_name in ipairs({ 'guard', 'clock' }) do
        local owner, should_inject, fault_reason, response_text = nil, false, nil, nil
        local function inject()
            if should_inject then
                assert(not owner:event(response_text))
            end
            return callback_name == 'clock' and 0 or true
        end
        owner = Snapshot.new({ enabled = true, mode = 'inspect', epoch = string.rep('a', 32),
            run_id = string.rep('b', 32), nonce = string.rep('c', 32), issued_count = 1,
            timeout = 2,
            clock = function() return callback_name == 'clock' and inject() or 0 end,
            guard = function() return callback_name == 'guard' and inject() or true end,
            issue = function(action, payload)
                response_text = table.concat({ payload.request_id, payload.run_id,
                    action, '1|1|Inspected|1|1|0|0' }, '|')
                return true
            end,
            complete = function() end,
            fault = function(reason) fault_reason = reason end })
        assert(owner:start() and owner:tick())
        should_inject = true
        assert(not owner:tick() and fault_reason ~= nil)
    end
end

test_full_capture_and_chunked_remainder()
test_inspect_divergence_is_observation()
test_begin_next_correlates_completed_predecessor()
test_sync_event_and_protocol_failures()
test_duplicate_late_and_deadline()
test_reentry_rollback_config_copy_and_disabled()
test_non_issue_callbacks_cannot_enqueue_events()
print('authority registry availability snapshot owner: ok')
