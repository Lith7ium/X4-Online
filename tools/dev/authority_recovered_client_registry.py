"""Optional join-checkpoint registry observation for the isolated X4 client.

This is a cooperative local status check, not a proof of loaded bytes or actor
identity. The surrounding owner must guard process, files, ticket and marker.
"""
import re
import shutil
from pathlib import Path

import authority_recovery_tcp_join_live as recovery

ROOT = Path(__file__).resolve().parents[2]


def _check_load_gate(load_gate):
    if load_gate not in ('identity', 'marker'):
        raise ValueError('invalid client registry load gate')


def install(case, nonce, status, *, load_gate='identity'):
    """Gate on identity by default; marker mode requires an identity-free probe.

    Marker mode uses the existing real marked-load hook, never an injected
    expected marker. Mixed marker/identity installations are rejected.
    """
    _check_load_gate(load_gate)
    if not isinstance(nonce, str) or not re.fullmatch(r'[0-9a-f]{32}', nonce):
        raise ValueError('invalid client registry nonce')
    if status == ('uninitialized',):
        expected = 'uninitialized'
    elif (type(status) is tuple and len(status) == 4 and status[0] == 'ready' and
          isinstance(status[1], str) and re.fullmatch(r'[0-9a-f]{32}', status[1]) and
          type(status[2]) is int and 1 <= status[2] <= 200000 and
          isinstance(status[3], str) and re.fullmatch(r'[0-9a-f]{64}', status[3])):
        expected = status[1]+'|'+str(status[2])
    else:
        raise ValueError('invalid client registry status')
    lab = Path(case)/'extensions/x4_lan_lab'; ui = lab/'ui'; md = lab/'md'
    module = ui/'recovery_registry_status.lua'; script = md/'authority_ship_registry.xml'
    manifest = lab/'ui.xml'; text = manifest.read_text(encoding='utf-8')
    hook = '    <file name="ui/authority_download_load_probe.lua" />\n'
    if text.count(hook) != 1: raise ValueError('unexpected client UI manifest')
    updated_manifest = text.replace(hook, '    <file name="ui/recovery_registry_status.lua" />\n'+hook)
    probe = ui/'authority_download_load_probe.lua'; text = probe.read_text(encoding='utf-8')
    hook = "local state='initial';local failed=false\n"
    if text.count(hook) != 1: raise ValueError('unexpected client load owner')
    text = text.replace(hook, hook+'local registry_status=nil;local registry_pause_requested=false;local registry_pause_confirmed=false\n')
    if load_gate == 'marker' and 'X4LAN_IDENTITY_READY' in text:
        raise ValueError('marker registry gate requires an identity-free load probe')
    hook = ('  if not X4LAN_IDENTITY_READY() then return end\n' if load_gate == 'identity' else
            '  if not X4LAN_AUTHORITY_MARKER_READY() then return end\n')
    if text.count(hook) != 1: raise ValueError('client ' + load_gate + ' gate unavailable')
    code = '''  if not engine.is_paused() then
   if registry_pause_confirmed then error('client registry pause lost') end
   if not registry_pause_requested then registry_pause_requested=true;engine.pause() end
   return
  end
  registry_pause_confirmed=true
  if not registry_status then
   registry_status=assert(X4LAN_RECOVERY_REGISTRY_STATUS.new({nonce='NONCE',expected='EXPECTED',
    clock=GetCurRealTime,paused=engine.is_paused,
    register=function(f)return RegisterEvent('X4AuthorityShipRegistry.Correlated',f)~=false end,
    issue=function(screen,op,args)return AddUITriggeredEvent(screen,op,args)~=false end,
    log=function(marker,status)DebugError('[X4LAN] AUTH_RECOVERY_REGISTRY '..'NONCE'..'|'..marker..'|'..status);return true end,
    fault=function()DebugError('[X4LAN] AUTH_RECOVERY_REGISTRY_ERROR '..'NONCE') end,
    store=function()return false end}))
   assert(registry_status:begin())
  end
  assert(registry_status:tick())
  if not registry_status:ready() then return end
'''.replace('NONCE', nonce).replace('EXPECTED', expected)
    updated_probe = text.replace(hook, hook+code)
    # Validate every hook before touching the caller-owned isolated overlay.
    shutil.copyfile(ROOT/'src/authority/lua/recovery_registry_status.lua', module)
    shutil.copyfile(ROOT/'tools/dev/authority_ship_registry.xml', script)
    manifest.write_text(updated_manifest, encoding='utf-8')
    probe.write_text(updated_probe, encoding='utf-8')
    return [module, script]


def verify_log(path, nonce, status, ticket, marker, *, load_gate='identity'):
    """Require ordered correlated receipts; marker mode rejects identity receipts.

    Identity mode retains its existing observation contract. Marker mode accepts
    exactly load request, inspected marker, startup registry status, and pause.
    """
    _check_load_gate(load_gate)
    evidence = recovery.marked.file_evidence
    before = evidence._read_regular(path, evidence.MAX_LOG, collect=True)
    data = before[2]
    if data and not data.endswith(b'\n'): raise ValueError('client log incomplete')
    if b'[X4LAN] AUTH_RECOVERY_REGISTRY_ERROR '+nonce.encode('ascii') in data:
        raise ValueError('client registry status faulted')
    expected = 'uninitialized' if status == ('uninitialized',) else status[1]+'|'+str(status[2])
    watch = recovery.base.client.ReceiptWatch(path, ticket)
    status_tag = b'[X4LAN] AUTH_RECOVERY_REGISTRY '
    status_value = (nonce+'|startup|'+expected).encode('ascii')
    status_rows = [line.split(status_tag, 1)[1].strip() for line in data.splitlines()
                   if status_tag in line and line.split(status_tag, 1)[1].strip().startswith((nonce+'|startup|').encode('ascii'))]
    if status_rows != [status_value]: raise ValueError('client registry status missing or ambiguous')
    needles = [recovery.base.client.TAG+watch.expected[0],
               b'AUTH_MARKER load INSPECTED '+marker.encode('ascii')]
    if load_gate == 'identity':
        needles.append(b'[X4LAN] AUTH_IDENTITY load READY')
    needles.extend([status_tag+status_value, recovery.base.client.TAG+watch.expected[1]])
    if load_gate == 'marker':
        if b'AUTH_IDENTITY load ' in data:
            raise ValueError('marker registry observation contains identity receipts')
        # Check every relevant row, including malformed, duplicate or late
        # marker/load/status events; expected values must match the entire row.
        tags = (recovery.base.client.TAG, b'AUTH_MARKER load ',
                status_tag+nonce.encode('ascii')+b'|')
        observed = []
        for line in data.splitlines():
            if len(line) > watch.MAX_LINE:
                raise ValueError('client registry log line too long')
            for tag in tags:
                if tag in line:
                    observed.append(tag+line.split(tag, 1)[1].strip())
        if observed != needles:
            raise ValueError('client registry/load receipts differ or are out of order')
    lines = data.splitlines(); positions = []
    for needle in needles:
        hits = [i for i, line in enumerate(lines) if needle in line]
        if len(hits) != 1: raise ValueError('missing or repeated client registry/load receipt')
        positions.append(hits[0])
    if positions != sorted(set(positions)): raise ValueError('client registry receipts out of order')
    if evidence._read_regular(path, evidence.MAX_LOG, collect=True) != before:
        raise ValueError('client log changed during registry observation')
    return True
