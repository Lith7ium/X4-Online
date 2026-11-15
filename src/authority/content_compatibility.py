"""Experimental comparison of supplied content descriptions; no I/O or admission.

The caller must obtain and authenticate both descriptions separately. Equal
descriptions do not prove that X4 loaded that content, or that either game is
compatible. Platform-specific executable hashes are intentionally not compared.
"""
from dataclasses import dataclass
import re

_ID = re.compile(r'[A-Za-z0-9_.-]{1,128}\Z')
_VERSION = re.compile(r'(?:0|[1-9][0-9]{0,11})\Z')
_SCHEME = re.compile(r'[A-Za-z0-9_.-]{1,64}\Z')
_SHA256 = re.compile(r'[0-9a-f]{64}\Z')
_FIELDS = {'schema', 'game_version', 'game_build', 'extensions', 'scripts'}
_OPTIONAL = {'platform', 'executable_sha256'}
_MAX_EXTENSIONS = 1024
SUPPORTED_SCRIPT_SCHEME = 'x4-authority-shared-scripts-v1'


@dataclass(frozen=True)
class Comparison:
    """`equal`, `different`, or `unconfirmed`; reasons contain no source paths."""
    status: str
    reasons: tuple[str, ...]


def _parse(value, side):
    errors = []
    if type(value) is not dict:
        return None, [side + ': manifest missing or not an object']
    if set(value) - (_FIELDS | _OPTIONAL):
        errors.append(side + ': unsupported manifest fields')
    if type(value.get('schema')) is not int or value['schema'] != 1:
        errors.append(side + ': missing or unsupported schema')
    for field in ('game_version', 'game_build'):
        item = value.get(field)
        if type(item) is not str or not _VERSION.fullmatch(item):
            errors.append(side + ': missing or invalid ' + field)
    if 'platform' in value and (type(value['platform']) is not str or
                                value['platform'] not in ('linux', 'windows')):
        errors.append(side + ': invalid platform')
    if 'executable_sha256' in value and (type(value['executable_sha256']) is not str or
                                         not _SHA256.fullmatch(value['executable_sha256'])):
        errors.append(side + ': invalid executable_sha256')

    scripts = value.get('scripts')
    if (type(scripts) is not dict or set(scripts) != {'scheme', 'sha256'} or
            type(scripts.get('scheme')) is not str or not _SCHEME.fullmatch(scripts['scheme']) or
            type(scripts.get('sha256')) is not str or not _SHA256.fullmatch(scripts['sha256'])):
        errors.append(side + ': missing or invalid shared script digest')
    elif scripts['scheme'] != SUPPORTED_SCRIPT_SCHEME:
        errors.append(side + ': unsupported shared script digest scheme')

    extensions = value.get('extensions')
    normalized = {}
    if type(extensions) is not list or len(extensions) > _MAX_EXTENSIONS:
        errors.append(side + ': missing or invalid active extensions')
    else:
        for row in extensions:
            if (type(row) is not dict or set(row) != {'id', 'version'} or
                    type(row.get('id')) is not str or not _ID.fullmatch(row['id']) or
                    type(row.get('version')) is not str or not _VERSION.fullmatch(row['version'])):
                errors.append(side + ': invalid active extension')
                break
            if row['id'] in normalized:
                errors.append(side + ': duplicate active extension ID')
                break
            normalized[row['id']] = row['version']
    if errors:
        return None, errors
    return (value['game_version'], value['game_build'], scripts['scheme'], scripts['sha256'], normalized), []


def compare(host, client):
    """Compare two supplied schema-1 manifests without accessing the filesystem.

    Empty extension lists are valid only if the producer positively observed
    that no extensions are active; `None` and omitted lists are unconfirmed.
    Optional platform/executable fields are checked for shape but ignored when
    comparing: platform-specific executable identities need separate validation.
    """
    left, left_errors = _parse(host, 'host')
    right, right_errors = _parse(client, 'client')
    if left_errors or right_errors:
        return Comparison('unconfirmed', tuple(left_errors + right_errors))
    reasons = []
    for offset, label in enumerate(('game version', 'game build', 'script digest scheme', 'shared script digest')):
        if left[offset] != right[offset]:
            reasons.append(label + ' differs')
    for name in sorted(left[4].keys() - right[4].keys()):
        reasons.append('client missing active extension: ' + name)
    for name in sorted(right[4].keys() - left[4].keys()):
        reasons.append('client has extra active extension: ' + name)
    for name in sorted(left[4].keys() & right[4].keys()):
        if left[4][name] != right[4][name]:
            reasons.append('active extension version differs: ' + name)
    if reasons:
        return Comparison('different', tuple(reasons))
    return Comparison('equal', ())
