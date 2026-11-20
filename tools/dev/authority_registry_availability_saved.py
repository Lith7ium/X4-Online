"""Read-only parser for the saved availability diagnostic cue.

A successful result describes bytes in one verified checkpoint only. It does not
prove runtime observation, object destruction, recovery, or game behavior.
"""
import re
import zlib
from xml.parsers import expat

from authority.checkpoints import Checkpoint
from authority.marker_evidence import _parse, MarkerEvidenceError


class AvailabilitySavedError(ValueError):
    """Saved diagnostic data is missing, ambiguous, malformed, or mismatched."""


_HEX = re.compile(r'[0-9a-f]{32}\Z')
_DECIMAL = re.compile(r'[1-9][0-9]{0,8}\Z')
_FIELDS = {
    '$format', '$epoch', '$run_id', '$issued_count', '$count', '$sealed', '$faulted',
    '$forward_present', '$object_exists', '$is_ship', '$is_operational', '$reverse_matches',
}
_TABLE_FIELDS = ('$forward_present', '$object_exists', '$is_ship', '$is_operational', '$reverse_matches')


def _integer(field, wanted=None, *, allow_zero=False):
    if field.get('type') != 'integer':
        raise AvailabilitySavedError('invalid integer field')
    raw = field.get('value')
    if raw is None and allow_zero:
        value = 0
    elif raw is not None and re.fullmatch(r'0|[1-9][0-9]*', raw):
        value = int(raw)
    else:
        raise AvailabilitySavedError('invalid integer value')
    if wanted is not None and value != wanted:
        raise AvailabilitySavedError('unexpected integer value')
    return value


def verify(checkpoint, expected_epoch, expected_run_id, expected_issued_count, expected_indices):
    """Return targeted cue observations from saved bytes after strict checks.

    Unrelated cue variables and unrelated save references are outside this schema.
    """
    indices = tuple(expected_indices) if isinstance(expected_indices, (list, tuple)) else ()
    if (not isinstance(checkpoint, Checkpoint) or not isinstance(expected_epoch, str)
            or not _HEX.fullmatch(expected_epoch) or not isinstance(expected_run_id, str)
            or not _HEX.fullmatch(expected_run_id) or type(expected_issued_count) is not int
            or not 1 <= expected_issued_count <= 200000 or not 1 <= len(indices) <= 16
            or any(type(i) is not int or not 1 <= i <= expected_issued_count for i in indices)
            or len(set(indices)) != len(indices)):
        raise AvailabilitySavedError('invalid expected availability request')

    scripts = cues = var_sets = 0
    active_script = active_cue = False
    fields = {}

    def state(path, attrs):
        nonlocal scripts, cues, var_sets, active_script, active_cue
        if path == ['savegame', 'md', 'script']:
            active_script = attrs.get('name') == 'X4AuthorityRegistryAvailabilityProbe'
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
                    raise AvailabilitySavedError('duplicate diagnostic field')
                fields[name] = dict(attrs)

    try:
        _parse(checkpoint, state)
        if (scripts, cues, var_sets) != (1, 1, 1) or set(fields) != _FIELDS:
            raise AvailabilitySavedError('missing or ambiguous diagnostic state')
        _integer(fields['$format'], 1)
        for name in ('$epoch', '$run_id'):
            field = fields[name]
            if field.get('type') != 'string' or not _DECIMAL.fullmatch(field.get('value', '')):
                raise AvailabilitySavedError('invalid correlation reference')
        _integer(fields['$issued_count'], expected_issued_count)
        if _integer(fields['$count']) != len(indices):
            raise AvailabilitySavedError('observation count mismatch')
        _integer(fields['$sealed'], 1)
        if fields['$faulted'].get('type') != 'integer' or 'value' in fields['$faulted']:
            raise AvailabilitySavedError('saved faulted flag is not confirmed false')
        table_refs = {}
        for name in _TABLE_FIELDS:
            field = fields[name]
            if field.get('type') != 'table' or not _DECIMAL.fullmatch(field.get('value', '')):
                raise AvailabilitySavedError('invalid observation table reference')
            table_refs[name] = field['value']
        refs = list(table_refs.values()) + [fields['$epoch']['value'], fields['$run_id']['value']]
        if len(set(table_refs.values())) != len(table_refs) or len(set(refs)) != len(refs):
            raise AvailabilitySavedError('aliased diagnostic references')

        values = {name: {} for name in _TABLE_FIELDS}
        resolved = {'$epoch': [], '$run_id': []}
        active_group = active_ref = None
        selected_refs = {ref: ('table', name) for name, ref in table_refs.items()}
        selected_refs[fields['$epoch']['value']] = ('string', '$epoch')
        selected_refs[fields['$run_id']['value']] = ('string', '$run_id')
        seen_selected = set()
        pending = None

        def refs_cb(path, attrs):
            nonlocal active_group, active_ref, pending
            if path == ['savegame', 'script', 'refs']:
                if active_ref is not None and pending is not None:
                    raise AvailabilitySavedError('dangling selected table key')
                active_group = attrs.get('type')
                active_ref = None
                pending = None
            elif path == ['savegame', 'script', 'refs', 'ref']:
                if active_ref is not None and pending is not None:
                    raise AvailabilitySavedError('unpaired selected table key')
                active_ref = None
                ref_id = attrs.get('id')
                if ref_id not in selected_refs:
                    return
                if ref_id in seen_selected:
                    raise AvailabilitySavedError('duplicate selected reference id')
                seen_selected.add(ref_id)
                expected_type, name = selected_refs[ref_id]
                if active_group != expected_type:
                    raise AvailabilitySavedError('selected reference in wrong group')
                if expected_type == 'table':
                    active_ref = name
                else:
                    resolved[name].append(attrs.get('string'))
            elif len(path) == 5 and path[:4] == ['savegame', 'script', 'refs', 'ref'] and active_ref:
                tag, kind, raw = path[-1], attrs.get('type'), attrs.get('value', '')
                if tag == 'key':
                    if pending is not None or kind != 'integer' or not _DECIMAL.fullmatch(raw):
                        raise AvailabilitySavedError('invalid or duplicate table key')
                    pending = int(raw)
                elif tag == 'value':
                    if pending is None or kind != 'integer' or raw not in ('', '0', '1'):
                        raise AvailabilitySavedError('invalid table boolean')
                    value = 0 if raw == '' else int(raw)
                    table = values[active_ref]
                    if pending in table or len(table) >= 16:
                        raise AvailabilitySavedError('duplicate or excess observation key')
                    table[pending] = bool(value)
                    pending = None
                else:
                    raise AvailabilitySavedError('unexpected table child')
            elif len(path) > 5 and path[:4] == ['savegame', 'script', 'refs', 'ref'] and active_ref:
                raise AvailabilitySavedError('nested table entry')

        _parse(checkpoint, refs_cb)
        if (pending is not None or seen_selected != set(selected_refs)
                or resolved['$epoch'] != [expected_epoch] or resolved['$run_id'] != [expected_run_id]):
            raise AvailabilitySavedError('missing or mismatched correlation strings')
        expected = set(indices)
        if any(set(table) != expected for table in values.values()):
            raise AvailabilitySavedError('observation tables have different or unexpected indices')
        return {
            'evidence_scope': 'saved checkpoint bytes only; no runtime, destruction, or recovery proof',
            'epoch': expected_epoch,
            'run_id': expected_run_id,
            'issued_count': expected_issued_count,
            'count': len(indices),
            'sealed': True,
            'faulted': False,
            'rows': [
                {'index': index, **{name[1:]: values[name][index] for name in _TABLE_FIELDS}}
                for index in sorted(indices)
            ],
        }
    except AvailabilitySavedError:
        raise
    except (MarkerEvidenceError, OSError, EOFError, expat.ExpatError, zlib.error) as exc:
        raise AvailabilitySavedError('saved availability data could not be verified') from exc
