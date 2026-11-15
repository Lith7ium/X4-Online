#!/usr/bin/env python3
"""Inspect two fixture slots and their saved ship/sector ancestry, not runtime binding."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
from authority.marker_evidence import _parse
import authority_registry_save_evidence as registry


class SectorEvidenceError(ValueError):
    pass


def verify(checkpoint, epoch):
    """Validate exactly two saved fixture slots against the ship registry and XML ancestry.

    This accepts only the anticipated MD serialization; it has not been observed
    for this fixture in native X4. A match says nothing about the file X4 loaded.
    """
    registry.verify(checkpoint, epoch, 2)
    names = {'$epoch', '$index1', '$index2', '$ship1', '$ship2', '$sector1', '$sector2'}
    fields = {}; counts = {'script': 0, 'cue': 0, 'vars': 0}; active_script = active_cue = False
    forward = None; registry_script = registry_cue = False

    def state(path, attrs):
        nonlocal active_script, active_cue, registry_script, registry_cue, forward
        if path == ['savegame', 'md', 'script']:
            active_script = attrs.get('name') == 'X4AuthoritySectorReferenceFixture'
            registry_script = attrs.get('name') == 'X4AuthorityShipRegistry'
            active_cue = registry_cue = False
            if active_script: counts['script'] += 1
        elif path == ['savegame', 'md', 'script', 'cue']:
            active_cue = active_script and attrs.get('name') == 'State'
            registry_cue = registry_script and attrs.get('name') == 'State'
            if active_cue: counts['cue'] += 1
        elif path == ['savegame', 'md', 'script', 'cue', 'vars'] and active_cue:
            counts['vars'] += 1
        elif path == ['savegame', 'md', 'script', 'cue', 'vars', 'value']:
            name = attrs.get('name')
            if active_cue and name in names:
                if name in fields: raise SectorEvidenceError('duplicate fixture field')
                fields[name] = dict(attrs)
            if registry_cue and name == '$ships':
                if forward is not None: raise SectorEvidenceError('duplicate registry forward reference')
                forward = attrs.get('value')
    _parse(checkpoint, state)
    if counts != {'script': 1, 'cue': 1, 'vars': 1} or set(fields) != names:
        raise SectorEvidenceError('missing or ambiguous fixture state')
    if fields['$epoch'].get('type') != 'string' or not registry.DECIMAL.fullmatch(fields['$epoch'].get('value', '')):
        raise SectorEvidenceError('invalid epoch reference')
    epoch_ref = fields['$epoch']['value']
    if not registry.DECIMAL.fullmatch(forward or ''): raise SectorEvidenceError('invalid registry forward reference')

    def component(name):
        field = fields[name]; match = registry.COMPONENT.fullmatch(field.get('value', ''))
        if field.get('type') != 'component' or not match: raise SectorEvidenceError('invalid fixture component')
        return format(int(match.group(1), 16), 'x')

    indices = []
    for n in (1, 2):
        field = fields['$index' + str(n)]; value = field.get('value', '')
        # X4 stores the Lua-origin numeric indices as largefloat in the native
        # checkpoint; only canonical positive integral values are accepted.
        if field.get('type') not in ('integer', 'largefloat') or not registry.DECIMAL.fullmatch(value):
            raise SectorEvidenceError('invalid fixture index')
        indices.append(int(value))
    ships = [component('$ship1'), component('$ship2')]
    sectors = [component('$sector1'), component('$sector2')]
    if set(indices) != {1, 2} or len(set(ships)) != 2 or len(set(sectors)) != 2:
        raise SectorEvidenceError('fixture slots are ambiguous')

    group = active = None; epoch_count = table_count = 0; pending = None; entries = {}
    def refs(path, attrs):
        nonlocal group, active, epoch_count, table_count, pending
        if path == ['savegame', 'script', 'refs']:
            group = attrs.get('type'); active = None; pending = None
        elif path == ['savegame', 'script', 'refs', 'ref']:
            active = None
            if group == 'string' and attrs.get('id') == epoch_ref:
                epoch_count += 1
                if attrs.get('string') != epoch: raise SectorEvidenceError('fixture epoch mismatch')
            elif group == 'table' and attrs.get('id') == forward:
                table_count += 1; active = 'forward'
        elif len(path) == 5 and path[:4] == ['savegame', 'script', 'refs', 'ref'] and active:
            if path[-1] == 'key':
                if pending is not None: raise SectorEvidenceError('dangling registry key')
                pending = dict(attrs)
            elif path[-1] == 'value':
                if pending is None or pending.get('type') != 'integer' or attrs.get('type') != 'component':
                    raise SectorEvidenceError('malformed registry pair')
                match = registry.COMPONENT.fullmatch(attrs.get('value', ''))
                value = pending.get('value', '')
                if not match or not registry.DECIMAL.fullmatch(value): raise SectorEvidenceError('invalid registry pair')
                index = int(value)
                if index in entries: raise SectorEvidenceError('duplicate registry index')
                entries[index] = format(int(match.group(1), 16), 'x'); pending = None
            else: raise SectorEvidenceError('invalid registry entry')
    _parse(checkpoint, refs)
    if epoch_count != 1 or table_count != 1 or pending is not None or any(entries.get(i) != s for i, s in zip(indices, ships)):
        raise SectorEvidenceError('fixture differs from registry')

    wanted = set(ships + sectors); found = {}; ancestors = []
    def tree(path, attrs):
        del ancestors[len(path)-1:]
        ancestors.append((path[-1], dict(attrs) if path[-1] == 'component' else {}))
        if len(path) < 3 or path[:2] != ['savegame', 'universe'] or path[-1] != 'component': return
        match = registry.COMPONENT.fullmatch(attrs.get('id', ''))
        if not match: return
        ident = format(int(match.group(1), 16), 'x')
        if ident not in wanted: return
        if ident in found: raise SectorEvidenceError('duplicate saved component')
        parents = [a for tag, a in ancestors[:-1] if tag == 'component' and a.get('class') == 'sector']
        found[ident] = (attrs.get('class', ''), parents)
    _parse(checkpoint, tree)
    if set(found) != wanted: raise SectorEvidenceError('saved fixture component missing')
    for ship, sector in zip(ships, sectors):
        if not found[ship][0].startswith('ship_') or found[sector][0] != 'sector':
            raise SectorEvidenceError('wrong saved component class')
        parents = found[ship][1]
        if len(parents) != 1: raise SectorEvidenceError('missing or ambiguous sector ancestor')
        match = registry.COMPONENT.fullmatch(parents[0].get('id', ''))
        if not match or format(int(match.group(1), 16), 'x') != sector:
            raise SectorEvidenceError('saved ship sector ancestor differs from slot')
    return {'slots_checked': 2, 'saved_ship_sector_ancestry_matches': True,
            'runtime_binding_proven': False, 'exact_loaded_file_proven': False,
            'universe_coverage_proven': False}
