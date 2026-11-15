#!/usr/bin/env python3
"""Opt-in paused sector-find calibration on one isolated X4; import starts nothing."""
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

TAG='[X4LAN] AUTH_SECTOR_FIND '
MACRO=re.compile(r'[A-Za-z0-9_.-]{1,128}\Z',re.ASCII)
ROW=re.compile(r'ROW slot=([12]) sector_macro=([A-Za-z0-9_.-]{1,128}) game=('+base.NUMBER+r')\Z',re.ASCII)
DONE=re.compile(r'DONE samples=2 game=('+base.NUMBER+r')\Z',re.ASCII)
_base_install=base.install
_base_check=base.check_log_bytes
_base_fault=base.fault_log


def install(case,profile,ticket,slot,nonce,macros):
    if (slot!=2 or not re.fullmatch(r'[0-9a-f]{32}',nonce) or len(macros)!=2 or
        any(not MACRO.fullmatch(v) or v in ('nil','null') for v in macros) or macros[0].casefold()==macros[1].casefold()):
        raise ValueError('invalid saved sector calibration configuration')
    protected=_base_install(case,profile,ticket,slot)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    mdpath=md/'authority_sector_find_calibration.xml';uipath=ui/'authority_sector_find_calibration.lua'
    shutil.copyfile(ROOT/'tools/dev'/mdpath.name,mdpath);shutil.copyfile(ROOT/'tools/dev'/uipath.name,uipath)
    cfg=ui/'config.lua';text=cfg.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('invalid private configuration')
    cfg.write_text(text[:-2]+',authority_sector_find_calibration=true,authority_sector_find_nonce="'+nonce+
        '",authority_sector_find_macros={'+','.join('"'+v+'"' for v in macros)+'}}\n',encoding='ascii')
    read=ui/'authority_sector_read_probe.lua';text=read.read_text()
    text+='''\n-- Diagnostic handles stay local to this process.
function X4LAN_SECTOR_READ_EXPORT()
 if state~='done' or failed then error('read not complete') end
 guard()
 return first[4],first[5],first[2],sample.game
end
'''
    read.write_text(text)
    manifest=lab/'ui.xml';text=manifest.read_text();hook='    <file name="ui/authority_download_load_probe.lua" />\n'
    if text.count(hook)!=1: raise ValueError('unexpected UI manifest')
    manifest.write_text(text.replace(hook,'    <file name="ui/authority_sector_find_calibration.lua" />\n'+hook))
    owner=ui/'authority_download_load_probe.lua';text=owner.read_text();hook=" if state=='done' then return end\n"
    if text.count(hook)!=1: raise ValueError('unexpected update owner')
    owner.write_text(text.replace(hook," if state=='done' then X4LAN_SECTOR_FIND_CALIBRATION_READY();return end\n"))
    return protected+[mdpath,uipath]


def fault_log(raw):
    lower=raw.lower()
    return (_base_fault(raw) or (TAG+'ERROR ').lower().encode() in lower or
        b'could not find suitable data type for conversion!' in lower or b'invalid data types for arithmetic operation!' in lower)


def validate(raw,ticket,slot,macros,partial=False):
    if fault_log(raw): raise ValueError('X4 or sector find probe fault')
    observed=_base_check(raw,ticket,slot,partial=partial)
    if observed is None: return None
    lines=raw.decode('utf-8').splitlines()
    rows=[line.split(TAG,1)[1].strip() for line in lines if TAG in line]
    pause_tag=base.load.TAG.decode()+'pause_observed|'
    pauses=[i for i,line in enumerate(lines) if pause_tag in line]
    row_positions=[i for i,line in enumerate(lines) if TAG in line]
    if row_positions and (len(pauses)!=1 or row_positions[0]<=pauses[0]):
        raise ValueError('calibration before confirmed pause')
    if len(rows)>3: raise ValueError('duplicate calibration evidence')
    for i,row in enumerate(rows[:2]):
        match=ROW.fullmatch(row)
        if (not match or int(match[1])!=i+1 or match[2]!=macros[i] or not math.isfinite(float(match[3])) or
            float(match[3])!=observed['reported_game_time']): raise ValueError('invalid calibration row')
    if len(rows)<3:
        if partial: return None
        raise ValueError('incomplete calibration')
    match=DONE.fullmatch(rows[2])
    if not match or float(match[1])!=observed['reported_game_time']: raise ValueError('invalid calibration completion')
    observed.update(calibrated_sector_macros=list(macros),calibrated_slots=2,exactly_one_match_each=True,
        local_ffi_checked=True,runtime_binding_proven=False,exact_loaded_file_proven=False,universal_uniqueness_proven=False)
    return observed


def run(args):
    out=base.snapshot.output_path(args.out).resolve();store=base.base.local_directory(args.store)
    source=store.parent
    if out.is_relative_to(source) or source.is_relative_to(out): raise ValueError('output must be separate from source experiment')
    if store!=base.archive.DEFAULT_STORE.resolve(strict=True): raise ValueError('only the recorded archive is supported')
    before=base.archive._path_fingerprints(store);checkpoint=CheckpointStore(store).latest_confirmed()
    if (checkpoint.checkpoint_id,checkpoint.sha256,checkpoint.size)!=(base.archive.CHECKPOINT_ID,base.archive.SHA256,base.archive.SIZE):
        raise ValueError('unexpected source checkpoint')
    verified=saved.verify(checkpoint,base.archive.REGISTRY_EPOCH)
    if base.archive._path_fingerprints(store)!=before: raise ValueError('archive changed while deriving saved sectors')
    slots=verified['slots']
    if len(slots)!=2 or [s['index'] for s in slots]!=[1,2] or not verified['sector_macros_unique_in_saved_universe']:
        raise ValueError('invalid saved sector evidence')
    macros=[s['sector_macro'] for s in slots];nonce=secrets.token_hex(16)
    if any(not MACRO.fullmatch(v) or v in ('nil','null') for v in macros) or macros[0].casefold()==macros[1].casefold():
        raise ValueError('invalid saved sector macros')
    old=(base.install,base.check_log_bytes,base.fault_log)
    try:
        args.slot=2
        base.install=lambda case,profile,ticket,slot: install(case,profile,ticket,slot,nonce,macros)
        base.check_log_bytes=lambda raw,ticket,slot,partial=False: validate(raw,ticket,slot,macros,partial)
        base.fault_log=fault_log
        result=base.run(args)
    finally:
        base.install,base.check_log_bytes,base.fault_log=old
    result.update(scope='one paused isolated Linux X4; two saved sector references; local read only',
        universal_uniqueness_proven=False,client_identity_proven=False,gameplay_tested=False)
    (Path(args.out)/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--store',type=Path,default=base.archive.DEFAULT_STORE);p.add_argument('--display',required=True)
    p.add_argument('--timeout',type=float,default=600);p.add_argument('--seed',type=int,default=276944566);p.set_defaults(slot=2)
    try: result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as error: p.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1

if __name__=='__main__': sys.exit(main())
