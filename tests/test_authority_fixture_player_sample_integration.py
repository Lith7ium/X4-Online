"""Offline fixture writer integration; no X4 or real profile is started."""
import copy
import math
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
import authority_fixture_player_sample_install as install
import authority_recovered_loopback_server as supervisor
import authority_fixture_player_source_observe as observe
from authority.experimental_tcp_motion import motion_digest


class FixtureSampleIntegrationTest(unittest.TestCase):
    def test_installs_one_bridge_tick_and_checks_final_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = Path(temporary) / 'case'
            lab = case / 'extensions/x4_lan_lab'
            ui, md = lab / 'ui', lab / 'md'
            ui.mkdir(parents=True); md.mkdir()
            profile = case / 'home/.config/EgoSoft/X4/45841'
            (profile / 'save').mkdir(parents=True)
            bridge = ui / 'authority_world_bridge_probe.lua'
            bridge.write_text("SetScript('onUpdate',function()\n local ok,reason=bridge:update();assert(ok,reason)\nend)\n")
            (lab / 'ui.xml').write_text('    <file name="ui/authority_world_bridge_probe.lua" />\n')
            (ui / 'config.lua').write_text('X4LAN_CONFIG = {enabled=false}\n')
            paths = install.install(case, profile, slot=2, port=12345, epoch='a'*32,
                                    generation='b'*32, lease='c'*32, attempt='d'*32, nonce='e'*32)
            self.assertTrue(all(path.is_file() and path.is_relative_to(case) for path in paths))
            self.assertEqual(bridge.read_text().count("SetScript('onUpdate'"), 1)
            self.assertIn('X4LAN_FIXTURE_SAMPLE_WRITE_TICK()', bridge.read_text())
            self.assertIn('fixture_sample_write_slot=2', (ui / 'config.lua').read_text())
            self.assertIn('X4LAN_FIXTURE_PLAYER_SAMPLE_WRITER = M', (ui / 'authority_fixture_player_sample_writer.lua').read_text())
            log = profile / 'engine-output.log'
            nonce, digest = 'e'*32, 'f'*64
            log.write_text('[X4LAN] AUTH_FIXTURE_SAMPLE_WRITE WRITE_ENTERED ' + nonce + '\n' +
                           '[X4LAN] AUTH_FIXTURE_SAMPLE_WRITE OBSERVED ' + nonce + ' ' + digest + '\n')
            self.assertTrue(install.verify_log(log, nonce=nonce, digest=digest))
            log.write_text(log.read_text() + '[X4LAN] AUTH_FIXTURE_SAMPLE_WRITE ERROR\n')
            with self.assertRaises(ValueError): install.verify_log(log, nonce=nonce, digest=digest)

    def test_one_validated_sample_reaches_writer_once(self):
        grants = {handle: {'session_epoch':'a'*32, 'epoch':'b'*32, 'generation':'c'*32,
                  'index':handle+2, 'sector_macro':'sector_'+str(handle), 'token':str(handle)*32,
                  'incarnation':str(handle+2)*32} for handle in (1, 2)}
        session = SimpleNamespace(world_epoch='a'*32, players=((1,'one'),(2,'two')),
                                  ready_players=((1,'one'),(2,'two')), state='running', pending=None)
        world = SimpleNamespace(session=session)
        host = SimpleNamespace(_world=world, _failed=False, tick=lambda *_a, **_k: None)
        calls = []

        class Delivery:
            def __init__(self, *_args, **_kwargs): self._failed = False
            def bind_test_incarnations(self, *_args, **_kwargs): return True
        class Owner:
            def __init__(self, _delivery, *, grant, **_kwargs): self.grant, self.sequence = grant, 0
            def pull(self):
                self.sequence += 1
                return {'version':2, 'epoch':self.grant['epoch'], 'generation':self.grant['generation'],
                        'index':self.grant['index'], 'sequence':self.sequence,
                        'sector_macro':self.grant['sector_macro'], 'source_time':float(self.sequence),
                        'x':110., 'y':20., 'z':30.,
                        'velocity':None if self.sequence == 1 else {'x':0.,'y':0.,'z':0.},
                        'orientation':{'yaw':0.,'pitch':0.,'roll':0.},
                        'angular_rate':None if self.sequence == 1 else {'yaw':0.,'pitch':0.,'roll':0.}}
        def write(handle, grant, sample):
            calls.append((handle, copy.deepcopy(sample)))
            target = [sample['x'],sample['y'],sample['z']]
            before = [100.,20.,30.]
            return {'registry_index':grant['index'], 'sector_macro':grant['sector_macro'],
                    'source_sequence':sample['sequence'], 'sample_sha256':motion_digest(sample),
                    'target':target, 'before':before, 'after':target.copy(),
                    'initial_distance':math.dist(before,target), 'target_error':0.,
                    'position_only':True, 'sustained_motion_proven':False}
        with patch.object(observe, 'ExperimentalTCPJobDelivery', Delivery), patch.object(observe, 'ExperimentalTCPClientAuthorityMotion', Owner):
            result = observe.observe(host=host, world=world, grants=grants, verify=lambda: True,
                deadline=time.monotonic()+5, enabled=True, sample_write_slot=2, write_sample_once=write)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], 2)
        self.assertEqual(result['server_position_once']['registry_index'], 4)
        self.assertTrue(result['source_to_server_frame_assumed'])
        self.assertFalse(result['same_run_frame_proven'])
        self.assertFalse(result['server_x4_motion_applied'])
        self.assertTrue(result['server_x4_position_once_applied'])
        self.assertFalse(result['client_movement_proven'])

    def test_no_write_when_throttle_unconfirmed_or_source_does_not_move(self):
        grants = {handle: {'session_epoch':'a'*32, 'epoch':'b'*32, 'generation':'c'*32,
                  'index':handle+2, 'sector_macro':'sector_'+str(handle), 'token':str(handle)*32,
                  'incarnation':str(handle+2)*32} for handle in (1, 2)}
        expected_receipt = {'start_dispatched':True, 'start_acknowledged':True, 'stop_acknowledged':True,
                            'movement_proven':False, 'human_input_proven':False, 'stationary_proven':False, 'stop_game_time':1.5}
        for mode in ('no_movement', 'missing_stop', 'throttle_error'):
            with self.subTest(mode=mode):
                session = SimpleNamespace(world_epoch='a'*32, players=((1,'one'),(2,'two')),
                    ready_players=((1,'one'),(2,'two')), state='running', pending=None)
                world = SimpleNamespace(session=session)
                host = SimpleNamespace(_world=world, _failed=False, tick=lambda *_a, **_k: None)
                writes = []
                class Delivery:
                    def __init__(self, *_args, **_kwargs): self._failed = False
                    def bind_test_incarnations(self, *_args, **_kwargs): return True
                class Owner:
                    def __init__(self, _delivery, *, grant, **_kwargs): self.grant, self.sequence = grant, 0
                    def pull(self):
                        self.sequence += 1
                        return {'version':2, 'epoch':self.grant['epoch'], 'generation':self.grant['generation'],
                            'index':self.grant['index'], 'sequence':self.sequence, 'sector_macro':self.grant['sector_macro'],
                            'source_time':float(self.sequence), 'x':100., 'y':20., 'z':30.,
                            'velocity':None if self.sequence == 1 else {'x':0.,'y':0.,'z':0.},
                            'orientation':{'yaw':0.,'pitch':0.,'roll':0.},
                            'angular_rate':None if self.sequence == 1 else {'yaw':0.,'pitch':0.,'roll':0.}}
                def pulse(_handle, _grant):
                    if mode == 'throttle_error': raise RuntimeError('unconfirmed impulse')
                    receipt = dict(expected_receipt)
                    if mode == 'missing_stop': receipt['stop_acknowledged'] = False
                    return receipt
                with (patch.object(observe, 'ExperimentalTCPJobDelivery', Delivery),
                      patch.object(observe, 'ExperimentalTCPClientAuthorityMotion', Owner),
                      patch.object(observe, 'MAX_PULLS_PER_PLAYER', 4)):
                    with self.assertRaises((RuntimeError, ValueError)):
                        observe.observe(host=host, world=world, grants=grants, verify=lambda: True,
                            deadline=time.monotonic()+5, operation_timeout=1, enabled=True, sample_write_slot=1,
                            write_sample_once=lambda *_args: writes.append(True), pulse_client_once=pulse)
                self.assertEqual(writes, [])
                self.assertTrue(host._failed)

    def test_write_secrets_redacted_only_after_owned_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / 'config.lua'
            raw = 'authority_control_lease="' + 'a'*32 + '"'
            for key, token in zip(('generation', 'lease', 'attempt', 'nonce'), ('b', 'c', 'd', 'e')):
                raw += ',fixture_sample_write_' + key + '="' + token*32 + '"'
            config.write_text(raw)
            with self.assertRaises(RuntimeError):
                supervisor.redact_stopped_server_config(config, [123])
            self.assertEqual(config.read_text(), raw)
            supervisor.redact_stopped_server_config(config, [])
            redacted = config.read_text()
            for token in 'abcde': self.assertNotIn(token*32, redacted)
            with self.assertRaises(ValueError):
                supervisor.redact_recovery_config(raw + ',fixture_sample_write_lease="' + 'c'*32 + '"')

    def test_identical_position_is_not_accepted_as_a_write(self):
        sample = {'version':2, 'epoch':'a'*32, 'generation':'b'*32, 'index':3, 'sequence':1,
                  'sector_macro':'sector_1', 'source_time':1., 'x':1., 'y':2., 'z':3., 'velocity':None,
                  'orientation':{'yaw':0.,'pitch':0.,'roll':0.}, 'angular_rate':None}
        report = {'registry_index':3,'sector_macro':'sector_1','source_sequence':1,
                  'sample_sha256':motion_digest(sample),'target':[1.,2.,3.],'before':[1.,2.,3.],
                  'after':[1.,2.,3.],'initial_distance':0.,'target_error':0.,
                  'position_only':True,'sustained_motion_proven':False}
        with self.assertRaises(ValueError): observe.validate_sample_write_report(report, sample)
