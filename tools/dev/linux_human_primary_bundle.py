"""Additive v21 closure for finite human primary replay; no wire schema changes."""
import hashlib
from pathlib import Path

import linux_primary_capture_bundle as previous
import linux_player_primary_trigger as primary
import linux_player_primary_capture as capture

SOURCE_VERSION = 21
PROVIDER = previous.PROVIDER
enabled = previous.enabled
collect = previous.collect
wrap_program = previous.wrap_program
SOURCES = tuple(dict.fromkeys(previous.SOURCES + primary.SOURCES + capture.SOURCES + (
    'tools/dev/linux_human_primary_bundle.py',
    'src/native/engine/linux/test_stock_keyboard_primary.c',
    'src/native/engine/linux/player_primary_human.md',
    'tests/test_linux_player_primary_human.py',
)))
HELPERS = tuple(dict.fromkeys(previous.HELPERS + primary.HELPERS + capture.HELPERS + ('linux_human_primary_bundle.py',)))


def source_paths(repo):
    paths = [Path(repo) / name for name in SOURCES]
    if any(path.is_symlink() or not path.is_file() for path in paths):
        raise ValueError('human primary source closure incomplete')
    return paths


def validate_bundle(root, manifest, network):
    primary.enabled(manifest)
    capture.enabled(manifest)
    active = primary.human_enabled(manifest)
    if manifest.get('view_query_source_version') != SOURCE_VERSION:
        if active:
            raise ValueError('human primary requires source version 21')
        return previous.validate_bundle(root, manifest, network)
    files = manifest.get('files', {})
    for name in SOURCES:
        key = 'source-receipts/' + name
        path = Path(root) / key
        if (path.is_symlink() or not path.is_file() or
                hashlib.sha256(path.read_bytes()).hexdigest() != files.get(key)):
            raise ValueError('missing or changed human primary source: ' + name)
    for name in HELPERS:
        path = Path(root) / name
        if (path.is_symlink() or not path.is_file() or files.get(name) != files.get('source-receipts/tools/dev/' + name) or
                hashlib.sha256(path.read_bytes()).hexdigest() != files.get(name)):
            raise ValueError('missing or changed human primary helper: ' + name)
    return previous.validate_bundle(root, dict(manifest, view_query_source_version=20), network)
