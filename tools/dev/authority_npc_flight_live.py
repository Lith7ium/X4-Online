#!/usr/bin/env python3
"""Explicit terminal Linux/Linus NPC-flight fixture. Never starts on import.

One source is resumed exclusively through the existing bridge after its offer is
revoked and its file service closed. The coordinator becomes stale and is never
used again. Guest remains paused. No admission or shared gameplay is tested.
"""
import argparse
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import shutil
import socket
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_create_test_live as creation
import authority_checkpoint_marker_live as marker
import authority_two_x4_live as base
from authority_npc_flight_terminal import TerminalControl
from authority_npc_flight_evidence import validate


def _row(line, marker):
    fields={}
    for item in line.split(marker,1)[1].split():
        if '=' in item:
            k,v=item.split('=',1)
            if k in fields: raise ValueError('duplicate evidence field')
            fields[k]=v
    for name in ('index','seq'):
        if name in fields: fields[name]=int(fields[name])
    for name in ('real_time','game_time','x','y','z','vx','vy','vz','reference_real_time',
                 'reference_x','reference_y','reference_z','target_x','target_y','target_z'):
        if name in fields: fields[name]=float(fields[name])
    return fields


def check_evidence(server,guest,*,epoch,frame,guest_actor):
    def rows(text,marker): return [_row(line,marker) for line in text.splitlines() if marker in line]
    orders=rows(server,'AUTH_NPC_SOURCE ORDER ')
    if len(orders)!=1: raise ValueError('expected one pilot/order receipt')
    return validate(epoch=epoch,index=1,frame=frame,guest_actor=guest_actor,order=orders[0],
        source=rows(server,'AUTH_NPC_SOURCE SAMPLE '),
        guest_writes=rows(guest,'NATURAL_GUEST_WRITE '),
        guest_readbacks=rows(guest,'NATURAL_GUEST_OBSERVE '))


class FlightExperiment(creation.Experiment):
    requires_steam_identity=True
    def __init__(self, *, flight_seconds, bridge_timeout):
        super().__init__(motion=True)
        self.flight_seconds=flight_seconds;self.bridge_timeout=bridge_timeout
        self.flight_sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.flight_sock.bind(('127.0.0.1',0));self.flight_sock.settimeout(.1)
        self.flight_lease=secrets.token_hex(16);self.flight_peer=None
        self.bound=None

    def bind_world(self, world, engine, offers):
        if self.bound is not None: raise RuntimeError('duplicate terminal control binding')
        self.bound=(world,engine,offers,offers.service)

    def install(self,case,phase):
        super().install(case,phase)
        lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
        config=ui/'config.lua';text=config.read_text(encoding='ascii')
        if not text.endswith('}\n'): raise ValueError('unexpected private configuration')
        for filename in ('authority_npc_flight_fixture.xml','authority_npc_flight_guard.xml'):
            shutil.copyfile(ROOT/'tools/dev'/filename,md/filename)
        if phase=='save':
            # The original post-checkpoint fixture has no explicit pilot. Modify
            # only this disposable overlay and require exactly one known hook.
            fixture=md/'authority_create_test_fixture.xml';data=fixture.read_text()
            hook='      <loadout><level exact="1.0"/><variation exact="0"/></loadout>\n'
            if data.count(hook)!=1: raise ValueError('pilot fixture hook missing')
            fixture.write_text(data.replace(hook,hook+'      <pilot><select faction="faction.argon" tags="tag.aipilot"/></pilot>\n'))
            shutil.copyfile(ROOT/'tools/dev/authority_npc_flight_source.lua',ui/'authority_npc_flight_source.lua')
            text=text[:-2]+f', authority_npc_flight_source=true, authority_npc_port={self.flight_sock.getsockname()[1]}, authority_npc_lease="{self.flight_lease}"'+'}\n'
            added='    <file name="ui/authority_npc_flight_source.lua" />\n'
        else:
            shutil.copyfile(ROOT/'tools/dev/authority_npc_flight_guest_trace.lua',ui/'authority_npc_flight_guest_trace.lua')
            text=text[:-2]+', authority_npc_flight_guest=true}\n'
            added='    <file name="ui/authority_npc_flight_guest_trace.lua" />\n'
        config.write_text(text,encoding='ascii')
        manifest=lab/'ui.xml';data=manifest.read_text()
        hook='    <file name="ui/authority_create_test_probe.lua" />\n'
        if data.count(hook)!=1: raise ValueError('create probe hook missing')
        manifest.write_text(data.replace(hook,added+hook))

    def protected(self,case):
        paths=super().protected(case);lab=case/'extensions/x4_lan_lab'
        paths += [lab/'md'/name for name in ('authority_npc_flight_fixture.xml','authority_npc_flight_guard.xml')]
        # Server is protected by its own sandbox; client files need explicit
        # read-only binds in the existing two-process harness.
        if (lab/'ui/authority_npc_flight_guest_trace.lua').exists():
            paths.append(lab/'ui/authority_npc_flight_guest_trace.lua')
        return paths

    def on_ready(self, *, world,server_proc,server_started,server_identity,client_proc,client_started,client_identity,game,out,deadline,result,steam_identity,**kwargs):
        if not self.bound or self.bound[0] is not world: raise RuntimeError('terminal bridge binding absent')
        _,engine,offers,service=self.bound
        uid=os.getuid();home=Path(pwd.getpwuid(uid).pw_dir)
        def progress(stage):
            # Never persist the UDP lease, raw packet, local actor or identity.
            fd=os.open(out/'npc-flight-progress.log',os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
            with os.fdopen(fd,'a',encoding='ascii') as stream:
                stream.write(f'{time.monotonic():.6f} {stage}\n')
        def check():
            if (base.client.game_identity(server_proc,server_started,game)!=server_identity or
                base.client.game_identity(client_proc,client_started,game)!=client_identity or
                base.live.steam_identity(home,uid)!=steam_identity):
                raise RuntimeError('owned X4 or Steam identity changed')
            for role in ('server','client'):
                path=out/role/'case/home/.config/EgoSoft/X4/45841/engine-output.log'
                if path.exists():
                    text=path.read_text(encoding='utf-8',errors='replace')
                    if '[X4LAN] AUTH_CREATE '+role+' ERROR ' in text or (role=='server' and '[X4LAN] AUTH_NPC_SOURCE ERROR ' in text):
                        raise RuntimeError(role+' fixture probe failed')
            return True
        def pump():
            check();self.relay.poll(64)
        def receive(sock,prefix,expected=None,*,expires=None):
            limit=min(deadline,time.monotonic()+30,expires if expires is not None else deadline)
            while time.monotonic()<limit:
                pump()
                try: raw,addr=sock.recvfrom(2048)
                except socket.timeout: continue
                if addr[0]!='127.0.0.1': continue
                try: parts=raw.decode('ascii').split('|')
                except UnicodeError: continue
                if parts[:2]!=prefix: continue
                if sock is self.flight_sock:
                    if parts[2:]==['HELLO']:
                        if self.flight_peer is not None and addr!=self.flight_peer: raise ValueError('NPC peer changed')
                        self.flight_peer=addr
                        if expected=='HELLO': return ['HELLO']
                        continue
                    if (expected in ('RUNNING','STOPPED') and
                            parts[2:]==['ARMED',self.flight_frame] and addr==self.flight_peer):
                        continue  # delayed duplicate from the paused source
                    if addr!=self.flight_peer or expected is None or parts[2]!=expected: raise ValueError('unexpected NPC receipt')
                    return parts[2:]
                role=parts[2] if len(parts)>2 else None
                if len(parts)==4 and role in ('server','client') and parts[3]=='HELLO':
                    if role in self.peers and self.peers[role]!=addr: raise ValueError('create peer changed')
                    self.peers[role]=addr
                    if expected=='HELLO': return ['HELLO']
                    continue
                if role not in self.peers or self.peers[role]!=addr or expected is None or parts[3]!=expected:
                    raise ValueError('unexpected create receipt')
                return parts[3:]
            raise TimeoutError('NPC flight receipt timed out: '+str(expected))
        # Both sockets are independently polled. The bounded polling never
        # treats HELLO as evidence of flight or client admission.
        progress('create_handshake_wait')
        handshake_deadline=min(deadline,time.monotonic()+30)
        while len(self.peers)<2:
            receive(self.sock,['RESULT',self.lease],'HELLO',expires=handshake_deadline)
        def command(role,name,fields=()):
            self.sock.sendto('|'.join(('CMD',self.lease,name,*fields)).encode(),self.peers[role])
            return receive(self.sock,['RESULT',self.lease],name)
        def check_creation_count(row):
            if (not row[2].isdigit() or int(row[2])==0 or not row[3].isdigit() or
                    not row[4].isdigit() or int(row[4])!=int(row[3])+1):
                raise ValueError('fixture identity or bounded fleet count invalid')
        spawned=command('server','SPAWN')
        if len(spawned)!=12 or spawned[1]!='1' or spawned[6:]!=['ship_arg_s_fighter_01_a_macro','argon','7183','-400','100000','500']:
            raise ValueError('bad server fixture receipt')
        sector=spawned[5]
        if not re.fullmatch('[A-Za-z0-9_]+',sector): raise ValueError('bad source identity')
        check_creation_count(spawned)
        received=command('client','CREATE',(spawned[6],sector,*spawned[7:]))
        if len(received)!=6 or received[1]!='1' or received[5]!=sector: raise ValueError('bad guest fixture receipt')
        check_creation_count(received)
        replay=command('client','REPLAY')
        if replay[1:]!=received[1:]: raise ValueError('guest fixture replay changed')
        guest_actor=received[2]
        fixture=self.epoch+'.1.'+sector
        if len(fixture)>64: raise ValueError('motion fixture label too long')
        self.relay.fixture=fixture
        self.flight_frame=sector
        command('client','MOTION')
        progress('guest_motion_armed')
        while self.flight_peer is None:
            receive(self.flight_sock,['NPCRESULT',self.flight_lease],'HELLO')
        progress('source_handshake_received')
        self.flight_sock.sendto(f'NPCCMD|{self.flight_lease}|ARM|{sector}'.encode(),self.flight_peer)
        progress('source_arm_sent')
        if receive(self.flight_sock,['NPCRESULT',self.flight_lease],'ARMED')!=['ARMED',sector]: raise ValueError('NPC order not armed')
        progress('source_armed_received')
        terminal=TerminalControl(world=world,engine=engine,offers=offers,service=service,
                                 check_processes=check,deadline=deadline,bridge_timeout=self.bridge_timeout)
        progress('terminal_fence_started');terminal.begin();progress('terminal_fence_confirmed')
        # The coordinator and its offers must never be used after this point.
        self.bound=None;world=None;offers=None;service=None
        result['server_state']='terminal experiment: coordinator stale'
        progress('bridge_resume_started');terminal.resume();progress('bridge_resume_confirmed')
        if receive(self.flight_sock,['NPCRESULT',self.flight_lease],'RUNNING')!=['RUNNING']: raise ValueError('source not running')
        progress('source_running_received')
        end=time.monotonic()+self.flight_seconds
        if end+self.bridge_timeout+1>=deadline: raise TimeoutError('insufficient remaining flight deadline')
        while time.monotonic()<end:
            pump()
            try:
                data,addr=self.sock.recvfrom(2048)
                parts=data.decode('ascii').split('|')
                if not (len(parts)==4 and parts[:2]==['RESULT',self.lease] and parts[2] in self.peers
                        and parts[3]=='HELLO' and self.peers[parts[2]]==addr): raise ValueError('unexpected create receipt during flight')
            except socket.timeout: pass
        self.flight_sock.sendto(f'NPCCMD|{self.flight_lease}|STOP|'.encode(),self.flight_peer)
        progress('source_stop_sent')
        if receive(self.flight_sock,['NPCRESULT',self.flight_lease],'STOPPED')!=['STOPPED']: raise ValueError('source stop unconfirmed')
        progress('source_stop_confirmed');terminal.source_stopped()
        progress('bridge_pause_started');terminal.pause();progress('bridge_pause_confirmed')
        result['server_state']='terminal pause confirmed; coordinator stale'
        command('client','MOTIONSTOP')
        logs=[(out/role/'case/home/.config/EgoSoft/X4/45841/engine-output.log').read_text(encoding='utf-8',errors='replace') for role in ('server','client')]
        result['npc_flight_experiment']=check_evidence(*logs,epoch=self.epoch,frame=sector,guest_actor=guest_actor)
        progress('evidence_checked')
        result['npc_flight_experiment'].update(bridge_pause_confirmed=True,checkpoint_after_flight=False,
                                                client_admitted=False,coordinator_reused=False)

    def close(self):
        self.flight_sock.close()
        try: super().close()
        finally:
            for path in self.configs:
                if path.is_file():
                    data=path.read_text(encoding='ascii')
                    path.write_text(data.replace('authority_npc_lease="'+self.flight_lease+'"','authority_npc_lease="redacted"'),encoding='ascii')


def run(args):
    exp=FlightExperiment(flight_seconds=args.flight_seconds,bridge_timeout=min(130,args.timeout))
    old_inject,old_run,old_world=marker.inject,base.run,base.WorldCoordinator
    def inject(case,phase,nonce): old_inject(case,phase,nonce);exp.install(case,phase)
    def wrapped_world(epoch,engine,store,offers,**kwargs):
        world=old_world(epoch,engine,store,offers,**kwargs);exp.bind_world(world,engine,offers);return world
    def run_base(arguments): return old_run(arguments,experiment=exp)
    try:
        marker.inject=inject;base.run=run_base;base.WorldCoordinator=wrapped_world
        result=marker.run(args)
        result['scope']='terminal isolated Linux/Linux natural-flight diagnostic; no admission or shared gameplay'
        if 'server_checkpoint_verified' in result:
            result['initial_checkpoint_verified_before_flight']=result.pop('server_checkpoint_verified')
        if result.get('success') and 'npc_flight_experiment' not in result: result.update(success=False,error='NPC flight evidence missing')
    finally:
        marker.inject=old_inject;base.run=old_run;base.WorldCoordinator=old_world;exp.close()
    (args.out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    p.add_argument('--display',required=True);p.add_argument('--timeout',type=float,default=900)
    p.add_argument('--seed',type=int,default=276944566);p.add_argument('--flight-seconds',type=float,default=30)
    args=p.parse_args()
    if not 5<=args.flight_seconds<=120: p.error('--flight-seconds must be between 5 and 120')
    try: result=run(args)
    except (OSError,ValueError,RuntimeError) as exc: p.exit(1,'REFUSED: '+str(exc)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1

if __name__=='__main__': sys.exit(main())
