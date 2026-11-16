#!/usr/bin/env python3
"""Prepare one isolated read-only X4 event comparison; import never starts X4."""
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
import authority_census_archive_provenance as archive
import authority_census_runtime_read_live as census
import authority_census_pair_live as pair
import authority_job_attach_live as attach
import authority_sector_pair_transfer_live as transfer

TAG='[X4LAN] AUTH_EVENT_COMPARE '
BASE_MD=('authority_checkpoint_marker.xml','authority_ship_registry.xml','authority_identity_fixture.xml')
MD=BASE_MD+('authority_ship_event_compare.xml',)
UI=('authority_checkpoint_marker_probe.lua','authority_registry_resolve_string.lua','authority_ship_event_compare.lua','authority_ship_event_compare_run.lua')
ROW=re.compile(r'ROW ([1-9][0-9]*) (god|player_build|activation|galaxy_enter) (0|[1-9][0-9]*) ([1-9][0-9]*)\Z',re.ASCII)
DONE=re.compile(r'DONE (0|[1-9][0-9]*)\Z',re.ASCII)

def install(case,profile,ticket,slot,window,generation):
    if slot!=1 or not math.isfinite(window) or not 1<=window<=180 or not re.fullmatch(r'[0-9a-f]{32}',generation):raise ValueError('invalid observer config')
    if len({generation,ticket['world_epoch'],archive.REGISTRY_EPOCH})!=3:raise ValueError('epoch or generation reused')
    config=base.load.install_probe(case,profile,ticket);lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    for name in MD:shutil.copyfile(archive.saved_state_script(name) if name in BASE_MD else ROOT/'tools/dev'/name,md/name)
    for name in UI:
        text=(ROOT/'tools/dev'/name).read_text()
        if name=='authority_ship_event_compare.lua':text=transfer.once(text,'return M\n','X4LAN_SHIP_EVENT_COMPARE=M\nreturn M\n')
        (ui/name).write_text(text)
    marker=ui/'authority_checkpoint_marker_probe.lua'
    marker.write_text(transfer.once(marker.read_text(),"if phase~='load' or state~='inspect' or type(marker)~='string'",
        "if marker~=cfg.authority_expected_marker or phase~='load' or state~='inspect' or type(marker)~='string'"))
    text=config.read_text(encoding='ascii');literal=base.base.lua_literal
    if not text.endswith('}\n'):raise ValueError('unexpected config')
    text=text[:-2]+(',authority_marker_phase="load",authority_expected_marker='+literal(archive.MARKER)+
        ',authority_ship_event_compare_run=true,authority_ship_event_compare_epoch='+literal(archive.REGISTRY_EPOCH)+
        ',authority_ship_event_compare_generation='+literal(generation)+',authority_ship_event_compare_capacity=128'+
        ',authority_ship_event_compare_window='+format(window,'.17g')+'}\n')
    config.write_text(text,encoding='ascii');config.chmod(0o600)
    manifest=lab/'ui.xml';hook='    <file name="ui/authority_download_load_probe.lua" />\n'
    manifest.write_text(transfer.once(manifest.read_text(),hook,''.join('    <file name="ui/'+name+'" />\n' for name in UI)+hook))
    owner=ui/'authority_download_load_probe.lua';text=owner.read_text();hook="local state='initial';local failed=false\n"
    text=transfer.once(text,hook,hook+'local pause_requested=false;local pause_confirmed=false\n')
    hook=" elseif state=='observing' then\n"
    text=transfer.once(text,hook,hook+'''  if not engine.is_paused() then
   if pause_confirmed then error('pre-observation pause lost') end
   if not pause_requested then pause_requested=true;engine.pause() end
   return
  end
  pause_confirmed=true
  if not X4LAN_AUTHORITY_MARKER_READY() then return end
''')
    owner.write_text(transfer.once(text," if state=='done' then return end\n",
        " if state=='done' then X4LAN_EVENT_COMPARE_TICK();return end\n"))
    if {p.name for p in md.iterdir()}!=set(MD):raise ValueError('unexpected private MD scripts')
    return [config,lab/'ui.xml',lab/'content.xml',profile/'content.xml',profile/'config.xml']+[md/name for name in MD]+[
        ui/name for name in (*UI,'sha256.lua','client_load_barrier.lua','x4_client_load_engine.lua','authority_download_load_probe.lua')]

def validate(raw,ticket,slot,*,partial=False):
    if slot!=1:raise ValueError('invalid slot')
    loaded=pair.load_observation(raw,ticket,partial=partial)
    if loaded is None:return None
    if not raw.endswith(b'\n'):
        if partial:return None
        raise ValueError('incomplete log')
    pause=False;ready=False;running=False;done=False;rows=[]
    for line in raw.decode('utf-8').splitlines():
        if base.load.TAG.decode()+'pause_observed|' in line:pause=True
        if TAG not in line:continue
        if not pause or done:raise ValueError('event observer out of order')
        value=line.split(TAG,1)[1].strip()
        if value=='READY':
            if ready or running:raise ValueError('duplicate or late ready')
            ready=True;continue
        if value=='RUNNING':
            if not ready or running:raise ValueError('invalid resume')
            running=True;continue
        m=ROW.fullmatch(value)
        if m:
            if not ready:raise ValueError('event before observer ready')
            seq,kind,index,actor=int(m[1]),m[2],int(m[3]),int(m[4])
            if seq!=len(rows)+1 or seq>2147483647 or index>9007199254740991 or actor>18446744073709551615:
                raise ValueError('invalid observer row')
            rows.append(dict(sequence=seq,kind=kind,registry_index=index,local_actor=str(actor)));continue
        m=DONE.fullmatch(value)
        if m and ready and running and int(m[1])==len(rows):done=True;continue
        raise ValueError('invalid observer receipt')
    if not done:
        if partial:return None
        raise ValueError('incomplete observer')
    counts={kind:sum(row['kind']==kind for row in rows) for kind in ('god','player_build','activation','galaxy_enter')}
    return dict(marker_checked=True,initial_pause_checked=True,final_pause_checked=True,queue_empty_sampled=True,
        observed=len(rows),events=rows,source_counts=counts,classification='events_observed' if rows else 'inconclusive_no_events',
        birth_confirmed=False,universe_coverage_proven=False,source_transfer_proven=False,multiplayer_proven=False,
        continuous_running_proven=False,exact_loaded_file_proven=False)

def run(args):
    if not math.isfinite(args.window) or not 1<=args.window<=180 or not math.isfinite(args.timeout) or args.timeout<args.window+90:
        raise ValueError('invalid window or timeout')
    out=base.snapshot.output_path(args.out);store=base.base.local_directory(args.store);census.ensure_separate(out,store)
    before=archive.fingerprints(store);generation=secrets.token_hex(16)
    old=(base.archive,base.install,base.check_origin_scripts,base.check_log_bytes,base.fault_log,base.MD,base.base.readonly_save_command,base.result_finalizer)
    def finish(result):
        if archive.fingerprints(store)!=before:raise ValueError('source archive changed')
        result.update(scope='one isolated Linux X4; read-only ship-event comparison',source_checkpoint_id=archive.CHECKPOINT_ID)
    try:
        args.poll_interval=.5;base.archive=archive;base.MD=BASE_MD;base.check_origin_scripts=census.origin_scripts
        base.base.readonly_save_command=attach.readonly_save_command
        base.install=lambda case,profile,ticket,slot:install(case,profile,ticket,slot,args.window,generation)
        base.check_log_bytes=validate
        base.fault_log=lambda raw:old[4](raw) or any(x in raw.lower() for x in (b'[x4lan] auth_event_compare error',
            b'maximum operator nesting level reached',b'could not find suitable data type for conversion!',b'invalid data types for arithmetic operation!'))
        base.result_finalizer=finish
        return base.run(args)
    finally:
        (base.archive,base.install,base.check_origin_scripts,base.check_log_bytes,base.fault_log,base.MD,
         base.base.readonly_save_command,base.result_finalizer)=old

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--store',type=Path,default=archive.DEFAULT_STORE);p.add_argument('--display',required=True)
    p.add_argument('--window',type=float,default=60);p.add_argument('--timeout',type=float,default=300)
    p.add_argument('--seed',type=int,default=276944566);p.set_defaults(slot=1)
    try:result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as error:p.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1
if __name__=='__main__':sys.exit(main())
