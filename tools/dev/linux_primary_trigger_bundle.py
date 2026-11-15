"""Additive v19 closure for the finite scripted primary trigger experiment."""
import hashlib
from pathlib import Path

import linux_semaphore_observer_bundle as previous
import linux_player_primary_trigger as primary

SOURCE_VERSION = 19
PROVIDER = previous.PROVIDER
enabled = previous.enabled
collect = previous.collect
wrap_program = previous.wrap_program
SOURCES = tuple(dict.fromkeys(previous.SOURCES + primary.SOURCES + (
    'tools/dev/linux_primary_trigger_bundle.py',
)))
HELPERS = tuple(dict.fromkeys(previous.HELPERS + primary.HELPERS + ('linux_primary_trigger_bundle.py',)))


def source_paths(repo):
    paths = [Path(repo) / name for name in SOURCES]
    if any(path.is_symlink() or not path.is_file() for path in paths):
        raise ValueError('primary trigger source closure incomplete')
    return paths


def validate_bundle(root, manifest, network):
    active = primary.enabled(manifest)
    if manifest.get('view_query_source_version') != SOURCE_VERSION:
        if active:
            raise ValueError('primary trigger requires source version 19')
        return previous.validate_bundle(root, manifest, network)
    files = manifest.get('files', {})
    for name in SOURCES:
        key = 'source-receipts/' + name
        path = Path(root) / key
        if (path.is_symlink() or not path.is_file() or
                hashlib.sha256(path.read_bytes()).hexdigest() != files.get(key)):
            raise ValueError('missing or changed primary trigger source: ' + name)
    for name in HELPERS:
        path = Path(root) / name
        if (path.is_symlink() or not path.is_file() or files.get(name) != files.get('source-receipts/tools/dev/' + name) or
                hashlib.sha256(path.read_bytes()).hexdigest() != files.get(name)):
            raise ValueError('missing or changed primary trigger helper: ' + name)
    return previous.validate_bundle(root, dict(manifest, view_query_source_version=18), network)
