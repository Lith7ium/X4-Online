"""Opt-in, single-owner loopback bridge for the experimental X4 controller.

Blocking methods implement WorldCoordinator's synchronous engine contract over
asynchronous Lua receipts. Use only with a disposable, isolated profile and a
fenced X4 process. A timeout permanently poisons this adapter: it does not fence
an already dispatched X4 operation. The caller serializes every access.
"""
import re
import socket
import time
from pathlib import Path

_HEX = re.compile(r'[0-9a-f]{32}\Z')


class LocalControlBridge:
    def __init__(self, *, enabled, sock, peer, lease, world_epoch, profile, store,
                 verify_checkpoint, timeout=130):
        if enabled is not True:
            raise ValueError('local control bridge requires explicit opt-in')
        if (not _HEX.fullmatch(lease) or not _HEX.fullmatch(world_epoch)
                or sock.family != socket.AF_INET or sock.type != socket.SOCK_DGRAM
                or sock.getsockname()[0] != '127.0.0.1'
                or not isinstance(peer, tuple) or len(peer) != 2 or peer[0] != '127.0.0.1'
                or not 1 <= peer[1] <= 65535 or not 0 < timeout <= 600
                or not callable(verify_checkpoint)):
            raise ValueError('invalid local bridge configuration')
        profile = Path(profile)
        if profile.is_symlink() or profile.name != '45841' or not profile.is_dir():
            raise ValueError('isolated 45841 profile required')
        save_dir = profile / 'save'
        if save_dir.is_symlink() or not save_dir.is_dir():
            raise ValueError('isolated save directory required')
        self._source = save_dir / 'save_009.xml.gz'
        if self._source.exists() or self._source.is_symlink():
            raise ValueError('owned save slot must initially be empty')
        self._sock, self._peer, self._lease, self._epoch = sock, peer, lease, world_epoch
        self._store, self._verify, self._timeout = store, verify_checkpoint, timeout
        self._next, self._pending_save, self._poisoned = 1, None, False

    def _exchange(self, command, expected):
        if self._poisoned:
            raise RuntimeError('bridge is fenced after an indeterminate operation')
        self._poisoned = True
        old_timeout = self._sock.gettimeout()
        try:
            self._sock.sendto(command.encode('ascii'), self._peer)
            deadline = time.monotonic() + self._timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('native control receipt timed out; engine state indeterminate')
                self._sock.settimeout(remaining)
                data, peer = self._sock.recvfrom(769)
                if peer != self._peer:
                    continue
                if data == f'HELLO|{self._lease}|{self._epoch}'.encode('ascii'):
                    continue
                if data != expected.encode('ascii'):
                    raise RuntimeError('unexpected native control receipt')
                self._poisoned = False
                return
        finally:
            self._sock.settimeout(old_timeout)

    def _request(self, operation, status):
        if self._pending_save is not None:
            raise RuntimeError('previous save has not been verified')
        number = self._next
        if number > 9007199254740991:
            raise ValueError('request IDs exhausted')
        self._next += 1
        prefix = f'{self._lease}|{self._epoch}|{number}'
        self._exchange(f'CMD|{prefix}|{operation}', f'RECEIPT|{prefix}|{operation}|{status}')
        return number

    def pause(self):
        self._request('pause', 'confirmed')

    def resume(self):
        self._request('resume', 'confirmed')

    def save(self):
        number = self._request('save', 'native_event_only')
        self._pending_save = number
        return self._source

    def checkpoint_published(self, checkpoint):
        number = self._pending_save
        if number is None:
            raise ValueError('no native save awaits verification')
        # Poison before validation: never authorize reuse after an uncertain copy.
        self._poisoned = True
        expected = f'X4 Authority {self._epoch} {number}'
        evidence = self._verify(self._store, checkpoint.checkpoint_id, expected)
        if (self._store.get(checkpoint.checkpoint_id) != checkpoint
                or evidence.checkpoint_id != checkpoint.checkpoint_id
                or evidence.sha256 != checkpoint.sha256 or evidence.size != checkpoint.size
                or evidence.save_name != expected):
            raise ValueError('published checkpoint identity mismatch')
        self._poisoned = False
        prefix = f'{self._lease}|{self._epoch}|{number}'
        self._exchange(f'VERIFY|{prefix}', f'VERIFIED|{prefix}')
        self._pending_save = None
        return True
