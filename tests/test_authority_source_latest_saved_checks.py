"""Opt-in saved-check boundaries over real loopback UDP/TCP; no X4."""
import select
import socket
from types import SimpleNamespace
import unittest

from tests import test_authority_experimental_tcp_motion as fixture
from authority.experimental_source_motion_ipc import ExperimentalSourceMotionIPC
from authority.experimental_tcp_job_delivery import ExperimentalTCPJobDelivery
from authority.experimental_tcp_motion import ExperimentalTCPMotion


class LatestSavedChecks(unittest.TestCase):
    def owners(self, **changes):
        case = fixture.MotionTCP('test_invalid_values_and_no_fake_velocity')
        case.setUp()
        self.addCleanup(case.doCleanups)
        client = case.case.connect()
        case.case.offer_and_claim(client)
        case.client(client, 1)
        case.case.host.tick(.1)
        host, control = case.case.host, case.case.control
        control.enable_latest_motion(enabled=True, timeout=1)
        delivery = ExperimentalTCPJobDelivery(host, enabled=True, timeout=1)
        motion = ExperimentalTCPMotion(delivery, enabled=True, min_interval=1/240)
        local = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        remote = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for sock in (local, remote):
            sock.bind(('127.0.0.1', 0))
            self.addCleanup(sock.close)
        local.connect(remote.getsockname())
        remote.connect(local.getsockname())
        remote.settimeout(.2)
        events = []
        holder = SimpleNamespace(bridge=None, full_action=lambda: True)
        def full(epoch, baseline):
            events.append(('full', holder.bridge.state if holder.bridge else 'constructing'))
            return epoch == 'b'*32 and baseline == 20000 and holder.full_action()
        def lifetime(epoch, baseline):
            events.append(('lifetime', holder.bridge.state))
            return epoch == 'b'*32 and baseline == 20000
        def guard():
            events.append(('guard', holder.bridge.state))
            return True
        def peer(address):
            events.append(('peer', holder.bridge.state))
            return address == remote.getsockname()
        options = dict(enabled=True, lease='1'*32, attempt='2'*32, epoch='b'*32,
            generation='c'*32, guard=guard, validate_peer=peer, timeout=2,
            latest=True, select_recipients=lambda _, members: members,
            saved_baseline=20000, saved_guard=full, saved_lifetime_guard=lifetime,
            batch_latest_saved_checks=True)
        options.update(changes)
        bridge = ExperimentalSourceMotionIPC(local, motion, **options)
        holder.bridge = bridge
        bridge.bind_confirmed(10055)
        events.clear()
        return SimpleNamespace(bridge=bridge, remote=remote, motion=motion,
            host=host, control=control, delivery=delivery, holder=holder, events=events)

    def response(self, owners, *, empty=False):
        packet = owners.remote.recv(769).decode().split('|')
        prefix = ['S', '1'*32, '2'*32]
        if empty:
            fields = prefix + ['NO_SAMPLE', 'b'*32, 'c'*32, packet[-1]]
        else:
            fields = prefix + ['SAMPLE', 'b'*32, 'c'*32, packet[-1],
                '10055', '1', 'sector_a', '1', '1', '2', '3', '-', '-', '-']
        owners.remote.send('|'.join(fields).encode())

    def counts(self, owners):
        return {kind: sum(event[0] == kind for event in owners.events)
                for kind in ('full', 'lifetime', 'guard', 'peer')}

    def test_two_full_boundaries_for_begin_pending_completed_and_empty_poll(self):
        for mode in ('pending', 'completed', 'empty'):
            with self.subTest(mode=mode):
                owners = self.owners()
                self.assertTrue(owners.bridge.begin_latest())
                counts = self.counts(owners)
                self.assertEqual(counts['full'], 2)
                self.assertGreater(counts['lifetime'], 0)
                self.assertGreater(counts['guard'], 0)
                self.assertGreater(counts['peer'], 0)
                owners.events.clear()
                if mode != 'pending':
                    self.response(owners, empty=mode == 'empty')
                result = owners.bridge.poll_latest()
                self.assertEqual(result[0], mode != 'pending')
                counts = self.counts(owners)
                self.assertEqual(counts['full'], 2)
                self.assertGreater(counts['lifetime'], 0)
                self.assertEqual([phase for kind, phase in owners.events if kind == 'full'],
                    ['pulling', 'pulling' if mode == 'pending' else 'ready'])
                self.assertFalse(owners.bridge._lifetime_only)

    def test_default_retains_nested_full_checks_without_lifetime_substitution(self):
        owners = self.owners(batch_latest_saved_checks=False)
        self.assertTrue(owners.bridge.begin_latest())
        self.assertEqual(self.counts(owners)['full'], 2)
        self.assertEqual(self.counts(owners)['lifetime'], 0)
        owners.events.clear()
        self.assertEqual(owners.bridge.poll_latest(), (False, None))
        self.assertEqual(self.counts(owners)['full'], 2)
        self.assertEqual(self.counts(owners)['lifetime'], 0)
        self.response(owners)
        owners.events.clear()
        self.assertTrue(owners.bridge.poll_latest()[0])
        self.assertGreater(self.counts(owners)['full'], 2)
        self.assertEqual(self.counts(owners)['lifetime'], 0)

    def test_obsolete_reply_uses_zero_full_checks_and_is_discarded(self):
        owners = self.owners()
        owners.bridge.begin_latest()
        owners.control.motion_barrier()
        owners.control.release_motion_barrier()
        self.response(owners)
        owners.events.clear()
        owners.holder.full_action = lambda: self.fail('obsolete reply must not use full guard')
        self.assertEqual(owners.bridge.poll_latest(), (True, None))
        self.assertEqual(self.counts(owners)['full'], 0)
        self.assertGreater(self.counts(owners)['lifetime'], 0)
        self.assertTrue(owners.control._motion_idle())
        self.assertFalse(owners.bridge._lifetime_only)

    def test_invalid_options_are_rejected_before_any_saved_checks(self):
        for change in ({'batch_latest_saved_checks': 1}, {'batch_latest_saved_checks': None},
                       {'latest': False, 'saved_lifetime_guard': None},
                       {'saved_guard': None, 'saved_baseline': None, 'saved_lifetime_guard': None},
                       {'saved_lifetime_guard': None}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.owners(**change)

    def test_begin_pre_and_post_failures_fence_without_returning_success(self):
        for boundary in (1, 2):
            for raises in (False, True):
                with self.subTest(boundary=boundary, raises=raises):
                    owners = self.owners()
                    full_calls = 0
                    def full_action():
                        nonlocal full_calls
                        full_calls += 1
                        if full_calls == boundary:
                            if raises:
                                raise RuntimeError('full guard fault')
                            return False
                        return True
                    owners.holder.full_action = full_action
                    with self.assertRaises(RuntimeError):
                        owners.bridge.begin_latest()
                    self.assertEqual(owners.bridge.state, 'failed')
                    self.assertTrue(owners.host._failed)
                    self.assertFalse(owners.bridge._lifetime_only)
                    readable = bool(select.select([owners.remote], [], [], 0)[0])
                    self.assertEqual(readable, boundary == 2)

    def test_poll_pre_and_post_enqueue_failures_fence_and_restore_flag(self):
        for boundary in (1, 2):
            for raises in (False, True):
                with self.subTest(boundary=boundary, raises=raises):
                    owners = self.owners()
                    owners.bridge.begin_latest()
                    self.response(owners)
                    full_calls = 0
                    def full_action():
                        nonlocal full_calls
                        full_calls += 1
                        if full_calls == boundary:
                            if raises:
                                raise RuntimeError('full guard fault')
                            return False
                        return True
                    owners.holder.full_action = full_action
                    # Restoration must preserve the caller's previous mode.
                    owners.bridge._lifetime_only = True
                    with self.assertRaises(RuntimeError):
                        owners.bridge.poll_latest()
                    self.assertEqual(owners.bridge.state, 'failed')
                    self.assertTrue(owners.host._failed)
                    self.assertTrue(owners.bridge._lifetime_only)
                    self.assertEqual(bool(owners.control._peers[next(iter(owners.control._peers))]
                                          .get('motion_pending')), boundary == 2)

    def test_lifetime_guard_fault_inside_operation_is_terminal(self):
        owners = self.owners()
        owners.bridge._saved_lifetime_guard = lambda epoch, baseline: False
        with self.assertRaises(RuntimeError):
            owners.bridge.begin_latest()
        self.assertEqual(owners.bridge.state, 'failed')
        self.assertFalse(owners.bridge._lifetime_only)
        self.assertFalse(select.select([owners.remote], [], [], 0)[0])


if __name__ == '__main__':
    unittest.main()
