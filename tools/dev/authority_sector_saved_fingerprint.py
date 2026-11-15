"""Read saved fixture fingerprints; no game load or runtime binding is proven."""
from collections import Counter
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
from authority.marker_evidence import _parse
import authority_registry_save_evidence as registry
import authority_sector_reference_evidence as sector_reference

_CODE = re.compile(r'[A-Za-z0-9_-]{1,64}\Z', re.ASCII)
_MACRO = re.compile(r'[A-Za-z0-9_.-]{1,256}\Z', re.ASCII)


def verify(checkpoint, epoch):
    """Return saved fields for the validated two slots, never runtime handles.

    The existing verifier establishes the registry/fixture references and
    ancestry in the same digest-checked save. Each target code must be unique
    among serialized universe component codes, and every serialized sector
    macro must be distinct, case-insensitively. This does not establish that
    an MD getter produces a saved field, or that codes identify live objects.
    """
    sector_reference.verify(checkpoint, epoch)
    components = {}; codes = Counter(); macros = Counter(); sectors = 0
    fields = {}; fixture_script = fixture_cue = False; ancestors = []

    def visit(path, attrs):
        nonlocal sectors, fixture_script, fixture_cue
        del ancestors[len(path)-1:]
        ancestors.append((path[-1], dict(attrs) if path[-1] == 'component' else {}))
        if path == ['savegame', 'md', 'script']:
            fixture_script = attrs.get('name') == 'X4AuthoritySectorReferenceFixture'
            fixture_cue = False
        elif path == ['savegame', 'md', 'script', 'cue']:
            fixture_cue = fixture_script and attrs.get('name') == 'State'
        elif path == ['savegame', 'md', 'script', 'cue', 'vars', 'value'] and fixture_cue:
            name = attrs.get('name')
            if name in ('$index1','$index2','$ship1','$ship2','$sector1','$sector2'):
                if name in fields: raise ValueError('duplicate fixture field')
                fields[name] = dict(attrs)
        if len(path) < 3 or path[:2] != ['savegame', 'universe'] or path[-1] != 'component':
            return
        code = attrs.get('code')
        if code: codes[code.casefold()] += 1
        kind = attrs.get('class', '')
        if kind == 'sector':
            macro = attrs.get('macro', '')
            if not _MACRO.fullmatch(macro): raise ValueError('invalid saved sector macro')
            sectors += 1; macros[macro.casefold()] += 1
        if kind != 'sector' and not kind.startswith('ship_'): return
        match = registry.COMPONENT.fullmatch(attrs.get('id', ''))
        if not match: return
        ident = format(int(match.group(1), 16), 'x')
        if ident in components: raise ValueError('duplicate saved ship or sector component')
        parents = [a for tag, a in ancestors[:-1] if tag == 'component' and a.get('class') == 'sector']
        components[ident] = (dict(attrs), parents)

    _parse(checkpoint, visit)
    expected = {'$index1','$index2','$ship1','$ship2','$sector1','$sector2'}
    if set(fields) != expected or not sectors or any(n != 1 for n in macros.values()):
        raise ValueError('missing fixture fields or ambiguous sector macros')
    slots = []
    for n in (1, 2):
        index = fields[f'$index{n}']
        if (index.get('type') not in ('integer', 'largefloat') or
                index.get('value') not in ('1', '2')):
            raise ValueError('unexpected fixture index')
        ids = []
        for name in (f'$ship{n}', f'$sector{n}'):
            field = fields[name]; match = registry.COMPONENT.fullmatch(field.get('value', ''))
            if field.get('type') != 'component' or not match: raise ValueError('invalid fixture reference')
            ids.append(format(int(match.group(1), 16), 'x'))
        try: (ship, parents), (sector, _) = (components[ids[0]], components[ids[1]])
        except KeyError as error: raise ValueError('saved fixture component missing') from error
        if not ship.get('class', '').startswith('ship_') or sector.get('class') != 'sector':
            raise ValueError('invalid fixture component class')
        if len(parents) != 1 or parents[0].get('id') != sector.get('id'):
            raise ValueError('saved fixture sector ancestry differs')
        for component in (ship, sector):
            code, macro = component.get('code', ''), component.get('macro', '')
            if not _CODE.fullmatch(code) or codes[code.casefold()] != 1 or not _MACRO.fullmatch(macro):
                raise ValueError('missing, invalid or ambiguous fixture code/macro')
        slots.append({'index': int(index['value']), 'ship_saved_id': ids[0], 'sector_saved_id': ids[1],
                      'ship_code': ship['code'], 'ship_macro': ship['macro'],
                      'sector_code': sector['code'], 'sector_macro': sector['macro']})
    return {'slots': slots, 'saved_sector_count': sectors,
            'fixture_codes_unique_in_saved_universe': True,
            'sector_macros_unique_in_saved_universe': True,
            'runtime_binding_proven': False, 'cross_process_identity_proven': False,
            'exact_loaded_file_proven': False}
