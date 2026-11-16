"""Read-only diagnostic: compare a sealed saved witness with its saved registry.

Checks the bytes of one checkpoint, not historical identity, X4 loading,
universe coverage, or multiplayer. Not used by the recovery admission guard.
"""
from pathlib import Path
import re
import sys
import zlib
from xml.parsers import expat

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from authority.checkpoints import Checkpoint
from authority.marker_evidence import _parse, MarkerEvidenceError

_DECIMAL = re.compile(r'[1-9][0-9]{0,8}\Z')
_COMPONENT = re.compile(r'\[0x([0-9a-f]{1,16})\]\Z')
_EPOCH = re.compile(r'[0-9a-f]{32}\Z')
_MAX = 200000


class WitnessEvidenceError(ValueError):
    """Saved diagnostic evidence is incomplete or inconsistent."""


def verify(checkpoint, expected_epoch, expected_count):
    """Verify four tables in one digest-checked checkpoint; fail closed."""
    if (not isinstance(checkpoint, Checkpoint) or not isinstance(expected_epoch, str)
            or not _EPOCH.fullmatch(expected_epoch) or type(expected_count) is not int
            or not 1 <= expected_count <= _MAX):
        raise WitnessEvidenceError('invalid verification request')
    names = {
        'X4AuthorityShipRegistry': {'$epoch', '$last', '$faulted', '$ships', '$byship'},
        'X4AuthorityRegistryWitness': {'$epoch', '$count', '$cursor', '$phase', '$faulted', '$objects', '$reverse'},
    }
    counts = {n: [0, 0, 0] for n in names}
    fields = {n: {} for n in names}
    active = None
    cue = False

    def state(path, attrs):
        nonlocal active, cue
        if path == ['savegame', 'md', 'script']:
            active = attrs.get('name') if attrs.get('name') in names else None
            cue = False
            if active: counts[active][0] += 1
        elif path == ['savegame', 'md', 'script', 'cue'] and active:
            cue = attrs.get('name') == 'State'
            if cue: counts[active][1] += 1
        elif path == ['savegame', 'md', 'script', 'cue', 'vars'] and active and cue:
            counts[active][2] += 1
        elif path == ['savegame', 'md', 'script', 'cue', 'vars', 'value'] and active and cue:
            name = attrs.get('name')
            if name in names[active]:
                if name in fields[active]: raise WitnessEvidenceError('duplicate state field')
                fields[active][name] = dict(attrs)

    try:
        _parse(checkpoint, state)
        for name in names:
            if counts[name] != [1, 1, 1] or set(fields[name]) != names[name]:
                raise WitnessEvidenceError('missing or ambiguous state')
        registry = fields['X4AuthorityShipRegistry']
        witness = fields['X4AuthorityRegistryWitness']
        for values in (registry, witness):
            fault = values['$faulted']
            if fault.get('type') != 'integer' or 'value' in fault:
                raise WitnessEvidenceError('faulted or unknown flag')
        for values, key in ((registry, '$last'), (witness, '$count'), (witness, '$cursor')):
            # X4 has saved these witness counters as largefloat in a native run.
            # Accept only the exact canonical decimal spelling of the already
            # bounded positive integer; never parse or round floating point.
            allowed = ('integer', 'largefloat') if values is witness else ('integer',)
            if values[key].get('type') not in allowed or values[key].get('value') != str(expected_count):
                raise WitnessEvidenceError('incorrect count or unfinished witness')
        references = {}
        for values, key, name, typ in (
            (registry, '$epoch', 'registry_epoch', 'string'),
            (witness, '$epoch', 'witness_epoch', 'string'),
            (witness, '$phase', 'phase', 'string'),
            (registry, '$ships', 'ships', 'table'),
            (registry, '$byship', 'byship', 'table'),
            (witness, '$objects', 'objects', 'table'),
            (witness, '$reverse', 'reverse', 'table'),
        ):
            entry = values[key]
            if entry.get('type') != typ or not _DECIMAL.fullmatch(entry.get('value', '')):
                raise WitnessEvidenceError('invalid reference')
            references[name] = entry['value']
        tables = ('ships', 'byship', 'objects', 'reverse')
        if len({references[name] for name in tables}) != 4:
            raise WitnessEvidenceError('aliased tables')
        wanted = {references[name]: name for name in tables}
        string_refs = {references['registry_epoch'], references['witness_epoch'], references['phase']}
        found_strings = {}
        seen = {name: 0 for name in tables}
        rows = {name: {} for name in tables}
        group = active_table = None
        groups = {'script': 0, 'string': 0, 'table': 0}
        pending = None

        def refs(path, attrs):
            nonlocal group, active_table, pending
            if path == ['savegame', 'script']:
                groups['script'] += 1
            elif path == ['savegame', 'script', 'refs']:
                if attrs.get('type') in ('string', 'table'):
                    groups[attrs['type']] += 1
                if pending is not None: raise WitnessEvidenceError('unpaired table key')
                group = attrs.get('type'); active_table = None
            elif path == ['savegame', 'script', 'refs', 'ref']:
                if pending is not None: raise WitnessEvidenceError('unpaired table key')
                active_table = None
                ref = attrs.get('id')
                if group == 'string' and ref in string_refs:
                    if ref in found_strings: raise WitnessEvidenceError('duplicate string reference')
                    found_strings[ref] = attrs.get('string')
                if group == 'table' and ref in wanted:
                    active_table = wanted[ref]
                    seen[active_table] += 1
                    if seen[active_table] != 1: raise WitnessEvidenceError('duplicate table reference')
            elif len(path) == 5 and path[:4] == ['savegame', 'script', 'refs', 'ref'] and active_table:
                tag = path[-1]
                if tag == 'key':
                    if pending is not None: raise WitnessEvidenceError('unpaired table key')
                    pending = (attrs.get('type'), attrs.get('value', ''))
                elif tag == 'value':
                    if pending is None: raise WitnessEvidenceError('value without key')
                    kt, kv = pending; pending = None
                    vt, vv = attrs.get('type'), attrs.get('value', '')
                    if active_table in ('ships', 'objects'): it, iv, ct, cv = kt, kv, vt, vv
                    else: ct, cv, it, iv = kt, kv, vt, vv
                    match = _COMPONENT.fullmatch(cv)
                    # The witness tables may serialize their numeric slot as
                    # largefloat; keep the exact positive decimal spelling and
                    # the same index, uniqueness and permutation checks.
                    allowed = ('integer', 'largefloat') if active_table in ('objects', 'reverse') else ('integer',)
                    if it not in allowed or not _DECIMAL.fullmatch(iv) or ct != 'component' or not match or int(match.group(1), 16) == 0:
                        raise WitnessEvidenceError('invalid table row')
                    index = int(iv); component = format(int(match.group(1), 16), 'x')
                    key, value = (index, component) if active_table in ('ships', 'objects') else (component, index)
                    if key in rows[active_table] or len(rows[active_table]) >= expected_count:
                        raise WitnessEvidenceError('duplicate or excess row')
                    rows[active_table][key] = value
                else: raise WitnessEvidenceError('unexpected table child')
            elif len(path) > 5 and path[:4] == ['savegame', 'script', 'refs', 'ref'] and active_table:
                raise WitnessEvidenceError('nested table row')
        _parse(checkpoint, refs)
        if groups != {'script': 1, 'string': 1, 'table': 1}:
            raise WitnessEvidenceError('ambiguous reference containers')
        if pending is not None or any(seen[name] != 1 for name in tables):
            raise WitnessEvidenceError('missing table')
        if (found_strings.get(references['registry_epoch']) != expected_epoch or
            found_strings.get(references['witness_epoch']) != expected_epoch or
            found_strings.get(references['phase']) != 'sealed'):
            raise WitnessEvidenceError('epoch or phase mismatch')
        ships, byship, objects, reverse = (rows[name] for name in tables)
        indices = set(range(1, expected_count + 1))
        if (set(ships) != indices or set(objects) != indices or
            len(byship) != expected_count or len(reverse) != expected_count or
            len(set(ships.values())) != expected_count):
            raise WitnessEvidenceError('incomplete or duplicate bindings')
        for i, component in ships.items():
            slot = expected_count + 1 - i
            if byship.get(component) != i or objects.get(slot) != component or reverse.get(component) != slot:
                raise WitnessEvidenceError('registry and witness disagree')
        found = set()
        def components(path, attrs):
            if len(path) < 3 or path[:2] != ['savegame', 'universe'] or path[-1] != 'component': return
            match = _COMPONENT.fullmatch(attrs.get('id', ''))
            if not match: return
            ident = format(int(match.group(1), 16), 'x')
            if ident not in byship: return
            if ident in found or not attrs.get('class', '').startswith('ship_') or not attrs.get('macro'):
                raise WitnessEvidenceError('duplicate or invalid ship component')
            found.add(ident)
        _parse(checkpoint, components)
        if len(found) != expected_count: raise WitnessEvidenceError('missing ship component')
        return {'count': expected_count, 'registry_witness_match': True,
                'historical_identity_proven': False, 'runtime_binding_proven': False,
                'universe_coverage_proven': False}
    except WitnessEvidenceError:
        raise
    except (OSError, EOFError, expat.ExpatError, zlib.error, MarkerEvidenceError) as error:
        raise WitnessEvidenceError('checkpoint could not be verified') from error
