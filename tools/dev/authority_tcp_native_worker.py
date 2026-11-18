#!/usr/bin/env python3
"""One opt-in Linux native-client worker; no X4 is started by this module.

The parent gives this process exclusive ownership of three inherited sockets.
An explicit diagnostic opt-in adds a fourth, separate motion UDP socket, used
either for received motion or for one fixture player's read-only source.
All secrets travel over the private IPC socket, never argv or standard output.

The three argv values are inherited TCP, UDP and private AF_UNIX stream FDs.
One newline-delimited IPC config contains exactly: version=1; claim (encoded
JSON string); epoch, handle, lease, udp_peer=[host,port], udp_next_id; deadline
(absolute Linux monotonic seconds); controller_timeout; client_process containing
pid/start_ticks/exe_dev/exe_ino. After a matching admission ACK the worker emits
{"event":"active"}. The sole IPC request is {"command":"stop"}; normal closure
emits {"event":"stopped"}, failure emits {"event":"failed"} if possible.
An active acknowledgement or process sample is not independent authentication,
continuous liveness or proof of X4 state. A stop received during a synchronous
operation aborts its receipt once that operation returns; it cannot interrupt
the UDP operation. The parent must fence the helper and X4 after uncertainty,
and establish the FD/process identities and exclusive ownership before release.
"""
import json
import math
import os
from pathlib import Path
import re
import select
import socket
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient
from authority.local_participant_control import LocalParticipantControl
from authority.load_messages import MAX_INTEGER, MAX_MESSAGE, _pairs, _reject_constant
from authority.trusted_load_messages import decode_load_claim
from authority.experimental_participant_motion_ipc import ExperimentalParticipantMotionIPC
from authority.experimental_tcp_motion import motion_value
from authority.experimental_tcp_client_authority_motion import grant_value

MAX_CONFIG=16384
MAX_IPC=256
_HEX=re.compile(r'[0-9a-f]{32}\Z')
RECOVERY_SETTER_FIXTURE = 'recovery_enh_870'
RECOVERY_SETTER_EPOCH = '4ba7be438ebb04ec5bb85fdb95b5a488'
RECOVERY_SETTER_INDEX = 1318


def parse_json(raw):
    try: return json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs,parse_constant=_reject_constant)
    except (UnicodeError,json.JSONDecodeError,RecursionError) as error: raise ValueError('invalid JSON') from error


def finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def check_process(expected):
    """Point-in-time Linux identity, not proof of owned process-group membership."""
    if type(expected) is not dict or set(expected)!={'pid','start_ticks','exe_dev','exe_ino'}:
        raise ValueError('invalid process identity')
    if any(type(expected[k]) is not int or expected[k]<0 for k in expected):
        raise ValueError('invalid process identity')
    if expected['pid']<1 or expected['exe_ino']<1: raise ValueError('invalid process identity')
    proc=Path('/proc')/str(expected['pid'])
    if proc.stat().st_uid!=os.geteuid(): raise RuntimeError('client process owner changed')
    fields=(proc/'stat').read_text().rsplit(')',1)[1].split()
    image=(proc/'exe').stat()
    if (fields[0] in ('Z','X','x') or int(fields[19])!=expected['start_ticks'] or
            image.st_dev!=expected['exe_dev'] or image.st_ino!=expected['exe_ino']):
        raise RuntimeError('client process identity changed')


def config_value(raw):
    obj=parse_json(raw)
    fields={'version','claim','epoch','handle','lease','udp_peer','udp_next_id','deadline',
            'controller_timeout','client_process'}
    if (type(obj) is not dict or not fields<=set(obj) or set(obj)-fields-{'already_admitted','motion','client_authority'} or
            type(obj['version']) is not int or obj['version']!=1):
        raise ValueError('invalid worker configuration')
    if 'motion' in obj and 'client_authority' in obj:
        raise ValueError('motion socket has more than one owner')
    if 'already_admitted' in obj and obj['already_admitted'] is not True:
        raise ValueError('invalid handoff state')
    if (type(obj['epoch']) is not str or not _HEX.fullmatch(obj['epoch']) or
            type(obj['lease']) is not str or not _HEX.fullmatch(obj['lease']) or
            type(obj['handle']) is not int or not 1<=obj['handle']<=MAX_INTEGER or
            type(obj['udp_next_id']) is not int or not 1<=obj['udp_next_id']<=MAX_INTEGER or
            not finite(obj['deadline']) or not finite(obj['controller_timeout']) or
            not 0<obj['controller_timeout']<=600 or type(obj['claim']) is not str):
        raise ValueError('invalid worker configuration')
    peer=obj['udp_peer']
    if (type(peer) is not list or len(peer)!=2 or peer[0]!='127.0.0.1' or
            type(peer[1]) is not int or not 1<=peer[1]<=65535):
        raise ValueError('invalid loopback participant peer')
    if 'motion' in obj:
        motion=obj['motion']
        if (type(motion) is not dict or set(motion)-{'saved_apply_fixture', 'saved_playback_fixture'}!={'lease','attempt','epoch','generation','timeout'} or
            any(type(motion[k]) is not str or not _HEX.fullmatch(motion[k]) for k in ('lease','attempt','epoch','generation')) or
            len({motion[k] for k in ('lease','attempt','epoch','generation')})!=4 or
            motion['lease'] in (obj['lease'],obj['epoch']) or motion['attempt'] in (obj['lease'],obj['epoch']) or
            not finite(motion['timeout']) or not 0<motion['timeout']<=30 or
            2*motion['timeout']>=obj['controller_timeout']):
            raise ValueError('invalid motion context or timeout')
        if 'saved_apply_fixture' in motion and 'saved_playback_fixture' in motion:
            raise ValueError('client motion apply and playback are mutually exclusive')
        if 'saved_apply_fixture' in motion and (
                type(motion['saved_apply_fixture']) is not str or
                motion['saved_apply_fixture'] != RECOVERY_SETTER_FIXTURE or
                motion['epoch'] != RECOVERY_SETTER_EPOCH):
            raise ValueError('invalid recovery setter fixture')
        if 'saved_playback_fixture' in motion and (
                type(motion['saved_playback_fixture']) is not str or
                motion['saved_playback_fixture'] != RECOVERY_SETTER_FIXTURE or
                motion['epoch'] != RECOVERY_SETTER_EPOCH):
            raise ValueError('invalid recovery playback fixture')
    try: raw_claim=obj['claim'].encode('ascii')
    except UnicodeError as error: raise ValueError('invalid claim encoding') from error
    claim=decode_load_claim(raw_claim)
    if claim.receipt.world_epoch!=obj['epoch'] or claim.receipt.connection_handle!=obj['handle']:
        raise ValueError('claim does not match worker context')
    if 'motion' in obj and claim.receipt.attempt_id in (obj['motion']['lease'],obj['motion']['attempt']):
        raise ValueError('motion secret conflicts with claim attempt')
    if 'client_authority' in obj:
        source=obj['client_authority']
        if (type(source) is not dict or set(source)-{'freeze_drain'}!={'lease','attempt','grant','fixture_slot','timeout'} or
                type(source.get('freeze_drain', False)) is not bool):
            raise ValueError('invalid client authority configuration')
        grant=grant_value(source['grant'])
        secrets=(source['lease'],source['attempt'],grant['epoch'],grant['generation'],grant['incarnation'],grant['token'])
        if (any(type(secret) is not str or not _HEX.fullmatch(secret) for secret in secrets) or
                len(set(secrets))!=len(secrets) or
                any(secret in (obj['lease'],obj['epoch'],claim.receipt.attempt_id) for secret in secrets) or
                grant['session_epoch']!=obj['epoch'] or type(source['fixture_slot']) is not int or
                source['fixture_slot'] not in (1,2) or grant['index']!=source['fixture_slot']+2 or
                not finite(source['timeout']) or not 0<source['timeout']<=30 or
                6*source['timeout']>=obj['controller_timeout']):
            raise ValueError('invalid client authority context or timeout')
    if time.monotonic()>=obj['deadline']: raise TimeoutError('expired worker configuration')
    check_process(obj['client_process'])
    return obj,raw_claim,claim.receipt.attempt_id


def read_line(sock,limit,deadline,check=lambda:None):
    """Read exactly one frame without consuming a subsequent protocol frame."""
    data=bytearray()
    while True:
        check()
        left=deadline-time.monotonic()
        if left<=0: raise TimeoutError('worker frame timed out')
        readable,_,bad=select.select([sock],[],[sock],min(left,.25))
        if bad: raise RuntimeError('worker socket exception')
        if not readable: continue
        check()
        try: piece=sock.recv(1)
        except BlockingIOError: continue
        if piece==b'': raise RuntimeError('worker socket closed')
        if piece==b'\n':
            check()
            if time.monotonic()>=deadline: raise TimeoutError('worker frame timed out')
            return bytes(data)
        data.extend(piece)
        if len(data)>limit: raise ValueError('worker frame too large')


def send_frame(sock,payload,deadline,check):
    raw=payload+b'\n';offset=0
    while offset<len(raw):
        check()
        left=deadline-time.monotonic()
        if left<=0: raise TimeoutError('worker send timed out')
        _,writable,bad=select.select([], [sock], [sock], min(left,.25))
        if bad: raise RuntimeError('worker socket exception')
        if not writable: continue
        try: count=sock.send(raw[offset:])
        except BlockingIOError: continue
        if count<=0: raise RuntimeError('worker send failed')
        offset+=count
    check()


def event(ipc,kind,deadline):
    raw=json.dumps({'event':kind},separators=(',',':')).encode('ascii')
    send_frame(ipc,raw,deadline,lambda:None)


def verify_sockets(tcp,udp,ipc,motion_udp=None):
    if (tcp.family!=socket.AF_INET or tcp.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)!=socket.SOCK_STREAM or
            tcp.getsockname()[0]!='127.0.0.1' or tcp.getpeername()[0]!='127.0.0.1'):
        raise ValueError('loopback TCP socket required')
    if (udp.family!=socket.AF_INET or udp.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)!=socket.SOCK_DGRAM or
            udp.getsockname()[0]!='127.0.0.1' or udp.getsockname()[1]<1):
        raise ValueError('bound loopback UDP socket required')
    if ipc.family!=socket.AF_UNIX or ipc.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)!=socket.SOCK_STREAM:
        raise ValueError('private IPC stream required')
    ipc.getpeername()
    sockets=[tcp,udp,ipc]
    if motion_udp is not None:
        if (motion_udp.family!=socket.AF_INET or motion_udp.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)!=socket.SOCK_DGRAM or
            motion_udp.getsockname()[0]!='127.0.0.1' or motion_udp.getsockname()[1]<1):
            raise ValueError('bound loopback motion UDP required')
        try: motion_udp.getpeername()
        except OSError: pass
        else: raise ValueError('motion UDP must be unconnected')
        sockets.append(motion_udp)
    identities=[(os.fstat(s.fileno()).st_dev,os.fstat(s.fileno()).st_ino) for s in sockets]
    if len(set(identities))!=len(identities): raise ValueError('socket ownership aliases')


class GuardedParticipant:
    """Own a previously enrolled UDP controller reconstructed from private state."""
    def __init__(self,udp,cfg,guard,motion_gate=None):
        self.guard,self.deadline,self.timeout=guard,cfg['deadline'],cfg['controller_timeout']
        self.motion_gate=motion_gate
        controller=LocalParticipantControl.__new__(LocalParticipantControl)
        controller.sock=udp;controller.lease=cfg['lease'];controller.peer=tuple(cfg['udp_peer'])
        controller.epoch=cfg['epoch'];controller.handle=cfg['handle'];controller.next_id=cfg['udp_next_id']
        controller.fault=False;controller.timeout=self.timeout
        self.controller=controller
    def call(self,operation,handles):
        self.guard()
        remaining=self.deadline-time.monotonic()
        if remaining<=0: raise TimeoutError('worker deadline')
        self.controller.timeout=min(self.timeout,remaining)
        self.controller.sock.settimeout(min(.25,remaining,self.timeout))
        result=getattr(self.controller,operation)(handles)
        self.guard()
        return result
    def pause(self,handles):
        if self.motion_gate is not None:
            if isinstance(self.motion_gate, LazyClientAuthority):self.motion_gate.suspend()
            else:self.motion_gate.stop()
        return self.call('pause',handles)
    def resume(self,handles):
        if self.motion_gate is not None and self.motion_gate.stopped:
            raise RuntimeError('stopped motion lease cannot resume')
        result=self.call('resume',handles)
        if self.motion_gate is not None and result is True:
            self.motion_gate.running=True
            if isinstance(self.motion_gate, LazyClientAuthority):self.motion_gate.resume_source()
        return result
    def close(self): self.controller.close()


class LazyMotion:
    """One participant-thread UDP owner, first bound only after resume."""
    def __init__(self,sock,cfg,guard):
        self.sock,self.cfg,self.guard=sock,cfg,guard
        self.running=False;self.stopped=False;self.bridge=None
        self.destination=sock.getsockname()
        self._playback_previous = None
    def _bind(self):
        self.guard()
        if self.bridge is None:
            # Imported here to avoid a module cycle when this file is __main__.
            from authority_tcp_job_client_live import socket_owner
            def peer(address):
                self.guard()
                return self.sock.getsockname()==self.destination and socket_owner(address,self.destination,self.cfg['client_process']) is True
            def context():
                self.guard()
                return self.running and self.sock.getsockname()==self.destination
            m=self.cfg['motion']
            self.bridge=ExperimentalParticipantMotionIPC(self.sock,enabled=True,lease=m['lease'],attempt=m['attempt'],
                epoch=m['epoch'],generation=m['generation'],guard=context,validate_peer=peer,timeout=m['timeout'],
                allow_apply=m.get('saved_apply_fixture') == RECOVERY_SETTER_FIXTURE,stop_enabled=True)
            self.bridge.wait_ready()
        self.guard()
    def __call__(self,sample,despawn):
        if not self.running or self.stopped or despawn is not False:raise RuntimeError('motion while paused or unsupported despawn')
        playback = self.cfg['motion'].get('saved_playback_fixture') == RECOVERY_SETTER_FIXTURE
        if playback:
            sample = motion_value(sample)
            if (sample['version'] != 1 or sample['epoch'] != RECOVERY_SETTER_EPOCH or
                    sample['generation'] != self.cfg['motion']['generation'] or
                    sample['index'] != RECOVERY_SETTER_INDEX or
                    sample['sector_macro'] != 'cluster_06_sector001_macro'):
                raise ValueError('recovery playback sample mismatch')
            previous = self._playback_previous
            if previous is None:
                # Lua consumes the actual first sample as enrollment only. Never
                # renumber, translate its pose, or fabricate its source clock.
                if sample['sequence'] != 1:
                    raise ValueError('recovery playback must enroll source sequence one')
            elif sample['sequence'] <= previous[0] or sample['source_time'] <= previous[1]:
                raise ValueError('recovery playback source regressed')
        self._bind()
        confirmed = self.bridge(sample,despawn)
        if playback and confirmed is True:
            self._playback_previous = (sample['sequence'], sample['source_time'])
        return confirmed
    def _check_setter_sample(self, sample):
        """Fence the only permitted recovery fixture before any setter IPC."""
        if not self.running or self.stopped or self.cfg['motion'].get('saved_apply_fixture') != RECOVERY_SETTER_FIXTURE:
            raise RuntimeError('recovery setter unavailable')
        if (type(sample) is not dict or sample.get('epoch') != RECOVERY_SETTER_EPOCH or
                type(sample.get('index')) is not int or sample['index'] != RECOVERY_SETTER_INDEX or
                sample.get('generation') != self.cfg['motion']['generation']):
            raise ValueError('recovery setter sample mismatch')
    def preflight(self, sample):
        self._check_setter_sample(sample)
        self._bind()
        return self.bridge.preflight(sample)
    def apply_once(self, sample):
        self._check_setter_sample(sample)
        self._bind()
        return self.bridge.apply_once(sample)
    def stop(self):
        if self.stopped:return True
        if not self.running:raise RuntimeError('motion stop cannot be confirmed before resume')
        self._bind()
        if self.bridge.stop_remote() is not True:raise RuntimeError('client motion stop unconfirmed')
        self.running=False;self.stopped=True;return True
    def close(self):
        if self.bridge is None:self.sock.close()
        elif self.bridge.state not in ('closed','failed'):self.bridge.close()


class LazyClientAuthority:
    """Read one controlled fixture ship only while this participant is running.

    This is a diagnostic grant, not proof of server authority or ship identity.
    The supervisor must coordinate the X4 source start and own its shutdown.
    """
    def __init__(self, sock, cfg, guard):
        self.sock, self.cfg, self.guard = sock, cfg, guard
        self.running = False
        self.stopped = False
        self.bridge = None
        self.grant = grant_value(cfg['client_authority']['grant'])

    def grant_is_current(self, grant):
        self.guard()
        return self.running and not self.stopped and grant == self.grant

    def pull(self):
        if not self.grant_is_current(self.grant):
            raise RuntimeError('client authority unavailable while paused')
        if self.bridge is None:
            # This import must be delayed when the worker is the main module.
            from authority_client_authority_bind import bind_client_authority
            from authority_fixture_player_source_arm import arm_fixture_source
            source = self.cfg['client_authority']
            grant = self.grant
            source_peer = arm_fixture_source(
                self.sock, process=self.cfg['client_process'], lease=source['lease'],
                attempt=source['attempt'], epoch=grant['epoch'], generation=grant['generation'],
                guard=lambda: (self.guard() is None), running=lambda: self.running and not self.stopped,
                timeout=source['timeout'])
            self.bridge = bind_client_authority(
                self.sock, process=self.cfg['client_process'], lease=source['lease'],
                attempt=source['attempt'], epoch=grant['epoch'], generation=grant['generation'],
                incarnation=grant['incarnation'], token=grant['token'], session_epoch=grant['session_epoch'],
                guard=lambda: (self.guard() is None), running=lambda: self.running and not self.stopped,
                grant=lambda epoch, generation, index, token, incarnation, session_epoch:
                    self.grant_is_current(dict(epoch=epoch, generation=generation, index=index,
                        token=token, incarnation=incarnation, session_epoch=session_epoch,
                        sector_macro=grant['sector_macro'])),
                timeout=source['timeout'], include_orientation=True,
                fixture_slot=source['fixture_slot'], fixture_sector=grant['sector_macro'],
                expected_peer=source_peer, freeze_drain=source.get('freeze_drain', False))
            self.bridge.register_saved()
        return self.bridge.pull()

    def suspend(self):
        try:
            if self.bridge is not None and self.cfg['client_authority'].get('freeze_drain', False):
                if not self.running or self.bridge.freeze() is not True:
                    raise RuntimeError('client authority freeze unconfirmed')
        finally:
            # A failed or uncertain freeze must never leave sampling available.
            self.running = False

    def resume_source(self):
        try:
            if self.bridge is not None and self.cfg['client_authority'].get('freeze_drain', False):
                if not self.running or self.bridge.resume() is not True:
                    raise RuntimeError('client authority resume unconfirmed')
            return True
        except BaseException:
            self.running = False
            raise

    def close(self):
        self.running = False
        self.stopped = True
        if self.bridge is None:
            self.sock.close()
        elif self.bridge.state not in ('closed', 'failed'):
            self.bridge.close()


def run(tcp,udp,ipc,motion_udp=None):
    verify_sockets(tcp,udp,ipc,motion_udp)
    tcp.setblocking(False);ipc.setblocking(False)
    # Bootstrap timeout is bounded even before receiving an absolute deadline.
    cfg,claim,attempt=config_value(read_line(ipc,MAX_CONFIG,time.monotonic()+30))
    if (('motion' in cfg or 'client_authority' in cfg)!=(motion_udp is not None)):
        raise ValueError('motion socket/config mismatch')
    deadline=cfg['deadline']
    def context():
        if time.monotonic()>=deadline: raise TimeoutError('worker deadline')
        check_process(cfg['client_process'])
        if time.monotonic()>=deadline: raise TimeoutError('worker deadline')
    def guard():
        context()
        readable,_,bad=select.select([ipc],[],[ipc],0)
        if readable or bad: raise RuntimeError('parent IPC closed or requested stop during operation')
        context()
    guard()
    if not cfg.get('already_admitted'):
        if select.select([tcp],[],[tcp],0)[0]: raise RuntimeError('unexpected input before claim')
        send_frame(tcp,claim,deadline,guard)
        ack=parse_json(read_line(tcp,MAX_MESSAGE,deadline,guard))
        if (type(ack) is not dict or set(ack)!={'version','kind','attempt_id'} or
                type(ack['version']) is not int or ack['version']!=1 or
                ack['kind']!='accepted' or ack['attempt_id']!=attempt):
            raise ValueError('unexpected admission response')
    guard()
    motion=LazyMotion(motion_udp,cfg,guard) if 'motion' in cfg else None
    source=LazyClientAuthority(motion_udp,cfg,guard) if 'client_authority' in cfg else None
    controller=GuardedParticipant(udp,cfg,guard,motion or source)
    adapter=ExperimentalTCPParticipantClient(tcp,controller,enabled=True,epoch=cfg['epoch'],
        handle=cfg['handle'],timeout=min(cfg['controller_timeout'],max(.001,deadline-time.monotonic())),apply_motion=motion,
        preflight_motion=motion.preflight if motion is not None and cfg['motion'].get('saved_apply_fixture') == RECOVERY_SETTER_FIXTURE else None,
        apply_motion_once=motion.apply_once if motion is not None and cfg['motion'].get('saved_apply_fixture') == RECOVERY_SETTER_FIXTURE else None,
        authority_grant=source.grant if source is not None else None,
        authority_guard=source.grant_is_current if source is not None else None,
        pull_authority_motion=source.pull if source is not None else None)
    cleaned=False
    def cleanup():
        nonlocal cleaned
        if cleaned:return
        cleaned=True;errors=[]
        for action in (lambda:adapter.close() if not adapter._closed and not adapter._failed else None,
                       controller.close, lambda:motion.close() if motion is not None else None,
                       lambda:source.close() if source is not None else None):
            try:action()
            except BaseException as error:errors.append(error)
        if errors:raise BaseExceptionGroup('participant worker cleanup failed',errors)
    try:
        guard()
        event(ipc,'active',deadline)
        context()
        while True:
            left=deadline-time.monotonic()
            if left<=0: raise TimeoutError('worker deadline')
            readable,_,bad=select.select([ipc,tcp],[],[ipc,tcp],min(.05,left))
            if bad: raise RuntimeError('worker socket exception')
            if ipc in readable:
                request=parse_json(read_line(ipc,MAX_IPC,deadline))
                if request!={'command':'stop'}: raise ValueError('invalid worker command')
                if motion is not None:
                    # Motion STOPPED is confirmed while TCP still belongs to
                    # this worker. Supervisor also requires clean process exit.
                    motion.stop()
                    event(ipc,'stopped',deadline)
                    cleanup()
                else:
                    cleanup()
                    event(ipc,'stopped',deadline)
                return
            context()
            adapter.poll(0)
            context()
    finally:
        cleanup()


def main(argv):
    if len(argv) not in (3,4): return 2
    try:
        fds=[int(x) for x in argv]
        if any(fd<3 for fd in fds) or len(set(fds))!=len(fds): return 2
    except ValueError: return 2
    sockets=[]
    try:
        for fd in fds: sockets.append(socket.socket(fileno=fd))
        run(*sockets)
        return 0
    except BaseException:
        if len(sockets)>=3:
            try: event(sockets[2],'failed',time.monotonic()+.25)
            except BaseException: pass
        return 1
    finally:
        for sock in sockets:
            try: sock.close()
            except BaseException: pass

if __name__=='__main__': sys.exit(main(sys.argv[1:]))
