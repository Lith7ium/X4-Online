-- Default-off observations of fixture 6 beside the existing sector-position getter.
-- gate.body authenticates the enrolled actor and reads native memory. It does not
-- call gate.actor, parameter builders, shield getters, or any simulation writer.
-- Matching bodies do not prove that the getter's component/scene transform or
-- interpolation cache matches. Literal none/gone is absence, not a valid pose.
local module = {}

function module.create(configuration, gate, emit)
    local enabled = configuration.native_gate_fixture_body_observe
    if enabled == nil or enabled == false then
        return nil
    end
    assert(enabled == true, 'fixture body observer must be boolean')
    assert(gate.platform() == 'linux' and type(gate.body) == 'function',
        'fixture body observer requires Linux body reader')
    assert(configuration.native_gate_hash == 'battle' and
        type(configuration.native_gate_snapshot_sha) == 'string' and
        type(configuration.native_gate_snapshot_fixture) == 'table' and
        #configuration.native_gate_snapshot_fixture == 12,
        'fixture body observer requires enrolled snapshot battle actors')
    assert(not configuration.native_gate_actor_diag and not configuration.native_gate_shield_refresh,
        'fixture body observer must not enable actor or shield-refresh diagnostics')

    local saved_identity = configuration.native_gate_snapshot_fixture[6]
    assert(type(saved_identity) == 'string' and #saved_identity == 16 and
        saved_identity:match('^[0-9a-f]+$') and saved_identity ~= '0000000000000000',
        'fixture body observer requires actor 6 saved identity')
    assert(type(emit) == 'function', 'fixture body observer requires logger')
    local ffi = require('ffi')
    local observe_steps = configuration.native_gate_body_step_diag
    assert(observe_steps == nil or type(observe_steps) == 'boolean',
        'fixture phase observer requires explicit boolean body-step diagnostic')
    if observe_steps then
        assert(type(gate.body_step) == 'function' and type(gate.body_step_status) == 'function',
            'fixture phase observer requires body-step readers')
    end
    local last_phase_tick
    local previous_sequence_after = {}

    -- Counts/sequences remain decimal strings, avoiding uint64 rounding in Lua.
    local function unsigned_decimal(value, maximum)
        return value and value:match('^%d+$') and
            (value == '0' or value:sub(1, 1) ~= '0') and
            (#value < #maximum or (#value == #maximum and value <= maximum))
    end
    local function sequence_less(left, right)
        return #left < #right or (#left == #right and left < right)
    end
    local function hex_words(value, words)
        return value and #value == words * 8 and value:match('^[0-9a-f]+$')
    end
    local function bounded_raw(value, maximum)
        if type(value) ~= 'string' then return 'raw_type=' .. type(value) end
        if #value <= maximum and not value:find('[%z\r\n]') then return 'raw=' .. value end
        local encoded = {}
        for index = 1, math.min(#value, maximum) do
            encoded[#encoded + 1] = string.format('%02x', value:byte(index))
        end
        return 'raw_size=' .. #value .. ' raw_hex=' .. table.concat(encoded)
    end

    local function emit_body_steps(tick, prefix)
        -- The original body reads above have warmed the actor's cached slot.
        -- Reading resets only the gate-private step counter. Always drain both,
        -- even if status or one body is unavailable. Qualification describes only
        -- a complete phase observation, never physics or cross-peer acceptance.
        local raw_steps = {gate.body_step(6, 0), gate.body_step(6, 1)}
        local status = gate.body_step_status()
        local status_tick, failures
        if type(status) == 'string' and #status <= 256 then
            status_tick, failures = status:match('^tick=(%d+) installed=1 restored=0 updates=%d+ captured=%d+ failures=(%d+) state=1 pin=1 stage=armed$')
        end
        emit('FIXTURE_BODY_STEP_STATUS ' .. prefix .. ' ' .. bounded_raw(status, 256))
        for which = 0, 1 do
            local raw = raw_steps[which + 1]
            local steps, dt, collision, sequence_before, sequence_after
            local body_before, motion_before, body_after, motion_after
            if type(raw) == 'string' and #raw <= 2400 then
                steps, dt, collision, sequence_before, sequence_after,
                    body_before, motion_before, body_after, motion_after = raw:match(
                    '^steps=(%d+) dt=([0-9a-f]+) collision=(%d+) seq0=(%d+) seq1=(%d+) body0=([0-9a-f]+) motion0=([0-9a-f]+) body1=([0-9a-f]+) motion1=([0-9a-f]+)$')
            end
            local reason = 'complete'
            if not unsigned_decimal(steps, '4294967295') or not hex_words(dt, 1) or
                not unsigned_decimal(collision, '4294967295') or
                not unsigned_decimal(sequence_before, '18446744073709551615') or
                not unsigned_decimal(sequence_after, '18446744073709551615') or
                not hex_words(body_before, 32) or not hex_words(motion_before, 32) or
                not hex_words(body_after, 32) or not hex_words(motion_after, 32) then
                reason = 'missing_or_malformed'
            elseif status_tick ~= tostring(tick) or failures ~= '0' then
                reason = 'status_unqualified'
            elseif sequence_before == '0' or not sequence_less(sequence_before, sequence_after) then
                reason = 'sequence_unqualified'
            elseif tick == 1400 then
                reason = 'initial_drain'
            elseif last_phase_tick ~= tick - 1 then
                reason = 'sample_gap'
            elseif steps ~= '1' then
                reason = 'step_count_unqualified'
            elseif not previous_sequence_after[which + 1] then
                reason = 'sequence_baseline'
            elseif not sequence_less(previous_sequence_after[which + 1], sequence_before) then
                reason = 'sequence_regression'
            end
            if reason == 'complete' or reason == 'initial_drain' or reason == 'sequence_baseline' then
                previous_sequence_after[which + 1] = sequence_after
            else
                -- An invalid sample breaks continuity; the next valid pair
                -- establishes a new baseline without qualifying that pair.
                previous_sequence_after[which + 1] = nil
            end
            local qualified = reason == 'complete' and '1' or '0'
            local pose = body_before and (' pose0=' .. body_before:sub(1, 64) ..
                ' pose1=' .. body_after:sub(1, 64)) or ''
            emit('FIXTURE_BODY_STEP_OBSERVE ' .. prefix .. ' which=' .. which ..
                ' qualified=' .. qualified .. ' reason=' .. reason ..
                ' failures=' .. (failures or 'unavailable') .. pose .. ' ' .. bounded_raw(raw, 2400))
        end
        last_phase_tick = tick
    end

    local function read_body(which)
        local raw_body = gate.body(6, which)
        assert(type(raw_body) == 'string' and #raw_body > 0 and #raw_body <= 1024 and
            not raw_body:find('[\r\n]'), 'fixture body observer unavailable or malformed body')
        return raw_body
    end

    local observer = {}

    function observer.wanted(tick, actor)
        return actor == 6 and tick >= 1400 and tick <= 1600
    end

    function observer.sample(tick, actor, get_position)
        assert(observer.wanted(tick, actor), 'fixture body observer outside bounded window')
        -- Keep the original getter single-call, with memory-only snapshots on both
        -- sides. Logs follow all reads, so logging cannot separate the getter/reads.
        local before = {read_body(0), read_body(1)}
        local position = get_position()
        local after = {read_body(0), read_body(1)}

        local position_copy = ffi.new('UIPosRot[1]')
        position_copy[0] = position
        -- Read each byte directly: the game's FFI/string path truncated binary
        -- buffers at embedded NUL despite the supplied length. Emit only hex.
        local position_bytes = ffi.cast('const unsigned char *', position_copy)
        local encoded_bytes = {}
        for index = 0, ffi.sizeof('UIPosRot') - 1 do
            encoded_bytes[#encoded_bytes + 1] = string.format('%02x', position_bytes[index])
        end
        local raw_position = table.concat(encoded_bytes)
        local prefix = 'tick=' .. tick .. ' actor=6 saved=' .. saved_identity
        for which = 0, 1 do
            emit('FIXTURE_BODY_OBSERVE ' .. prefix .. ' phase=before which=' .. which ..
                ' raw=' .. before[which + 1])
        end
        emit('FIXTURE_EULER_OBSERVE ' .. prefix .. ' raw=' .. raw_position)
        for which = 0, 1 do
            emit('FIXTURE_BODY_OBSERVE ' .. prefix .. ' phase=after which=' .. which ..
                ' raw=' .. after[which + 1])
        end
        if observe_steps then emit_body_steps(tick, prefix) end
        return position
    end

    return observer
end

X4LAN_FIXTURE_BODY_OBSERVER = module
return module
