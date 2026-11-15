"""Narrow, opt-in save verifier for a disposable two-sector fixture.

No game, network socket or file is created at import. The parent bridge's
normal verification remains unchanged. The caller must route its private UI
bridge's marker events to X4AuthorityPlayerFixtureMarker and establish live
spawn/readback evidence before invoking save. This class does not perform or
prove that runtime evidence; no native harness is enabled by this file.
"""
import re
from authority.local_control_bridge import LocalControlBridge
import authority_player_sector_evidence as fixture


class PlayerFixtureBridge(LocalControlBridge):
    """Prepare distinct-marker validation; native save remains disabled."""
    def __init__(self, *, fixture_epoch, **kwargs):
        if (type(fixture_epoch) is not str or not re.fullmatch(r'[0-9a-f]{32}',fixture_epoch)
                or kwargs.get('marker_required') is not True):
            raise ValueError('fixture epoch and required distinct marker are mandatory')
        super().__init__(**kwargs)
        self._fixture_epoch = fixture_epoch

    def save(self):
        # The fixture currently has no independently validated live seat,
        # frame, hull and safety evidence. Never dispatch a save prematurely.
        raise RuntimeError('fixture live-readback gate is not implemented; native save disabled')

    def checkpoint_published(self, checkpoint):
        if self._poisoned:
            raise RuntimeError('fixture bridge is fenced after an indeterminate operation')
        number = self._pending_save
        if number is None:
            raise ValueError('no native save awaits verification')
        self._poisoned = True
        expected = f'X4 Authority {self._epoch} {number}'
        evidence = self._verify(self._store, checkpoint.checkpoint_id, expected)
        if (checkpoint.marker != self._pending_marker or self._pending_marker is None
                or self._store.get(checkpoint.checkpoint_id) != checkpoint
                or evidence.checkpoint_id != checkpoint.checkpoint_id
                or evidence.sha256 != checkpoint.sha256 or evidence.size != checkpoint.size
                or evidence.save_name != expected):
            raise ValueError('published fixture checkpoint identity mismatch')
        checked = fixture.verify(checkpoint, self._fixture_epoch, self._pending_marker)
        if (checked.get('saved_slots_checked') != 2 or
                checked.get('saved_owner_class_sector_checked') is not True):
            raise ValueError('saved player fixture validation failed')
        self._poisoned = False
        prefix = f'{self._lease}|{self._epoch}|{number}'
        self._exchange(f'VERIFY|{prefix}', f'VERIFIED|{prefix}')
        self._pending_save = None
        self._pending_marker = None
        return True
