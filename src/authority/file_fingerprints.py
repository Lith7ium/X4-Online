"""Compare regular-file observations made through a path and a descriptor.

On Windows, CPython can report different ctime values for the same file via
lstat and fstat. Those values must still be compared between observations made
by the same API, but are not necessarily comparable across the two APIs.
"""
import os

_WINDOWS = os.name == 'nt'


def fingerprint(info):
    """Return the full fingerprint for comparing like-for-like observations."""
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def same_path_and_descriptor(path_info, descriptor_info):
    """Compare the fields available from both observation methods.

    Callers must separately compare full path fingerprints over time and full
    descriptor fingerprints over time, including their respective ctimes.
    Directory and reparse-point ownership remains the caller's responsibility.
    """
    path_fingerprint = fingerprint(path_info)
    descriptor_fingerprint = fingerprint(descriptor_info)
    if _WINDOWS:
        return path_fingerprint[:-1] == descriptor_fingerprint[:-1]
    return path_fingerprint == descriptor_fingerprint
