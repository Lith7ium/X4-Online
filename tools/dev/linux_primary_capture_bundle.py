"""Additive v20 closure for finite primary capture and scripted trigger experiments."""
import hashlib
from pathlib import Path

import linux_primary_trigger_bundle as previous
import linux_player_primary_trigger as primary
import linux_player_primary_capture as capture

SOURCE_VERSION = 20
PROVIDER = previous.PROVIDER
enabled = previous.enabled
collect = previous.collect
wrap_program = previous.wrap_program
SOURCES = tuple(dict.fromkeys(previous.SOURCES + primary.SOURCES + capture.SOURCES + (
    'tools/dev/linux_primary_capture_bundle.py',
)))
HELPERS = tuple(dict.fromkeys(previous.HELPERS + primary.HELPERS + capture.HELPERS + ('linux_primary_capture_bundle.py',)))


def source_paths(repo):
    paths = [Path(repo) / name for name in SOURCES]
    if any(path.is_symlink() or not path.is_file() for path in paths):
        raise ValueError('primary capture source closure incomplete')
    return paths


def validate_bundle(root, manifest, network):
    primary.enabled(manifest)
    active = capture.enabled(manifest)
    if manifest.get('view_query_source_version') != SOURCE_VERSION:
        if active:
            raise ValueError('primary capture requires source version 20')
        return previous.validate_bundle(root, manifest, network)
    files = manifest.get('files', {})
    for name in SOURCES:
        key = 'source-receipts/' + name
        path = Path(root) / key
        if (path.is_symlink() or not path.is_file() or
                hashlib.sha256(path.read_bytes()).hexdigest() != files.get(key)):
            raise ValueError('missing or changed primary capture source: ' + name)
    for name in HELPERS:
        path = Path(root) / name
        if (path.is_symlink() or not path.is_file() or files.get(name) != files.get('source-receipts/tools/dev/' + name) or
                hashlib.sha256(path.read_bytes()).hexdigest() != files.get(name)):
            raise ValueError('missing or changed primary capture helper: ' + name)
    return previous.validate_bundle(root, dict(manifest, view_query_source_version=19), network)
