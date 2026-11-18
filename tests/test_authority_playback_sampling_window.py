"""Tiny real-checkpoint/helper and private save-window tests; never starts X4."""
import gzip
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev'),str(ROOT/'tests')]
from authority.checkpoints import CheckpointStore
from authority_witness_guard_client import WitnessGuardClient
from authority_witness_source_guard import WitnessSourceGuard
from test_authority_witness_source_guard import source_xml, MARKER
import authority_playback_sampling_window as subject


@unittest.skipUnless(sys.platform=='linux' and hasattr(os,'pidfd_open'),'Linux helper required')
class WindowTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);(self.root/'store').mkdir();store=CheckpointStore(self.root/'store')
        source=self.root/'source.gz';source.write_bytes(gzip.compress(source_xml().encode()))
        self.cp=store.publish(source,marker=MARKER);store.confirm(self.cp)
        self.source=WitnessSourceGuard(store,self.cp)
        self.helper=WitnessGuardClient(store,self.cp,deadline=time.monotonic()+20,
                                       registry=[],pump=lambda:None,timeout=3)
        self.addCleanup(self.helper._cleanup)
        self.hash_calls=[]
        def full_sha(path):
            self.hash_calls.append(path)
            return hashlib.sha256(path.read_bytes()).hexdigest()
        self.window=subject.PlaybackSamplingWindow(full_sha,self.source)
        self.addCleanup(self.window.cleanup)
        self.entries=[]
        for name in ('server-input.gz','fresh-client-target.gz'):
            path=self.root/name;path.write_bytes(self.cp.path.read_bytes());path.chmod(0o400)
            self.entries.append((path,self.cp.sha256))
        self.process_checks=0
        def process_guard():self.process_checks+=1;return True
        self.process_guard=process_guard

    def enter(self):
        return self.window.open(self.entries,self.helper,process_guard=self.process_guard,
                                deadline=time.monotonic()+10)

    def install_production_pump(self, active_check):
        from authority_recovered_server_client import WitnessGuardPump, ServerClient
        participant=object.__new__(ServerClient)
        participant._active_check=active_check
        control=SimpleNamespace(_reader_lease=None, _reader_free=lambda:None)
        host=SimpleNamespace(_busy=False,_control=control)
        pump=WitnessGuardPump(participant,self.helper.deadline)
        pump.activate(host=host,guard=lambda:participant.check_active(server_checked=True))
        self.helper.pump=pump
        return host

    def test_real_helper_pump_checks_pinned_saves_on_open_metadata_and_stop(self):
        states=[]
        def active_check(*, server_checked=False):
            self.assertTrue(server_checked)
            states.append(self.helper.state)
            return self.window.check_save(*self.entries[1])
        host=self.install_production_pump(active_check)
        self.assertTrue(self.enter())
        opening=len(states)
        self.assertGreater(opening,0)
        self.assertEqual(self.hash_calls,[])  # Opening helper pump already uses pins.
        self.assertTrue(self.window.check_checkpoint(self.helper))
        self.assertGreater(len(states),opening)
        self.assertTrue(self.window.stop_checkpoint(self.helper))
        self.assertIn('checking',states);self.assertIn('stopping',states)
        self.assertTrue(self.window.close(process_guard=self.process_guard))
        self.assertFalse(self.window.failed);self.assertFalse(host._busy)
        self.assertIsNone(host._control._reader_lease)
        self.assertEqual(self.hash_calls,[])

    def test_real_helper_pump_cannot_reenter_checkpoint_even_if_error_is_caught(self):
        attempts=[]
        def active_check(*, server_checked=False):
            if not attempts:
                attempts.append(True)
                try:self.window.check_checkpoint(self.helper)
                except RuntimeError:pass
            return True
        self.install_production_pump(active_check)
        with self.assertRaises(RuntimeError):self.enter()
        self.assertEqual(attempts,[True]);self.assertTrue(self.window.failed)
        self.window.cleanup()
        with self.assertRaises(RuntimeError):self.window.check_save(*self.entries[0])

    def test_process_callback_has_no_general_save_reentry_exception(self):
        def recursive_process_guard():return self.window.check_save(*self.entries[0])
        with self.assertRaises(RuntimeError):
            self.window.open(self.entries,self.helper,process_guard=recursive_process_guard,
                             deadline=time.monotonic()+10)
        self.assertTrue(self.window.failed)

    def test_full_outside_metadata_inside_full_boundaries_and_clean_stop(self):
        self.assertTrue(self.window.check_save(*self.entries[0]))
        self.assertTrue(self.window.check_source())
        self.assertTrue(self.window.check_checkpoint(self.helper))
        self.assertEqual(self.hash_calls,[self.entries[0][0]])
        self.assertTrue(self.enter())
        with patch.object(self.source,'check',side_effect=AssertionError('unexpected full check')):
            self.assertTrue(self.window.check_source())
            self.assertTrue(self.window.check_checkpoint(self.helper))
            for entry in self.entries:self.assertTrue(self.window.check_save(*entry))
        self.assertEqual(self.hash_calls,[self.entries[0][0]])
        self.assertEqual(self.window.metrics['source_metadata_checks'],1)
        self.assertEqual(self.window.metrics['checkpoint_metadata_checks'],1)
        self.assertTrue(self.helper.stop())
        # Client STOP process guards can still check the pins after helper STOP.
        self.assertTrue(self.window.check_save(*self.entries[0]))
        self.assertTrue(self.window.check_source())
        self.assertTrue(self.window.close(process_guard=self.process_guard))
        self.assertEqual(self.window.state,'closed');self.assertFalse(self.window.failed)
        self.assertEqual(self.window.metrics['saves']['digest_checks'],4)
        self.assertGreater(self.process_checks,0)
        self.assertTrue(self.window.check_save(*self.entries[1]))
        self.assertTrue(self.window.check_source())
        self.assertEqual(self.hash_calls,[self.entries[0][0],self.entries[1][0]])

    def test_window_is_single_use_and_close_requires_real_full_stop(self):
        self.enter()
        with self.assertRaisesRegex(RuntimeError,'STOP not confirmed'):
            self.window.close(process_guard=self.process_guard)
        self.assertTrue(self.window.failed)
        self.helper.stop();self.window.cleanup()
        with self.assertRaises(RuntimeError):self.window.check_save(*self.entries[0])
        self.assertEqual(self.hash_calls,[])

    def test_closed_window_cannot_reopen(self):
        self.enter();self.helper.stop();self.window.close(process_guard=self.process_guard)
        with self.assertRaises(ValueError):self.enter()
        self.assertTrue(self.window.failed)

    def test_mutated_save_fails_and_cleanup_closes_pins_without_fallback(self):
        self.enter()
        pins=[entry[0]._fd for entry in self.window._saves._guards.values()]
        path=self.entries[0][0];path.chmod(0o600);path.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.window.check_save(*self.entries[0])
        self.assertTrue(self.window.failed);self.assertTrue(self.window.cleanup())
        for fd in pins:
            with self.assertRaises(OSError):os.fstat(fd)
        with self.assertRaises(RuntimeError):self.window.check_save(*self.entries[0])
        self.assertEqual(self.hash_calls,[])

    def test_source_pointer_and_save_replacement_are_rejected(self):
        self.enter()
        path=self.entries[1][0];replacement=self.root/'replacement'
        replacement.write_bytes(path.read_bytes());replacement.chmod(0o400);os.replace(replacement,path)
        with self.assertRaises(ValueError):self.window.check_save(*self.entries[1])
        self.window.cleanup()
        # Independently prove source metadata fences pointer replacement.
        other=subject.PlaybackSamplingWindow(lambda p:hashlib.sha256(p.read_bytes()).hexdigest(),self.source)
        self.addCleanup(other.cleanup)
        other.open(self.entries,self.helper,process_guard=self.process_guard,deadline=time.monotonic()+10)
        pointer=self.source.store.directory/'CURRENT';pointer.write_bytes(pointer.read_bytes()+b' ')
        with self.assertRaises(ValueError):other.check_source()
        self.assertTrue(other.failed)

    def test_expiry_helper_identity_and_bad_process_guard_fence(self):
        self.enter()
        with patch.object(subject,'time',SimpleNamespace(monotonic=lambda:self.window._deadline+1)):
            with self.assertRaises(TimeoutError):self.window.check_save(*self.entries[0])
        self.assertTrue(self.window.failed);self.window.cleanup()
        for kind in ('helper','process'):
            window=subject.PlaybackSamplingWindow(lambda p:hashlib.sha256(p.read_bytes()).hexdigest(),self.source)
            self.addCleanup(window.cleanup)
            window.open(self.entries,self.helper,process_guard=self.process_guard,deadline=time.monotonic()+10)
            if kind=='helper':
                with self.assertRaisesRegex(RuntimeError,'guard changed'):window.check_checkpoint(object())
            else:
                with patch.object(window,'_process_guard',return_value=False):
                    with self.assertRaisesRegex(RuntimeError,'process guard'):window.check_source()
            self.assertTrue(window.failed);window.cleanup()

    def test_full_boundaries_are_mandatory_and_failure_cleanup_is_sticky(self):
        with patch.object(self.source,'check',return_value=False):
            with self.assertRaisesRegex(RuntimeError,'full boundary failed'):self.enter()
        self.assertTrue(self.window.failed);self.assertTrue(self.window.cleanup())
        with self.assertRaises(RuntimeError):self.window.check_source()
        for bad in (time.monotonic()-1,time.monotonic()+61,float('inf')):
            window=subject.PlaybackSamplingWindow(lambda p:hashlib.sha256(p.read_bytes()).hexdigest(),self.source)
            self.addCleanup(window.cleanup)
            with self.assertRaises(ValueError):
                window.open(self.entries,self.helper,process_guard=self.process_guard,deadline=bad)
            self.assertTrue(window.failed)

    def test_close_full_source_failure_keeps_failure_after_fd_cleanup(self):
        self.enter();self.helper.stop()
        with patch.object(self.source,'check',side_effect=ValueError('full boundary mutation')):
            with self.assertRaisesRegex(ValueError,'full boundary mutation'):
                self.window.close(process_guard=self.process_guard)
        self.window.cleanup();self.assertTrue(self.window.failed)
        with self.assertRaises(RuntimeError):self.window.check_save(*self.entries[0])

if __name__=='__main__':unittest.main()
