"""Build a Windows load/participant overlay for isolated fixture diagnostics.

The saved checkpoint must contain the two identity-fixture ships and the
checkpoint marker used by the existing Linux diagnostic. This does not start
X4, establish process ownership, authenticate log messages or admit a player.
The caller must establish that the supplied path names the intended private
physical profile before installation and X4 startup; a path ending in
``45841/save`` can also name an ordinary profile. The caller owns the view,
profile and their ancestors, and keeps them exclusive throughout use. The
participant probe can listen before marker and identity observations complete:
the caller must withhold all commands until correlated admission. The config
contains a plaintext ticket and lease; the caller must restrict access using
private ACLs and securely clean up its owned configuration after X4 stops.
Checks here cannot prevent concurrent replacement or establish these duties.
"""
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat

from .trusted_load_messages import encode_bound_offer
from .client_registry_overlay import extend_load_probe
from lockstep.launcher import extension

ROOT = Path(__file__).resolve().parents[2]
_HEX32 = re.compile(r'[0-9a-f]{32}\Z')
_HEX64 = re.compile(r'[0-9a-f]{64}\Z')
_MAX_DLL = 8 * 1024 * 1024
_FIELDS = ('world_epoch', 'connection_handle', 'baseline_id', 'load_generation',
           'checkpoint_id', 'sha256', 'attempt_id', 'slot')


def _ordinary(path, *, directory):
    info = path.lstat()
    if ((directory and not stat.S_ISDIR(info.st_mode)) or
            (not directory and not stat.S_ISREG(info.st_mode))):
        raise ValueError('expected ordinary file or directory')
    # Reparse metadata is exposed by Windows Python 3.11 even when
    # pathlib.Path.is_junction is unavailable.
    if hasattr(info, 'st_file_attributes'):
        reparse = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', None)
        attributes = info.st_file_attributes
        if (type(reparse) is not int or reparse <= 0 or type(attributes) is not int or
                attributes < 0 or attributes & reparse):
            raise ValueError('reparse point not permitted')
    elif os.name == 'nt':
        raise ValueError('Windows reparse attributes unavailable')
    return info


def _source(path, maximum):
    info = _ordinary(path, directory=False)
    if not 0 < info.st_size <= maximum:
        raise ValueError('invalid source size')
    data = path.read_bytes()
    if len(data) != info.st_size:
        raise ValueError('source changed while reading')
    return data


def _windows_save_path(value):
    if (type(value) is not str or not value or
            any(ord(character) < 32 or ord(character) > 126 for character in value)):
        raise ValueError('ASCII Windows save path required')
    path = PureWindowsPath(value)
    if (not path.is_absolute() or '..' in path.parts or len(path.parts) < 3 or
            path.name.lower() != 'save' or path.parent.name != '45841'):
        raise ValueError('Windows profile-45841 save path syntax required')
    return value


def install_fixture_overlay(view, *, new_test_view, bound_offer, save_path,
                            participant_port, participant_lease, windows_dll, dll_sha256,
                            registry_status=None, registry_nonce=None):
    """Create one absent x4_lan_lab in an exclusively owned new test view.

    A failure after creation leaves an owned partial extension for inspection;
    this function never deletes or overwrites it. Its returned SHA-256 map is
    only a snapshot: the caller must guard these files and the view until X4
    stops. The DLL digest must come from a separately verified trusted source.
    The save-path check is syntactic; the caller must independently establish
    that it resolves to the intended private physical profile. Before the
    ordered observations and correlated admission, the caller must not send
    participant commands even though the UDP probe may already be listening.
    The caller must protect the plaintext ticket and lease with private ACLs
    and clean up the owned configuration after X4 stops.
    Optional registry status must come from the verified offered checkpoint;
    the Lua gate checks its epoch/count before the ordinary pause receipt.
    """
    if new_test_view is not True:
        raise ValueError('exclusive new test view required')
    encode_bound_offer(bound_offer)  # validates the immutable offer and marker
    offer = bound_offer.offer
    if (not _HEX32.fullmatch(offer.world_epoch) or
            type(participant_port) is not int or not 1 <= participant_port <= 65535 or
            type(participant_lease) is not str or not _HEX32.fullmatch(participant_lease) or
            type(dll_sha256) is not str or not _HEX64.fullmatch(dll_sha256)):
        raise ValueError('invalid participant or DLL configuration')
    save_path = _windows_save_path(save_path)
    view = Path(view)
    windows_dll = Path(windows_dll)
    if not view.is_absolute() or not windows_dll.is_absolute():
        raise ValueError('absolute view and DLL paths required')
    _ordinary(view, directory=True)
    _ordinary(view / '.x4ls-view', directory=False)
    extensions = view / 'extensions'
    _ordinary(extensions, directory=True)
    dll = _source(windows_dll, _MAX_DLL)
    if not dll.startswith(b'MZ') or hashlib.sha256(dll).hexdigest() != dll_sha256:
        raise ValueError('Windows DLL does not match trusted digest')
    sources = {
        'ui/sha256.lua': ROOT / 'src/lockstep/base/ui/sha256.lua',
        'ui/client_load_barrier.lua': ROOT / 'src/authority/lua/client_load_barrier.lua',
        'ui/x4_client_load_engine.lua': ROOT / 'src/authority/lua/x4_client_load_engine.lua',
        'ui/authority_identity_probe.lua': ROOT / 'tools/dev/authority_identity_probe.lua',
        'ui/authority_checkpoint_marker_probe.lua': ROOT / 'tools/dev/authority_checkpoint_marker_probe.lua',
        'ui/authority_download_load_probe.lua': ROOT / 'tools/dev/authority_download_load_probe.lua',
        'ui/authority_control_state.lua': ROOT / 'src/authority/lua/control_state.lua',
        'ui/x4_control_engine.lua': ROOT / 'src/authority/lua/x4_control_engine.lua',
        'ui/local_udp_module.lua': ROOT / 'src/authority/lua/local_udp_module.lua',
        'ui/authority_two_x4_participant_probe.lua': ROOT / 'tools/dev/authority_two_x4_participant_probe.lua',
        'md/authority_identity_fixture.xml': ROOT / 'tools/dev/authority_identity_fixture.xml',
        'md/authority_checkpoint_marker.xml': ROOT / 'tools/dev/authority_checkpoint_marker.xml',
    }
    files = {name: _source(path, 1024 * 1024) for name, path in sources.items()}
    load_probe = files['ui/authority_download_load_probe.lua']
    hook = b" elseif state=='observing' then\n"
    if load_probe.count(hook) != 1:
        raise ValueError('unexpected load probe hook')
    files['ui/authority_download_load_probe.lua'] = load_probe.replace(
        hook, hook + b'  if not X4LAN_AUTHORITY_MARKER_READY() then return end\n'
                     b'  if not X4LAN_IDENTITY_READY() then return end\n')
    if registry_status is not None or registry_nonce is not None:
        files['ui/authority_download_load_probe.lua'] = extend_load_probe(
            files['ui/authority_download_load_probe.lua'].decode('utf-8'),
            registry_nonce, registry_status).encode('utf-8')
        for target, source in (
                ('ui/recovery_registry_status.lua', 'src/authority/lua/recovery_registry_status.lua'),
                ('md/authority_ship_registry.xml', 'tools/dev/authority_ship_registry.xml')):
            files[target] = _source(ROOT / source, 1024 * 1024)
    udp = files['ui/local_udp_module.lua']
    if udp.count(b'return M\n') != 1:
        raise ValueError('unexpected UDP module export')
    files['ui/local_udp_module.lua'] = udp.replace(b'return M\n', b'X4LAN_LOCAL_UDP_MODULE=M\nreturn M\n')
    ticket = {field: getattr(offer, field) for field in _FIELDS if field != 'slot'}
    ticket['slot'] = 'save_009'
    def lua_string(value):
        return json.dumps(value, ensure_ascii=True)
    ticket_lua = ','.join(key + '=' + (str(ticket[key]) if type(ticket[key]) is int else lua_string(ticket[key]))
                          for key in _FIELDS)
    config = ('X4LAN_CONFIG = {enabled=false,test_profile="45841",authority_download_load=true,'
              'authority_identity_phase="load",authority_marker_phase="load",'
              f'authority_load_save_path={lua_string(save_path)},authority_ticket={{{ticket_lua}}},'
              f'authority_participant_port={participant_port},authority_participant_lease={lua_string(participant_lease)}' + '}\n')
    ui_files = [name for name in sources if name.startswith('ui/')]
    if registry_status is not None:
        ui_files.insert(ui_files.index('ui/authority_download_load_probe.lua'),
                        'ui/recovery_registry_status.lua')
    files.update({'ui/config.lua': config.encode('ascii'),
                  'ui.xml': extension.ui_xml(ui_files).encode('utf-8'),
                  'content.xml': extension.CONTENT.encode('utf-8'),
                  'native/x4lan_net_64.dll': dll})
    target = extensions / extension.EXTENSION_ID
    target.mkdir()  # exclusive: an existing extension is never changed
    for name in ('ui', 'md', 'native'):
        (target / name).mkdir()
    for name, data in files.items():
        with (target / name).open('xb') as output:
            output.write(data)
    return {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
