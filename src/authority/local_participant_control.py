"""Opt-in loopback pause/resume controller for one isolated X4 participant.

The supervisor owns the X4 process and its private configuration and must
verify process identity and protect the lease itself. A loopback receipt is
not proof of process identity, save loading, or network participant identity.
Calls must be serialized. A dispatched command that times out or returns an
unexpected receipt permanently poisons this controller; the supervisor must
fence the X4 process before creating a replacement.
"""
import re
import secrets
import socket
import time

_HEX = re.compile(r'[0-9a-f]{32}\Z')
_MAX_ID = 9007199254740991


class LocalParticipantControl:
    """Synchronous WorldCoordinator participant adapter for exactly one handle."""

    def __init__(self, *, enabled, timeout=130):
        if enabled is not True:
            raise ValueError('participant control requires explicit opt-in')
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 600:
            raise ValueError('invalid participant timeout')
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', 0))
        self.sock.settimeout(.25)
        self.lease = secrets.token_hex(16)
        self.peer = self.epoch = self.handle = None
        self.next_id = 1
        self.fault = False
        self.timeout = timeout

    def enroll(self, epoch, deadline):
        """Pin a loopback sender bearing this lease; caller verifies process ownership."""
        if self.fault or self.peer is not None:
            raise RuntimeError('participant unavailable or already enrolled')
        if not isinstance(epoch, str) or not _HEX.fullmatch(epoch):
            raise ValueError('invalid world epoch')
        self.epoch = epoch
        expected = f'HELLO|{self.lease}|{epoch}'.encode('ascii')
        while time.monotonic() < deadline:
            try:
                data, peer = self.sock.recvfrom(769)
            except socket.timeout:
                continue
            if data == expected and peer[0] == '127.0.0.1':
                self.peer = peer
                return
        self.fault = True
        raise TimeoutError('participant enrollment timed out')

    def request(self, operation):
        if operation not in ('pause', 'resume'):
            raise ValueError('unsupported participant operation')
        if self.fault or self.peer is None:
            raise RuntimeError('participant unavailable')
        if self.next_id > _MAX_ID:
            self.fault = True
            raise RuntimeError('participant request IDs exhausted')
        self.fault = True
        number = self.next_id
        self.next_id += 1
        prefix = f'{self.lease}|{self.epoch}|{number}'
        self.sock.sendto(f'CMD|{prefix}|{operation}'.encode('ascii'), self.peer)
        expected = f'RECEIPT|{prefix}|{operation}|confirmed'.encode('ascii')
        hello = f'HELLO|{self.lease}|{self.epoch}'.encode('ascii')
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                data, peer = self.sock.recvfrom(769)
            except socket.timeout:
                continue
            if peer != self.peer:
                continue
            if data == hello:
                continue
            if data != expected:
                raise RuntimeError('unexpected participant receipt')
            self.fault = False
            return
        raise TimeoutError('participant state indeterminate')

    def pause(self, handles):
        if self.handle is None or handles != (self.handle,):
            raise ValueError('unexpected participant set')
        self.request('pause')
        return True

    def resume(self, handles):
        if self.handle is None or handles != (self.handle,):
            raise ValueError('unexpected participant set')
        self.request('resume')
        return True

    def close(self):
        self.fault = True
        self.sock.close()


class LocalParticipantGroup:
    """Serialized participant adapter; the supervisor owns each controller.

    Once a command fails, some clients may have changed state already. The
    group remains faulted; replacing it is safe only after the supervisor has
    fenced or settled every affected process.
    """

    def __init__(self, *, enabled, world_epoch):
        if enabled is not True:
            raise ValueError('participant group requires explicit opt-in')
        if not isinstance(world_epoch, str) or not _HEX.fullmatch(world_epoch):
            raise ValueError('invalid participant group world epoch')
        self._epoch = world_epoch
        self._controllers = {}
        self._faulted = False

    def attach(self, handle, controller):
        if self._faulted:
            raise RuntimeError('participant group is faulted')
        if (type(handle) is not int or handle < 1
                or not isinstance(controller, LocalParticipantControl)
                or controller.handle != handle or controller.fault or controller.peer is None
                or controller.epoch != self._epoch
                or handle in self._controllers
                or any(existing is controller for existing in self._controllers.values())):
            raise ValueError('invalid or duplicate participant controller')
        self._controllers[handle] = controller

    def detach(self, handle):
        if self._faulted:
            raise RuntimeError('participant group is faulted')
        if type(handle) is not int or handle not in self._controllers:
            raise ValueError('unknown participant handle')
        return self._controllers.pop(handle)

    def _control(self, operation, handles):
        if self._faulted:
            raise RuntimeError('participant group is faulted')
        if (not isinstance(handles, tuple) or any(type(handle) is not int or handle < 1 for handle in handles)
                or len(set(handles)) != len(handles)):
            raise ValueError('invalid participant set')
        controllers = []
        for handle in handles:
            controller = self._controllers.get(handle)
            if (controller is None or controller.handle != handle or controller.fault or controller.peer is None
                    or controller.epoch != self._epoch):
                raise ValueError('participant controller is unavailable')
            controllers.append((handle, controller))
        # Fault before dispatch: even an exception after one successful receipt
        # leaves a mixed or uncertain client state.
        self._faulted = True
        for handle, controller in controllers:
            if getattr(controller, operation)((handle,)) is not True:
                raise RuntimeError('participant operation was not confirmed')
        self._faulted = False
        return True

    def pause(self, handles):
        return self._control('pause', handles)

    def resume(self, handles):
        return self._control('resume', handles)
