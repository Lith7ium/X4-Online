#!/usr/bin/env python3
"""Opt-in isolated X4 registry census save/reload diagnostic; no multiplayer.

No game starts on import. Identity evidence is limited: resolving and
re-enrolling the saved MD references is checked for every selected index, and
macros are compared, but there is no independent cross-process identity check.
The inventory does not establish complete universe coverage.
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
import authority_checkpoint_marker_live as marker
import authority_two_x4_live as base


def inject(case, phase, epoch, limit):
    if phase not in ('save', 'load') or not re.fullmatch(r'[0-9a-f]{32}', epoch):
        raise ValueError('invalid census configuration')
    if type(limit) is not int or not 1 <= limit <= 200000:
        raise ValueError('invalid census limit')
    lab = case/'extensions/x4_lan_lab'; ui = lab/'ui'
    for source, target in ((ROOT/'tools/dev/authority_ship_registry.xml', lab/'md/authority_ship_registry.xml'),
                           (ROOT/'tools/dev/authority_registry_census_probe.lua', ui/'authority_registry_census_probe.lua'),
                           (ROOT/'src/authority/lua/x4_ship_engine.lua', ui/'x4_ship_engine.lua')):
        shutil.copyfile(source, target)
    config = ui/'config.lua'; text = config.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('unexpected census config')
    suffix = ', authority_registry_phase="'+phase+'", authority_registry_limit='+str(limit)+', authority_registry_deadline=3600'
    if phase == 'save': suffix += ', authority_registry_epoch="'+epoch+'"'
    config.write_text(text[:-2]+suffix+'}\n', encoding='ascii')
    probe = ui/('authority_world_bridge_probe.lua' if phase == 'save' else 'authority_download_load_probe.lua')
    text = probe.read_text(encoding='utf-8')
    marker_line = (' if not started and now-loaded_at>=3 and not X4LAN_AUTHORITY_MARKER_READY() then return end\n'
                   if phase == 'save' else '  if not X4LAN_AUTHORITY_MARKER_READY() then return end\n')
    extra = (' if not started and now-loaded_at>=3 and not X4LAN_AUTHORITY_REGISTRY_CENSUS_READY() then return end\n'
             if phase == 'save' else '  if not X4LAN_AUTHORITY_REGISTRY_CENSUS_READY() then return end\n')
    if text.count(marker_line) != 1: raise ValueError('marker gate missing')
    probe.write_text(text.replace(marker_line, marker_line+extra), encoding='utf-8')
    manifest = lab/'ui.xml'; text = manifest.read_text(encoding='utf-8')
    hook = '    <file name="ui/authority_checkpoint_marker_probe.lua" />\n'
    if text.count(hook) != 1: raise ValueError('unexpected UI manifest')
    manifest.write_text(text.replace(hook, hook+'    <file name="ui/x4_ship_engine.lua" />\n'
                                    +'    <file name="ui/authority_registry_census_probe.lua" />\n'), encoding='utf-8')


def observations(path, phase, limit, expected_epoch):
    if not isinstance(expected_epoch, str) or not re.fullmatch(r'[0-9a-f]{32}', expected_epoch):
        raise ValueError('invalid expected registry epoch')
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 256 << 20:
        raise ValueError('registry log missing or oversized')
    tag = '[X4LAN] AUTH_REGISTRY '+phase+' '
    rows = [line.split(tag, 1)[1].strip() for line in path.read_text(encoding='utf-8', errors='strict').splitlines() if tag in line]
    if any(row.startswith('ERROR ') for row in rows): raise ValueError('registry probe failure')
    if not rows or rows[0] != 'PAUSED' or rows.count('PAUSED') != 1:
        raise ValueError('pause not confirmed before census')
    epochs = [row for row in rows if row.startswith('EPOCH ')]
    if epochs != ['EPOCH '+expected_epoch]: raise ValueError('missing, duplicate or mismatched registry epoch')
    done = [row for row in rows if row.startswith('DONE ')]
    if len(done) != 1: raise ValueError('missing or duplicate completion')
    match = re.fullmatch(r'DONE count=([0-9]+) coverage=unknown independent_identity=false', done[0])
    if not match: raise ValueError('invalid registry completion')
    count = int(match.group(1))
    if not 1 <= count <= limit: raise ValueError('invalid count')
    observations = []
    for row in rows:
        if row.startswith('ROW '):
            m = re.fullmatch(r'ROW ([0-9]+) ([A-Za-z0-9_]+)', row)
            if not m: raise ValueError('malformed registry row')
            observations.append((int(m.group(1)), m.group(2)))
    if [number for number, _ in observations] != list(range(1, count+1)):
        raise ValueError('incomplete or reordered registry rows')
    inventory = [row for row in rows if row.startswith('INVENTORY ')]
    if phase == 'save':
        if len(inventory) != 1: raise ValueError('inventory missing')
        m = re.fullmatch(r'INVENTORY selected=([0-9]+) eligible=([0-9]+) distinct=([0-9]+) enumerated=([0-9]+) unconfirmed=([0-9]+) unlocated=([0-9]+) observed_sectors=([0-9]+) truncated=(true|false) coverage=unknown', inventory[0])
        if (not m or int(m.group(1)) != count or not 1 <= int(m.group(7))
                or int(m.group(2)) < count or int(m.group(3)) != int(m.group(2))+int(m.group(5))+int(m.group(6))
                or int(m.group(4)) < int(m.group(3)) or (m.group(8)=='true') != (int(m.group(2)) > count)):
            raise ValueError('invalid inventory receipt')
        sectors = int(m.group(7))
    else:
        if inventory: raise ValueError('unexpected client inventory')
        sectors = None
    return observations, sectors


def run(args):
    out = base.snapshot.output_path(args.out)
    epoch = secrets.token_hex(16)
    original_inject = marker.inject
    original_readonly = base.load.readonly_save_command
    def inject_both(case, phase, nonce):
        original_inject(case, phase, nonce)
        inject(case, phase, epoch, args.limit)
    def readonly(case, *a, **kw):
        command = original_readonly(case, *a, **kw); pos = command.index('--die-with-parent')
        lab = case/'extensions/x4_lan_lab'
        for path in (lab/'md/authority_ship_registry.xml', lab/'ui/authority_registry_census_probe.lua',
                     lab/'ui/x4_ship_engine.lua'):
            command[pos:pos] = ['--ro-bind', str(path), str(path)]; pos += 3
        return command
    try:
        marker.inject, base.load.readonly_save_command = inject_both, readonly
        result = marker.run(args)
    finally:
        marker.inject, base.load.readonly_save_command = original_inject, original_readonly
    result['scope'] = ('isolated Linux/Linux save/transfer/load; finite existing-ship sample; '
                       'no independent identity proof, completeness, admission, or gameplay')
    if result.get('success'):
        log = Path('case/home/.config/EgoSoft/X4/45841/engine-output.log')
        try:
            before, sectors = observations(out/'server'/log, 'save', args.limit, epoch)
            after, _ = observations(out/'client'/log, 'load', args.limit, epoch)
            if before != after: raise ValueError('restored register macro sequence differs')
            result.update(registry_count=len(before), inventory_observed_sectors=sectors,
                          duplicate_enrollment_checked=True, cross_load_macros_match=True,
                          independent_identity_proven=False, universe_coverage_proven=False)
        except (OSError, UnicodeError, ValueError) as error:
            result.update(success=False, error=str(error))
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game', required=True, type=Path); p.add_argument('--out', required=True, type=Path)
    p.add_argument('--display', required=True); p.add_argument('--timeout', type=float, default=7500)
    p.add_argument('--seed', type=int, default=276944566); p.add_argument('--limit', type=int, default=200000)
    args = p.parse_args()
    if not 1 <= args.limit <= 200000: p.error('limit must be between 1 and 200000')
    try: result = run(args)
    except (OSError, ValueError, RuntimeError) as error: p.exit(1, 'REFUSED: '+str(error)+'\n')
    print(json.dumps(result, indent=2)); return 0 if result['success'] else 1

if __name__ == '__main__': main()
