#!/usr/bin/env python3
"""Opt-in two-X4 checkpoint marker diagnostic, without admission or gameplay.

Fresh marker is set only in the server's MD state before the verified save. The
client receives only the save, then checks the marker after event_game_loaded.
This does not prove a byte-for-byte read or make a production trust decision.
"""
import argparse
import json
from pathlib import Path
import re
import secrets
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
import authority_two_x4_identity_live as identity
import authority_two_x4_live as base


def inject(case, phase, nonce):
    if phase not in ('save', 'load') or not re.fullmatch(r'[0-9a-f]{32}', nonce):
        raise ValueError('invalid marker configuration')
    lab = case/'extensions/x4_lan_lab'; ui = lab/'ui'
    shutil.copyfile(ROOT/'tools/dev/authority_checkpoint_marker.xml', lab/'md/authority_checkpoint_marker.xml')
    shutil.copyfile(ROOT/'tools/dev/authority_checkpoint_marker_probe.lua', ui/'authority_checkpoint_marker_probe.lua')
    config = ui/'config.lua'; text = config.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('unexpected private configuration')
    suffix = ', authority_marker_phase="'+phase+'"'
    if phase == 'save': suffix += ', authority_marker="'+nonce+'"'
    config.write_text(text[:-2]+suffix+'}\n', encoding='ascii')
    probe = ui/('authority_world_bridge_probe.lua' if phase == 'save' else 'authority_download_load_probe.lua')
    text = probe.read_text(encoding='utf-8')
    old = (' if not started and now-loaded_at>=3 then\n' if phase == 'save'
           else " elseif state=='observing' then\n")
    if text.count(old) != 1: raise ValueError('unexpected marker probe hook')
    new = (" if not started and now-loaded_at>=3 and not X4LAN_AUTHORITY_MARKER_READY() then return end\n"+old
           if phase == 'save' else old+"  if not X4LAN_AUTHORITY_MARKER_READY() then return end\n")
    probe.write_text(text.replace(old, new), encoding='utf-8')
    ui_xml = lab/'ui.xml'; text = ui_xml.read_text(encoding='utf-8')
    hook = '    <file name="ui/authority_identity_probe.lua" />\n'
    if text.count(hook) != 1: raise ValueError('unexpected UI manifest')
    ui_xml.write_text(text.replace(hook, hook+'    <file name="ui/authority_checkpoint_marker_probe.lua" />\n'), encoding='utf-8')


def verify_receipts(server_text, client_text, nonce, ticket):
    if not re.fullmatch(r'[0-9a-f]{32}', nonce): raise ValueError('invalid marker')
    required = ('world_epoch', 'connection_handle', 'baseline_id', 'load_generation',
                'checkpoint_id', 'sha256', 'attempt_id', 'slot')
    if not isinstance(ticket, dict) or set(ticket) != set(required): raise ValueError('missing load attempt')
    if not re.fullmatch(r'[0-9a-f]{64}', ticket['sha256']): raise ValueError('invalid offered checkpoint')
    pattern = re.compile(r'AUTH_MARKER (save|load) (STORED|INSPECTED) ([0-9a-f]{32})')
    def parse(text):
        lines = [line for line in text.splitlines() if 'AUTH_MARKER ' in line]
        matches = [pattern.search(line) for line in lines]
        if len(lines) != 1 or not matches[0]: raise ValueError('missing, malformed or duplicate marker receipt')
        return matches[0].groups()
    if parse(server_text) != ('save', 'STORED', nonce) or parse(client_text) != ('load', 'INSPECTED', nonce):
        raise ValueError('checkpoint marker differs')
    return True


def run(args):
    out = base.snapshot.output_path(args.out)
    nonce = secrets.token_hex(16); observed = []
    old_inject, old_download, old_readonly = identity.inject, base.offer_and_download, base.load.readonly_save_command
    def inject_both(case, phase):
        old_inject(case, phase); inject(case, phase, nonce)
    def capture(*a, **kw):
        ticket, target = old_download(*a, **kw)
        observed.append(dict(ticket))
        return ticket, target
    def readonly(case, *a, **kw):
        command = old_readonly(case, *a, **kw); pos = command.index('--die-with-parent')
        lab = case/'extensions/x4_lan_lab'
        for path in (lab/'md/authority_checkpoint_marker.xml', lab/'ui/authority_checkpoint_marker_probe.lua'):
            command[pos:pos] = ['--ro-bind', str(path), str(path)]; pos += 3
        return command
    try:
        identity.inject, base.offer_and_download, base.load.readonly_save_command = inject_both, capture, readonly
        result = identity.run(args)
    finally:
        identity.inject, base.offer_and_download, base.load.readonly_save_command = old_inject, old_download, old_readonly
    result['scope'] = ('two isolated Linux X4 processes; saved marker and game-loaded event; '
                       'local transfer; no admission or gameplay')
    if result.get('success'):
        try:
            if len(observed) != 1: raise ValueError('expected one load offer')
            log = Path('case/home/.config/EgoSoft/X4/45841/engine-output.log')
            verify_receipts((out/'server'/log).read_text(), (out/'client'/log).read_text(), nonce, observed[0])
            result.update(marker_restored_after_game_loaded=True, marker_bound_to_offered_load_attempt=True,
                          exact_loaded_file_proven=False, client_admitted=False)
        except (OSError, ValueError) as error:
            result.update(success=False, error=str(error))
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game', required=True, type=Path); p.add_argument('--out', required=True, type=Path)
    p.add_argument('--display', required=True); p.add_argument('--timeout', type=float, default=600)
    p.add_argument('--seed', type=int, default=276944566)
    try: result = run(p.parse_args())
    except (OSError, ValueError, RuntimeError) as error: p.exit(1, 'REFUSED: '+str(error)+'\n')
    print(json.dumps(result, indent=2)); return 0 if result['success'] else 1

if __name__ == '__main__': sys.exit(main())
