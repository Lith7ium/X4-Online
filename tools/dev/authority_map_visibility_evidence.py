"""Evidence table for the map visibility probe (tools/dev/authority_map_visibility_probe.lua).

Reads the probe's log rows ("[X4LAN] AUTH_MAPVIS ...") and reports, for the three views
onscreen / offscreen / back, the NPC's raw-list membership, the camera readback and whether the
requested camera effect was reached. Screen visibility of the icon is judged from the captured
images, not from these rows; the table names the image of each view.

  python tools/dev/authority_map_visibility_evidence.py <x4 log> [--shots DIR] [--json OUT]
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

PREFIX = '[X4LAN] AUTH_MAPVIS '
VIEWS = ('onscreen', 'offscreen', 'back')
_FIELD = re.compile(r'(\w+)=(\S*)')


def parse_rows(text):
    """Probe rows as (kind, {field: value}) in log order; LIST ids become a list of decimal strings."""
    rows = []
    for line in text.splitlines():
        at = line.find(PREFIX)
        if at < 0:
            continue
        body = line[at + len(PREFIX):].strip()
        kind, _, rest = body.partition(' ')
        if kind == 'ERROR':
            rows.append((kind, {'message': rest}))
            continue
        fields = dict(_FIELD.findall(rest))
        if kind == 'LIST':
            fields['ids'] = [item for item in fields.get('ids', '').split(',') if item]
        rows.append((kind, fields))
    return rows


def _flag(value):
    if value not in ('true', 'false'):
        raise ValueError(f'not a boolean: {value!r}')
    return value == 'true'


def evaluate(rows, shots=None):
    """Evidence dict. `shots` maps seq (int) to an image path, when the images are at hand."""
    errors = [fields['message'] for kind, fields in rows if kind == 'ERROR']
    pick = next((fields for kind, fields in rows if kind == 'PICK'), None)
    views = {}
    for kind, fields in rows:
        if kind == 'VIEW' and fields.get('view') in VIEWS:
            views.setdefault(fields['view'], {})[fields['phase']] = fields
        if kind == 'LIST' and fields.get('view') in VIEWS:
            views.setdefault(fields['view'], {}).setdefault('lists', {})[fields['phase']] = fields['ids']
    seq_of = {fields['view']: int(fields['seq']) for kind, fields in rows if kind == 'SHOT'}
    table, problems = [], list(errors)
    npc_ids, distances = set(), set()
    for name in VIEWS:
        phases = views.get(name, {})
        before, after = phases.get('before_shot'), phases.get('after_shot')
        if not before or not after:
            problems.append(f'{name}: missing view rows')
            continue
        lists = phases.get('lists', {})
        stable_list = lists.get('before_shot') == lists.get('after_shot')
        if not stable_list:
            problems.append(f'{name}: raw list changed during the screenshot')
        for row in (before, after):
            npc_ids.add(row['npc'])
            distances.add(row['npc_player_m'])
            if not _flag(row['paused']):
                problems.append(f'{name}: game not paused')
        image = None
        if shots and name in seq_of and seq_of[name] in shots:
            path = Path(shots[seq_of[name]])
            image = {'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        entry = {
            'view': name,
            'control': before['control'],
            'reached': _flag(before['reached']),
            'npc_listed': _flag(before['npc_listed']) and _flag(after['npc_listed']),
            'npc_listed_before_after': [_flag(before['npc_listed']), _flag(after['npc_listed'])],
            'player_listed': _flag(before['player_listed']),
            'raw_count': int(before['raw_count']),
            'list_stable': stable_list,
            'focus': before['focus'],
            'selected': int(before['selected']),
            'camera': {key: float(before[f'camera_{key}']) for key in ('x', 'y', 'z', 'distance')},
            'target': ({key: float(before[f'target_{key}']) for key in ('x', 'y', 'z', 'distance')}
                       if 'target_x' in before else None),
            'npc_known': _flag(before['npc_known']),
            'npc_radar': _flag(before['npc_radar']),
            'shot_seq': seq_of.get(name),
            'image': image,
        }
        if 'pan_failed' in phases:
            entry['pan_failed_first'] = {key: float(phases['pan_failed'][f'camera_{key}']) for key in ('x', 'y', 'z', 'distance')}
        table.append(entry)
    if len(npc_ids) > 1:
        problems.append('NPC identity changed between views')
    if len(distances) > 1:
        problems.append('NPC-player distance changed although paused')
    selected = {entry['selected'] for entry in table}
    if len(selected) > 1:
        problems.append('map selection changed between views')
    by_name = {entry['view']: entry for entry in table}
    conclusion = 'inconclusive'
    if not problems and len(by_name) == 3:
        on, off, back = by_name['onscreen'], by_name['offscreen'], by_name['back']
        if not (on['reached'] and off['reached'] and back['reached']):
            conclusion = 'inconclusive: a requested camera effect was not reached'
        elif on['npc_listed'] and back['npc_listed'] and not off['npc_listed']:
            conclusion = 'listed onscreen, absent offscreen, listed again: the raw list follows the view for this fixture'
        elif on['npc_listed'] and off['npc_listed'] and back['npc_listed']:
            conclusion = 'listed in all three views: the raw list is not clipped to the view for this fixture'
        elif not on['npc_listed'] and not back['npc_listed']:
            conclusion = 'inconclusive: the NPC is not listed even onscreen'
        else:
            conclusion = 'inconclusive: membership does not follow onscreen/offscreen/back consistently'
    return {
        'pick': pick,
        'views': table,
        'problems': problems,
        'conclusion': conclusion,
        'icon_visibility': 'judge from the images; not derived from the API under test',
        'done': any(kind == 'DONE' for kind, _ in rows),
    }


def markdown(evidence):
    lines = ['| View | Control | Reached | NPC listed | Raw count | Camera X | Camera distance | Focus | Image |',
             '| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |']
    for entry in evidence['views']:
        image = entry['image']['file'] if entry['image'] else '-'
        lines.append(f"| {entry['view']} | {entry['control']} | {entry['reached']} | {entry['npc_listed']} | "
                     f"{entry['raw_count']} | {entry['camera']['x']:.1f} | {entry['camera']['distance']:.1f} | "
                     f"{entry['focus']} | {image} |")
    lines.append('')
    lines.append(f"Conclusion: {evidence['conclusion']}")
    for problem in evidence['problems']:
        lines.append(f'- problem: {problem}')
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('log', type=Path)
    parser.add_argument('--shots', type=Path)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args(argv)
    rows = parse_rows(args.log.read_text(encoding='utf-8', errors='replace'))
    shots = None
    if args.shots:
        shots = {int(path.name.split('-')[1]): path for path in sorted(args.shots.glob('shot-*.png'))}
    evidence = evaluate(rows, shots)
    if args.json:
        with args.json.open('x', encoding='utf-8') as handle:
            json.dump(evidence, handle, indent=2)
    sys.stdout.write(markdown(evidence))
    return 0 if evidence['done'] and not evidence['problems'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
