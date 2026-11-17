"""Opt-in metadata and boundary-digest checks for private diagnostic files.

This helper is not connected to any live guard. Its metadata checks are not
proof that the bytes stayed unchanged between digest checks.
"""
import hashlib
import hmac
import os
import re
import stat


class PinnedFileGuard:
    """Pin one regular file and verify its expected digest at explicit boundaries."""

    def __init__(self, path, expected_sha256):
        path = os.fspath(path)
        if not isinstance(path, str) or not os.path.isabs(path):
            raise ValueError('an absolute file path is required')
        if not isinstance(expected_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
            raise ValueError('a lowercase SHA-256 digest is required')
        self._path = path
        self._expected_sha256 = expected_sha256
        self._fd = None
        self._busy = False
        self._invalid = False
        before = os.lstat(path)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('guarded path is not a regular file')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            pinned = os.fstat(fd)
            after = os.lstat(path)
            self._fingerprint = self._file_fingerprint(before)
            if (not stat.S_ISREG(pinned.st_mode) or
                    self._file_fingerprint(pinned) != self._fingerprint or
                    self._file_fingerprint(after) != self._fingerprint):
                raise ValueError('guarded file changed while opening')
            self._fd = fd
            self._original = (fd, self._path, self._expected_sha256, self._fingerprint)
        except BaseException:
            os.close(fd)
            raise

    @staticmethod
    def _file_fingerprint(info):
        return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns)

    def check(self):
        """Check path and descriptor identity/metadata, without reading contents."""
        self._require_idle()
        try:
            return self._check()
        except BaseException:
            self._invalid = True
            raise

    def _require_idle(self):
        if self._busy:
            self._invalid = True
            raise RuntimeError('reentrant file guard operation')
        if self._invalid:
            raise RuntimeError('file guard was invalidated')

    def _context(self):
        return (self._fd, self._path, self._expected_sha256, self._fingerprint)

    def _check(self):
        if self._fd is None:
            raise RuntimeError('guarded file is closed')
        if self._context() != self._original:
            self._invalid = True
            raise RuntimeError('file guard context changed')
        try:
            descriptor = os.fstat(self._fd)
            path = os.lstat(self._path)
        except FileNotFoundError:
            raise ValueError('guarded file disappeared') from None
        if (not stat.S_ISREG(descriptor.st_mode) or not stat.S_ISREG(path.st_mode) or
                self._file_fingerprint(descriptor) != self._fingerprint or
                self._file_fingerprint(path) != self._fingerprint):
            raise ValueError('guarded file identity or metadata changed')
        return True

    def verify_digest(self, *, guard=None):
        """Hash pinned bytes once, checking metadata and the optional live guard.

        A guard callback must return exactly True. It is called before each
        block and once after reading so callers can enforce their own deadline.
        """
        if guard is not None and not callable(guard):
            raise ValueError('guard must be callable')
        self._require_idle()
        try:
            return self._verify_digest(guard)
        except BaseException:
            self._invalid = True
            raise

    def _verify_digest(self, guard):
        self._check()
        context = self._context()
        original = self._original
        fd, _, expected, fingerprint = context
        self._busy = True
        try:
            def check_callback():
                if (not self._busy or self._invalid or self._original != original or
                        self._context() != context):
                    self._invalid = True
                    raise RuntimeError('file guard context changed during digest')
                self._check()
                if guard is not None:
                    accepted = guard()
                    if (not self._busy or self._invalid or self._original != original or
                            self._context() != context):
                        self._invalid = True
                        raise RuntimeError('file guard context changed during digest')
                    self._check()
                    if accepted is not True:
                        raise RuntimeError('live guard failed during file digest')

            digest = hashlib.sha256()
            offset = 0
            size = fingerprint[3]
            while offset < size:
                check_callback()
                block = os.pread(fd, min(1 << 20, size - offset), offset)
                if not block:
                    raise ValueError('guarded file truncated during digest')
                digest.update(block)
                offset += len(block)
            check_callback()
            if not hmac.compare_digest(digest.hexdigest(), expected):
                raise ValueError('guarded file digest differs')
            return True
        finally:
            self._busy = False

    def close(self):
        if self._busy:
            self._invalid = True
            raise RuntimeError('reentrant file guard operation')
        if self._fd is not None:
            if self._context() != self._original:
                self._invalid = True
                raise RuntimeError('file guard context changed; refusing cleanup')
            try:
                descriptor = os.fstat(self._fd)
            except OSError as error:
                self._invalid = True
                raise RuntimeError('file descriptor unavailable; refusing cleanup') from error
            if (descriptor.st_dev, descriptor.st_ino) != self._fingerprint[:2]:
                self._invalid = True
                raise RuntimeError('file descriptor replaced; refusing cleanup')
            os.close(self._fd)
            self._fd = None

    def __enter__(self):
        self.check()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
