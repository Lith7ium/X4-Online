"""Synthetic evidence checks only; no X4, transfer, or admission is performed."""
import hashlib
from pathlib import Path
import sys
import tempfile
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
from authority.checkpoints import Checkpoint
from authority.save_transfer import SaveOffer
from authority.world import LoadOffer
import authority_marked_admission_evidence as evidence


class MarkedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name)
        self.target = path / 'save_009.xml.gz'
        self.target.write_bytes(b'synthetic save bytes')
        digest = hashlib.sha256(self.target.read_bytes()).hexdigest()
        self.marker = 'a' * 32
        checkpoint_id = 'checkpoint-' + 'b' * 32
        self.cp = Checkpoint(checkpoint_id, self.target, digest, self.target.stat().st_size)
        save = SaveOffer('j1.xml.gz', digest, self.cp.size, checkpoint_id)
        self.offer = LoadOffer('world', 1, 2, 3, save)
        self.world = SimpleNamespace(_load_offers={1: self.offer},
                                     _store=SimpleNamespace(get=lambda _id: self.cp, latest_confirmed=lambda: self.cp),
                                     _baseline=(2,self.cp),
                                     session=SimpleNamespace(state='paused', ready_players=(), pending=None,
                                        save_required=False, players=((1,'local'),), world_epoch='world',
                                        baseline_id=2, _loads={1:(3,2)}))
        self.ticket = dict(world_epoch='world', connection_handle=1, baseline_id=2,
                           load_generation=3, checkpoint_id=checkpoint_id, sha256=digest,
                           attempt_id='c' * 32, slot='save_009')
        self.expected = MappingProxyType(dict(self.ticket))
        self.server = path / 'server.log'; self.client = path / 'client.log'
        identity = lambda phase: ''.join(
            f'[X4LAN] AUTH_IDENTITY {phase} ACTOR {i} id={i} name=Authority identity {name} macro=ship_arg_s_fighter_01_a_macro\n'
            for i,name in ((1,'alpha 7181'),(2,'beta 7182'))) + f'[X4LAN] AUTH_IDENTITY {phase} READY\n'
        self.server.write_text(identity('save') + '[X4LAN] AUTH_MARKER save STORED ' + self.marker + '\n')
        fields = '|'.join(str(self.ticket[k]) for k in evidence.FIELDS)
        self.client.write_text('[X4LAN] AUTH_DOWNLOAD_LOAD load_requested|' + fields + '\n' + identity('load') +
                               '[X4LAN] AUTH_MARKER load INSPECTED ' + self.marker + '\n'
                               '[X4LAN] AUTH_DOWNLOAD_LOAD pause_observed|' + fields + '\n')
        self.marker_patch = patch.object(evidence, 'verify_saved_marker', return_value=True)
        self.marker_mock = self.marker_patch.start()
        self.addCleanup(self.marker_patch.stop)

    def run_verify(self, **kwargs):
        args = dict(world=self.world, handle=1, ticket=self.ticket, expected_ticket=self.expected,
                    target=self.target, marker=self.marker, server_log=self.server,
                    client_log=self.client, check_processes=lambda: True, check_protected=lambda: True)
        args.update(kwargs)
        return evidence.verify(**args)

    def test_success_is_descriptive_and_no_admission(self):
        result = self.run_verify()
        self.assertTrue(result['ordered_load_receipts'])
        self.assertFalse(result['exact_x4_bytes_read_proven'])
        self.assertFalse(result['attempt_authenticated'])
        self.assertFalse(result['confirmed_checkpoint_current_at_return_proven'])
        self.assertFalse(result['admission_authorized'])
        self.assertNotIn('trusted_confirmation', result)
        self.assertIs(self.world._load_offers[1], self.offer)
        self.marker_mock.assert_called_once_with(self.cp, self.marker,
                script_name='X4AuthorityCheckpointMarker', cue_name='Store')

    def test_stale_attempt_and_offer(self):
        for field, value in (('attempt_id', 'd' * 32), ('load_generation', 2)):
            changed = dict(self.ticket, **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.run_verify(ticket=changed)
        self.world._load_offers.clear()
        with self.assertRaises(ValueError): self.run_verify()

    def test_boolean_never_aliases_integer_ticket_fields(self):
        for field in ('connection_handle', 'baseline_id', 'load_generation'):
            ticket = dict(self.ticket, **{field: True})
            expected = MappingProxyType(dict(ticket))
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.run_verify(ticket=ticket, expected_ticket=expected)

    def test_wrong_or_duplicate_marker_or_receipt(self):
        original = self.client.read_text()
        cases = (original.replace(self.marker, 'd' * 32),
                 original + '[X4LAN] AUTH_MARKER load INSPECTED ' + self.marker + '\n',
                 original + original.splitlines()[0] + '\n',
                 '\n'.join(reversed(original.splitlines())) + '\n')
        for text in cases:
            self.client.write_text(text)
            with self.subTest(text=text[:35]), self.assertRaises(ValueError): self.run_verify()
        self.client.write_text(original)
        self.marker_mock.side_effect = ValueError('saved marker mismatch')
        with self.assertRaises(ValueError): self.run_verify()

    def test_final_log_check_rejects_late_identity_or_marker(self):
        self.assertIsNone(evidence.verify_logs(self.server,self.client,self.marker,self.ticket))
        with self.client.open('a') as f:
            f.write('[X4LAN] AUTH_IDENTITY load READY\n')
        with self.assertRaises(ValueError):
            evidence.verify_logs(self.server,self.client,self.marker,self.ticket)

    def test_receipts_are_checked_from_identity_and_marker_snapshot(self):
        # A separate poll could observe B between the A snapshots of the log.
        with patch.object(evidence.download_live.ReceiptWatch, 'poll',
                          side_effect=AssertionError('must not reopen receipt log')):
            self.assertTrue(self.run_verify()['ordered_load_receipts'])
            original = self.client.read_bytes()
            self.client.write_bytes(original.rstrip(b'\n'))
            with self.assertRaises(ValueError):
                self.run_verify()
            self.client.write_bytes(original + b'x' * (evidence.download_live.ReceiptWatch.MAX_LINE + 1) + b'\n')
            with self.assertRaises(ValueError):
                self.run_verify()

    def test_target_change_or_symlink_is_refused(self):
        self.target.write_bytes(b'wrong')
        with self.assertRaises(ValueError): self.run_verify()
        self.target.unlink()
        self.target.symlink_to(self.client)
        with self.assertRaises(OSError): self.run_verify()

    def test_check_failures_and_mutation_during_verification(self):
        for name in ('check_processes', 'check_protected'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.run_verify(**{name: lambda: False})
            def fail(): raise RuntimeError('supervisor check failed')
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                self.run_verify(**{name: fail})
        calls = []
        def mutate():
            calls.append(1)
            if len(calls) == 2: self.target.write_bytes(b'changed')
            return True
        with self.assertRaises(ValueError): self.run_verify(check_protected=mutate)

    def test_world_must_be_paused_and_target_unready(self):
        self.world.session.state = 'running'
        with self.assertRaises(ValueError): self.run_verify()
        self.world.session.state = 'paused'; self.world.session.ready_players = ((1, 'player'),)
        with self.assertRaises(ValueError): self.run_verify()

    def test_offered_checkpoint_must_still_be_confirmed(self):
        self.world._store.latest_confirmed = lambda: None
        with self.assertRaises(ValueError): self.run_verify()

    def test_pointer_may_change_after_initial_observation(self):
        # This observation is intentionally not an admission or freshness proof.
        def pointer_changed(*args, **kwargs):
            self.world._store.latest_confirmed = lambda: None
        self.marker_mock.side_effect = pointer_changed
        result = self.run_verify()
        self.assertFalse(result['confirmed_checkpoint_current_at_return_proven'])
        self.assertFalse(result['admission_authorized'])

    def test_current_session_fences_stale_or_disconnected_load(self):
        s=self.world.session
        for field,value in (('baseline_id',9),('world_epoch','other'),('players',()),
                            ('_loads',{1:(4,2)}),('pending',object()),('save_required',True)):
            original=getattr(s,field);setattr(s,field,value)
            with self.subTest(field=field), self.assertRaises(ValueError): self.run_verify()
            setattr(s,field,original)


if __name__ == '__main__': unittest.main()
