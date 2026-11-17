"""Opt-in private fixture helpers for the recovered overlapping-client test.

The fixture is limited to its original two undocked ships and four-entry
registry. It does not prove real gameplay, general reconnect or multiplayer.
"""
from pathlib import Path
import shutil

import authority_fixture_checkpoint_source as fixture_source
import authority_player_sector_evidence as fixture_evidence
import authority_recovery_bridge_live as bridge
import authority_recovered_server_client as server_client
import authority_saved_fixture_log as fixture_log

MARKER_SCRIPT = 'X4AuthorityPlayerFixtureMarker'
ROOT = Path(__file__).resolve().parents[2]


def validate_scripts(scripts):
    if type(scripts) is not dict or set(scripts) != set(fixture_source.SAVED_SCRIPTS):
        raise ValueError('verified fixture scripts required')
    if any(type(data) is not bytes or not data or len(data) > 1 << 20 for data in scripts.values()):
        raise ValueError('invalid fixture script bytes')


def install_saved_scripts(case, scripts):
    validate_scripts(scripts)
    md = case / 'extensions/x4_lan_lab/md'
    paths = []
    for name, data in scripts.items():
        path = md / name
        if path.is_symlink():
            raise ValueError('private fixture script is a symlink')
        path.write_bytes(data)
        paths.append(path)
    return paths


def replace_marker(path):
    text = path.read_text(encoding='utf-8')
    if 'X4AuthorityCheckpointMarker' not in text:
        raise ValueError('private marker hook missing')
    path.write_text(text.replace('X4AuthorityCheckpointMarker', MARKER_SCRIPT), encoding='utf-8')


def install_server(case, profile, scripts, port, lease, epoch):
    protected = bridge.install_probe(case, profile, port, lease, epoch)
    lab = case / 'extensions/x4_lan_lab'
    for name in ('authority_checkpoint_marker_probe.lua', 'authority_world_bridge_probe.lua'):
        replace_marker(lab / 'ui' / name)
    for path in install_saved_scripts(case, scripts):
        if path not in protected:
            protected.append(path)
    return protected


def verify_checkpoint_mapping(checkpoint):
    epoch = fixture_source.fixture_save.base.archive.REGISTRY_EPOCH
    evidence = fixture_evidence.verify(checkpoint, epoch, checkpoint.marker,
                                       registry_count=4, fixture_indices=(3, 4),
                                       require_original_sector=False)
    if (evidence.get('saved_slots_checked') != 2 or
            evidence.get('saved_owner_class_sector_checked') is not True or
            evidence.get('saved_registry_slot_mapping_checked') is not True):
        raise ValueError('fixture checkpoint mapping differs')


def check_client_log(path, ticket, marker):
    captured = fixture_log.capture(path, None, 32 << 20)
    if captured is None:
        raise ValueError('fixture client log unavailable')
    data, _, _ = captured
    if not data.endswith(b'\n'):
        raise ValueError('fixture client log incomplete')
    low = data.lower()
    if any(error in low for error in (b'error while parsing expression:',
            b'maximum operator nesting level reached', b'error in md cue md.x4authority',
            b'error in lua script', b'stack traceback:')):
        raise ValueError('fixture client script reported a fault')
    watch = server_client.recovery.base.client.ReceiptWatch(path, ticket)
    rows = []
    for line in data.splitlines():
        if len(line) > watch.MAX_LINE:
            raise ValueError('fixture client log line too long')
        if server_client.recovery.base.client.TAG in line:
            rows.append(('load', line.split(server_client.recovery.base.client.TAG, 1)[1].strip()))
        if b'AUTH_MARKER ' in line:
            rows.append(('marker', line.split(b'AUTH_MARKER ', 1)[1].strip()))
    expected = [('load', watch.expected[0]), ('marker', b'load INSPECTED ' + marker.encode('ascii')),
                ('load', watch.expected[1])]
    if rows != expected:
        raise ValueError('fixture client load and marker receipts differ')


class FixtureServerClient(server_client.ServerClient):
    """Preserve recovery checks while omitting the unrelated old identity cue."""
    def install(self, case):
        super().install(case)
        manifest = case / 'extensions/x4_lan_lab/ui.xml'
        text = manifest.read_text(encoding='utf-8')
        identity_entry = '    <file name="ui/authority_identity_probe.lua" />\n'
        if text.count(identity_entry) != 1:
            raise ValueError('unexpected old identity probe in private manifest')
        manifest.write_text(text.replace(identity_entry, ''), encoding='utf-8')

    def protected(self, case):
        paths = super().protected(case)
        return [path for path in paths if path.name not in
                ('authority_identity_fixture.xml', 'authority_identity_probe.lua')]

    def verify_logs(self, server_log, client_log, ticket, marker):
        if self.recovery_watch is None or not self.recovery_watch.poll() or self.recovery_watch.stage != 3:
            raise ValueError('fixture server recovery observation changed')
        check_client_log(client_log, ticket, marker)
        if not self.recovery_watch.poll() or self.recovery_watch.stage != 3:
            raise ValueError('fixture server recovery log changed')
