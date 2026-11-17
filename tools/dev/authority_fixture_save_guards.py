"""Private, owner-thread-only save guards for the two-player fixture probe."""
from contextlib import ExitStack
import os
from pathlib import Path
import stat
import time

from authority_pinned_file_guard import PinnedFileGuard


class FixtureSaveGuards:
    """Use pinned metadata only inside an explicitly bounded observation.

    The caller must own and serialize its FD table, all fixture processes, and
    all writers. A read-only game bind is necessary but does not exclude an
    external writer; this experimental diagnostic assumes there is none.
    """

    def __init__(self, full_sha):
        if not callable(full_sha):
            raise ValueError('full save digest function required')
        self._full_sha = full_sha
        self._guards = None
        self._stack = None
        self._cleanup_failed = False
        self.metrics = {'metadata_checks': 0, 'digest_checks': 0, 'sampling_windows': 0,
                        'verified_digest_bytes': 0, 'digest_seconds': 0.0}

    def check(self, path, expected):
        self._require_usable()
        if self._guards is None:
            return self._full_sha(path) == expected
        entry = self._guards.get(Path(path))
        if entry is None or entry[1] != expected:
            raise ValueError('save is outside the pinned fixture context')
        self.metrics['metadata_checks'] += 1
        return entry[0].check()

    def open(self, entries, *, expected_count=3):
        self._require_usable()
        if (type(expected_count) is not int or expected_count not in (2, 3) or
                self._guards is not None or type(entries) is not list or len(entries) != expected_count):
            raise ValueError('expected two or three distinct fixture saves')
        stack = ExitStack()
        guards = {}
        try:
            for path, expected in entries:
                path = Path(path)
                if not path.is_absolute() or path in guards:
                    raise ValueError('invalid fixture save path')
                info = os.lstat(path)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or
                        stat.S_IMODE(info.st_mode) != 0o400):
                    raise ValueError('fixture save must be private and read-only')
                pin = PinnedFileGuard(path, expected)
                # Register cleanup before checking the new pin: a failed
                # context-manager __enter__ would not be unwound by ExitStack.
                stack.callback(pin.close)
                pin.check()
                after = os.lstat(path)
                if ((info.st_dev, info.st_ino, info.st_uid, info.st_mode, info.st_size,
                     info.st_mtime_ns, info.st_ctime_ns) !=
                        (after.st_dev, after.st_ino, after.st_uid, after.st_mode, after.st_size,
                         after.st_mtime_ns, after.st_ctime_ns)):
                    raise ValueError('fixture save changed while pinning')
                guards[path] = (pin, expected, info.st_size)
            self._stack, self._guards = stack, guards
        except BaseException as error:
            try:
                stack.close()
            except BaseException as cleanup_error:
                self._cleanup_failed = True
                raise BaseExceptionGroup('fixture save pinning and cleanup failed',
                                         [error, cleanup_error]) from None
            raise

    def boundary(self, guard):
        self._require_usable()
        if self._guards is None or not callable(guard):
            raise RuntimeError('fixture save guard is not active')
        for pin, _, size in self._guards.values():
            started = time.monotonic()
            self.metrics['digest_checks'] += 1
            try:
                if pin.verify_digest(guard=guard) is not True:
                    raise RuntimeError('fixture digest was not confirmed')
                self.metrics['verified_digest_bytes'] += size
            finally:
                self.metrics['digest_seconds'] += time.monotonic() - started
        return True

    def close(self):
        self._require_usable()
        if self._stack is not None:
            try:
                self._stack.close()
            except BaseException:
                # ExitStack consumes callbacks even when one fails. It is no
                # longer safe to retry or to resume checking through this owner.
                self._cleanup_failed = True
                raise
            self._stack = self._guards = None

    def _require_usable(self):
        if self._cleanup_failed:
            raise RuntimeError('fixture save guard cleanup failed; owner is fenced')


class FixtureSamplingWindow:
    """Bound metadata shortcuts to one sampling phase, with full checks outside it."""

    def __init__(self, guards, verify_context, digest_guard):
        if not isinstance(guards, FixtureSaveGuards) or not callable(verify_context) or not callable(digest_guard):
            raise ValueError('fixture window requires its save and process guards')
        self.guards = guards
        self.verify_context = verify_context
        self.digest_guard = digest_guard
        self.active = False
        self.failed = False

    def boundary(self):
        if self.failed or not self.active:
            raise RuntimeError('fixture sampling window is not active')
        try:
            self.verify_context()
            self.guards.boundary(self.digest_guard)
            self.verify_context()
        except BaseException:
            self.failed = True
            raise
        return True

    def open(self, entries, *, expected_count=3):
        if self.failed or self.active:
            raise RuntimeError('fixture sampling window cannot open')
        try:
            # With no pins active, these are full save hashes, including the
            # newly admitted client's exact downloaded file and checkpoint.
            self.verify_context()
            self.guards.open(entries, expected_count=expected_count)
            self.active = True
            self.boundary()
            self.guards.metrics['sampling_windows'] += 1
        except BaseException:
            self.failed = True
            raise
        return True

    def close(self):
        if self.failed or not self.active:
            raise RuntimeError('fixture sampling window cannot close')
        try:
            self.boundary()
            self.guards.close()
            self.active = False
            # The transition must begin only after the same files were also
            # checked using the normal, full-hash path.
            self.verify_context()
        except BaseException:
            self.failed = True
            raise
        return True
