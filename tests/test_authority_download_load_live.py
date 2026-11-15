import gzip
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
from authority.checkpoints import CheckpointStore
from lockstep.launcher import joinfiles
import authority_download_load_live as experiment

class DownloadLoadTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('luajit'), 'LuaJIT required')
    def test_probe_uses_real_lua_barrier_across_reload(self):
        subprocess.run(['luajit', 'tests/authority_download_load_probe.lua'],cwd=ROOT,check=True)

    def test_coordinator_offer_download_stays_unadmitted(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'source').mkdir();(root/'published').mkdir()
            (root/'case/save').mkdir(parents=True)
            raw=root/'world.gz';raw.write_bytes(gzip.compress(b'<savegame><world/></savegame>'))
            source=CheckpointStore(root/'source').publish(raw)
            service=joinfiles.FileService('a'*32,slots=(1,)).start()
            try:
                world,ticket,staged=experiment.stage_download(service,CheckpointStore(root/'published'),source,root,root/'case')
                self.assertEqual(staged.read_bytes(),raw.read_bytes())
                self.assertEqual(ticket['sha256'],source.sha256)
                self.assertEqual(world.session.state,'paused')
                self.assertEqual(world.session.ready_players,())
                self.assertEqual(staged.stat().st_mode & 0o777,0o400)
            finally: service.close()

    def test_receipts_are_ordered_unique_and_bound_to_all_ticket_fields(self):
        ticket={'world_epoch':'epoch','connection_handle':1,'baseline_id':2,'load_generation':3,
                'checkpoint_id':'checkpoint-'+'a'*32,'sha256':'b'*64,'attempt_id':'c'*32,'slot':'save_009'}
        def row(event,t): return b'[X4LAN] AUTH_DOWNLOAD_LOAD '+(event+'|'+'|'.join(str(t[k]) for k in experiment.FIELDS)).encode()+b'\n'
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'log';watch=experiment.ReceiptWatch(path,ticket)
            path.write_bytes(row('load_requested',ticket));self.assertTrue(watch.poll());self.assertEqual(watch.stage,1)
            with path.open('ab') as f: f.write(row('pause_observed',ticket))
            self.assertTrue(watch.poll());self.assertEqual(watch.stage,2)
            with path.open('ab') as f: f.write(row('pause_observed',ticket))
            with self.assertRaises(ValueError):watch.poll()
            for field in experiment.FIELDS:
                changed=dict(ticket);changed[field]=str(changed[field])+'0'
                path.write_bytes(row('load_requested',changed));watch=experiment.ReceiptWatch(path,ticket)
                with self.assertRaises(ValueError):watch.poll()
            path.write_bytes(row('pause_observed',ticket));watch=experiment.ReceiptWatch(path,ticket)
            with self.assertRaises(ValueError):watch.poll()

if __name__=='__main__': unittest.main()
