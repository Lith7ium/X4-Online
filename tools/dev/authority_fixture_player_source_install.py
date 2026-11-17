"""Install an opt-in player pose source into an existing private join overlay.

The supervisor owns the profile, checkpoint, process, UDP socket and grant;
this installer neither starts X4 nor proves client control or network delivery.
"""
import math
import os
import stat
from pathlib import Path
import re
import shutil

import authority_participant_client_authority_install as existing
import authority_saved_player_control_live as seat
from authority_load_live import lua_literal

ROOT = Path(__file__).resolve().parents[2]



class Installation:
    """Protected paths and post-process redaction for this overlay only."""
    def __init__(self, paths, config, secrets):
        self.paths = tuple(paths)
        self.config = config
        self.secrets = dict(secrets)
        current = config.lstat()
        self.identity = (current.st_dev, current.st_ino)

    def redact(self):
        # The caller must first stop X4 and finish all evidence checks.
        fd = os.open(self.config, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            current = os.fstat(fd)
            if (not stat.S_ISREG(current.st_mode) or
                    (current.st_dev, current.st_ino) != self.identity or current.st_size > 65536):
                raise ValueError('fixture source config ownership changed')
            raw = b''
            while len(raw) < current.st_size:
                chunk = os.read(fd, current.st_size - len(raw))
                if not chunk:
                    raise ValueError('incomplete fixture source config')
                raw += chunk
            after, path = os.fstat(fd), self.config.lstat()
            if ((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) !=
                    (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns, current.st_ctime_ns) or
                    (path.st_dev, path.st_ino) != self.identity or not stat.S_ISREG(path.st_mode)):
                raise ValueError('fixture source config changed during redaction')
            text = raw.decode('ascii')
            pattern = r'authority_fixture_player_source=\{([^{}]*)\}'
            matches = list(re.finditer(pattern, text))
            if len(matches) != 1:
                raise ValueError('fixture source block missing or ambiguous')
            match = matches[0]
            block = match.group(1)
            for key, value in self.secrets.items():
                original = key + '=' + lua_literal(value)
                if block.count(original) != 1:
                    raise ValueError('fixture source secret missing or ambiguous')
                block = block.replace(original, key + '=' + lua_literal('redacted'))
            text = text[:match.start(1)] + block + text[match.end(1):]
            data = text.encode('ascii')
            os.lseek(fd, 0, os.SEEK_SET)
            written = 0
            while written < len(data):
                count = os.write(fd, data[written:])
                if count <= 0:
                    raise OSError('short fixture source redaction')
                written += count
            os.ftruncate(fd, len(data))
        finally:
            os.close(fd)



def _write_config_transaction(config, original, replacement, paths, secrets):
    """Write secrets last and restore the owned file if a write fails.

    The caller must exclusively own this private profile while installing.
    Never restore through a path that was replaced during the operation.
    """
    fd = os.open(config, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        path = config.lstat()
        identity = (before.st_dev, before.st_ino)
        if (not stat.S_ISREG(before.st_mode) or not stat.S_ISREG(path.st_mode) or
                (path.st_dev, path.st_ino) != identity or before.st_size > 65536):
            raise ValueError('fixture source config ownership changed')
        contents = b''
        while len(contents) < before.st_size:
            chunk = os.read(fd, before.st_size - len(contents))
            if not chunk:
                raise ValueError('incomplete fixture source config')
            contents += chunk
        current = os.fstat(fd)
        if ((current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns, current.st_ctime_ns) !=
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) or
                contents != original):
            raise ValueError('fixture source config changed before installation')
        # Build the cleanup handle and set the private mode before any secret write.
        installation = Installation(paths, config, secrets)
        if installation.identity != identity:
            raise ValueError('fixture source config ownership changed')
        os.fchmod(fd, 0o600)

        def ensure_owned():
            descriptor = os.fstat(fd)
            path_stat = config.lstat()
            if (not stat.S_ISREG(descriptor.st_mode) or not stat.S_ISREG(path_stat.st_mode) or
                    (descriptor.st_dev, descriptor.st_ino) != identity or
                    (path_stat.st_dev, path_stat.st_ino) != identity):
                raise ValueError('fixture source config ownership changed during installation')

        def write_all(data):
            os.lseek(fd, 0, os.SEEK_SET)
            written = 0
            while written < len(data):
                count = os.write(fd, data[written:])
                if count <= 0:
                    raise OSError('short fixture source config write')
                written += count
            os.ftruncate(fd, len(data))

        try:
            ensure_owned()
            write_all(replacement)
            ensure_owned()
        except BaseException as failure:
            try:
                ensure_owned()
                write_all(original)
                ensure_owned()
            except BaseException as rollback_failure:
                raise BaseExceptionGroup('fixture source installation and rollback failed',
                                         [failure, rollback_failure]) from None
            raise
        return installation
    finally:
        os.close(fd)


def install(case, profile, *, slot, epoch, sector, lease, attempt, generation,
            bootstrap_nonce, sampler_nonce, port, timeout, interval=0.1, latest_cache=False, freeze_drain=False, throttle=None):
    tokens = (epoch, lease, attempt, generation, bootstrap_nonce, sampler_nonce)
    if (type(latest_cache) is not bool or type(freeze_drain) is not bool or
            (freeze_drain and not latest_cache) or type(slot) is not int or slot not in (1, 2) or
            any(type(v) is not str or not re.fullmatch(r'[0-9a-f]{32}', v) for v in tokens) or
            len(set(tokens)) != len(tokens) or bootstrap_nonce[:16] == sampler_nonce[:16] or
            type(sector) is not str or not re.fullmatch(r'[A-Za-z0-9_]{1,128}', sector) or
            type(port) is not int or not 1 <= port <= 65535 or
            any(type(v) not in (int, float) or not math.isfinite(v) for v in (timeout, interval)) or
            not 0 < timeout <= 120 or not 0 < interval <= 60):
        raise ValueError('invalid fixture source context')
    if throttle is not None:
        if (type(throttle) is not dict or set(throttle) != {'port', 'lease', 'attempt', 'nonce', 'timeout'} or
                type(throttle['port']) is not int or not 1 <= throttle['port'] <= 65535 or
                type(throttle['timeout']) not in (int, float) or not math.isfinite(throttle['timeout']) or
                not 3 <= throttle['timeout'] <= 15 or
                any(type(throttle[key]) is not str or not re.fullmatch(r'[0-9a-f]{32}', throttle[key])
                    for key in ('lease', 'attempt', 'nonce')) or
                len(set(tokens + tuple(throttle[key] for key in ('lease', 'attempt', 'nonce')))) != 9):
            raise ValueError('invalid fixture throttle context')
        throttle = dict(throttle)
    case = Path(case).resolve(strict=True)
    profile = Path(profile).resolve(strict=True)
    if not profile.is_relative_to(case) or profile.name != '45841':
        raise ValueError('private fixture profile required')
    lab = case / 'extensions/x4_lan_lab'
    ui, md = lab / 'ui', lab / 'md'
    manifest, config = lab / 'ui.xml', ui / 'config.lua'
    loader, participant = ui / 'authority_download_load_probe.lua', ui / 'authority_two_x4_participant_probe.lua'
    manifest_text = manifest.read_text(encoding='utf-8')
    config_text = config.read_text(encoding='ascii')
    original_config = config_text.encode('ascii')
    loader_text = loader.read_text(encoding='utf-8')
    participant_text = participant.read_text(encoding='utf-8')
    if not config_text.endswith('}\n'):
        raise ValueError('unexpected private configuration')
    gate = '  if not X4LAN_REGISTERED_PLAYER_CONTROL_TICK() then return end\n'
    loader_text = seat.replace_once(loader_text, gate, gate + '  X4LAN_FIXTURE_SEAT_READY=true\n')
    participant_text = seat.replace_once(participant_text, ' assert(state:on_update())\n',
        ''' assert(state:on_update())
 if not fixture_source then
  fixture_source=assert(X4LAN_FIXTURE_PLAYER_SOURCE.new_x4(cfg.authority_fixture_player_source))
 end
 assert(fixture_source:tick())
''')
    participant_text = seat.replace_once(participant_text,
        'local net,state,engine,next_hello,failed=nil,nil,nil,0,false\n',
        'local net,state,engine,next_hello,failed=nil,nil,nil,0,false\nlocal fixture_source\n')
    scripts = (*existing.SCRIPTS, ('tools/dev/authority_fixture_player_source.lua', 'authority_fixture_player_source.lua'))
    if latest_cache:
        scripts += (('src/authority/lua/fixture_player_latest_cache.lua', 'fixture_player_latest_cache.lua'),)
    if freeze_drain:
        scripts += (('src/authority/lua/fixture_player_freeze_barrier.lua', 'fixture_player_freeze_barrier.lua'),)
    throttle_cue = None
    if throttle is not None:
        scripts += (('tools/dev/authority_fixture_client_throttle.lua', 'authority_fixture_client_throttle.lua'),
                    ('tools/dev/authority_fixture_client_throttle_driver.lua', 'authority_fixture_client_throttle_driver.lua'))
        throttle_cue = md / 'authority_fixture_client_throttle.xml'
    hook = '    <file name="ui/authority_download_load_probe.lua" />\n'
    additions = ''.join('    <file name="ui/' + target + '" />\n' for _, target in scripts)
    manifest_text = seat.replace_once(manifest_text, hook, additions + hook)
    values = dict(slot=slot, epoch=epoch, sector=sector, lease=lease, attempt=attempt,
                  generation=generation, bootstrap_nonce=bootstrap_nonce, sampler_nonce=sampler_nonce,
                  port=port, timeout=timeout, interval=interval, save_path=str(profile / 'save'))
    if throttle is not None:
        values.update(throttle_port=throttle['port'], throttle_lease=throttle['lease'],
                      throttle_attempt=throttle['attempt'], throttle_nonce=throttle['nonce'],
                      throttle_timeout=throttle['timeout'])
    config_text = (config_text[:-2] + ',authority_fixture_player_source={' + ','.join(
        key + '=' + (lua_literal(value) if isinstance(value, str) else format(value, '.17g'))
        for key, value in values.items()) + (',latest_cache=true' if latest_cache else '') +
        (',freeze_drain=true' if freeze_drain else '') +
        (',throttle_enabled=true' if throttle is not None else '') + '}}\n')
    installed = []
    for source, name in scripts:
        target = ui / name
        shutil.copyfile(ROOT / source, target)
        installed.append(target)
    if throttle_cue is not None:
        shutil.copyfile(ROOT / 'tools/dev/authority_fixture_client_throttle.xml', throttle_cue)
    cue = md / 'authority_job_descriptor_probe.xml'
    shutil.copyfile(ROOT / 'tools/dev/authority_job_descriptor_probe.xml', cue)
    loader.write_text(loader_text, encoding='utf-8')
    participant.write_text(participant_text, encoding='utf-8')
    manifest.write_text(manifest_text, encoding='utf-8')
    secrets = {name: values[name] for name in
               ('epoch', 'lease', 'attempt', 'generation', 'bootstrap_nonce', 'sampler_nonce')}
    if throttle is not None:
        secrets.update({name: values[name] for name in ('throttle_lease', 'throttle_attempt', 'throttle_nonce')})
    return _write_config_transaction(config, original_config, config_text.encode('ascii'),
                                     [*installed, cue, *([throttle_cue] if throttle_cue else []), loader, participant, manifest, config], secrets)
