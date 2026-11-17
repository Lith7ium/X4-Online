"""Narrow, opt-in save verifier for a disposable two-sector fixture.

No game, network socket or file is created at import. The parent bridge's
normal verification remains unchanged. The caller must route its private UI
bridge's marker events to X4AuthorityPlayerFixtureMarker. The experimental
save is for a disposable world: this class does not establish process or
profile isolation, spawn safety, usable seats, or runtime readback evidence.
No native harness is enabled by this file.
"""
import re
from authority.local_control_bridge import LocalControlBridge
import authority_player_sector_evidence as fixture


class PlayerFixtureBridge(LocalControlBridge):
    """Verify a disposable fixture save before native confirmation."""
    def __init__(self, *, fixture_epoch, **kwargs):
        if (type(fixture_epoch) is not str or not re.fullmatch(r'[0-9a-f]{32}',fixture_epoch)
                or kwargs.get('marker_required') is not True):
            raise ValueError('fixture epoch and required distinct marker are mandatory')
        super().__init__(**kwargs)
        self._fixture_epoch = fixture_epoch
        self._fixture_save_attempted = False

    def save(self):
        # The fixture currently has no independently validated live seat,
        # frame, hull and safety evidence. Never dispatch a save prematurely.
        raise RuntimeError('fixture live-readback gate is not implemented; native save disabled')

    def save_fixture_experiment(self, *, enabled=False):
        """Request one unverified fixture save in an owned disposable profile.

        The caller must fence the X4 process, isolated profile and all save
        writers, confirm pause and route the marker to the fixture marker cue.
        A returned path is only a native save receipt, not a verified checkpoint.
        Publication still requires ``checkpoint_published`` to verify saved
        identity and fixture references before native confirmation.
        """
        if enabled is not True:
            raise ValueError('experimental fixture save requires explicit opt-in')
        if self._poisoned or self._fixture_save_attempted:
            raise RuntimeError('fixture save already attempted or bridge fenced')
        if self._pending_save is not None:
            raise RuntimeError('previous save has not been verified')
        self._fixture_save_attempted = True
        try:
            return super().save()
        except BaseException:
            # A failed dispatch may already have mutated X4 or written a save.
            self._poisoned = True
            raise

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
        try:
            self._poisoned = False
            prefix = f'{self._lease}|{self._epoch}|{number}'
            self._exchange(f'VERIFY|{prefix}', f'VERIFIED|{prefix}')
            self._pending_save = None
            self._pending_marker = None
        except BaseException:
            self._poisoned = True
            raise
        return True
