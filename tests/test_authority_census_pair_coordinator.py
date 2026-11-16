"""Two fake local X4 owners, real UDP/TCP and gated helper; no X4."""
from pathlib import Path
import socket
import sys
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/dev'))
import authority_census_pair_coordinator as m


class CensusCoordinator(unittest.TestCase):
    def exercise(self,mode):
        c=m.CensusCoordinator({'sector_a':(24,25)});cfg={r:c.add_role(r) for r in ('server','client')}
        peers=[];threads=[];stop=threading.Event();alive=threading.Event();alive.set();commands=[];errors=[]
        for role in ('server','client'):
            peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);peer.bind(('127.0.0.1',0));peer.settimeout(.1);peers.append(peer)
            def fake(role=role,peer=peer):
                p=cfg[role];prefix='|'.join(('CENSUS',p['lease'],role,p['attempt'],p['epoch']))
                expected='|'.join(('CMD',p['lease'],role,p['attempt'],p['epoch']))+'|'
                addr=('127.0.0.1',p['port'])
                def send(value):peer.sendto((prefix+'|'+value).encode(),addr)
                try:
                    send('READY')
                    if role=='client' and mode=='duplicate_ready':send('READY')
                    if role=='server' and mode=='premature_no_event':send('NO_EVENT')
                    if role=='server' and mode=='premature_descriptor':send('DESCRIPTOR|19|10055|ship_macro|pioneers|sector_a|-100|200|300')
                    while not stop.is_set():
                        try:raw,_=peer.recvfrom(769)
                        except socket.timeout:continue
                        text=raw.decode();assert text.startswith(expected)
                        command=text[len(expected):];name=command.split('|')[0];commands.append((role,name))
                        if name=='CHECK':
                            if not (mode=='no_check' and role=='client'):send('CHECKED|'+command.split('|')[1])
                        elif role=='server' and command=='START':
                            if mode=='no_event':send('NO_EVENT')
                            else:
                                sector='unknown' if mode=='missing_sector' else 'sector_a'
                                send('DESCRIPTOR|19|10055|ship_macro|pioneers|'+sector+'|-100|200|300')
                        elif name=='WITNESS':
                            if role=='client' and mode=='client_guard_loss':alive.clear()
                            body=command[len('WITNESS|'):]
                            if role=='client' and mode=='bad_witness':body='19|25|sector_a'
                            send('WITNESS_OK|'+body)
                        else:raise AssertionError(command)
                except BaseException as error:
                    if not stop.is_set():errors.append(error)
                finally:peer.close()
            thread=threading.Thread(target=fake,daemon=True);threads.append(thread);thread.start()
        try:
            context={'deadline':time.monotonic()+(1 if mode=='no_check' else 8),'check':alive.is_set}
            if mode=='ok':
                result=c.run(context)
                self.assertEqual(result['job_sequence'],19);self.assertEqual(result['transport_sequence'],1)
                self.assertEqual(result['saved_witness_index'],24);self.assertTrue(result['tcp_ack_after_client_witness'])
                self.assertFalse(result['ship_creation_requested']);self.assertFalse(result['runtime_frame_identity_proven'])
                self.assertLess(commands.index(('server','WITNESS')),commands.index(('client','WITNESS')))
                self.assertTrue(c.cleanup_before_owned_processes())
                self.assertIsNone(c.tcp.helpers[0].pidfd)
                def logs(labels):return ''.join('[X4LAN] AUTH_CENSUS_JOB '+s+'\n' for s in labels).encode()
                self.assertTrue(c.verify_final({'server':logs(['READY','CHECKED','DESCRIPTOR','WITNESS_OK']),
                                                'client':logs(['READY','CHECKED','WITNESS_OK'])}))
            elif mode=='no_event':
                with self.assertRaises(m.NoNewRegistryEntry):c.run(context)
                self.assertFalse(c.complete);self.assertEqual(c.tcp.helpers,[])
                self.assertNotIn(('server','WITNESS'),commands)
                def logs(labels):return ''.join('[X4LAN] AUTH_CENSUS_JOB '+s+'\n' for s in labels).encode()
                self.assertTrue(c.verify_no_event_final({'server':logs(['READY','CHECKED','NO_EVENT']),
                                                         'client':logs(['READY','CHECKED'])}))
                self.assertFalse(c.verify_no_event_final({'server':logs(['READY','NO_EVENT','ERROR FAULT']),
                                                          'client':logs(['READY'])}))
            else:
                with self.assertRaises((ValueError,RuntimeError,TimeoutError)):c.run(context)
                if mode in ('no_check','duplicate_ready','premature_no_event','premature_descriptor'):
                    self.assertNotIn(('server','START'),commands)
                if mode=='missing_sector':self.assertNotIn(('client','WITNESS'),commands)
        finally:
            stop.set();c.cleanup_before_owned_processes();c.cleanup_after_owned_processes()
            for thread in threads:thread.join(2)
        self.assertEqual(errors,[])

    def test_real_tcp_with_two_fake_owners(self):self.exercise('ok')
    def test_absent_guard_prevents_start(self):self.exercise('no_check')
    def test_duplicate_ready_prevents_start(self):self.exercise('duplicate_ready')
    def test_unknown_sector_does_not_issue_client_witness(self):self.exercise('missing_sector')
    def test_wrong_client_witness_fails(self):self.exercise('bad_witness')
    def test_guard_lost_during_client_witness_fails(self):self.exercise('client_guard_loss')
    def test_no_new_entry_is_inconclusive_with_final_logs(self):self.exercise('no_event')
    def test_result_before_start_is_rejected(self):
        for mode in ('premature_no_event','premature_descriptor'):
            with self.subTest(mode=mode):self.exercise(mode)

if __name__=='__main__':unittest.main()
