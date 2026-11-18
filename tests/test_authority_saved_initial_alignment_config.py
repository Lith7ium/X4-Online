"""Fixture alignment configuration and generated overlays; no X4 execution."""
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev'), str(ROOT / 'tests')]

from authority.client_motion_overlay import (
    RECOVERY_APPLY_EPOCH, RECOVERY_APPLY_FIXTURE, render_motion_config,
    validate_motion_settings,
)
from authority.experimental_client_load import HonestClientLoadClaim
from authority.load_messages import Receipt
from authority.trusted_load_messages import encode_load_claim
from authority import windows_fixture_session
import authority_recovered_client_motion_install as installer
import authority_recovered_server_client as recovered
import authority_tcp_native_worker as worker
import test_authority_recovered_client_motion_install as overlay_fixture
from test_authority_client_motion_overlay import playback_settings

FIXTURE = RECOVERY_APPLY_FIXTURE
OPTION = 'saved_initial_alignment_fixture'


def alignment_settings():
    settings = playback_settings()
    settings.update(saved_replica_control_fixture=FIXTURE,
                    saved_initial_alignment_fixture=FIXTURE)
    return settings


def alignment_request():
    return {'generation': '3' * 32, 'indices': [1318], 'timeout': 5,
            'saved_playback_fixture': FIXTURE,
            'saved_replica_control_fixture': FIXTURE,
            OPTION: FIXTURE}


class InitialAlignmentConfigTests(unittest.TestCase):
    def setUp(self):
        self.status = ('ready', RECOVERY_APPLY_EPOCH, 10082, 'a' * 64)

    def test_alignment_requires_fixed_controlled_playback_context(self):
        valid = alignment_settings()
        validate_motion_settings(self.status, valid)
        self.assertIn('authority_client_motion_saved_initial_alignment_fixture="recovery_enh_870"',
                      render_motion_config(self.status, valid))
        self.assertNotIn('saved_initial_alignment',
                         render_motion_config(self.status, playback_settings()))
        for change in ({OPTION: None}, {OPTION: True}, {OPTION: 'other'},
                       {'saved_replica_control_fixture': None},
                       {'saved_playback_fixture': None}, {'index': 1317},
                       {'indices': [1318]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_motion_settings(self.status, dict(valid, **change))
        for missing in ('saved_replica_control_fixture', 'saved_playback_fixture'):
            candidate = dict(valid)
            del candidate[missing]
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                validate_motion_settings(self.status, candidate)
        with self.assertRaises(ValueError):
            validate_motion_settings(('ready', 'b' * 32, 10082, 'a' * 64), valid)

    def test_generated_overlay_forwards_opt_in_and_keeps_readonly_binder(self):
        fixture = overlay_fixture.Install()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.prepare_playback()
        fixture.settings.update(saved_replica_control_fixture=FIXTURE,
                                saved_initial_alignment_fixture=FIXTURE)
        fixture.install()
        control = (fixture.ui / 'authority_two_x4_participant_probe.lua').read_text()
        self.assertIn('saved_initial_alignment_fixture=cfg.authority_client_motion_saved_initial_alignment_fixture,',
                      control)
        self.assertIn('authority_client_motion_saved_initial_alignment_fixture="recovery_enh_870"',
                      (fixture.ui / 'config.lua').read_text())
        self.assertEqual((fixture.md / 'authority_saved_baseline_motion_bind.xml').read_bytes(),
                         (ROOT / 'tools/dev/authority_saved_baseline_motion_bind.xml').read_bytes())
        self.assertFalse((fixture.md / 'authority_saved_motion_apply.xml').exists())
        self.assertLess(control.index('client playback STOP required before pause'),
                        control.index("assert(state:submit('isolated-client'"))

    def test_windows_request_validation_and_settings_forwarding(self):
        request = alignment_request()
        windows_fixture_session.validate_motion_request(request, 30)
        bound = SimpleNamespace(offer=SimpleNamespace(
            world_epoch='a' * 32, attempt_id='b' * 32,
            checkpoint_id='checkpoint-' + 'c' * 32))
        settings = windows_fixture_session._motion_settings(
            request, self.status, bound, SimpleNamespace(lease='d' * 32), 'e' * 32, 23456)
        self.assertEqual(settings[OPTION], FIXTURE)
        validate_motion_settings(self.status, settings)
        for change in ({OPTION: None}, {OPTION: 'other'},
                       {'saved_replica_control_fixture': None},
                       {'saved_playback_fixture': None}, {'indices': [1317]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                windows_fixture_session.validate_motion_request(dict(request, **change), 30)

    def test_recovered_client_forwards_settings_and_worker_context(self):
        client = object.__new__(recovered.ServerClient)
        client.keep_worker = True
        client.motion_sock = client.motion_worker_config = None
        client.client_authority_worker_config = None
        client.lease = 'a' * 32
        client._pin_motion_socket = Mock()
        ticket = {'world_epoch': 'b' * 32, 'attempt_id': 'c' * 32}
        with patch.object(recovered, 'verify_playback_install_inputs') as verify, \
                patch.object(installer, 'install', return_value=SimpleNamespace(paths=())) as install:
            client.prepare_client_motion(Path('/private'), Path('/private/45841'),
                                         self.status, alignment_request(), ticket)
        self.addCleanup(client.motion_sock.close)
        verify.assert_called_once()
        settings = install.call_args.args[3]
        validate_motion_settings(self.status, settings)
        self.assertEqual(settings[OPTION], FIXTURE)
        self.assertEqual(client.motion_worker_config[OPTION], FIXTURE)
        for change in ({OPTION: None}, {'saved_replica_control_fixture': None}):
            other = object.__new__(recovered.ServerClient)
            other.keep_worker = True
            other.motion_sock = other.motion_worker_config = None
            other.client_authority_worker_config = None
            with self.subTest(change=change), self.assertRaises(ValueError):
                other.prepare_client_motion(Path('/private'), Path('/private/45841'),
                                            self.status, dict(alignment_request(), **change), ticket)

    def test_worker_preserves_alignment_and_rejects_missing_control_or_wrong_epoch(self):
        receipt = Receipt('a' * 32, 1, 1, 1, 'b' * 32,
                          'checkpoint-' + 'c' * 32, 'd' * 64, 10)
        claim = encode_load_claim(HonestClientLoadClaim(receipt, 'e' * 32, True, True))
        proc = Path('/proc') / str(os.getpid())
        image = (proc / 'exe').stat()
        fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
        config = {'version': 1, 'claim': claim.decode('ascii'), 'epoch': receipt.world_epoch,
                  'handle': 1, 'lease': 'f' * 32, 'udp_peer': ['127.0.0.1', 23456],
                  'udp_next_id': 2, 'deadline': time.monotonic() + 10,
                  'controller_timeout': 30,
                  'client_process': {'pid': os.getpid(), 'start_ticks': int(fields[19]),
                                     'exe_dev': image.st_dev, 'exe_ino': image.st_ino},
                  'motion': {'lease': '1' * 32, 'attempt': '2' * 32,
                             'epoch': RECOVERY_APPLY_EPOCH, 'generation': '3' * 32,
                             'timeout': 5, 'saved_playback_fixture': FIXTURE,
                             'saved_replica_control_fixture': FIXTURE, OPTION: FIXTURE}}
        result, _, _ = worker.config_value(json.dumps(config).encode())
        self.assertEqual(result['motion'][OPTION], FIXTURE)
        for change in ({OPTION: None}, {'saved_replica_control_fixture': None},
                       {'saved_playback_fixture': None}, {'epoch': '9' * 32}):
            candidate = dict(config, motion=dict(config['motion'], **change))
            with self.subTest(change=change), self.assertRaises(ValueError):
                worker.config_value(json.dumps(candidate).encode())


if __name__ == '__main__':
    unittest.main()
