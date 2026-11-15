"""Bounded bridge save verification with fake native receipts; no X4."""
import socket
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
import authority_player_fixture_bridge as subject
from authority.checkpoints import Checkpoint

class FixtureBridgeTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        profile=Path(temp.name)/'45841';(profile/'save').mkdir(parents=True)
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.sock.bind(('127.0.0.1',0))
        self.addCleanup(self.sock.close)
        self.marker='b'*32;self.epoch='a'*32;self.fixture_epoch='c'*32
        self.cp=Checkpoint('checkpoint-'+'d'*32,profile/'save'/'save_009.xml.gz','e'*64,10,self.marker)
        self.store=SimpleNamespace(get=lambda _:self.cp)
        self.info=SimpleNamespace(checkpoint_id=self.cp.checkpoint_id,sha256=self.cp.sha256,size=self.cp.size,
            save_name=f'X4 Authority {self.epoch} 7')
        self.bridge=subject.PlayerFixtureBridge(enabled=True,sock=self.sock,peer=('127.0.0.1',1234),
            lease='f'*32,world_epoch=self.epoch,profile=profile,store=self.store,
            verify_checkpoint=lambda *args:self.info,marker_required=True,fixture_epoch=self.fixture_epoch)
        self.bridge._pending_save=7;self.bridge._pending_marker=self.marker

    def test_native_save_is_explicitly_disabled(self):
        with patch.object(self.bridge,'_request') as request:
            with self.assertRaisesRegex(RuntimeError,'live-readback gate'):self.bridge.save()
            request.assert_not_called()

    def test_distinct_test_marker_does_not_replace_archived_script(self):
        marker=ET.parse(ROOT/'tools/dev/authority_player_fixture_marker.xml').getroot()
        old=ET.parse(ROOT/'tools/dev/authority_checkpoint_marker.xml').getroot()
        self.assertEqual(marker.get('name'),'X4AuthorityPlayerFixtureMarker')
        self.assertEqual(old.get('name'),'X4AuthorityCheckpointMarker')
        self.assertIsNotNone(marker.find("./cues/cue[@name='MarkerState']"))
        self.assertEqual(marker.find("./cues/cue[@name='Store']").get('instantiate'),'true')
        self.assertIsNone(old.find("./cues/cue[@name='Store']").get('instantiate'))
        new_bytes=(ROOT/'tools/dev/authority_player_fixture_marker.xml').read_bytes()
        self.assertEqual(new_bytes.replace(b'X4AuthorityPlayerFixtureMarker',b'X4AuthorityCheckpointMarker'),
                         (ROOT/'src/authority/md/checkpoint_marker.xml').read_bytes())

    def test_fixture_verification_precedes_native_confirmation(self):
        events=[]
        def verify(cp,epoch,marker):
            events.append(('fixture',cp,epoch,marker))
            return {'saved_slots_checked':2,'saved_owner_class_sector_checked':True}
        def exchange(command,expected): events.append(('exchange',command,expected))
        with patch.object(subject.fixture,'verify',side_effect=verify), patch.object(self.bridge,'_exchange',side_effect=exchange):
            self.assertTrue(self.bridge.checkpoint_published(self.cp))
        self.assertEqual(events[0],('fixture',self.cp,self.fixture_epoch,self.marker))
        self.assertTrue(events[1][1].startswith('VERIFY|'))
        self.assertIsNone(self.bridge._pending_save)

    def test_invalid_fixture_never_confirms_and_keeps_bridge_poisoned(self):
        with patch.object(subject.fixture,'verify',return_value={'saved_slots_checked':1,
                'saved_owner_class_sector_checked':True}) as verify, patch.object(self.bridge,'_exchange') as exchange:
            with self.assertRaises(ValueError):self.bridge.checkpoint_published(self.cp)
            exchange.assert_not_called();self.assertTrue(self.bridge._poisoned)
            self.assertEqual(self.bridge._pending_save,7)
            with self.assertRaisesRegex(RuntimeError,'fenced'):self.bridge.checkpoint_published(self.cp)
            self.assertEqual(verify.call_count,1);exchange.assert_not_called()

    def test_verify_timeout_never_allows_retry(self):
        def timeout(*_):
            self.bridge._poisoned=True
            raise TimeoutError('uncertain VERIFY')
        with patch.object(subject.fixture,'verify',return_value={'saved_slots_checked':2,
                'saved_owner_class_sector_checked':True}) as verify, patch.object(self.bridge,'_exchange',side_effect=timeout) as exchange:
            with self.assertRaises(TimeoutError): self.bridge.checkpoint_published(self.cp)
            with self.assertRaisesRegex(RuntimeError,'fenced'):self.bridge.checkpoint_published(self.cp)
            self.assertEqual(verify.call_count,1);self.assertEqual(exchange.call_count,1)

    def test_mismatched_manifest_or_save_identity_never_confirms(self):
        self.info.sha256='0'*64
        with patch.object(subject.fixture,'verify') as verify,patch.object(self.bridge,'_exchange') as exchange:
            with self.assertRaises(ValueError):self.bridge.checkpoint_published(self.cp)
            verify.assert_not_called();exchange.assert_not_called()
            self.assertTrue(self.bridge._poisoned)

if __name__=='__main__':unittest.main()
