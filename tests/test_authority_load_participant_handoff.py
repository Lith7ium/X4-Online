"""Experimental load-to-participant handoff, real local TCP and fake X4."""
import hashlib
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from authority.experimental_remote_load_client import ExperimentalRemoteLoadClient
from authority.experimental_tcp_control import offer_request
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient
from authority.load_messages import Offer
from authority.trusted_load_messages import decode_load_claim, encode_bound_offer
from authority.trusted_marker_load_session import MarkerBoundOffer
from lockstep.launcher.joinfiles import FileService


class FakeController:
    def __init__(self): self.calls=[]
    def pause(self,handles): self.calls.append(('pause',handles)); return True
    def resume(self,handles): self.calls.append(('resume',handles)); return True


class HandoffTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        data=b'experimental-save';path=self.root/'source';path.write_bytes(data)
        self.token='a'*32;self.marker='b'*32
        self.service=FileService(self.token,slots=(1,)).start();self.addCleanup(self.service.close)
        self.service.offer('j1.xml.gz',path)
        self.offer=Offer(world_epoch='epoch',connection_handle=1,baseline_id=1,load_generation=1,
            attempt_id='c'*32,checkpoint_id='checkpoint-'+'d'*32,sha256=hashlib.sha256(data).hexdigest(),
            size=len(data),name='j1.xml.gz')

    def start(self, *, first=None, second=None, eof=False, bad_accepted=None):
        listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM);listener.bind(('127.0.0.1',0));listener.listen(1)
        listener.settimeout(3);client=socket.create_connection(listener.getsockname(),timeout=3)
        results=[];errors=[]
        def server():
            try:
                conn,_=listener.accept();conn.settimeout(3)
                with conn, conn.makefile('rb') as reader:
                    if reader.readline()!=offer_request(): raise AssertionError('wrong offer request')
                    conn.sendall(encode_bound_offer(MarkerBoundOffer(self.offer,self.marker))+b'\n')
                    claim=decode_load_claim(reader.readline().rstrip(b'\n'))
                    if claim.receipt.attempt_id!=self.offer.attempt_id: raise AssertionError('wrong claim')
                    if bad_accepted=='missing': return
                    attempt='e'*32 if bad_accepted=='wrong_attempt' else self.offer.attempt_id
                    ack=json.dumps({'version':1,'kind':'accepted','attempt_id':attempt}).encode()+b'\n'
                    command=(json.dumps(first).encode()+b'\n') if first is not None else b''
                    conn.sendall(ack+command)  # queued together, so accepted reader must not overread
                    if eof or bad_accepted: return
                    results.append(reader.readline())
                    if second is not None and results[-1]:
                        conn.sendall(json.dumps(second).encode()+b'\n');results.append(reader.readline())
            except (OSError,ValueError,AssertionError) as error: errors.append(error)
            finally: listener.close()
        thread=threading.Thread(target=server,daemon=True);thread.start();self.addCleanup(lambda:thread.join(4))
        load=ExperimentalRemoteLoadClient(client,enabled=True,file_host='127.0.0.1',file_port=self.service.port,
            file_token=self.token,file_slot=1,deadline=time.monotonic()+5,io_timeout=2)
        self.addCleanup(load.close)
        bound=load.request_offer();save=load.download(self.root/'download');load.verify_staged(save)
        load.load_requested(bound.offer.attempt_id);load.loaded_marker(bound.offer.attempt_id,bound.marker)
        load.paused(bound.offer.attempt_id,True)
        if bad_accepted:
            with self.assertRaises((ValueError,ConnectionError)): load.claim(bound.offer.attempt_id)
        else: load.claim(bound.offer.attempt_id)
        return load,bound,results,errors,thread

    def command(self,operation,number,**changes):
        command={'version':1,'kind':'participant_command','epoch':self.offer.world_epoch,
                 'connection_handle':self.offer.connection_handle,'request_id':number,'operation':operation}
        command.update(changes);return command

    def test_queued_command_and_followup_use_same_accepted_connection(self):
        load,bound,results,errors,thread=self.start(first=self.command('pause',1),second=self.command('resume',2))
        controller=FakeController();sock=load.take_connection()
        participant=ExperimentalTCPParticipantClient(sock,controller,enabled=True,
            epoch=bound.offer.world_epoch,handle=bound.offer.connection_handle,timeout=2)
        try:
            sent=0;deadline=time.monotonic()+3
            while sent<2 and time.monotonic()<deadline:
                if participant.poll(.1): sent+=1
            self.assertEqual(sent,2)
            thread.join(2);self.assertFalse(thread.is_alive());self.assertFalse(errors)
            self.assertEqual(controller.calls,[('pause',(1,)),('resume',(1,))])
            replies=[json.loads(line) for line in results]
            self.assertEqual([(r['operation'],r['request_id'],r['status']) for r in replies],
                             [('pause',1,'confirmed'),('resume',2,'confirmed')])
        finally: participant.close()

    def test_wrong_epoch_or_handle_does_not_dispatch(self):
        for change in ({'epoch':'other'},{'connection_handle':2}):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                self.root=Path(directory)
                load,bound,results,errors,thread=self.start(first=self.command('pause',1,**change))
                controller=FakeController();sock=load.take_connection()
                participant=ExperimentalTCPParticipantClient(sock,controller,enabled=True,
                    epoch=bound.offer.world_epoch,handle=bound.offer.connection_handle,timeout=2)
                with self.assertRaises(ValueError):
                    for _ in range(20): participant.poll(.1)
                thread.join(2);self.assertFalse(errors);self.assertEqual(controller.calls,[])
                self.assertEqual(results,[b''])

    def test_eof_after_accepted_faults_participant(self):
        load,bound,_,errors,thread=self.start(eof=True);thread.join(2);self.assertFalse(errors)
        controller=FakeController();sock=load.take_connection()
        participant=ExperimentalTCPParticipantClient(sock,controller,enabled=True,
            epoch=bound.offer.world_epoch,handle=bound.offer.connection_handle,timeout=2)
        with self.assertRaises(RuntimeError):
            for _ in range(20): participant.poll(.1)
        self.assertEqual(controller.calls,[])

    def test_bad_or_missing_accepted_cannot_transfer_or_dispatch(self):
        for mode in ('wrong_attempt','missing'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                self.root=Path(directory)
                load,_,_,errors,thread=self.start(bad_accepted=mode)
                thread.join(2);self.assertFalse(errors)
                controller=FakeController()
                with self.assertRaises(RuntimeError): load.take_connection()
                self.assertEqual(controller.calls,[])


if __name__=='__main__': unittest.main()
