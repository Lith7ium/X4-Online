#!/usr/bin/env python3
"""Opt-in disposable one-X4 sector-create diagnostic; import starts nothing."""
import argparse
import json
import math
from pathlib import Path
import re
import secrets
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
from authority.checkpoints import CheckpointStore
import authority_sector_read_live as base
import authority_sector_saved_fingerprint as saved
import authority_job_attach_live as job_attach

TAG='[X4LAN] AUTH_SECTOR_CREATE '
MACRO=re.compile(r'[A-Za-z0-9_.-]{1,128}\Z',re.ASCII)
ROW=re.compile(r'ROW index=([34]) stage=(create|replay|final) macro=([A-Za-z0-9_.-]{1,128}) location=(local|remote) x=('+base.NUMBER+r') y=('+base.NUMBER+r') z=('+base.NUMBER+r') count=([0-9]+) game=('+base.NUMBER+r')\Z',re.ASCII)
DONE=re.compile(r'DONE game=('+base.NUMBER+r')\Z',re.ASCII)
_base_install=base.install
_base_check=base.check_log_bytes
_base_fault=base.fault_log


def once(text,old,new):
    if text.count(old)!=1: raise ValueError('missing or ambiguous private overlay hook')
    return text.replace(old,new)


def install(case,profile,ticket,slot,nonce,macros):
    if (slot!=2 or not re.fullmatch(r'[0-9a-f]{32}',nonce) or len(macros)!=2 or
        any(not isinstance(v,str) or not MACRO.fullmatch(v) or v in ('nil','null') for v in macros) or
        macros[0].casefold()==macros[1].casefold()): raise ValueError('invalid create experiment config')
    protected=_base_install(case,profile,ticket,slot)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    mdpaths=[]
    for src,dest in (('authority_sector_create_receiver.xml','authority_ship_create_receiver.xml'),
                     ('authority_sector_create_inspect.xml','authority_sector_create_inspect.xml')):
        path=md/dest;shutil.copyfile(ROOT/'tools/dev'/src,path);mdpaths.append(path)
    shutil.copyfile(ROOT/'src/authority/lua/x4_ship_engine.lua',ui/'x4_ship_engine.lua')
    for src,var in (('authority_sector_create_driver.lua','X4LAN_SECTOR_CREATE_DRIVER'),
                    ('authority_sector_create_owner.lua','X4LAN_SECTOR_CREATE_OWNER')):
        text=(ROOT/'tools/dev'/src).read_text()
        if src=='authority_sector_create_owner.lua':
            text=once(text," local function fail() state='failed';return false end",
                " local function fail() if state~='failed' then DebugError('[X4LAN] AUTH_SECTOR_CREATE ERROR owner') end;state='failed';return false end")
        text=once(text,'return M\n',var+'=M\nreturn M\n')
        (ui/src).write_text(text)
    shutil.copyfile(ROOT/'tools/dev/authority_sector_create_run.lua',ui/'authority_sector_create_run.lua')
    cfg=ui/'config.lua';text=cfg.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('unexpected config')
    cfg.write_text(text[:-2]+',authority_sector_create_run=true,authority_sector_create_nonce="'+nonce+
        '",authority_sector_create_deadline=90,authority_sector_create_macros={'+','.join('"'+v+'"' for v in macros)+'}}\n',encoding='ascii')
    cfg.chmod(0o600)
    manifest=lab/'ui.xml';text=manifest.read_text();hook='    <file name="ui/authority_download_load_probe.lua" />\n'
    names=('x4_ship_engine.lua','authority_sector_create_driver.lua','authority_sector_create_owner.lua','authority_sector_create_run.lua')
    manifest.write_text(once(text,hook,''.join('    <file name="ui/'+name+'" />\n' for name in names)+hook))
    owner=ui/'authority_download_load_probe.lua';text=owner.read_text();hook=" if state=='done' then return end\n"
    owner.write_text(once(text,hook," if state=='done' then X4LAN_SECTOR_CREATE_RUN_TICK();return end\n"))
    if {p.name for p in md.iterdir()}!=set((*base.MD,'authority_sector_read_guard.xml',*(p.name for p in mdpaths))):
        raise ValueError('unexpected private MD scripts')
    return protected+mdpaths+[ui/name for name in names]


def fault_log(raw):
    lowered=raw.lower()
    return (_base_fault(raw) or (TAG+'ERROR ').lower().encode() in lowered or
        b'could not find suitable data type for conversion!' in lowered or b'invalid data types for arithmetic operation!' in lowered)


def validate(raw,ticket,slot,macros,partial=False):
    if fault_log(raw): raise ValueError('X4 or create probe fault')
    observed=_base_check(raw,ticket,slot,partial=partial)
    if observed is None:return None
    lines=raw.decode('utf-8').splitlines();pause=base.load.TAG.decode()+'pause_observed|'
    pauses=[i for i,line in enumerate(lines) if pause in line]
    positions=[i for i,line in enumerate(lines) if TAG in line]
    if positions and (len(pauses)!=1 or positions[0]<=pauses[0]): raise ValueError('create before confirmed pause')
    rows=[lines[i].split(TAG,1)[1].strip() for i in positions]
    if len(rows)>8: raise ValueError('duplicated create receipts')
    expected=((3,'create'),(3,'replay'),(4,'create'),(4,'replay'),(3,'final'),(4,'final'))
    parsed=[];baseline=None;locations={}
    for i,row in enumerate(rows[:6]):
        m=ROW.fullmatch(row)
        if not m or (int(m[1]),m[2])!=expected[i] or m[3]!=macros[int(m[1])-3]: raise ValueError('invalid create row')
        coords=[float(m[j]) for j in (5,6,7)];game=float(m[9]);count=int(m[8])
        if (not all(math.isfinite(x) for x in (*coords,game)) or game!=observed['reported_game_time'] or
            any(abs(a-b)>2 for a,b in zip(coords,(-400,100000,500)))): raise ValueError('invalid create pose or time')
        if baseline is None: baseline=count-1
        if baseline<0 or count!=baseline+(1 if i<2 else 2): raise ValueError('invalid candidate counts')
        index=int(m[1]);loc=m[4]
        if index in locations and locations[index]!=loc: raise ValueError('sector relationship changed')
        locations[index]=loc
        parsed.append(dict(index=index,stage=m[2],sector_macro=m[3],location=loc,position=coords,count=count))
    if len(rows)<8:
        if len(rows)==7 and rows[6]!='PENDING': raise ValueError('invalid pending receipt')
        if partial:return None
        raise ValueError('incomplete create receipts')
    if rows[6]!='PENDING': raise ValueError('missing pending fence')
    match=DONE.fullmatch(rows[7])
    if not match or float(match[1])!=observed['reported_game_time'] or 'remote' not in locations.values():
        raise ValueError('invalid completion or missing remote sector')
    observed.update(created_records=parsed,baseline_candidate_count=baseline,at_least_one_remote_sector=True,
        completion_receipt_preceded_owned_cleanup=True,complete_world_coverage=False,independent_md_reads_proven=False,
        client_identity_proven=False,exact_position_transfer_proven=False,collision_free_proven=False)
    return observed


def finalize_result(result,store,before):
    result.update(scope='one paused isolated Linux X4; two-sector synthetic create and replay; no client or gameplay',
        complete_world_coverage=False,client_identity_proven=False,collision_free_proven=False,checkpoint_requested=False)
    if result.get('success') and base.archive._path_fingerprints(store)!=before:
        raise ValueError('source archive changed during run')


def run(args):
    out=base.snapshot.output_path(args.out).resolve();store=base.base.local_directory(args.store);source=store.parent
    if out.is_relative_to(source) or source.is_relative_to(out): raise ValueError('output must be separate from source experiment')
    if store!=base.archive.DEFAULT_STORE.resolve(strict=True): raise ValueError('only recorded archive supported')
    if not math.isfinite(args.timeout) or args.timeout<120: raise ValueError('invalid experiment timeout')
    before=base.archive._path_fingerprints(store);checkpoint=CheckpointStore(store).latest_confirmed()
    if (checkpoint.checkpoint_id,checkpoint.sha256,checkpoint.size)!=(base.archive.CHECKPOINT_ID,base.archive.SHA256,base.archive.SIZE):
        raise ValueError('unexpected source checkpoint')
    verified=saved.verify(checkpoint,base.archive.REGISTRY_EPOCH)
    if base.archive._path_fingerprints(store)!=before: raise ValueError('archive changed during saved-sector parsing')
    slots=verified['slots']
    if len(slots)!=2 or [s['index'] for s in slots]!=[1,2] or not verified['sector_macros_unique_in_saved_universe']:
        raise ValueError('invalid saved-sector evidence')
    macros=[s['sector_macro'] for s in slots]
    if any(not isinstance(v,str) or not MACRO.fullmatch(v) or v in ('nil','null') for v in macros) or macros[0].casefold()==macros[1].casefold():
        raise ValueError('invalid saved-sector macros')
    nonce=secrets.token_hex(16)
    old=(base.install,base.check_log_bytes,base.fault_log,base.base.readonly_save_command,base.result_finalizer)
    try:
        args.slot=2
        base.install=lambda case,profile,ticket,slot: install(case,profile,ticket,slot,nonce,macros)
        base.check_log_bytes=lambda raw,ticket,slot,partial=False: validate(raw,ticket,slot,macros,partial)
        base.fault_log=fault_log;base.base.readonly_save_command=job_attach.readonly_save_command
        base.result_finalizer=lambda result: finalize_result(result,store,before)
        return base.run(args)
    finally:
        base.install,base.check_log_bytes,base.fault_log,base.base.readonly_save_command,base.result_finalizer=old


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--store',type=Path,default=base.archive.DEFAULT_STORE);p.add_argument('--display',required=True)
    p.add_argument('--timeout',type=float,default=300);p.add_argument('--seed',type=int,default=276944566);p.set_defaults(slot=2)
    try: result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as error: p.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1

if __name__=='__main__':sys.exit(main())
