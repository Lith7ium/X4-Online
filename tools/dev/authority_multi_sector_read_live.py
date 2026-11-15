#!/usr/bin/env python3
"""Opt-in two-sector, one-X4 read diagnostic. Import never starts X4."""
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

TAG='[X4LAN] AUTH_MULTI_SECTOR '
NUM=base.NUMBER
SAMPLE=re.compile(r'SAMPLE slot=([12]) n=([123]) real_before=('+NUM+r') real_after=('+NUM+r') game_before=('+NUM+r') game_after=('+NUM+r') x=('+NUM+r') y=('+NUM+r') z=('+NUM+r')\Z',re.ASCII)
DONE=re.compile(r'DONE samples=6 game=('+NUM+r')\Z',re.ASCII)
base_install=base.install
base_check=base.check_log_bytes
base_fault=base.fault_log


def install(case,profile,ticket,slot,nonce):
    if slot!=2 or not re.fullmatch(r'[0-9a-f]{32}',nonce): raise ValueError('invalid configuration')
    protected=base_install(case,profile,ticket,slot)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    shutil.copyfile(ROOT/'tools/dev/authority_multi_sector_read.xml',md/'authority_multi_sector_read.xml')
    shutil.copyfile(ROOT/'tools/dev/authority_multi_sector_read.lua',ui/'authority_multi_sector_read.lua')
    config=ui/'config.lua';text=config.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('invalid configuration')
    config.write_text(text[:-2]+',authority_multi_sector_read=true,authority_multi_nonce="'+nonce+'"}\n',encoding='ascii');config.chmod(0o600)
    read=ui/'authority_sector_read_probe.lua';text=read.read_text(encoding='utf-8')
    text+='''\nfunction X4LAN_MULTI_SECTOR_INITIAL()
 if state~='done' or failed then error('read not complete') end
 guard()
 return first[4],first[5],sample.game
end
'''
    read.write_text(text,encoding='utf-8')
    manifest=lab/'ui.xml';text=manifest.read_text(encoding='utf-8')
    hook='    <file name="ui/authority_download_load_probe.lua" />\n'
    if text.count(hook)!=1: raise ValueError('unexpected manifest')
    manifest.write_text(text.replace(hook,'    <file name="ui/authority_multi_sector_read.lua" />\n'+hook),encoding='utf-8')
    owner=ui/'authority_download_load_probe.lua';text=owner.read_text(encoding='utf-8')
    hook=" if state=='done' then return end\n"
    if text.count(hook)!=1: raise ValueError('unexpected update owner')
    owner.write_text(text.replace(hook," if state=='done' then X4LAN_MULTI_SECTOR_READY();return end\n"),encoding='utf-8')
    return protected+[md/'authority_multi_sector_read.xml',ui/'authority_multi_sector_read.lua']


def validate(raw,ticket,slot,partial=False):
    observed=base_check(raw,ticket,slot,partial=partial)
    if observed is None: return None
    rows=[line.split(TAG,1)[1].strip() for line in raw.decode('utf-8').splitlines() if TAG in line]
    if len(rows)>7: raise ValueError('duplicate multi-sector evidence')
    samples=[];previous={}
    for i,row in enumerate(rows[:6]):
        m=SAMPLE.fullmatch(row)
        if not m or int(m[1])!=i%2+1 or int(m[2])!=i//2+1: raise ValueError('invalid sample order')
        values=[float(m[j]) for j in range(3,10)]
        if not all(math.isfinite(v) for v in values): raise ValueError('nonfinite sample')
        rb,ra,gb,ga,*pos=values
        if rb<0 or ra<rb or gb<0 or ga<gb or (samples and (rb<=samples[-1]['real_after'] or gb<samples[-1]['game_after'])):
            raise ValueError('invalid or nonmonotonic sample clocks')
        index=int(m[1]);old=previous.get(index);rate=None
        if old:
            dt=ra-old['real_after']
            if gb<=old['game_after']: raise ValueError('game time did not advance for ship')
            if .02<=dt<=5:
                rate=[(pos[j]-old['position'][j])/dt for j in range(3)]
                if not all(math.isfinite(v) for v in rate) or math.hypot(*rate)>5000: rate=None
        sample=dict(slot=index,sample=int(m[2]),real_before=rb,real_after=ra,game_before=gb,game_after=ga,position=pos,
                    derived_rate_per_engine_real_second=rate)
        samples.append(sample);previous[index]=sample
    if len(rows)<7:
        if partial: return None
        raise ValueError('incomplete multi-sector evidence')
    m=DONE.fullmatch(rows[6])
    if not m or not math.isfinite(float(m[1])) or float(m[1])<samples[-1]['game_after']:
        raise ValueError('missing final pause receipt')
    observed.update(samples=samples,final_pause_checked=True,reported_final_game=float(m[1]),
                    registry_entries=2,sector_count=2,position_rate_proven=False)
    return observed


def run(args):
    nonce=secrets.token_hex(16)
    try:
        base.install=lambda case,profile,ticket,slot: install(case,profile,ticket,slot,nonce)
        base.check_log_bytes=lambda raw,ticket,slot,partial=False: validate(raw,ticket,slot,partial)
        base.fault_log=lambda raw: base_fault(raw) or (TAG+'ERROR ').encode() in raw
        result=base.run(args)
    finally:
        base.install=base_install;base.check_log_bytes=base_check;base.fault_log=base_fault
    result.update(scope='one isolated Linux X4; two stored registry entries; read only; no admission or gameplay',
                  native_velocity_sampled=False,universe_coverage_proven=False)
    (Path(args.out)/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
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
