#!/usr/bin/env python3
"""Opt-in one-X4 jobs control OR treatment case; never launches X4 on import."""
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
import authority_sector_read_live as base

TAG='[X4LAN] AUTH_JOBS_CASE '
NUM=base.NUMBER
BEGIN=re.compile(r'BEGAN mode=(control|treatment) order=([\w-]{1,96}) game=('+NUM+r')\Z',re.ASCII)
SAMPLE=re.compile(r'SAMPLE n=(\d+) pilot=same order=([\w-]{1,96}) order_state=(started|critical) real=('+NUM+r') game_before=('+NUM+r') game_after=('+NUM+r') x=('+NUM+r') y=('+NUM+r') z=('+NUM+r')\Z',re.ASCII)
DONE=re.compile(r'DONE mode=(control|treatment) samples=(\d+) game=('+NUM+r')\Z',re.ASCII)


def install(case,profile,ticket,slot,mode,nonce,min_game):
    if slot!=2 or mode not in ('control','treatment') or not re.fullmatch(r'[0-9a-f]{32}',nonce) or not math.isfinite(min_game) or not 1<=min_game<=30:
        raise ValueError('invalid jobs case configuration')
    protected=base_install(case,profile,ticket,slot)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    shutil.copyfile(ROOT/'tools/dev/authority_sector_jobs_correlated.xml',md/'authority_sector_jobs_correlated.xml')
    shutil.copyfile(ROOT/'tools/dev/authority_sector_jobs_case.lua',ui/'authority_sector_jobs_case.lua')
    config=ui/'config.lua';text=config.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('invalid read config')
    config.write_text(text[:-2]+',authority_sector_jobs_case=true,authority_jobs_mode="'+mode+
                      '",authority_jobs_nonce="'+nonce+'",authority_jobs_min_game='+repr(min_game)+'}\n',encoding='ascii');config.chmod(0o600)
    read=ui/'authority_sector_read_probe.lua';text=read.read_text(encoding='utf-8')
    text+='''\n-- Private jobs-case export; the normal read probe does not export local handles.
function X4LAN_SECTOR_READ_EXPORT()
 if state~='done' or failed then error('read not complete') end
 guard()
 if first[1]~='present' or (first[3]~='started' and first[3]~='critical') then error('pilot/order unavailable') end
 return first[4],first[5],first[2],sample.game
end
'''
    read.write_text(text,encoding='utf-8')
    manifest=lab/'ui.xml';text=manifest.read_text(encoding='utf-8')
    hook='    <file name="ui/authority_download_load_probe.lua" />\n'
    if text.count(hook)!=1: raise ValueError('unexpected case manifest')
    manifest.write_text(text.replace(hook,'    <file name="ui/authority_sector_jobs_case.lua" />\n'+hook),encoding='utf-8')
    owner=ui/'authority_download_load_probe.lua';text=owner.read_text(encoding='utf-8')
    hook=" if state=='done' then return end\n"
    if text.count(hook)!=1: raise ValueError('unexpected update owner')
    owner.write_text(text.replace(hook," if state=='done' then X4LAN_JOBS_CASE_READY();return end\n"),encoding='utf-8')
    return protected+[md/'authority_sector_jobs_correlated.xml',ui/'authority_sector_jobs_case.lua']


def validate(raw,ticket,slot,mode,min_game,partial=False):
    observed=base_check(raw,ticket,slot,partial=partial)
    if observed is None: return None
    if observed.get('reported_pilot')!='present' or observed.get('reported_order_state') not in ('started','critical'):
        raise ValueError('pilot/order prerequisites were not reported')
    rows=[line.split(TAG,1)[1].strip() for line in raw.decode('utf-8').splitlines() if TAG in line]
    if not rows:
        if partial:return None
        raise ValueError('missing jobs begin')
    begin=BEGIN.fullmatch(rows[0])
    if (not begin or begin[1]!=mode or begin[2]!=observed['reported_order_id'] or
        not math.isfinite(float(begin[3])) or float(begin[3])<0 or
        float(begin[3])!=observed['reported_game_time'] or len(rows)>8):
        raise ValueError('unexpected jobs begin or duplicate receipt')
    begin_game=float(begin[3])
    samples=[]
    for i,row in enumerate(rows[1:7],1):
        m=SAMPLE.fullmatch(row)
        if not m or int(m[1])!=i or m[2]!=observed['reported_order_id']: raise ValueError('invalid jobs sample')
        values=[float(m[j]) for j in range(4,10)]
        if not all(math.isfinite(v) for v in values) or values[0]<0 or values[1]<0 or values[2]<values[1]:
            raise ValueError('invalid sample number')
        if values[1]<=begin_game or (samples and (values[0]<=samples[-1]['engine_real_time'] or values[1]<=samples[-1]['game_after'])):
            raise ValueError('sample clocks do not advance')
        samples.append({'reported_pilot':'same','reported_order_id':m[2],'reported_order_state':m[3],
                        'engine_real_time':values[0],'game_before':values[1],'game_after':values[2],'position':values[3:]})
    if len(rows)<8:
        if partial:return None
        raise ValueError('incomplete jobs run')
    done=DONE.fullmatch(rows[7])
    if (not done or done[1]!=mode or int(done[2])!=6 or not math.isfinite(float(done[3])) or
        float(done[3])<samples[-1]['game_after'] or samples[-1]['game_before']<begin_game+min_game):
        raise ValueError('invalid final pause receipt')
    observed.update(jobs_mode=mode,jobs_change_requested=mode=='treatment',jobs_effect_proven=False,
                    samples=samples,begin_game=begin_game,final_paused_game=float(done[3]),final_pause_checked=True)
    return observed


base_check=base.check_log_bytes
base_fault=base.fault_log
base_install=base.install


def run(args):
    if args.mode not in ('control','treatment') or args.slot!=2 or not math.isfinite(args.min_game) or not 1<=args.min_game<=30:
        raise ValueError('mode, slot 2 and bounded minimum game duration required')
    nonce=secrets.token_hex(16)
    try:
        base.install=lambda case,profile,ticket,slot: install(case,profile,ticket,slot,args.mode,nonce,args.min_game)
        base.check_log_bytes=lambda raw,ticket,slot,partial=False: validate(raw,ticket,slot,args.mode,args.min_game,partial)
        base.fault_log=lambda raw: base_fault(raw) or (TAG+'ERROR ').encode() in raw
        # install() calls the saved original, not the temporary hook.
        result=base.run(args)
    finally:
        base.install=base_install;base.check_log_bytes=base_check;base.fault_log=base_fault
    result.update(scope='one isolated Linux X4 jobs '+args.mode+' case; no admission or gameplay',
                  jobs_mode=args.mode,jobs_effect_proven=False)
    (Path(args.out)/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--store',type=Path,default=base.archive.DEFAULT_STORE);p.add_argument('--display',required=True)
    p.add_argument('--mode',choices=('control','treatment'),required=True);p.add_argument('--timeout',type=float,default=600)
    p.add_argument('--min-game',type=float,default=5.0,help='minimum in-game seconds from paused begin to sixth sample (1..30)')
    p.add_argument('--seed',type=int,default=276944566);p.set_defaults(slot=2)
    try: result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as error: p.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1

if __name__=='__main__': sys.exit(main())
