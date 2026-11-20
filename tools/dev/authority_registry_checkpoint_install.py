"""Opt-in registry capture barrier for an isolated recovered control bridge.

The caller must independently verify the input checkpoint and supply its saved
snapshot observations. This installer neither admits clients nor confirms a
checkpoint. It adds live reload inspection before activation and a fresh full
capture before the bridge stores each new checkpoint marker and saves X4.
"""
from pathlib import Path
import os
import re
import stat

ROOT = Path(__file__).resolve().parents[2]
_TOKEN = re.compile(r'[0-9a-f]{32}\Z')
_BITS = re.compile(r'[01]+\Z')
_MAX_LOG = 16 * 1024 * 1024


def _replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('recovery bridge hook missing or ambiguous')
    return text.replace(old, new)


def verify_bridge_observation(log_path, nonce, evidence, *, previous_run_id=None):
    """Match one saved format-3 snapshot to its complete live bridge exchange.

    ``evidence`` must come from ``verify_join_snapshot``. A successful return
    correlates the bridge log to those saved bytes; it does not establish a
    loaded checkpoint or authorize admission on its own.
    """
    if (not isinstance(nonce, str) or not _TOKEN.fullmatch(nonce)
            or previous_run_id is not None and
            (not isinstance(previous_run_id, str) or not _TOKEN.fullmatch(previous_run_id))
            or not isinstance(evidence, dict) or evidence.get('format') != 3
            or evidence.get('source_registry_checked') is not True):
        raise ValueError('invalid verified bridge evidence')
    run_id = evidence.get('run_id')
    count = evidence.get('issued_count')
    binding = evidence.get('availability_bits')
    operational = evidence.get('operational_bits')
    if (not isinstance(run_id, str) or not _TOKEN.fullmatch(run_id)
            or run_id in (nonce, previous_run_id) or
            type(count) is not int or not 1 <= count <= 200000
            or any(not isinstance(bits, str) or len(bits) != count or not _BITS.fullmatch(bits)
                   for bits in (binding, operational))
            or any(o == '1' and b != '1' for b, o in zip(binding, operational))):
        raise ValueError('invalid saved snapshot vector')
    available = binding.count('1')
    unavailable = count - available
    operational_count = operational.count('1')
    if any(type(evidence.get(key)) is not int or evidence[key] != value for key, value in
           (('available_count', available), ('unavailable_count', unavailable),
            ('operational_count', operational_count))):
        raise ValueError('saved snapshot totals disagree with vectors')

    fd = os.open(log_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_LOG:
            raise ValueError('bridge log is not a bounded regular file')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(_MAX_LOG + 1)
        if len(raw) > _MAX_LOG or len(raw) != info.st_size:
            raise ValueError('bridge log changed or exceeded bound')
        text = raw.decode('utf-8', errors='replace')
    finally:
        os.close(fd)

    prefix = f'[X4LAN] AUTH_REGISTRY_CHECKPOINT {nonce}|'
    tagged = [line.split(prefix, 1)[1].strip() for line in text.splitlines() if prefix in line]
    if any(row.startswith('ERROR|') for row in tagged):
        raise ValueError('bridge reported an error for this nonce')
    target = []
    positions = []
    for position, row in enumerate(tagged):
        fields = row.split('|')
        if (len(fields) >= 3 and fields[0] == 'RESPONSE' and fields[2] == run_id
                or len(fields) >= 3 and fields[0] == 'COMPLETE' and fields[2] == run_id):
            target.append(fields)
            positions.append(position)
    batches = (count + 63) // 64
    capture = previous_run_id is not None
    expected_rows = batches + (3 if capture else 1)
    if (len(target) != expected_rows or not positions
            or positions != list(range(positions[0], positions[0] + len(positions)))):
        raise ValueError('bridge exchange missing, duplicated or interleaved')
    response = target[:-1]
    if capture:
        if response[0] != ['RESPONSE', f'{nonce}-1', run_id, 'BeginNext', 'Initialized', str(count)]:
            raise ValueError('BeginNext receipt mismatch')
        response = response[1:]
    seen_available = seen_unavailable = seen_operational = 0
    for batch, first in enumerate(range(1, count + 1, 64), 1):
        n = min(64, count - first + 1)
        bits = binding[first - 1:first - 1 + n]
        ops = operational[first - 1:first - 1 + n]
        request = f'{nonce}-{batch + int(capture)}'
        if capture:
            seen_available += bits.count('1')
            seen_unavailable += bits.count('0')
            seen_operational += ops.count('1')
            expected = ['RESPONSE', request, run_id, 'Capture', str(first), str(n),
                        'Captured', str(seen_available), str(seen_unavailable),
                        str(seen_operational), bits, ops]
        else:
            expected = ['RESPONSE', request, run_id, 'Inspect', str(first), str(n),
                        'Inspected', bits, bits, ops, ops]
        if response[batch - 1] != expected:
            raise ValueError('bridge batch differs from saved snapshot')
    if capture:
        seal = ['RESPONSE', f'{nonce}-{batches + 2}', run_id, 'Seal', 'Sealed',
                str(count), str(available), str(unavailable), str(operational_count)]
        if target[-2] != seal:
            raise ValueError('bridge seal receipt mismatch')
    completion = ['COMPLETE', 'capture' if capture else 'inspect', run_id]
    if capture:
        completion.append(previous_run_id)
    completion.extend(map(str, (count, available, unavailable, operational_count)))
    if target[-1] != completion:
        raise ValueError('bridge completion mismatch')
    return True


def install(case, nonce, evidence):
    """Install into a fresh disposable case using verified format-3 evidence."""
    if (not isinstance(nonce, str) or not _TOKEN.fullmatch(nonce)
            or not isinstance(evidence, dict) or evidence.get('format') != 3):
        raise ValueError('invalid registry checkpoint configuration')
    epoch, run_id = evidence.get('epoch'), evidence.get('run_id')
    count = evidence.get('issued_count')
    binding_bits = evidence.get('availability_bits')
    operational_bits = evidence.get('operational_bits')
    if (any(not isinstance(value, str) or not _TOKEN.fullmatch(value)
            for value in (epoch, run_id))
            or len({epoch, run_id, nonce}) != 3
            or type(count) is not int or not 1 <= count <= 200000
            or any(not isinstance(bits, str) or len(bits) != count
                   or not _BITS.fullmatch(bits) for bits in (binding_bits, operational_bits))
            or any(operational == '1' and binding != '1'
                   for binding, operational in zip(binding_bits, operational_bits))):
        raise ValueError('invalid saved snapshot observations')

    lab = Path(case) / 'extensions/x4_lan_lab'
    ui = lab / 'ui'
    probe_path = ui / 'authority_world_bridge_probe.lua'
    manifest_path = lab / 'ui.xml'
    probe = probe_path.read_text(encoding='ascii')
    manifest = manifest_path.read_text(encoding='ascii')
    if 'registry_status' in probe or 'registry_checkpoint' in probe:
        raise ValueError('registry checkpoint owner conflicts with an installed owner')

    modules = {
        ui / 'registry_availability_snapshot.lua': ROOT / 'tools/dev/authority_registry_availability_snapshot.lua',
        ui / 'registry_checkpoint_gate.lua': ROOT / 'src/authority/lua/registry_checkpoint_gate.lua',
        lab / 'md/authority_registry_availability_snapshot.xml': ROOT / 'tools/dev/authority_registry_availability_snapshot.xml',
    }
    if any(path.exists() for path in modules):
        raise ValueError('registry checkpoint module already exists')

    probe = _replace_once(probe, 'local activated=false\n', '''local activated=false
local registry_checkpoint, registry_checkpoint_pause_time
''')
    before_activation = ''' if not registry_checkpoint then
  registry_checkpoint_pause_time = engine.game_time()
  registry_checkpoint = X4LAN_AUTHORITY_REGISTRY_CHECKPOINT_GATE.new({
   enabled=true, epoch="EPOCH", issued_count=COUNT, nonce="NONCE",
   initial_run_id="RUN_ID", expected_binding_bits="BINDING_BITS",
   expected_operational_bits="OPERATIONAL_BITS", clock=GetCurRealTime,
   timeout=110,
   guard=function()
    return C.IsPlayerValid() and C.IsGamePaused()
     and engine.game_time() == registry_checkpoint_pause_time
   end,
   issue=function(action, payload)
    return AddUITriggeredEvent('X4AuthorityRegistryAvailabilitySnapshot', action, payload) ~= false
   end,
   store_marker=function(marker)
    return AddUITriggeredEvent('X4AuthorityCheckpointMarker', 'Store', {marker=marker}) ~= false
   end,
   report=function(observation)
    DebugError('[X4LAN] AUTH_REGISTRY_CHECKPOINT NONCE|COMPLETE|'
     ..observation.mode..'|'..observation.run_id..'|'
     ..(observation.previous_run_id and (observation.previous_run_id..'|') or '')
     ..string.format('%.0f|%.0f|%.0f|%.0f', observation.issued_count,
      observation.available_count, observation.unavailable_count, observation.operational_count))
   end,
   fault=function(reason)
    DebugError('[X4LAN] AUTH_REGISTRY_CHECKPOINT NONCE|ERROR|'..tostring(reason))
   end,
  })
  RegisterEvent('X4AuthorityRegistryAvailabilitySnapshot.Result', function(_, value)
   DebugError('[X4LAN] AUTH_REGISTRY_CHECKPOINT NONCE|RESPONSE|'..value)
   assert(registry_checkpoint:event(value), 'registry checkpoint event refused')
  end)
  assert(registry_checkpoint:start(), 'registry reload inspection refused')
 end
 assert(registry_checkpoint:tick(), 'registry checkpoint update failed')
 if not activated and not registry_checkpoint:ready() then return end
'''
    replacements = {'EPOCH': epoch, 'COUNT': str(count), 'NONCE': nonce,
                    'RUN_ID': run_id, 'BINDING_BITS': binding_bits,
                    'OPERATIONAL_BITS': operational_bits}
    for placeholder, value in replacements.items():
        before_activation = before_activation.replace(placeholder, value)
    probe = _replace_once(probe, ' if not activated then\n',
                          before_activation + ' if not activated then\n')
    probe = _replace_once(probe,
                          "    AddUITriggeredEvent('X4AuthorityCheckpointMarker','Store',{marker=marker})\n",
                          '''    registry_checkpoint_pause_time = engine.game_time()
    assert(registry_checkpoint:prepare(marker), 'registry checkpoint capture refused')
''')
    manifest_hook = '    <file name="ui/authority_world_bridge_probe.lua" />\n'
    manifest = _replace_once(manifest, manifest_hook,
                             '    <file name="ui/registry_availability_snapshot.lua" />\n'
                             '    <file name="ui/registry_checkpoint_gate.lua" />\n' + manifest_hook)

    # Validate hooks and read dependencies before modifying the disposable case.
    contents = {target: source.read_bytes() for target, source in modules.items()}
    for target, data in contents.items():
        target.write_bytes(data)
    probe_path.write_text(probe, encoding='ascii')
    manifest_path.write_text(manifest, encoding='ascii')
    return [*modules, probe_path, manifest_path]
