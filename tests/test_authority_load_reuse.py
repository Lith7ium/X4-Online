"""Synthetic origin checks for loading the last same-slot reuse checkpoint; no X4."""
from decimal import Decimal
import gzip
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/dev'))
import authority_load_live as load
from authority.checkpoints import CheckpointStore

class LoadReuseTests(unittest.TestCase):
    def make_source(self, root, *, names=None, times=None):
        origin=root/'source';epoch='a'*32
        profile=root/'destination';profile.mkdir()
        (profile/'content.xml').write_text('<content/>')
        source_profile=origin/'case/home/.config/EgoSoft/X4/45841';source_profile.mkdir(parents=True)
        (source_profile/'content.xml').write_text('<content/>')
        (source_profile/'engine-output.log').write_text(''.join('[X4LAN] '+m+'\n' for m in load.REUSE_MARKERS))
        config=origin/'case/extensions/x4_lan_lab/ui/config.lua';config.parent.mkdir(parents=True)
        config.write_text('authority_control_lease="redacted", authority_cycle_id="'+epoch+'"')
        times=times or (10,20,30)
        names=names or tuple(f'X4 Authority {epoch} {3*c-1}' for c in (1,2,3))
        rows=[];checkpoints=[]
        for cycle in (1,2,3):
            directory=origin/'checkpoints'/f'cycle-{cycle}';directory.mkdir(parents=True)
            save=root/f'save-{cycle}.gz'
            save.write_bytes(gzip.compress((f'<savegame><info><save name="{names[cycle-1]}"/>'
                                           f'<game time="{times[cycle-1]}"/></info></savegame>').encode()))
            checkpoint=CheckpointStore(directory).publish(save);checkpoints.append(checkpoint)
            rows.append({'cycle':cycle,'checkpoint_id':checkpoint.checkpoint_id,'sha256':checkpoint.sha256,
                         'size':checkpoint.size,'game_time':str(times[cycle-1]),'file_verified':True})
        result={'success':True,'resume_confirmed':True,'owned_processes_remaining':[],'cycles':rows}
        (origin/'result.json').write_text(json.dumps(result))
        return origin,checkpoints,profile

    def test_stage_last_verified_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            origin,checkpoints,profile=self.make_source(Path(tmp))
            store_dir=origin/'checkpoints/cycle-3';(profile/'save').mkdir()
            checkpoint,target=load.stage_checkpoint(CheckpointStore(store_dir),checkpoints[2].checkpoint_id,profile)
            self.assertEqual(load.verify_origin(store_dir,checkpoint,profile),Decimal('30'))
            self.assertEqual(load.live.sha(target),checkpoint.sha256)
            for cycle in (1,2):
                with self.assertRaises(ValueError):
                    load.verify_origin(origin/'checkpoints'/f'cycle-{cycle}',checkpoints[cycle-1],profile)

    def test_each_cycle_requires_matching_evidence(self):
        for index in range(3):
            for key,value in (('checkpoint_id','checkpoint-'+'0'*32),('sha256','0'*64),('size',True),
                              ('game_time','0'),('file_verified',False),('cycle',True)):
                with self.subTest(index=index,key=key), tempfile.TemporaryDirectory() as tmp:
                    origin,checkpoints,profile=self.make_source(Path(tmp))
                    path=origin/'result.json';result=json.loads(path.read_text());result['cycles'][index][key]=value
                    path.write_text(json.dumps(result))
                    with self.assertRaises(ValueError):
                        load.verify_origin(origin/'checkpoints/cycle-3',checkpoints[2],profile)

    def test_wrong_title_or_nonadvancing_time_in_any_checkpoint(self):
        for index in range(3):
            names=[f'X4 Authority {"a"*32} {3*c-1}' for c in (1,2,3)];names[index]='wrong title'
            with self.subTest(wrong_title=index), tempfile.TemporaryDirectory() as tmp:
                origin,checkpoints,profile=self.make_source(Path(tmp),names=names)
                with self.assertRaises(ValueError):
                    load.verify_origin(origin/'checkpoints/cycle-3',checkpoints[2],profile)
        for times in ((10,10,30),(10,20,19)):
            with self.subTest(times=times), tempfile.TemporaryDirectory() as tmp:
                origin,checkpoints,profile=self.make_source(Path(tmp),times=times)
                with self.assertRaises(ValueError):
                    load.verify_origin(origin/'checkpoints/cycle-3',checkpoints[2],profile)

    def test_incomplete_or_invalid_source_rejected(self):
        for mutation in ('missing_store','missing_log','reordered_log','duplicate_log','identity','content','result'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                origin,checkpoints,profile=self.make_source(Path(tmp))
                log=origin/'case/home/.config/EgoSoft/X4/45841/engine-output.log'
                if mutation=='missing_store': shutil.rmtree(origin/'checkpoints/cycle-2')
                elif mutation=='missing_log': log.unlink()
                elif mutation=='reordered_log': log.write_text(''.join('[X4LAN] '+m+'\n' for m in reversed(load.REUSE_MARKERS)))
                elif mutation=='duplicate_log': log.write_text(log.read_text()+'[X4LAN] '+load.REUSE_MARKERS[-1]+'\n')
                elif mutation=='identity': (origin/'case/extensions/x4_lan_lab/ui/config.lua').write_text('authority_cycle_id="'+'b'*32+'"')
                elif mutation=='content': (profile/'content.xml').write_text('<changed/>')
                else:
                    path=origin/'result.json';result=json.loads(path.read_text());result['owned_processes_remaining']=[1];path.write_text(json.dumps(result))
                with self.assertRaises(ValueError):
                    load.verify_origin(origin/'checkpoints/cycle-3',checkpoints[2],profile)

if __name__=='__main__': unittest.main()
