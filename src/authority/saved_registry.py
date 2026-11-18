"""Read saved ship-registry status from one compressed X4 checkpoint."""
import re

from .marker_evidence import _parse
from . import registry_evidence

_HEX32 = re.compile(r'[0-9a-f]{32}\Z')
_DECIMAL_REFERENCE = re.compile(r'[1-9][0-9]{0,8}\Z')


def checkpoint_status(expected, actual):
    """Bind a first bootstrap save, then require the complete saved mapping."""
    if not isinstance(expected, tuple) or not isinstance(actual, tuple):
        raise ValueError('invalid registry status')
    if expected and expected[0] == 'bootstrap':
        if (len(expected) != 3 or len(actual) != 4 or
                actual[:3] != ('ready', expected[1], expected[2])):
            raise ValueError('checkpoint registry differs from enrollment')
    elif actual != expected:
        raise ValueError('checkpoint registry differs from recovered status')
    return actual


def saved_status(checkpoint):
    """Return initialized epoch, last index and mapping hash from saved XML."""
    script_count = cue_count = variable_set_count = state_child_count = 0
    active_registry_script = active_state_cue = False
    state_fields = {}
    state_cue_attributes = []
    state_has_text = False

    def inspect_state(path, attributes):
        nonlocal script_count, cue_count, variable_set_count, state_child_count
        nonlocal active_registry_script, active_state_cue

        if path == ['savegame', 'md', 'script']:
            active_registry_script = attributes.get('name') == 'X4AuthorityShipRegistry'
            active_state_cue = False
            script_count += int(active_registry_script)
        elif path == ['savegame', 'md', 'script', 'cue'] and active_registry_script:
            active_state_cue = attributes.get('name') == 'State'
            cue_count += int(active_state_cue)
            if active_state_cue:
                state_cue_attributes.append(dict(attributes))
        elif (len(path) > 4 and path[:4] == ['savegame', 'md', 'script', 'cue'] and
              active_registry_script and active_state_cue):
            state_child_count += 1
            if path == ['savegame', 'md', 'script', 'cue', 'vars']:
                variable_set_count += 1
            elif path == ['savegame', 'md', 'script', 'cue', 'vars', 'value']:
                name = attributes.get('name')
                if name in ('$epoch', '$last'):
                    if name in state_fields:
                        raise ValueError('duplicate registry field')
                    state_fields[name] = dict(attributes)

    def detect_state_text(path, value):
        nonlocal state_has_text
        in_state_cue = len(path) >= 4 and path[:4] == ['savegame', 'md', 'script', 'cue']
        if active_registry_script and active_state_cue and in_state_cue and value.strip():
            state_has_text = True

    _parse(checkpoint, inspect_state, characters=detect_state_text)
    if script_count == 0 and cue_count == 0:
        return ('uninitialized',)
    if (script_count, cue_count, variable_set_count, state_child_count) == (1, 1, 0, 0) and not state_has_text:
        cue_attributes = state_cue_attributes[0]
        if (set(cue_attributes) == {'id', 'name', 'state'} and
                cue_attributes.get('name') == 'State' and cue_attributes.get('state') == 'waiting' and
                _DECIMAL_REFERENCE.fullmatch(cue_attributes.get('id', ''))):
            return ('uninitialized',)
        raise ValueError('unknown uninitialized registry cue')
    if (script_count, cue_count, variable_set_count) != (1, 1, 1) or set(state_fields) != {'$epoch', '$last'}:
        raise ValueError('ambiguous saved registry')

    epoch_reference = state_fields['$epoch']
    last_index = state_fields['$last']
    if (epoch_reference.get('type') != 'string' or
            not _DECIMAL_REFERENCE.fullmatch(epoch_reference.get('value', ''))):
        raise ValueError('invalid saved epoch reference')
    if (last_index.get('type') != 'integer' or
            not _DECIMAL_REFERENCE.fullmatch(last_index.get('value', ''))):
        raise ValueError('empty or invalid saved baseline')
    entry_count = int(last_index['value'])
    if entry_count > registry_evidence.MAX_ENTRIES:
        raise ValueError('saved baseline exceeds limit')

    epoch_references = []
    inside_string_references = False

    def find_epoch(path, attributes):
        nonlocal inside_string_references
        if path == ['savegame', 'script', 'refs']:
            inside_string_references = attributes.get('type') == 'string'
        elif (path == ['savegame', 'script', 'refs', 'ref'] and inside_string_references and
              attributes.get('id') == epoch_reference['value']):
            epoch_references.append(attributes.get('string'))

    _parse(checkpoint, find_epoch)
    if (len(epoch_references) != 1 or not isinstance(epoch_references[0], str) or
            not _HEX32.fullmatch(epoch_references[0])):
        raise ValueError('missing or ambiguous saved epoch')

    epoch = epoch_references[0]
    evidence = registry_evidence.verify(
        checkpoint, epoch, entry_count, include_mapping_fingerprint=True)
    return ('ready', epoch, entry_count, evidence['mapping_sha256'])
