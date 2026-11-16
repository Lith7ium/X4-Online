"""Synthetic local owner integration; no X4 or network start."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class SourceSingle(unittest.TestCase):
    def test_held_source_event_waits_for_clients_and_actual_md_ack(self):
        subprocess.run(['luajit','tests/authority_source_single_job_owner.lua'],cwd=ROOT,
                       check=True,capture_output=True,text=True,timeout=5)
    def test_two_fifo_heads_wait_for_per_event_rearm(self):
        subprocess.run(['luajit','tests/authority_source_multi_job_owner.lua'],cwd=ROOT,
                       check=True,capture_output=True,text=True,timeout=5)
    def test_continuous_waits_for_window_and_empty_snapshot(self):
        for scenario in ('continuous', 'empty'):
            with self.subTest(scenario=scenario):
                subprocess.run(['luajit','tests/authority_source_multi_job_owner.lua',scenario],cwd=ROOT,
                               check=True,capture_output=True,text=True,timeout=5)
    def test_overflow_and_changed_actor_fail_without_next_ack(self):
        for scenario in ('overflow','actor','known'):
            with self.subTest(scenario=scenario):
                subprocess.run(['luajit','tests/authority_source_multi_job_owner.lua',scenario],cwd=ROOT,
                               check=True,capture_output=True,text=True,timeout=5)
    def test_running_guard_and_rearm_with_fake_x4_abi(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib=Path(tmp)/'fake.so'
            subprocess.run(['cc','-shared','-fPIC','-O2',str(ROOT/'tests/fixtures/multi_create_running_owner_abi.c'),
                            '-o',str(lib)],check=True,capture_output=True)
            subprocess.run(['luajit','tests/authority_source_single_job_x4_fake.lua'],cwd=ROOT,
                           env=dict(os.environ,LD_PRELOAD=str(lib)),check=True,capture_output=True,text=True,timeout=5)
if __name__=='__main__': unittest.main()
