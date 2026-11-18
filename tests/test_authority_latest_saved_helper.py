"""Real checkpoint helper and latest UDP/TCP ownership integration; no X4."""
import os
from pathlib import Path
import socket
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev'), str(ROOT/'tests')]
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import ExperimentalTCPMotion, motion_digest
from authority.experimental_source_motion_ipc import ExperimentalSourceMotionIPC
from authority_recovered_server_client import WitnessGuardPump
import test_authority_experimental_tcp_motion as motion_fixture
import test_authority_playback_sampling_window as window_fixture


@unittest.skipUnless(sys.platform == 'linux' and hasattr(os, 'pidfd_open'), 'Linux helper required')
class LatestSavedHelperTests(unittest.TestCase):
    def test_real_helper_boundaries_and_lifetime_guards_preserve_tcp_owner(self):
        files = window_fixture.WindowTests()
        files.setUp()
        self.addCleanup(lambda: self.assertTrue(files.doCleanups()))
        tcp = motion_fixture.MotionTCP()
        tcp.setUp()
        self.addCleanup(lambda: self.assertTrue(tcp.doCleanups()))
        first, second = tcp.case.connect(), tcp.case.connect()
        tcp.case.offer_and_claim(first); tcp.case.offer_and_claim(second)
        tcp.client(first, 1); tcp.client(second, 2)
        host, control = tcp.case.host, tcp.case.control
        host.tick(.1)
        control.enable_latest_motion(enabled=True, timeout=1)
        delivery = ExperimentalTCPJobDelivery(host, enabled=True, timeout=1)
        motion = ExperimentalTCPMotion(delivery, enabled=True, min_interval=1/240)
        helper, window = files.helper, files.window
        pump_states = []

        def active_check():
            self.assertTrue(host._busy)
            self.assertIsNotNone(control._reader_lease)
            pump_states.append(helper.state)
            return window.check_save(*files.entries[1])

        # Use the production pump with this test's real TCP owner and reader lease.
        pump = WitnessGuardPump(SimpleNamespace(), helper.deadline)
        pump.activate(host=host, guard=active_check)
        helper.pump = pump
        self.assertTrue(files.enter())
        local, remote = socket.socket(socket.AF_INET, socket.SOCK_DGRAM), socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(local.close); self.addCleanup(remote.close)
        local.bind(('127.0.0.1', 0)); remote.bind(('127.0.0.1', 0))
        local.connect(remote.getsockname()); remote.connect(local.getsockname())
        remote.settimeout(2)
        epoch, baseline = helper.status[1:3]

        def saved_check(received_epoch, received_baseline):
            self.assertEqual((received_epoch, received_baseline), (epoch, baseline))
            return window.check_checkpoint(helper)

        def lifetime_check(received_epoch, received_baseline):
            self.assertEqual((received_epoch, received_baseline), (epoch, baseline))
            return window.check_checkpoint_lifetime(helper)

        source = ExperimentalSourceMotionIPC(local, motion, enabled=True, lease='1'*32,
            attempt='2'*32, epoch=epoch, generation='c'*32, guard=lambda: True,
            validate_peer=lambda peer: peer == remote.getsockname(), timeout=3,
            select_recipients=lambda _, members: members, saved_baseline=baseline,
            saved_guard=saved_check, saved_lifetime_guard=lifetime_check,
            latest=True, batch_latest_saved_checks=True)
        self.addCleanup(lambda: source._fail() if source.state != 'closed' else None)
        self.assertTrue(source.bind_confirmed(1))
        baseline_sequence = helper.seq
        baseline_lifetime = window.metrics['checkpoint_lifetime_checks']
        with patch.object(host, 'tick', wraps=host.tick) as tick:
            self.assertTrue(source.begin_latest())
            self.assertEqual(helper.seq, baseline_sequence+2)
            request = remote.recv(769).decode().split('|')
            self.assertEqual(request[3], 'PULL')
            remote.send('|'.join(['S', '1'*32, '2'*32, 'SAMPLE', epoch, 'c'*32,
                request[-1], '1', '1', 'sector_a', '1', '1', '2', '3', '10', '0', '0']).encode())
            completed, sample = source.poll_latest()
            self.assertTrue(completed)
            self.assertEqual(sample['sequence'], 1)
            self.assertEqual(helper.seq, baseline_sequence+4)
            tick.assert_not_called()  # Helper pumping must not poll the TCP owner.
        self.assertGreater(window.metrics['checkpoint_lifetime_checks'], baseline_lifetime)
        self.assertIsNone(control._reader_lease)
        self.assertFalse(host._busy); self.assertFalse(delivery._active)
        track = motion._tracks[(epoch, 'c'*32, 1)]
        expected_receipt = (1, motion_digest(sample))
        deadline = time.monotonic()+3
        while (len(track['peer_samples']) != 2 or not control._motion_idle()) and time.monotonic() < deadline:
            host.tick(.01)
        self.assertEqual(len(tcp.received), 2)
        self.assertEqual(list(track['peer_samples'].values()), [expected_receipt, expected_receipt])
        self.assertTrue(control._motion_idle())
        self.assertEqual(helper.seq, baseline_sequence+4)  # TCP callbacks use lifetime checks only.
        source.close()
        self.assertEqual(source.state, 'closed')
        self.assertTrue(window.stop_checkpoint(helper))
        self.assertTrue(window.close(process_guard=files.process_guard))
        self.assertEqual(helper.state, 'stopped')
        self.assertEqual(helper.helper.proc.returncode, 0)
        self.assertIsNone(helper.helper.pidfd)
        self.assertEqual(window.state, 'closed'); self.assertFalse(window.failed)
        self.assertIn('checking', pump_states); self.assertIn('stopping', pump_states)
        self.assertIsNone(control._reader_lease)
        self.assertFalse(host._busy); self.assertFalse(delivery._active)
        tcp.finish()
