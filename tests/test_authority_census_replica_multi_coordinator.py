"""Three fake X4 owners, real loopback UDP/TCP and owned helpers; no game."""
from pathlib import Path
import socket
import sys
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/dev'))
import authority_census_replica_multi_coordinator as multi


class MultiCoordinatorTests(unittest.TestCase):
    def exercise(self,mode):
        coord=multi.MultiCensusCoordinator({'sector_a':(24,)})
        config={r:coord.add_role(r) for r in ('server','client1','client2')}
        stop=threading.Event();commands=[];errors=[];threads=[]
        tcp_ok=set()
        for name,transport in coord.transports.items():
            original=transport.exchange
            def exchange(*args,_role=name,_original=original,**kw):
                result=_original(*args,**kw)
                if mode=='second_tcp_fail' and _role=='client2':raise RuntimeError('uncertain second TCP ACK')
                tcp_ok.add(_role);return result
            transport.exchange=exchange
        for role in ('server','client1','client2'):
            def fake(role=role):
                p=config[role];wire_role=p['role'];sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
                sock.bind(('127.0.0.1',0));sock.settimeout(.1);addr=('127.0.0.1',p['port'])
                prefix='|'.join(('CENSUS',p['lease'],wire_role,p['attempt'],p['epoch']))
                expected='|'.join(('CMD',p['lease'],wire_role,p['attempt'],p['epoch']))+'|'
                def send(v):sock.sendto((prefix+'|'+v).encode(),addr)
                try:
                    send('READY')
                    if role=='server' and mode=='premature':send('SOURCE_ACKED|19|10055')
                    while not stop.is_set():
                        try:raw,_=sock.recvfrom(769)
                        except socket.timeout:continue
                        text=raw.decode();assert text.startswith(expected)
                        cmd=text[len(expected):];op=cmd.split('|')[0];commands.append((role,cmd))
                        if op=='CHECK':send('CHECKED|'+cmd.split('|')[1])
                        elif role=='server' and op=='START':send('DESCRIPTOR|19|10055|ship_macro|pioneers|sector_a|-100|200|300')
                        elif op=='WITNESS':send(('WITNESS_OK|' if role=='server' else 'WITNESS_READY|')+cmd[len('WITNESS|'):])
                        elif role!='server' and op=='REPLICA':send('WITNESS_OK|19|24|sector_a')
                        elif role=='server' and op=='DELIVERY_ACK':
                            parts=cmd.split('|');r=parts[3];assert r in tcp_ok
                            assert parts[1:3]==['19','10055'] and parts[4]==coord.incarnations[r]
                            if r=='client1':
                                if mode=='wrong_partial':send('PARTIAL_ACKED|19|10055|client2')
                                elif mode=='premature_final':send('SOURCE_ACKED|19|10055')
                                else:send('PARTIAL_ACKED|19|10055|client1')
                            elif mode!='missing_final':send('SOURCE_ACKED|19|10055')
                        else:raise AssertionError(cmd)
                except BaseException as e:
                    if not stop.is_set():errors.append(e)
                finally:sock.close()
            thread=threading.Thread(target=fake,daemon=True);thread.start();threads.append(thread)
        try:
            context={'deadline':time.monotonic()+(1 if mode=='missing_final' else 8),'check':lambda:True}
            if mode=='ok':
                result=coord.run(context);self.assertEqual(result['clients_confirmed'],['client1','client2'])
                self.assertTrue(result['source_queue_acked']);self.assertEqual(tcp_ok,{'client1','client2'})
                ack=[cmd for role,cmd in commands if role=='server' and cmd.startswith('DELIVERY_ACK|')]
                self.assertEqual([x.split('|')[3] for x in ack],['client1','client2'])
                def logs(labels):return ''.join('[X4LAN] AUTH_CENSUS_JOB '+s+'\n' for s in labels).encode()
                final={'server':logs(['READY','DESCRIPTOR','WITNESS_OK','PARTIAL_ACKED','SOURCE_ACKED'])}
                for role in coord.CLIENTS:final[role]=logs(['READY','WITNESS_READY','WITNESS_OK'])+b'[X4LAN] AUTH_CENSUS_REPLICA DONE\n'
                self.assertTrue(coord.cleanup_before_owned_processes());self.assertTrue(coord.verify_final(final))
            else:
                with self.assertRaises((ValueError,RuntimeError,TimeoutError)):coord.run(context)
                self.assertFalse(coord.complete)
                if mode=='second_tcp_fail':
                    ack=[cmd for role,cmd in commands if role=='server' and cmd.startswith('DELIVERY_ACK|')]
                    self.assertEqual([x.split('|')[3] for x in ack],['client1'])
                if mode=='premature':self.assertFalse(any(cmd.startswith('DELIVERY_ACK|') for _,cmd in commands))
        finally:
            stop.set();coord.cleanup_before_owned_processes();coord.cleanup_after_owned_processes()
            for thread in threads:thread.join(2)
        self.assertEqual(errors,[])

    def test_two_distinct_receipts(self):self.exercise('ok')
    def test_lost_second_tcp_ack_does_not_release(self):self.exercise('second_tcp_fail')
    def test_wrong_partial_ack_fails(self):self.exercise('wrong_partial')
    def test_premature_final_ack_fails(self):self.exercise('premature_final')
    def test_early_source_ack_fails(self):self.exercise('premature')
    def test_missing_source_receipt_fails(self):self.exercise('missing_final')
    def test_same_udp_peer_cannot_impersonate_two_owners(self):
        c=multi.MultiCensusCoordinator({'sector_a':(24,)})
        cfg={r:c.add_role(r) for r in ('server','client1','client2')}
        c.context={'deadline':time.monotonic()+2,'check':lambda:True};c.deadline=c.context['deadline']
        peer=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);peer.bind(('127.0.0.1',0))
        try:
            for role in ('server','client1'):
                p=cfg[role];raw='|'.join(('CENSUS',p['lease'],p['role'],p['attempt'],p['epoch'],'READY'))
                peer.sendto(raw.encode(),('127.0.0.1',p['port']))
            with self.assertRaisesRegex(ValueError,'shared across owners'):
                while True:c._pump(.2)
        finally:
            peer.close();c.cleanup_before_owned_processes();c.cleanup_after_owned_processes()


if __name__=='__main__':unittest.main()
