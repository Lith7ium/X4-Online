"""Shared read-only registry gate for the existing client load update hook.

The caller supplies status derived from its verified checkpoint. Epoch/count
receipts describe the live registry header; they do not prove the full mapping
or actor identity. This module performs no filesystem or native operations.
"""
import re


def _check_load_gate(load_gate):
    if load_gate not in ('identity', 'marker'):
        raise ValueError('invalid client registry load gate')


def registry_status_text(status):
    """Validate the saved status tuple and format the observed live header."""
    if status == ('uninitialized',):
        return 'uninitialized'
    if (type(status) is tuple and len(status) == 4 and status[0] == 'ready' and
            type(status[1]) is str and re.fullmatch(r'[0-9a-f]{32}', status[1]) and
            type(status[2]) is int and 1 <= status[2] <= 200000 and
            type(status[3]) is str and re.fullmatch(r'[0-9a-f]{64}', status[3])):
        return status[1] + '|' + str(status[2])
    raise ValueError('invalid client registry status')


def registry_receipt(nonce, status):
    """Return the expected correlated startup record, without its log tag."""
    if type(nonce) is not str or not re.fullmatch(r'[0-9a-f]{32}', nonce):
        raise ValueError('invalid client registry nonce')
    return (nonce + '|startup|' + registry_status_text(status)).encode('ascii')


def extend_load_probe(text, nonce, status, *, load_gate='identity'):
    """Add the existing paused registry check before the load pause receipt."""
    _check_load_gate(load_gate)
    registry_receipt(nonce, status)
    expected = registry_status_text(status)
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
    return updated_probe
