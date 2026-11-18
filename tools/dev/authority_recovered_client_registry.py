"""Optional join-checkpoint registry observation for the isolated X4 client.

This is a cooperative local status check, not a proof of loaded bytes or actor
identity. The surrounding owner must guard process, files, ticket and marker.
"""
import re
import shutil
from pathlib import Path

import authority_recovery_tcp_join_live as recovery
from authority.client_registry_overlay import extend_load_probe, registry_receipt

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
    registry_receipt(nonce, status)
    lab = Path(case)/'extensions/x4_lan_lab'; ui = lab/'ui'; md = lab/'md'
    module = ui/'recovery_registry_status.lua'; script = md/'authority_ship_registry.xml'
    manifest = lab/'ui.xml'; text = manifest.read_text(encoding='utf-8')
    hook = '    <file name="ui/authority_download_load_probe.lua" />\n'
    if text.count(hook) != 1: raise ValueError('unexpected client UI manifest')
    updated_manifest = text.replace(hook, '    <file name="ui/recovery_registry_status.lua" />\n'+hook)
    probe = ui/'authority_download_load_probe.lua'; text = probe.read_text(encoding='utf-8')
    updated_probe = extend_load_probe(text, nonce, status, load_gate=load_gate)
    # Validate every hook before touching the caller-owned isolated overlay.
    shutil.copyfile(ROOT/'src/authority/lua/recovery_registry_status.lua', module)
    shutil.copyfile(ROOT/'tools/dev/authority_ship_registry.xml', script)
    manifest.write_text(updated_manifest, encoding='utf-8')
    probe.write_text(updated_probe, encoding='utf-8')
    return [module, script]


def _verify_log_data(data, nonce, status, watch, marker, load_gate):
    """Validate complete captured rows without reading the live log again."""
    if data and not data.endswith(b'\n'): raise ValueError('client log incomplete')
    if b'[X4LAN] AUTH_RECOVERY_REGISTRY_ERROR '+nonce.encode('ascii') in data:
        raise ValueError('client registry status faulted')
    expected = 'uninitialized' if status == ('uninitialized',) else status[1]+'|'+str(status[2])
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


def verify_log(path, nonce, status, ticket, marker, *, load_gate='identity'):
    """Require ordered correlated receipts and two matching append-only captures.

    Unrelated complete rows may append between the captures. Replacement,
    truncation, rewritten prefixes and newly appended load/registry/marker or
    identity rows fail closed. Each capture must itself be stable; an in-read
    append remains an unstable observation rather than a retry here.
    """
    _check_load_gate(load_gate)
    evidence = recovery.marked.file_evidence
    watch = recovery.base.client.ReceiptWatch(path, ticket)
    before = evidence._read_regular(path, evidence.MAX_LOG, collect=True)
    _verify_log_data(before[2], nonce, status, watch, marker, load_gate)
    after = evidence._read_regular(path, evidence.MAX_LOG, collect=True)
    if after != before:
        if (after[0][:2] != before[0][:2] or len(after[2]) <= len(before[2]) or
                not after[2].startswith(before[2])):
            raise ValueError('client log changed during registry observation')
        appended = after[2][len(before[2]):]
        relevant = (recovery.base.client.TAG, b'AUTH_MARKER load ',
                    b'AUTH_IDENTITY load ', b'AUTH_RECOVERY_REGISTRY')
        if any(tag in appended for tag in relevant):
            raise ValueError('client log changed during registry observation')
        try:
            _verify_log_data(after[2], nonce, status, watch, marker, load_gate)
        except ValueError as error:
            raise ValueError('client log changed during registry observation') from error
    return True
