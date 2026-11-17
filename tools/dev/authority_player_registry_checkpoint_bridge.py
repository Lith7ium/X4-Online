"""Experimental checkpoint verification for the two registered fixtures."""

from authority_player_fixture_bridge import PlayerFixtureBridge
import authority_player_sector_evidence as fixture


class PlayerRegistryCheckpointBridge(PlayerFixtureBridge):
    """Fence native confirmation until the saved registry mapping is verified."""

    def _verify_fixture(self, checkpoint):
        evidence = fixture.verify(
            checkpoint, self._fixture_epoch, self._pending_marker,
            registry_count=4, fixture_indices=(3, 4),
        )
        if evidence.get('saved_registry_slot_mapping_checked') is not True:
            raise ValueError('saved fixture registry mapping was not verified')
        return evidence
