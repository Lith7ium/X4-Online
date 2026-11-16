"""Fake ABI and private setup checks only; no native X4 starts."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'src')]
import authority_multi_create_running_live as m

class Running(unittest.TestCase):
    def ticket(self):
        return dict(world_epoch='a'*32,connection_handle=1,baseline_id=1,load_generation=1,
                    checkpoint_id=m.archive.CHECKPOINT_ID,sha256=m.archive.SHA256,attempt_id='b'*32,slot='save_009')
    def test_owner_with_real_client_and_fake_abi(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib=Path(tmp)/'fake.so'
            subprocess.run(['cc','-shared','-fPIC','-O2',str(ROOT/'tests/fixtures/multi_create_running_owner_abi.c'),'-o',str(lib)],check=True,capture_output=True)
            for real in ('0','1'):
                subprocess.run(['luajit','tests/authority_multi_create_running_owner.lua'],cwd=ROOT,
                               env=dict(os.environ,LD_PRELOAD=str(lib),RUNNING_REAL_INSPECTOR=real),
                               check=True,capture_output=True,text=True,timeout=5)
    def test_installer_replaces_only_owner_and_stays_default_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=Path(tmp)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
            ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
            for p in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',
                      lab/'content.xml',profile/'content.xml',profile/'config.xml'):p.write_text('test')
            files=m.install(case,profile,self.ticket(),1,'f'*32,30,[('sector_a',41),('sector_b',53)])
            self.assertIn('authority_multi_create_running=true',(ui/'config.lua').read_text())
            self.assertEqual((ui/'authority_multi_create_run.lua').read_text(),(ROOT/'tools/dev/authority_multi_create_running_run.lua').read_text())
            self.assertIn(ui/'authority_multi_create_run.lua',files)
            self.assertEqual((ui/'authority_download_load_probe.lua').read_text().count("SetScript('onUpdate'"),1)
    def test_progress_and_order_are_required(self):
        t=self.ticket();fields='|'.join(str(t[k]) for k in m.base.load.FIELDS);load=m.base.load.TAG.decode()
        prefix=[load+'load_requested|'+fields,'[X4LAN] AUTH_MARKER load INSPECTED '+m.archive.MARKER,load+'pause_observed|'+fields]
        rows=['RUNNING 100 101','ROW create 10055 sector_a 102','DONE 103'];sectors=[('sector_a',41),('sector_b',53)]
        encode=lambda x:('\n'.join(x)+'\n').encode()
        ok=m.validate(encode(prefix+[m.TAG+x for x in rows]),t,1,sectors=sectors)
        self.assertEqual(ok['created'],1);self.assertFalse(ok['uninterrupted_running_proven'])
        self.assertIsNone(m.validate(encode(prefix+[m.TAG+rows[0]]),t,1,partial=True,sectors=sectors))
        for values in (['RUNNING 100 100',*rows[1:]], [rows[0],'ROW create 10055 sector_a 100',rows[2]],
                       [rows[0],rows[1],'DONE 102'],[rows[0],rows[1],rows[2],rows[2]]):
            with self.assertRaises(ValueError):m.validate(encode(prefix+[m.TAG+x for x in values]),t,1,sectors=sectors)
