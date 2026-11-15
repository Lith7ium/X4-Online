"""Synthetic checks for the restart harness; no X4 process is started."""
import gzip
import json
from pathlib import Path
import sys
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools/dev')]
from authority.checkpoints import CheckpointStore
import authority_recovery_live as recovery


class RecoveryLiveTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("luajit"), "LuaJIT required")
    def test_probe_reload_waits_for_marker_before_pause(self):
        subprocess.run(["luajit", "tests/authority_recovery_probe.lua"], cwd=ROOT, check=True)

    def test_receipts_require_request_matching_marker_and_pause_in_order(self):
        marker='a'*32
        rows=[b'[X4LAN] AUTH_RECOVERY REQUEST\n',
              b'[X4LAN] AUTH_MARKER load INSPECTED '+marker.encode()+b'\n',
              b'[X4LAN] AUTH_RECOVERY PAUSED\n']
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'log';watch=recovery.RecoveryWatch(path,marker)
            path.write_bytes(rows[0]);self.assertTrue(watch.poll());self.assertEqual(watch.stage,1)
            with path.open('ab') as out: out.write(rows[1]+rows[2])
            self.assertTrue(watch.poll());self.assertEqual(watch.stage,3)
            with path.open('ab') as out: out.write(rows[2])
            with self.assertRaises(ValueError): watch.poll()
            for bad in ([rows[1],rows[0],rows[2]], [rows[0],rows[1].replace(b'a'*32,b'b'*32),rows[2]],
                        [rows[0],b'[X4LAN] AUTH_MARKER load ERROR\n']):
                path.write_bytes(b''.join(bad));watch=recovery.RecoveryWatch(path,marker)
                with self.assertRaises(ValueError): watch.poll()

    def test_source_requires_exact_confirmed_last_departure_and_matching_extensions(self):
        with tempfile.TemporaryDirectory() as d:
            origin=Path(d);directory=origin/'checkpoints';directory.mkdir()
            source=origin/'save.gz';source.write_bytes(gzip.compress(b'<savegame/>'))
            store=CheckpointStore(directory);checkpoint=store.publish(source,marker='a'*32);store.confirm(checkpoint)
            source_profile=origin/'case/home/.config/EgoSoft/X4/45841';source_profile.mkdir(parents=True)
            profile=origin/'new-profile';profile.mkdir()
            for folder in (source_profile,profile): (folder/'content.xml').write_text('<content/>')
            md=origin/'case/extensions/x4_lan_lab/md';md.mkdir(parents=True)
            md.joinpath('authority_checkpoint_marker.xml').write_bytes((ROOT/'src/authority/md/checkpoint_marker.xml').read_bytes())
            result={'success':True,'marked_saves_checked':True,'owned_processes_remaining':[],
                    'lifecycle':{'last_departure_checkpoint':{'checkpoint_id':checkpoint.checkpoint_id,'sha256':checkpoint.sha256}}}
            result_path=origin/'result.json';result_path.write_text(json.dumps(result))
            recovery.verify_source(directory,checkpoint,profile)
            result['lifecycle']['last_departure_checkpoint']['sha256']='0'*64
            result_path.write_text(json.dumps(result))
            with self.assertRaises(ValueError): recovery.verify_source(directory,checkpoint,profile)
            result['lifecycle']['last_departure_checkpoint']['sha256']=checkpoint.sha256
            result_path.write_text(json.dumps(result));(profile/'content.xml').write_text('<other/>')
            with self.assertRaises(ValueError): recovery.verify_source(directory,checkpoint,profile)


if __name__=='__main__': unittest.main()
