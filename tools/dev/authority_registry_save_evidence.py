#!/usr/bin/env python3
"""Read-only structural evidence for one experimental ship registry checkpoint.

Checks the saved bidirectional registry and referenced X4 ship components. It
cannot establish which object a separate running X4 instance resolved, complete
universe coverage, or correct multiplayer behavior. No X4 process is started.
The verifier now lives in :mod:`authority.registry_evidence` so runtime
supervisors can use it without importing this CLI module.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from authority.checkpoints import Checkpoint, CheckpointStore
from authority.marker_evidence import MarkerEvidenceError, _parse
from authority.registry_evidence import (
    COMPONENT, DECIMAL, EPOCH, MAX_ENTRIES, RegistryEvidenceError, verify,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', required=True, type=Path)
    parser.add_argument('--expected-epoch', required=True)
    parser.add_argument('--expected-count', required=True, type=int)
    parser.add_argument('--server-log', type=Path)
    parser.add_argument('--client-log', type=Path)
    parser.add_argument('--sector-parents', action='store_true',
                        help='inspect saved component ancestry; no runtime mapping claim')
    args = parser.parse_args()
    if bool(args.server_log) != bool(args.client_log):
        parser.error('both logs must be supplied together')
    try:
        rows = None
        if args.server_log:
            from authority_registry_census_live import observations
            rows, _ = observations(args.server_log, 'save', args.expected_count, args.expected_epoch)
            client, _ = observations(args.client_log, 'load', args.expected_count, args.expected_epoch)
            if rows != client:
                raise RegistryEvidenceError('server and client macro rows differ')
        checkpoint = CheckpointStore(args.store).latest_confirmed()
        result = verify(checkpoint, args.expected_epoch, args.expected_count, expected_rows=rows,
                        include_sector_parents=args.sector_parents)
    except (OSError, ValueError) as error:
        parser.exit(1, 'REFUSED: ' + str(error) + '\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
