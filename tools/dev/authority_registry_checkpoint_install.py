"""Opt-in registry capture barrier for an isolated recovered control bridge.

The caller must independently verify the input checkpoint and supply its saved
snapshot observations. This installer neither admits clients nor confirms a
checkpoint. It adds live reload inspection before activation and a fresh full
capture before the bridge stores each new checkpoint marker and saves X4.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
_TOKEN = re.compile(r'[0-9a-f]{32}\Z')
_BITS = re.compile(r'[01]+\Z')


def _replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('recovery bridge hook missing or ambiguous')
    return text.replace(old, new)


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
     ..string.format('%.0f|%.0f|%.0f|%.0f', observation.issued_count,
      observation.available_count, observation.unavailable_count, observation.operational_count))
   end,
   fault=function(reason)
    DebugError('[X4LAN] AUTH_REGISTRY_CHECKPOINT NONCE|ERROR|'..tostring(reason))
   end,
  })
  RegisterEvent('X4AuthorityRegistryAvailabilitySnapshot.Result', function(_, value)
   assert(registry_checkpoint:event(value), 'registry checkpoint event refused')
   DebugError('[X4LAN] AUTH_REGISTRY_CHECKPOINT NONCE|RESPONSE|'..value)
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
