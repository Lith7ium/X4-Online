"""Synthetic runner and Lua callback checks; no X4 process is started."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('sector_live',ROOT/'tools/dev/authority_sector_reference_live.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)


class SectorLiveTest(unittest.TestCase):
    def test_private_overlay_gates_both_phases_without_identity_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            for phase in ('save','load'):
                case=Path(tmp)/phase;lab=case/'extensions/x4_lan_lab';ui=lab/'ui'
                ui.mkdir(parents=True);(lab/'md').mkdir()
                (ui/'config.lua').write_text('X4LAN_CONFIG = {}\n')
                filename='authority_world_bridge_probe.lua' if phase=='save' else 'authority_download_load_probe.lua'
                hook=' if not started and now-loaded_at>=3 then\n' if phase=='save' else " elseif state=='observing' then\n"
                if phase=='save': hook+=' local ok,reason=bridge:update();assert(ok,reason)\n'
                (ui/filename).write_text(hook)
                (lab/'ui.xml').write_text('    <file name="ui/'+filename+'" />\n')
                M.inject(case,phase,'a'*32,'b'*32)
                text=(ui/filename).read_text();manifest=(lab/'ui.xml').read_text();config=(ui/'config.lua').read_text()
                self.assertLess(text.index('X4LAN_AUTHORITY_MARKER_READY'),text.index('X4LAN_AUTHORITY_SECTOR_READY'))
                self.assertIn('authority_sector_reference_probe.lua',manifest)
                if phase=='save': self.assertLess(text.index('X4LAN_AUTHORITY_SECTOR_ENSURE_PAUSED'),text.index('bridge:update()'))
                self.assertFalse((lab/'md/authority_identity_fixture.xml').exists())
                self.assertEqual('authority_marker="' in config,phase=='save')

    def test_receipt_fails_on_duplicate_or_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'log';line='[X4LAN] AUTH_SECTOR save VERIFIED '+'a'*32+' slots=2\n'
            path.write_text(line);M.observations(path,'save','a'*32)
            for text in (line+line,line+'[X4LAN] AUTH_SECTOR save ERROR pause_lost\n',''):
                path.write_text(text)
                with self.assertRaises(ValueError): M.observations(path,'save','a'*32)

    def test_marker_failure_marks_runner_failed_and_restores_hooks(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'result'
            def fake_run(_):
                out.mkdir()
                for side in ('server','client'):
                    log=out/side/'case/home/.config/EgoSoft/X4/45841/engine-output.log'
                    log.parent.mkdir(parents=True);log.write_text('synthetic')
                M.base.offer_and_download()
                return {'success':True}
            def fake_transfer(): return ({'sha256':'x'},None)
            with patch.object(M.base.snapshot,'output_path',return_value=out), \
                 patch.object(M.base,'run',side_effect=fake_run), \
                 patch.object(M.base,'offer_and_download',side_effect=fake_transfer) as transfer, \
                 patch.object(M,'observations'), \
                 patch.object(M.marker,'verify_receipts',side_effect=ValueError('marker mismatch')):
                result=M.run(types.SimpleNamespace(out=out))
                self.assertIs(M.base.offer_and_download,transfer)
            self.assertFalse(result['success']);self.assertIn('marker mismatch',result['error'])

    @unittest.skipUnless(shutil.which('luajit'),'LuaJIT required')
    def test_probe_callbacks_and_pause_loss(self):
        for mode in ('save','load','pause-loss'):
            with self.subTest(mode=mode):
                subprocess.run(['luajit','tests/authority_sector_reference_probe.lua',mode],cwd=ROOT,
                               check=True,capture_output=True,text=True,timeout=5)


if __name__=='__main__': unittest.main()
