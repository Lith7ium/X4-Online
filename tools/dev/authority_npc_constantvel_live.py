#!/usr/bin/env python3
"""Opt-in one-existing-NPC velocity/release diagnostic; import starts nothing."""
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
import authority_sector_jobs_case_live as jobs

base=jobs.base
TAG='[X4LAN] AUTH_NPC_CONSTANTVEL '
NUM=base.NUMBER
BEGIN=re.compile(r'BEGAN order=([\w-]{1,96}) game=('+NUM+r')\Z',re.ASCII)
SAMPLE=re.compile(r'SAMPLE phase=(before|during|after) n=([123]) pilot=same order=([\w-]{1,96}) order_state=(started|critical|other|none) real=('+NUM+r') game_before=('+NUM+r') game_after=('+NUM+r') x=('+NUM+r') y=('+NUM+r') z=('+NUM+r')\Z',re.ASCII)
ACK=re.compile(r'(APPLIED|RELEASED) game=('+NUM+r')\Z',re.ASCII)
DONE=re.compile(r'DONE before=3 during=3 after=3 game=('+NUM+r')\Z',re.ASCII)


def install(case,profile,ticket,slot,nonce):
    if slot!=2 or not re.fullmatch(r'[0-9a-f]{32}',nonce): raise ValueError('invalid configuration')
    protected=jobs.install(case,profile,ticket,slot,'control',nonce,5.)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    old_md=md/'authority_sector_jobs_correlated.xml';old_ui=ui/'authority_sector_jobs_case.lua'
    old_md.unlink();old_ui.unlink()
    new_md=md/'authority_npc_constantvel.xml';new_ui=ui/'authority_npc_constantvel.lua'
    shutil.copyfile(ROOT/'tools/dev/authority_npc_constantvel.xml',new_md)
    shutil.copyfile(ROOT/'tools/dev/authority_npc_constantvel.lua',new_ui)
    protected=[p for p in protected if p not in (old_md,old_ui)]+[new_md,new_ui]
    cfg=ui/'config.lua';text=cfg.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('unexpected configuration')
    cfg.write_text(text[:-2]+',authority_npc_constantvel=true,authority_npc_velocity_nonce="'+nonce+'"}\n',encoding='ascii')
    manifest=lab/'ui.xml';text=manifest.read_text()
    old='ui/authority_sector_jobs_case.lua';new='ui/authority_npc_constantvel.lua'
    if text.count(old)!=1: raise ValueError('unexpected case manifest')
    manifest.write_text(text.replace(old,new))
    owner=ui/'authority_download_load_probe.lua';text=owner.read_text()
    old='X4LAN_JOBS_CASE_READY()';new='X4LAN_NPC_CONSTANTVEL_READY()'
    if text.count(old)!=1: raise ValueError('unexpected update owner')
    owner.write_text(text.replace(old,new))
    return protected


def validate(raw,ticket,slot,partial=False):
    observed=jobs.base_check(raw,ticket,slot,partial=partial)
    if observed is None: return None
    if observed.get('reported_pilot')!='present' or observed.get('reported_order_state') not in ('started','critical'):
        raise ValueError('missing initial active pilot/order')
    rows=[line.split(TAG,1)[1].strip() for line in raw.decode('utf-8').splitlines() if TAG in line]
    if len(rows)<13:
        if partial: return None
        raise ValueError('incomplete velocity experiment')
    if len(rows)!=13: raise ValueError('duplicate velocity evidence')
    begin=BEGIN.fullmatch(rows[0])
    if not begin or begin[1]!=observed['reported_order_id'] or float(begin[2])!=observed['reported_game_time']:
        raise ValueError('invalid begin receipt')
    initial=float(begin[2]);last_game=initial;last_real=-1;samples=[];acks={}
    for i,row in enumerate(rows[1:12],1):
        if i in (4,8):
            ack=ACK.fullmatch(row);expected='APPLIED' if i==4 else 'RELEASED'
            if not ack or ack[1]!=expected or not math.isfinite(float(ack[2])) or float(ack[2])<last_game:
                raise ValueError('invalid setter receipt order')
            last_game=float(ack[2]);acks[expected.lower()]=last_game;continue
        m=SAMPLE.fullmatch(row)
        phase='before' if i<=3 else 'during' if i<=7 else 'after'
        number=i if i<=3 else i-4 if i<=7 else i-8
        if not m or m[1]!=phase or int(m[2])!=number or (m[3]=='none')!=(m[4]=='none'):
            raise ValueError('invalid sample receipt')
        values=[float(m[j]) for j in range(5,11)]
        real,game_before,game_after,*pos=values
        if (not all(math.isfinite(v) for v in values) or real<=last_real or game_before<=last_game
                or game_after<game_before): raise ValueError('invalid sample clocks')
        if game_before-last_game<1-1e-6:
            raise ValueError('sample interval shorter than requested')
        samples.append(dict(phase=phase,index=number,order_id=m[3],order_state=m[4],
                            engine_real_time=real,game_before=game_before,game_after=game_after,position=pos))
        last_real,last_game=real,game_after
    done=DONE.fullmatch(rows[12])
    if not done or not math.isfinite(float(done[1])) or float(done[1])<last_game:
        raise ValueError('missing final pause')
    observed.update(samples=samples,apply_receipt_game=acks['applied'],release_receipt_game=acks['released'],
                    final_pause_game=float(done[1]),final_pause_checked=True,native_velocity_readback=False,
                    prior_constant_velocity_mode_known=False,order_queue_preservation_proven=False,
                    complete_state_restored_proven=False)
    return observed


def run(args):
    out=base.snapshot.output_path(args.out).resolve()
    source=base.base.local_directory(args.store).parent
    if out.is_relative_to(source) or source.is_relative_to(out):
        raise ValueError('output and source experiment must be separate')
    nonce=secrets.token_hex(16)
    old=(base.install,base.check_log_bytes,base.fault_log)
    try:
        base.install=lambda case,profile,ticket,slot: install(case,profile,ticket,slot,nonce)
        base.check_log_bytes=validate
        base.fault_log=lambda raw: old[2](raw) or (TAG+'ERROR ').encode() in raw
        result=base.run(args)
    finally:
        base.install,base.check_log_bytes,base.fault_log=old
    result.update(scope='one existing NPC; zero-velocity intervention and release; isolated Linux; no admission or gameplay',
                  complete_state_restored_proven=False)
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
