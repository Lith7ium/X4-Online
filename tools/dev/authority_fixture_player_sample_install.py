"""Install one disabled-by-default fixture writer into a private server case."""
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]
TOKEN = re.compile(r'[0-9a-f]{32}\Z')


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('fixture sample writer hook differs')
    return text.replace(old, new)


def install(case, profile, *, slot, port, epoch, generation, lease, attempt, nonce):
    """Configure one XYZ-only write under the existing server bridge update.

    The caller owns the fresh case, UDP socket, process, and source grant.
    Paths returned here must be protected before X4 starts. These private
    loopback capabilities are not network credentials or proof of frame parity.
    """
    tokens = (epoch, generation, lease, attempt, nonce)
    if (type(slot) is not int or slot not in (1, 2) or type(port) is not int or not 1 <= port <= 65535 or
            any(type(value) is not str or not TOKEN.fullmatch(value) for value in tokens) or len(set(tokens)) != 5):
        raise ValueError('invalid fixture sample writer configuration')
    case = Path(case).resolve(strict=True)
    profile = Path(profile).resolve(strict=True)
    if not profile.is_relative_to(case) or profile.name != '45841':
        raise ValueError('private server profile required')
    lab = case / 'extensions/x4_lan_lab'
    ui, md = lab / 'ui', lab / 'md'
    manifest, config = lab / 'ui.xml', ui / 'config.lua'
    bridge = ui / 'authority_world_bridge_probe.lua'
    source = (ROOT / 'tools/dev/authority_fixture_player_sample_writer.lua').read_text(encoding='utf-8')
    if not source.endswith('return M\n'):
        raise ValueError('fixture writer export changed')
    writer = ui / 'authority_fixture_player_sample_writer.lua'
    writer.write_text(source[:-len('return M\n')] + 'X4LAN_FIXTURE_PLAYER_SAMPLE_WRITER = M\nreturn M\n',
                      encoding='utf-8')
    bootstrap = ui / 'authority_fixture_player_sample_bootstrap.lua'
    cue = md / 'authority_fixture_local_offset.xml'
    resolver = ui / 'authority_registry_resolve_string.lua'
    for source_path, target in ((ROOT / 'tools/dev/authority_fixture_player_sample_bootstrap.lua', bootstrap),
                                (ROOT / 'tools/dev/authority_fixture_local_offset.xml', cue),
                                (ROOT / 'tools/dev/authority_registry_resolve_string.lua', resolver)):
        shutil.copyfile(source_path, target)
    hook = ' local ok,reason=bridge:update();assert(ok,reason)\n'
    bridge.write_text(replace_once(bridge.read_text(encoding='utf-8'), hook,
        hook + " assert(X4LAN_FIXTURE_SAMPLE_WRITE_TICK(),'fixture sample writer failed')\n"), encoding='utf-8')
    hook = '    <file name="ui/authority_world_bridge_probe.lua" />\n'
    manifest.write_text(replace_once(manifest.read_text(encoding='utf-8'), hook,
        '    <file name="ui/authority_registry_resolve_string.lua" />\n'
        '    <file name="ui/authority_fixture_player_sample_writer.lua" />\n'
        '    <file name="ui/authority_fixture_player_sample_bootstrap.lua" />\n' + hook), encoding='utf-8')
    original = config.read_text(encoding='ascii')
    if not original.endswith('}\n'):
        raise ValueError('unexpected private server configuration')
    settings = (f',authority_fixture_sample_write=true,fixture_sample_write_slot={slot},'
        f'fixture_sample_write_port={port},fixture_sample_write_epoch="{epoch}",'
        f'fixture_sample_write_generation="{generation}",fixture_sample_write_lease="{lease}",'
        f'fixture_sample_write_attempt="{attempt}",fixture_sample_write_nonce="{nonce}",'
        'fixture_sample_write_timeout=120')
    config.write_text(original[:-2] + settings + '}\n', encoding='ascii')
    return [writer, bootstrap, cue, resolver, bridge, manifest, config]


def verify_log(path, *, nonce, digest):
    """Check final local write and readback receipts after owned X4 cleanup."""
    import authority_saved_fixture_log as fixture_log
    if (type(nonce) is not str or not TOKEN.fullmatch(nonce) or type(digest) is not str or
            not re.fullmatch(r'[0-9a-f]{64}', digest)):
        raise ValueError('invalid fixture write evidence context')
    captured = fixture_log.capture(path, None, 32 << 20)
    if captured is None or not captured[2] or not captured[0].endswith(b'\n'):
        raise ValueError('fixture write log incomplete')
    raw = captured[0]
    lower = raw.lower()
    errors = (b'error while parsing expression:', b'maximum operator nesting level reached',
              b'error in md cue md.x4authority', b'error in lua script', b'stack traceback:',
              b'[x4lan] auth_world_bridge error', b'[x4lan] auth_fixture_sample_write error')
    if any(error in lower for error in errors):
        raise ValueError('fixture sample writer reported an engine error')
    tag = b'[X4LAN] AUTH_FIXTURE_SAMPLE_WRITE '
    receipts = [line.split(tag, 1)[1].strip() for line in raw.splitlines() if tag in line]
    expected = [('WRITE_ENTERED ' + nonce).encode('ascii'), ('OBSERVED ' + nonce + ' ' + digest).encode('ascii')]
    if receipts != expected:
        raise ValueError('fixture write receipts differ')
    return True
