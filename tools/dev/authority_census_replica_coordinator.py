"""Private census replica coordinator; no X4 start or save."""
import re
import secrets
import select
import socket
import time

import authority_census_archive_provenance as archive
import authority_census_pair_transport as transport
import authority_job_descriptor_loopback as wire

_NATURAL=re.compile(r'[1-9][0-9]{0,15}\Z',re.ASCII)


class NoNewRegistryEntry(RuntimeError):
    """One bounded observation ended without a newly allocated entry."""


class CensusCoordinator:
    """Correlate one local replica and one TCP ACK; no mutation retries."""
    def __init__(self,candidates, *, defer_source_ack=False):
        if type(defer_source_ack) is not bool:raise ValueError('invalid source ACK mode')
        self.defer_source_ack=defer_source_ack
        self.candidates=candidates;self.attempt=secrets.token_hex(16);self.epoch=archive.REGISTRY_EPOCH
        if self.attempt==self.epoch:raise RuntimeError('run and registry epochs collide')
        self.roles={};self.context=None;self.deadline=None;self.complete=False;self.source_started=False
        self.tcp=transport.OwnedJobTransport()
        self.replica_dispatch_attempted=False
        self.release_identity=None

    def add_role(self,role):
        if role not in ('server','client') or role in self.roles:raise ValueError('invalid role')
        sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.roles[role]={'sock':sock,'lease':secrets.token_hex(16),'peer':None,'events':[],
                          'event_at':0,'pending':None,'counter':0,'witness':None}
        sock.bind(('127.0.0.1',0));sock.setblocking(False)
        return {'role':role,'port':sock.getsockname()[1],'lease':self.roles[role]['lease'],
                'attempt':self.attempt,'epoch':self.epoch}

    def _context(self):
        if self.context is None or self.context['check']() is not True or time.monotonic()>=self.deadline:
            raise RuntimeError('census context failed')

    def _command(self,role,*parts):
        e=self.roles[role]
        if e['peer'] is None:raise RuntimeError('peer unknown')
        raw='|'.join(('CMD',e['lease'],role,self.attempt,self.epoch,*parts)).encode('ascii')
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
            if p[:5]!=['CENSUS',e['lease'],role,self.attempt,self.epoch]:raise ValueError('foreign receipt context')
            body=p[5:]
            if body==['FAULT']:raise RuntimeError('census owner fault')
            if body and body[0]=='CHECKED':
                if len(body)!=2 or e['pending'] is None or body[1]!=str(e['pending']):raise ValueError('unexpected check reply')
                e['pending']=None;continue
            expected=(['READY','DESCRIPTOR','WITNESS_OK']+(['SOURCE_ACKED'] if self.defer_source_ack else [])
                      if role=='server' else ['READY','WITNESS_READY','WITNESS_OK'])
            at=e['event_at']
            if role=='server' and at==1 and not self.source_started:
                raise ValueError('source result before START')
            if role=='server' and at==1 and body==['NO_EVENT']:
                e['events'].append(body);e['event_at']=len(expected)
                continue
            if at>=len(expected) or not body or body[0]!=expected[at]:raise ValueError('reordered or duplicate receipt')
            if body[0]=='READY':
                if len(body)!=1:raise ValueError('invalid READY')
                e['peer']=peer
            elif body[0]=='DESCRIPTOR':
                if len(body)!=9 or not _NATURAL.fullmatch(body[1]) or body[2]!='10055':raise ValueError('invalid descriptor receipt')
                try:xyz=[float(v) for v in body[6:9]]
                except ValueError:raise ValueError('invalid coordinates') from None
                body=wire._descriptor({'version':1,'type':'job_descriptor','attempt':self.attempt,'epoch':self.epoch,
                    'transport_sequence':1,'job_sequence':int(body[1]),'index':10055,'macro':body[3],
                    'faction':body[4],'sector_macro':body[5],'x':xyz[0],'y':xyz[1],'z':xyz[2]})
            elif body[0]=='SOURCE_ACKED':
                if (role!='server' or self.release_identity is None or len(body)!=3
                    or tuple(body[1:])!=self.release_identity):
                    raise ValueError('foreign or premature source ACK')
            else:
                if role=='client' and body[0]=='WITNESS_OK' and not self.replica_dispatch_attempted:
                    raise ValueError('replica completion before dispatch')
                if len(body)!=4 or e['witness'] is None or tuple(body[1:])!=e['witness']:
                    raise ValueError('foreign witness reply')
            e['events'].append(body);e['event_at']+=1

    def guard(self):
        self._context()
        for role,e in self.roles.items():
            if e['pending'] is not None:raise RuntimeError('overlapping checks')
            e['counter']+=1
            if e['counter']>2147483647:raise RuntimeError('check counter exhausted')
            e['pending']=e['counter'];self._command(role,'CHECK',str(e['counter']))
        while any(e['pending'] is not None for e in self.roles.values()):
            remaining=self.deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('census guard deadline')
            self._pump(min(.2,remaining))
        self._context();return True

    def _await(self,role,count):
        while len(self.roles[role]['events'])<count:
            self.guard()
            if len(self.roles[role]['events'])<count:self._pump(min(.2,max(0,self.deadline-time.monotonic())))
        self.guard();return self.roles[role]['events'][count-1]

    def _issue_witness(self,role,seq,index,macro):
        e=self.roles[role]
        if e['witness'] is not None:raise RuntimeError('witness already issued')
        e['witness']=(str(seq),str(index),macro)
        self._command(role,'WITNESS',*e['witness'])

    def run(self,context):
        if self.context is not None or set(self.roles)!={'server','client'}:raise RuntimeError('invalid coordinator state')
        self.context=context;self.deadline=context['deadline']
        while any(not e['events'] for e in self.roles.values()):
            self._pump(min(.2,max(0,self.deadline-time.monotonic())))
        self.guard();self.source_started=True;self._command('server','START');self.guard()
        desc=self._await('server',2)
        if desc==['NO_EVENT']:raise NoNewRegistryEntry('no new registry entry observed')
        choices=self.candidates.get(desc['sector_macro'])
        if not choices:raise ValueError('no eligible saved witness for observed sector')
        index=choices[0]
        self.guard();self._issue_witness('server',desc['job_sequence'],index,desc['sector_macro'])
        self._await('server',3);self.guard()
        def client_witness(received):
            if received!=desc:raise ValueError('unexpected received descriptor')
            self.guard();self._issue_witness('client',desc['job_sequence'],index,desc['sector_macro'])
            self._await('client',2);self.guard()
            self.replica_dispatch_attempted=True
            self._command('client','REPLICA',str(desc['job_sequence']),'10055',desc['macro'],desc['faction'],
                          desc['sector_macro'],*(format(desc[k],'.17g') for k in ('x','y','z')))
            self._await('client',3);self.guard()
            return True
        result=self.tcp.exchange(desc,self.attempt,self.epoch,desc['job_sequence'],client_witness,self.deadline,self.guard)
        if result!=desc:raise RuntimeError('TCP descriptor differs')
        self.guard()
        if self.defer_source_ack:
            # attempt is also the source queue generation, bound in the UDP
            # envelope. A failed/uncertain send is never retried.
            self.release_identity=(str(desc['job_sequence']),str(desc['index']))
            self._command('server','DELIVERY_ACK',*self.release_identity)
            self._await('server',4)
            self.guard()
        self.complete=True
        details={'transport_sequence':1,'job_sequence':desc['job_sequence'],'index':10055,
                'macro':desc['macro'],'faction':desc['faction'],'sector_macro':desc['sector_macro'],
                'position':[desc['x'],desc['y'],desc['z']],'saved_witness_index':index,
                'tcp_ack_after_client_replica':True,'ship_creation_requested':True,'artificial_seed':7183,
                'runtime_frame_identity_proven':False,'continuous_pause_proven':False,'multiplayer_proven':False}
        if self.defer_source_ack:details['source_queue_acked']=True
        return details

    def cleanup_before_owned_processes(self):
        return self.tcp.cleanup_before_owned_processes()

    def _verify_logs(self,logs,source_expected):
        if set(logs)!={'server','client'}:return False
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
        expected=['READY','DESCRIPTOR','WITNESS_OK']+(['SOURCE_ACKED'] if self.defer_source_ack else [])
        if not self.complete or not self._verify_logs(logs,expected):return False
        tag='[X4LAN] AUTH_CENSUS_REPLICA '
        rows={role:[line.split(tag,1)[1].strip() for line in raw.decode('utf-8').splitlines() if tag in line] for role,raw in logs.items()}
        return rows=={'server':[],'client':['DONE']}

    def verify_no_event_final(self,logs):
        return (not self.complete and not self.replica_dispatch_attempted
                and self.roles['server']['events'][-1:]==[['NO_EVENT']]
                and self._verify_logs(logs,['READY','NO_EVENT'])
                and all(b'[X4LAN] AUTH_CENSUS_REPLICA ' not in raw for raw in logs.values()))

    def cleanup_after_owned_processes(self):
        errors=[]
        for e in self.roles.values():
            try:e['sock'].close()
            except BaseException as error:errors.append(error)
        if errors:raise RuntimeError('UDP cleanup unconfirmed') from errors[0]
        return True
