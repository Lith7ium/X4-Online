"""Strict read-only verifier for a saved full registry availability snapshot.

Availability records binding presence; operational bits record the captured
operational observation. Both describe checkpoint bytes only. Operational bits
are not current command permission: callers must recheck live before acting.
"""
import hashlib
import re
import zlib
from xml.parsers import expat

from .checkpoints import Checkpoint
from .marker_evidence import _parse, MarkerEvidenceError, _PumpCallbackError


class RegistryAvailabilityEvidenceError(ValueError):
    """The saved availability snapshot is absent, ambiguous, or inconsistent."""


_HEX32 = re.compile(r'[0-9a-f]{32}\Z')
_REF = re.compile(r'[0-9]{1,32}\Z')
_COMPONENT = re.compile(r'\[0x([0-9a-f]+)\]\Z')
_INTEGER = re.compile(r'(?:0|[1-9][0-9]*)\Z')
_LARGE_INTEGER = re.compile(r'(?:0|[1-9][0-9]*)\.0+\Z')
_MAX = 200000
_FIELDS = {'$format', '$epoch', '$run_id', '$issued_count', '$cursor',
           '$available_count', '$unavailable_count', '$operational_count',
           '$sealed', '$faulted', '$available', '$operational', '$ships', '$byship'}


def _integer(field, expected=None):
    if field.get('type') != 'integer':
        raise RegistryAvailabilityEvidenceError('invalid integer field')
    raw = field.get('value')
    if raw is None:
        value = 0
    elif _INTEGER.fullmatch(raw):
        value = int(raw)
    else:
        raise RegistryAvailabilityEvidenceError('invalid integer value')
    if expected is not None and value != expected:
        raise RegistryAvailabilityEvidenceError('unexpected integer value')
    return value


def _table_index(kind, raw):
    if kind == 'integer' and _INTEGER.fullmatch(raw):
        value = int(raw)
    elif kind == 'largefloat' and (_INTEGER.fullmatch(raw) or _LARGE_INTEGER.fullmatch(raw)):
        value = int(raw.split('.', 1)[0]) if '.' in raw else int(raw)
    else:
        raise RegistryAvailabilityEvidenceError('invalid table index')
    if not 1 <= value <= _MAX:
        raise RegistryAvailabilityEvidenceError('table index outside supported range')
    return value


def verify(checkpoint, expected_epoch, expected_run_id, expected_count, *, pump=None):
    """Verify a complete saved availability snapshot using three streaming passes."""
    if (not isinstance(checkpoint, Checkpoint) or not isinstance(expected_epoch, str)
            or not _HEX32.fullmatch(expected_epoch) or not isinstance(expected_run_id, str)
            or not _HEX32.fullmatch(expected_run_id) or type(expected_count) is not int
            or not 1 <= expected_count <= _MAX):
        raise RegistryAvailabilityEvidenceError('invalid verification request')
    try:
        scripts = cues = var_sets = 0
        active_script = active_cue = False
        fields = {}

        def state(path, attrs):
            nonlocal scripts, cues, var_sets, active_script, active_cue
            if path == ['savegame', 'md', 'script']:
                active_script = attrs.get('name') == 'X4AuthorityRegistryAvailabilitySnapshot'
                active_cue = False
                scripts += int(active_script)
            elif path == ['savegame', 'md', 'script', 'cue'] and active_script:
                active_cue = attrs.get('name') == 'State'
                cues += int(active_cue)
            elif path == ['savegame', 'md', 'script', 'cue', 'vars'] and active_script and active_cue:
                var_sets += 1
            elif path == ['savegame', 'md', 'script', 'cue', 'vars', 'value'] and active_script and active_cue:
                name = attrs.get('name')
                if name in _FIELDS:
                    if name in fields:
                        raise RegistryAvailabilityEvidenceError('duplicate snapshot field')
                    fields[name] = dict(attrs)

        _parse(checkpoint, state, pump=pump)
        if (scripts, cues, var_sets) != (1, 1, 1) or set(fields) != _FIELDS:
            raise RegistryAvailabilityEvidenceError('missing or ambiguous snapshot state')
        _integer(fields['$format'], 3)
        for name, wanted in (('$epoch', expected_epoch), ('$run_id', expected_run_id)):
            field = fields[name]
            if field.get('type') != 'string' or not _REF.fullmatch(field.get('value', '')):
                raise RegistryAvailabilityEvidenceError('invalid correlation reference')
        if fields['$epoch']['value'] == fields['$run_id']['value']:
            raise RegistryAvailabilityEvidenceError('correlation strings alias')
        _integer(fields['$issued_count'], expected_count)
        _integer(fields['$cursor'], expected_count)
        available_count = _integer(fields['$available_count'])
        unavailable_count = _integer(fields['$unavailable_count'])
        operational_count = _integer(fields['$operational_count'])
        if available_count + unavailable_count != expected_count:
            raise RegistryAvailabilityEvidenceError('availability counters disagree')
        if operational_count > available_count:
            raise RegistryAvailabilityEvidenceError('operational count exceeds available bindings')
        _integer(fields['$sealed'], 1)
        if fields['$faulted'].get('type') != 'integer' or 'value' in fields['$faulted']:
            raise RegistryAvailabilityEvidenceError('saved faulted flag is not confirmed false')

        table_names = ('$available', '$operational', '$ships', '$byship')
        table_refs = {}
        for name in table_names:
            field = fields[name]
            if field.get('type') != 'table' or not _REF.fullmatch(field.get('value', '')):
                raise RegistryAvailabilityEvidenceError('invalid table reference')
            table_refs[name] = field['value']
        if len(set(table_refs.values())) != len(table_refs):
            raise RegistryAvailabilityEvidenceError('snapshot tables alias')

        selected = {('table', ref): name for name, ref in table_refs.items()}
        selected.update({('string', fields['$epoch']['value']): '$epoch',
                         ('string', fields['$run_id']['value']): '$run_id'})
        seen = set()
        availability = {}
        operational = {}
        ships = {}
        ship_components = set()
        reverse = {}
        resolved = {'$epoch': [], '$run_id': []}
        active_group = active_ref = None
        pending = None

        def refs(path, attrs):
            nonlocal active_group, active_ref, pending
            if path == ['savegame', 'script', 'refs']:
                if active_ref and pending is not None:
                    raise RegistryAvailabilityEvidenceError('dangling selected table key')
                active_group, active_ref, pending = attrs.get('type'), None, None
            elif path == ['savegame', 'script', 'refs', 'ref']:
                if active_ref and pending is not None:
                    raise RegistryAvailabilityEvidenceError('unpaired selected table key')
                active_ref = None
                typed = (active_group, attrs.get('id'))
                if typed not in selected:
                    return
                if typed in seen:
                    raise RegistryAvailabilityEvidenceError('duplicate selected reference')
                seen.add(typed)
                name = selected[typed]
                if active_group == 'table':
                    active_ref = name
                else:
                    resolved[name].append(attrs.get('string'))
            elif len(path) == 5 and path[:4] == ['savegame', 'script', 'refs', 'ref'] and active_ref:
                tag, kind, raw = path[-1], attrs.get('type'), attrs.get('value', '')
                if tag == 'key':
                    if pending is not None:
                        raise RegistryAvailabilityEvidenceError('duplicate or unpaired table key')
                    if active_ref in ('$available', '$operational'):
                        pending = _table_index(kind, raw)
                    elif active_ref == '$ships':
                        pending = ('index', _table_index(kind, raw))
                    else:
                        if kind != 'component' or not _COMPONENT.fullmatch(raw):
                            raise RegistryAvailabilityEvidenceError('invalid reverse component key')
                        pending = ('component', _component(raw))
                elif tag == 'value':
                    if pending is None:
                        raise RegistryAvailabilityEvidenceError('table value without key')
                    key, pending = pending, None
                    if active_ref in ('$available', '$operational'):
                        if kind != 'integer' or raw not in ('', '0', '1'):
                            raise RegistryAvailabilityEvidenceError('invalid availability/operational bit')
                        table = availability if active_ref == '$available' else operational
                        if key in table:
                            raise RegistryAvailabilityEvidenceError('duplicate availability/operational index')
                        table[key] = 0 if raw == '' else int(raw)
                    elif active_ref == '$ships':
                        if kind != 'component' or not _COMPONENT.fullmatch(raw):
                            raise RegistryAvailabilityEvidenceError('invalid ship component value')
                        component = _component(raw)
                        if key[1] in ships or component in ship_components:
                            raise RegistryAvailabilityEvidenceError('duplicate ship mapping')
                        ships[key[1]] = component
                        ship_components.add(component)
                    else:
                        if kind != 'integer' or not _INTEGER.fullmatch(raw):
                            raise RegistryAvailabilityEvidenceError('invalid reverse index')
                        index = int(raw)
                        if not 1 <= index <= expected_count or key[1] in reverse:
                            raise RegistryAvailabilityEvidenceError('duplicate or invalid reverse mapping')
                        reverse[key[1]] = index
                else:
                    raise RegistryAvailabilityEvidenceError('unexpected selected table child')
            elif len(path) > 5 and path[:4] == ['savegame', 'script', 'refs', 'ref'] and active_ref:
                raise RegistryAvailabilityEvidenceError('nested selected table entry')

        _parse(checkpoint, refs, pump=pump)
        if pending is not None or seen != set(selected):
            raise RegistryAvailabilityEvidenceError('missing or incomplete selected references')
        if resolved['$epoch'] != [expected_epoch] or resolved['$run_id'] != [expected_run_id]:
            raise RegistryAvailabilityEvidenceError('correlation strings mismatch')
        expected_indices = set(range(1, expected_count + 1))
        if set(availability) != expected_indices:
            raise RegistryAvailabilityEvidenceError('availability table has gaps or extra indices')
        if set(operational) != expected_indices:
            raise RegistryAvailabilityEvidenceError('operational table has gaps or extra indices')
        available_indices = {i for i, bit in availability.items() if bit == 1}
        operational_indices = {i for i, bit in operational.items() if bit == 1}
        if len(available_indices) != available_count or expected_count - len(available_indices) != unavailable_count:
            raise RegistryAvailabilityEvidenceError('availability bits disagree with counters')
        if len(operational_indices) != operational_count or operational_indices - available_indices:
            raise RegistryAvailabilityEvidenceError('operational bits disagree with binding availability or count')
        if set(ships) != available_indices or set(reverse.values()) != available_indices:
            raise RegistryAvailabilityEvidenceError('ship tables do not match available indices')
        if len(reverse) != len(ships) or any(reverse.get(component) != index for index, component in ships.items()):
            raise RegistryAvailabilityEvidenceError('ship tables are not exact inverses')

        wanted = set(ships.values())
        found = set()
        def components(path, attrs):
            if len(path) < 3 or path[:2] != ['savegame', 'universe'] or path[-1] != 'component':
                return
            match = _COMPONENT.fullmatch(attrs.get('id', ''))
            if not match:
                return
            component = _component(attrs['id'])
            if component not in wanted:
                return
            if component in found:
                raise RegistryAvailabilityEvidenceError('duplicate saved component definition')
            if not attrs.get('class', '').startswith('ship_'):
                raise RegistryAvailabilityEvidenceError('available component is not a ship')
            found.add(component)

        _parse(checkpoint, components, pump=pump)
        if found != wanted:
            raise RegistryAvailabilityEvidenceError('missing saved ship component definition')
        bits = ''.join(str(availability[i]) for i in range(1, expected_count + 1))
        operational_bits = ''.join(str(operational[i]) for i in range(1, expected_count + 1))
        digest = hashlib.sha256(b'X4AuthorityRegistryAvailabilitySnapshot mapping v3\n')
        for index in sorted(ships):
            digest.update(f'{index}:{ships[index]}\n'.encode('ascii'))
        availability_digest = hashlib.sha256(b'X4AuthorityRegistryAvailabilitySnapshot availability v3\n')
        availability_digest.update(bits.encode('ascii'))
        operational_digest = hashlib.sha256(b'X4AuthorityRegistryAvailabilitySnapshot operational v3\n')
        operational_digest.update(operational_bits.encode('ascii'))
        return {'evidence_scope': 'saved checkpoint bytes only', 'format': 3,
                'operational_scope': 'captured saved observation only; commands must recheck live before acting',
                'epoch': expected_epoch, 'run_id': expected_run_id,
                'issued_count': expected_count, 'available_count': available_count,
                'unavailable_count': unavailable_count, 'availability_bits': bits,
                'operational_count': operational_count, 'operational_bits': operational_bits,
                'mapping_sha256': digest.hexdigest(),
                'availability_sha256': availability_digest.hexdigest(),
                'operational_sha256': operational_digest.hexdigest()}
    except _PumpCallbackError as error:
        raise error.error
    except RegistryAvailabilityEvidenceError:
        raise
    except (MarkerEvidenceError, OSError, EOFError, expat.ExpatError, zlib.error) as error:
        raise RegistryAvailabilityEvidenceError('snapshot checkpoint could not be verified') from error


def _component(raw):
    match = _COMPONENT.fullmatch(raw)
    value = int(match.group(1), 16)
    if value == 0:
        raise RegistryAvailabilityEvidenceError('null component reference')
    return format(value, 'x')
