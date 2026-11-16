"""Offline builder contract tests; no compiler or Windows runtime is invoked."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / 'src/native/build.py'
spec = importlib.util.spec_from_file_location('x4_native_build', SCRIPT)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class NativeBuildOutputTest(unittest.TestCase):
    def test_both_targets_are_published_to_explicit_new_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'artifacts'
            commands = []

            def compile_stub(command, *, check):
                self.assertTrue(check)
                commands.append(command)
                Path(command[command.index('-o') + 1]).write_bytes(b'build artifact')

            with patch.object(sys, 'argv', ['build.py', '--zig', '/compiler/zig', '--out', str(output)]), \
                 patch.object(builder.subprocess, 'run', side_effect=compile_stub):
                builder.main()
            self.assertEqual({p.name for p in output.iterdir()}, {'x4lan_net.so', 'x4lan_net_64.dll'})
            self.assertEqual([c[c.index('-target') + 1] for c in commands],
                             ['x86_64-linux-gnu.2.17', 'x86_64-windows-gnu'])
            self.assertTrue(all(p.read_bytes() == b'build artifact' for p in output.iterdir()))

    def test_existing_output_is_never_touched(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'artifacts'
            output.mkdir()
            sentinel = output / 'x4lan_net_64.dll'
            sentinel.write_bytes(b'keep')
            with patch.object(sys, 'argv', ['build.py', '--zig', '/compiler/zig', '--out', str(output)]), \
                 patch.object(builder.subprocess, 'run') as compile_stub, self.assertRaises(SystemExit):
                builder.main()
            compile_stub.assert_not_called()
            self.assertEqual(sentinel.read_bytes(), b'keep')

    def test_failed_compile_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'artifacts'
            with patch.object(sys, 'argv', ['build.py', '--zig', '/compiler/zig', '--out', str(output)]), \
                 patch.object(builder.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'zig')), \
                 self.assertRaises(subprocess.CalledProcessError):
                builder.main()
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
