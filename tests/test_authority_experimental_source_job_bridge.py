"""Real admitted local TCP and UDP with actual Lua gate/IPC and fake X4 MD."""
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
from lupa.luajit21 import LuaRuntime

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_source_job_bridge import ExperimentalSourceJobBridge
import test_authority_experimental_tcp_job_delivery as fixture


class SourceBridgeTest(unittest.TestCase):
    def setUp(self):
        self.base=fixture.JobTCP('test_two_admitted_clients_apply_before_gate_receipts');self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.epoch,self.generation,self.attempt,self.lease=(x*32 for x in 'abcd')
        self.errors=[];self.stop=threading.Event();self.thread=None;self.releases=[]
        self.addCleanup(self.finish)

    def finish(self):
        self.stop.set()
        if self.thread:self.thread.join(4);self.assertFalse(self.thread.is_alive())
        self.assertEqual(self.errors,[])

    def start_source(self,sock,mode):
        def run():
            try:
                lua=LuaRuntime(unpack_returned_tuples=True)
                module=lua.execute("return dofile('src/authority/lua/source_job_ipc.lua')")
                gate=lua.execute("return dofile('src/authority/lua/job_delivery.lua')")
                wrap=lua.eval('function(f) return function(...) return f(...) end end')
                def table(v):
                    if isinstance(v,dict):return lua.table_from({k:table(x) for k,x in v.items()})
                    return v
                candidate_ref=[];mutated=[]
                def guard():
                    if mode=='mutate_guard' and candidate_ref and not mutated:
                        candidate_ref[0]['descriptor']['x']=999;mutated.append(True)
                    return True
                def send(raw):
                    if mode=='bad_candidate' and '|CANDIDATE|' in raw:raw=raw.replace(self.generation,'f'*32)
                    if mode=='mutate_send' and candidate_ref and '|CANDIDATE|' in raw:
                        candidate_ref[0]['descriptor']['x']=999
                    sock.send(raw.encode())
                    if mode=='duplicate_ready' and '|READY|' in raw:sock.send(raw.encode())
                    return True
                def release(epoch,seq,index):
                    assert len(self.base.applied)==2*(len(self.releases)+1)
                    self.releases.append((epoch,seq,index));return True
                app=module.new(table({'enabled':True,'lease':self.lease,'attempt':self.attempt,'epoch':self.epoch,
                     'generation':self.generation,'timeout':4,'gate':gate,'clock':wrap(time.monotonic),
                     'guard':wrap(guard),'send':wrap(send),'release':wrap(release)}))
                event={'epoch':self.epoch,'generation':self.generation,'sequence':1,'index':10055,
                       'descriptor':{'macro':'ship_test_macro','faction':'pioneers','sector_macro':'sector_a','x':1,'y':2,'z':3}}
                candidate_ref.append(table(event));assert app['candidate'](app,candidate_ref[0])
                rearmed=0
                sock.settimeout(.1)
                while not self.stop.is_set():
                    try:packet=sock.recv(4097).decode()
                    except socket.timeout:continue
                    if mode=='no_rearm' and '|REARM|' in packet:continue
                    if mode=='wrong_receipt' and '|RECEIPT|' in packet:
                        packet=packet.replace('peer_1','peer_9')
                    result=app['packet'](app,packet)
                    if isinstance(result,tuple):result=result[0]
                    if not result:break
                    if app['state'](app)=='await_source_ack':
                        if mode=='no_source_ack':continue
                        assert app['source_acked'](app,self.epoch,rearmed+1,10055+rearmed)
                        if mode=='early_candidate':
                            event['sequence']=2;event['index']=10056
                            result=app['candidate'](app,table(event))
                            assert isinstance(result,tuple) and result[0] is False
                            break
                    if app['state'](app)=='idle':
                        rearmed+=1
                        if mode!='two_events' or rearmed==2:break
                        event['sequence']=2;event['index']=10056
                        candidate_ref[:]=[table(event)];assert app['candidate'](app,candidate_ref[0])
            except BaseException as error:
                if not self.stop.is_set():self.errors.append(error)
            finally:sock.close()
        self.thread=threading.Thread(target=run,daemon=True);self.thread.start()

    def exercise(self,mode):
        a=self.base.case.connect();b=self.base.case.connect()
        self.base.case.offer_and_claim(a);self.base.case.offer_and_claim(b)
        self.base.client(a,1);self.base.client(b,2,fail_apply=mode=='client_fail')
        self.base.case.host.tick(.1)
        delivery=ExperimentalTCPJobDelivery(self.base.case.host,enabled=True,timeout=1)
        server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);server.bind(('127.0.0.1',0))
        source=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);source.bind(('127.0.0.1',0))
        server.connect(source.getsockname());source.connect(server.getsockname())
        self.start_source(source,mode)
        refused=[]
        def supervisor_guard():
            if mode=='guard_reentry':
                for action in (self.base.case.host.tick,self.base.case.control.poll):
                    try:action()
                    except RuntimeError:refused.append(True)
                    else:raise AssertionError('reentrant host/control access was allowed')
            return True
        bridge=ExperimentalSourceJobBridge(delivery,server,enabled=True,lease=self.lease,attempt=self.attempt,
                   epoch=self.epoch,generation=self.generation,guard=supervisor_guard,timeout=2)
        if mode=='double_bind':
            with self.assertRaises(ValueError):ExperimentalSourceJobBridge(delivery,server,enabled=True,lease=self.lease,attempt=self.attempt,
                   epoch=self.epoch,generation=self.generation,guard=lambda:True,timeout=2)
        if mode in ('ok','double_bind','mutate_guard','mutate_send','guard_reentry','two_events'):
            result=bridge.run_one();self.assertTrue(result['source_ack_observed']);self.assertEqual(len(result['members']),2)
            self.assertEqual(result['event']['descriptor']['x'],1)
            if mode=='guard_reentry':self.assertTrue(refused)
            self.assertEqual(self.releases,[(self.epoch,1,10055)]);self.assertEqual(bridge.state,'idle')
            if mode=='two_events':
                result=bridge.run_one();self.assertEqual(result['event']['sequence'],2)
                self.assertEqual(self.releases,[(self.epoch,1,10055),(self.epoch,2,10056)])
            bridge.close()
        else:
            with self.assertRaises((ValueError,RuntimeError,TimeoutError,ConnectionError)):bridge.run_one()
            self.assertEqual(bridge.state,'failed');self.assertTrue(self.base.case.host._failed)
            if mode in ('bad_candidate','client_fail','wrong_receipt','duplicate_ready'):self.assertEqual(self.releases,[])
            if mode in ('no_source_ack','no_rearm','early_candidate'):self.assertEqual(self.releases,[(self.epoch,1,10055)])

    def test_two_admitted_clients_and_real_lua_gate(self):self.exercise('ok')
    def test_foreign_generation_before_send(self):self.exercise('bad_candidate')
    def test_failed_second_client_does_not_release_source(self):self.exercise('client_fail')
    def test_wrong_source_receipt_does_not_release(self):self.exercise('wrong_receipt')
    def test_lost_source_ack_is_failure_even_after_release(self):self.exercise('no_source_ack')
    def test_mutation_during_guard_is_not_published(self):self.exercise('mutate_guard')
    def test_mutation_during_send_is_not_published(self):self.exercise('mutate_send')
    def test_source_socket_cannot_be_bound_twice(self):self.exercise('double_bind')
    def test_queued_duplicate_prevents_source_receipt(self):self.exercise('duplicate_ready')
    def test_guard_cannot_reenter_host_or_control_reader(self):self.exercise('guard_reentry')
    def test_immediate_next_candidate_waits_for_rearm(self):self.exercise('two_events')
    def test_missing_rearm_receipt_fences_after_ack(self):self.exercise('no_rearm')
    def test_early_candidate_fails_instead_of_being_discarded(self):self.exercise('early_candidate')

if __name__=='__main__':unittest.main()
