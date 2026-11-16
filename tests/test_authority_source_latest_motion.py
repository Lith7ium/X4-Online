"""Real loopback TCP/UDP; synthetic source, not X4 or Internet evidence."""
import socket
import threading
import time
import unittest

from tests import test_authority_experimental_tcp_motion as fixture
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import ExperimentalTCPMotion
from authority.experimental_source_motion_ipc import ExperimentalSourceMotionIPC
from authority.experimental_source_job_bridge import ExperimentalSourceJobBridge
from authority.experimental_job_motion_scheduler import ExperimentalJobMotionScheduler


class SourceLatest(unittest.TestCase):
    def setUp(self):
        self.case=fixture.MotionTCP('test_invalid_values_and_no_fake_velocity')
        self.case.setUp();self.addCleanup(self.case.doCleanups)
        a=self.case.case.connect();b=self.case.case.connect()
        self.case.case.offer_and_claim(a);self.case.case.offer_and_claim(b)
        self.case.client(a,1);self.case.client(b,2,delay=.3);self.case.case.host.tick(.1)
        self.host=self.case.case.host;self.control=self.case.case.control
        self.control.enable_latest_motion(enabled=True,timeout=1)
        self.delivery=ExperimentalTCPJobDelivery(self.host,enabled=True,timeout=1)
        self.motion=ExperimentalTCPMotion(self.delivery,enabled=True,min_interval=1/240)
        self.local=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.local.bind(('127.0.0.1',0));self.addCleanup(self.local.close)
        self.remote=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.remote.bind(('127.0.0.1',0));self.addCleanup(self.remote.close)
        self.local.connect(self.remote.getsockname());self.remote.connect(self.local.getsockname())
        self.good=True
        self.bridge=ExperimentalSourceMotionIPC(self.local,self.motion,enabled=True,lease='1'*32,attempt='2'*32,
            epoch='b'*32,generation='c'*32,guard=lambda:self.good,validate_peer=lambda p:p==self.remote.getsockname(),
            timeout=2,select_recipients=lambda _,members:members,latest=True,
            saved_baseline=20000,saved_guard=lambda epoch,baseline:epoch=='b'*32 and baseline==20000,
            saved_lifetime_guard=lambda epoch,baseline:epoch=='b'*32 and baseline==20000)
        self.bridge.bind_confirmed(10055)

    def respond(self,seq,index=10055):
        packet=self.remote.recv(769).decode().split('|')
        response=['S','1'*32,'2'*32,'SAMPLE','b'*32,'c'*32,packet[-1],
                  str(index),str(seq),'sector_a',str(seq),'1','2','3','10','0','0']
        self.remote.send('|'.join(response).encode())

    def wait(self,condition,timeout=1):
        end=time.monotonic()+timeout
        while not condition() and time.monotonic()<end:self.host.tick(.005)
        self.assertTrue(condition())

    def test_udp_wait_and_slow_peer_do_not_block_fast_peer(self):
        self.assertTrue(self.bridge.begin_latest());self.respond(1)
        self.assertEqual(self.bridge.poll_latest()[1]['sequence'],1)
        self.wait(lambda:len(self.case.received)==2)
        time.sleep(.005)
        self.assertTrue(self.bridge.begin_latest())
        # No source reply yet. The same owner still completes the fast receipt.
        self.assertEqual(self.bridge.poll_latest(),(False,None))
        self.wait(lambda:bool(self.motion._tracks[('b'*32,'c'*32,10055)]['peer_samples']))
        self.respond(2);self.assertEqual(self.bridge.poll_latest()[1]['sequence'],2)
        time.sleep(.005);self.assertTrue(self.bridge.begin_latest());self.respond(3)
        self.assertEqual(self.bridge.poll_latest()[1]['sequence'],3)
        self.wait(lambda:any(h==1 and v['sequence']==3 for h,v,_ in self.case.received),timeout=.2)
        self.wait(lambda:any(h==2 and v['sequence']==3 for h,v,_ in self.case.received))
        self.assertEqual([v['sequence'] for h,v,_ in self.case.received if h==2],[1,3])
        self.wait(self.control._motion_idle);self.bridge.close()

    def test_full_distinct_track_queue_disconnects_only_slow_peer(self):
        self.control._latest_motion.limit=1
        self.bridge.bind_confirmed(10056);self.bridge.bind_confirmed(10057)
        self.assertTrue(self.bridge.begin_latest());self.respond(1)
        self.bridge.poll_latest();self.wait(lambda:len(self.case.received)==2)
        time.sleep(.005);self.assertTrue(self.bridge.begin_latest());self.respond(1,10056)
        self.bridge.poll_latest()
        self.wait(lambda:any(h==1 and v['index']==10056 for h,v,_ in self.case.received),timeout=.2)
        time.sleep(.005);self.assertTrue(self.bridge.begin_latest());self.respond(1,10057)
        self.bridge.poll_latest()
        self.assertEqual(len(self.control._peers),1);self.assertFalse(self.host._failed)
        self.wait(lambda:any(h==1 and v['index']==10057 for h,v,_ in self.case.received),timeout=.2)
        self.wait(self.control._motion_idle,timeout=.2)
        self.case.stop.set();self.bridge.close()

    def test_all_full_peers_disconnect_reports_no_queued_sample(self):
        self.control._latest_motion.limit=1
        self.bridge.bind_confirmed(10056);self.bridge.bind_confirmed(10057)
        self.assertTrue(self.bridge.begin_latest());self.respond(1)
        self.bridge.poll_latest();self.wait(lambda:len(self.case.received)==2)
        time.sleep(.005);self.assertTrue(self.bridge.begin_latest());self.respond(1,10056)
        self.assertEqual(self.bridge.poll_latest()[1]['index'],10056)
        time.sleep(.005);self.assertTrue(self.bridge.begin_latest());self.respond(1,10057)
        self.assertEqual(self.bridge.poll_latest(),(True,None))
        self.assertEqual(len(self.control._peers),0);self.assertFalse(self.host._failed)
        self.assertIsNotNone(self.case.case.world.session.pending)
        self.case.stop.set();self.bridge.close()

    def test_scheduler_pumps_while_waiting_and_fences_job_before_read(self):
        ji=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);ji.bind(('127.0.0.1',0));self.addCleanup(ji.close)
        jo=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);jo.bind(('127.0.0.1',0));self.addCleanup(jo.close)
        ji.connect(jo.getsockname());jo.connect(ji.getsockname())
        job=ExperimentalSourceJobBridge(self.delivery,ji,enabled=True,lease='4'*32,attempt='5'*32,
            epoch='b'*32,generation='c'*32,guard=lambda:True,timeout=2)
        import select
        self.bridge._saved_guard=lambda epoch,baseline:not select.select([ji],[],[],0)[0]
        scheduler=ExperimentalJobMotionScheduler(job,self.bridge,enabled=True)
        self.assertEqual(scheduler.step(),('motion_pending',None));self.respond(1)
        self.assertEqual(scheduler.step()[0],'motion')
        end=time.monotonic()+1
        while len(self.case.received)<2 and time.monotonic()<end:scheduler.step();time.sleep(.002)
        self.assertEqual(len(self.case.received),2)
        # Wait for the next UDP request while the first slow TCP receipt is
        # in flight; the scheduler keeps polling TCP without a source reply.
        while self.bridge.state!='pulling' and time.monotonic()<end:scheduler.step();time.sleep(.002)
        self.assertEqual(self.bridge.state,'pulling')
        jo.send(('|'.join(['S','4'*32,'5'*32,'FINISHED','b'*32,'c'*32,'0'])).encode())
        self.assertEqual(scheduler.step(),('motion_pending',None))
        self.respond(2);self.assertEqual(scheduler.step()[0],'motion')
        seen=[];end=time.monotonic()+1
        while time.monotonic()<end:
            kind,_=scheduler.step();seen.append(kind)
            if kind=='job_snapshot_finished':break
            time.sleep(.002)
        self.assertIn('motion_drain',seen)
        self.assertEqual(seen[-1],'job_snapshot_finished')
        self.assertFalse(self.control._latest_motion.blocked)
        scheduler.close()

    def test_paused_world_does_not_start_source_request(self):
        session=self.case.case.world.session
        old=session._state
        try:
            session._state='paused'
            self.assertFalse(self.bridge.begin_latest())
            self.assertEqual(self.bridge.state,'ready')
            self.assertFalse(self.host._failed)
        finally:session._state=old
        self.bridge.close()

    def test_guard_cannot_reenter_world_tick(self):
        caught=[]
        def reenter():
            try:self.host.tick(0)
            except RuntimeError:caught.append(True)
            return True
        self.bridge._guard=reenter
        self.assertTrue(self.bridge.begin_latest());self.respond(1)
        self.assertEqual(self.bridge.poll_latest()[1]['sequence'],1)
        self.wait(self.control._motion_idle)
        self.assertTrue(caught);self.bridge.close()

    def test_host_defers_world_action_until_outstanding_source_is_drained(self):
        self.assertTrue(self.bridge.begin_latest())
        third=self.case.case.connect()
        prior=list(self.case.case.engine.calls)
        for _ in range(3):self.host.tick(0)
        self.assertEqual(self.case.case.engine.calls,prior)
        self.assertIsNotNone(self.case.case.world.session.pending)
        self.respond(1);self.assertEqual(self.bridge.poll_latest(),(True,None))
        self.host.tick(0)
        self.assertEqual(self.case.case.engine.calls[len(prior)],'pause')
        third.close();self.bridge.close()

    def test_revoked_source_fences_before_tcp_dispatch(self):
        self.assertTrue(self.bridge.begin_latest());self.respond(1)
        self.assertEqual(self.bridge.poll_latest()[1]['sequence'],1)
        self.good=False
        with self.assertRaises(RuntimeError):self.host.tick(.01)
        self.assertTrue(self.host._failed);self.assertEqual(self.case.received,[])

    def test_lifecycle_barrier_discards_outstanding_udp_result(self):
        self.assertTrue(self.bridge.begin_latest())
        self.assertTrue(self.control.motion_barrier())
        self.control.release_motion_barrier()
        # A completed barrier still invalidates a reply from before it.
        self.respond(1);self.assertEqual(self.bridge.poll_latest(),(True,None))
        self.assertEqual(self.case.received,[])
        self.bridge.close()

if __name__=='__main__':unittest.main()
