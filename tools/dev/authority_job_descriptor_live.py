#!/usr/bin/env python3
"""Opt-in isolated job descriptor diagnostic; importing never starts X4.

One local activation is sampled after registry acknowledgement. No save,
client, delivery or birth claim is made. Source guards and cleanup come from
the archived attach/read runner. This file does not itself start X4 on import.
"""
import argparse
import json
import math
from pathlib import Path
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_job_attach_live as attach

TAG='[X4LAN] AUTH_JOB_DESCRIPTOR '
NUM=attach.base.NUMBER
SAMPLE=re.compile(r'SAMPLE request=([0-9a-f]{32}) epoch=([0-9a-f]{32}) sequence=([1-9][0-9]*) index=([1-9][0-9]*) '
 r'macro=([A-Za-z0-9_-]{1,128}) owner=([A-Za-z0-9_-]{1,128}) sector_macro=([A-Za-z0-9_-]{1,128}) '
 r'x=('+NUM+r') y=('+NUM+r') z=('+NUM+r') game_before_request=('+NUM+r') game_before_pose=('+NUM+r') game_after_pose=('+NUM+r')\Z',re.ASCII)
_original_install=attach.install
_original_validate=attach.validate


def install(case,profile,ticket,slot,window):
    protected=_original_install(case,profile,ticket,slot,window)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    extra_md=md/'authority_job_descriptor_probe.xml'
    shutil.copyfile(ROOT/'tools/dev/authority_job_descriptor_probe.xml',extra_md)
    for name in ('authority_registry_resolve_string.lua','authority_job_descriptor_probe.lua'):
        shutil.copyfile(ROOT/'tools/dev'/name,ui/name)
    shutil.copyfile(ROOT/'tools/dev/authority_job_descriptor_attach.lua',ui/'authority_job_attach.lua')
    config=ui/'config.lua';text=config.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('unexpected attach config')
    config.write_text(text[:-2]+',authority_job_descriptor=true}\n',encoding='ascii')
    manifest=lab/'ui.xml';text=manifest.read_text(encoding='utf-8')
    hook='    <file name="ui/authority_job_attach.lua" />\n'
    text=attach.replace_once(text,hook, '    <file name="ui/authority_registry_resolve_string.lua" />\n'
        '    <file name="ui/authority_job_descriptor_probe.lua" />\n'+hook)
    manifest.write_text(text,encoding='utf-8')
    if {p.name for p in md.iterdir()}!=set((*attach.MD,extra_md.name)):
        raise ValueError('unexpected private descriptor MD scripts')
    return protected+[extra_md,ui/'authority_registry_resolve_string.lua',ui/'authority_job_descriptor_probe.lua']


def validate(raw,ticket,slot,*,partial=False):
    observed=_original_validate(raw,ticket,slot,partial=partial)
    if observed is None: return None
    lines=raw.decode('utf-8').splitlines()
    samples=[(i,line.split(TAG,1)[1].strip()) for i,line in enumerate(lines) if TAG in line]
    if len(samples)!=1: raise ValueError('expected exactly one descriptor sample')
    position,text=samples[0];match=SAMPLE.fullmatch(text)
    if not match or match[1]!=ticket['world_epoch'] or match[2]!=attach.archive.REGISTRY_EPOCH:
        raise ValueError('descriptor request or epoch differs')
    sequence,index=int(match[3]),int(match[4]);new=[e for e in observed['events'] if e['classification']=='new_registry_entry']
    if not new or (sequence,index)!=(new[0]['sequence'],new[0]['index']):
        raise ValueError('descriptor is not the first new registry entry')
    event_pos=[i for i,line in enumerate(lines) if attach.TAG+f'EVENT sequence={sequence} index={index} class=new_registry_entry' in line]
    later=[i for i,line in enumerate(lines) if attach.TAG+'EVENT ' in line or attach.TAG+'SUMMARY ' in line]
    if len(event_pos)!=1 or position<=event_pos[0] or any(event_pos[0]<i<position for i in later):
        raise ValueError('descriptor event ordering differs')
    values=[float(match[i]) for i in range(8,14)]
    if not all(math.isfinite(v) for v in values) or not 0<=values[3]<=values[4]<=values[5]:
        raise ValueError('descriptor coordinates or game-time bracket invalid')
    observed.update(descriptor_sampled=True,descriptor_sequence=sequence,descriptor_index=index,
        descriptor_macro=match[5],descriptor_owner=match[6],descriptor_sector_macro=match[7],
        descriptor_position=values[:3],descriptor_game_before_request=values[3],
        descriptor_game_before_pose=values[4],descriptor_game_after_pose=values[5],
        descriptor_atomic=False,sector_identity_proven=False,birth_confirmed=False,delivery_confirmed=False)
    return observed


def run(args):
    old_install,old_validate=attach.install,attach.validate
    try:
        attach.install=install;attach.validate=validate
        result=attach.run(args)
    finally:
        attach.install,attach.validate=old_install,old_validate
    result.update(scope='one isolated Linux X4; local non-atomic job descriptor sample; no client or gameplay',
        descriptor_atomic=False,sector_identity_proven=False,birth_confirmed=False,
        delivery_confirmed=False,checkpoint_requested=False)
    (Path(args.out)/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--store',type=Path,default=attach.archive.DEFAULT_STORE);p.add_argument('--display',required=True)
    p.add_argument('--window',type=float,default=60);p.add_argument('--timeout',type=float,default=300)
    p.add_argument('--seed',type=int,default=276944566);p.set_defaults(slot=1)
    try: result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as error: p.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1
if __name__=='__main__':sys.exit(main())
