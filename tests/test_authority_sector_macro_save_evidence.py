"""Real synthetic save bytes for the offline sector-macro check; no X4."""
import gzip
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
from authority.checkpoints import CheckpointStore
import authority_sector_macro_save_evidence as subject


def save_xml(sectors):
    data=''.join('<component class="sector" id="%s" macro="%s"/>'%row for row in sectors)
    return ('<savegame><universe>'+data+'<component class="ship_s" id="[0x99]" macro="ship"/>'
            '</universe></savegame>').encode()

class SectorMacroSaveTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'checkpoints';self.path.mkdir()
        self.store=CheckpointStore(self.path)

    def check(self, rows, count=None):
        source=self.root/'save.gz';source.write_bytes(gzip.compress(save_xml(rows)))
        cp=self.store.publish(source);self.store.confirm(cp)
        with patch.object(subject.archive,'CHECKPOINT_ID',cp.checkpoint_id), \
             patch.object(subject.archive,'SHA256',cp.sha256),patch.object(subject.archive,'SIZE',cp.size), \
             patch.object(subject,'SAVED_SECTOR_COUNT',len(rows) if count is None else count):
            return subject.verify(self.path)

    def test_unique_saved_ids_and_macros_only(self):
        result=self.check([('[0x1]','cluster_a_macro'),('[0x2]','cluster_b_macro')])
        self.assertEqual(result['saved_sectors'],2)
        self.assertEqual(result['distinct_saved_sector_macros_casefolded'],2)
        self.assertFalse(result['runtime_macro_binding_proven'])
        self.assertFalse(result['cross_instance_frame_identity_proven'])
        self.assertFalse(result['general_uniqueness_proven'])

    def test_missing_duplicate_and_ambiguous_values_refused(self):
        for rows in ([('[0x1]','same'),('[0x2]','SAME')],
                     [('[0x1]','first'),('[0x01]','second')],
                     [('[0x0]','first')], [('[0x1]','')], [('[invalid]','first')]):
            with self.subTest(rows=rows),self.assertRaises(ValueError): self.check(rows)

    def test_wrong_count_and_unconfirmed_pointer_refused(self):
        with self.assertRaisesRegex(ValueError,'count'): self.check([('[0x1]','a')],count=2)
        cp=self.store.latest_confirmed()
        (self.path/'CONFIRMED').write_text('bad pointer')
        with patch.object(subject.archive,'CHECKPOINT_ID',cp.checkpoint_id):
            with self.assertRaisesRegex(ValueError,'not confirmed'): subject.verify(self.path)

if __name__=='__main__': unittest.main()
