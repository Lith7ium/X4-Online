"""Reject FIFOs in isolated checkpoint reads; no actual saves or X4."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


@unittest.skipUnless(hasattr(os, 'mkfifo') and getattr(os, 'O_NONBLOCK', 0),
                     'FIFO and nonblocking open required')
class StreamingFifoTests(unittest.TestCase):
    def test_fifo_is_rejected_without_blocking(self):
        # A process deadline makes a blocking-open regression safe to run.
        script = r'''
import gzip
import hashlib
import os
from pathlib import Path
import sys
import tempfile
from unittest import mock

sys.path.insert(0, sys.argv[1])
from authority.checkpoints import Checkpoint, CheckpointError, CheckpointStore
from authority.experimental_client_load import ExperimentalClientLoad
from authority.load_messages import Offer
from authority.marker_evidence import MarkerEvidenceError, verify_saved_marker
import authority.recovery as recovery

case = sys.argv[2]
marker = 'a' * 32
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    source = root / 'source.gz'
    marker_xml = ('<savegame><script><refs type="string"><ref id="42" string="' + marker +
        '"/></refs></script><md><script name="X4AuthorityCheckpointMarker">'
        '<cue name="MarkerState"><vars><value name="$marker" type="string" value="42"/>'
        '<value name="$loaded" type="integer"/></vars></cue></script></md></savegame>')
    source.write_bytes(gzip.compress(marker_xml.encode()))
    data = source.read_bytes()
    if case == 'marker':
        source.unlink()
        os.mkfifo(source)
        checkpoint = Checkpoint('checkpoint-' + 'b' * 32, source, hashlib.sha256(data).hexdigest(), len(data))
        try:
            verify_saved_marker(checkpoint, marker, script_name='X4AuthorityCheckpointMarker', cue_name='MarkerState')
        except MarkerEvidenceError:
            pass
        else:
            raise AssertionError('marker accepted FIFO')
    elif case == 'recovery':
        store_dir = root / 'store'
        store_dir.mkdir()
        store = CheckpointStore(store_dir)
        checkpoint = store.publish(source, marker=marker)
        store.confirm(checkpoint)
        profile = root / 'profile'
        profile.mkdir(mode=0o700)
        real_verify = recovery.verify_saved_marker
        def swap_after_marker(*args, **kwargs):
            result = real_verify(*args, **kwargs)
            checkpoint.path.unlink()
            os.mkfifo(checkpoint.path)
            return result
        with mock.patch.object(recovery, 'verify_saved_marker', side_effect=swap_after_marker):
            try:
                recovery.stage_confirmed_recovery(store, profile)
            except CheckpointError:
                pass
            else:
                raise AssertionError('recovery accepted replaced FIFO')
        assert list(profile.iterdir()) == [], 'recovery left a partial staged save'
    elif case == 'client':
        offer = Offer(world_epoch='epoch-1', connection_handle=1, baseline_id=2, load_generation=3,
                      attempt_id='c' * 32, checkpoint_id='checkpoint-' + 'b' * 32,
                      sha256=hashlib.sha256(data).hexdigest(), size=len(data), name='j1.xml.gz')
        client = ExperimentalClientLoad(enabled=True, offer=offer, expected_marker=marker)
        real_open = os.open
        swapped = []
        def swap_before_open(path, flags, *args, **kwargs):
            if path == source and not swapped:
                source.unlink()
                os.mkfifo(source)
                swapped.append(True)
            return real_open(path, flags, *args, **kwargs)
        with mock.patch.object(os, 'open', side_effect=swap_before_open):
            try:
                client.verify_staged(source)
            except ValueError:
                pass
            else:
                raise AssertionError('client accepted replaced FIFO')
        assert swapped, 'client did not reach the intended open'
        try:
            client.verify_staged(source)
        except ValueError:
            pass
        else:
            raise AssertionError('failed client was reusable')
'''
        source_dir = Path(__file__).resolve().parents[1] / 'src'
        for case in ('marker', 'recovery', 'client'):
            with self.subTest(case=case):
                result = subprocess.run(
                    [sys.executable, '-c', script, str(source_dir), case],
                    capture_output=True, text=True, timeout=5,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
