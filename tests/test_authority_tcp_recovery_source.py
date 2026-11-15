"""Pinned TCP recovery provenance tests on disposable synthetic archives."""
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev'),str(ROOT/'tests')]
from authority.checkpoints import CheckpointStore
from test_authority_trusted_marker_load_session import XML, MARKER
import authority_tcp_recovery_source as subject
import authority_recovery_bridge_live as bridge


class TCPSourceTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.store_path=self.root/'source/checkpoints';self.store_path.mkdir(parents=True)
        source=self.root/'save.gz';source.write_bytes(gzip.compress(XML.encode()))
        self.store=CheckpointStore(self.store_path);self.checkpoint=self.store.publish(source,marker=MARKER)
        self.store.confirm(self.checkpoint)
        server=self.store_path.parent/'server/case'
        profile=server/'home/.config/EgoSoft/X4/45841';profile.mkdir(parents=True)
        self.profile=self.root/'target';self.profile.mkdir()
        for directory in (profile,self.profile): (directory/'content.xml').write_text('<content/>')
        md=server/'extensions/x4_lan_lab/md';md.mkdir(parents=True)
        (md/'authority_checkpoint_marker.xml').write_bytes((ROOT/'src/authority/md/checkpoint_marker.xml').read_bytes())
        (md/'authority_identity_fixture.xml').write_bytes((ROOT/'tools/dev/authority_identity_fixture.xml').read_bytes())
        self.result_path=self.store_path.parent/'result.json'
        self.result={k:True for k in ('success','owned_cleanup_confirmed','helper_clean_exit',
            'simulated_client_disconnect','last_eof_observed','last_departure_pause_confirmed',
            'last_departure_checkpoint_confirmed','marker_changed','tcp_claim_used','tcp_participant_commands_used',
            'intermediate_checkpoint_confirmed','remaining_client_resumed',
            'native_server_and_client_resume_confirmed','native_server_and_client_pause_confirmed')}
        self.result.update(owned_processes_remaining=[],last_checkpoint_id=self.checkpoint.checkpoint_id,
                           last_checkpoint_sha256=self.checkpoint.sha256,server_state='paused',pending_operation=None)
        self.write_result()
        patched=patch.multiple(subject,DEFAULT_STORE=self.store_path,CHECKPOINT_ID=self.checkpoint.checkpoint_id,
            SHA256=self.checkpoint.sha256,SIZE=self.checkpoint.size,MARKER=MARKER)
        patched.start();self.addCleanup(patched.stop)

    def write_result(self): self.result_path.write_text(json.dumps(self.result))
    def verify(self): return subject.verify(self.store_path,self.checkpoint,self.profile)

    def test_exact_checkpoint_result_marker_and_scripts(self):
        data=self.verify()
        self.assertEqual(data,(ROOT/'tools/dev/authority_identity_fixture.xml').read_bytes())

    def test_failure_flags_identity_marker_and_result_are_strict(self):
        self.result['last_eof_observed']=False;self.write_result()
        with self.assertRaises(ValueError): self.verify()
        self.result['last_eof_observed']=True;self.result['last_checkpoint_sha256']='0'*64;self.write_result()
        with self.assertRaises(ValueError): self.verify()
        self.result['last_checkpoint_sha256']=self.checkpoint.sha256;self.write_result()
        with patch.object(subject,'MARKER','b'*32):
            with self.assertRaises(ValueError): self.verify()
        self.result_path.write_text('{"success":true,"success":true}')
        with self.assertRaises(ValueError): self.verify()

    def test_current_must_equal_confirmed(self):
        other=self.root/'other.gz';other.write_bytes(gzip.compress(XML.encode()))
        self.store.publish(other,marker=MARKER)
        with self.assertRaisesRegex(ValueError,'not confirmed'): self.verify()

    def test_profile_and_saved_script_must_match(self):
        (self.profile/'content.xml').write_text('<different/>')
        with self.assertRaisesRegex(ValueError,'configuration'): self.verify()
        (self.profile/'content.xml').write_text('<content/>')
        fixture=self.store_path.parent/'server/case/extensions/x4_lan_lab/md/authority_identity_fixture.xml'
        fixture.write_text('<changed/>')
        with self.assertRaisesRegex(ValueError,'script differs'): self.verify()

    def test_symlink_and_unexpected_script_refused(self):
        fixture=self.store_path.parent/'server/case/extensions/x4_lan_lab/md/authority_identity_fixture.xml'
        fixture.unlink();fixture.symlink_to(ROOT/'tools/dev/authority_identity_fixture.xml')
        with self.assertRaisesRegex(ValueError,'symlink'): self.verify()
        fixture.unlink();fixture.write_bytes((ROOT/'tools/dev/authority_identity_fixture.xml').read_bytes())
        (fixture.parent/'unknown.xml').write_text('<md/>')
        with self.assertRaisesRegex(ValueError,'unexpected'): self.verify()

    def test_only_fixed_store_accepted(self):
        with self.assertRaisesRegex(ValueError,'recorded TCP'): subject.verify(self.root,self.checkpoint,self.profile)


class RecoveryDispatchTest(unittest.TestCase):
    def test_default_legacy_verifier_is_unchanged(self):
        with patch.object(bridge.recovery,'verify_source') as old,patch.object(bridge.tcp_source,'verify') as new:
            self.assertIsNone(bridge.verify_selected_source('marked-bridge','store','checkpoint','profile'))
            old.assert_called_once_with('store','checkpoint','profile');new.assert_not_called()
            new.return_value=b'fixture'
            self.assertEqual(bridge.verify_selected_source('tcp-last-disconnect','store','checkpoint','profile'),b'fixture')
            with self.assertRaises(ValueError): bridge.verify_selected_source('unknown','store','checkpoint','profile')

    def test_fixture_install_is_exclusive_and_byte_exact(self):
        with tempfile.TemporaryDirectory() as d:
            case=Path(d);(case/'extensions/x4_lan_lab/md').mkdir(parents=True)
            target=bridge.install_saved_identity_fixture(case,b'<fixture/>')
            self.assertEqual(target.read_bytes(),b'<fixture/>')
            with self.assertRaises(FileExistsError): bridge.install_saved_identity_fixture(case,b'<different/>')
            self.assertEqual(target.read_bytes(),b'<fixture/>')


if __name__=='__main__': unittest.main()
