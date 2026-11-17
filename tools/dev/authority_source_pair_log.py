"""Read final local source-pair diagnostics without claiming native velocity.

The caller must first stop the owned process and fence other log writers. The
result describes only this private log message, not cross-client movement or
the accuracy of the estimated velocity.
"""
import math
import os
import re
import stat


MAX_LOG_BYTES = 32 << 20
TAG = b'[X4LAN] AUTH_LOCAL_PAIR'
NUMBER = rb'[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?'
ESTIMATED = re.compile(
    rb' estimated dt=(' + NUMBER + rb') vx=(' + NUMBER +
    rb') vy=(' + NUMBER + rb') vz=(' + NUMBER + rb')\Z'
)


def _fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read_final_regular_file(path):
    """Reject special files before reading; never wait for a FIFO writer."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_LOG_BYTES:
            raise ValueError('invalid final pair log file')
        chunks = []
        total = 0
        while True:
            chunk = os.read(fd, min(1 << 20, MAX_LOG_BYTES - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_LOG_BYTES:
                raise ValueError('final pair log exceeds limit')
            chunks.append(chunk)
        after = os.fstat(fd)
        if _fingerprint(before) != _fingerprint(after) or total != before.st_size:
            raise ValueError('final pair log changed while reading')
        return _fingerprint(before), b''.join(chunks)
    finally:
        os.close(fd)


def read_source_pair_log(path):
    """Return missing/unavailable/estimated, or raise on an invalid final log.

    Missing means no pair message in an otherwise readable, complete log. An
    unreadable or changing file is an error, never evidence of a missing pair.
    The no-follow reader protects the final path component; the caller owns the
    surrounding private directory and the file's writer fence.
    """
    fingerprint, raw = _read_final_regular_file(path)
    current = path.lstat()
    if (not stat.S_ISREG(current.st_mode) or
            _fingerprint(current) != fingerprint):
        raise ValueError('final pair log changed')
    if not raw.endswith(b'\n'):
        raise ValueError('incomplete final pair log')
    if raw.count(TAG) == 0:
        return {'status': 'missing'}
    if raw.count(TAG) != 1:
        raise ValueError('duplicate pair messages')
    message = raw.split(TAG, 1)[1].split(b'\n', 1)[0]
    if message == b' unavailable':
        return {'status': 'unavailable'}
    match = ESTIMATED.fullmatch(message)
    if match is None:
        raise ValueError('invalid pair message')
    elapsed, vx, vy, vz = (float(value) for value in match.groups())
    if (not all(math.isfinite(value) for value in (elapsed, vx, vy, vz)) or
            not 0.02 <= elapsed <= 1 or any(abs(value) > 5000 for value in (vx, vy, vz))):
        raise ValueError('invalid pair values')
    return {'status': 'estimated', 'dt': elapsed, 'vx': vx, 'vy': vy, 'vz': vz}
