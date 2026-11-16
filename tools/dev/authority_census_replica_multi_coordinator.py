"""Bounded two-client census diagnostic; isolated loopback only, no X4 starts."""
import re
import secrets
import select
import socket
import time

import authority_census_replica_coordinator as base
import authority_census_pair_transport as transport
import authority_job_descriptor_loopback as wire


class MultiCensusCoordinator(base.CensusCoordinator):
    """One source and two independently fenced clients; one diagnostic event."""
    CLIENTS=('client1','client2')

    def __init__(self,candidates):
        super().__init__(candidates,defer_source_ack=True)
        self.incarnations={name:secrets.token_hex(16) for name in self.CLIENTS}
        if len(set(self.incarnations.values()) | {self.attempt,self.epoch})!=4:
            raise RuntimeError('connection token collision')
        self.transports={'client1':self.tcp,'client2':transport.OwnedJobTransport()}
        self.dispatched=set()
        self.confirmed=set()
        self.release_identity=None
        self.release_peer=None

    def add_role(self,role):
        if role not in ('server',*self.CLIENTS) or role in self.roles:raise ValueError('invalid role')
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:
            sock.bind(('127.0.0.1',0));sock.setblocking(False)
            lease=secrets.token_hex(16)
            if lease in {self.attempt,self.epoch,*self.incarnations.values(),*(e['lease'] for e in self.roles.values())}:
                raise RuntimeError('lease collision')
            self.roles[role]={'sock':sock,'lease':lease,'peer':None,'events':[],
                              'event_at':0,'pending':None,'counter':0,'witness':None}
            config={'role':'server' if role=='server' else 'client','port':sock.getsockname()[1],
                    'lease':lease,'attempt':self.attempt,'epoch':self.epoch}
            if role=='server':config['participants']=[{'id':n,'incarnation':self.incarnations[n]} for n in self.CLIENTS]
            return config
        except BaseException:
            sock.close();raise

    def _command(self,role,*parts):
        e=self.roles[role]
        if e['peer'] is None:raise RuntimeError('peer unknown')
        wire_role='server' if role=='server' else 'client'
        raw='|'.join(('CMD',e['lease'],wire_role,self.attempt,self.epoch,*parts)).encode('ascii')
        if len(raw)>768 or e['sock'].sendto(raw,e['peer'])!=len(raw):raise RuntimeError('UDP send unconfirmed')

    def _pump(self,timeout):
        self._context();sockets=[v['sock'] for v in self.roles.values()]
        ready,_,bad=select.select(sockets,[],sockets,timeout);self._context()
        if bad:raise RuntimeError('local UDP exception')
        for role,e in self.roles.items():
            if e['sock'] not in ready:continue
            raw,peer=e['sock'].recvfrom(769)
            if len(raw)>768 or peer[0]!='127.0.0.1' or (e['peer'] is not None and e['peer']!=peer):
                raise ValueError('foreign or oversized UDP receipt')
            try:p=raw.decode('ascii').split('|')
            except UnicodeError:raise ValueError('invalid UDP receipt') from None
            wire_role='server' if role=='server' else 'client'
            if p[:5]!=['CENSUS',e['lease'],wire_role,self.attempt,self.epoch]:raise ValueError('foreign receipt context')
            body=p[5:]
            if body==['FAULT']:raise RuntimeError('census owner fault')
            if body and body[0]=='CHECKED':
                if len(body)!=2 or e['pending'] is None or body[1]!=str(e['pending']):raise ValueError('unexpected check reply')
                e['pending']=None;continue
            expected=['READY','DESCRIPTOR','WITNESS_OK','PARTIAL_ACKED','SOURCE_ACKED'] if role=='server' else ['READY','WITNESS_READY','WITNESS_OK']
            at=e['event_at']
            if role=='server' and at==1 and not self.source_started:raise ValueError('source result before START')
            if role=='server' and at==1 and body==['NO_EVENT']:
                e['events'].append(body);e['event_at']=len(expected);continue
            if at>=len(expected) or not body or body[0]!=expected[at]:raise ValueError('reordered or duplicate receipt')
            if body[0]=='READY':
                if len(body)!=1:raise ValueError('invalid READY')
                if any(other is not e and other['peer']==peer for other in self.roles.values()):
                    raise ValueError('UDP endpoint shared across owners')
                e['peer']=peer
            elif body[0]=='DESCRIPTOR':
                if len(body)!=9 or not base._NATURAL.fullmatch(body[1]) or body[2]!='10055':raise ValueError('invalid descriptor receipt')
                try:xyz=[float(v) for v in body[6:9]]
                except ValueError:raise ValueError('invalid coordinates') from None
                body=wire._descriptor({'version':1,'type':'job_descriptor','attempt':self.attempt,'epoch':self.epoch,
                    'transport_sequence':1,'job_sequence':int(body[1]),'index':10055,'macro':body[3],
                    'faction':body[4],'sector_macro':body[5],'x':xyz[0],'y':xyz[1],'z':xyz[2]})
            elif body[0] in ('PARTIAL_ACKED','SOURCE_ACKED'):
                if role!='server' or self.release_identity is None or tuple(body[1:3])!=self.release_identity:
                    raise ValueError('foreign or premature source ACK')
                if body[0]=='PARTIAL_ACKED':
                    if len(body)!=4 or body[3]!=self.release_peer or self.release_peer!=self.CLIENTS[0] or self.confirmed!={self.CLIENTS[0]}:
                        raise ValueError('invalid partial ACK')
                elif len(body)!=3 or self.release_peer!=self.CLIENTS[1] or self.confirmed!=set(self.CLIENTS):
                    raise ValueError('premature final ACK')
            else:
                if role in self.CLIENTS and body[0]=='WITNESS_OK' and role not in self.dispatched:
                    raise ValueError('replica completion before dispatch')
                if len(body)!=4 or e['witness'] is None or tuple(body[1:])!=e['witness']:
                    raise ValueError('foreign witness reply')
            e['events'].append(body);e['event_at']+=1

    def run(self,context):
        if self.context is not None or set(self.roles)!={'server',*self.CLIENTS}:raise RuntimeError('invalid coordinator state')
        self.context=context;self.deadline=context['deadline']
        while any(not e['events'] for e in self.roles.values()):self._pump(min(.2,max(0,self.deadline-time.monotonic())))
        self.guard();self.source_started=True;self._command('server','START');self.guard()
        desc=self._await('server',2)
        if desc==['NO_EVENT']:raise base.NoNewRegistryEntry('no new registry entry observed')
        choices=self.candidates.get(desc['sector_macro'])
        if not choices:raise ValueError('no eligible saved witness for observed sector')
        index=choices[0];self.guard();self._issue_witness('server',desc['job_sequence'],index,desc['sector_macro'])
        self._await('server',3);self.guard()
        for role in self.CLIENTS:
            def witness(received,role=role):
                if received!=desc:raise ValueError('unexpected received descriptor')
                self.guard();self._issue_witness(role,desc['job_sequence'],index,desc['sector_macro'])
                self._await(role,2);self.guard();self.replica_dispatch_attempted=True;self.dispatched.add(role)
                self._command(role,'REPLICA',str(desc['job_sequence']),'10055',desc['macro'],desc['faction'],
                              desc['sector_macro'],*(format(desc[k],'.17g') for k in ('x','y','z')))
                self._await(role,3);self.guard();return True
            received=self.transports[role].exchange(desc,self.attempt,self.epoch,desc['job_sequence'],witness,self.deadline,self.guard)
            if received!=desc:raise RuntimeError('TCP descriptor differs')
            self.guard();self.confirmed.add(role);self.release_identity=(str(desc['job_sequence']),str(desc['index']));self.release_peer=role
            self._command('server','DELIVERY_ACK',*self.release_identity,role,self.incarnations[role])
            self._await('server',4 if role==self.CLIENTS[0] else 5);self.guard()
        self.complete=True
        return {'job_sequence':desc['job_sequence'],'index':desc['index'],'macro':desc['macro'],'faction':desc['faction'],
                'sector_macro':desc['sector_macro'],'position':[desc['x'],desc['y'],desc['z']],'saved_witness_index':index,
                'clients_confirmed':list(self.CLIENTS),'tcp_ack_after_client_replica':True,'source_queue_acked':True,
                'ship_creation_requested':True,'artificial_seed':7183,'runtime_frame_identity_proven':False,
                'continuous_pause_proven':False,'multiplayer_proven':False}

    def cleanup_before_owned_processes(self):
        errors=[]
        for t in self.transports.values():
            try:
                if t.cleanup_before_owned_processes() is not True:raise RuntimeError('helper cleanup unconfirmed')
            except BaseException as error:errors.append(error)
        if errors:raise RuntimeError('multi-client helper cleanup unconfirmed') from errors[0]
        return True

    def _verify_logs(self,logs,source_expected):
        if set(logs)!={'server',*self.CLIENTS}:return False
        for e in self.roles.values():
            try:e['sock'].recvfrom(769)
            except BlockingIOError:pass
            else:return False
        for role,raw in logs.items():
            tag='[X4LAN] AUTH_CENSUS_JOB '
            rows=[line.split(tag,1)[1].strip() for line in raw.decode('utf-8').splitlines() if tag in line]
            rows=[row for row in rows if row!='CHECKED']
            expected=source_expected if role=='server' else (['READY','WITNESS_READY','WITNESS_OK'] if self.complete else ['READY'])
            if rows!=expected:return False
        return True

    def verify_final(self,logs):
        if not self.complete or not self._verify_logs(logs,['READY','DESCRIPTOR','WITNESS_OK','PARTIAL_ACKED','SOURCE_ACKED']):return False
        tag='[X4LAN] AUTH_CENSUS_REPLICA '
        rows={r:[line.split(tag,1)[1].strip() for line in raw.decode('utf-8').splitlines() if tag in line] for r,raw in logs.items()}
        return rows=={'server':[],**{r:['DONE'] for r in self.CLIENTS}}

    def verify_no_event_final(self,logs):
        return (not self.complete and not self.replica_dispatch_attempted and self.roles['server']['events'][-1:]==[['NO_EVENT']]
                and self._verify_logs(logs,['READY','NO_EVENT'])
                and all(b'[X4LAN] AUTH_CENSUS_REPLICA ' not in raw for raw in logs.values()))
