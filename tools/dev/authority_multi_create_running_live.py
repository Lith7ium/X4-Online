#!/usr/bin/env python3
"""Separate opt-in running Multi-Create diagnostic; import never launches X4."""
import argparse
import json
import math
from pathlib import Path
import re
import secrets
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_multi_create_live as paused
import authority_census_runtime_read_live as census
import authority_census_archive_provenance as archive
import authority_census_pair_inputs as inputs
import authority_census_pair_live as pair
import authority_job_attach_live as attach

base=paused.base
TAG='[X4LAN] AUTH_MULTI_RUNNING '
NUMBER=base.NUMBER
RUNNING=re.compile(r'RUNNING ('+NUMBER+r') ('+NUMBER+r')\Z',re.ASCII)
CREATE=re.compile(r'ROW create ([1-9][0-9]*) ([A-Za-z0-9_.-]+) ('+NUMBER+r')\Z',re.ASCII)
DONE=re.compile(r'DONE ('+NUMBER+r')\Z',re.ASCII)

def install(case,profile,ticket,slot,nonce,timeout,sectors):
    files=paused.install(case,profile,ticket,slot,nonce,timeout,sectors)
    ui=case/'extensions/x4_lan_lab/ui';config=ui/'config.lua';text=config.read_text(encoding='ascii')
    if not text.endswith('}\n'):raise ValueError('unexpected config')
    config.write_text(text[:-2]+',authority_multi_create_running=true}\n',encoding='ascii');config.chmod(0o600)
    (ui/'authority_multi_create_run.lua').write_text((ROOT/'tools/dev/authority_multi_create_running_run.lua').read_text())
    return files

def validate(raw,ticket,slot,*,partial=False,sectors):
    if pair.load_observation(raw,ticket,partial=partial) is None:return None
    if not raw.endswith(b'\n'):
        if partial:return None
        raise ValueError('incomplete log')
    rows=[];pause=False
    for line in raw.decode('utf-8').splitlines():
        if base.load.TAG.decode()+'pause_observed|' in line:pause=True
        if TAG in line:
            if not pause:raise ValueError('running scenario before pause receipt')
            rows.append(line.split(TAG,1)[1].strip())
    if len(rows)>3:raise ValueError('duplicate running receipts')
    if rows:
        run=RUNNING.fullmatch(rows[0]);values=[float(run[1]),float(run[2])] if run else []
        if len(values)!=2 or not all(math.isfinite(x) and x>=0 for x in values) or values[1]<=values[0]:raise ValueError('resume progression missing')
    if len(rows)>=2:
        create=CREATE.fullmatch(rows[1]);g=float(create[3]) if create else float('nan')
        if not create or int(create[1])!=archive.COUNT+1 or create[2]!=sectors[0][0] or not math.isfinite(g) or g<values[1]:raise ValueError('invalid create receipt')
    if len(rows)>=3:
        done=DONE.fullmatch(rows[2]);end=float(done[1]) if done else float('nan')
        if not done or not math.isfinite(end) or end<=g:raise ValueError('post-create progression missing')
    if len(rows)<3:
        if partial:return None
        raise ValueError('missing running receipts')
    return dict(initial_pause_checked=True,marker_checked=True,resume_observed=True,created=1,
                start_game_time=values[0],resumed_game_time=values[1],create_game_time=g,final_game_time=end,
                local_sector=sectors[0][0],artificial_seed=7183,source_transfer_proven=False,
                tcp_delivery_proven=False,multiplayer_proven=False,universe_coverage_proven=False,
                uninterrupted_running_proven=False,exact_loaded_file_proven=False)

def run(args):
    if not math.isfinite(args.timeout) or not 120<=args.timeout<=600:raise ValueError('invalid timeout')
    out=base.snapshot.output_path(args.out);store=base.base.local_directory(args.store)
    census.ensure_separate(out,store)
    witness_path=inputs.WITNESS_PATH.resolve(strict=True)
    if out.resolve().is_relative_to(witness_path) or witness_path.is_relative_to(out.resolve()):raise ValueError('output overlaps witness')
    witnesses=inputs.load_witness();sectors=[(name,ids[0]) for name,ids in sorted(witnesses.items()) if ids][:2]
    if len(sectors)!=2:raise ValueError('two eligible saved witnesses required')
    before=archive.fingerprints(store);nonce=secrets.token_hex(16)
    old=(base.archive,base.install,base.check_origin_scripts,base.check_log_bytes,base.fault_log,base.MD,
         base.base.readonly_save_command,base.result_finalizer)
    def finish(result):
        if archive.fingerprints(store)!=before:raise ValueError('source archive changed')
        result.update(scope='one isolated Linux X4; running local synthetic create only',
                      source_checkpoint_id=archive.CHECKPOINT_ID,witness_artifact_sha256=inputs.WITNESS_SHA256)
    try:
        args.poll_interval=1.0;base.archive=archive;base.MD=paused.BASE_MD
        base.install=lambda case,profile,ticket,slot:install(case,profile,ticket,slot,nonce,30,sectors)
        base.check_origin_scripts=census.origin_scripts
        base.check_log_bytes=lambda raw,ticket,slot,partial=False:validate(raw,ticket,slot,partial=partial,sectors=sectors)
        base.fault_log=lambda raw:old[4](raw) or any(x in raw.lower() for x in
            (b'[x4lan] auth_multi_running error',b'maximum operator nesting level reached',
             b'could not find suitable data type for conversion!',b'invalid data types for arithmetic operation!'))
        base.base.readonly_save_command=attach.readonly_save_command;base.result_finalizer=finish
        return base.run(args)
    finally:
        (base.archive,base.install,base.check_origin_scripts,base.check_log_bytes,base.fault_log,base.MD,
         base.base.readonly_save_command,base.result_finalizer)=old

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--store',type=Path,default=archive.DEFAULT_STORE);p.add_argument('--display',required=True)
    p.add_argument('--timeout',type=float,default=300);p.add_argument('--seed',type=int,default=276944566);p.set_defaults(slot=1)
    try:result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as error:p.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1
if __name__=='__main__':sys.exit(main())
