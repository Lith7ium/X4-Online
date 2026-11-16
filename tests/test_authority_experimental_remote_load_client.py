"""Real loopback sockets plus fake X4 events; no game or external network."""
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from authority.experimental_remote_load_client import ExperimentalRemoteLoadClient
import authority.experimental_remote_load_client as subject
from authority.experimental_tcp_control import offer_request
from authority.load_messages import Offer
from authority.trusted_load_messages import decode_load_claim, encode_bound_offer
from authority.trusted_marker_load_session import MarkerBoundOffer
from lockstep.launcher.joinfiles import FetchError, FileService


class RemoteLoadClientTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup); self.root=Path(temp.name)
        self.data=b'cooperative test save'; self.save=self.root/'source'; self.save.write_bytes(self.data)
        self.token='a'*32; self.marker='b'*32
        self.service=FileService(self.token,slots=(1,)).start(); self.addCleanup(self.service.close)
        self.service.offer('j1.xml.gz',self.save)
        self.offer=Offer(world_epoch='epoch',connection_handle=1,baseline_id=1,load_generation=1,
            attempt_id='c'*32,checkpoint_id='checkpoint-'+'d'*32,sha256=hashlib.sha256(self.data).hexdigest(),
            size=len(self.data),name='j1.xml.gz')
        self.bound=MarkerBoundOffer(self.offer,self.marker)

    def connect(self, *, ack_attempt=None, after_ack=b'', offer=None, after_offer=b'', not_ready_count=0, offer_delay=0, io_timeout=2):
        listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM);listener.bind(('127.0.0.1',0));listener.listen(1)
        listener.settimeout(3);client=socket.create_connection(listener.getsockname(),timeout=3)
        errors=[]; claims=[]
        def serve():
            try:
                conn,_=listener.accept();conn.settimeout(3)
                with conn:
                    stream=conn.makefile('rb')
                    for _ in range(not_ready_count):
                        if stream.readline()!=offer_request(): raise AssertionError('unexpected offer request')
                        conn.sendall(b'{\"version\":1,\"kind\":\"not_ready\"}\n')
                    if stream.readline()!=offer_request(): raise AssertionError('unexpected offer request')
                    if offer_delay: time.sleep(offer_delay)
                    conn.sendall(encode_bound_offer(offer or self.bound)+b'\n'+after_offer)
                    line=stream.readline()
                    if not line: return
                    claims.append(decode_load_claim(line.rstrip(b'\n')))
                    msg={'version':1,'kind':'accepted','attempt_id':ack_attempt or self.offer.attempt_id}
                    conn.sendall(json.dumps(msg).encode()+b'\n'+after_ack)
            except (OSError,ValueError,AssertionError) as error: errors.append(error)
            finally: listener.close()
        thread=threading.Thread(target=serve,daemon=True);thread.start()
        self.addCleanup(lambda:thread.join(4))
        obj=ExperimentalRemoteLoadClient(client,enabled=True,file_host='127.0.0.1',file_port=self.service.port,
            file_token=self.token,file_slot=1,deadline=time.monotonic()+5,io_timeout=io_timeout)
        self.addCleanup(obj.close)
        return obj,claims,errors

    def staged(self,obj):
        bound=obj.request_offer(); self.assertEqual(bound,self.bound)
        path=obj.download(self.root/'download'); self.assertEqual(path.read_bytes(),self.data)
        obj.verify_staged(path); return path

    def observations(self,obj):
        attempt=self.offer.attempt_id
        obj.load_requested(attempt);obj.loaded_marker(attempt,self.marker);obj.paused(attempt,True)

    def test_not_ready_then_offer_retries_on_same_socket(self):
        obj,claims,errors=self.connect(not_ready_count=2)
        self.staged(obj); self.observations(obj); obj.claim(self.offer.attempt_id)
        self.assertEqual(len(claims),1)
        self.assertFalse(errors)

    def test_not_ready_retry_obeys_overall_deadline(self):
        obj,_,_=self.connect(not_ready_count=10)
        obj._deadline=time.monotonic()+.25
        with self.assertRaises(TimeoutError): obj.request_offer()
        with self.assertRaises(RuntimeError): obj.request_offer()

    def test_offer_can_wait_past_io_timeout_but_within_deadline(self):
        obj,_,errors=self.connect(offer_delay=.2,io_timeout=.05)
        self.assertEqual(obj.request_offer(),self.bound)
        self.assertFalse(errors)

    def test_silent_offer_wait_ends_at_absolute_deadline(self):
        obj,_,_=self.connect(offer_delay=.3,io_timeout=.05)
        obj._deadline=time.monotonic()+.1
        with self.assertRaises(TimeoutError): obj.request_offer()
        with self.assertRaises(RuntimeError): obj.request_offer()

    def test_offer_wait_reports_eof_without_waiting_for_deadline(self):
        listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        listener.bind(('127.0.0.1',0)); listener.listen(1)
        client=socket.create_connection(listener.getsockname(),timeout=2)
        def serve():
            conn,_=listener.accept()
            with conn: conn.recv(4096)
            listener.close()
        thread=threading.Thread(target=serve,daemon=True); thread.start()
        self.addCleanup(lambda:thread.join(2))
        obj=ExperimentalRemoteLoadClient(client,enabled=True,file_host='127.0.0.1',file_port=self.service.port,
            file_token=self.token,file_slot=1,deadline=time.monotonic()+2,io_timeout=.05)
        self.addCleanup(obj.close)
        start=time.monotonic()
        with self.assertRaises(ConnectionError): obj.request_offer()
        self.assertLess(time.monotonic()-start,1)

    def test_unexpected_input_after_not_ready_faults(self):
        listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        listener.bind(('127.0.0.1',0)); listener.listen(1)
        client=socket.create_connection(listener.getsockname(),timeout=2)
        def serve():
            conn,_=listener.accept()
            with conn:
                conn.recv(4096)
                conn.sendall(b'{"version":1,"kind":"not_ready"}\nunexpected\n')
            listener.close()
        thread=threading.Thread(target=serve,daemon=True); thread.start()
        self.addCleanup(lambda:thread.join(2))
        obj=ExperimentalRemoteLoadClient(client,enabled=True,file_host='127.0.0.1',file_port=self.service.port,
            file_token=self.token,file_slot=1,deadline=time.monotonic()+3,io_timeout=1)
        self.addCleanup(obj.close)
        with self.assertRaises(ConnectionError): obj.request_offer()

    def test_real_loopback_transfer_claim_and_no_overread(self):
        obj,claims,errors=self.connect(after_ack=b'next-command\n')
        self.staged(obj); self.observations(obj); obj.claim(self.offer.attempt_id)
        conn=obj.take_connection(); self.addCleanup(conn.close); conn.settimeout(2)
        self.assertEqual(conn.recv(64),b'next-command\n')
        self.assertEqual(claims[0].receipt.attempt_id,self.offer.attempt_id)
        self.assertEqual(claims[0].marker,self.marker);self.assertFalse(errors)
        with self.assertRaises(RuntimeError): obj.take_connection()

    def test_changed_save_and_wrong_marker_fault_attempt(self):
        for failure in ('changed','marker'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                obj,claims,_=self.connect(); obj.request_offer(); path=obj.download(Path(directory)/'download')
                obj.verify_staged(path); obj.load_requested(self.offer.attempt_id)
                if failure=='marker':
                    with self.assertRaises(ValueError): obj.loaded_marker(self.offer.attempt_id,'f'*32)
                else:
                    obj.loaded_marker(self.offer.attempt_id,self.marker);obj.paused(self.offer.attempt_id,True)
                    path.write_bytes(b'changed')
                    with self.assertRaises(ValueError): obj.claim(self.offer.attempt_id)
                self.assertEqual(claims,[])
                with self.assertRaises(RuntimeError): obj.claim(self.offer.attempt_id)

    def test_wrong_accepted_attempt_is_rejected(self):
        obj,claims,_=self.connect(ack_attempt='e'*32);self.staged(obj);self.observations(obj)
        with self.assertRaises(ValueError): obj.claim(self.offer.attempt_id)
        self.assertEqual(len(claims),1)
        with self.assertRaises(RuntimeError): obj.take_connection()

    def test_mismatched_file_offer_and_out_of_order_event_fail(self):
        wrong=Offer(**{**self.offer.__dict__,'sha256':'f'*64})
        obj,_,_=self.connect(offer=MarkerBoundOffer(wrong,self.marker));obj.request_offer()
        with self.assertRaises(FetchError): obj.download(self.root/'wrong')
        obj2,_,_=self.connect()
        with self.assertRaises(RuntimeError): obj2.load_requested(self.offer.attempt_id)

    def test_unexpected_input_before_claim_is_rejected(self):
        obj,claims,_=self.connect(after_offer=b'premature\n')
        self.staged(obj); self.observations(obj)
        with self.assertRaises(ConnectionError): obj.claim(self.offer.attempt_id)
        self.assertEqual(claims,[])

    def test_deadline_expiring_during_download_faults_after_return(self):
        obj,_,_=self.connect(); obj.request_offer()
        obj._deadline=time.monotonic()+0.02
        def slow_receive(*args,**kwargs):
            self.assertEqual(kwargs['deadline'], obj._deadline)
            time.sleep(.04)
            return self.root/'synthetic-result'
        with patch.object(subject,'receive',side_effect=slow_receive):
            with self.assertRaises(TimeoutError): obj.download(self.root/'unused')
        with self.assertRaises(RuntimeError): obj.verify_staged(self.root/'synthetic-result')


if __name__=='__main__': unittest.main()
