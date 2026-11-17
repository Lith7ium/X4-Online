"""Watch one private client log for a single local sector observation.

The caller must fence the owned process, profile, session and all other log
writers around polling. A sector name is a point-in-time client observation,
not a portable sector identity or a server subscription. STOP and process-exit
arguments are caller assertions; this module cannot independently prove them.
File metadata cannot exclude rewriting old bytes while the file also grows.
Poll order cannot establish the exact native time at which a line was emitted.
"""
import os
from pathlib import Path
import re
import stat


class ClientSectorLogWatch:
    """Inspect an append-only file with serialized calls; failures are terminal."""

    MAX_LOG_BYTES = 256 * 1024 * 1024
    MAX_LINE_BYTES = 4096
    CHUNK_BYTES = 64 * 1024
    MAX_POLL_BYTES = 256 * 1024
    TAG = b'[X4LAN] AUTH_CLIENT_SECTOR'
    OBSERVATION = re.compile(rb' observed sector=([A-Za-z0-9_]{1,128})\Z')
    ERROR_TAGS = (
        b'[X4LAN] AUTH_RECOVERED_CLIENT_MOTION ERROR',
        b'[X4LAN] AUTH_PARTICIPANT ERROR',
        b'Error while executing onEvent script for event: X4AuthorityPlayerSectorInterest.Result.',
        b'Error while executing onEvent script for event: X4AuthoritySavedBaselineMotionBind.Result.',
        b'Error while executing onEvent script for event: X4AuthorityReplicaMotionBind.Result.',
    )

    def __init__(self, path, *, disarmed=False):
        if type(disarmed) is not bool:
            raise ValueError('invalid sector watch mode')
        self.path = Path(path)
        self._identity = None
        self._offset = 0
        self._previous_stat = None
        self._line = b''
        self._sector = None
        self._state = 'disarmed' if disarmed else 'watching'

    def _accept_line(self, line):
        count = line.count(self.TAG)
        if not count:
            return
        if count != 1 or self._state != 'watching' or self._sector is not None:
            raise ValueError('duplicate or late sector observation')
        message = line.split(self.TAG, 1)[1]
        match = self.OBSERVATION.fullmatch(message)
        if match is None:
            raise ValueError('invalid sector observation')
        self._sector = match.group(1).decode('ascii')

    def _consume(self, chunk):
        self._line += chunk
        if any(tag in self._line for tag in self.ERROR_TAGS):
            raise ValueError('client sector or motion owner reported an error')
        if self._state == 'disarmed' and self.TAG in self._line:
            raise ValueError('sector observation before arming')
        while b'\n' in self._line:
            line, self._line = self._line.split(b'\n', 1)
            if len(line) > self.MAX_LINE_BYTES:
                raise ValueError('client log line exceeds limit')
            self._accept_line(line)
        if len(self._line) > self.MAX_LINE_BYTES:
            raise ValueError('client log line exceeds limit')

    def poll(self):
        """Read one bounded batch; return whether the observed file was caught up."""
        if self._state not in ('disarmed', 'watching', 'stopped'):
            raise ValueError('sector watch is unavailable')
        try:
            try:
                flags = (os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) |
                         getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NONBLOCK', 0))
                fd = os.open(self.path, flags)
            except FileNotFoundError:
                if self._identity is None:
                    return False
                raise ValueError('client log disappeared') from None
            except OSError:
                raise ValueError('client log unavailable') from None
            try:
                before = os.fstat(fd)
                identity = (before.st_dev, before.st_ino)
                if not stat.S_ISREG(before.st_mode) or before.st_size > self.MAX_LOG_BYTES:
                    raise ValueError('invalid client log')
                if self._identity is not None:
                    previous_size, previous_mtime, previous_ctime = self._previous_stat
                    if identity != self._identity or before.st_size < previous_size:
                        raise ValueError('client log replaced or truncated')
                    if (before.st_size == previous_size and
                            (previous_mtime, previous_ctime) != (before.st_mtime_ns, before.st_ctime_ns)):
                        raise ValueError('client log changed without appending')
                self._identity = identity
                remaining = self.MAX_POLL_BYTES
                while self._offset < before.st_size and remaining > 0:
                    chunk = os.pread(fd, min(self.CHUNK_BYTES, remaining, before.st_size - self._offset), self._offset)
                    if not chunk:
                        raise ValueError('client log changed while reading')
                    self._offset += len(chunk)
                    remaining -= len(chunk)
                    self._consume(chunk)
                after = os.fstat(fd)
                current = self.path.lstat()
                if ((after.st_dev, after.st_ino) != identity or after.st_size < before.st_size or
                        not stat.S_ISREG(current.st_mode) or (current.st_dev, current.st_ino) != identity or
                        current.st_size < after.st_size or
                        (after.st_size == before.st_size and
                         (after.st_mtime_ns, after.st_ctime_ns) != (before.st_mtime_ns, before.st_ctime_ns)) or
                        (current.st_size == after.st_size and
                         (current.st_mtime_ns, current.st_ctime_ns) != (after.st_mtime_ns, after.st_ctime_ns))):
                    raise ValueError('client log changed while reading')
                self._previous_stat = (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                return self._offset == after.st_size == current.st_size
            finally:
                os.close(fd)
        except OSError:
            self._state = 'failed'
            raise ValueError('client log unavailable') from None
        except BaseException:
            self._state = 'failed'
            raise

    def arm(self):
        """Arm once after a fully caught-up log with no incomplete line."""
        if self._state != 'disarmed':
            self._state = 'failed'
            raise ValueError('sector watch cannot be armed')
        if not self.poll() or self._line:
            self._state = 'failed'
            raise ValueError('client log not ready for sector observation')
        self._state = 'watching'

    def observe(self):
        """Return a provisional local sector only when the log is caught up.

        This observation alone confirms neither process identity nor a receipt.
        """
        if self._state != 'watching':
            self._state = 'failed'
            raise ValueError('sector watch is unavailable')
        if not self.poll():
            return None
        return self._sector

    def confirm_stop(self, *, confirmed):
        """Fence sector lines observed later than the caller's STOP assertion."""
        if self._state != 'watching' or confirmed is not True:
            self._state = 'failed'
            raise ValueError('confirmed client stop required')
        if not self.poll():
            self._state = 'failed'
            raise ValueError('client log not caught up before stop')
        if self._sector is None:
            self._state = 'failed'
            raise ValueError('sector observation missing before stop')
        self._state = 'stopped'

    def finish(self, *, process_stopped):
        """Return the sole sector after caller-confirmed process exit and final EOF."""
        if self._state != 'stopped' or process_stopped is not True:
            self._state = 'failed'
            raise ValueError('confirmed client process exit required')
        if not self.poll():
            self._state = 'failed'
            raise ValueError('client log not caught up after process exit')
        if self._identity is None or self._line:
            self._state = 'failed'
            raise ValueError('incomplete final client log')
        self._state = 'finished'
        return self._sector
