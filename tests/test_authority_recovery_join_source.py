"""Synthetic recovery-source provenance; no X4 or recorded archive access."""
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev'), str(ROOT/'tests')]
from authority.checkpoints import CheckpointStore
from test_authority_trusted_marker_load_session import XML, MARKER
import authority_recovery_join_source as subject


class RecoverySourceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name); self.root=root; self.store_path=root/'source/checkpoints'; self.store_path.mkdir(parents=True)
        source=root/'save.gz'; source.write_bytes(gzip.compress(XML.encode()))
        self.store=CheckpointStore(self.store_path); self.checkpoint=self.store.publish(source,marker=MARKER)
        self.store.confirm(self.checkpoint)
        case=self.store_path.parent/'case'; profile=case/'home/.config/EgoSoft/X4/45841'; profile.mkdir(parents=True)
        self.profile=root/'target'; self.profile.mkdir()
        for directory in (profile,self.profile): (directory/'content.xml').write_text('<content/>')
        self.md=case/'extensions/x4_lan_lab/md'; self.md.mkdir(parents=True)
        (self.md/'authority_checkpoint_marker.xml').write_bytes((ROOT/'src/authority/md/checkpoint_marker.xml').read_bytes())
        (self.md/'authority_identity_fixture.xml').write_bytes((ROOT/'tools/dev/authority_identity_fixture.xml').read_bytes())
        self.result_path=self.store_path.parent/'result.json'
        self.result={k:True for k in ('success','load_marker_observed','pause_observed','bridge_activated',
            'coordinator_paused','source_client_disconnect_simulated','saved_identity_fixture_preserved')}
        self.result.update(source_type='tcp-last-disconnect',source_checkpoint_id=subject.prior.CHECKPOINT_ID,
            source_sha256=subject.prior.SHA256,fresh_checkpoint_id=self.checkpoint.checkpoint_id,
            fresh_sha256=self.checkpoint.sha256,owned_processes_remaining=[])
        self.write_result()
        patched=patch.multiple(subject,DEFAULT_STORE=self.store_path,CHECKPOINT_ID=self.checkpoint.checkpoint_id,
            SHA256=self.checkpoint.sha256,SIZE=self.checkpoint.size,MARKER=MARKER)
        patched.start(); self.addCleanup(patched.stop)

    def write_result(self): self.result_path.write_text(json.dumps(self.result))
    def verify(self): return subject.verify(self.store_path,self.checkpoint,self.profile)

    def test_valid_fixture(self):
        self.assertEqual(self.verify(),(ROOT/'tools/dev/authority_identity_fixture.xml').read_bytes())

    def test_result_failures_and_wrong_identity(self):
        for key,value in (('pause_observed',False),('source_type','other'),('fresh_sha256','0'*64),
                          ('owned_processes_remaining',[1]),('cleanup_error','failed'),('cleanup_errors',[])):
            with self.subTest(key=key):
                old=dict(self.result); self.result[key]=value; self.write_result()
                with self.assertRaises(ValueError): self.verify()
                self.result=old
        self.write_result()
        with patch.object(subject,'MARKER','b'*32):
            with self.assertRaises(ValueError): self.verify()
        self.result_path.write_text('{"success":true,"success":true}')
        with self.assertRaises(ValueError): self.verify()

    def test_current_and_confirmed_must_match(self):
        other=self.root/'other.gz'; other.write_bytes(gzip.compress(XML.encode()))
        self.store.publish(other,marker=MARKER)
        with self.assertRaisesRegex(ValueError,'not confirmed'): self.verify()

    def test_profile_script_and_symlink_protection(self):
        (self.profile/'content.xml').write_text('<different/>')
        with self.assertRaisesRegex(ValueError,'configuration'): self.verify()
        (self.profile/'content.xml').write_text('<content/>')
        fixture=self.md/'authority_identity_fixture.xml'; fixture.write_text('<changed/>')
        with self.assertRaisesRegex(ValueError,'script differs'): self.verify()
        fixture.unlink(); fixture.symlink_to(ROOT/'tools/dev/authority_identity_fixture.xml')
        with self.assertRaisesRegex(ValueError,'symlink'): self.verify()

    def test_other_source_and_unexpected_saved_script_rejected(self):
        with self.assertRaisesRegex(ValueError,'recorded recovery'): subject.verify(self.root,self.checkpoint,self.profile)
        (self.md/'unexpected.xml').write_text('<md/>')
        with self.assertRaisesRegex(ValueError,'unexpected'): self.verify()


if __name__=='__main__': unittest.main()
