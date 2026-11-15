#!/usr/bin/env python3
"""Opt-in sequential two-profile saved-sector comparison; import starts nothing."""
import argparse
import copy
import json
from pathlib import Path
import re
import secrets
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_sector_read_live as base
import authority_sector_saved_fingerprint as saved
from authority.checkpoints import CheckpointStore

TAG='[X4LAN] AUTH_SECTOR_FINGERPRINT '
TOKEN=r'[A-Za-z0-9_.-]{1,128}'
ROW=re.compile(r'ROW slot=([12]) n=([12]) ship_code=('+TOKEN+r') ship_macro=('+TOKEN+r') sector_code=('+TOKEN+r') sector_macro=('+TOKEN+r') game=('+base.NUMBER+r')\Z',re.ASCII)
DONE=re.compile(r'DONE samples=4 game=('+base.NUMBER+r')\Z',re.ASCII)
base_install=base.install
base_check=base.check_log_bytes
base_fault=base.fault_log


def install(case,profile,ticket,slot,nonce):
    if slot!=2 or not re.fullmatch(r'[0-9a-f]{32}',nonce): raise ValueError('invalid configuration')
    protected=base_install(case,profile,ticket,slot)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    mdpath=md/'authority_sector_fingerprint.xml';uipath=ui/'authority_sector_fingerprint.lua'
    shutil.copyfile(ROOT/'tools/dev/authority_sector_fingerprint.xml',mdpath)
    shutil.copyfile(ROOT/'tools/dev/authority_sector_fingerprint.lua',uipath)
    cfg=ui/'config.lua';text=cfg.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('invalid private configuration')
    cfg.write_text(text[:-2]+',authority_sector_fingerprint=true,authority_fingerprint_nonce="'+nonce+'"}\n',encoding='ascii')
    read=ui/'authority_sector_read_probe.lua';text=read.read_text(encoding='utf-8')
    text+='''\n-- Private local handles, valid only inside this process.
function X4LAN_SECTOR_READ_EXPORT()
 if state~='done' or failed then error('read not complete') end
 guard()
 return first[4],first[5],first[2],sample.game
end
'''
    read.write_text(text,encoding='utf-8')
    manifest=lab/'ui.xml';text=manifest.read_text(encoding='utf-8')
    hook='    <file name="ui/authority_download_load_probe.lua" />\n'
    if text.count(hook)!=1: raise ValueError('unexpected UI manifest')
    manifest.write_text(text.replace(hook,'    <file name="ui/authority_sector_fingerprint.lua" />\n'+hook),encoding='utf-8')
    owner=ui/'authority_download_load_probe.lua';text=owner.read_text(encoding='utf-8')
    hook=" if state=='done' then return end\n"
    if text.count(hook)!=1: raise ValueError('unexpected update owner')
    owner.write_text(text.replace(hook," if state=='done' then X4LAN_SECTOR_FINGERPRINT_READY();return end\n"),encoding='utf-8')
    return protected+[mdpath,uipath]


def fault_log(raw):
    lower=raw.lower()
    return (base_fault(raw) or (TAG+'ERROR ').lower().encode() in lower or
        b'could not find suitable data type for conversion!' in lower or
        b'invalid data types for arithmetic operation!' in lower)


def validate(raw,ticket,slot,expected,partial=False):
    if fault_log(raw): raise ValueError('X4 or fingerprint probe fault')
    observed=base_check(raw,ticket,slot,partial=partial)
    if observed is None: return None
    rows=[line.split(TAG,1)[1].strip() for line in raw.decode('utf-8').splitlines() if TAG in line]
    if len(rows)>5: raise ValueError('duplicate fingerprint evidence')
    result=[]
    for i,row in enumerate(rows[:4]):
        m=ROW.fullmatch(row);index=i%2+1;sequence=i//2+1
        if not m or int(m[1])!=index or int(m[2])!=sequence:
            raise ValueError('invalid fingerprint row')
        fields={'index':index,'ship_code':m[3],'ship_macro':m[4],'sector_code':m[5],'sector_macro':m[6]}
        if any(v in ('null','nil') for v in (m[3],m[4],m[5],m[6])): raise ValueError('unavailable fingerprint')
        if fields!=expected[index]: raise ValueError('live and saved fingerprint differ')
        if float(m[7])!=observed['reported_game_time']: raise ValueError('game time changed')
        result.append(fields)
    if len(rows)<5:
        if partial:return None
        raise ValueError('incomplete fingerprint evidence')
    m=DONE.fullmatch(rows[4])
    if not m or float(m[1])!=observed['reported_game_time']: raise ValueError('invalid fingerprint completion')
    observed.update(fingerprint_rows=result,local_actor_and_sector_checks=True,
        runtime_binding_proven=False,exact_loaded_file_proven=False,universal_identity_proven=False)
    return observed


def run(args):
    out=base.snapshot.output_path(args.out).resolve()
    source=base.base.local_directory(args.store).parent
    if out.is_relative_to(source) or source.is_relative_to(out): raise ValueError('output must be separate from source experiment')
    before=base.archive._path_fingerprints(base.archive.DEFAULT_STORE)
    origin=base.archive.verify(base.archive.DEFAULT_STORE)
    checkpoint=CheckpointStore(base.archive.DEFAULT_STORE).latest_confirmed()
    verified=saved.verify(checkpoint,base.archive.REGISTRY_EPOCH)
    if base.archive._path_fingerprints(base.archive.DEFAULT_STORE)!=before: raise ValueError('archive changed while deriving fingerprints')
    fields=('index','ship_code','ship_macro','sector_code','sector_macro')
    expected={row['index']:{key:row[key] for key in fields} for row in verified['slots']}
    if len(verified['slots'])!=2 or set(expected)!={1,2}: raise ValueError('invalid saved slots')
    out.mkdir(mode=0o700,parents=True,exist_ok=False)
    result={'success':False,'scope':'two sequential isolated Linux profiles; two saved ships and sectors; read-only',
        'source_checkpoint_id':origin['checkpoint_id'],'source_sha256':origin['sha256'],
        'registry_epoch':origin['registry_epoch'],'saved_fingerprints':[expected[1],expected[2]],
        'profiles':[], 'exact_loaded_file_proven':False,'runtime_binding_proven':False,
        'universal_identity_proven':False,'gameplay_tested':False}
    old=(base.install,base.check_log_bytes,base.fault_log)
    try:
        for n in (1,2):
            nonce=secrets.token_hex(16);runargs=copy.copy(args);runargs.out=out/f'profile-{n}';runargs.slot=2
            base.install=lambda case,profile,ticket,slot: install(case,profile,ticket,slot,nonce)
            base.check_log_bytes=lambda raw,ticket,slot,partial=False: validate(raw,ticket,slot,expected,partial)
            base.fault_log=fault_log
            arm=base.run(runargs);result['profiles'].append(arm)
            if not arm.get('success') or arm.get('owned_processes_remaining')!=[]:
                result['error']=f'profile {n} failed or cleanup unconfirmed';break
        else:
            if base.archive._path_fingerprints(base.archive.DEFAULT_STORE)!=before:
                raise ValueError('archive changed during comparison')
            result['success']=True
    except BaseException as error:
        result.update(success=False,error=str(error) or type(error).__name__)
        if not isinstance(error,(Exception,KeyboardInterrupt)): raise
    finally:
        base.install,base.check_log_bytes,base.fault_log=old
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--display',required=True);p.add_argument('--timeout',type=float,default=600)
    p.set_defaults(store=base.archive.DEFAULT_STORE,seed=276944566,slot=2)
    try: result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as error: p.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1

if __name__=='__main__': sys.exit(main())
