#!/usr/bin/env python3
"""Opt-in one-X4 saved-registry job attach diagnostic; import never starts X4."""
import argparse
import json
import math
from pathlib import Path
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_sector_read_live as base
import authority_census_runtime_read_live as census
import authority_census_archive_provenance as archive

TAG='[X4LAN] AUTH_JOB_ATTACH '
EVENT=re.compile(r'EVENT sequence=([1-9][0-9]*) index=([1-9][0-9]*) class=(previously_observed|previously_unobserved_existing_index|new_registry_entry)\Z',re.ASCII)
SUMMARY=re.compile(r'SUMMARY observed=([0-9]+) acknowledged=([0-9]+) baseline=10054 class=(inconclusive_no_events|local_activations_observed)\Z',re.ASCII)
MD=('authority_checkpoint_marker.xml','authority_ship_registry.xml','authority_identity_fixture.xml','authority_job_ship_events.xml')
UI=('authority_checkpoint_marker_probe.lua','authority_job_registry_probe.lua','authority_job_registry_host.lua','authority_job_attach.lua')
_readonly_save_command=base.base.readonly_save_command


def replace_once(text,old,new):
    if text.count(old)!=1: raise ValueError('missing or ambiguous private overlay hook')
    return text.replace(old,new)


def install(case,profile,ticket,slot,window):
    if slot!=1 or not math.isfinite(window) or not 1<=window<=180 or ticket['world_epoch']==archive.REGISTRY_EPOCH:
        raise ValueError('invalid attach configuration')
    config=base.load.install_probe(case,profile,ticket)
    lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
    for name in MD: shutil.copyfile(ROOT/'tools/dev'/name,md/name)
    for name in UI: shutil.copyfile(ROOT/'tools/dev'/name,ui/name)
    marker=ui/'authority_checkpoint_marker_probe.lua'
    marker.write_text(replace_once(marker.read_text(),"if phase~='load' or state~='inspect' or type(marker)~='string'",
        "if marker~=cfg.authority_expected_marker or phase~='load' or state~='inspect' or type(marker)~='string'"))
    text=config.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('invalid load configuration')
    config.write_text(text[:-2]+',authority_marker_phase="load",authority_expected_marker="'+archive.MARKER+
        '",authority_job_attach=true,authority_job_registry_epoch="'+archive.REGISTRY_EPOCH+
        '",authority_job_window='+format(window,'.17g')+'}\n',encoding='ascii');config.chmod(0o600)
    manifest=lab/'ui.xml';text=manifest.read_text()
    hook='    <file name="ui/authority_download_load_probe.lua" />\n'
    manifest.write_text(replace_once(text,hook,''.join('    <file name="ui/'+name+'" />\n' for name in UI)+hook))
    owner=ui/'authority_download_load_probe.lua';text=owner.read_text()
    hook="local state='initial';local failed=false\n"
    text=replace_once(text,hook,hook+'local pause_requested=false;local pause_confirmed=false\n')
    hook=" elseif state=='observing' then\n"
    text=replace_once(text,hook,hook+'''  if not engine.is_paused() then
   if pause_confirmed then error('pre-attach pause lost') end
   if not pause_requested then pause_requested=true;engine.pause() end
   return
  end
  pause_confirmed=true
  if not X4LAN_AUTHORITY_MARKER_READY() then return end
''')
    text=replace_once(text," if state=='done' then return end\n",
        " if state=='done' then X4LAN_JOB_ATTACH_UPDATE();return end\n")
    owner.write_text(text)
    if {p.name for p in md.iterdir()}!=set(MD): raise ValueError('unexpected private MD scripts')
    return [config,lab/'ui.xml',lab/'content.xml',profile/'content.xml',profile/'config.xml']+[
        md/name for name in MD]+[ui/name for name in (*UI,'sha256.lua','client_load_barrier.lua',
        'x4_client_load_engine.lua','authority_download_load_probe.lua')]


def validate(raw,ticket,slot,*,partial=False):
    if slot!=1: raise ValueError('invalid attach slot')
    if not raw.endswith(b'\n'):
        if partial: return None
        raise ValueError('incomplete log')
    tags=(base.load.TAG.decode(),'[X4LAN] AUTH_MARKER load ',TAG)
    rows=[]
    for line in raw.decode('utf-8').splitlines():
        for tag in tags:
            if tag in line: rows.append((tag,line.split(tag,1)[1].strip()))
    run=ticket['world_epoch'];fields='|'.join(str(ticket[k]) for k in base.load.FIELDS)
    fixed=[(tags[0],'load_requested|'+fields),(tags[1],'INSPECTED '+archive.MARKER),
           (tags[0],'pause_observed|'+fields),
           (TAG,'READY registry_epoch='+archive.REGISTRY_EPOCH+' run_epoch='+run+' baseline=10054'),
           (TAG,'RESUMED run_epoch='+run)]
    for i,row in enumerate(rows[:len(fixed)]):
        if row!=fixed[i]: raise ValueError('invalid or reordered load/attach receipt')
    if len(rows)<len(fixed):
        if partial: return None
        raise ValueError('incomplete attach receipts')
    seen=set();last=archive.COUNT;events=[];summary=None;paused=False
    for tag,value in rows[len(fixed):]:
        if tag!=TAG or paused: raise ValueError('unexpected or duplicate attach receipt')
        if summary is None:
            match=EVENT.fullmatch(value)
            if match:
                sequence,index,classification=int(match[1]),int(match[2]),match[3]
                if sequence!=len(events)+1 or index>9007199254740991: raise ValueError('invalid event sequence or index')
                if classification=='previously_observed':
                    if index not in seen: raise ValueError('unseen index marked observed')
                elif classification=='previously_unobserved_existing_index':
                    if index in seen or index>archive.COUNT: raise ValueError('invalid existing index')
                else:
                    if index in seen or index!=last+1: raise ValueError('invalid new index')
                    last=index
                seen.add(index);events.append(dict(sequence=sequence,index=index,classification=classification));continue
            summary=SUMMARY.fullmatch(value)
            if not summary: raise ValueError('invalid attach event or summary')
            if (int(summary[1])!=len(events) or int(summary[2])!=len(events) or
                summary[3]!=('local_activations_observed' if events else 'inconclusive_no_events')):
                raise ValueError('attach summary mismatch')
        elif value=='PAUSED run_epoch='+run: paused=True
        else: raise ValueError('missing final pause')
    if not paused:
        if partial: return None
        raise ValueError('incomplete job attach observation')
    return dict(registry_epoch=archive.REGISTRY_EPOCH,baseline_count=archive.COUNT,
        queue_freshness_checked=True,attach_ready_before_resume=True,final_pause_checked=True,
        event_observed=bool(events),events=events,observed=len(events),acknowledged=len(events),
        classification=summary[3],birth_confirmed=False,delivery_confirmed=False,universe_coverage_proven=False)


def readonly_save_command(case,game,binds,lock,display,auth,username,seed,target):
    # The directory is private, and the staged save and every potential new
    # slot are read-only in the game namespace. The base runner rechecks bytes.
    command=_readonly_save_command(case,game,binds,lock,display,auth,username,seed,target)
    save=target.parent
    if save.name!='save' or target.name!='save_009.xml.gz': raise ValueError('unexpected private save path')
    pos=command.index('--die-with-parent')
    command[pos:pos]=['--ro-bind',str(save),str(save)]
    return command


def run(args):
    if not math.isfinite(args.window) or not 1<=args.window<=180 or not math.isfinite(args.timeout) or args.timeout<args.window+90:
        raise ValueError('invalid window or timeout')
    census.ensure_separate(base.snapshot.output_path(args.out),base.base.local_directory(args.store))
    old=(base.archive,base.install,base.check_origin_scripts,base.check_log_bytes,base.fault_log,base.MD,base.base.readonly_save_command)
    try:
        args.poll_interval=.5
        base.archive=archive;base.MD=MD[:3];base.check_origin_scripts=census.origin_scripts
        base.base.readonly_save_command=readonly_save_command
        base.install=lambda case,profile,ticket,slot: install(case,profile,ticket,slot,args.window)
        base.check_log_bytes=validate
        base.fault_log=lambda raw: old[4](raw) or (TAG+'ERROR').encode() in raw
        result=base.run(args)
    finally:
        base.archive,base.install,base.check_origin_scripts,base.check_log_bytes,base.fault_log,base.MD,base.base.readonly_save_command=old
    result.update(scope='one isolated Linux X4; local saved-registry job attach; no client or gameplay',
        birth_confirmed=False,delivery_confirmed=False,universe_coverage_proven=False,checkpoint_requested=False)
    (Path(args.out)/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--store',type=Path,default=archive.DEFAULT_STORE);p.add_argument('--display',required=True)
    p.add_argument('--window',type=float,default=60);p.add_argument('--timeout',type=float,default=300)
    p.add_argument('--seed',type=int,default=276944566);p.set_defaults(slot=1)
    try: result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as error: p.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1

if __name__=='__main__': sys.exit(main())
