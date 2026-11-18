"""Playback with actual Lua owner/buffer and fake native ABI; no X4 launch."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MotionPlaybackTests(unittest.TestCase):
    def test_real_buffer_and_controller_lifecycle(self):
        subprocess.run(['luajit', 'tests/authority_motion_playback.lua'], cwd=ROOT,
                       check=True, capture_output=True, text=True, timeout=5)

    def test_capture_clock_buffer_and_controller(self):
        subprocess.run(['luajit', 'tests/authority_motion_capture_playback.lua'], cwd=ROOT,
                       check=True, capture_output=True, text=True, timeout=5)

    def test_existing_owner_deferred_binding_and_stop(self):
        subprocess.run(['luajit', 'tests/authority_motion_playback_owner.lua'], cwd=ROOT,
                       check=True, capture_output=True, text=True, timeout=5)

    def test_saved_replica_control_prepares_and_releases_asynchronously(self):
        subprocess.run(['luajit', 'tests/authority_motion_replica_control_owner.lua'], cwd=ROOT,
                       check=True, capture_output=True, text=True, timeout=5)

    def test_native_factory_with_fake_x4_abi(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory)/'fake.so'
            subprocess.run(['cc', '-O2', '-shared', '-fPIC', 'tests/fixtures/saved_motion_apply_abi.c',
                            '-o', str(library)], cwd=ROOT, check=True, capture_output=True)
            subprocess.run(['luajit', 'tests/authority_motion_playback_x4.lua'], cwd=ROOT,
                           check=True, capture_output=True, text=True, timeout=5,
                           env=dict(os.environ, LD_PRELOAD=str(library)))
