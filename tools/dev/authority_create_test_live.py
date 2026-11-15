#!/usr/bin/env python3
"""Opt-in Linux/X4 creation fixture; imports do not launch X4.

Requires two disposable profiles and an unused output directory. This is not a
network protocol, a full census, crash consistency, or a gameplay test.
"""
import argparse
import json
from pathlib import Path
import re
import secrets
import shutil
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
import authority_checkpoint_marker_live as marker
import authority_two_x4_live as base
from authority.fixture_udp import FixtureUDP


class Experiment:
    def __init__(self, motion=False):
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1',0));self.sock.settimeout(.25)
        self.lease=secrets.token_hex(16);self.epoch=secrets.token_hex(16)
        self.peers={};self.configs=[]
        self.motion=motion;self.relay=None
        self.source_lease=secrets.token_hex(16);self.guest_lease=secrets.token_hex(16)
        if motion:
            self.relay=FixtureUDP(fixture=self.epoch+'.1.pending',source_lease=self.source_lease,
                                  guest_lease=self.guest_lease,max_age_seconds=1)
            self.motion_port=self.relay.address[1]

    def install(self,case,phase):
        lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
        for filename in ('authority_ship_registry.xml','authority_ship_create_receiver.xml','authority_create_test_fixture.xml'):
            shutil.copyfile(ROOT/'tools/dev'/filename,md/filename)
        for source,name in ((ROOT/'tools/dev/authority_create_test_probe.lua','authority_create_test_probe.lua'),
                            (ROOT/'src/authority/lua/x4_ship_engine.lua','x4_ship_engine.lua')):
            shutil.copyfile(source,ui/name)
        if self.motion:
            shutil.copyfile(ROOT/'tools/dev/authority_registry_motion_guard.xml',md/'authority_registry_motion_guard.xml')
            for source in ('tools/dev/authority_registry_motion_probe.lua','tools/dev/authority_registry_motion_native.lua',
                           'src/authority/lua/fixture_wire.lua','src/authority/lua/fixture_continuous.lua'):
                shutil.copyfile(ROOT/source,ui/Path(source).name)
        if phase=='load':
            shutil.copyfile(case.parent.parent/'server/case/extensions/x4_lan_lab/native/x4lan_net.so',lab/'native/x4lan_net.so')
        config=ui/'config.lua';data=config.read_text(encoding='ascii')
        if not data.endswith('}\n'): raise ValueError('unexpected private configuration')
        role='server' if phase=='save' else 'client'
        data=data[:-2]+f', authority_create_role="{role}", authority_create_port={self.sock.getsockname()[1]}, authority_create_lease="{self.lease}", authority_create_epoch="{self.epoch}"'+'}\n'
        if self.motion:
            # Frame is not known until the actual fixture is created. The relay
            # is initialized just before MOTION after both probes have started.
            # A dedicated port must therefore be reserved before installation.
            lease=self.source_lease if role=='server' else self.guest_lease
            data=data[:-2]+f', authority_motion_test=true, authority_motion_port={self.motion_port}, authority_motion_lease="{lease}", authority_motion_save_path={json.dumps(str(case/"home/.config/EgoSoft/X4/45841/save"))}'+'}\n'
        config.write_text(data,encoding='ascii');self.configs.append(config)
        manifest=lab/'ui.xml';data=manifest.read_text(encoding='utf-8')
        hook='    <file name="ui/authority_checkpoint_marker_probe.lua" />\n'
        if data.count(hook)!=1: raise ValueError('marker script hook missing')
        additions='    <file name="ui/x4_ship_engine.lua" />\n'
        if self.motion:
            additions+=''.join(f'    <file name="ui/{name}" />\n' for name in ('fixture_wire.lua','fixture_continuous.lua','authority_registry_motion_probe.lua','authority_registry_motion_native.lua'))
        additions+='    <file name="ui/authority_create_test_probe.lua" />\n'
        manifest.write_text(data.replace(hook,hook+additions),encoding='utf-8')
        if phase=='save':
            probe=ui/'authority_world_bridge_probe.lua';data=probe.read_text(encoding='utf-8')
            hook=' if not started and now-loaded_at>=3 and not X4LAN_AUTHORITY_MARKER_READY() then return end\n'
            if data.count(hook)!=1: raise ValueError('marker gate missing')
            probe.write_text(data.replace(hook,hook+' if not started and now-loaded_at>=3 and not X4LAN_AUTHORITY_CREATE_READY() then return end\n'),encoding='utf-8')

    def protected(self,case):
        lab=case/'extensions/x4_lan_lab'
        paths=[lab/'md'/x for x in ('authority_ship_registry.xml','authority_ship_create_receiver.xml','authority_create_test_fixture.xml')] + [lab/'ui'/x for x in ('x4_ship_engine.lua','authority_create_test_probe.lua')] + [lab/'native/x4lan_net.so']
        if self.motion:
            paths += [lab/'md/authority_registry_motion_guard.xml'] + [lab/'ui'/x for x in ('fixture_wire.lua','fixture_continuous.lua','authority_registry_motion_probe.lua','authority_registry_motion_native.lua')]
        return paths

    def on_ready(self,*,server_proc,server_started,server_identity,client_proc,client_started,client_identity,game,out,deadline,result,**kwargs):
        def check():
            if (base.client.game_identity(server_proc,server_started,game)!=server_identity or
                base.client.game_identity(client_proc,client_started,game)!=client_identity):
                raise RuntimeError('owned X4 process changed')
            for role in ('server','client'):
                log=out/role/'case/home/.config/EgoSoft/X4/45841/engine-output.log'
                if log.exists() and '[X4LAN] AUTH_CREATE '+role+' ERROR ' in log.read_text(encoding='utf-8',errors='replace'):
                    raise RuntimeError(role+' creation probe failed')
        def receive(expected_role=None,expected_name=None):
            while time.monotonic()<deadline:
                check()
                if self.relay: self.relay.poll(64)
                try: data,addr=self.sock.recvfrom(1024)
                except socket.timeout: continue
                if addr[0]!='127.0.0.1': continue
                try: text=data.decode('ascii')
                except UnicodeError: continue
                prefix='RESULT|'+self.lease+'|'
                if not text.startswith(prefix): continue
                parts=text[len(prefix):].split('|');role=parts.pop(0)
                if role not in ('server','client') or not parts: raise ValueError('bad test receipt')
                if parts==['HELLO']:
                    if role in self.peers and self.peers[role]!=addr: raise ValueError('test peer changed')
                    self.peers[role]=addr;continue
                if self.peers.get(role)!=addr or role!=expected_role or parts[0]!=expected_name:
                    raise ValueError('unexpected or out-of-order test receipt')
                return parts
            raise TimeoutError('creation test receipt timed out')
        while len(self.peers)<2:
            try:
                data,addr=self.sock.recvfrom(1024)
                parts=data.decode('ascii').split('|')
                if len(parts)==4 and parts[:2]==['RESULT',self.lease] and parts[2] in ('server','client') and parts[3]=='HELLO' and addr[0]=='127.0.0.1':
                    if parts[2] in self.peers and self.peers[parts[2]]!=addr: raise ValueError('test peer changed')
                    self.peers[parts[2]]=addr
            except socket.timeout: pass
            check()
            if time.monotonic()>=deadline: raise TimeoutError('creation test handshake timed out')
        def command(role,name,fields=()):
            packet='|'.join(('CMD',self.lease,name,*fields))
            self.sock.sendto(packet.encode('ascii'),self.peers[role])
            return receive(role,{'STATUS':'FAULTED','AFTER':'AFTER_CONFLICT'}.get(name,name))
        def measurement(row,with_descriptor=False):
            if len(row)!=(12 if with_descriptor else 6) or not re.fullmatch(r'[A-Za-z0-9_]+',row[5]) or row[1]!='1' or not row[2].isdigit() or int(row[2])==0 or not row[3].isdigit() or not row[4].isdigit():
                raise ValueError('bad creation measurement')
            before,after=map(int,row[3:5]);
            if after!=before+1: raise ValueError('test fleet count did not increase by one')
            return row[2],before,after,row[5]
        spawned=command('server','SPAWN')
        server_id,sbefore,safter,server_sector=measurement(spawned,with_descriptor=True)
        macro,owner,seed,x,y,z=spawned[6:]
        if (macro,owner,seed,x,y,z)!=('ship_arg_s_fighter_01_a_macro','argon','7183','-400','100000','500'):
            raise ValueError('unexpected server descriptor')
        descriptor=(macro,server_sector,owner,seed,x,y,z)
        client_id,cbefore,cafter,client_sector=measurement(command('client','CREATE',descriptor))
        again,rbefore,rafter,replay_sector=measurement(command('client','REPLAY'))
        if (again,rbefore,rafter,replay_sector)!=(client_id,cbefore,cafter,client_sector) or server_sector!=client_sector: raise ValueError('replay changed identity or count')
        if self.motion:
            # Configure the one-fixture relay only after comparing the actual
            # test sectors; no packet has been serviced before this point.
            fixture=self.epoch+'.1.'+client_sector
            if len(fixture)>64: raise ValueError('motion fixture label too long')
            self.relay.fixture=fixture
            command('client','MOTION');command('server','MOTION')
            finish=time.monotonic()+8
            if finish>=deadline: raise TimeoutError('insufficient motion test time')
            while time.monotonic()<finish:
                check();self.relay.poll(64)
                try:
                    data,addr=self.sock.recvfrom(1024)
                    parts=data.decode('ascii').split('|')
                    if not (len(parts)==4 and parts[:2]==['RESULT',self.lease] and parts[2] in self.peers
                            and parts[3]=='HELLO' and self.peers[parts[2]]==addr):
                        raise ValueError('unexpected receipt during motion')
                except socket.timeout: pass
            command('server','MOTIONSTOP');command('client','MOTIONSTOP')
            from authority_registry_motion_evidence import validate
            logs=[(out/role/'case/home/.config/EgoSoft/X4/45841/engine-output.log').read_text(encoding='utf-8',errors='replace')
                  for role in ('server','client')]
            result['registry_motion_test']=validate(*logs,epoch=self.epoch,frame=client_sector)
        conflict=command('client','CONFLICT')
        if conflict!=['CONFLICT',str(cafter)]: raise ValueError('conflict changed count')
        if command('client','STATUS')!=['FAULTED']: raise ValueError('registry did not fault')
        if command('client','AFTER')!=['AFTER_CONFLICT',str(cafter)]: raise ValueError('post-fault request did not refuse')
        check()
        result.update(creation_test={'server_index':1,'client_index':1,'server_local_id':server_id,'client_local_id':client_id,
            'sector_macro':client_sector,'server_matching_faction_macro_before':sbefore,'server_matching_faction_macro_after':safter,
            'client_matching_faction_macro_before':cbefore,'client_matching_faction_macro_after':cafter,
            'replay_same_local_reference':True,'conflict_refused':True,'register_faulted':True,'post_fault_refused':True,
            'count_scope':'operational ships of one macro in faction argon fleet; faction coverage unproven',
            'fixture_descriptor_forwarded_over_loopback':True,'descriptor_coordinate_source':'server create request; not native pose readback',
            'arbitrary_creation_discovery_proven':False})

    def close(self):
        self.sock.close()
        if self.relay: self.relay.close()
        for path in self.configs:
            if path.is_file():
                data=path.read_text(encoding='ascii');needle='authority_create_lease="'+self.lease+'"'
                if data.count(needle)!=1: raise ValueError('test lease redaction failed')
                path.write_text(data.replace(needle,'authority_create_lease="redacted"'),encoding='ascii')
                if self.motion:
                    data=path.read_text(encoding='ascii')
                    for lease in (self.source_lease,self.guest_lease):
                        data=data.replace('authority_motion_lease="'+lease+'"','authority_motion_lease="redacted"')
                    path.write_text(data,encoding='ascii')


def run(args):
    exp=Experiment(motion=getattr(args,'motion',False));old_inject=marker.inject;old_run=base.run
    def inject(case,phase,nonce): old_inject(case,phase,nonce);exp.install(case,phase)
    def run_base(arguments): return old_run(arguments,experiment=exp)
    try:
        marker.inject=inject;base.run=run_base
        result=marker.run(args)
        result['scope']='two isolated Linux X4 processes; one post-checkpoint fixture; no admission or gameplay'
        if result.get('success') and 'creation_test' not in result: result.update(success=False,error='creation evidence absent')
    finally:
        marker.inject=old_inject;base.run=old_run;exp.close()
    (args.out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    p.add_argument('--display',required=True);p.add_argument('--timeout',type=float,default=900)
    p.add_argument('--seed',type=int,default=276944566)
    p.add_argument('--motion',action='store_true',help='opt in to guarded, one-fixture test setter impulses')
    try: result=run(p.parse_args())
    except (OSError,ValueError,RuntimeError) as exc: p.exit(1,'REFUSED: '+str(exc)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['success'] else 1

if __name__=='__main__': sys.exit(main())
