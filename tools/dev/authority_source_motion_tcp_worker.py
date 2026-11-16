#!/usr/bin/env python3
"""Opt-in one-job/one-motion diagnostic worker; no process or listener starts.

All X4/profile lifecycle, PID identities, socket FDs, cleanup and failure
fencing belong to the outer supervisor. TCP checkpoint/admission are synthetic.
"""
import json
from pathlib import Path
import re
import select
import socket
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_source_to_tcp_worker as base
import authority_tcp_job_client_live as client_worker
from authority_tcp_native_worker import check_process, parse_json, read_line, send_frame
from authority_source_job_bind import bind_source, authorize_source
from authority_motion_ipc_supervisor import bind_source_motion
from authority.experimental_job_motion_scheduler import ExperimentalJobMotionScheduler
from authority.experimental_tcp_motion import ExperimentalTCPMotion
from authority.experimental_motion_pair_evidence import validate_pair
from authority.local_participant_control import LocalParticipantControl

_EXTRA=('client_motion_lease','client_motion_attempt','source_motion_lease','source_motion_attempt')
_SAVED=('saved_index','saved_baseline','saved_sector')
_TOKEN=re.compile(r'[0-9a-f]{32}\Z')

def config(raw):
    all_values=parse_json(raw)
    if type(all_values) is not dict or any(k not in all_values for k in _EXTRA):raise ValueError('missing motion context')
    extras={k:all_values[k] for k in _EXTRA}
    if any(type(v) is not str or not _TOKEN.fullmatch(v) for v in extras.values()):raise ValueError('invalid motion context')
    count=all_values.get('motion_count',1)
    if type(count) is not int or count not in (1,2):raise ValueError('invalid bounded motion count')
    apply_once=all_values.get('apply_once',False)
    if type(apply_once) is not bool or ('apply_once' in all_values and apply_once is not True):raise ValueError('invalid apply opt-in')
    saved={k:all_values[k] for k in _SAVED if k in all_values}
    if saved:
        if (set(saved)!=set(_SAVED) or type(saved['saved_baseline']) is not int or
            type(saved['saved_index']) is not int or not 1<=saved['saved_index']<=saved['saved_baseline']<=9007199254740991 or
            type(saved['saved_sector']) is not str or not base._NAME.fullmatch(saved['saved_sector'])):
            raise ValueError('invalid saved baseline context')
    if apply_once and (not saved or count!=1):raise ValueError('one-shot apply requires one saved sample')
    rest={k:v for k,v in all_values.items() if k not in _EXTRA and k not in _SAVED and k not in ('motion_count','apply_once')}
    if 'continuous' in rest or 'max_events' in rest:raise ValueError('single job diagnostic required')
    c=base.config(json.dumps(rest,separators=(',',':'),allow_nan=False).encode())
    names=('epoch','lease','attempt','generation','participant_lease','job_epoch','source_lease','source_attempt','source_control_lease')
    values=[c[k] for k in names]+list(extras.values())
    if len(set(values))!=len(values):raise ValueError('motion tokens overlap session context')
    c.update(extras);c.update(saved);c['motion_count']=count;c['apply_once']=apply_once
    if saved and saved['saved_sector'] not in c['sectors']:raise ValueError('saved sector is not witnessed')
    return c


def run(client_control,client_job,client_motion,source_control,source_job,source_motion,private,c):
    sockets=(client_control,client_job,client_motion,source_control,source_job,source_motion)
    for sock in sockets:client_worker.validate_udp(sock)
    if len({s.getsockname() for s in sockets})!=len(sockets):raise ValueError('distinct local UDP ports required')
    identity=dict(c['source_process']);job_peer=control_peer=motion_peer=None;scheduler=None
    def source_guard():
        check_process(identity)
        for sock,peer in ((source_job,job_peer),(source_motion,motion_peer)):
            if peer is not None and (sock.getpeername()!=peer or not client_worker.socket_owner(peer,sock.getsockname(),identity)):
                raise RuntimeError('source UDP ownership changed')
        if control_peer is not None and not client_worker.socket_owner(control_peer,source_control.getsockname(),identity):
            raise RuntimeError('source control ownership changed')
        check_process(identity);return True
    def action(delivery,members,guard):
        nonlocal job_peer,control_peer,motion_peer,scheduler
        source_control.settimeout(.1)
        expected=('HELLO|'+c['source_control_lease']+'|'+c['source_world_epoch']).encode('ascii')
        while control_peer is None:
            guard()
            try:packet,peer=source_control.recvfrom(769)
            except socket.timeout:continue
            if packet!=expected or not client_worker.socket_owner(peer,source_control.getsockname(),identity):
                raise RuntimeError('source control peer unconfirmed')
            control_peer=peer
        left=c['deadline']-time.monotonic()
        if left<=45:raise TimeoutError('insufficient motion session budget')
        bound=bind_source(source_job,process=identity,lease=c['source_lease'],attempt=c['source_attempt'],
            epoch=c['job_epoch'],generation=c['generation'],guard=guard,timeout=min(20,left-40))
        if bound is not source_job:raise RuntimeError('job source handoff differs')
        job_peer=source_job.getpeername();guard()
        authorize_source(source_job,process=identity,lease=c['source_lease'],attempt=c['source_attempt'],
            epoch=c['job_epoch'],generation=c['generation'],guard=guard,timeout=min(10,c['deadline']-time.monotonic()-40))
        job=base.SelectedSourceBridge(delivery,source_job,enabled=True,lease=c['source_lease'],attempt=c['source_attempt'],
            epoch=c['job_epoch'],generation=c['generation'],guard=guard,timeout=min(90,c['deadline']-time.monotonic()-1),
            expected_index=c['index'],sectors=c['sectors'])
        motion=ExperimentalTCPMotion(delivery,enabled=True,allow_apply=c['apply_once'])
        event=None;samples=[];saved='saved_index' in c
        def validate_sample(value):
            target=c['saved_index'] if saved else (event['index'] if event is not None else None)
            sector=c['saved_sector'] if saved else (event['descriptor']['sector_macro'] if event is not None else None)
            if target is None or value['index']!=target or value['sequence']!=len(samples)+1:
                return False
            if value['epoch']!=c['job_epoch'] or value['generation']!=c['generation'] or value['sector_macro']!=sector:
                return False
            if not samples:return value['velocity'] is None
            if c['motion_count']!=2 or len(samples)!=1:return False
            validate_pair([samples[0],value],epoch=c['job_epoch'],generation=c['generation'],index=target,sector=sector)
            return True
        def saved_guard(epoch,baseline):
            if epoch!=c['job_epoch'] or baseline!=c['saved_baseline'] or guard() is not True:return False
            readable,_,bad=select.select([source_job],[],[source_job],0)
            return not readable and not bad and guard() is True
        source=bind_source_motion(source_motion,motion,process=identity,lease=c['source_motion_lease'],
            attempt=c['source_motion_attempt'],epoch=c['job_epoch'],generation=c['generation'],guard=guard,
            timeout=min(35,c['deadline']-time.monotonic()-1),validate_sample=validate_sample,
            saved_baseline=c['saved_baseline'] if saved else None,saved_guard=saved_guard if saved else None)
        motion_peer=source_motion.getpeername();guard()
        scheduler=ExperimentalJobMotionScheduler(job,source,enabled=True)
        ctl=LocalParticipantControl.__new__(LocalParticipantControl)
        ctl.sock=source_control;ctl.lease=c['source_control_lease'];ctl.peer=control_peer
        ctl.epoch=c['source_world_epoch'];ctl.handle=1;ctl.next_id=1;ctl.fault=False
        ctl.timeout=min(20,c['deadline']-time.monotonic()-35)
        if ctl.timeout<=0:raise TimeoutError('source resume budget expired')
        guard();ctl.resume((1,));guard()
        if saved:
            guard();scheduler.register_saved(c['saved_index']);guard()
        while len(samples)<c['motion_count']:
            guard()
            if saved:kind,value='motion',scheduler.step_motion_only()
            else:kind,value=scheduler.step()
            guard()
            if kind=='job_snapshot_finished':raise RuntimeError('source ended before motion sample')
            if kind=='job':
                if event is not None:raise RuntimeError('unexpected second job in single-job diagnostic')
                if value['index']!=c['index'] or value['sequence']!=1:raise RuntimeError('unexpected source job')
                event=value
            elif value is not None:
                if (not saved and event is None) or value['index']!=(c['saved_index'] if saved else event['index']) or value['sequence']!=len(samples)+1:
                    raise RuntimeError('motion without completed job or out of sequence')
                samples.append(value)
        if saved:
            if c['apply_once']:
                guard();scheduler.apply_once(samples[0]);guard()
            if c['motion_count']==2:
                samples=validate_pair(samples,epoch=c['job_epoch'],generation=c['generation'],index=c['saved_index'],sector=c['saved_sector'])
            result={'event':'result','ok':True,'tcp_admitted':True,'synthetic_server_checkpoint_and_admission':True,
                    'saved_baseline_registered':True,'index':c['saved_index'],'sector_macro':c['saved_sector'],
                    'checkpoint_identity_proven':False,'frame_identity_proven':False,'motion_pose_applied':c['apply_once'],
                    'motion_client_bound_buffered':True,'motion_velocity_source':'position_difference_per_source_game_second',
                    'motion_frame_identity_proven':False}
            if c['motion_count']==1:result['motion_sample']=samples[0]
            else:result['motion_samples']=samples
            return result
        if c['motion_count']==2:
            samples=validate_pair(samples,epoch=c['job_epoch'],generation=c['generation'],index=event['index'],
                                  sector=event['descriptor']['sector_macro'])
        result={'event':'result','ok':True,'tcp_admitted':True,'tcp_job_receipt':True,'source_md_ack_observed':True,
                'client_md_ffi_asserted_by_owner':True,'synthetic_server_checkpoint_and_admission':True,
                'source_activation_is_birth':False,'descriptor_atomic':False,'frame_identity_proven':False,
                'event_sequence':event['sequence'],'index':event['index'],
                'sector_macro':event['descriptor']['sector_macro'],'macro':event['descriptor']['macro'],
                'faction':event['descriptor']['faction'],'motion_client_bound_buffered':True,
                'motion_velocity_source':'position_difference_per_source_game_second','motion_frame_identity_proven':False}
        if c['motion_count']==1:result['motion_sample']=samples[0]
        else:result['motion_samples']=samples
        return result
    try:
        return client_worker.run(client_control,client_job,private,c,None,delivery_action=action,
                                 extra_guard=source_guard,expected_jobs=None,motion_udp=client_motion,allow_motion_apply=c['apply_once'])
    finally:
        if scheduler is not None and scheduler.state=='ready':scheduler.close()


def main():
    if len(sys.argv)!=8:return 2
    private=None
    try:
        cc,cj,cm,sc,sj,sm,private=(socket.socket(fileno=int(v)) for v in sys.argv[1:])
        c=config(read_line(private,16384,time.monotonic()+30));result=run(cc,cj,cm,sc,sj,sm,private,c)
        send_frame(private,json.dumps(result,separators=(',',':'),allow_nan=False).encode('ascii'),c['deadline'],
                   lambda:(check_process(c['source_process']),check_process(c['client_process'])))
        return 0
    except BaseException:
        try:
            if private is not None:private.sendall(b'{"event":"result","ok":false}\n')
        except BaseException:pass
        return 1
if __name__=='__main__':sys.exit(main())
