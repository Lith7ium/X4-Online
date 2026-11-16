#!/usr/bin/env python3
"""Prepare one isolated paused Multi-Create experiment; import never starts X4."""
import argparse
import json
import math
from pathlib import Path
import secrets
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_sector_read_live as base
import authority_census_runtime_read_live as census
import authority_census_archive_provenance as archive
import authority_census_pair_inputs as inputs
import authority_census_pair_live as pair
import authority_sector_pair_transfer_live as transfer
import authority_job_attach_live as attach

TAG='[X4LAN] AUTH_MULTI_CREATE '
BASE_MD=('authority_checkpoint_marker.xml','authority_ship_registry.xml','authority_identity_fixture.xml')
UI=('authority_checkpoint_marker_probe.lua','authority_registry_resolve_string.lua',
    'authority_multi_create_client.lua','authority_multi_create_scenario.lua',
    'x4_multi_create_inspector.lua','authority_multi_create_run.lua')
GLOBALS={'authority_multi_create_client.lua':'X4LAN_MULTI_CREATE_CLIENT',
         'authority_multi_create_scenario.lua':'X4LAN_MULTI_CREATE_SCENARIO',
         'x4_multi_create_inspector.lua':'X4LAN_MULTI_CREATE_INSPECTOR'}

def install(case,profile,ticket,slot,nonce,timeout,sectors):
    if slot!=1 or len(sectors)!=2 or sectors[0][0]==sectors[1][0]:raise ValueError('invalid scenario')
    config=base.load.install_probe(case,profile,ticket)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    md_names=BASE_MD+('authority_multi_create_receiver.xml',)
    for name in md_names:
        shutil.copyfile(archive.saved_state_script(name) if name in BASE_MD else ROOT/'tools/dev'/name,md/name)
    for name in UI:
        source=ROOT/'src/authority/lua'/name if name=='x4_multi_create_inspector.lua' else ROOT/'tools/dev'/name
        text=source.read_text()
        if name in GLOBALS:text=transfer.once(text,'return M\n',GLOBALS[name]+'=M\nreturn M\n')
        (ui/name).write_text(text)
    marker=ui/'authority_checkpoint_marker_probe.lua'
    marker.write_text(transfer.once(marker.read_text(),"if phase~='load' or state~='inspect' or type(marker)~='string'",
        "if marker~=cfg.authority_expected_marker or phase~='load' or state~='inspect' or type(marker)~='string'"))
    text=config.read_text(encoding='ascii')
    if not text.endswith('}\n'):raise ValueError('unexpected config')
    literal=base.base.lua_literal
    text=text[:-2]+(',authority_marker_phase="load",authority_expected_marker='+literal(archive.MARKER)+
        ',authority_multi_create_run=true,authority_multi_create_epoch='+literal(archive.REGISTRY_EPOCH)+
        ',authority_multi_create_nonce='+literal(nonce)+',authority_multi_create_baseline='+str(archive.COUNT)+
        ',authority_multi_create_timeout='+format(timeout,'.17g')+
        ''.join(',authority_multi_create_sector'+str(i)+'='+literal(name)+',authority_multi_create_witness'+str(i)+'='+str(index)
                for i,(name,index) in enumerate(sectors,1))+'}\n')
    config.write_text(text,encoding='ascii');config.chmod(0o600)
    manifest=lab/'ui.xml';hook='    <file name="ui/authority_download_load_probe.lua" />\n'
    manifest.write_text(transfer.once(manifest.read_text(),hook,''.join('    <file name="ui/'+n+'" />\n' for n in UI)+hook))
    owner=ui/'authority_download_load_probe.lua';text=owner.read_text()
    hook="local state='initial';local failed=false\n"
    text=transfer.once(text,hook,hook+'local pause_requested=false;local pause_confirmed=false\n')
    hook=" elseif state=='observing' then\n"
    text=transfer.once(text,hook,hook+'''  if not engine.is_paused() then
   if pause_confirmed then error('pre-test pause lost') end
   if not pause_requested then pause_requested=true;engine.pause() end
   return
  end
  pause_confirmed=true
  if not X4LAN_AUTHORITY_MARKER_READY() then return end
''')
    text=transfer.once(text," if state=='done' then return end\n",
        " if state=='done' then X4LAN_MULTI_CREATE_RUN_TICK();return end\n")
    owner.write_text(text)
    if {p.name for p in md.iterdir()}!=set(md_names):raise ValueError('unexpected private MD scripts')
    return [config,lab/'ui.xml',lab/'content.xml',profile/'content.xml',profile/'config.xml']+[md/name for name in md_names]+[
        ui/name for name in (*UI,'sha256.lua','client_load_barrier.lua','x4_client_load_engine.lua','authority_download_load_probe.lua')]

def validate(raw,ticket,slot,*,partial=False,sectors):
    if pair.load_observation(raw,ticket,partial=partial) is None:return None
    if not raw.endswith(b'\n'):
        if partial:return None
        raise ValueError('incomplete log')
    expected=['ROW create '+str(archive.COUNT+1)+' '+sectors[0][0],
              'ROW create '+str(archive.COUNT+2)+' '+sectors[1][0],
              'ROW replay '+str(archive.COUNT+1)+' '+sectors[0][0],
              'ROW replay '+str(archive.COUNT+2)+' '+sectors[1][0],'DONE']
    rows=[];pause_line=None
    for line_no,line in enumerate(raw.decode('utf-8').splitlines()):
        if base.load.TAG.decode()+'pause_observed|' in line:pause_line=line_no
        if TAG in line:
            if pause_line is None:raise ValueError('scenario before observed pause')
            rows.append(line.split(TAG,1)[1].strip())
    if rows!=expected[:len(rows)] or len(rows)>len(expected):raise ValueError('invalid scenario receipts')
    if len(rows)<len(expected):
        if partial:return None
        raise ValueError('missing scenario receipts')
    return dict(initial_pause_checked=True,marker_checked=True,created=2,replayed=2,
                local_sectors=[x[0] for x in sectors],artificial_seed=7183,
                source_transfer_proven=False,tcp_delivery_proven=False,multiplayer_proven=False,
                universe_coverage_proven=False,continuous_pause_proven=False,exact_loaded_file_proven=False)

def run(args):
    if not math.isfinite(args.timeout) or not 120<=args.timeout<=600:raise ValueError('invalid timeout')
    out=base.snapshot.output_path(args.out);store=base.base.local_directory(args.store)
    census.ensure_separate(out,store)
    witness_path=inputs.WITNESS_PATH.resolve(strict=True)
    if out.resolve().is_relative_to(witness_path) or witness_path.is_relative_to(out.resolve()):raise ValueError('output overlaps witness')
    witnesses=inputs.load_witness();sectors=[(name,indices[0]) for name,indices in sorted(witnesses.items()) if indices][:2]
    if len(sectors)!=2:raise ValueError('two eligible saved witnesses required')
    before=archive.fingerprints(store);nonce=secrets.token_hex(16)
    old=(base.archive,base.install,base.check_origin_scripts,base.check_log_bytes,base.fault_log,base.MD,
         base.base.readonly_save_command,base.result_finalizer)
    def finish(result):
        if archive.fingerprints(store)!=before:raise ValueError('source archive changed')
        result.update(scope='one paused isolated Linux X4; local synthetic multi-create only',
                      source_checkpoint_id=archive.CHECKPOINT_ID,witness_artifact_sha256=inputs.WITNESS_SHA256)
    try:
        args.poll_interval=1.0;base.archive=archive;base.MD=BASE_MD
        base.install=lambda case,profile,ticket,slot:install(case,profile,ticket,slot,nonce,30,sectors)
        base.check_origin_scripts=census.origin_scripts
        base.check_log_bytes=lambda raw,ticket,slot,partial=False:validate(raw,ticket,slot,partial=partial,sectors=sectors)
        base.fault_log=lambda raw:old[4](raw) or any(x in raw.lower() for x in
            (b'[x4lan] auth_multi_create error',b'maximum operator nesting level reached',
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
    p.add_argument('--timeout',type=float,default=300);p.add_argument('--seed',type=int,default=276944566)
    p.set_defaults(slot=1)
    try:result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as error:p.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1
if __name__=='__main__':sys.exit(main())
