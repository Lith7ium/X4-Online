"""Supervisor source-fence integration only; no X4 or network."""
import gzip
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev'),str(ROOT/'tests')]
from authority.checkpoints import CheckpointStore
import authority.checkpoints as checkpoints
import authority_recovered_loopback_server as supervisor
from authority_witness_source_guard import WitnessSourceGuard
from test_authority_witness_source_guard import MARKER, source_xml

class SupervisorWitnessFenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);(root/'checkpoints').mkdir()
        self.store=CheckpointStore(root/'checkpoints');source=root/'source.gz'
        source.write_bytes(gzip.compress(source_xml().encode()))
        self.cp=self.store.publish(source,marker=MARKER);self.store.confirm(self.cp)
        self.guard=WitnessSourceGuard(self.store,self.cp)
        self.script=root/'registry.xml';self.script.write_bytes(b'original')
        self.scripts={self.script:b'original'}

    def verify(self):
        return supervisor.verify_witness_source(self.store,self.cp,self.guard,self.scripts)

    def test_repeated_supervisor_fence_avoids_reparse_and_checks_source(self):
        with mock.patch.object(checkpoints,'_validate_save',side_effect=AssertionError('unexpected parse')):
            self.assertTrue(self.verify());self.assertTrue(self.verify())
            self.script.write_bytes(b'altered')
            with self.assertRaisesRegex(ValueError,'scripts changed'):self.verify()

    def test_pointer_change_is_refused_by_supervisor_fence(self):
        (self.store.directory/'CURRENT').write_bytes(b'{}')
        with self.assertRaises((ValueError,OSError)):self.verify()

    def test_guard_failure_is_never_ignored(self):
        with mock.patch.object(self.guard,'check',return_value=False):
            with self.assertRaisesRegex(ValueError,'did not confirm'):self.verify()
        with mock.patch.object(self.guard,'check',side_effect=ValueError('source changed')):
            with self.assertRaisesRegex(ValueError,'source changed'):self.verify()

    def test_create_path_keeps_original_full_validation_and_script_guard(self):
        with mock.patch.object(checkpoints,'_validate_save',wraps=checkpoints._validate_save) as full:
            self.assertTrue(supervisor.verify_witness_source(self.store,self.cp,None,self.scripts))
            self.assertGreaterEqual(full.call_count,1)
        self.script.write_bytes(b'altered')
        with self.assertRaisesRegex(ValueError,'scripts changed'):
            supervisor.verify_witness_source(self.store,self.cp,None,self.scripts)

if __name__=='__main__':unittest.main()
