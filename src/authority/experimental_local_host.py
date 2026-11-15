"""Opt-in loopback-only owner for existing experimental host components.

The caller creates and fences the engine, listener, and started file service;
it owns cleanup, serializes all access, and supplies real participant controls
before using real clients. No X4 process or network listener is started here.
"""
import socket

from lockstep.launcher.joinfiles import FileService
from .experimental_tcp_control import ExperimentalTCPControl
from .world import WorldCoordinator


class ExperimentalLocalHost:
    """Pump a connected loopback control channel and one world action per tick.

    This is an integration seam, not a runnable server. Bridge actions are
    synchronous and may block the owner's network pumping until they finish.
    After an indeterminate exception all components must be fenced/discarded.
    """
    def __init__(self, world, control, service, *, enabled=False):
        if (enabled is not True or type(world) is not WorldCoordinator or
                type(control) is not ExperimentalTCPControl or type(service) is not FileService):
            raise ValueError('explicitly enabled local host components required')
        control._owner()
        if (control._session._world is not world or world._offers.service is not service or
                service.server.server_address[0] != '127.0.0.1' or
                service.thread is None or not service.thread.is_alive() or control._peers or
                world.session.players):
            raise ValueError('fresh serialized world and live loopback service required')
        self._world, self._control, self._service = world, control, service
        self._failed = False
        self._busy = False

    def _check(self):
        try:
            self._control._owner()
        except RuntimeError as error:
            if self._control._failed or self._control._closed:
                self._failed = True
                raise RuntimeError('control unavailable; fence all components') from error
            raise
        if self._failed:
            raise RuntimeError('host faulted; fence all components')
        if self._busy:
            raise RuntimeError('reentrant host access is forbidden')
        if not self._service.thread.is_alive():
            self._failed = True
            raise RuntimeError('file service stopped; fence all components')

    def adopt(self, conn):
        """Adopt an accepted loopback IPv4 connection; caller owns rejection."""
        self._check()
        if (type(conn) is not socket.socket or conn.family != socket.AF_INET or
                conn.getpeername()[0] != '127.0.0.1'):
            raise ValueError('connected loopback socket required')
        self._busy = True
        try:
            return self._control.adopt(conn)
        except BaseException:
            if self._control._failed:
                self._failed = True
            raise
        finally:
            self._busy = False

    def tick(self, timeout=0):
        """Pump sockets and dispatch at most one pending synchronous action."""
        self._check()
        self._busy = True
        try:
            self._control.poll(timeout)
            pending = self._world.session.pending
            if pending is None:
                return None
            if pending.operation == 'resume' and not self._control.ready_for_resume():
                return None
            return self._world.step()
        except BaseException:
            self._failed = True
            raise
        finally:
            self._busy = False
