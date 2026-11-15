#!/usr/bin/env python3
"""One opt-in arm of the isolated NPC signal A/B diagnostic; import starts nothing."""
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
TAG='[X4LAN] AUTH_NPC_SIGNAL_AB '
NUM=base.NUMBER
BEGIN=re.compile(r'BEGAN mode=(control|treatment) order=([\w-]{1,96}) order_state=(started|critical) game=('+NUM+r')\Z',re.ASCII)
SAMPLE=re.compile(r'SAMPLE phase=(before|during|after|tail) n=([1-5]) pilot=same order=([\w-]{1,96}) order_state=(started|critical|other|none) real=('+NUM+r') game_before=('+NUM+r') game_after=('+NUM+r') x=('+NUM+r') y=('+NUM+r') z=('+NUM+r')\Z',re.ASCII)
ACK=re.compile(r'(APPLIED|RELEASED) game=('+NUM+r')\Z',re.ASCII)
DECISION=re.compile(r'DECISION mode=(control|treatment) outcome=(noop|sent|skipped_order) order=([\w-]{1,96}) order_state=(started|critical|other|none) game=('+NUM+r')\Z',re.ASCII)
DONE=re.compile(r'DONE mode=(control|treatment) before=3 during=3 after=5 tail=5 game=('+NUM+r')\Z',re.ASCII)


def install(case,profile,ticket,slot,nonce,mode):
    if slot!=2 or mode not in ('control','treatment') or not re.fullmatch(r'[0-9a-f]{32}',nonce): raise ValueError('invalid configuration')
    protected=jobs.install(case,profile,ticket,slot,'control',nonce,5.)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    old_md=md/'authority_sector_jobs_correlated.xml';old_ui=ui/'authority_sector_jobs_case.lua'
    old_md.unlink();old_ui.unlink()
    new_md=md/'authority_npc_signal_ab.xml';new_ui=ui/'authority_npc_signal_ab.lua'
    shutil.copyfile(ROOT/'tools/dev/authority_npc_signal_ab.xml',new_md)
    shutil.copyfile(ROOT/'tools/dev/authority_npc_signal_ab.lua',new_ui)
    protected=[p for p in protected if p not in (old_md,old_ui)]+[new_md,new_ui]
    cfg=ui/'config.lua';text=cfg.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('unexpected configuration')
    cfg.write_text(text[:-2]+',authority_npc_signal_ab=true,authority_npc_velocity_nonce="'+nonce+'",authority_npc_signal_mode="'+mode+'"}\n',encoding='ascii')
    manifest=lab/'ui.xml';text=manifest.read_text()
    old='ui/authority_sector_jobs_case.lua';new='ui/authority_npc_signal_ab.lua'
    if text.count(old)!=1: raise ValueError('unexpected case manifest')
    manifest.write_text(text.replace(old,new))
    owner=ui/'authority_download_load_probe.lua';text=owner.read_text()
    old='X4LAN_JOBS_CASE_READY()';new='X4LAN_NPC_SIGNAL_AB_READY()'
    if text.count(old)!=1: raise ValueError('unexpected update owner')
    owner.write_text(text.replace(old,new))
    return protected


def validate(raw,ticket,slot,mode,partial=False):
    if mode not in ('control','treatment'): raise ValueError('invalid mode')
    observed=jobs.base_check(raw,ticket,slot,partial=partial)
    if observed is None: return None
    if observed.get('reported_pilot')!='present' or observed.get('reported_order_state') not in ('started','critical'):
        raise ValueError('missing initial active pilot/order')
    rows=[line.split(TAG,1)[1].strip() for line in raw.decode('utf-8').splitlines() if TAG in line]
    if len(rows)<21:
        if partial: return None
        raise ValueError('incomplete signal experiment')
    if len(rows)!=21: raise ValueError('duplicate signal evidence')
    begin=BEGIN.fullmatch(rows[0])
    if (not begin or begin[1]!=mode or begin[2]!=observed['reported_order_id'] or
        begin[3]!=observed['reported_order_state'] or float(begin[4])!=observed['reported_game_time']):
        raise ValueError('invalid begin receipt')
    last_game=float(begin[4]);last_real=-1;samples=[];acks={};cursor=1
    def read_samples(phase,count,interval):
        nonlocal cursor,last_game,last_real
        for number in range(1,count+1):
            m=SAMPLE.fullmatch(rows[cursor]);cursor+=1
            if (not m or m[1]!=phase or int(m[2])!=number or (m[3]=='none')!=(m[4]=='none') or
                (phase=='before' and (m[3]!=begin[2] or m[4]!=begin[3]))):
                raise ValueError('invalid sample or changed baseline order')
            values=[float(m[j]) for j in range(5,11)]
            real,game_before,game_after,*pos=values
            if (not all(math.isfinite(v) for v in values) or real<=last_real or
                game_before-last_game<interval-1e-6 or game_after<game_before):
                raise ValueError('invalid sample values or interval')
            samples.append(dict(phase=phase,index=number,order_id=m[3],order_state=m[4],
                engine_real_time=real,game_before=game_before,game_after=game_after,position=pos))
            last_real,last_game=real,game_after
    def ack(expected):
        nonlocal cursor,last_game
        m=ACK.fullmatch(rows[cursor]);cursor+=1
        if not m or m[1]!=expected or not math.isfinite(float(m[2])) or float(m[2])<last_game:
            raise ValueError('invalid setter receipt')
        last_game=float(m[2]);acks[expected.lower()]=last_game
    read_samples('before',3,1);ack('APPLIED');read_samples('during',3,1);ack('RELEASED')
    read_samples('after',5,5)
    decision=DECISION.fullmatch(rows[cursor]);cursor+=1
    if (not decision or decision[1]!=mode or
        (mode=='control' and decision[2]!='noop') or (mode=='treatment' and decision[2] not in ('sent','skipped_order')) or
        (decision[3]=='none')!=(decision[4]=='none') or
        (decision[2]=='sent' and (decision[3]!=begin[2] or decision[4]!=begin[3])) or
        not math.isfinite(float(decision[5])) or float(decision[5])<last_game):
        raise ValueError('invalid decision receipt')
    last_game=float(decision[5]);decision_game=last_game
    read_samples('tail',5,5)
    done=DONE.fullmatch(rows[cursor])
    if not done or done[1]!=mode or not math.isfinite(float(done[2])) or float(done[2])<last_game:
        raise ValueError('missing final pause')
    observed.update(mode=mode,samples=samples,apply_receipt_game=acks['applied'],release_receipt_game=acks['released'],
        decision_receipt_game=decision_game,decision_outcome=decision[2],decision_order_id=decision[3],decision_order_state=decision[4],
        signal_dispatch_requested=(decision[2]=='sent'),
        observed_order_changed=(decision[3]!=begin[2] or decision[4]!=begin[3] or
            any(s['order_id']!=begin[2] or s['order_state']!=begin[3] for s in samples)),signal_handler_execution_proven=False,
        final_pause_game=float(done[2]),final_pause_checked=True,native_velocity_readback=False,
        prior_constant_velocity_mode_known=False,order_queue_preservation_proven=False,complete_state_restored_proven=False)
    return observed


def run(args):
    if args.mode not in ('control','treatment') or args.slot!=2 or args.seed!=276944566: raise ValueError('invalid arm, slot or seed')
    out=base.snapshot.output_path(args.out).resolve()
    source=base.base.local_directory(args.store).parent
    if out.is_relative_to(source) or source.is_relative_to(out):
        raise ValueError('output and source experiment must be separate')
    nonce=secrets.token_hex(16)
    old=(base.install,base.check_log_bytes,base.fault_log)
    try:
        base.install=lambda case,profile,ticket,slot: install(case,profile,ticket,slot,nonce,args.mode)
        base.check_log_bytes=lambda raw,ticket,slot,partial=False: validate(raw,ticket,slot,args.mode,partial)
        base.fault_log=lambda raw: old[2](raw) or (TAG+'ERROR ').encode() in raw
        result=base.run(args)
    finally:
        base.install,base.check_log_bytes,base.fault_log=old
    result.update(scope='one isolated Linux A/B arm; no admission or gameplay', mode=args.mode,
                  signal_handler_execution_proven=False, complete_state_restored_proven=False,
                  requested_checkpoint_sha256=base.archive.SHA256, requested_registry_epoch=base.archive.REGISTRY_EPOCH,
                  requested_slot=2, requested_seed=276944566)
    (Path(args.out)/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--store',type=Path,default=base.archive.DEFAULT_STORE);p.add_argument('--display',required=True)
    p.add_argument('--mode',choices=('control','treatment'),required=True)
    p.add_argument('--timeout',type=float,default=600);p.set_defaults(slot=2,seed=276944566)
    try: result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as error: p.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1


if __name__=='__main__': sys.exit(main())
