"""One actual gated/pidfd helper and loopback TCP, with fake witness guard."""
import sys
import time
from pathlib import Path
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/dev'))
import authority_census_pair_transport as m


def descriptor():
    return dict(version=1,type='job_descriptor',attempt='a'*32,epoch='b'*32,
                transport_sequence=1,job_sequence=19,index=10055,macro='ship_gen_m_tugboat_01_a_macro',
                faction='pioneers',sector_macro='cluster_115_sector001_macro',x=-100,y=200,z=300)


class OwnedTransport(unittest.TestCase):
    def test_real_gated_helper_receives_witness_ack(self):
        transport=m.OwnedJobTransport();events=[]
        try:
            result=transport.exchange(descriptor(),'a'*32,'b'*32,19,
                lambda value:events.append(value) or True,time.monotonic()+5,lambda:True)
            self.assertEqual(result,descriptor());self.assertEqual(events,[descriptor()])
            self.assertEqual(len(transport.helpers),1);self.assertEqual(transport.helpers[0].proc.returncode,0)
            with self.assertRaises(RuntimeError):transport.exchange(descriptor(),'a'*32,'b'*32,19,
                lambda _:True,time.monotonic()+2,lambda:True)
        finally:self.assertTrue(transport.cleanup_before_owned_processes())
        self.assertIsNone(transport.helpers[0].pidfd)

    def test_witness_guard_loss_and_helper_still_reaped(self):
        transport=m.OwnedJobTransport();state={'good':True}
        def witness(_):state['good']=False;return True
        try:
            with self.assertRaisesRegex(RuntimeError,'guard failed'):
                transport.exchange(descriptor(),'a'*32,'b'*32,19,witness,time.monotonic()+5,lambda:state['good'])
        finally:self.assertTrue(transport.cleanup_before_owned_processes())
        self.assertIsNone(transport.helpers[0].pidfd)
        self.assertIsNotNone(transport.helpers[0].proc.returncode)

    def test_wrong_job_sequence_fails_before_helper(self):
        transport=m.OwnedJobTransport()
        with self.assertRaisesRegex(ValueError,'context differs'):
            transport.exchange(descriptor(),'a'*32,'b'*32,1,lambda _:True,time.monotonic()+2,lambda:True)
        self.assertEqual(transport.helpers,[]);self.assertTrue(transport.cleanup_before_owned_processes())

    def test_cleanup_attempts_helper_after_socket_close_exception(self):
        transport=m.OwnedJobTransport();bad=Mock();bad.close.side_effect=OSError('failed');good=Mock();helper=Mock()
        transport.sockets=[bad,good];transport.helpers=[helper]
        with self.assertRaisesRegex(RuntimeError,'cleanup unconfirmed'):transport.cleanup_before_owned_processes()
        good.close.assert_called_once();helper.stop.assert_called_once();self.assertFalse(transport.closed)

    def test_helper_status_does_not_mask_external_reap(self):
        transport=m.OwnedJobTransport();helper=Mock(pidfd=1);helper.proc.returncode=None
        with patch.object(m.signal,'getsignal',return_value=m.signal.SIG_DFL), \
             patch.object(m.os,'waitid',side_effect=ChildProcessError):
            with self.assertRaisesRegex(RuntimeError,'reaped externally'):transport._status(helper)
        helper.proc.poll.assert_not_called()

if __name__=='__main__':unittest.main()
