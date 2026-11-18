"""Read-only local replica binding contracts, no X4 start."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
class ReplicaMotionBinding(unittest.TestCase):
    def test_local_binding_correlation_staleness_and_identity(self):
        subprocess.run(['luajit','tests/authority_replica_motion_binding.lua'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=5)
    def test_x4_factory_fake_abi_rejects_local_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib=Path(tmp)/'fake.so'
            subprocess.run(['cc','-shared','-fPIC','-O2',str(ROOT/'tests/fixtures/replica_motion_binding_abi.c'),'-o',str(lib)],check=True,capture_output=True)
            for mode in ('zone','dock','pause','despawn'):
                with self.subTest(mode=mode):
                    subprocess.run(['luajit','tests/authority_replica_motion_binding_x4.lua'],cwd=ROOT,env=dict(os.environ,LD_PRELOAD=str(lib),TEST_BIND_FAILURE=mode),check=True,capture_output=True,text=True,timeout=5)
            for path_case in ('drive_forward','drive_backslash','unc','wrong_profile','case_mismatch','expected_wrong_profile'):
                with self.subTest(path_case=path_case):
                    subprocess.run(['luajit','tests/authority_replica_motion_binding_x4.lua'],cwd=ROOT,
                        env=dict(os.environ,LD_PRELOAD=str(lib),TEST_SAVE_PATH_CASE=path_case),check=True,capture_output=True,text=True,timeout=5)
    def test_md_bind_is_read_only_and_registry_scoped(self):
        root=ET.parse(ROOT/'tools/dev/authority_replica_motion_bind.xml').getroot()
        self.assertEqual(root.get('name'),'X4AuthorityReplicaMotionBind')
        self.assertEqual([c.get('name') for c in root.findall('./cues/cue')],['Bind'])
        text=ET.tostring(root,encoding='unicode')
        for required in ('State.$byship','State.$receipts','State.$epoch','State.$faulted','State.$pending','isoperational','isclass.ship','isclass.sector','dock.exists','isinternallystored','sector.macro.id','request_id'):
            self.assertIn(required,text)
        for node in root.findall('.//set_value'):self.assertTrue(node.get('name').startswith('$'))
        self.assertFalse(root.findall('.//create_ship'));self.assertFalse(root.findall('.//remove_value'))
        for node in root.findall('.//raise_lua_event'):self.assertIn('$r.$request_id',node.get('param'))
if __name__=='__main__':unittest.main()
