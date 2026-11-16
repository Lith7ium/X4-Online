#!/usr/bin/env python3
"""Opt-in isolated two-X4 source/job/motion-to-client-buffer diagnostic.

Import starts nothing. Admission/checkpoint and client seed are synthetic; no
cross-process frame equivalence, X4 motion writer, WAN or gameplay is claimed.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import socket
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'src')]
import authority_source_tcp_pair_live as pair
import authority_census_archive_provenance as archive
import authority_census_replica_live as lifecycle
import authority_source_single_job_install as source_install
import authority_participant_motion_install as client_install
from authority.experimental_tcp_motion import motion_value
from authority.experimental_motion_pair_evidence import validate_pair
from authority_helper_lifecycle import OwnedHelper
from authority_tcp_native_worker import parse_json


def finish_worker_output(sock,reader,deadline,guard):
    """Reject both already-buffered and newly received bytes after one result."""
    guard()
    if reader.buffer:raise RuntimeError('extra buffered worker output')
    remaining=deadline-time.monotonic()
    if remaining<=0:raise TimeoutError('worker output deadline')
    sock.settimeout(min(1,remaining))
    if sock.recv(1)!=b'':raise RuntimeError('extra worker output')
    guard()


class MotionCoordinator(pair.Coordinator):
    """Reuse the saved-world/process lifecycle; add two private motion sockets."""
    @staticmethod
    def _sources():
        paths=set(pair.Coordinator._sources()) | {
            ROOT/'tools/dev/authority_source_motion_pair_live.py',
            ROOT/'tools/dev/authority_source_motion_tcp_worker.py',
            ROOT/'tools/dev/authority_motion_ipc_supervisor.py',
            ROOT/'tools/dev/authority_participant_motion_install.py',
            ROOT/'src/authority/lua/source_motion_ipc.lua',
            ROOT/'src/authority/lua/source_motion_sampler.lua',
            ROOT/'src/authority/lua/replica_motion_binding.lua',
            ROOT/'src/authority/lua/motion_client_owner.lua',
            ROOT/'src/authority/lua/motion_buffer.lua',
            ROOT/'src/authority/lua/saved_baseline_source_bootstrap.lua',
            ROOT/'src/authority/lua/saved_baseline_motion_binding.lua',
            ROOT/'tools/dev/authority_saved_baseline_motion_bind.xml',
            ROOT/'src/authority/lua/client_load_barrier.lua',
            ROOT/'src/authority/lua/x4_client_load_engine.lua',
            ROOT/'src/lockstep/base/ui/sha256.lua',
            ROOT/'tools/dev/authority_download_load_probe.lua',
            ROOT/'tools/dev/authority_replica_motion_bind.xml',
            ROOT/'tools/dev/authority_multi_create_receiver.xml'}
        paths.update(ROOT/source for source,_ in source_install.UI)
        paths.update(ROOT/source for source,_,_ in client_install.base.MODULES)
        paths.update(archive.saved_state_script(name) if name in source_install.BASE_MD
                     else ROOT/'tools/dev'/name for name in source_install.MD)
        return tuple(sorted(paths))

    def __init__(self,candidates,*,defer_source_ack=False,motion_count=1,saved_index=None):
        if type(motion_count) is not int or motion_count not in (1,2):raise ValueError('invalid bounded motion count')
        super().__init__(candidates,defer_source_ack=defer_source_ack)
        self.motion_count=motion_count
        # Probe all saved candidates but do not require the diagnostic fallback
        # itself to happen: this test targets one motion binding.
        self.witnesses={name:tuple(items) for name,items in candidates.items()
                        if items and pair._ALLOWED.fullmatch(name)}
        if not self.witnesses:raise ValueError('no saved sector witnesses')
        self.saved_index=saved_index;self.saved_sector=None
        if saved_index is not None:
            matches=[name for name,items in self.witnesses.items() if saved_index in items]
            if type(saved_index) is not int or not 1<=saved_index<=archive.COUNT or len(matches)!=1:
                raise ValueError('saved index must be uniquely present in pinned census')
            self.saved_sector=matches[0]

    def add_role(self,role):
        value=super().add_role(role);r=self.roles[role]
        try:
            motion=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);motion.bind(('127.0.0.1',0))
            r.update(motion=motion,motion_lease=self.fresh(),motion_attempt=self.fresh(),motion_nonce=self.fresh())
            while r['motion_nonce'][:16]==r['nonce'][:16]:r['motion_nonce']=self.fresh()
            if role=='server' and self.saved_index is not None:
                r['saved_nonce']=self.fresh()
                while r['saved_nonce'][:16] in (r['nonce'][:16],r['motion_nonce'][:16]):r['saved_nonce']=self.fresh()
            return value
        except BaseException:
            if 'motion' in locals():motion.close()
            r['control'].close();r['job'].close();del self.roles[role];raise

    def install(self,case,profile,ticket,config,nonce,timeout,window):
        self.check_sources();role=config.get('role')
        if role not in self.roles or role in self.tickets or ticket['world_epoch']!=self.attempt:raise ValueError('invalid private ticket')
        self.tickets[role]=dict(ticket);r=self.roles[role]
        if role=='server':
            settings={'control_port':r['control'].getsockname()[1],'control_lease':r['control_lease'],
                'job_port':r['job'].getsockname()[1],'lease':r['lease'],'attempt':r['attempt'],
                'epoch':archive.REGISTRY_EPOCH,'generation':self.generation,'descriptor_request':r['nonce'],
                'timeout':min(120,window+40),'host_timeout':20,'window':window,'capacity':128,'baseline':archive.COUNT,
                'motion':{'port':r['motion'].getsockname()[1],'lease':r['motion_lease'],
                          'attempt':r['motion_attempt'],'nonce':r['motion_nonce']}}
            if self.saved_index is not None:settings['saved_nonce']=r['saved_nonce']
            files=source_install.install(case,profile,ticket,settings)
        else:
            settings={'participant_port':r['control'].getsockname()[1],'participant_lease':r['control_lease'],
                'job_port':r['job'].getsockname()[1],'lease':r['lease'],'attempt':r['attempt'],
                'epoch':archive.REGISTRY_EPOCH,'generation':self.generation,'nonce':r['nonce'],
                'seed':7183,'timeout':25,'multi_witness':True}
            motion={'port':r['motion'].getsockname()[1],'lease':r['motion_lease'],'attempt':r['motion_attempt'],
                'epoch':archive.REGISTRY_EPOCH,'generation':self.generation,'nonce':r['motion_nonce'],
                'timeout':15,'max_age':15,'max_tracks':1024}
            if self.saved_index is not None:motion['saved_baseline']=True
            motion=self.motion_settings(motion)
            files=client_install.install(case,profile,ticket,settings,self.witnesses,motion)
        self.check_sources();return files

    def run(self,context):
        if set(self.launches)!={'server','client'} or set(self.tickets)!={'server','client'}:raise RuntimeError('missing pair')
        deadline=min(context['deadline']-5,time.monotonic()+110)
        if deadline-time.monotonic()<=40:raise TimeoutError('insufficient pair test time')
        def guard():
            if context['check']() is not True or time.monotonic()>=deadline:raise RuntimeError('pair context changed')
            self.check_sources()
            if time.monotonic()>=deadline:raise TimeoutError('source verification deadline')
            return True
        def identity(role):
            proc,started,game=self.launches[role];ident=lifecycle.base.load.game_identity(proc,started,game)
            if ident is None:raise RuntimeError('owned X4 unavailable')
            st=os.stat('/proc/'+str(ident[0])+'/exe')
            return {'pid':ident[0],'start_ticks':ident[1],'exe_dev':st.st_dev,'exe_ino':st.st_ino}
        guard();source=identity('server');client=identity('client');guard()
        if source['pid']==client['pid']:raise RuntimeError('source and client X4 share PID')
        self.private,self.child=socket.socketpair();c,s=self.roles['client'],self.roles['server']
        sockets=(c['control'],c['job'],c['motion'],s['control'],s['job'],s['motion'],self.child)
        fds=tuple(x.fileno() for x in sockets)
        helper=OwnedHelper([sys.executable,str(ROOT/'tools/dev/authority_source_motion_tcp_worker.py'),*(str(fd) for fd in fds)],registry=self.helpers,pass_fds=fds)
        for x in sockets:x.close()
        cfg={'version':1,'epoch':self.attempt,'lease':c['lease'],'attempt':c['attempt'],
             'generation':self.generation,'participant_lease':c['control_lease'],'client_process':client,'deadline':deadline,
             'job_epoch':archive.REGISTRY_EPOCH,'source_lease':s['lease'],'source_attempt':s['attempt'],
             'source_control_lease':s['control_lease'],'source_world_epoch':self.attempt,'source_process':source,
             'index':archive.COUNT+1,'sectors':sorted(self.witnesses),
             'client_motion_lease':c['motion_lease'],'client_motion_attempt':c['motion_attempt'],
             'source_motion_lease':s['motion_lease'],'source_motion_attempt':s['motion_attempt']}
        if self.motion_count==2:cfg['motion_count']=2
        if self.saved_index is not None:
            cfg.update(saved_index=self.saved_index,saved_baseline=archive.COUNT,saved_sector=self.saved_sector)
        cfg=self.worker_config(cfg)
        payload=json.dumps(cfg,separators=(',',':'),allow_nan=False).encode('ascii')+b'\n'
        if len(payload)>16384:raise ValueError('private worker configuration too large')
        self.private.settimeout(min(2,deadline-time.monotonic()));self.private.sendall(payload);guard()
        self.replica_dispatch_attempted=self.saved_index is None;helper.release();guard()
        reader=pair.ProgressFrames(self.private)
        result=parse_json(reader.read(deadline,guard));guard();self._validate_motion_result(result)
        if helper.proc.wait(timeout=min(5,max(.01,deadline-time.monotonic())))!=0:raise RuntimeError('worker failed')
        finish_worker_output(self.private,reader,deadline,guard)
        guard();self.result=result
        if self.saved_index is None:
            self.output_details=dict(tcp_ack_after_client_replica=True,ship_creation_requested=True,artificial_seed=7183,
                source_queue_acked=True,source_activation_is_birth=False,descriptor_atomic=False,frame_identity_proven=False,
                synthetic_tcp_checkpoint_and_admission=True,motion_client_bound_buffered=True,motion_pose_applied=False)
        else:
            self.output_details=dict(saved_baseline_registered=True,saved_index=self.saved_index,
                saved_sector=self.saved_sector,checkpoint_identity_proven=False,frame_identity_proven=False,
                synthetic_tcp_checkpoint_and_admission=True,motion_client_bound_buffered=True,motion_pose_applied=False)
        key='motion_sample' if self.motion_count==1 else 'motion_samples'
        self.output_details[key]=result[key]
        return self.output_details

    def motion_settings(self,settings):return settings
    def worker_config(self,config):return config

    def _validate_motion_result(self,result):
        key='motion_sample' if self.motion_count==1 else 'motion_samples'
        extra={key,'motion_client_bound_buffered','motion_velocity_source','motion_frame_identity_proven'}
        if type(result) is not dict or not extra<=set(result):raise ValueError('missing motion result')
        if self.saved_index is None:self._validate_result({k:v for k,v in result.items() if k not in extra})
        else:
            expected={'event':'result','ok':True,'tcp_admitted':True,'saved_baseline_registered':True,
                'synthetic_server_checkpoint_and_admission':True,'checkpoint_identity_proven':False,
                'frame_identity_proven':False,'motion_pose_applied':False,'index':self.saved_index,'sector_macro':self.saved_sector}
            if set(result)!=set(expected)|extra or any(type(result[k]) is not type(v) or result[k]!=v for k,v in expected.items()):
                raise ValueError('invalid saved baseline worker evidence')
        if result['motion_client_bound_buffered'] is not True or result['motion_frame_identity_proven'] is not False or result['motion_velocity_source']!='position_difference_per_source_game_second':raise ValueError('invalid motion evidence')
        if self.motion_count==2:
            validate_pair(result[key],epoch=archive.REGISTRY_EPOCH,generation=self.generation,index=result['index'],sector=result['sector_macro'])
        else:
            sample=motion_value(result[key])
            if sample['epoch']!=archive.REGISTRY_EPOCH or sample['generation']!=self.generation or sample['index']!=result['index'] or sample['sequence']!=1 or sample['sector_macro']!=result['sector_macro'] or sample['velocity'] is not None:
                raise ValueError('motion identity or initial velocity differs from confirmed job')

    def verify_final(self,logs):
        if self.saved_index is None:super().verify_final(logs)
        else:
            self.check_sources()
            if set(logs)!={'server','client'} or self.result is None:raise ValueError('final saved pair logs missing')
            for role in ('server','client'):
                if lifecycle.load_observation(logs[role],self.tickets[role]) is None:raise ValueError('saved pair load evidence missing')
            raw=logs['server'];rows=[]
            if not raw.endswith(b'\n'):raise ValueError('source log incomplete')
            for line in raw.decode('utf-8').splitlines():
                if pair._SOURCE_TAG in line:
                    match=pair.STATE.fullmatch(line.split(pair._SOURCE_TAG,1)[1].strip())
                    if not match:raise ValueError('invalid source status')
                    rows.append((match[1],float(match[2])))
            allowed=('binding','attaching','await_go','observing')
            if (not rows or rows[0][0]!='binding' or rows[-1][0]!='observing' or
                any(name not in allowed or not math.isfinite(t) or t<0 for name,t in rows) or
                any(allowed.index(b[0])<=allowed.index(a[0]) or b[1]<a[1] for a,b in zip(rows,rows[1:]))):
                raise ValueError('source left saved observation phase')
            if b'AUTH_PARTICIPANT_JOB LOCAL_APPLIED ' in logs['client']:
                raise ValueError('unexpected job creation in saved diagnostic')
            running=False
            for line in logs['client'].decode('utf-8').splitlines():
                if '[X4LAN] AUTH_PARTICIPANT_JOB RUNNING ' in line:
                    if running:raise ValueError('duplicate running evidence')
                    text=line.split('[X4LAN] AUTH_PARTICIPANT_JOB RUNNING ',1)[1].strip()
                    t=float(text)
                    if not math.isfinite(t) or t<0:raise ValueError('invalid running time')
                    running=True
                if '[X4LAN] AUTH_PARTICIPANT_MOTION BUFFERED ' in line and not running:
                    raise ValueError('motion before running evidence')
            if not running:raise ValueError('client running evidence absent')
        tag='[X4LAN] AUTH_PARTICIPANT_MOTION BUFFERED '
        pattern=re.compile(r'([1-9][0-9]*) ([1-9][0-9]*) ([A-Za-z0-9_]{1,128}) ([-+0-9.eE]+)\Z',re.ASCII)
        rows=[]
        for line in logs['client'].decode('utf-8').splitlines():
            if tag in line:
                match=pattern.fullmatch(line.split(tag,1)[1].strip())
                if not match:raise ValueError('invalid client motion buffer evidence')
                try:value=float(match[4])
                except ValueError:raise ValueError('invalid client motion source time') from None
                if not math.isfinite(value):raise ValueError('invalid client motion source time')
                rows.append((int(match[1]),int(match[2]),match[3],value))
        samples=[self.result['motion_sample']] if self.motion_count==1 else self.result['motion_samples']
        if rows!=[(sample['index'],sample['sequence'],sample['sector_macro'],sample['source_time']) for sample in samples]:
            raise ValueError('client buffer log differs from motion result')
        return True

    def cleanup_after_owned_processes(self):
        try:return super().cleanup_after_owned_processes()
        finally:
            for r in self.roles.values():r['motion'].close()


def run(args):
    if not math.isfinite(args.window) or not 1<=args.window<=80:raise ValueError('invalid source window')
    args.defer_source_ack=True;args.two_clients=False;active=[None]
    original=(lifecycle.coordinator.CensusCoordinator,lifecycle.installer.install,lifecycle.owned.spawn_owned_gated,lifecycle.load_observation)
    def make(candidates,*,defer_source_ack=False):
        active[0]=MotionCoordinator(candidates,defer_source_ack=defer_source_ack,motion_count=getattr(args,'motion_count',1),
                                    saved_index=getattr(args,'saved_index',None));return active[0]
    def install(case,profile,ticket,config,nonce,timeout,window):return active[0].install(case,profile,ticket,config,nonce,timeout,window)
    def spawn(command,log,processes):
        result=original[2](command,log,processes);role=Path(log).parent.name
        if role not in ('server','client') or role in active[0].launches:raise ValueError('unexpected owned role')
        active[0].launches[role]=(result[0],result[1],args.game.resolve(strict=True));return result
    def load(raw,ticket,*,partial=False):
        if pair.private_fault(raw):raise ValueError('source or participant owner fault')
        return original[3](raw,ticket,partial=partial)
    try:
        lifecycle.coordinator.CensusCoordinator=make;lifecycle.installer.install=install
        lifecycle.owned.spawn_owned_gated=spawn;lifecycle.load_observation=load
        result=lifecycle.run(args)
        if getattr(args,'saved_index',None) is None:
            result.update(scope='two isolated Linux X4; source job and read-only motion samples to client hold buffer',
                          source_activation_is_birth=False,descriptor_atomic=False,frame_identity_proven=False,
                          motion_pose_applied=False,multiplayer_proven=False)
        else:
            result.update(scope='two isolated Linux X4; saved registry read-only motion to client hold buffer',
                          checkpoint_identity_proven=False,descriptor_atomic=False,frame_identity_proven=False,
                          motion_pose_applied=False,multiplayer_proven=False)
        (Path(args.out)/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        return result
    finally:
        (lifecycle.coordinator.CensusCoordinator,lifecycle.installer.install,lifecycle.owned.spawn_owned_gated,lifecycle.load_observation)=original


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--store',type=Path,default=archive.DEFAULT_STORE);p.add_argument('--display',required=True)
    p.add_argument('--timeout',type=float,default=600);p.add_argument('--window',type=float,default=60)
    p.add_argument('--seed',type=int,default=276944566)
    p.add_argument('--motion-count',type=int,choices=(1,2),default=1,help='bounded read-only samples for one confirmed source actor')
    p.add_argument('--saved-index',type=int,help='opt-in one saved census index; no job or create receipt')
    try:result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as e:p.exit(1,'REFUSED: '+str(e)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1
if __name__=='__main__':sys.exit(main())
