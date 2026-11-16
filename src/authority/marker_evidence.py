"""Read-only evidence for the observed X4 MD marker save representation.

This validates a marker in saved bytes, not an X4 load or a multiplayer session.
The caller supplies the exact MD script and cue names for the intended schema.
Two streaming passes avoid retaining the game's potentially large string table.
"""
import gzip
import hashlib
import os
import re
import stat
import zlib
from xml.parsers import expat

from .checkpoints import Checkpoint, MAX_COMPRESSED, MAX_XML

_CHUNK = 64 * 1024
_MAX_DEPTH = 1024
_MAX_TOKEN = 4 * 1024 * 1024
_HEX = re.compile(r'[0-9a-f]{32}\Z')
_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,127}\Z')
_REF = re.compile(r'[0-9]{1,32}\Z')


class MarkerEvidenceError(ValueError):
    """The saved marker is missing, ambiguous, malformed or different."""


class _DigestReader:
    def __init__(self, raw):
        self.raw = raw
        self.digest = hashlib.sha256()
        self.size = 0

    def read(self, size=-1):
        block = self.raw.read(_CHUNK if size < 0 else min(size, _CHUNK))
        self.size += len(block)
        if self.size > MAX_COMPRESSED:
            raise MarkerEvidenceError('compressed save exceeds limit')
        self.digest.update(block)
        return block


def _parse(checkpoint, callback, *, characters=None):
    parser = expat.ParserCreate()
    path = []
    def start(name, attrs):
        path.append(name)
        if len(path) > _MAX_DEPTH:
            raise MarkerEvidenceError('XML nesting exceeds limit')
        if len(path) == 1 and name != 'savegame':
            raise MarkerEvidenceError('unexpected save root')
        callback(path, attrs)
    def end(_name):
        path.pop()
    def reject(*_args):
        raise MarkerEvidenceError('DTD and external entities are unsupported')
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    if characters is not None:
        parser.CharacterDataHandler = lambda value: characters(path, value)
    parser.StartDoctypeDeclHandler = reject
    parser.ExternalEntityRefHandler = reject
    fd = os.open(checkpoint.path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as raw:
        before = os.fstat(raw.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise MarkerEvidenceError('checkpoint is not a regular file')
        reader = _DigestReader(raw)
        total = 0
        with gzip.GzipFile(fileobj=reader, mode='rb') as stream:
            while True:
                block = stream.read(_CHUNK)
                if not block:
                    break
                total += len(block)
                if total > MAX_XML:
                    raise MarkerEvidenceError('decompressed save exceeds limit')
                parser.Parse(block, False)
                if total - parser.CurrentByteIndex > _MAX_TOKEN:
                    raise MarkerEvidenceError('XML token exceeds limit')
            parser.Parse(b'', True)
        after = os.fstat(raw.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise MarkerEvidenceError('checkpoint changed while reading')
        if (reader.digest.hexdigest(), reader.size) != (checkpoint.sha256, checkpoint.size):
            raise MarkerEvidenceError('checkpoint differs from verified digest')


def verify_saved_marker(checkpoint, expected, *, script_name, cue_name):
    """Verify one marker in X4 save bytes and raise on uncertainty.

    This recognizes the specific, observed ``script/refs`` and MD cue format;
    unknown or duplicate schema components fail. A successful return is evidence
    about these bytes only and does not confirm that any X4 process loaded them.
    """
    if (not isinstance(checkpoint, Checkpoint) or not isinstance(expected, str)
            or not _HEX.fullmatch(expected) or not isinstance(script_name, str)
            or not _NAME.fullmatch(script_name) or not isinstance(cue_name, str)
            or not _NAME.fullmatch(cue_name)):
        raise MarkerEvidenceError('invalid marker verification request')
    # Count all target containers, even if malformed or empty.
    scripts = cues = vars_count = values = loaded_values = 0
    active_script = active_cue = False
    reference = None
    def find_marker(path, attrs):
        nonlocal scripts, cues, vars_count, values, loaded_values, active_script, active_cue, reference
        if path == ['savegame', 'md', 'script']:
            active_script = attrs.get('name') == script_name
            active_cue = False
            if active_script:
                scripts += 1
        elif path == ['savegame', 'md', 'script', 'cue'] and active_script:
            active_cue = attrs.get('name') == cue_name
            if active_cue:
                cues += 1
        elif path == ['savegame', 'md', 'script', 'cue', 'vars'] and active_script and active_cue:
            vars_count += 1
        elif (path == ['savegame', 'md', 'script', 'cue', 'vars', 'value']
              and active_script and active_cue and attrs.get('name') == '$marker'):
            values += 1
            if attrs.get('type') != 'string' or not _REF.fullmatch(attrs.get('value', '')):
                raise MarkerEvidenceError('invalid marker reference')
            reference = attrs['value']
        elif (path == ['savegame', 'md', 'script', 'cue', 'vars', 'value']
              and active_script and active_cue and attrs.get('name') == '$loaded'):
            loaded_values += 1
            # Native X4 9.00 saves encode false as an integer without a value
            # attribute. Unknown encodings fail closed until verified.
            if attrs.get('type') != 'integer' or 'value' in attrs:
                raise MarkerEvidenceError('saved load flag is not confirmed false')
    try:
        _parse(checkpoint, find_marker)
        if (scripts, cues, vars_count, values, loaded_values) != (1, 1, 1, 1, 1):
            raise MarkerEvidenceError('missing or ambiguous marker cue')
        string_groups = 0
        active_strings = False
        matches = 0
        resolved = None
        def find_string(path, attrs):
            nonlocal string_groups, active_strings, matches, resolved
            if path == ['savegame', 'script', 'refs']:
                active_strings = attrs.get('type') == 'string'
                if active_strings:
                    string_groups += 1
            elif path == ['savegame', 'script', 'refs', 'ref'] and active_strings and attrs.get('id') == reference:
                matches += 1
                resolved = attrs.get('string')
        _parse(checkpoint, find_string)
        if string_groups != 1 or matches != 1 or resolved != expected:
            raise MarkerEvidenceError('missing, ambiguous or mismatched marker string')
    except MarkerEvidenceError:
        raise
    except (OSError, EOFError, expat.ExpatError, zlib.error) as exc:
        raise MarkerEvidenceError('saved marker could not be verified') from exc
    return True
