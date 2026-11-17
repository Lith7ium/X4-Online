#!/usr/bin/env python3
"""Read-only structural evidence for one experimental ship registry checkpoint.

Checks the saved bidirectional registry and referenced X4 ship components. It
cannot establish which object a separate running X4 instance resolved, complete
universe coverage, or correct multiplayer behavior. No X4 process is started.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from xml.parsers import expat
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from authority.checkpoints import Checkpoint, CheckpointStore
from authority.marker_evidence import _parse, MarkerEvidenceError

DECIMAL = re.compile(r'[1-9][0-9]{0,8}\Z')
COMPONENT = re.compile(r'\[0x([0-9a-f]+)\]\Z')
EPOCH = re.compile(r'[0-9a-f]{32}\Z')
MAX_ENTRIES = 200000


class RegistryEvidenceError(ValueError):
    """The checkpoint registry is missing, ambiguous, or inconsistent."""


def verify(checkpoint, expected_epoch, expected_count, *, expected_rows=None,
           include_sector_parents=False, include_mapping_fingerprint=False,
           expected_components=None):
    if (not isinstance(checkpoint, Checkpoint) or not isinstance(expected_epoch, str)
            or not EPOCH.fullmatch(expected_epoch) or type(expected_count) is not int
            or not 1 <= expected_count <= MAX_ENTRIES):
        raise RegistryEvidenceError('invalid verification request')
    if type(include_mapping_fingerprint) is not bool:
        raise RegistryEvidenceError('invalid mapping fingerprint option')
    if expected_components is not None:
        if (type(expected_components) is not dict or not expected_components
                or any(type(index) is not int or not 1 <= index <= expected_count
                       or type(component) is not str
                       or not re.fullmatch(r'[1-9a-f][0-9a-f]{0,15}', component)
                       for index, component in expected_components.items())
                or len(set(expected_components.values())) != len(expected_components)):
            raise RegistryEvidenceError('invalid expected component mapping')
    if expected_rows is not None:
        if (not isinstance(expected_rows, (list, tuple)) or len(expected_rows) != expected_count
                or any(not isinstance(row, tuple) or len(row) != 2 or type(row[0]) is not int
                       or row[0] != i or not isinstance(row[1], str) or not row[1]
                       for i, row in enumerate(expected_rows, 1))):
            raise RegistryEvidenceError('invalid expected macro rows')
    script_count = cue_count = variable_set_count = 0
    active_script = active_cue = False
    fields = {}

    def find_state(path, attrs):
        nonlocal script_count, cue_count, variable_set_count, active_script, active_cue
        if path == ['savegame', 'md', 'script']:
            active_script = attrs.get('name') == 'X4AuthorityShipRegistry'
            active_cue = False
            if active_script:
                script_count += 1
        elif path == ['savegame', 'md', 'script', 'cue'] and active_script:
            active_cue = attrs.get('name') == 'State'
            if active_cue:
                cue_count += 1
        elif path == ['savegame', 'md', 'script', 'cue', 'vars'] and active_script and active_cue:
            variable_set_count += 1
        elif path == ['savegame', 'md', 'script', 'cue', 'vars', 'value'] and active_script and active_cue:
            name = attrs.get('name')
            if name in ('$ships', '$byship', '$last', '$epoch', '$faulted'):
                if name in fields:
                    raise RegistryEvidenceError('duplicate registry field')
                fields[name] = dict(attrs)

    try:
        _parse(checkpoint, find_state)
        if ((script_count, cue_count, variable_set_count) != (1, 1, 1)
                or set(fields) != {'$ships', '$byship', '$last', '$epoch', '$faulted'}):
            raise RegistryEvidenceError('missing or ambiguous state')
        for name, field_type in (('$ships', 'table'), ('$byship', 'table'), ('$epoch', 'string')):
            field = fields[name]
            if field.get('type') != field_type or not DECIMAL.fullmatch(field.get('value', '')):
                raise RegistryEvidenceError('invalid state reference')
        if (fields['$last'].get('type') != 'integer' or fields['$last'].get('value') != str(expected_count)
                or fields['$faulted'].get('type') != 'integer' or 'value' in fields['$faulted']):
            raise RegistryEvidenceError('invalid count or faulted registry')
        forward_ref = fields['$ships']['value']
        reverse_ref = fields['$byship']['value']
        epoch_ref = fields['$epoch']['value']
        if forward_ref == reverse_ref:
            raise RegistryEvidenceError('registry tables alias')
        group = active = None
        seen = {'forward': 0, 'reverse': 0, 'epoch': 0}
        pending = None
        forward = {}
        reverse = {}
        epoch_value = None

        def collect(path, attrs):
            nonlocal group, active, pending, epoch_value
            if path == ['savegame', 'script', 'refs']:
                if pending is not None:
                    raise RegistryEvidenceError('dangling table key')
                group = attrs.get('type')
                active = None
                pending = None
            elif path == ['savegame', 'script', 'refs', 'ref']:
                if pending is not None:
                    raise RegistryEvidenceError('dangling table key')
                reference = attrs.get('id')
                active = None
                if group == 'table' and reference == forward_ref:
                    active = 'forward'
                elif group == 'table' and reference == reverse_ref:
                    active = 'reverse'
                elif group == 'string' and reference == epoch_ref:
                    active = 'epoch'
                if active:
                    seen[active] += 1
                    if seen[active] != 1:
                        raise RegistryEvidenceError('duplicate table reference')
                    if active == 'epoch':
                        epoch_value = attrs.get('string')
            elif (len(path) == 5 and path[:4] == ['savegame', 'script', 'refs', 'ref']
                  and active in ('forward', 'reverse')):
                tag = path[-1]
                value_type = attrs.get('type')
                value = attrs.get('value', '')
                if tag == 'key':
                    if pending is not None:
                        raise RegistryEvidenceError('unpaired key')
                    pending = (value_type, value)
                elif tag == 'value':
                    if pending is None:
                        raise RegistryEvidenceError('value without key')
                    key_type, key_value = pending
                    pending = None
                    if active == 'forward':
                        index_type, index_value, component_type, component_value = key_type, key_value, value_type, value
                    else:
                        component_type, component_value, index_type, index_value = key_type, key_value, value_type, value
                    if (index_type != 'integer' or not DECIMAL.fullmatch(index_value)
                            or component_type != 'component' or not COMPONENT.fullmatch(component_value)):
                        raise RegistryEvidenceError('unexpected table entry')
                    index = int(index_value)
                    component = COMPONENT.fullmatch(component_value).group(1)
                    # Canonicalize the hex representation before duplicate checks.
                    component = format(int(component, 16), 'x')
                    table = forward if active == 'forward' else reverse
                    key = index if active == 'forward' else component
                    table_value = component if active == 'forward' else index
                    if key in table or len(table) >= expected_count:
                        raise RegistryEvidenceError('duplicate or excess table entry')
                    table[key] = table_value
                else:
                    raise RegistryEvidenceError('unexpected table child')
            elif len(path) > 5 and path[:4] == ['savegame', 'script', 'refs', 'ref'] and active in ('forward', 'reverse'):
                raise RegistryEvidenceError('nested table element')

        _parse(checkpoint, collect)
        if pending is not None or seen != {'forward': 1, 'reverse': 1, 'epoch': 1} or epoch_value != expected_epoch:
            raise RegistryEvidenceError('missing or inconsistent references or epoch')
        if (len(forward) != expected_count or len(reverse) != expected_count
                or set(forward) != set(range(1, expected_count + 1))):
            raise RegistryEvidenceError('incomplete table')
        if (len(set(forward.values())) != expected_count
                or any(reverse.get(component) != index for index, component in forward.items())):
            raise RegistryEvidenceError('tables are not one-to-one inverses')
        if expected_components is not None and any(
                forward.get(index) != component for index, component in expected_components.items()):
            raise RegistryEvidenceError('saved component mapping differs from expected')
        if type(include_sector_parents) is not bool:
            raise RegistryEvidenceError('invalid sector analysis option')
        wanted = set(forward.values())
        found = {}
        ancestors = []
        sectors = set()
        sector_found = zone_found = non_zone_parent = docked = 0

        def components(path, attrs):
            nonlocal sector_found, zone_found, non_zone_parent, docked
            if include_sector_parents:
                del ancestors[len(path) - 1:]
                ancestors.append((path[-1], dict(attrs) if path[-1] == 'component' else {}))
            if len(path) < 3 or path[:2] != ['savegame', 'universe'] or path[-1] != 'component':
                return
            match = COMPONENT.fullmatch(attrs.get('id', ''))
            if not match:
                return
            component_id = format(int(match.group(1), 16), 'x')
            if component_id not in wanted:
                return
            if component_id in found:
                raise RegistryEvidenceError('duplicate component id')
            component_class = attrs.get('class', '')
            macro = attrs.get('macro', '')
            if not component_class.startswith('ship_') or not macro:
                raise RegistryEvidenceError('registered object is not a saved ship component')
            found[component_id] = macro
            if include_sector_parents:
                parent_components = [parent for tag, parent in ancestors[:-1] if tag == 'component']
                sector_parents = [parent for parent in parent_components if parent.get('class') == 'sector']
                if len(sector_parents) > 1:
                    raise RegistryEvidenceError('ambiguous sector parent')
                if sector_parents:
                    sector_id = COMPONENT.fullmatch(sector_parents[0].get('id', ''))
                    if not sector_id:
                        raise RegistryEvidenceError('invalid sector parent identity')
                    sectors.add(format(int(sector_id.group(1), 16), 'x'))
                    sector_found += 1
                if any(parent.get('class') == 'zone' for parent in parent_components):
                    zone_found += 1
                if not parent_components or parent_components[-1].get('class') != 'zone':
                    non_zone_parent += 1
                if any(parent.get('class') == 'dockingbay' for parent in parent_components):
                    docked += 1

        _parse(checkpoint, components)
        if len(found) != expected_count:
            raise RegistryEvidenceError('registered components missing')
        if expected_rows is not None and any(found[forward[index]] != macro for index, macro in expected_rows):
            raise RegistryEvidenceError('saved component macro differs from observed index')
        result = {'macro_rows_checked': expected_rows is not None, 'count': expected_count,
                  'unique_saved_components': len(found), 'distinct_macros': len(set(found.values())),
                  'forward_reverse_match': True, 'runtime_binding_proven': False, 'universe_coverage_proven': False}
        if include_mapping_fingerprint:
            digest = hashlib.sha256(b'X4AuthorityShipRegistry mapping v1\n')
            for index in range(1, expected_count + 1):
                digest.update(f'{index}:{forward[index]}\n'.encode('ascii'))
            result['mapping_sha256'] = digest.hexdigest()
        if include_sector_parents:
            result.update(saved_sector_ancestor_count=len(sectors), ships_with_sector_ancestor=sector_found,
                          ships_without_sector_ancestor=expected_count - sector_found, ships_with_zone_ancestor=zone_found,
                          ships_with_non_zone_component_parent=non_zone_parent, ships_under_dockingbay=docked,
                          sector_runtime_mapping_proven=False, position_or_velocity_proven=False)
        return result
    except RegistryEvidenceError:
        raise
    except (OSError, EOFError, expat.ExpatError, zlib.error, MarkerEvidenceError) as error:
        raise RegistryEvidenceError('checkpoint could not be verified') from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', required=True, type=Path)
    parser.add_argument('--expected-epoch', required=True)
    parser.add_argument('--expected-count', required=True, type=int)
    parser.add_argument('--server-log', type=Path)
    parser.add_argument('--client-log', type=Path)
    parser.add_argument('--sector-parents', action='store_true',
                        help='inspect saved component ancestry; no runtime mapping claim')
    args = parser.parse_args()
    if bool(args.server_log) != bool(args.client_log):
        parser.error('both logs must be supplied together')
    try:
        rows = None
        if args.server_log:
            from authority_registry_census_live import observations
            rows, _ = observations(args.server_log, 'save', args.expected_count, args.expected_epoch)
            client, _ = observations(args.client_log, 'load', args.expected_count, args.expected_epoch)
            if rows != client:
                raise RegistryEvidenceError('server and client macro rows differ')
        checkpoint = CheckpointStore(args.store).latest_confirmed()
        result = verify(checkpoint, args.expected_epoch, args.expected_count, expected_rows=rows,
                        include_sector_parents=args.sector_parents)
    except (OSError, ValueError) as error:
        parser.exit(1, 'REFUSED: ' + str(error) + '\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
