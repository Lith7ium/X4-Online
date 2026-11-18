"""Paired playback wiring and real TCP/UDP ownership path; no native X4."""
import copy
import hashlib
import json
from pathlib import Path
import socket
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev'), str(ROOT/'tests')]
import authority_recovered_server_client as client
import authority_tcp_native_worker as worker
import authority_native_client_playback as playback
import test_authority_recovered_client_motion_install as installer_fixture
import test_authority_recovered_setter_worker_wiring as setter_fixture
from authority.experimental_tcp_participant_client import ExperimentalTCPParticipantClient
from authority.experimental_tcp_motion import motion_digest

EPOCH, FIXTURE = setter_fixture.EPOCH, setter_fixture.FIXTURE
SECTOR = 'cluster_06_sector001_macro'


def sample(sequence, source_time, x, velocity=None):
    return dict(version=1, epoch=EPOCH, generation='d'*32, index=1318, sequence=sequence,
                sector_macro=SECTOR, source_time=source_time, x=x, y=-7012.32470703125,
                z=128768.8359375, velocity=velocity)


def prepare_pinned_fixture(test):
    fixture = installer_fixture.Install()
    fixture.setUp()
    test.addCleanup(fixture.doCleanups)
    fixture.prepare_playback()
    fixture.status = playback.STATUS
    ids = ('ego_dlc_boron', 'ego_dlc_mini_01', 'ego_dlc_mini_02', 'ego_dlc_pirate',
           'ego_dlc_split', 'ego_dlc_terran', 'ego_dlc_timelines', 'ego_dlc_ventures', 'x4_lan_lab')
    (fixture.profile/'content.xml').write_text('<?xml version="1.0"?><content>'+''.join(
        '<extension id="'+name+'" enabled="true" />' for name in ids)+'</content>\n')
    test.assertEqual(hashlib.sha256((fixture.profile/'content.xml').read_bytes()).hexdigest(), playback.CONTENT_SHA)
    for name, digest in playback.SCRIPT_PINS.items():
        source = ROOT/('src/authority/md/checkpoint_marker.xml' if name == 'authority_checkpoint_marker.xml' else 'tools/dev/'+name)
        test.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), digest)
        (fixture.md/name).write_bytes(source.read_bytes())
    return fixture


class PlaybackSetup(unittest.TestCase):
    def test_real_installer_uses_one_index_and_carries_playback_without_setter(self):
        fixture = prepare_pinned_fixture(self)
        participant = client.ServerClient(time.monotonic()+5, fixture.case, keep_worker=True)
        self.addCleanup(participant.cleanup_diagnostic)
        paths = participant.prepare_client_motion(fixture.case, fixture.profile, fixture.status,
            dict(indices=[1318], generation='3'*32, timeout=2, saved_playback_fixture=FIXTURE),
            dict(world_epoch='e'*32, attempt_id='f'*32))
        self.assertTrue(all(path.is_file() for path in paths))
        config = (fixture.ui/'config.lua').read_text()
        self.assertIn('authority_client_motion_index=1318', config)
        self.assertIn('authority_client_motion_saved_playback_fixture="recovery_enh_870"', config)
        self.assertNotIn('authority_client_motion_saved_apply_fixture', config)
        self.assertNotIn('authority_client_motion_indices=', config)
        self.assertIn(fixture.ui/'motion_playback.lua', paths)
        self.assertEqual(participant.motion_worker_config['saved_playback_fixture'], FIXTURE)
        self.assertNotIn('saved_apply_fixture', participant.motion_worker_config)
        participant.redact()

    def test_fresh_verified_mapping_is_accepted_without_historical_digest(self):
        fixture = prepare_pinned_fixture(self)
        fresh_status = (*playback.STATUS[:3], 'd'*64)
        self.assertNotEqual(fresh_status, playback.STATUS)
        participant = client.ServerClient(time.monotonic()+5, fixture.case, keep_worker=True)
        self.addCleanup(participant.cleanup_diagnostic)
        paths = participant.prepare_client_motion(fixture.case, fixture.profile, fresh_status,
            dict(indices=[1318], generation='3'*32, timeout=2, saved_playback_fixture=FIXTURE),
            dict(world_epoch='e'*32, attempt_id='f'*32))
        self.assertIn(fixture.ui/'motion_playback.lua', paths)
        self.assertEqual(participant.motion_worker_config['saved_playback_fixture'], FIXTURE)

    def test_lineage_path_fences_still_reject_foreign_and_symlink_profiles(self):
        fixture = prepare_pinned_fixture(self)
        linked_case = fixture.case.parent/'linked-case'
        linked_case.symlink_to(fixture.case, target_is_directory=True)
        linked_profile = fixture.profile.parent/'linked-profile'
        linked_profile.symlink_to(fixture.profile, target_is_directory=True)
        for case, profile in ((linked_case, fixture.profile), (fixture.case, linked_profile),
                              (fixture.ui, fixture.profile)):
            with self.subTest(case=case, profile=profile), self.assertRaisesRegex(ValueError, 'lineage'):
                client.verify_playback_install_inputs(case, profile, playback.STATUS)

    def test_invalid_option_or_status_refuses_before_install_or_socket(self):
        request = dict(indices=[1318], generation='3'*32, timeout=2, saved_playback_fixture=FIXTURE)
        status = ('ready', EPOCH, 10082, 'd'*64)
        cases = [({**request, 'saved_apply_fixture': FIXTURE}, status),
                 ({**request, 'saved_playback_fixture': False}, status),
                 ({**request, 'saved_playback_fixture': 'other'}, status),
                 ({**request, 'indices': [1317]}, status), ({**request, 'indices': [1318,1319]}, status),
                 (request, ('ready', 'c'*32, 10082, 'd'*64)),
                 (request, ('pending', EPOCH, 10082, 'd'*64)),
                 (request, ('ready', EPOCH, 100, 'd'*64)),
                 (request, ('ready', EPOCH, 10082.0, playback.STATUS[3])),
                 (request, ('ready', EPOCH, 10082, 'invalid')),
                 (request, ('ready', EPOCH, True, 'd'*64)),
                 (request, ('ready', EPOCH, '10082', 'd'*64)),
                 (request, ('ready', EPOCH, 10082, 'D'*64)),
                 (request, ('ready', EPOCH, 10082, 123)),
                 (request, ('ready', EPOCH, 10082)),
                 (request, ['ready', EPOCH, 10082, 'd'*64])]
        with patch('authority_recovered_client_motion_install.install') as install:
            for request_value, status_value in cases:
                participant = client.ServerClient(time.monotonic()+5, Path('/unused'), keep_worker=True)
                self.addCleanup(participant.cleanup_diagnostic)
                with self.subTest(request=request_value, status=status_value), self.assertRaises(ValueError):
                    participant.prepare_client_motion(Path('/unused'), Path('/unused'), status_value, request_value,
                                                      dict(world_epoch='e'*32, attempt_id='f'*32))
                self.assertIsNone(participant.motion_sock)
            install.assert_not_called()

    def test_changed_current_content_or_script_is_refused_before_install(self):
        for name in ('content.xml', *playback.SCRIPT_PINS):
            with self.subTest(name=name):
                fixture = prepare_pinned_fixture(self)
                path = fixture.profile/name if name == 'content.xml' else fixture.md/name
                path.write_bytes(path.read_bytes()+b'<!-- changed -->')
                participant = client.ServerClient(time.monotonic()+5, fixture.case, keep_worker=True)
                self.addCleanup(participant.cleanup_diagnostic)
                with patch('authority_recovered_client_motion_install.install') as install, self.assertRaises(ValueError):
                    participant.prepare_client_motion(fixture.case, fixture.profile, fixture.status,
                        dict(indices=[1318],generation='3'*32,timeout=2,saved_playback_fixture=FIXTURE),
                        dict(world_epoch='e'*32,attempt_id='f'*32))
                self.assertIsNone(participant.motion_sock)
                install.assert_not_called()

    def test_worker_config_requires_explicit_epoch_fenced_exclusive_option(self):
        config = setter_fixture.worker_config()
        with patch.object(worker, 'check_process'):
            self.assertEqual(worker.config_value(json.dumps(config).encode())[0], config)
            config['motion']['saved_playback_fixture'] = FIXTURE
            self.assertEqual(worker.config_value(json.dumps(config).encode())[0], config)
            for change in ({'saved_playback_fixture': False}, {'saved_playback_fixture': 'other'},
                           {'epoch': 'c'*32}, {'saved_apply_fixture': FIXTURE}):
                altered = copy.deepcopy(config); altered['motion'].update(change)
                with self.subTest(change=change), self.assertRaises(ValueError):
                    worker.config_value(json.dumps(altered).encode())


class PairedPlayback(unittest.TestCase):
    def test_first_source_sequence_and_context_rejected_before_any_bridge(self):
        local = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); local.bind(('127.0.0.1',0))
        self.addCleanup(local.close)
        config = setter_fixture.worker_config(); config['motion']['saved_playback_fixture'] = FIXTURE
        owner = worker.LazyMotion(local, config, lambda: True); owner.running = True
        good = sample(1, 88.125, -116813.1328125)
        for change in ({'sequence': 2}, {'epoch': 'c'*32}, {'generation': 'e'*32},
                       {'index': 1317}, {'sector_macro': 'other'}):
            with self.subTest(change=change), patch.object(owner, '_bind') as bind, self.assertRaises(ValueError):
                owner({**good, **change}, False)
            bind.assert_not_called()
        with self.assertRaises(RuntimeError): owner.preflight(good)
        with self.assertRaises(RuntimeError): owner.apply_once(good)

    def test_three_real_source_packets_flow_on_one_tcp_to_udp_owner_unchanged(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(('127.0.0.1',0)); listener.listen(1)
        tcp = socket.create_connection(listener.getsockname(), timeout=1)
        server, _ = listener.accept(); server.settimeout(1)
        local = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); local.bind(('127.0.0.1',0))
        peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); peer.bind(('127.0.0.1',0)); peer.settimeout(2)
        for sock in (listener,tcp,server,local,peer): self.addCleanup(sock.close)
        config = setter_fixture.worker_config(); config['motion']['saved_playback_fixture'] = FIXTURE
        owner = worker.LazyMotion(local, config, lambda: True); owner.running = True
        participant = ExperimentalTCPParticipantClient(tcp, Mock(), enabled=True, epoch='9'*32,
                                                       handle=1, timeout=3, apply_motion=owner)
        packets, errors = [], []
        def simulated_x4():
            try:
                peer.sendto(f"R|{'a'*32}|{'b'*32}|READY|{EPOCH}|{'d'*32}".encode(), local.getsockname())
                for _ in range(4):
                    data, address = peer.recvfrom(768); fields = data.decode().split('|'); packets.append(fields)
                    kind = fields[3]
                    if kind == 'BIND': reply = ['R',*fields[1:3],'BOUND',*fields[4:11]]
                    elif kind == 'STOP': reply = ['R',*fields[1:3],'STOPPED',*fields[4:]]
                    else: raise AssertionError('unexpected setter privilege')
                    peer.sendto('|'.join(reply).encode(), address)
            except BaseException as error: errors.append(error)
        responder = threading.Thread(target=simulated_x4)
        originals = [sample(1,88.125,-116813.1328125),
                     sample(2,88.375,-116812.1328125,dict(x=4,y=0,z=0)),
                     sample(5,88.625,-116811.1328125,None)]
        before = copy.deepcopy(originals)
        try:
            with patch('authority_tcp_job_client_live.socket_owner',return_value=True):
                responder.start()
                bridge = None
                for value in originals:
                    message = dict(version=1,kind='motion_snapshot',connection_handle=1,session_epoch='9'*32,
                                   incarnation='3'*32,request_id=value['sequence'],sample=value)
                    server.sendall(json.dumps(message).encode()+b'\n')
                    deadline = time.monotonic()+2
                    while not participant.poll(.01): self.assertLess(time.monotonic(),deadline)
                    receipt = json.loads(server.recv(4096))
                    self.assertEqual(receipt['sample_sha256'],motion_digest(value))
                    self.assertEqual(receipt['status'],'accepted')
                    bridge = bridge or owner.bridge
                    self.assertIs(owner.bridge,bridge)
                self.assertFalse(owner.bridge._allow_apply)
                self.assertTrue(owner.stop())
            responder.join(2)
            self.assertFalse(responder.is_alive()); self.assertFalse(errors)
            self.assertEqual(originals,before)
            self.assertEqual([fields[3] for fields in packets],['BIND','BIND','BIND','STOP'])
            for fields,value in zip(packets,originals):
                self.assertEqual(int(fields[8]),value['sequence'])
                self.assertEqual(float(fields[11]),value['source_time'])
                self.assertEqual([float(v) for v in fields[12:15]],[value[a] for a in ('x','y','z')])
                self.assertEqual(fields[15:18],['-']*3 if value['velocity'] is None else ['4','0','0'])
            self.assertTrue(owner.stopped)
            with self.assertRaises(RuntimeError): owner(originals[-1],False)
        finally:
            responder.join(2)
            participant.close(); owner.close()
