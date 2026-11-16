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
from authority_helper_lifecycle import OwnedHelper
from authority_tcp_native_worker import read_line,parse_json


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

    def __init__(self,candidates,*,defer_source_ack=False):
        super().__init__(candidates,defer_source_ack=defer_source_ack)
        # Probe all saved candidates but do not require the diagnostic fallback
        # itself to happen: this test targets one motion binding.
        self.witnesses={name:tuple(items) for name,items in candidates.items()
                        if items and pair._ALLOWED.fullmatch(name)}
        if not self.witnesses:raise ValueError('no saved sector witnesses')

    def add_role(self,role):
        value=super().add_role(role);r=self.roles[role]
        try:
            motion=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);motion.bind(('127.0.0.1',0))
            r.update(motion=motion,motion_lease=self.fresh(),motion_attempt=self.fresh(),motion_nonce=self.fresh())
            while r['motion_nonce'][:16]==r['nonce'][:16]:r['motion_nonce']=self.fresh()
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
            files=source_install.install(case,profile,ticket,settings)
        else:
            settings={'participant_port':r['control'].getsockname()[1],'participant_lease':r['control_lease'],
                'job_port':r['job'].getsockname()[1],'lease':r['lease'],'attempt':r['attempt'],
                'epoch':archive.REGISTRY_EPOCH,'generation':self.generation,'nonce':r['nonce'],
                'seed':7183,'timeout':25,'multi_witness':True}
            motion={'port':r['motion'].getsockname()[1],'lease':r['motion_lease'],'attempt':r['motion_attempt'],
                'epoch':archive.REGISTRY_EPOCH,'generation':self.generation,'nonce':r['motion_nonce'],
                'timeout':15,'max_age':15,'max_tracks':1024}
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
        payload=json.dumps(cfg,separators=(',',':'),allow_nan=False).encode('ascii')+b'\n'
        if len(payload)>16384:raise ValueError('private worker configuration too large')
        self.private.settimeout(min(2,deadline-time.monotonic()));self.private.sendall(payload);guard()
        self.replica_dispatch_attempted=True;helper.release();guard()
        result=parse_json(read_line(self.private,16384,deadline,guard));guard();self._validate_motion_result(result)
        if helper.proc.wait(timeout=min(5,max(.01,deadline-time.monotonic())))!=0:raise RuntimeError('worker failed')
        self.private.settimeout(min(1,max(.01,deadline-time.monotonic())))
        if self.private.recv(1)!=b'':raise RuntimeError('extra worker output')
        guard();self.result=result
        self.output_details=dict(tcp_ack_after_client_replica=True,ship_creation_requested=True,artificial_seed=7183,
            source_queue_acked=True,source_activation_is_birth=False,descriptor_atomic=False,frame_identity_proven=False,
            synthetic_tcp_checkpoint_and_admission=True,motion_sample=result['motion_sample'],
            motion_client_bound_buffered=True,motion_pose_applied=False)
        return self.output_details

    def _validate_motion_result(self,result):
        extra={'motion_sample','motion_client_bound_buffered','motion_velocity_source','motion_frame_identity_proven'}
        if type(result) is not dict or not extra<=set(result):raise ValueError('missing motion result')
        self._validate_result({k:v for k,v in result.items() if k not in extra})
        if result['motion_client_bound_buffered'] is not True or result['motion_frame_identity_proven'] is not False or result['motion_velocity_source']!='position_difference_per_source_game_second':raise ValueError('invalid motion evidence')
        sample=motion_value(result['motion_sample'])
        if sample['epoch']!=archive.REGISTRY_EPOCH or sample['generation']!=self.generation or sample['index']!=result['index'] or sample['sequence']!=1 or sample['sector_macro']!=result['sector_macro']:
            raise ValueError('motion identity differs from confirmed job')

    def verify_final(self,logs):
        super().verify_final(logs)
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
        sample=self.result['motion_sample']
        if rows!=[(sample['index'],sample['sequence'],sample['sector_macro'],sample['source_time'])]:
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
        active[0]=MotionCoordinator(candidates,defer_source_ack=defer_source_ack);return active[0]
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
        result.update(scope='two isolated Linux X4; source job and one read-only motion sample to client hold buffer',
                      source_activation_is_birth=False,descriptor_atomic=False,frame_identity_proven=False,
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
    try:result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as e:p.exit(1,'REFUSED: '+str(e)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1
if __name__=='__main__':sys.exit(main())
