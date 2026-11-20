local Probe = assert(loadfile('tools/dev/authority_registry_availability_probe.lua'))()

local function make_fixture(mode, issued_count, indices)
    local current_time = 0
    local requests = {}
    local completed_result = nil
    local fault_reason = nil
    local options = {
        enabled = true,
        mode = mode,
        epoch = string.rep('a', 32),
        run_id = string.rep('b', 32),
        nonce = string.rep('c', 32),
        issued_count = issued_count,
        indices = indices,
        timeout = 2,
        clock = function()
            return current_time
        end,
        guard = function()
            return true
        end,
        issue = function(action, payload)
            requests[#requests + 1] = { action = action, payload = payload }
            return true
        end,
        complete = function(result)
            completed_result = result
        end,
        fault = function(reason)
            fault_reason = reason
        end,
    }
    local owner = Probe.new(options)
    assert(owner:start())
    return owner, requests,
        function(value) current_time = value end,
        function() return completed_result end,
        function() return fault_reason end,
        options
end

local function response_for(request, body)
    local payload = request.payload
    return table.concat({ payload.request_id, payload.run_id, request.action, body }, '|')
end

local function deliver(owner, request, body)
    assert(owner:event(response_for(request, body)))
    assert(owner:tick())
end

local function test_capture_serializes_and_copies_results()
    -- issued_count is the full registry bound, while indices are a small sample.
    local owner, requests, _, completed, fault = make_fixture(
        'capture', 10082, { 2, 10082 })
    assert(owner:tick())
    assert(requests[1].action == 'Initialize')
    deliver(owner, requests[1], 'Initialized|10082')
    assert(requests[2].action == 'Capture' and requests[2].payload.index == 2)
    deliver(owner, requests[2], '2|Captured|1|0|1|1|0')
    assert(requests[3].action == 'Capture' and requests[3].payload.index == 10082)
    deliver(owner, requests[3], '10082|Captured|0|1|0|0|1')
    assert(requests[4].action == 'Seal')
    deliver(owner, requests[4], 'Sealed|2')

    assert(completed() ~= nil and fault() == nil)
    assert(#completed().observations == 2)
    assert(completed().observations[1].flags.forward_present == true)
    local state = owner:state()
    state.captured_observations[1].flags.forward_present = false
    assert(owner:state().captured_observations[1].flags.forward_present == true)
end

local function test_inspect_keeps_saved_and_fresh_separate()
    local owner, requests, _, completed, fault = make_fixture('inspect', 10082, { 8 })
    assert(owner:tick())
    assert(requests[1].action == 'Inspect' and requests[1].payload.index == 8)
    deliver(owner, requests[1], '8|Inspected|1|1|0|1|0|0|1|1|0|1')

    assert(completed() ~= nil and fault() == nil)
    local observation = completed().observations[1]
    assert(observation.saved.forward_present == true)
    assert(observation.saved.is_ship == false)
    assert(observation.fresh.forward_present == false)
    assert(observation.fresh.is_ship == true)
end

local function test_duplicate_and_late_events_fail()
    local owner, requests, _, _, fault = make_fixture('inspect', 10, { 4 })
    assert(owner:tick())
    local response = response_for(requests[1], '4|Inspected|1|1|1|1|1|1|1|1|1|1')
    assert(owner:event(response))
    assert(not owner:event(response))
    assert(fault() ~= nil)

    owner, requests = make_fixture('inspect', 10, { 4 })
    assert(owner:tick())
    local request = requests[1]
    deliver(owner, request, '4|Inspected|1|1|1|1|1|1|1|1|1|1')
    assert(not owner:event(response_for(request, '4|Inspected|1|1|1|1|1|1|1|1|1|1')))
end

local function test_timeout_and_queued_response_deadline()
    local owner, requests, set_time, _, fault = make_fixture('inspect', 10, { 4 })
    assert(owner:tick())
    set_time(3)
    assert(not owner:tick())
    assert(fault() ~= nil)

    owner, requests, set_time, _, fault = make_fixture('inspect', 10, { 4 })
    assert(owner:tick())
    assert(owner:event(response_for(requests[1], '4|Inspected|1|1|1|1|1|1|1|1|1|1')))
    set_time(3)
    assert(not owner:tick())
    assert(fault() ~= nil)
end

local function test_malformed_responses_and_changed_options_fail()
    local owner, requests, _, _, fault = make_fixture('capture', 10, { 1 })
    assert(owner:tick())
    assert(owner:event(response_for(requests[1], 'Initialized|9')))
    assert(not owner:tick())
    assert(fault() ~= nil)

    owner, requests, _, _, fault = make_fixture('inspect', 10, { 1 })
    assert(owner:tick())
    assert(owner:event(response_for(requests[1], '1|Inspected|2|1|1|1|1|1|1|1|1|1')))
    assert(not owner:tick())
    assert(fault() ~= nil)

    local options = {
        enabled = true,
        mode = 'inspect',
        epoch = string.rep('a', 32),
        run_id = string.rep('b', 32),
        nonce = string.rep('c', 32),
        issued_count = 10,
        indices = { 1, 2 },
        timeout = 1,
        clock = function() return 0 end,
        guard = function() return true end,
        issue = function() return true end,
        complete = function() end,
        fault = function() end,
    }
    owner = Probe.new(options)
    options.issued_count = 1
    options.indices[1] = 10
    assert(owner:start())
    assert(owner:tick())
    assert(owner:state().pending_request.index == 1)
end

local function test_index_validation_and_guard_clock_reentry()
    local base_options = {
        enabled = true,
        mode = 'inspect',
        epoch = string.rep('a', 32),
        run_id = string.rep('b', 32),
        nonce = string.rep('c', 32),
        issued_count = 10,
        timeout = 1,
        clock = function() return 0 end,
        guard = function() return true end,
        issue = function() return true end,
        complete = function() end,
        fault = function() end,
    }
    local invalid_sets = {
        {}, { 1, 1 }, { 11 }, { [1]=1, [3]=3 }, { [2]=2 }, { 1, unexpected=2 },
        { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17 },
    }
    for _, indices in ipairs(invalid_sets) do
        base_options.indices = indices
        assert(not pcall(function() Probe.new(base_options) end))
    end

    local owner
    local observed_fault = nil
    base_options.indices = { 1 }
    base_options.guard = function()
        owner:tick()
        return true
    end
    base_options.fault = function(reason)
        observed_fault = reason
    end
    owner = Probe.new(base_options)
    assert(owner:start())
    assert(not owner:tick())
    assert(observed_fault ~= nil and owner:state().phase == 'refused')

    observed_fault = nil
    owner = nil
    base_options.guard = function() return true end
    base_options.clock = function()
        owner:tick()
        return 0
    end
    owner = Probe.new(base_options)
    assert(owner:start())
    assert(not owner:tick())
    assert(observed_fault ~= nil and owner:state().phase == 'refused')
end

local function test_event_input_is_bounded()
    local owner = Probe.new({
        enabled = true,
        mode = 'inspect',
        epoch = string.rep('a', 32),
        run_id = string.rep('b', 32),
        nonce = string.rep('c', 32),
        issued_count = 1,
        indices = { 1 },
        timeout = 1,
        clock = function() return 0 end,
        guard = function() return true end,
        issue = function() return true end,
        complete = function() end,
        fault = function() end,
    })
    assert(owner:start())
    assert(not owner:event(string.rep('x', 513)))
    assert(owner:state().phase == 'refused')
end

local function test_complete_reentry_cannot_finish_successfully()
    local owner
    local fault_reason = nil
    local completed = false
    local options = {
        enabled = true,
        mode = 'inspect',
        epoch = string.rep('a', 32),
        run_id = string.rep('b', 32),
        nonce = string.rep('c', 32),
        issued_count = 1,
        indices = { 1 },
        timeout = 1,
        clock = function() return 0 end,
        guard = function() return true end,
        issue = function() return true end,
        complete = function()
            completed = true
            owner:tick()
        end,
        fault = function(reason)
            fault_reason = reason
        end,
    }
    owner = Probe.new(options)
    assert(owner:start())
    assert(owner:tick())
    local request = owner:state().pending_request
    assert(owner:event(table.concat({ request.request_id, options.run_id, 'Inspect',
        '1|Inspected|1|1|1|1|1|1|1|1|1|1' }, '|')))
    assert(not owner:tick())
    assert(completed and fault_reason ~= nil)
    assert(owner:state().phase == 'refused' and owner:state().stopped)
end

test_capture_serializes_and_copies_results()
test_inspect_keeps_saved_and_fresh_separate()
test_duplicate_and_late_events_fail()
test_timeout_and_queued_response_deadline()
test_malformed_responses_and_changed_options_fail()
test_index_validation_and_guard_clock_reentry()
test_event_input_is_bounded()
test_complete_reentry_cannot_finish_successfully()
print('authority registry availability owner test passed')
