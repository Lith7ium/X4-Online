"""Synthetic Linux child and network namespace; no X4 or profile access."""
import errno
import os
from pathlib import Path
import select
import shutil
import socket
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/dev'))
from authority_inherited_udp_guard import InheritedHostUDPGuard

CHILD = '''import os, select, socket, sys
fd = int(sys.argv[1])
endpoint = socket.socket(fileno=fd)
held = []
print("ready", flush=True)
for line in sys.stdin:
    if line.strip() == "duplicate":
        held.append(os.dup(fd))
    elif line.strip() == "replace":
        replacement = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        os.dup2(replacement.fileno(), fd)
        held.append(replacement)
    elif line.strip() == "send":
        endpoint.send(b"from child")
    elif line.strip() == "receive":
        if not select.select([endpoint], [], [], 5)[0]:
            raise RuntimeError("UDP receive timed out")
        print("received " + endpoint.recv(256).decode("ascii"), flush=True)
        continue
    print("done", flush=True)
'''


class InheritedHostUDPGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if (sys.platform != 'linux' or not hasattr(os, 'pidfd_open') or
                not hasattr(os, 'O_PATH') or not hasattr(socket, 'SO_REUSEPORT')):
            raise unittest.SkipTest('requires Linux pidfd, O_PATH, and SO_REUSEPORT support')
        if shutil.which('unshare') is None:
            raise unittest.SkipTest('requires unshare for a private user and network namespace')
        if not Path('/proc/thread-self/net/udp6').is_file():
            raise unittest.SkipTest('requires the Linux IPv6 UDP table for collision checks')
        try:
            pidfd = os.pidfd_open(os.getpid())
            os.close(pidfd)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                for option in (57, 71):
                    if len(probe.getsockopt(socket.SOL_SOCKET, option, 8)) != 8:
                        raise OSError('64-bit socket cookie unavailable')
            result = subprocess.run(
                ['unshare', '--user', '--map-root-user', '--net', 'true'],
                capture_output=True, text=True, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise unittest.SkipTest(f'namespace or socket-cookie prerequisite unavailable: {error}') from error
        if result.returncode != 0:
            raise unittest.SkipTest(f'private user/network namespace unavailable: {result.stderr.strip()}')

    def setUp(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.anchor = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(self.server.close)
        self.addCleanup(self.anchor.close)
        self.server.bind(('127.0.0.1', 0))
        self.anchor.bind(('127.0.0.1', 0))
        self.server.connect(self.anchor.getsockname())
        self.anchor.connect(self.server.getsockname())
        self.child = subprocess.Popen(
            ['unshare', '--user', '--map-root-user', '--net', sys.executable, '-u',
             '-c', CHILD, str(self.anchor.fileno())],
            pass_fds=(self.anchor.fileno(),), stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop_child)
        self.child_output = b''
        self.assertEqual(self.read_child_line(), 'ready',
                         'namespace child did not start successfully')
        pid = self.child.pid
        fields = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
        executable = (Path('/proc') / str(pid) / 'exe').stat()
        self.process = {'pid': pid, 'start_ticks': int(fields[19]),
                        'exe_dev': executable.st_dev, 'exe_ino': executable.st_ino}
        self.pidfd = os.pidfd_open(pid)
        self.addCleanup(os.close, self.pidfd)
        self.owner_live = True
        self.guard = InheritedHostUDPGuard(
            enabled=True, anchor=self.anchor, supervisor=self.server,
            process=self.process, process_pidfd=self.pidfd, child_fd=self.anchor.fileno(),
            owner_guard=lambda: self.owner_live)
        self.addCleanup(self.guard.close)

    def stop_child(self):
        if self.child.poll() is None:
            self.child.terminate()
        try:
            self.child.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            self.child.kill()
            self.child.communicate(timeout=5)

    def child_command(self, command):
        self.child.stdin.write(command + '\n')
        self.child.stdin.flush()
        self.assertEqual(self.read_child_line(), 'done')

    def read_child_line(self):
        deadline = time.monotonic() + 10
        while b'\n' not in self.child_output:
            remaining = deadline - time.monotonic()
            self.assertGreater(remaining, 0, 'namespace child response timed out')
            readable, _, _ = select.select([self.child.stdout], [], [], remaining)
            self.assertTrue(readable, 'namespace child response timed out')
            chunk = os.read(self.child.stdout.fileno(), 256)
            self.assertTrue(chunk, 'namespace child closed its output')
            self.child_output += chunk
            self.assertLessEqual(len(self.child_output), 1024, 'namespace child output too long')
        line, self.child_output = self.child_output.split(b'\n', 1)
        return line.decode('ascii').strip()

    def test_host_socket_remains_visible_across_network_namespaces(self):
        self.assertNotEqual(os.stat('/proc/self/ns/net').st_ino,
                            os.stat(f'/proc/{self.child.pid}/ns/net').st_ino)
        self.assertTrue(self.guard.check())
        self.assertTrue(self.guard.check())

    def test_udp_data_round_trip_across_network_namespaces(self):
        self.assertTrue(self.guard.check())
        self.child_command('send')
        self.server.settimeout(5)
        self.assertEqual(self.server.recv(256), b'from child')
        self.server.send(b'from supervisor')
        self.child.stdin.write('receive\n')
        self.child.stdin.flush()
        self.assertEqual(self.read_child_line(), 'received from supervisor')
        self.assertTrue(self.guard.check())

    def test_duplicate_child_descriptor_is_rejected(self):
        self.child_command('duplicate')
        with self.assertRaisesRegex(RuntimeError, 'descriptor identity or exclusivity'):
            self.guard.check()

    def test_replaced_child_descriptor_is_rejected(self):
        self.child_command('replace')
        with self.assertRaisesRegex(RuntimeError, 'descriptor identity or exclusivity'):
            self.guard.check()

    def test_reconnected_anchor_is_rejected(self):
        other = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(other.close)
        other.bind(('127.0.0.1', 0))
        self.anchor.connect(other.getsockname())
        with self.assertRaisesRegex(RuntimeError, 'identity, peer, or exclusivity changed'):
            self.guard.check()

    def test_replaced_supervisor_socket_is_rejected(self):
        address = self.server.getsockname()
        self.server.close()
        replacement = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(replacement.close)
        replacement.bind(address)
        replacement.connect(self.anchor.getsockname())
        with self.assertRaisesRegex(RuntimeError, 'supervisor UDP socket closed'):
            self.guard.check()
        with self.assertRaisesRegex(RuntimeError, 'guard closed'):
            self.guard.check()

    def test_replaced_supervisor_descriptor_is_rejected(self):
        replacement = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(replacement.close)
        replacement.bind(('127.0.0.1', 0))
        replacement.connect(self.anchor.getsockname())
        os.dup2(replacement.fileno(), self.server.fileno())
        with self.assertRaisesRegex(RuntimeError, 'supervisor UDP socket identity'):
            self.guard.check()

    def test_competing_flow_is_rejected_even_after_reuse_is_disabled(self):
        self.anchor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        competitor = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(competitor.close)
        competitor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        competitor.bind(self.anchor.getsockname())
        competitor.connect(self.server.getsockname())
        self.anchor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        with self.assertRaisesRegex(RuntimeError, 'competing socket'):
            self.guard.check()

    def assert_competing_ipv6_flow_rejected(self, local_socket, remote_socket):
        try:
            competitor = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
            self.addCleanup(competitor.close)
            competitor.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            local_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            competitor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            competitor.bind(('::ffff:127.0.0.1', local_socket.getsockname()[1]))
            competitor.connect(('::ffff:127.0.0.1', remote_socket.getsockname()[1]))
        except OSError as error:
            if error.errno in (errno.EAFNOSUPPORT, errno.EADDRNOTAVAIL,
                               errno.EPROTONOSUPPORT, errno.ENOPROTOOPT):
                self.skipTest(f'IPv4-mapped IPv6 socket unavailable: {error}')
            raise
        local_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        with self.assertRaisesRegex(RuntimeError, 'competing IPv6 socket'):
            self.guard.check()

    def test_competing_ipv6_at_inherited_endpoint_is_rejected(self):
        self.assert_competing_ipv6_flow_rejected(self.anchor, self.server)

    def test_competing_ipv6_at_supervisor_endpoint_is_rejected(self):
        self.assert_competing_ipv6_flow_rejected(self.server, self.anchor)

    def test_reuse_option_is_rejected(self):
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        with self.assertRaisesRegex(RuntimeError, 'supervisor UDP socket identity, peer, or exclusivity changed'):
            self.guard.check()

    def test_external_owner_failure_is_rejected(self):
        self.owner_live = False
        with self.assertRaisesRegex(RuntimeError, 'ownership changed'):
            self.guard.check()
        self.owner_live = True
        with self.assertRaisesRegex(RuntimeError, 'guard closed'):
            self.guard.check()

    def test_process_exit_is_rejected(self):
        self.child.terminate()
        self.child.wait(timeout=5)
        with self.assertRaisesRegex(RuntimeError, 'pidfd'):
            self.guard.check()

    def test_wrong_descriptor_and_disabled_mode_are_rejected(self):
        params = dict(anchor=self.anchor, supervisor=self.server,
                      process=self.process, process_pidfd=self.pidfd,
                      child_fd=self.anchor.fileno(), owner_guard=lambda: True)
        with self.assertRaises(ValueError):
            InheritedHostUDPGuard(enabled=False, **params)
        params['child_fd'] = self.anchor.fileno() + 1000
        with self.assertRaisesRegex(RuntimeError, 'descriptor identity or exclusivity'):
            InheritedHostUDPGuard(enabled=True, **params)

    def test_wrong_pidfd_is_rejected(self):
        wrong_pidfd = os.pidfd_open(os.getpid())
        self.addCleanup(os.close, wrong_pidfd)
        with self.assertRaisesRegex(RuntimeError, 'pidfd changed'):
            InheritedHostUDPGuard(
                enabled=True, anchor=self.anchor, supervisor=self.server,
                process=self.process, process_pidfd=wrong_pidfd,
                child_fd=self.anchor.fileno(), owner_guard=lambda: True)


if __name__ == '__main__':
    unittest.main()
