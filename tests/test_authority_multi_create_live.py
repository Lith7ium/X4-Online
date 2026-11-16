"""Offline scenario and private overlay checks; never launch X4."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/dev'),str(ROOT/'src')]
import authority_multi_create_live as m

class MultiCreateLive(unittest.TestCase):
    def ticket(self):
        return dict(world_epoch='a'*32,connection_handle=1,baseline_id=1,load_generation=1,
                    checkpoint_id=m.archive.CHECKPOINT_ID,sha256=m.archive.SHA256,attempt_id='b'*32,slot='save_009')
    def test_real_client_scenario(self):
        subprocess.run(['luajit','tests/authority_multi_create_scenario.lua'],cwd=ROOT,check=True,timeout=5)
    def test_private_installer_and_single_update_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            case=Path(tmp)/'case';profile=case/'profile';lab=case/'extensions/x4_lan_lab';ui=lab/'ui';md=lab/'md'
            ui.mkdir(parents=True);md.mkdir();(profile/'save').mkdir(parents=True)
            for p in (ui/'native_gate_snapshot.lua',md/'native_gate_battle.xml',ui/'config.lua',ui/'sha256.lua',
                      lab/'content.xml',profile/'content.xml',profile/'config.xml'):p.write_text('test')
            protected=m.install(case,profile,self.ticket(),1,'f'*32,30,[('sector_a',1),('sector_b',2)])
            owner=(ui/'authority_download_load_probe.lua').read_text()
            self.assertEqual(owner.count("SetScript('onUpdate'"),1)
            self.assertIn('X4LAN_MULTI_CREATE_RUN_TICK()',owner)
            self.assertIn('authority_multi_create_run=true',(ui/'config.lua').read_text())
            self.assertIn(md/'authority_multi_create_receiver.xml',protected)
            self.assertEqual((md/'authority_ship_registry.xml').read_bytes(),m.archive.saved_state_script('authority_ship_registry.xml').read_bytes())
            for name in m.UI:self.assertIn(ui/name,protected)
    def test_log_order_and_pause(self):
        ticket=self.ticket();fields='|'.join(str(ticket[k]) for k in m.base.load.FIELDS)
        load=m.base.load.TAG.decode();mark='[X4LAN] AUTH_MARKER load '
        prefix=[load+'load_requested|'+fields,mark+'INSPECTED '+m.archive.MARKER,load+'pause_observed|'+fields]
        sectors=[('sector_a',1),('sector_b',2)]
        rows=['ROW create 10055 sector_a','ROW create 10056 sector_b','ROW replay 10055 sector_a','ROW replay 10056 sector_b','DONE']
        encode=lambda lines:('\n'.join(lines)+'\n').encode()
        raw=encode(prefix+[m.TAG+r for r in rows]);r=m.validate(raw,ticket,1,sectors=sectors)
        self.assertEqual((r['created'],r['replayed']),(2,2));self.assertFalse(r['source_transfer_proven'])
        self.assertIsNone(m.validate(encode(prefix+[m.TAG+rows[0]]),ticket,1,partial=True,sectors=sectors))
        for lines in (prefix+[m.TAG+rows[1]],prefix+[m.TAG+r for r in rows[:-1]],
                      prefix[:2]+[m.TAG+rows[0]]+prefix[2:]+[m.TAG+r for r in rows[1:]],
                      prefix+[m.TAG+r for r in rows]+[m.TAG+rows[0]]):
            with self.assertRaises(ValueError):m.validate(encode(lines),ticket,1,sectors=sectors)
