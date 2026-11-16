"""Admitted host and real loopback sockets, synthetic local job application."""
import json
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
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient
import test_authority_experimental_tcp_participants as fixture


class Controller:
    def pause(self, handles): return True
    def resume(self, handles): return True


class JobTCP(unittest.TestCase):
    def setUp(self):
        self.case=fixture.ParticipantTCPTest('test_adapter_refuses_use_outside_active_host_operation')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        self.stop=threading.Event();self.threads=[];self.errors=[];self.applied=[]
        self.addCleanup(self.finish)

    def finish(self):
        self.stop.set()
        for thread in self.threads:thread.join(2)
        self.assertFalse(any(t.is_alive() for t in self.threads))
        self.assertEqual(self.errors,[])

    def client(self, conn, handle, *, fail_apply=False, mutate=False, bad_receipt=None):
        def run():
            try:
                conn.settimeout(3);frame=b''
                while not frame.endswith(b'\n'):
                    chunk=conn.recv(1)
                    if not chunk:raise RuntimeError('admission closed')
                    frame+=chunk
                if json.loads(frame)['kind']!='accepted':raise RuntimeError('missing admission')
                def apply(event):
                    self.applied.append((handle,event))
                    if mutate:event['descriptor']['macro']='different_macro'
                    return not fail_apply
                app=ExperimentalTCPParticipantClient(conn,Controller(),enabled=True,epoch='a'*32,handle=handle,
                                                      timeout=1,apply_job=apply)
                if bad_receipt:
                    original=app._job
                    def tamper(command):
                        original(command)
                        answer=json.loads(app._out)
                        if bad_receipt=='digest':answer['event_sha256']='0'*64
                        elif bad_receipt=='incarnation':answer['incarnation']='0'*32
                        app._out=json.dumps(answer,separators=(',', ':')).encode()+b'\n'
                        if bad_receipt=='duplicate_key':app._out=app._out[:-2]+b',"status":"applied"}\n'
                    app._job=tamper
                while not self.stop.is_set():app.poll(.05)
                app.close()
            except BaseException as error:
                if not self.stop.is_set() and not fail_apply and not mutate and not bad_receipt:self.errors.append(error)
        thread=threading.Thread(target=run);self.threads.append(thread);thread.start()

    def test_two_admitted_clients_apply_before_gate_receipts(self):
        a=self.case.connect();b=self.case.connect()
        self.case.offer_and_claim(a);self.case.offer_and_claim(b)
        self.client(a,1);self.client(b,2)
        self.case.host.tick(.1)
        self.assertEqual(self.case.world.session.state,'running')
        delivery=ExperimentalTCPJobDelivery(self.case.host,enabled=True,timeout=2)
        members=delivery.membership();self.assertEqual(len(members),2)
        event={'epoch':'b'*32,'generation':'c'*32,'sequence':1,'index':10055,
               'descriptor':{'macro':'ship_test_macro','faction':'pioneers','sector_macro':'sector_a','x':1,'y':2,'z':3}}
        lua=LuaRuntime(unpack_returned_tuples=True)
        gate_module=lua.execute("return dofile('src/authority/lua/job_delivery.lua')")
        wrap=lua.eval('function(f) return function(...) return f(...) end end')
        def table(value):
            if isinstance(value,dict):return lua.table_from({k:table(v) for k,v in value.items()})
            if isinstance(value,(tuple,list)):return lua.table_from([table(v) for v in value])
            return value
        def normal(value):
            if hasattr(value,'items'):return {k:normal(v) for k,v in value.items()}
            return value
        releases=[]
        gate=gate_module.new(table({'enabled':True,'generation':event['generation'],'timeout':5,
            'clock':wrap(lambda:0),'membership':wrap(lambda:table(delivery.membership())),
            'send':wrap(lambda p,e:delivery.enqueue(normal(p),normal(e))),
            'release':wrap(lambda epoch,seq,index:releases.append((epoch,seq,index)) or True)}))
        self.assertTrue(gate['begin'](gate,table(event)))
        self.assertEqual(self.applied,[])
        receipts=[]
        def ack(peer,received):
            self.assertEqual(received,event)
            self.assertIn(int(peer['id'].split('_')[1]),[h for h,_ in self.applied])
            result=gate['ack'](gate,table(peer),table(received))
            receipts.append(peer);return result[0] if isinstance(result,tuple) else result
        self.assertTrue(delivery.flush(ack))
        self.assertEqual(receipts,list(members));self.assertEqual(len(self.applied),2)
        self.assertEqual(releases,[(event['epoch'],1,10055)])
        self.assertEqual(gate['state'](gate),'released')
        self.assertTrue(gate['source_acked'](gate,event['epoch'],1,10055))
        with self.assertRaises(ValueError):delivery.deliver(event,members,ack)
        self.assertEqual(len(self.applied),2)

    def test_failed_application_fences_host_and_does_not_confirm_gate(self):
        client=self.case.connect();self.case.offer_and_claim(client);self.client(client,1,fail_apply=True)
        self.case.host.tick(.1);self.assertEqual(self.case.world.session.state,'running')
        delivery=ExperimentalTCPJobDelivery(self.case.host,enabled=True,timeout=2)
        event={'epoch':'b'*32,'generation':'c'*32,'sequence':1,'index':10055,
               'descriptor':{'macro':'ship_test_macro','faction':'pioneers','sector_macro':'sector_a','x':1,'y':2,'z':3}}
        receipts=[]
        with self.assertRaises((RuntimeError,ValueError,ConnectionError)):
            delivery.deliver(event,delivery.membership(),lambda *v:receipts.append(v) or True)
        self.assertEqual(receipts,[]);self.assertTrue(self.case.host._failed)
        with self.assertRaises(RuntimeError):delivery.membership()

    def test_reentrant_queue_failure_cannot_be_reported_as_success(self):
        client=self.case.connect();self.case.offer_and_claim(client);self.client(client,1)
        self.case.host.tick(.1)
        delivery=ExperimentalTCPJobDelivery(self.case.host,enabled=True,timeout=2)
        event={'epoch':'b'*32,'generation':'c'*32,'sequence':1,'index':10055,
               'descriptor':{'macro':'ship_test_macro','faction':'pioneers','sector_macro':'sector_a','x':1,'y':2,'z':3}}
        def reenter(peer,received):
            delivery.enqueue(peer,received)
            try:delivery.enqueue(peer,received)
            except ValueError:pass
            return True
        with self.assertRaises(RuntimeError):delivery.deliver(event,delivery.membership(),reenter)
        self.assertTrue(self.case.host._failed)

    def test_mutated_client_event_cannot_be_acknowledged(self):
        client=self.case.connect();self.case.offer_and_claim(client);self.client(client,1,mutate=True)
        self.case.host.tick(.1)
        delivery=ExperimentalTCPJobDelivery(self.case.host,enabled=True,timeout=2)
        event={'epoch':'b'*32,'generation':'c'*32,'sequence':1,'index':10055,
               'descriptor':{'macro':'ship_test_macro','faction':'pioneers','sector_macro':'sector_a','x':1,'y':2,'z':3}}
        receipts=[]
        with self.assertRaises((RuntimeError,ValueError,ConnectionError)):
            delivery.deliver(event,delivery.membership(),lambda *v:receipts.append(v) or True)
        self.assertEqual(receipts,[]);self.assertTrue(self.case.host._failed)

    def test_control_reader_lease_and_single_delivery_owner(self):
        client=self.case.connect();self.case.offer_and_claim(client);self.client(client,1)
        self.case.host.tick(.1)
        delivery=ExperimentalTCPJobDelivery(self.case.host,enabled=True,timeout=2)
        with self.assertRaises(ValueError):ExperimentalTCPJobDelivery(self.case.host,enabled=True,timeout=2)
        event={'epoch':'b'*32,'generation':'c'*32,'sequence':1,'index':10055,
               'descriptor':{'macro':'ship_test_macro','faction':'pioneers','sector_macro':'sector_a','x':1,'y':2,'z':3}}
        def ack(*_):
            with self.assertRaises(RuntimeError):self.case.control.poll()
            with self.assertRaises(RuntimeError):self.case.control.ready_for_resume()
            return True
        self.assertTrue(delivery.deliver(event,delivery.membership(),ack))

    def test_callback_deadline_fault_cannot_undo_callback_side_effect(self):
        client=self.case.connect();self.case.offer_and_claim(client);self.client(client,1)
        self.case.host.tick(.1)
        delivery=ExperimentalTCPJobDelivery(self.case.host,enabled=True,timeout=.2)
        event={'epoch':'b'*32,'generation':'c'*32,'sequence':1,'index':10055,
               'descriptor':{'macro':'ship_test_macro','faction':'pioneers','sector_macro':'sector_a','x':1,'y':2,'z':3}}
        effects=[]
        def slow(*_):time.sleep(.3);effects.append('already applied');return True
        with self.assertRaises(TimeoutError):delivery.deliver(event,delivery.membership(),slow)
        self.assertEqual(effects,['already applied']);self.assertTrue(self.case.host._failed)

    def test_second_client_disconnect_after_first_receipt_never_completes(self):
        a=self.case.connect();b=self.case.connect()
        self.case.offer_and_claim(a);self.case.offer_and_claim(b)
        self.client(a,1);self.client(b,2,fail_apply=True)
        self.case.host.tick(.1)
        delivery=ExperimentalTCPJobDelivery(self.case.host,enabled=True,timeout=2)
        event={'epoch':'b'*32,'generation':'c'*32,'sequence':1,'index':10055,
               'descriptor':{'macro':'ship_test_macro','faction':'pioneers','sector_macro':'sector_a','x':1,'y':2,'z':3}}
        receipts=[]
        with self.assertRaises((RuntimeError,ValueError,ConnectionError)):
            delivery.deliver(event,delivery.membership(),lambda peer,_:receipts.append(peer['id']) or True)
        self.assertEqual(receipts,['peer_1']);self.assertTrue(self.case.host._failed)

    def check_bad_receipt(self, mode):
        client=self.case.connect();self.case.offer_and_claim(client);self.client(client,1,bad_receipt=mode)
        self.case.host.tick(.1)
        delivery=ExperimentalTCPJobDelivery(self.case.host,enabled=True,timeout=2)
        event={'epoch':'b'*32,'generation':'c'*32,'sequence':1,'index':10055,
               'descriptor':{'macro':'ship_test_macro','faction':'pioneers','sector_macro':'sector_a','x':1,'y':2,'z':3}}
        receipts=[]
        with self.assertRaises((RuntimeError,ValueError,ConnectionError)):
            delivery.deliver(event,delivery.membership(),lambda *v:receipts.append(v) or True)
        self.assertEqual(receipts,[]);self.assertTrue(self.case.host._failed)

    def test_wrong_digest_never_reaches_gate(self):self.check_bad_receipt('digest')
    def test_wrong_incarnation_never_reaches_gate(self):self.check_bad_receipt('incarnation')
    def test_duplicate_json_key_never_reaches_gate(self):self.check_bad_receipt('duplicate_key')

if __name__=='__main__':unittest.main()
