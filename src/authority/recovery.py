"""Stage a confirmed checkpoint for an exclusively controlled X4 recovery.

This copies bytes only. It does not launch X4, prove which file X4 loaded, verify
its MD marker or admit clients. The caller must create and exclusively own a new
private profile directory and fence all writers and X4 processes using it.
"""
import hashlib
import os
from pathlib import Path
import stat

from .checkpoints import CHUNK, CheckpointError, CheckpointStore
from .marker_evidence import verify_saved_marker


def stage_confirmed_recovery(store, private_profile):
    """Copy the marked CONFIRMED checkpoint into a new private save_008 slot.

    The profile must be a new, empty, owner-only directory outside the checkpoint
    store. The caller is responsible for establishing that it is an isolated
    profile and not any normal X4 profile. This function cannot fence processes.
    It creates ``save/`` and exclusively creates ``save_008.xml.gz``; slot 009
    remains free for the normal experimental save controller. The returned pair
    is (verified checkpoint metadata, staged path). The saved marker and its
    reset load flag are checked, but no X4 load is performed or proven.
    """
    if not isinstance(store, CheckpointStore):
        raise ValueError('checkpoint store required')
    profile = Path(private_profile)
    if profile.is_symlink() or not profile.is_dir():
        raise ValueError('new private profile directory required')
    profile = profile.resolve(strict=True)
    if profile == store.directory or profile.is_relative_to(store.directory) or store.directory.is_relative_to(profile):
        raise ValueError('profile and checkpoint store must be separate')
    flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    root_fd = os.open(profile, flags)
    save_fd = None
    created_dir = created_file = False
    try:
        root_stat = os.fstat(root_fd)
        if (not stat.S_ISDIR(root_stat.st_mode) or root_stat.st_uid != os.geteuid()
                or stat.S_IMODE(root_stat.st_mode) != 0o700):
            raise ValueError('profile must be owner-only and owned by the caller')
        if os.listdir(root_fd):
            raise ValueError('private profile must be empty')
        checkpoint = store.latest_marked_confirmed()
        verify_saved_marker(checkpoint, checkpoint.marker,
                            script_name='X4AuthorityCheckpointMarker', cue_name='MarkerState')
        os.mkdir('save', 0o700, dir_fd=root_fd)
        created_dir = True
        save_fd = os.open('save', flags, dir_fd=root_fd)
        source_fd = os.open(checkpoint.path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        try:
            before = os.fstat(source_fd)
            if not stat.S_ISREG(before.st_mode):
                raise CheckpointError('checkpoint is not a regular file')
            dest_fd = os.open('save_008.xml.gz', os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600, dir_fd=save_fd)
            created_file = True
            with os.fdopen(dest_fd, 'w+b') as dest, os.fdopen(source_fd, 'rb') as source:
                source_fd = -1
                digest = hashlib.sha256()
                size = 0
                while True:
                    block = source.read(CHUNK)
                    if not block:
                        break
                    size += len(block)
                    if size > checkpoint.size:
                        raise CheckpointError('checkpoint grew during staging')
                    digest.update(block)
                    dest.write(block)
                after = os.fstat(source.fileno())
                if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
                        (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
                    raise CheckpointError('checkpoint changed during staging')
                if (digest.hexdigest(), size) != (checkpoint.sha256, checkpoint.size):
                    raise CheckpointError('staged source differs from confirmed checkpoint')
                dest.flush()
                os.fsync(dest.fileno())
                dest.seek(0)
                staged_digest = hashlib.sha256()
                while True:
                    block = dest.read(CHUNK)
                    if not block:
                        break
                    staged_digest.update(block)
                if staged_digest.hexdigest() != checkpoint.sha256:
                    raise CheckpointError('staged checkpoint does not match confirmed bytes')
        finally:
            if source_fd >= 0:
                os.close(source_fd)
        os.fsync(save_fd)
        os.fsync(root_fd)
        return checkpoint, profile / 'save' / 'save_008.xml.gz'
    except BaseException as error:
        # Caller guarantees exclusive ownership of the new profile throughout.
        if created_file and save_fd is not None:
            try:
                os.unlink('save_008.xml.gz', dir_fd=save_fd)
            except FileNotFoundError:
                pass
            except BaseException as cleanup_error:
                error.add_note(f'staged file cleanup failed: {type(cleanup_error).__name__}: {cleanup_error}')
        if created_dir:
            try:
                os.rmdir('save', dir_fd=root_fd)
            except FileNotFoundError:
                pass
            except BaseException as cleanup_error:
                error.add_note(f'staged directory cleanup failed: {type(cleanup_error).__name__}: {cleanup_error}')
        raise
    finally:
        if save_fd is not None:
            os.close(save_fd)
        os.close(root_fd)
