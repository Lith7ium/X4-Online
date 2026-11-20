"""Saved-byte and bridge-receipt guard for opt-in format-3 recovery.

This module does not launch X4, publish a checkpoint or confirm admission.
The caller owns source provenance, the game process and save lifecycle.
"""
from pathlib import Path
import secrets

from authority.registry_availability_evidence import verify_join_snapshot
import authority_registry_checkpoint_install as bridge_gate

ROOT = Path(__file__).resolve().parents[2]


def validate_mode(args):
    required = getattr(args, 'require_registry_snapshot', False)
    if type(required) is not bool:
        raise ValueError('invalid registry snapshot option')
    if required and any(value for name, value in vars(args).items()
                        if name != 'require_registry_snapshot'
                        and name.startswith(('diagnostic_', 'fixture_', 'registry_'))):
        raise ValueError('registry snapshot requires the normal recovered server without diagnostic owners')
    return required


def receipt(checkpoint, evidence):
    """Compact identity for a confirmed saved snapshot, reusable by bootstrap."""
    if evidence.get('source_registry_checked') is not True or evidence.get('format') != 3:
        raise ValueError('verified format-3 source registry required')
    return {
        'checkpoint_id': checkpoint.checkpoint_id,
        'sha256': checkpoint.sha256,
        'run_id': checkpoint.marker,
        'epoch': evidence['epoch'],
        'issued_count': evidence['issued_count'],
        'availability_sha256': evidence['availability_sha256'],
        'operational_sha256': evidence['operational_sha256'],
        'mapping_sha256': evidence['mapping_sha256'],
    }


def verify_previous_receipt(previous_result, checkpoint, evidence):
    expected = receipt(checkpoint, evidence)
    record = previous_result.get('registry_snapshot') if type(previous_result) is dict else None
    if (type(record) is not dict or record.get('initial_inspect_verified') is not True
            or record.get('final_receipt') != expected):
        raise ValueError('previous supervisor has no matching verified final registry receipt')
    return expected


def verify_transition(previous, current):
    """No ID revival; operational observations may change independently."""
    if (current['epoch'] != previous['epoch'] or
            current['issued_count'] != previous['issued_count'] or
            current['run_id'] == previous['run_id'] or
            any(old == '0' and new == '1' for old, new in zip(
                previous['availability_bits'], current['availability_bits']))):
        raise ValueError('saved registry epoch/count or missing-binding lifetime changed')


class RegistrySnapshotState:
    """Track one recovered source and the latest fully verified saved run."""

    def __init__(self, source_checkpoint, source_evidence):
        self.latest_evidence = source_evidence
        self.latest_receipt = receipt(source_checkpoint, source_evidence)
        self.source_receipt = dict(self.latest_receipt)
        self.nonce = None
        self.initial_inspect_verified = False
        self.save_count = 0

    def install(self, case, *, reserved_tokens, read_source):
        if self.nonce is not None:
            raise ValueError('registry gate already installed')
        registry_md = Path(case) / 'extensions/x4_lan_lab/md/authority_ship_registry.xml'
        registry_md.write_bytes(read_source(ROOT / 'tools/dev/authority_ship_registry.xml'))
        reserved = set(reserved_tokens) | {self.latest_evidence['epoch'], self.latest_evidence['run_id']}
        nonce = secrets.token_hex(16)
        while nonce in reserved:
            nonce = secrets.token_hex(16)
        protected = bridge_gate.install(case, nonce, self.latest_evidence)
        self.nonce = nonce
        return [registry_md, *protected]

    def verify_initial(self, log_path):
        bridge_gate.verify_bridge_observation(log_path, self.nonce, self.latest_evidence)
        self.initial_inspect_verified = True

    def verify_save(self, checkpoint, log_path):
        if not self.initial_inspect_verified:
            raise ValueError('initial registry inspection not verified')
        current = verify_join_snapshot(checkpoint)
        verify_transition(self.latest_evidence, current)
        bridge_gate.verify_bridge_observation(log_path, self.nonce, current,
                                              previous_run_id=self.latest_evidence['run_id'])
        self.latest_evidence = current
        self.latest_receipt = receipt(checkpoint, current)
        self.save_count += 1
        return dict(self.latest_receipt)

    def metadata(self):
        return {'required': True, 'source_receipt': dict(self.source_receipt),
                'initial_inspect_verified': self.initial_inspect_verified,
                'verified_save_count': self.save_count,
                'final_receipt': dict(self.latest_receipt) if self.save_count else None,
                'native_load_bytes_proven': False}
