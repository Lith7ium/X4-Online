"""One-shot local writer and owner use fake X4 ABI; no native X4 process."""
from pathlib import Path
import os, subprocess, tempfile, unittest
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
class SavedMotionApply(unittest.TestCase):
    def test_owner_and_writer_fences(self):
        subprocess.run(['luajit','tests/authority_saved_motion_apply.lua'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)
    def test_x4_abi_position_and_radian_conversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            abi=Path(tmp)/'fake.so'
            subprocess.run(['cc','-O2','-shared','-fPIC','tests/fixtures/saved_motion_apply_abi.c','-o',str(abi)],cwd=ROOT,check=True,capture_output=True)
            for script in ('authority_saved_motion_apply_x4.lua','authority_saved_motion_apply_full_x4.lua',
                           'authority_saved_motion_apply_recovery_x4.lua'):
                with self.subTest(script=script):
                    subprocess.run(['luajit','tests/'+script],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5,env=dict(os.environ,LD_PRELOAD=str(abi)))

    def test_md_recovery_fixture_is_explicit_and_epoch_pinned(self):
        root=ET.parse(ROOT/'tools/dev/authority_saved_motion_apply.xml').getroot()
        recovery=[item for item in root.iter('do_elseif') if "'recovery_enh_870'" in item.get('value','')]
        self.assertEqual(len(recovery),1)
        self.assertIn("$r.$epoch == '4ba7be438ebb04ec5bb85fdb95b5a488'",recovery[0].get('value'))
        self.assertEqual(recovery[0].find('find_sector').get('macro'),'macro.cluster_06_sector001_macro')
        identity=recovery[0].find('do_if').get('value')
        for expected in ('ENH-870','ship_arg_m_trans_container_02_b_macro','antigone'):
            self.assertIn(expected,identity)
