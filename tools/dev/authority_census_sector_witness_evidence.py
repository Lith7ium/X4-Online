#!/usr/bin/env python3
"""Find saved registry witnesses by sector in the pinned census save.

Read-only, offline and save-structural only: no runtime or cross-process handle
is inferred. The verified archive and two additional digest-checked streams
are bounded and can cover either one or all recorded sectors.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
from authority.checkpoints import CheckpointStore
from authority.marker_evidence import _parse
import authority_census_archive_provenance as archive
import authority_registry_save_evidence as registry
from authority_sector_archive_provenance import _pointer

_MACRO=re.compile(r'[A-Za-z0-9_.-]{1,128}\Z',re.ASCII)
_COMPONENT=re.compile(r'\[0x([0-9a-f]+)\]\Z',re.ASCII)
_ANY_COMPONENT=re.compile(r'\[0[xX]([0-9a-fA-F]+)\]\Z',re.ASCII)
_DECIMAL=re.compile(r'[1-9][0-9]{0,8}\Z',re.ASCII)
_MAX_SHIPS=200000
_SAVED_SECTORS=152


def _component(value):
    match=_COMPONENT.fullmatch(value or '')
    if not match:raise ValueError('invalid saved component reference')
    digits=match.group(1).lstrip('0')
    if not digits or len(digits)>16:raise ValueError('invalid saved component reference')
    return digits


def _extract(checkpoint,macro,count,sector_count=_SAVED_SECTORS):
    """Join one verified forward table with saved component ancestry.

    Caller must independently verify the checkpoint marker, epoch and complete
    forward/reverse bijection in the same pinned bytes before calling this.
    """
    if macro is not None and (not isinstance(macro,str) or not _MACRO.fullmatch(macro)):
        raise ValueError('invalid requested sector macro')
    if type(count) is not int or count<1 or count>_MAX_SHIPS:raise ValueError('invalid registry count')
    ancestry=[];seen_macros=set();sectors_by_id={};ships={};forward_ref=None
    selected=None;scripts=cues=vars_count=fields=0;active_script=active_cue=False
    def first(path,attrs):
        nonlocal selected,forward_ref,scripts,cues,vars_count,fields,active_script,active_cue
        del ancestry[len(path)-1:]
        ancestry.append((path[-1],dict(attrs) if path[-1]=='component' else {}))
        if path==['savegame','md','script']:
            active_script=attrs.get('name')=='X4AuthorityShipRegistry';active_cue=False
            if active_script:scripts+=1
        elif path==['savegame','md','script','cue'] and active_script:
            active_cue=attrs.get('name')=='State'
            if active_cue:cues+=1
        elif path==['savegame','md','script','cue','vars'] and active_script and active_cue:vars_count+=1
        elif path==['savegame','md','script','cue','vars','value'] and active_script and active_cue and attrs.get('name')=='$ships':
            fields+=1
            if attrs.get('type')!='table' or not _DECIMAL.fullmatch(attrs.get('value','')):raise ValueError('invalid forward reference')
            forward_ref=attrs['value']
        if len(path)<3 or path[:2]!=['savegame','universe'] or path[-1]!='component':return
        cls=attrs.get('class','')
        if cls=='sector':
            ident=_component(attrs.get('id'));name=attrs.get('macro','')
            if not _MACRO.fullmatch(name) or ident in sectors_by_id or name.casefold() in seen_macros:
                raise ValueError('ambiguous saved sector ID or macro')
            sectors_by_id[ident]=name;seen_macros.add(name.casefold())
            if name==macro:
                if selected is not None:raise ValueError('duplicate selected sector')
                selected=ident
        if not cls.startswith('ship_'):return
        parents=[a for tag,a in ancestry[:-1] if tag=='component']
        sectors=[a for a in parents if a.get('class')=='sector']
        if len(sectors)>1:raise ValueError('ambiguous saved sector ancestry')
        if not sectors or (macro is not None and sectors[0].get('macro')!=macro):return
        ident=_component(attrs.get('id'))
        if ident in ships or len(ships)>=_MAX_SHIPS:raise ValueError('duplicate or excessive saved ships')
        ships[ident]=(_component(sectors[0].get('id')),
                      any(a.get('class')=='dockingbay' for a in parents),
                      bool(parents and parents[-1].get('class')=='zone'))
    _parse(checkpoint,first)
    if ((scripts,cues,vars_count,fields)!=(1,1,1,1) or (macro is not None and selected is None)
            or len(sectors_by_id)!=sector_count):
        raise ValueError('missing or ambiguous registry or selected sector')
    group=active=None;matches=0;pending=None;forward={};values=set()
    sector_counts=dict.fromkeys(sectors_by_id if macro is None else (selected,),0)
    ship_counts=dict.fromkeys(ships,0)
    def second(path,attrs):
        nonlocal group,active,matches,pending
        if path==['savegame','script','refs']:
            if pending is not None:raise ValueError('dangling registry key')
            group=attrs.get('type');active=None
        elif path==['savegame','script','refs','ref']:
            if pending is not None:raise ValueError('dangling registry key')
            active=group=='table' and attrs.get('id')==forward_ref
            if active:
                matches+=1
                if matches!=1:raise ValueError('duplicate forward table')
        elif len(path)==5 and path[:4]==['savegame','script','refs','ref'] and active:
            if path[-1]=='key':
                if pending is not None:raise ValueError('duplicate registry key')
                pending=(attrs.get('type'),attrs.get('value',''))
            elif path[-1]=='value':
                if pending is None:raise ValueError('unpaired registry value')
                typ,value=pending;pending=None
                if typ!='integer' or not _DECIMAL.fullmatch(value) or attrs.get('type')!='component':
                    raise ValueError('invalid registry mapping')
                index=int(value);ident=_component(attrs.get('value'))
                if index in forward or ident in values or len(forward)>=count:raise ValueError('duplicate or excessive registry mapping')
                forward[index]=ident;values.add(ident)
            else:raise ValueError('unexpected registry element')
        elif len(path)>5 and path[:4]==['savegame','script','refs','ref'] and active:
            raise ValueError('nested registry element')
        if len(path)>=3 and path[:2]==['savegame','universe'] and path[-1]=='component':
            value=attrs.get('id','');match=_ANY_COMPONENT.fullmatch(value)
            if match:
                ident=match.group(1).lstrip('0').lower()
                if ident in sector_counts:
                    sector_counts[ident]+=1
                    if attrs.get('class')!='sector' or attrs.get('macro')!=sectors_by_id[ident]:
                        raise ValueError('saved sector ID collides with another component')
                if ident in ship_counts:ship_counts[ident]+=1
    _parse(checkpoint,second)
    if (pending is not None or matches!=1 or len(forward)!=count or set(forward)!=set(range(1,count+1))
            or any(n!=1 for n in sector_counts.values())):
        raise ValueError('missing or inconsistent saved references')
    grouped={ident:[] for ident in sector_counts}
    for index,ident in sorted(forward.items()):
        if ident not in ships:continue
        if ship_counts[ident]!=1:raise ValueError('saved witness component ID is ambiguous')
        sector,docked,zone=ships[ident]
        if sector not in grouped:raise ValueError('saved witness sector missing')
        grouped[sector].append({'index':index,'saved_under_dockingbay':docked,'saved_immediate_parent_zone':zone})
    common={'saved_sector_count':len(sectors_by_id),'saved_registry_count':count,
            'runtime_binding_proven':False,'cross_instance_frame_identity_proven':False,'exact_loaded_file_proven':False}
    if macro is not None:
        if not grouped[selected]:raise ValueError('no saved registry witness in requested sector')
        return dict(common,sector_macro=macro,sector_saved_component_ref='[0x'+selected+']',witnesses=grouped[selected])
    rows=[{'sector_macro':name,'sector_saved_component_ref':'[0x'+ident+']','witnesses':grouped[ident]}
          for ident,name in sorted(sectors_by_id.items(),key=lambda item:item[1].casefold())]
    return dict(common,sectors=rows,registry_entries_without_sector_witness=count-sum(len(v) for v in grouped.values()))


def _verify(store_path,macro):
    store=Path(os.path.abspath(store_path));before=archive.fingerprints(store)
    source=archive.verify(store)
    if _pointer(store/'CURRENT')!=_pointer(store/'CONFIRMED'):raise ValueError('current checkpoint is not confirmed')
    checkpoint=CheckpointStore(store).latest_confirmed()
    if (checkpoint.checkpoint_id,checkpoint.sha256,checkpoint.size,checkpoint.path)!=(
        archive.CHECKPOINT_ID,archive.SHA256,archive.SIZE,store/archive.CHECKPOINT_ID/'save.xml.gz'):
        raise ValueError('confirmed census checkpoint differs')
    result=_extract(checkpoint,macro,archive.COUNT)
    if archive.fingerprints(store)!=before:raise ValueError('archive changed during witness extraction')
    result.update(scope='one pinned census checkpoint; saved structural evidence only',
                  checkpoint_id=source['checkpoint_id'],sha256=source['sha256'],registry_epoch=source['registry_epoch'])
    return result


def verify(store_path,macro):
    if not isinstance(macro,str) or not _MACRO.fullmatch(macro):raise ValueError('invalid requested sector macro')
    return _verify(store_path,macro)


def verify_all(store_path):
    """Return all saved sectors with bounded candidate registry indices."""
    return _verify(store_path,None)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store',type=Path,default=archive.DEFAULT_STORE)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--sector-macro')
    group.add_argument('--all',action='store_true')
    args=parser.parse_args()
    try:result=verify_all(args.store) if args.all else verify(args.store,args.sector_macro)
    except (OSError,ValueError) as error:parser.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
