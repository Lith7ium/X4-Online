"""One explicitly selected saved-registry source in a private running join.

This reads server-side motion only. It neither resolves a client counterpart
nor sends motion to a participant. Caller owns both X4 processes, all sockets,
the confirmed-checkpoint writer fence, log watching, and global failure cleanup.
"""
import copy
import math
import os
import time
from pathlib import Path

from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import ExperimentalTCPMotion
from authority_motion_ipc_supervisor import bind_running_source_motion


def run(*, sock, settings, index, baseline, guard, pump, active, host, world,
        identity, verify, verify_process, timeout=90, candidate_indices=None):
    if (((candidate_indices is None and (type(index) is not int or index<1 or index>settings['baseline'])) or
         (candidate_indices is not None and (index is not None or type(candidate_indices) is not tuple or
             not 1<=len(candidate_indices)<=32 or any(type(n) is not int or not 1<=n<=settings['baseline'] for n in candidate_indices) or
             len(set(candidate_indices))!=len(candidate_indices)))) or type(identity) is not tuple or len(identity)!=2 or
        any(type(n) is not int or n<1 for n in identity) or not callable(verify) or not callable(verify_process) or
        type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=90 or
        guard.status[:3]!=('ready',settings['epoch'],settings['baseline'])):
        raise ValueError('diagnostic source context invalid')
    pinned=world._baseline
    if (type(pinned) is not tuple or len(pinned)!=2 or pinned[1]!=baseline or
            world.session.state!='running' or world.session.pending is not None or
            world.session.baseline_id is not None):
        raise RuntimeError('running source does not retain the admitted checkpoint')
    deadline=min(guard.deadline,time.monotonic()+timeout)
    def bounded():
        if time.monotonic()>=deadline:raise TimeoutError('source diagnostic deadline')
    def active_guard():
        bounded()
        verify()
        bounded()
        return True
    def pump_guard():
        # The enclosing source IPC rechecks its full context before and after
        # each saved-guard call. While the helper hashes, only process/log and
        # client liveness need pumping; re-hashing source on each IPC byte or
        # wait poll would repeat the same check without adding a boundary.
        bounded();verify_process()
        if active.participant.check_active(server_checked=True) is not True:
            raise RuntimeError('retained client unavailable')
        verify_process();bounded()
        return True
    pump.activate(host=host,guard=pump_guard)
    active_guard()
    st=os.stat(Path('/proc')/str(identity[0])/'exe')
    process={'pid':identity[0],'start_ticks':identity[1],'exe_dev':st.st_dev,'exe_ino':st.st_ino}
    def saved(epoch,count):
        if (epoch,count)!=(settings['epoch'],settings['baseline']) or guard.status[:3]!=('ready',epoch,count):return False
        if (world._baseline!=pinned or world.session.state!='running' or
                world.session.pending is not None or world.session.baseline_id is not None):return False
        return guard.check() is True
    staged=[]
    def capture(value):
        staged.append(copy.deepcopy(value));return True
    delivery=ExperimentalTCPJobDelivery(host,enabled=True,timeout=15)
    motion=ExperimentalTCPMotion(delivery,enabled=True)
    source=bind_running_source_motion(sock,motion,process=process,lease=settings['lease'],attempt=settings['attempt'],
        epoch=settings['epoch'],generation=settings['generation'],world=world,client_guard=active_guard,timeout=timeout,
        saved_baseline=settings['baseline'],saved_guard=saved,select_recipients=lambda _sample,_members:[],
        validate_sample=capture,candidate_indices=candidate_indices)
    if candidate_indices is not None:index=source.request_candidate()
    source.register_saved(index)
    samples=[]
    for _ in range(20):
        before=len(staged)
        source.pull()
        if len(staged)>before:
            if len(staged)!=before+1:raise RuntimeError('ambiguous source sample')
            samples.append(staged[-1])
            if len(samples)==2:break
        time.sleep(.1)
    if len(samples)!=2:raise RuntimeError('two server source samples unavailable')
    if source.stop_remote() is not True:raise RuntimeError('source stop unconfirmed')
    active_guard()
    source.close()
    if guard.stop() is not True:raise RuntimeError('checkpoint guard stop unconfirmed')
    active_guard()
    public=[{key:sample[key] for key in ('sequence','sector_macro','source_time','x','y','z','velocity')} for sample in samples]
    return {'index':index,'candidate_selected':candidate_indices is not None,'candidate_is_reservation':False,
            'samples':public,'source_stopped_before_disconnect':True,
            'server_only':True,'client_motion_proven':False,'cross_process_identity_proven':False}
