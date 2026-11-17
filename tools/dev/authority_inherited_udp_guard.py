"""Sample an inherited host-network UDP endpoint owned by a diagnostic child.

This optional Linux-only guard does not launch a process or transfer a socket.
The supervisor must already own and pin the child, create/connect the socket in
its current network namespace, pass one FD to the child, and retain the anchor
and supervisor sockets until this guard is closed. The child must not duplicate,
pass on, reconnect, or replace that FD. The caller must serialize the guard with its UDP
operations and fence the entire session after a failure. These are point-in-time
checks, not proof that the child cannot change a descriptor after a check.
"""
import os
from pathlib import Path
import select
import socket
import sys

from authority_tcp_native_worker import check_process

# Linux socket options return 64-bit kernel cookies; Python may not expose names.
_SO_COOKIE = 57
_SO_NETNS_COOKIE = 71


def _identity(fd):
    stat = os.fstat(fd)
    return stat.st_dev, stat.st_ino


def _cookie(sock, option):
    raw = sock.getsockopt(socket.SOL_SOCKET, option, 8)
    if len(raw) != 8:
        raise RuntimeError('socket cookie unavailable')
    return int.from_bytes(raw, byteorder=sys.byteorder)


def _pidfd_pid(fd):
    if os.readlink(f'/proc/self/fd/{fd}') != 'anon_inode:[pidfd]':
        raise RuntimeError('process handle is not a pidfd')
    fields = [line.split(':', 1)[1].strip()
              for line in Path(f'/proc/self/fdinfo/{fd}').read_text().splitlines()
              if line.startswith('Pid:')]
    if len(fields) != 1 or not fields[0].isdigit():
        raise RuntimeError('live pidfd unavailable')
    return int(fields[0])


def _ipv4_udp(sock):
    return (type(sock) is socket.socket and sock.family == socket.AF_INET and
            sock.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) == socket.SOCK_DGRAM)


class InheritedHostUDPGuard:
    """Opt-in sampled guard; all endpoint and ownership assumptions are external.

    ``anchor`` is a retained duplicate of the child's connected UDP endpoint,
    used solely for verification. ``supervisor`` is the connected peer socket.
    The caller owns both sockets and the original pidfd. This object duplicates
    the pidfd and pins the current host net namespace until ``close``.
    """
    def __init__(self, *, enabled, anchor, supervisor, process, process_pidfd,
                 child_fd, owner_guard):
        if (enabled is not True or not _ipv4_udp(anchor) or not _ipv4_udp(supervisor) or
                type(process) is not dict or type(process_pidfd) is not int or
                process_pidfd < 0 or type(child_fd) is not int or child_fd < 0 or
                not callable(owner_guard)):
            raise ValueError('invalid inherited host UDP guard')
        self._pidfd = None
        self._netns_fd = None
        self._anchor = anchor
        self._supervisor = supervisor
        self._process = dict(process)
        self._child_fd = child_fd
        self._owner_guard = owner_guard
        try:
            self._pidfd = os.dup(process_pidfd)
            self._netns_fd = os.open('/proc/thread-self/ns/net', os.O_RDONLY | os.O_CLOEXEC)
            self._netns_identity = _identity(self._netns_fd)
            self._socket_identity = _identity(anchor.fileno())
            self._socket_cookie = _cookie(anchor, _SO_COOKIE)
            self._netns_cookie = _cookie(anchor, _SO_NETNS_COOKIE)
            self._supervisor_identity = _identity(supervisor.fileno())
            self._supervisor_cookie = _cookie(supervisor, _SO_COOKIE)
            # A fresh socket in the caller's current namespace establishes that
            # the anchor actually originated in the pinned host namespace.
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as witness:
                if _cookie(witness, _SO_NETNS_COOKIE) != self._netns_cookie:
                    raise RuntimeError('UDP socket is not in host network namespace')
            self._local = anchor.getsockname()
            self._destination = supervisor.getsockname()
            if (self._local[0] != '127.0.0.1' or not self._local[1] or
                    self._destination[0] != '127.0.0.1' or not self._destination[1] or
                    anchor.getpeername() != self._destination or
                    supervisor.getpeername() != self._local or self._local == self._destination):
                raise RuntimeError('connected host loopback UDP endpoint required')
            self.check()
        except BaseException:
            self.close()
            raise

    def _process_check(self):
        if (_pidfd_pid(self._pidfd) != self._process.get('pid') or
                select.select([self._pidfd], [], [], 0)[0]):
            raise RuntimeError('owned process pidfd changed or exited')
        check_process(self._process)

    def _anchor_check(self):
        anchor = self._anchor
        current_netns = os.open('/proc/thread-self/ns/net', os.O_RDONLY | os.O_CLOEXEC)
        try:
            current_netns_identity = _identity(current_netns)
        finally:
            os.close(current_netns)
        if (_identity(self._netns_fd) != self._netns_identity or
                current_netns_identity != self._netns_identity):
            raise RuntimeError('host network namespace changed')
        self._socket_check('inherited', anchor, self._socket_identity,
                           self._socket_cookie, self._local, self._destination)
        self._socket_check('supervisor', self._supervisor, self._supervisor_identity,
                           self._supervisor_cookie, self._destination, self._local)

    def _socket_check(self, label, sock, identity, cookie, local, peer):
        if sock.fileno() < 0:
            raise RuntimeError(f'{label} UDP socket closed')
        if (_identity(sock.fileno()) != identity or
                _cookie(sock, _SO_COOKIE) != cookie or
                _cookie(sock, _SO_NETNS_COOKIE) != self._netns_cookie or
                sock.getsockname() != local or sock.getpeername() != peer or
                sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) or
                sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT)):
            raise RuntimeError(f'{label} UDP socket identity, peer, or exclusivity changed')

    def check(self):
        """Check current ownership; uncertainty raises and must fence the session."""
        try:
            return self._check()
        except BaseException:
            self.close()
            raise

    def _check(self):
        if self._pidfd is None or self._netns_fd is None:
            raise RuntimeError('inherited UDP guard closed')
        self._process_check()
        if self._owner_guard() is not True:
            raise RuntimeError('external process ownership changed')
        self._anchor_check()
        process_dir = Path('/proc') / str(self._process['pid'])
        descriptors = process_dir / 'fd'
        expected = f'socket:[{self._socket_identity[1]}]'
        matches = []
        for fd in descriptors.iterdir():
            try:
                if os.readlink(fd) == expected:
                    matches.append(fd.name)
            except FileNotFoundError:
                continue
        if matches != [str(self._child_fd)]:
            raise RuntimeError('child UDP descriptor identity or exclusivity changed')
        child_fd = os.open(descriptors / str(self._child_fd), os.O_PATH | os.O_CLOEXEC)
        try:
            if _identity(child_fd) != self._socket_identity:
                raise RuntimeError('child UDP descriptor replaced')
        finally:
            os.close(child_fd)
        def endpoint(address):
            ipv4 = int.from_bytes(socket.inet_aton(address[0]), byteorder=sys.byteorder)
            return f'{ipv4:08X}:{address[1]:04X}'
        def mapped_endpoint(address):
            ipv6 = socket.inet_pton(socket.AF_INET6, '::ffff:' + address[0])
            words = (int.from_bytes(ipv6[i:i + 4], byteorder=sys.byteorder)
                     for i in range(0, 16, 4))
            return ''.join(f'{word:08X}' for word in words) + f':{address[1]:04X}'
        rows = Path('/proc/thread-self/net/udp').read_text().splitlines()[1:]
        parsed = [line.split() for line in rows]
        rows6 = Path('/proc/thread-self/net/udp6').read_text().splitlines()[1:]
        parsed6 = [line.split() for line in rows6]
        flows = ((self._local, self._destination, self._socket_identity),
                 (self._destination, self._local, self._supervisor_identity))
        for local, remote, identity in flows:
            matches = [row for row in parsed if len(row) > 9 and
                       row[1] == endpoint(local) and row[2] == endpoint(remote)]
            if len(matches) != 1 or matches[0][9] != str(identity[1]):
                raise RuntimeError('host network UDP flow changed or has a competing socket')
            mapped_matches = [row for row in parsed6 if len(row) > 9 and
                              row[1] == mapped_endpoint(local) and
                              row[2] == mapped_endpoint(remote)]
            if mapped_matches:
                raise RuntimeError('host network UDP flow has a competing IPv6 socket')
        self._anchor_check()
        self._process_check()
        if self._owner_guard() is not True:
            raise RuntimeError('external process ownership changed')
        return True

    def close(self):
        for name in ('_pidfd', '_netns_fd'):
            fd = getattr(self, name, None)
            if fd is not None:
                setattr(self, name, None)
                os.close(fd)
