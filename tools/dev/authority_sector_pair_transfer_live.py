#!/usr/bin/env python3
"""Experimental private two-X4 index-3 transfer; not production networking."""
import argparse
import json
import math
import os
from pathlib import Path
import secrets
import select
import signal
import shutil
import socket
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'src')]
import authority_sector_pair_live as pair
import authority_descriptor_loopback as wire
from authority_helper_lifecycle import OwnedHelper


def once(text, old, new):
    if text.count(old)!=1: raise ValueError('missing or ambiguous overlay hook')
    return text.replace(old,new)


class CompilerCleanupUnconfirmed(RuntimeError):
    """Compiler group or leader cleanup could not be proven; retain its Popen."""
    def __init__(self,proc):
        super().__init__('compiler cleanup unconfirmed')
        self.proc=proc


def compile_net(compiler,target):
    """Bound the trusted compiler group and reap it before proceeding."""
    proc=subprocess.Popen([compiler,'-std=c11','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',
                           str(ROOT/'src/native/net.c'),'-ldl','-o',str(target)],
                          start_new_session=True,stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        status=proc.wait(timeout=30)
    except BaseException as original:
        unconfirmed=False
        try:
            if proc.returncode is None:
                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                except BaseException:unconfirmed=True
        finally:
            try:proc.wait(timeout=5)
            except BaseException:unconfirmed=True
        if unconfirmed:raise CompilerCleanupUnconfirmed(proc) from original
        raise
    if status!=0:raise RuntimeError('native UDP module compilation failed')


class PairTransferParticipant:
    """Single-use coordinator; no local X4 handles leave either process."""
    def __init__(self):
        self.attempt=secrets.token_hex(16)
        self.epoch=pair.base.archive.REGISTRY_EPOCH
        self.roles={}
        self.helpers=[]
        self.context=None
        self.deadline=None
        self.closed=False
        self.complete=False
        self.sockets=[]
        self.compiler_cleanup_error=None

    def install(self,case,profile,ticket,role,nonce,macros,timeout):
        if role in self.roles or role not in ('server','client'):
            raise ValueError('duplicate role')
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.sockets.append(sock)
        sock.bind(('127.0.0.1',0));sock.setblocking(False)
        lease=secrets.token_hex(16)
        self.roles[role]={'sock':sock,'peer':None,'lease':lease,'events':[],
                          'event_at':0,'pending':None,'counter':0}
        lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md';native=lab/'native'
        native.mkdir(exist_ok=True)
        files=[]
        for source,dest in (('authority_sector_create_receiver.xml','authority_ship_create_receiver.xml'),
                            ('authority_sector_pair_create_inspect.xml','authority_sector_pair_create_inspect.xml')):
            path=md/dest;shutil.copyfile(ROOT/'tools/dev'/source,path);files.append(path)
        # In this experiment slot 1 is the target; prove it is remote and the
        # receiver is fresh in the existing baseline-2 readiness query, before
        # either process can be sent START. Keep the test-only receiver itself
        # fail-closed if the player sector changes before Create.
        ready=md/'authority_sector_pair_ready.xml';text=ready.read_text()
        hook='and not md.X4AuthorityShipRegistry.State.$faulted and $v.$epoch'
        ready.write_text(once(text,hook,
            'and not md.X4AuthorityShipRegistry.State.$faulted and not md.X4AuthorityShipCreateReceiver.State.$epoch? '
            'and not md.X4AuthorityShipCreateReceiver.State.$receipts? and @player.sector.isclass.sector '
            'and $s1 != player.sector and $v.$epoch'))
        receiver=md/'authority_ship_create_receiver.xml';text=receiver.read_text()
        hook='and @$sector.isclass.sector and $sector.macro.id == $req.$sector'
        receiver.write_text(once(text,hook,
            'and @$sector.isclass.sector and @player.sector.isclass.sector and $sector != player.sector '
            'and $sector.macro.id == $req.$sector'))
        engine=ui/'x4_ship_engine.lua';shutil.copyfile(ROOT/'src/authority/lua/x4_ship_engine.lua',engine);files.append(engine)
        names=[]
        for name,global_name in (('authority_sector_pair_create.lua','X4LAN_PAIR_CREATE_DRIVER'),
                                 ('authority_sector_pair_create_x4.lua','X4LAN_PAIR_CREATE_X4'),
                                 ('authority_sector_pair_create_udp.lua','X4LAN_PAIR_CREATE_UDP')):
            path=ui/name;text=(ROOT/'tools/dev'/name).read_text()
            path.write_text(once(text,'return M\n',global_name+'=M\nreturn M\n'))
            files.append(path);names.append(name)
        path=ui/'authority_sector_pair_session.lua'
        shutil.copyfile(ROOT/'tools/dev'/path.name,path);files.append(path);names.append(path.name)
        compiler=shutil.which('cc')
        if not compiler:raise ValueError('C compiler required')
        lib=native/'x4lan_net.so'
        try:compile_net(compiler,lib)
        except CompilerCleanupUnconfirmed as error:
            self.compiler_cleanup_error=error
            raise
        files.append(lib)
        config=ui/'config.lua';text=config.read_text(encoding='ascii')
        if not text.endswith('}\n'):raise ValueError('unexpected config')
        config.write_text(text[:-2]+',authority_pair_create=true,authority_pair_port='+str(sock.getsockname()[1])+
                          ',authority_pair_lease="'+lease+'",authority_pair_attempt="'+self.attempt+'"}\n',encoding='ascii')
        config.chmod(0o600)
        manifest=lab/'ui.xml';text=manifest.read_text()
        hook='    <file name="ui/authority_download_load_probe.lua" />\n'
        manifest.write_text(once(text,hook,''.join('    <file name="ui/'+n+'" />\n' for n in ['x4_ship_engine.lua',*names])+hook))
        owner=ui/'authority_download_load_probe.lua';text=owner.read_text()
        hook=" if state=='done' then X4LAN_SECTOR_PAIR_TICK();return end\n"
        owner.write_text(once(text,hook," if state=='done' then if X4LAN_SECTOR_PAIR_TICK() then X4LAN_PAIR_CREATE_TICK() end;return end\n"))
        expected=set((*pair.base.MD,'authority_sector_read_guard.xml','authority_sector_pair_ready.xml',
                      'authority_ship_create_receiver.xml','authority_sector_pair_create_inspect.xml'))
        if {p.name for p in md.iterdir()}!=expected:raise ValueError('unexpected MD scripts')
        return files

    def check_live_log(self,role,raw):
        return b'[x4lan] auth_pair_create error fault' not in raw.lower()

    def _helper_status(self,helper):
        proc=helper.proc
        if proc is None:return None
        if proc.returncode is not None:return proc.returncode
        if signal.getsignal(signal.SIGCHLD)!=signal.SIG_DFL or helper.pidfd is None:
            raise RuntimeError('helper ownership unconfirmed')
        try:info=os.waitid(os.P_PIDFD,helper.pidfd,os.WEXITED|os.WNOHANG|os.WNOWAIT)
        except ChildProcessError:raise RuntimeError('helper reaped externally') from None
        return None if info is None else proc.poll()

    def _context(self):
        if self.context is None or self.context['check']() is not True or time.monotonic()>=self.deadline:
            raise RuntimeError('pair context failed')
        for helper in self.helpers:
            status=self._helper_status(helper)
            if status is not None and status!=0:
                raise RuntimeError('sender helper failed')

    def _pump(self,timeout):
        self._context()
        ready,_,bad=select.select([e['sock'] for e in self.roles.values()],[],
                                   [e['sock'] for e in self.roles.values()],timeout)
        self._context()
        if bad:raise RuntimeError('local UDP exception')
        for role,e in self.roles.items():
            if e['sock'] not in ready:continue
            data,peer=e['sock'].recvfrom(769)
            if peer[0]!='127.0.0.1' or (e['peer'] is not None and e['peer']!=peer) or len(data)>768:
                raise ValueError('foreign or oversized local datagram')
            try:parts=data.decode('ascii').split('|')
            except UnicodeError:raise ValueError('invalid local datagram') from None
            if parts[:5]!=['PAIR',e['lease'],role,self.attempt,self.epoch]:raise ValueError('foreign local receipt')
            body=parts[5:]
            if body==['FAULT']:raise RuntimeError('X4 participant fault')
            if body and body[0]=='CHECKED':
                if len(body)!=2 or e['pending'] is None or body[1]!=str(e['pending']):
                    raise ValueError('unexpected check receipt')
                e['pending']=None;continue
            expected=['READY','DESCRIPTOR','FINISHED'] if role=='server' else ['READY','AWAIT','INSPECTED']
            pos=e['event_at']
            if pos>=len(expected) or not body or body[0]!=expected[pos]:raise ValueError('unexpected local receipt')
            if pos==0:
                if len(body)!=1:raise ValueError('invalid ready')
                e['peer']=peer
            elif body[0]=='AWAIT':
                if len(body)!=1:raise ValueError('invalid await')
            elif body[0] in ('FINISHED','INSPECTED'):
                if body!=[body[0],'1','3']:raise ValueError('invalid completion')
            elif body[0]=='DESCRIPTOR':
                if len(body)!=10 or body[1:3]!=['1','3'] or body[6]!='7183':raise ValueError('invalid source descriptor')
                try:xyz=[float(v) for v in body[7:10]]
                except ValueError:raise ValueError('invalid source position') from None
                body=wire._descriptor({'version':1,'type':'descriptor','attempt':self.attempt,'epoch':self.epoch,
                    'seq':1,'index':3,'macro':body[3],'sector':body[4],'owner':body[5],
                    'seed':7183,'x':xyz[0],'y':xyz[1],'z':xyz[2]})
                if (body['macro'],body['sector'],body['owner'])!=('ship_arg_s_fighter_01_a_macro',self.context['macros'][0],'argon'):
                    raise ValueError('unexpected source descriptor')
            e['events'].append(body);e['event_at']+=1

    def _command(self,role,*parts):
        e=self.roles[role]
        if e['peer'] is None:raise RuntimeError('local peer unknown')
        data='|'.join(('CMD',e['lease'],role,self.attempt,self.epoch,*parts)).encode('ascii')
        if len(data)>768 or e['sock'].sendto(data,e['peer'])!=len(data):raise RuntimeError('local send unconfirmed')

    def _guard(self):
        self._context()
        for role,e in self.roles.items():
            if e['pending'] is not None:raise RuntimeError('overlapping check')
            e['counter']+=1
            if e['counter']>2147483647:raise RuntimeError('check counter exhausted')
            e['pending']=e['counter'];self._command(role,'CHECK',str(e['counter']))
        while any(e['pending'] is not None for e in self.roles.values()):
            remaining=self.deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('pair guard deadline')
            self._pump(min(.2,remaining))
        self._context()
        return True

    def _await(self,role,count):
        while len(self.roles[role]['events'])<count:
            self._guard()
            if len(self.roles[role]['events'])<count:
                self._pump(min(.2,max(0,self.deadline-time.monotonic())))
        self._guard()
        return self.roles[role]['events'][count-1]

    def on_ready(self,context):
        if self.context is not None or set(self.roles)!={'server','client'}:raise RuntimeError('invalid pair state')
        self.context=context;self.deadline=min(context['deadline'],time.monotonic()+120)
        while any(not e['events'] for e in self.roles.values()):
            self._pump(min(.2,max(0,self.deadline-time.monotonic())))
        self._guard()
        self._command('client','START');self._guard()
        self._command('server','START');self._guard()
        self._await('client',2)
        descriptor=self._await('server',2)
        listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM);self.sockets.append(listener)
        listener.bind(('127.0.0.1',0));listener.listen(1)
        self._guard()
        remaining=self.deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('pair connection deadline')
        listener.settimeout(min(2,remaining))
        sender=socket.create_connection(listener.getsockname(),timeout=min(2,remaining));self.sockets.append(sender)
        receiver,_=listener.accept();self.sockets.append(receiver)
        self._guard()
        ipc_parent,ipc_child=socket.socketpair();self.sockets.extend((ipc_parent,ipc_child))
        helper=OwnedHelper([sys.executable,str(ROOT/'tools/dev/authority_descriptor_sender_worker.py'),
                            str(sender.fileno()),str(ipc_child.fileno())],registry=self.helpers,
                           pass_fds=(sender.fileno(),ipc_child.fileno()))
        sender.close();ipc_child.close();listener.close()
        self._guard()
        ipc_parent.settimeout(2)
        ipc_parent.sendall(json.dumps({'descriptor':descriptor,'deadline':self.deadline},allow_nan=False).encode('ascii'))
        ipc_parent.shutdown(socket.SHUT_WR);ipc_parent.close()
        self._guard();helper.release();self._guard()
        def inspect(value):
            if value!=descriptor:raise ValueError('transport descriptor changed')
            self._guard()
            fields=('1','3',value['macro'],value['sector'],value['owner'],str(value['seed']),
                    *(format(value[n],'.17g') for n in ('x','y','z')))
            self._command('client','DESCRIPTOR',*fields)
            self._await('client',3)
            self._guard()
            return True
        received=wire.receive_descriptor(receiver,self.attempt,self.epoch,inspect,self.deadline,self._guard)
        if received!=descriptor:raise ValueError('transport mismatch')
        while self._helper_status(helper) is None:
            self._guard();self._pump(min(.2,max(0,self.deadline-time.monotonic())))
        if self._helper_status(helper)!=0:raise RuntimeError('sender did not verify ACK')
        self._guard();self._command('server','ACK','1','3')
        self._await('server',3);self._guard()
        self.complete=True
        return {'index':3,'tcp_ack_after_client_inspect':True,'local_replay_checked':True,
                'remote_sector_checked':True,'continuous_pause_proven':False,'multiplayer_proven':False}

    def cleanup_before_owned_processes(self):
        if self.closed:return True
        local_udp={e['sock'] for e in self.roles.values()}
        errors=[]
        for sock in self.sockets:
            if sock not in local_udp:
                try:sock.close()
                except BaseException as error:errors.append(error)
        for helper in reversed(self.helpers):
            try:helper.stop()
            except BaseException as error:errors.append(error)
        if self.compiler_cleanup_error is not None:raise self.compiler_cleanup_error
        if errors:raise RuntimeError('participant pre-cleanup unconfirmed') from errors[0]
        self.closed=True
        return True

    def cleanup_after_owned_processes(self):
        errors=[]
        for sock in self.sockets:
            try:sock.close()
            except BaseException as error:errors.append(error)
        if errors:raise RuntimeError('participant post-cleanup unconfirmed') from errors[0]
        return True

    def verify_final(self,logs):
        if not self.complete or set(logs)!={'server','client'}:return False
        # After X4 has stopped, no late datagram may remain unexamined.
        for e in self.roles.values():
            try:e['sock'].recvfrom(769)
            except BlockingIOError:pass
            else:return False
        for role,raw in logs.items():
            if not self.check_live_log(role,raw):return False
            tag='[X4LAN] AUTH_PAIR_CREATE '
            labels=[line.split(tag,1)[1].strip() for line in raw.decode('utf-8').splitlines() if tag in line]
            labels=[label for label in labels if label!='CHECKED']
            expected=['READY','DESCRIPTOR','FINISHED'] if role=='server' else ['READY','AWAIT','INSPECTED']
            if labels!=expected:return False
        return True


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--store',type=Path,default=pair.base.archive.DEFAULT_STORE);p.add_argument('--display',required=True)
    p.add_argument('--timeout',type=float,default=600);p.add_argument('--seed',type=int,default=276944566)
    args=p.parse_args();participant=PairTransferParticipant()
    try:result=pair.run(args,participant)
    except BaseException:
        participant.cleanup_before_owned_processes()
        participant.cleanup_after_owned_processes()
        raise
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1

if __name__=='__main__':sys.exit(main())
