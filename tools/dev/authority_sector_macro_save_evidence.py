#!/usr/bin/env python3
"""Check sector macro uniqueness in one pinned save, without opening X4.

This examines serialized components only. A saved macro is not established as
an X4 runtime frame identifier, a cross-instance identity, or a general rule.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
from authority.checkpoints import CheckpointStore
from authority.marker_evidence import _parse
from authority_sector_archive_provenance import _pointer
import authority_census_archive_provenance as archive

SAVED_SECTOR_COUNT = 152
_COMPONENT = re.compile(r'\[0x([0-9a-f]+)\]\Z')
_MACRO = re.compile(r'[A-Za-z0-9_.-]{1,256}\Z')


def verify(store_path=archive.DEFAULT_STORE):
    """Verify the pinned save and count distinct serialized sectors/macros.

    File/path checks are sampled, not adversarial directory-fd or ABA fences.
    No claim is made about which bytes any game process has loaded.
    """
    store_path = Path(os.path.abspath(store_path))
    before = archive.fingerprints(store_path)
    if _pointer(store_path/'CURRENT') != _pointer(store_path/'CONFIRMED'):
        raise ValueError('current checkpoint is not confirmed')
    checkpoint = CheckpointStore(store_path).latest_confirmed()
    if (checkpoint.checkpoint_id, checkpoint.sha256, checkpoint.size, checkpoint.path) != (
            archive.CHECKPOINT_ID, archive.SHA256, archive.SIZE,
            store_path/archive.CHECKPOINT_ID/'save.xml.gz'):
        raise ValueError('confirmed census checkpoint differs from pinned save')
    ids, macros = set(), set()
    count = 0
    def visit(path, attrs):
        nonlocal count
        if len(path)<3 or path[:2]!=['savegame','universe'] or path[-1]!='component': return
        if attrs.get('class')!='sector': return
        count += 1
        ident = _COMPONENT.fullmatch(attrs.get('id',''))
        macro = attrs.get('macro','')
        if not ident or not _MACRO.fullmatch(macro):
            raise ValueError('saved sector has invalid ID or macro')
        # Normalize equivalent hexadecimal IDs and conservative macro casing.
        component = int(ident.group(1),16)
        if component == 0 or component in ids: raise ValueError('duplicate or zero saved sector ID')
        folded = macro.casefold()
        if folded in macros: raise ValueError('duplicate saved sector macro')
        ids.add(component); macros.add(folded)
    _parse(checkpoint, visit)  # full gzip/XML stream and pinned compressed digest
    if count != SAVED_SECTOR_COUNT:
        raise ValueError('saved sector count differs from pinned candidate')
    if archive.fingerprints(store_path) != before:
        raise ValueError('archive changed during verification')
    return {'scope':'one pinned census checkpoint; saved universe components only',
            'checkpoint_id':checkpoint.checkpoint_id,'sha256':checkpoint.sha256,
            'saved_sectors':count,'distinct_saved_sector_ids':len(ids),
            'distinct_saved_sector_macros_casefolded':len(macros),
            'runtime_macro_binding_proven':False,'cross_instance_frame_identity_proven':False,
            'general_uniqueness_proven':False,'exact_loaded_file_proven':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store',type=Path,default=archive.DEFAULT_STORE)
    try: result=verify(parser.parse_args().store)
    except (OSError,ValueError) as error: parser.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
