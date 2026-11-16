#!/usr/bin/env python3
"""Opt-in one-X4 localhost TCP/UDP job diagnostic; import never starts X4."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_census_archive_provenance as archive
import authority_census_pair_inputs as inputs
import authority_census_pair_live as pair
import authority_census_runtime_read_live as census
import authority_job_attach_live as attach
import authority_participant_job_install as installer
import authority_sector_read_live as base
from authority.load_messages import _pairs, _reject_constant

TAG='[X4LAN] AUTH_PARTICIPANT_JOB '
RUNNING=re.compile(r'RUNNING ('+base.NUMBER+r')\Z',re.ASCII)
APPLIED=re.compile(r'LOCAL_APPLIED ([1-9][0-9]*) ('+base.NUMBER+r')\Z',re.ASCII)

def observe(raw,ticket,*,partial=False,sector):
    load=pair.load_observation(raw,ticket,partial=partial)
    if load is None:return None
    if not raw.endswith(b'\n'):
        if partial:return None
        raise ValueError('incomplete engine log')
    rows=[];pause=False
    for line in raw.decode('utf-8').splitlines():
        if base.load.TAG.decode()+'pause_observed|' in line:pause=True
        if TAG in line:
            if not pause:raise ValueError('participant before load pause')
            rows.append(line.split(TAG,1)[1].strip())
    if len(rows)>2:raise ValueError('duplicate local job receipts')
    if rows:
        m=RUNNING.fullmatch(rows[0]);running=float(m[1]) if m else float('nan')
        if not math.isfinite(running) or running<0:raise ValueError('invalid running receipt')
    if len(rows)==2:
        m=APPLIED.fullmatch(rows[1]);applied=float(m[2]) if m else float('nan')
        if not m or int(m[1])!=archive.COUNT+1 or not math.isfinite(applied) or applied<=running:
            raise ValueError('local apply or game-time progression unconfirmed')
    if len(rows)<2:
        if partial:return None
        raise ValueError('missing local job receipt')
    return dict(marker_checked=True,initial_pause_checked=True,local_job_applied=True,
        running_game_time=running,applied_game_time=applied,local_sector=sector,artificial_seed=7183,
        continuous_running_proven=False,exact_loaded_file_proven=False)

class Worker:
    """Owned worker, secret config over a private FD, bounded single result."""
    def __init__(self,settings):
        self.settings=settings;self.proc=None;self.control=None;self.buffer=b'';self.result=None;self.sent=False;self.eof=False
        self.participant=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.participant.bind(('127.0.0.1',0))
        self.job=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.job.bind(('127.0.0.1',0))
        self.parent,self.child=socket.socketpair();self.parent.setblocking(False)
    def start(self):
        fds=(self.participant.fileno(),self.job.fileno(),self.child.fileno())
        self.proc=subprocess.Popen([sys.executable,str(ROOT/'tools/dev/authority_tcp_job_client_live.py'),*(str(fd) for fd in fds)],
            cwd=ROOT,pass_fds=fds,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        self.child.close();self.participant.close();self.job.close();self.control=self.parent
    def go(self,config):
        if self.sent or self.proc is None or self.proc.poll() is not None:raise RuntimeError('worker unavailable for GO')
        raw=json.dumps(config,separators=(',',':'),allow_nan=False).encode('ascii')+b'\n'
        if len(raw)>16384:raise ValueError('worker configuration too large')
        self.control.settimeout(2)
        try:self.control.sendall(raw)
        finally:self.control.setblocking(False)
        self.sent=True
    def poll(self):
        if self.proc is None:return None
        while not self.eof:
            try:chunk=self.control.recv(16385-len(self.buffer))
            except BlockingIOError:break
            if not chunk:self.eof=True;break
            if self.result is not None:raise ValueError('unexpected extra worker frame')
            self.buffer+=chunk
            if len(self.buffer)>16384:raise ValueError('oversized worker result')
            if b'\n' in self.buffer:
                line,tail=self.buffer.split(b'\n',1)
                if tail:raise ValueError('unexpected extra worker frame')
                self.result=json.loads(line.decode('ascii'),object_pairs_hook=_pairs,parse_constant=_reject_constant)
                self.buffer=b''
        if self.eof and self.result is None:raise RuntimeError('worker exited without result')
        code=self.proc.poll()
        if code is not None and code!=0:raise RuntimeError('worker failed')
        return self.result if code==0 and self.eof else None
    def close(self):
        for sock in (self.participant,self.job,self.child,self.parent):
            try:sock.close()
            except OSError:pass
        if self.proc is not None:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:self.proc.wait(timeout=10)
                except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait(timeout=10)
            else:self.proc.wait()

def run(args):
    if not math.isfinite(args.timeout) or not 120<=args.timeout<=600:raise ValueError('invalid timeout')
    out=base.snapshot.output_path(args.out);store=base.base.local_directory(args.store);census.ensure_separate(out,store)
    witness_path=inputs.WITNESS_PATH.resolve(strict=True)
    if out.resolve().is_relative_to(witness_path) or witness_path.is_relative_to(out.resolve()):raise ValueError('output overlaps witness')
    witnesses=inputs.load_witness();selected=[(k,v[0]) for k,v in sorted(witnesses.items()) if v]
    if not selected:raise ValueError('no saved witness')
    sector,witness=selected[0];before=archive.fingerprints(store)
    def source_paths():
        paths=set((ROOT/'src/authority').rglob('*.py')) | set((ROOT/'src/lockstep/launcher').rglob('*.py'))
        paths.update(ROOT/'tools/dev'/n for n in ('authority_tcp_job_client_live.py','authority_tcp_native_worker.py',
            'authority_tcp_job_x4_live.py','authority_participant_job_install.py','authority_sector_read_live.py','authority_exec_gate.py'))
        paths.add(ROOT/'src/lockstep/__init__.py');paths.add(ROOT/'src/native/net.c')
        return paths
    source_fingerprints={p:base.stable_read(p,1<<20,collect=False)[:2] for p in source_paths()}
    def check_sources():
        if source_paths()!=set(source_fingerprints) or any(
            base.stable_read(p,1<<20,collect=False)[:2]!=fp for p,fp in source_fingerprints.items()):
            raise ValueError('worker or supervisor source changed')
    values=set([archive.REGISTRY_EPOCH])
    def fresh():
        v=secrets.token_hex(16)
        while v in values:v=secrets.token_hex(16)
        values.add(v);return v
    settings=dict(participant_port=0,participant_lease=fresh(),job_port=0,lease=fresh(),attempt=fresh(),
        epoch=archive.REGISTRY_EPOCH,generation=fresh(),nonce=fresh(),seed=7183,timeout=12)
    worker=Worker(settings);settings['participant_port']=worker.participant.getsockname()[1];settings['job_port']=worker.job.getsockname()[1]
    event={'epoch':archive.REGISTRY_EPOCH,'generation':settings['generation'],'sequence':1,'index':archive.COUNT+1,
           'descriptor':{'macro':'ship_gen_m_tugboat_01_a_macro','faction':'pioneers','sector_macro':sector,'x':-400,'y':100000,'z':500}}
    identity=None;ticket_value=None;go=False
    old=(base.archive,base.install,base.check_origin_scripts,base.check_log_bytes,base.fault_log,base.MD,
         base.base.readonly_save_command,base.result_finalizer,base.load.game_identity)
    def install(case,profile,ticket,slot):
        nonlocal ticket_value
        if slot!=1 or ticket_value is not None:raise ValueError('unexpected install')
        if ticket['world_epoch'] in values:raise ValueError('world epoch collides with participant context')
        ticket_value=dict(ticket);files=installer.install(case,profile,ticket,settings,{sector:witness})
        check_sources();return files
    def game_identity(proc,started,game):
        nonlocal identity
        current=old[8](proc,started,game)
        if current is not None:
            if identity is not None and identity!=current:raise RuntimeError('owned X4 changed')
            identity=current
        return current
    def check(raw,ticket,slot,partial=False):
        nonlocal go
        check_sources()
        loaded=pair.load_observation(raw,ticket,partial=partial)
        if loaded is not None and not go:
            if identity is None or ticket_value!=ticket:raise RuntimeError('load without owned process or matching ticket')
            st=os.stat('/proc/'+str(identity[0])+'/exe')
            config={'version':1,'epoch':ticket['world_epoch'],'lease':settings['lease'],'attempt':settings['attempt'],
                'generation':settings['generation'],'participant_lease':settings['participant_lease'],
                'client_process':{'pid':identity[0],'start_ticks':identity[1],'exe_dev':st.st_dev,'exe_ino':st.st_ino},
                'deadline':time.monotonic()+min(90,args.timeout/2),'event':event}
            check_sources();worker.start();check_sources();worker.go(config);go=True
        result=worker.poll()
        if result is None:
            if partial:return None
            raise ValueError('worker result missing')
        local=observe(raw,ticket,partial=partial,sector=sector)
        if local is None:return None
        # The worker's exact success contract is validated below before reporting.
        validate_worker(result,event)
        local.update(coordinator_reports_tcp_job_receipt=True,synthetic_server_context=True,
            source_transfer_proven=False,multiplayer_proven=False,universe_coverage_proven=False)
        return local
    def finish(result):
        if archive.fingerprints(store)!=before:raise ValueError('source archive changed')
        check_sources()
        if result.get('success') and (worker.proc is None or worker.proc.poll()!=0):raise ValueError('worker cleanup unconfirmed')
        result.update(scope='one isolated Linux X4; synthetic server and local TCP/UDP participant',
                      source_checkpoint_id=archive.CHECKPOINT_ID,witness_artifact_sha256=inputs.WITNESS_SHA256)
    try:
        args.poll_interval=.2;base.archive=archive;base.MD=installer.BASE_MD;base.install=install
        base.check_origin_scripts=census.origin_scripts;base.check_log_bytes=check;base.load.game_identity=game_identity
        base.fault_log=lambda raw:old[4](raw) or any(x in raw.lower() for x in (b'[x4lan] auth_participant_job error',
            b'maximum operator nesting level reached',b'could not find suitable data type for conversion!',b'invalid data types for arithmetic operation!'))
        base.base.readonly_save_command=attach.readonly_save_command;base.result_finalizer=finish
        return base.run(args)
    finally:
        (base.archive,base.install,base.check_origin_scripts,base.check_log_bytes,base.fault_log,base.MD,
         base.base.readonly_save_command,base.result_finalizer,base.load.game_identity)=old
        worker.close()

def validate_worker(result,event):
    expected={'event':'result','ok':True,'tcp_admitted':True,'tcp_job_receipt':True,
              'x4_md_ffi_asserted_by_owner':True,'synthetic_server_and_checkpoint':True,
              'checkpoint_offered_to_x4':False,'event_sequence':event['sequence'],'index':event['index']}
    if type(result) is not dict or set(result)!=set(expected):raise ValueError('invalid worker result fields')
    for k,v in expected.items():
        if type(result[k]) is not type(v) or result[k]!=v:raise ValueError('worker result differs: '+k)
    return True

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--store',type=Path,default=archive.DEFAULT_STORE);p.add_argument('--display',required=True)
    p.add_argument('--timeout',type=float,default=300);p.add_argument('--seed',type=int,default=276944566);p.set_defaults(slot=1)
    try:result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as error:p.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1
if __name__=='__main__':sys.exit(main())
