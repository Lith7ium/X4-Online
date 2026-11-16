#!/usr/bin/env python3
"""One isolated source+client X4 TCP/UDP diagnostic; import starts nothing.

The checkpoint and host admission used by TCP are synthetic. The actual source
emits one non-atomic descriptor for an activation, not a proven birth. The
client uses an explicitly artificial seed/loadout. No Internet or gameplay.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import secrets
import select
import socket
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'src')]
import authority_census_archive_provenance as archive
import authority_census_replica_live as lifecycle
import authority_participant_job_install as client_install
import authority_source_single_job_install as source_install
import authority_tcp_job_x4_live as client_evidence
from authority_helper_lifecycle import OwnedHelper
from authority_tcp_native_worker import read_line,parse_json

STATE=re.compile(r'STATE (binding|attaching|await_go|observing|selected|reading|delivering|finishing|done) ([-+0-9.eE]+)\Z',re.ASCII)
_SOURCE_TAG='[X4LAN] AUTH_SOURCE_SINGLE '
_ALLOWED=re.compile(r'[A-Za-z0-9_]{1,128}\Z')


def private_fault(raw):
    if type(raw) is not bytes:raise ValueError('raw log bytes required')
    data=raw.lower()
    return any(v in data for v in (b'[x4lan] auth_source_single error',
        b'[x4lan] auth_participant_job error',b'maximum operator nesting level reached'))


class ProgressFrames:
    """Bounded private stream framing; never treat a local apply log as an ACK."""
    def __init__(self,sock):self.sock=sock;self.buffer=bytearray()
    def _pop(self):
        at=self.buffer.find(b'\n')
        if at<0:
            if len(self.buffer)>16384:raise ValueError('oversized progress frame')
            return None
        if at>16384:raise ValueError('oversized progress frame')
        frame=bytes(self.buffer[:at]);del self.buffer[:at+1]
        return frame
    def read(self,deadline,guard):
        while True:
            guard();remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('progress frame timed out')
            frame=self._pop()
            if frame is not None:return frame
            readable,_,bad=select.select([self.sock],[],[self.sock],min(remaining,.25))
            if bad:raise RuntimeError('progress socket exception')
            if not readable:continue
            data=self.sock.recv(4096)
            if not data:raise RuntimeError('progress socket closed')
            self.buffer.extend(data)
            guard()
    def available(self):
        """Read only already available bytes; incomplete/invalid suffix is unknown."""
        self.sock.setblocking(False)
        while True:
            frame=self._pop()
            if frame is not None:
                yield frame;continue
            try:data=self.sock.recv(4096,socket.MSG_DONTWAIT)
            except BlockingIOError:return
            if not data:return
            self.buffer.extend(data)



class Coordinator:
    """Serialize one private pair; all X4 and FD ownership remains external."""
    def __init__(self,candidates,*,defer_source_ack=False,max_events=1,continuous=False):
        if defer_source_ack is not True:raise ValueError('deferred source Ack required')
        if type(max_events) is not int or not 1<=max_events<=8:raise ValueError('invalid bounded event count')
        if type(continuous) is not bool or (continuous and max_events!=1):raise ValueError('invalid continuous mode')
        self.max_events=max_events;self.continuous=continuous;self.progress=[];self.progress_bytes=0;self.snapshot_finished=False
        self._used={archive.REGISTRY_EPOCH};self.attempt=self.fresh();self.generation=self.fresh()
        self.roles={};self.launches={};self.helpers=[];self.private=None;self.child=None
        self.replica_dispatch_attempted=False;self.tickets={};self.result=None
        self.source_paths=self._sources()
        self.source_fingerprints={p:lifecycle.base.stable_read(p,1<<20,collect=False)[:2] for p in self.source_paths}
        self.witnesses={name:items[0] for name,items in candidates.items() if items and _ALLOWED.fullmatch(name)}
        if not self.witnesses:raise ValueError('no usable saved-sector witnesses')

    @staticmethod
    def _sources():
        explicit=('tools/dev/authority_source_to_tcp_worker.py','tools/dev/authority_tcp_job_client_live.py',
                  'tools/dev/authority_tcp_native_worker.py','tools/dev/authority_source_job_bind.py',
                  'tools/dev/authority_helper_lifecycle.py','tools/dev/authority_exec_gate.py',
                  'tools/dev/authority_source_tcp_pair_live.py','tools/dev/authority_source_single_job_install.py',
                  'tools/dev/authority_participant_job_install.py','src/native/net.c')
        paths={ROOT/p for p in explicit}
        paths.update((ROOT/'src/authority').rglob('*.py'))
        paths.update((ROOT/'src/lockstep').rglob('*.py'))
        return tuple(sorted(paths))

    def check_sources(self):
        if self._sources()!=self.source_paths or any(
            lifecycle.base.stable_read(p,1<<20,collect=False)[:2]!=value for p,value in self.source_fingerprints.items()):
            raise ValueError('worker or dependency source changed')
        return True

    def fresh(self):
        value=secrets.token_hex(16)
        while value in self._used:value=secrets.token_hex(16)
        self._used.add(value);return value

    def add_role(self,role):
        if role not in ('server','client') or role in self.roles:raise ValueError('invalid role')
        ctl=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);job=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:
            ctl.bind(('127.0.0.1',0));job.bind(('127.0.0.1',0))
            if ctl.getsockname()==job.getsockname():raise ValueError('duplicate UDP endpoints')
            entry={'control':ctl,'job':job,'control_lease':self.fresh(),'lease':self.fresh(),'attempt':self.fresh(),'nonce':self.fresh()}
            self.roles[role]=entry;return {'role':role}
        except BaseException:
            ctl.close();job.close();raise

    def install(self,case,profile,ticket,config,nonce,timeout,window):
        self.check_sources()
        role=config.get('role')
        if role not in self.roles or role in self.tickets or ticket['world_epoch']!=self.attempt:raise ValueError('invalid private ticket')
        self.tickets[role]=dict(ticket);r=self.roles[role]
        if role=='server':
            settings={'control_port':r['control'].getsockname()[1],'control_lease':r['control_lease'],
                'job_port':r['job'].getsockname()[1],'lease':r['lease'],'attempt':r['attempt'],
                'epoch':archive.REGISTRY_EPOCH,'generation':self.generation,'descriptor_request':r['nonce'],
                'timeout':min(120,window+40),'host_timeout':20,'window':window,'capacity':128,'baseline':archive.COUNT}
            if self.continuous:settings['continuous']=True
            elif self.max_events>1:settings['max_events']=self.max_events
            files=source_install.install(case,profile,ticket,settings);self.check_sources();return files
        settings={'participant_port':r['control'].getsockname()[1],'participant_lease':r['control_lease'],
            'job_port':r['job'].getsockname()[1],'lease':r['lease'],'attempt':r['attempt'],
            'epoch':archive.REGISTRY_EPOCH,'generation':self.generation,'nonce':r['nonce'],
            'seed':7183,'timeout':25}
        files=client_install.install(case,profile,ticket,settings,self.witnesses);self.check_sources();return files

    def run(self,context):
        if set(self.launches)!= {'server','client'} or set(self.tickets)!= {'server','client'}:
            raise RuntimeError('missing launched process or load ticket')
        deadline=min(context['deadline']-5,time.monotonic()+110)
        if deadline-time.monotonic()<=40:raise TimeoutError('insufficient pair test time')
        def guard():
            if context['check']() is not True or time.monotonic()>=deadline:raise RuntimeError('pair context changed')
            self.check_sources()
            if time.monotonic()>=deadline:raise TimeoutError('source verification deadline')
            return True
        def identity(role):
            proc,started,game=self.launches[role]
            ident=lifecycle.base.load.game_identity(proc,started,game)
            if ident is None:raise RuntimeError('owned X4 unavailable')
            st=os.stat('/proc/'+str(ident[0])+'/exe')
            return {'pid':ident[0],'start_ticks':ident[1],'exe_dev':st.st_dev,'exe_ino':st.st_ino}
        guard();source=identity('server');client=identity('client');guard()
        if source['pid']==client['pid']:raise RuntimeError('source and client X4 share PID')
        self.private,self.child=socket.socketpair()
        r1,r2=self.roles['client'],self.roles['server']
        sockets=(r1['control'],r1['job'],r2['control'],r2['job'],self.child)
        fds=tuple(s.fileno() for s in sockets)
        helper=OwnedHelper([sys.executable,str(ROOT/'tools/dev/authority_source_to_tcp_worker.py'),*(str(fd) for fd in fds)],
                           registry=self.helpers,pass_fds=fds)
        for s in sockets:s.close()
        cfg={'version':1,'epoch':self.attempt,'lease':r1['lease'],'attempt':r1['attempt'],
             'generation':self.generation,'participant_lease':r1['control_lease'],'client_process':client,'deadline':deadline,
             'job_epoch':archive.REGISTRY_EPOCH,'source_lease':r2['lease'],'source_attempt':r2['attempt'],
             'source_control_lease':r2['control_lease'],'source_world_epoch':self.attempt,'source_process':source,
             'index':archive.COUNT+1,'sectors':sorted(self.witnesses)}
        if self.continuous:cfg['continuous']=True
        elif self.max_events>1:cfg['max_events']=self.max_events
        payload=json.dumps(cfg,separators=(',',':'),allow_nan=False).encode('ascii')+b'\n'
        if len(payload)>16384:raise ValueError('private worker configuration too large')
        self.private.settimeout(min(2,deadline-time.monotonic()));self.private.sendall(payload);guard()
        self.replica_dispatch_attempted=True;helper.release();guard()
        reader=ProgressFrames(self.private) if self.continuous else None
        try:
            while True:
                frame=reader.read(deadline,guard) if reader else read_line(self.private,16384,deadline,guard)
                value=parse_json(frame)
                if self.continuous and type(value) is dict and value.get('event')=='progress':
                    self._accept_progress(value,len(frame));continue
                guard();result=value;break
            self._validate_result(result)
        except BaseException:
            if reader:
                try:
                    for frame in reader.available():
                        value=parse_json(frame)
                        if type(value) is not dict or value.get('event')!='progress':break
                        self._accept_progress(value,len(frame))
                except (OSError,ValueError,RuntimeError):pass
            raise
        if self.continuous:
            self.snapshot_finished=True
            if not self.progress:raise RuntimeError('empty queue snapshot, no events applied')
        if helper.proc.wait(timeout=min(5,max(.01,deadline-time.monotonic())))!=0:
            raise RuntimeError('worker failed')
        if reader and reader.buffer:raise RuntimeError('extra buffered worker output')
        self.private.settimeout(min(1,max(.01,deadline-time.monotonic())))
        if self.private.recv(1)!=b'':raise RuntimeError('extra worker output')
        guard();self.result=result
        details=dict(tcp_ack_after_client_replica=True,ship_creation_requested=True,artificial_seed=7183,
                    source_queue_acked=True,source_activation_is_birth=False,descriptor_atomic=False,
                    frame_identity_proven=False,synthetic_tcp_checkpoint_and_admission=True)
        if self.continuous:details.update(events=self.progress,snapshot_finished=True,queue_snapshot_only=True)
        elif self.max_events>1:details['events']=result['events']
        else:details.update(source_sequence=result['event_sequence'],registry_index=result['index'],
                    source_sector=result['sector_macro'],source_macro=result['macro'],source_faction=result['faction'])
        return details

    def _accept_progress(self,frame,size):
        if (not self.continuous or type(frame) is not dict or set(frame)!={'event','completed'} or
            frame['event']!='progress' or type(size) is not int or size<1):raise ValueError('invalid progress frame')
        self._validate_event(frame['completed'],len(self.progress)+1)
        if self.progress_bytes+size>64*1024*1024:raise RuntimeError('progress artifact resource limit reached')
        self.progress_bytes+=size;self.progress.append(dict(frame['completed']))

    def _validate_result(self,r):
        fields={'event','ok','tcp_admitted','tcp_job_receipt','source_md_ack_observed','client_md_ffi_asserted_by_owner',
                'synthetic_server_checkpoint_and_admission','source_activation_is_birth','descriptor_atomic','frame_identity_proven'}
        event_fields={'event_sequence','index','sector_macro','macro','faction'}
        required=fields|({'snapshot_finished','completed_count'} if self.continuous else ({'events'} if self.max_events>1 else event_fields))
        if type(r) is not dict or set(r)!=required:raise ValueError('invalid source worker result')
        expected={'event':'result','ok':True,'tcp_admitted':True,'tcp_job_receipt':True,'source_md_ack_observed':True,
                  'client_md_ffi_asserted_by_owner':True,'synthetic_server_checkpoint_and_admission':True,
                  'source_activation_is_birth':False,'descriptor_atomic':False,'frame_identity_proven':False}
        if self.continuous and not self.progress:
            expected.update(tcp_job_receipt=False,source_md_ack_observed=False,client_md_ffi_asserted_by_owner=False)
        if any(type(r[k]) is not type(v) or r[k]!=v for k,v in expected.items()):raise ValueError('invalid source worker evidence')
        if self.continuous:
            if r['snapshot_finished'] is not True or type(r['completed_count']) is not int or r['completed_count']!=len(self.progress):
                raise ValueError('invalid source snapshot completion')
            return
        events=r['events'] if self.max_events>1 else [{k:r[k] for k in event_fields}]
        if type(events) is not list or len(events)!=self.max_events:raise ValueError('invalid source event count')
        for seq,event in enumerate(events,1):self._validate_event(event,seq)

    def _validate_event(self,event,seq):
        if (type(event) is not dict or set(event)!={'event_sequence','index','sector_macro','macro','faction'} or
            type(event['event_sequence']) is not int or event['event_sequence']!=seq or
            type(event['index']) is not int or event['index']!=archive.COUNT+seq or
            type(event['sector_macro']) is not str or event['sector_macro'] not in self.witnesses or
            any(type(event[k]) is not str or not _ALLOWED.fullmatch(event[k]) for k in ('macro','faction'))):
            raise ValueError('invalid source event descriptor or order')

    def verify_final(self,logs):
        self.check_sources()
        if set(logs)!={'server','client'} or self.result is None:raise ValueError('final pair logs missing')
        raw=logs['server'];rows=[]
        if not raw.endswith(b'\n'):raise ValueError('source log incomplete')
        for line in raw.decode('utf-8').splitlines():
            if _SOURCE_TAG in line:
                text=line.split(_SOURCE_TAG,1)[1].strip();m=STATE.fullmatch(text)
                if not m:raise ValueError('invalid source log receipt')
                t=float(m[2]);
                if not math.isfinite(t) or t<0:raise ValueError('invalid source time')
                rows.append((m[1],t))
        order=('binding','attaching','await_go','observing','selected','reading','delivering','finishing','done')
        positions=[order.index(s) for s,_ in rows]
        invalid_order=any(
            later<=earlier and not ((self.continuous or self.max_events>1) and earlier==order.index('delivering') and
                                   order.index('observing')<=later<order.index('delivering'))
            for earlier,later in zip(positions,positions[1:]))
        if (not rows or rows[0][0]!='binding' or rows[-1][0]!='done' or invalid_order or
            (not self.continuous and any(state=='finishing' for state,_ in rows)) or
            any(rows[i][1]<rows[i-1][1] for i in range(1,len(rows)))):
            raise ValueError('source state log order or time differs')
        if self.max_events==1 and not self.continuous:
            if client_evidence.observe(logs['client'],self.tickets['client'],sector=self.result['sector_macro']) is None:
                raise ValueError('client readback evidence absent')
        else:
            if client_evidence.pair.load_observation(logs['client'],self.tickets['client']) is None:
                raise ValueError('client load evidence absent')
            lines=logs['client'].decode('utf-8').splitlines()
            rows=[];pause=False
            for line in lines:
                if client_evidence.base.load.TAG.decode()+'pause_observed|' in line:pause=True
                if client_evidence.TAG in line:
                    if not pause:raise ValueError('client event before pause evidence')
                    rows.append(line.split(client_evidence.TAG,1)[1].strip())
            expected_count=len(self.progress) if self.continuous else self.max_events
            if len(rows)!=1+expected_count:raise ValueError('client apply count differs')
            m=client_evidence.RUNNING.fullmatch(rows[0]);last=float(m[1]) if m else float('nan')
            if not math.isfinite(last) or last<0:raise ValueError('invalid running evidence')
            running=last
            for seq,line in enumerate(rows[1:],1):
                m=client_evidence.APPLIED.fullmatch(line);t=float(m[2]) if m else float('nan')
                if not m or int(m[1])!=archive.COUNT+seq or not math.isfinite(t) or t<=running or t<last:
                    raise ValueError('invalid client apply order')
                last=t
        return True

    def cleanup_before_owned_processes(self):
        errors=[]
        for h in reversed(self.helpers):
            try:h.stop()
            except BaseException as e:errors.append(e)
        for s in (self.private,self.child):
            if s is not None:
                try:s.close()
                except OSError as e:errors.append(e)
        if errors:raise RuntimeError('worker cleanup unconfirmed') from errors[0]
        return True

    def cleanup_after_owned_processes(self):
        for r in self.roles.values():
            r['control'].close();r['job'].close()
        return True


def run(args):
    if not math.isfinite(args.window) or not 1<=args.window<=80:raise ValueError('invalid source window')
    count=getattr(args,'max_events',1);continuous=getattr(args,'continuous',False)
    if type(continuous) is not bool or (continuous and count!=1):raise ValueError('continuous conflicts with event count')
    if type(count) is not int or not 1<=count<=8:raise ValueError('invalid bounded event count')
    args.defer_source_ack=True;args.two_clients=False
    active=[None]
    original=(lifecycle.coordinator.CensusCoordinator,lifecycle.installer.install,
              lifecycle.owned.spawn_owned_gated,lifecycle.load_observation)
    def make(candidates,*,defer_source_ack=False):
        active[0]=Coordinator(candidates,defer_source_ack=defer_source_ack,max_events=count,continuous=continuous);return active[0]
    def install(case,profile,ticket,config,nonce,timeout,window):
        return active[0].install(case,profile,ticket,config,nonce,timeout,window)
    def spawn(command,log,processes):
        result=original[2](command,log,processes)
        role=Path(log).parent.name
        if role not in ('server','client') or role in active[0].launches:raise ValueError('unexpected owned role')
        active[0].launches[role]=(result[0],result[1],args.game.resolve(strict=True));return result
    def load(raw,ticket,*,partial=False):
        if private_fault(raw):
            raise ValueError('source or participant owner fault')
        return original[3](raw,ticket,partial=partial)
    try:
        lifecycle.coordinator.CensusCoordinator=make;lifecycle.installer.install=install
        lifecycle.owned.spawn_owned_gated=spawn;lifecycle.load_observation=load
        result=lifecycle.run(args)
        result['scope']='two isolated Linux X4; source activation to client over local TCP/UDP; synthetic admission'
        result['source_activation_is_birth']=False;result['descriptor_atomic']=False
        result['frame_identity_proven']=False;result['multiplayer_proven']=False
        if continuous and active[0] is not None:
            c=active[0]
            if not result['success']:result['completed_events_worker_reported']=c.progress
            result['queue_snapshot_finished']=c.snapshot_finished
            if not result['success']:result['inflight_event_outcome_uncertain']=True
            if c.snapshot_finished and not c.progress:result['ship_creation_requested']=False
        (Path(args.out)/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        return result
    finally:
        (lifecycle.coordinator.CensusCoordinator,lifecycle.installer.install,
         lifecycle.owned.spawn_owned_gated,lifecycle.load_observation)=original


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--store',type=Path,default=archive.DEFAULT_STORE);p.add_argument('--display',required=True)
    p.add_argument('--timeout',type=float,default=600);p.add_argument('--window',type=float,default=60)
    p.add_argument('--seed',type=int,default=276944566)
    p.add_argument('--max-events',type=int,default=1,help='opt-in bounded count, maximum 8')
    p.add_argument('--continuous',action='store_true',help='run until point-in-time queue snapshot at window end')
    try:r=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as e:p.exit(1,'REFUSED: '+str(e)+'\n')
    print(json.dumps(r,indent=2));return 0 if r['success'] else 1
if __name__=='__main__':sys.exit(main())
