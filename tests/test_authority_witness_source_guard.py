"""Offline cached source guard; uses tiny generated XML and no X4."""
import gzip
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev'),str(ROOT/'tests')]
from authority.checkpoints import CheckpointStore
import authority.checkpoints as checkpoints
import authority_witness_source_guard as subject
from test_authority_registry_witness_save_evidence import save

MARKER='b'*32

def source_xml():
    text=save().replace('<ref id="2" string="sealed"/>',
                        '<ref id="2" string="sealed"/><ref id="42" string="'+MARKER+'"/>')
    return text.replace('</md>', '<script name="X4AuthorityCheckpointMarker"><cue name="MarkerState"><vars>'
        '<value name="$marker" type="string" value="42"/><value name="$loaded" type="integer"/>'
        '</vars></cue></script></md>')

class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'store').mkdir();self.store=CheckpointStore(self.root/'store')
        path=self.root/'save.gz';path.write_bytes(gzip.compress(source_xml().encode()))
        self.cp=self.store.publish(path,marker=MARKER);self.store.confirm(self.cp)
        self.guard=subject.WitnessSourceGuard(self.store,self.cp)

    def test_initial_full_validation_and_cached_repeat_checks_hash_without_parsing(self):
        with mock.patch.object(checkpoints,'_validate_save',wraps=checkpoints._validate_save) as validation:
            another=subject.WitnessSourceGuard(self.store,self.cp)
            self.assertGreaterEqual(validation.call_count,2)
        with mock.patch.object(checkpoints,'_validate_save',side_effect=AssertionError('unexpected parse')), \
             mock.patch.object(subject.registry,'saved_status',side_effect=AssertionError('unexpected status parse')), \
             mock.patch.object(subject.witness,'verify',side_effect=AssertionError('unexpected witness parse')), \
             mock.patch.object(subject.hashlib,'sha256',wraps=subject.hashlib.sha256) as sha:
            self.assertTrue(another.check());self.assertTrue(another.check())
            self.assertGreaterEqual(sha.call_count,2)

    def test_pointer_or_manifest_changes_fail_closed(self):
        for name in ('CURRENT','CONFIRMED','manifest.json'):
            with self.subTest(name=name):
                if name=='manifest.json': path=self.cp.path.parent/name
                else: path=self.store.directory/name
                old=path.read_bytes();path.write_bytes(old+b' ')
                try:
                    with self.assertRaises((ValueError,OSError)):self.guard.check()
                finally:path.write_bytes(old)
                # Recreate guard because ctime/identity changes are intentionally fenced.
                self.guard=subject.WitnessSourceGuard(self.store,self.cp)

    def test_other_valid_current_pointer_is_rejected(self):
        source=self.root/'other.gz';source.write_bytes(gzip.compress(source_xml().encode()))
        other=self.store.publish(source,marker=MARKER)
        self.assertNotEqual(other.checkpoint_id,self.cp.checkpoint_id)
        with self.assertRaises((ValueError,OSError)):self.guard.check()

    def test_manifest_symlink_and_removed_confirmed_pointer_are_rejected(self):
        for relative in ('manifest.json','CONFIRMED'):
            with self.subTest(relative=relative):
                path=self.cp.path.parent/relative if relative=='manifest.json' else self.store.directory/relative
                original=path.read_bytes(); path.unlink()
                if relative=='manifest.json':
                    alternate=self.root/'manifest-copy';alternate.write_bytes(original);path.symlink_to(alternate)
                with self.assertRaises((ValueError,OSError)):self.guard.check()
                if path.is_symlink():path.unlink()
                path.write_bytes(original)
                self.guard=subject.WitnessSourceGuard(self.store,self.cp)

    def test_replaced_pointer_same_bytes_and_symlink_are_rejected(self):
        p=self.store.directory/'CURRENT';copy=p.read_bytes();new=self.root/'replacement';new.write_bytes(copy)
        os.replace(new,p)
        with self.assertRaises((ValueError,OSError)):self.guard.check()
        self.guard=subject.WitnessSourceGuard(self.store,self.cp)
        p.unlink();p.symlink_to(self.store.directory/'CONFIRMED')
        with self.assertRaises((ValueError,OSError)):self.guard.check()

    def test_same_size_save_mutation_with_restored_mtime_is_rejected(self):
        p=self.cp.path;st=p.stat();data=bytearray(p.read_bytes());data[len(data)//2]^=1
        p.write_bytes(data);os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns))
        with self.assertRaises((ValueError,OSError)):self.guard.check()

    def test_save_path_replaced_during_hash_is_rejected(self):
        original=subject._read_file; done=[False]
        def race(parent,name,**kwargs):
            result=original(parent,name,**kwargs)
            if name=='save.xml.gz' and not done[0]:
                done[0]=True;p=self.cp.path;replacement=self.root/'alternate'
                replacement.write_bytes(p.read_bytes());os.replace(replacement,p)
            return result
        with mock.patch.object(subject,'_read_file',side_effect=race):
            with self.assertRaises((ValueError,OSError)):self.guard.check()

    def test_save_mutates_after_hash_before_final_metadata_check(self):
        original=subject._read_file;manifest_reads=[0]
        def race(parent,name,**kwargs):
            result=original(parent,name,**kwargs)
            if name=='manifest.json':
                manifest_reads[0]+=1
                if manifest_reads[0]==2:
                    p=self.cp.path;data=bytearray(p.read_bytes());data[0]^=1;p.write_bytes(data)
            return result
        with mock.patch.object(subject,'_read_file',side_effect=race):
            with self.assertRaises((ValueError,OSError)):self.guard.check()

    def test_pointer_changes_during_hash_is_rejected(self):
        original=subject._read_file;done=[False]
        def race(parent,name,**kwargs):
            result=original(parent,name,**kwargs)
            if name=='save.xml.gz' and not done[0]:
                done[0]=True;p=self.store.directory/'CURRENT';p.write_bytes(p.read_bytes()+b' ')
            return result
        with mock.patch.object(subject,'_read_file',side_effect=race):
            with self.assertRaises((ValueError,OSError)):self.guard.check()

if __name__=='__main__':unittest.main()
