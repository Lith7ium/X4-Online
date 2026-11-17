"""Copy one offered save to a new X4 slot in caller-owned directories.

The caller must fence other writers and X4's save-list scan while the copy is
in progress. This module does not find profiles, load a save, or authenticate a
server. A failed operation deliberately leaves any file it created in place;
even a successful copy may be left behind if subsequent verification fails.
"""
import hashlib
import os
from pathlib import Path
import re
import stat

from .load_messages import Offer
from .file_fingerprints import fingerprint, same_path_and_descriptor

_SLOT = re.compile(r'save_[0-9]{3}\.xml\.gz\Z')
_CHUNK_SIZE = 1024 * 1024


def _write_all(outgoing, block, pump):
    remaining = memoryview(block)
    while remaining:
        pump()
        written = outgoing.write(remaining)
        pump()
        if written is None or written <= 0:
            raise OSError('incomplete save copy')
        remaining = remaining[written:]


def copy_offered_save(source, target, offer, *, pump):
    """Copy and check one offer without replacing an existing slot.

    ``source`` and ``target`` must be in exclusively controlled directories,
    including their parent paths. ``pump`` checks the owner's deadline and may
    maintain its connection; it runs between bounded I/O operations, but cannot
    interrupt an individual filesystem call. The target is created directly and
    can be visible while incomplete. If staging fails, the caller must continue
    fencing X4's save-list scan until any incomplete target is handled under
    its control. No target or source cleanup is attempted.
    The caller must separately verify the completed target before requesting
    an X4 load. No protection against concurrent path replacement or Windows
    reparse-point manipulation is provided; those are the caller's
    responsibility. Windows behavior has not been validated in a native run.
    """
    if type(offer) is not Offer or not callable(pump):
        raise ValueError('offer and owner pump required')
    source, target = Path(source), Path(target)
    if not _SLOT.fullmatch(target.name):
        raise ValueError('target must be an X4 compressed save slot')

    pump()
    before_path = os.lstat(source)
    if not stat.S_ISREG(before_path.st_mode):
        raise ValueError('downloaded save is not a regular file')
    source_flags = (os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_CLOEXEC', 0)
                    | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    source_fd = os.open(source, source_flags)
    try:
        incoming = os.fdopen(source_fd, 'rb', buffering=0)
        source_fd = -1
        with incoming:
            pump()
            before = os.fstat(incoming.fileno())
            pump()
            if not stat.S_ISREG(before.st_mode) or not same_path_and_descriptor(before_path, before):
                raise ValueError('downloaded save changed before copying')
            pump()
            target_flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
                            | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NOFOLLOW', 0))
            target_fd = os.open(target, target_flags, 0o600)
            try:
                pump()
                outgoing = os.fdopen(target_fd, 'wb', buffering=0)
                target_fd = -1
                with outgoing:
                    digest = hashlib.sha256()
                    size = 0
                    while True:
                        pump()
                        block = incoming.read(min(_CHUNK_SIZE, offer.size - size + 1))
                        pump()
                        if not block:
                            break
                        size += len(block)
                        if size > offer.size:
                            raise ValueError('downloaded save exceeds offer size')
                        digest.update(block)
                        _write_all(outgoing, block, pump)
                    after = os.fstat(incoming.fileno())
                    pump()
                    after_path = os.lstat(source)
                    pump()
                    if (not stat.S_ISREG(after.st_mode) or not stat.S_ISREG(after_path.st_mode) or
                            fingerprint(before) != fingerprint(after) or
                            fingerprint(before_path) != fingerprint(after_path) or
                            not same_path_and_descriptor(after_path, after) or
                            size != offer.size or digest.hexdigest() != offer.sha256):
                        raise ValueError('downloaded save changed or differs from offer')
                    outgoing.flush()
                    os.fsync(outgoing.fileno())
                    pump()
            finally:
                if target_fd >= 0:
                    os.close(target_fd)
    finally:
        if source_fd >= 0:
            os.close(source_fd)
    return target
