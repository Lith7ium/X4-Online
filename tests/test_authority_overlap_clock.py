"""Clock observer tests use only loopback sockets and fake X4 responses."""
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

import authority_overlap_clock as clock


class ClockTests(unittest.TestCase):
    def setUp(self):
        self.host=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.host.bind(('127.0.0.1',0)); self.addCleanup(self.host.close)
        self.peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.peer.bind(('127.0.0.1',0)); self.peer.settimeout(1); self.addCleanup(self.peer.close)
        self.lease='1'*32
        self.observer=clock.OverlapClock(self.host,self.lease)
        self.peer.sendto(('CLOCK_READY|'+self.lease).encode(),self.host.getsockname())

    def run_peer(self, results):
        errors=[]
        def respond():
            try:
                for status,value in results:
                    request,address=self.peer.recvfrom(768)
                    nonce=request.split(b'|')[1]
                    self.peer.sendto(b'CLOCK_RESULT|'+nonce+b'|'+status+b'|'+value,address)
            except BaseException as error: errors.append(error)
        thread=threading.Thread(target=respond);thread.start()
        self.addCleanup(thread.join,2)
        return errors

    def tick(self): time.sleep(.002)
    def test_two_guarded_samples_advance(self):
        errors=self.run_peer([(b'running',b'10.0'),(b'running',b'10.5')])
        seen=[]
        result=self.observer.observe(time.monotonic()+2,self.tick,lambda:seen.append(1),interval=.01)
        self.assertEqual(result,{'server_game_time_before':10.0,'server_game_time_after':10.5})
        self.assertGreater(len(seen),2);self.assertEqual(errors,[])

    def test_paused_or_invalid_response_fails(self):
        for status,value in [(b'paused',b'1'),(b'running',b'nan')]:
            with self.subTest(status=status,value=value):
                if self.observer.peer is None: self.observer._read(time.monotonic()+1,self.tick,lambda:None)
                errors=self.run_peer([(status,value)])
                with self.assertRaises(ValueError): self.observer.sample(time.monotonic()+1,self.tick,lambda:None)
                self.assertEqual(errors,[])

    def test_unchanged_clock_fails(self):
        self.run_peer([(b'running',b'5'),(b'running',b'5')])
        with self.assertRaisesRegex(ValueError,'did not advance'):
            self.observer.observe(time.monotonic()+1,self.tick,lambda:None,interval=.01)

    def test_foreign_or_stale_packet_is_rejected(self):
        self.observer._read(time.monotonic()+1,self.tick,lambda:None)
        self.peer.sendto(b'CLOCK_RESULT|'+b'2'*32+b'|running|1',self.host.getsockname())
        with self.assertRaisesRegex(ValueError,'unexpected'):
            self.observer.sample(time.monotonic()+1,self.tick,lambda:None)

    def test_guard_failure_stops_before_request(self):
        def fail(): raise RuntimeError('participant lost')
        with self.assertRaisesRegex(RuntimeError,'participant lost'):
            self.observer.sample(time.monotonic()+1,self.tick,fail)
        self.peer.settimeout(.02)
        with self.assertRaises(TimeoutError): self.peer.recvfrom(768)

    def test_install_changes_only_isolated_case(self):
        with tempfile.TemporaryDirectory() as temp:
            lab=Path(temp)/'extensions/x4_lan_lab';ui=lab/'ui';ui.mkdir(parents=True)
            (ui/'config.lua').write_text('X4LAN_CONFIG = {enabled=false}\n')
            (ui/'authority_world_bridge_probe.lua').write_text(' X4LAN_AUTHORITY_RECOVERY_UPDATE()\n')
            (lab/'ui.xml').write_text('<file name="ui/authority_world_bridge_probe.lua" />')
            observer=clock.install(temp,1234)
            self.assertTrue(observer.is_file())
            self.assertIn('authority_overlap_clock_port=1234',(ui/'config.lua').read_text())
            self.assertIn('X4LAN_AUTHORITY_OVERLAP_CLOCK_UPDATE()',(ui/'authority_world_bridge_probe.lua').read_text())
            self.assertIn('ui/authority_overlap_clock.lua',(lab/'ui.xml').read_text())


if __name__=='__main__': unittest.main()
