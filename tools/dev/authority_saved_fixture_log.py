"""Capture one checked prefix of a growing, private X4 diagnostic log."""
import hashlib
import os
from pathlib import Path
import stat


def capture(path, previous, limit):
    """Read the initial prefix twice, checking continuity and path identity.

    An append can proceed while reading. The caller receives only the prefix
    visible at the first stat and must poll again if the file has grown. This
    samples file identity and contents; it cannot exclude adversarial ABA edits.
    """
    path = Path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        if previous is None:
            return None
        raise ValueError('engine log: previously observed file disappeared') from None
    except OSError as error:
        raise OSError('engine log: cannot open evidence file') from error
    try:
        before = os.fstat(fd)
        identity = (before.st_dev, before.st_ino)
        size = before.st_size
        if not stat.S_ISREG(before.st_mode) or size > limit:
            raise ValueError('engine log: invalid file or size bound exceeded')
        if previous is not None and (identity != previous[0] or size < previous[1]):
            raise ValueError('engine log: file replaced or truncated')

        def read_prefix():
            os.lseek(fd, 0, os.SEEK_SET)
            chunks, remaining = [], size
            while remaining:
                part = os.read(fd, min(1 << 20, remaining))
                if not part:
                    raise ValueError('engine log: file truncated during capture')
                chunks.append(part)
                remaining -= len(part)
            return b''.join(chunks)

        first = read_prefix()
        middle = os.fstat(fd)
        second = read_prefix()
        after = os.fstat(fd)
        if middle.st_size < size or after.st_size < size or first != second:
            raise ValueError('engine log: captured prefix changed or was truncated')
        if previous is not None:
            old_size, old_digest = previous[1:]
            if hashlib.sha256(first[:old_size]).digest() != old_digest:
                raise ValueError('engine log: previously observed prefix changed')
        try:
            current = path.lstat()
        except FileNotFoundError:
            raise ValueError('engine log: file disappeared during capture') from None
        if (not stat.S_ISREG(current.st_mode) or
                (current.st_dev, current.st_ino) != identity or current.st_size < size):
            raise ValueError('engine log: file replaced or truncated during capture')
        if max(middle.st_size, after.st_size, current.st_size) > limit:
            raise ValueError('engine log: size bound exceeded')
        snapshot = (identity, size, hashlib.sha256(first).digest())
        caught_up = middle.st_size == after.st_size == current.st_size == size
        return first, snapshot, caught_up
    except OSError as error:
        raise OSError('engine log: cannot capture evidence file') from error
    finally:
        os.close(fd)
