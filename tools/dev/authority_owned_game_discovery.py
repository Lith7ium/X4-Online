"""Owner-thread process discovery scopes for the private paired diagnostic.

Full group uniqueness discovery brackets one synchronous guard call. Nested
lookups still reread the declared launcher and X4 identities. Discovery of an
additional X4 in the group is deferred until that call exits, never across a
socket read/wait or an entire sampling window. This is not a process lock.
"""
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
import os
from pathlib import Path
import threading

import linux_gate_live as live

_active = ContextVar('authority_owned_game_discovery', default=None)


def scoped_identity(process, started, game):
    scope = _active.get()
    if scope is None:
        return None
    return scope.resolve(process, started, game)


def retained_scope(factory, expected_client, active_clients):
    """Departure removes the client before teardown; never scope that teardown."""
    if factory is None or not active_clients:
        return nullcontext()
    if len(active_clients) != 1 or active_clients[0] is not expected_client:
        raise RuntimeError('retained discovery participant changed')
    return factory()


@dataclass(frozen=True)
class OwnedGameEntry:
    launcher: object
    launcher_started: int
    game: Path
    game_identity: tuple[int, int]
    launcher_snapshot: dict
    game_snapshot: dict


class OwnedGameDiscovery:
    def __init__(self, declarations):
        from authority_download_load_live import _discover_game_identity
        self.owner = threading.get_ident()
        self.discover = _discover_game_identity
        self.entries = []
        if type(declarations) is not tuple or len(declarations) != 2:
            raise ValueError('two owned games required')
        for process, started, game, identity in declarations:
            game = Path(game).resolve(strict=True)
            if (type(started) is not int or type(identity) is not tuple or len(identity) != 2 or
                    any(type(value) is not int or value < 1 for value in identity) or
                    any(process is entry.launcher or identity[0] == entry.game_identity[0] for entry in self.entries)):
                raise ValueError('distinct owned games required')
            if self.discover(process, started, game) != identity:
                raise RuntimeError('owned game discovery changed')
            launcher = self._read(process.pid)
            actor = self._read(identity[0])
            if (launcher['start'] != started or actor['start'] != identity[1] or
                    launcher['group'] != process.pid or launcher['session'] != process.pid or
                    actor['group'] != launcher['group'] or actor['session'] != launcher['session'] or
                    actor['exe'] != self._image(game/'X4')):
                raise RuntimeError('owned game launch context changed')
            self.entries.append(OwnedGameEntry(process, started, game, identity, launcher, actor))
        self.entries = tuple(self.entries)
        self._full_check()

    @staticmethod
    def _image(path):
        image = path.stat()
        return image.st_dev, image.st_ino

    def _read(self, pid):
        row = live.owned_process_identity(pid)
        if row['state'] in ('Z', 'X', 'x') or row['uid'] != os.geteuid():
            raise RuntimeError('owned process exited or changed owner')
        return {**{key: row[key] for key in ('pid', 'start', 'uid', 'group', 'session')},
                'exe': self._image(Path('/proc')/str(pid)/'exe')}

    def _targeted(self, entry):
        if threading.get_ident() != self.owner or entry.launcher.poll() is not None:
            raise RuntimeError('owned launcher unavailable or wrong thread')
        if (self._read(entry.launcher.pid) != entry.launcher_snapshot or
                self._read(entry.game_identity[0]) != entry.game_snapshot):
            raise RuntimeError('owned process identity changed')
        return entry.game_identity

    def _full_check(self):
        for entry in self.entries:
            self._targeted(entry)
            if self.discover(entry.launcher, entry.launcher_started, entry.game) != entry.game_identity:
                raise RuntimeError('owned group uniqueness changed')
            self._targeted(entry)

    def resolve(self, process, started, game):
        for entry in self.entries:
            if (process is entry.launcher and type(started) is int and
                    started == entry.launcher_started and Path(game) == entry.game):
                return self._targeted(entry)
        raise RuntimeError('undeclared owned game lookup')

    @contextmanager
    def scope(self):
        if threading.get_ident() != self.owner:
            raise RuntimeError('owned discovery scope on wrong thread')
        previous = _active.get()
        if previous is not None and previous is not self:
            raise RuntimeError('different owned discovery scope active')
        outer = previous is None
        if outer:
            self._full_check()
        else:
            for entry in self.entries:
                self._targeted(entry)
        token = _active.set(self)
        body_error = None
        try:
            yield
        except BaseException as error:
            body_error = error
            raise
        finally:
            try:
                if outer:
                    self._full_check()
                else:
                    for entry in self.entries:
                        self._targeted(entry)
            except BaseException as error:
                if body_error is not None:
                    raise BaseExceptionGroup('guard and owned discovery exit failed', [body_error, error]) from None
                raise
            finally:
                _active.reset(token)
