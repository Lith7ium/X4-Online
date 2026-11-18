"""Disposable X4 profiles (-personalfolderid) for launcher clients.

Only the ids in PROFILES and CAPTURE_PROFILE are accepted; the player's own
Steam-id profile is refused. The existing prepare() resets a client profile;
prepare_fresh() instead creates an absent profile without deleting old files.
"""
import ctypes
import os
from pathlib import Path
import re
import shutil
import stat
import sys

PROFILES = (45850, 45851, 45853, 45854, 45855, 45856, 45857, 45858)
CAPTURE_PROFILE = 45841  # tools/dev/native_gate_snapshot.lua only saves inside .../45841/save
SNAPSHOT_SLOT = 'save_009.xml.gz'


class _KnownFolderId(ctypes.Structure):
    _fields_ = [
        ('data1', ctypes.c_uint32),
        ('data2', ctypes.c_uint16),
        ('data3', ctypes.c_uint16),
        ('data4', ctypes.c_ubyte * 8),
    ]


_FOLDERID_DOCUMENTS = _KnownFolderId(
    0xFDD39AD0, 0x238F, 0x46AF,
    (0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7),
)


def _windows_documents_directory():
    """Resolve the current user's Documents folder through Windows Known Folders."""
    shell32 = ctypes.WinDLL('shell32')
    ole32 = ctypes.WinDLL('ole32')
    get_known_folder_path = shell32.SHGetKnownFolderPath
    get_known_folder_path.argtypes = [
        ctypes.POINTER(_KnownFolderId), ctypes.c_uint32, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    get_known_folder_path.restype = ctypes.c_int32
    free_task_memory = ole32.CoTaskMemFree
    free_task_memory.argtypes = [ctypes.c_void_p]
    free_task_memory.restype = None

    path_pointer = ctypes.c_void_p()
    try:
        result = get_known_folder_path(
            ctypes.byref(_FOLDERID_DOCUMENTS), 0, None, ctypes.byref(path_pointer),
        )
        if result < 0:
            raise OSError(f'SHGetKnownFolderPath failed with HRESULT 0x{result & 0xFFFFFFFF:08X}')
        if not path_pointer.value:
            raise OSError('SHGetKnownFolderPath succeeded without returning a path')
        path_text = ctypes.wstring_at(path_pointer.value)
        if not path_text:
            raise OSError('SHGetKnownFolderPath returned an empty path')
        return Path(path_text)
    finally:
        if path_pointer.value:
            free_task_memory(path_pointer)


def documents():
    if sys.platform == 'win32':
        documents_directory = _windows_documents_directory()
    else:
        documents_directory = Path(os.environ['USERPROFILE']) / 'Documents'
    return documents_directory / 'Egosoft' / 'X4'


def profile_dir(profile, root=None):
    if profile not in (*PROFILES, CAPTURE_PROFILE):
        raise SystemExit(f'profile {profile} is not a disposable launcher profile')
    path = (Path(root) if root else documents()) / str(profile)
    if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
        raise SystemExit(f'{path} is a link; refusing')
    return path


# Render-only settings turned down for unattended soaks (--fast): more frames per second means more
# admitted ticks per second. Detail distances (lodfactor, effectdistance) stay at 1.0 because they can
# change what the simulation does; every client gets identical settings either way.
FAST = {'gfxquality': 0, 'shaderquality': 0, 'shadows': 0, 'softshadows': 'false', 'ssao': 0, 'glow': 0, 'uiglow': 0,
        'distortion': 'false', 'ssr': 'false', 'texturequality': 'low', 'chromaticaberration': 'false', 'volumetric': 0,
        'pom': 'off', 'envmapprobes': 'low', 'frameratelimit': 'false', 'presentmode': 'immediate', 'nosound': 'true'}


def config_xml(width, height, fast=False, borderless=False):
    """borderless: X4's borderless window (it fills the screen and cannot be resized: a resize reloads X4's UI)."""
    extra = ''.join(f'<{k}>{v}</{k}>' for k, v in FAST.items()) if fast else ''
    return ('<?xml version="1.0"?><root><autosave>false</autosave><uisafemode>false</uisafemode>'
            f'<fullscreen>false</fullscreen><borderless>{"true" if borderless else "false"}</borderless><res_width>{width}</res_width>'
            f'<res_height>{height}</res_height><antialiasing>0</antialiasing><vsync>false</vsync>{extra}</root>\n')


def content_xml(extension_ids):
    rows = ''.join(f'<extension id="{name}" enabled="true" />' for name in extension_ids)
    return f'<?xml version="1.0"?><content>{rows}</content>\n'


def prepare(profile, extension_ids, width=1280, height=720, snapshot=None, root=None, fast=False, borderless=False):
    """Fresh profile: windowed config, autosave and protected UI off, optional snapshot."""
    path = profile_dir(profile, root)
    if path.exists():
        shutil.rmtree(path)
    (path / 'save').mkdir(parents=True)
    (path / 'config.xml').write_text(config_xml(width, height, fast, borderless))
    (path / 'content.xml').write_text(content_xml(extension_ids))
    if snapshot:
        shutil.copyfile(snapshot, path / 'save' / SNAPSHOT_SLOT)
    return path


def _valid_profile_root(info, *, windows):
    """Reject links and, on Windows, all final-component reparse points."""
    if not stat.S_ISDIR(info.st_mode):
        return False
    if windows:
        reparse_point = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', None)
        attributes = getattr(info, 'st_file_attributes', None)
        if (type(reparse_point) is not int or reparse_point <= 0 or
                type(attributes) is not int or attributes < 0):
            return False
        if attributes & reparse_point:
            return False
    return True


def prepare_fresh(profile, extension_ids, *, root, width=1280, height=720,
                  fast=False, borderless=False):
    """Create an absent disposable profile without removing existing files.

    This is for experiments whose supervisor exclusively controls ``root``,
    its ancestors and the new profile throughout preparation and use. The
    root must already exist; no save is staged. A failure after directory
    creation can leave a partial profile, which the caller must inspect
    rather than reuse. This does not guard against another process replacing
    a directory during preparation.
    """
    if (type(profile) is not int or profile not in (*PROFILES, CAPTURE_PROFILE) or
            type(extension_ids) not in (list, tuple) or
            any(type(name) is not str or not re.fullmatch(r'[A-Za-z0-9_]+', name)
                for name in extension_ids) or
            type(width) is not int or not 320 <= width <= 16384 or
            type(height) is not int or not 200 <= height <= 16384 or
            type(fast) is not bool or type(borderless) is not bool):
        raise ValueError('invalid disposable profile configuration')
    root = Path(root)
    try:
        root_info = root.lstat()
    except OSError as exc:
        raise ValueError('existing, non-link profile root required') from exc
    if not _valid_profile_root(root_info, windows=os.name == 'nt'):
        raise ValueError('existing, non-link profile root required')
    path = profile_dir(profile, root)
    # mkdir without exist_ok is the ownership boundary: existing directories,
    # links and files all fail without modifying them.
    path.mkdir()
    (path / 'save').mkdir()
    with (path / 'config.xml').open('x', encoding='utf-8', newline='\n') as output:
        output.write(config_xml(width, height, fast, borderless))
    with (path / 'content.xml').open('x', encoding='utf-8', newline='\n') as output:
        output.write(content_xml(extension_ids))
    return path


def unstage(profile, root=None):
    """Remove the snapshot prepare() staged: the lane tool shares these profiles and refuses to overwrite a staged save."""
    staged = profile_dir(profile, root) / 'save' / SNAPSHOT_SLOT
    if staged.is_file():
        staged.unlink()
        return True
    return False


def collect(profile, logfile, out, root=None):
    """Copy the client's log (and any saves it wrote) into the run directory."""
    path = profile_dir(profile, root)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if (path / logfile).is_file():
        shutil.copy2(path / logfile, out / 'engine-output.log')  # the name the census tools read
    if (path / 'x4lan-crash.txt').is_file():  # the crash note (native_gate_crash_note): an unhandled exception's CRASH line
        shutil.copy2(path / 'x4lan-crash.txt', out / 'x4lan-crash.txt')
    saves = [p for p in (path / 'save').glob('*') if p.is_file() and p.name != SNAPSHOT_SLOT] if (path / 'save').is_dir() else []   # files only: a hot join's save/mpjoin stays
    for save in saves:
        shutil.copy2(save, out / save.name)
