#!/usr/bin/env python3
"""Opt-in recovered Linux X4 and real remote-load owner diagnostic.

One supervisor owns both private X4 processes and their single global lock.
This composes the existing recovery and remote-load supervisors: it does not
connect to the persistent recovered_loopback_server, support repeated joins,
or demonstrate Windows, internet or gameplay. Importing starts no processes.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
import authority_recovery_tcp_join_live as recovery
import authority_remote_load_pair_live as remote


class RecoveredRemoteParticipant(recovery.RecoveredParticipant, remote.RemoteParticipant):
    """Fresh post-recovery offer through the existing real remote-load owner.

    Cooperative multiple inheritance is intentional: recovery's fresh-marker
    guard wraps remote's TCP offer/download; remote supplies keepalive and
    socket handoff, and recovery validates native marker/identity evidence.
    """


def run(args):
    original = recovery.RecoveredParticipant
    try:
        recovery.RecoveredParticipant = RecoveredRemoteParticipant
        result = recovery.run(args)
    finally:
        recovery.RecoveredParticipant = original
    result.update(scope=('one recovered isolated Linux X4 and one isolated Linux client; '
                         'real remote-load owner over loopback; no persistent server, '
                         'repeated joins, Windows, Internet or gameplay'),
                  persistent_loopback_server_used=False, repeated_joins_tested=False,
                  exact_loaded_file_proven=False, windows_tested=False,
                  internet_tested=False, gameplay_tested=False)
    (Path(args.out)/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--display', required=True)
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--seed', type=int, default=276944566)
    try:
        result = run(parser.parse_args())
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, 'REFUSED: '+str(error)+'\n')
    print(json.dumps(result, indent=2))
    return 0 if result['success'] else 1


if __name__ == '__main__':
    sys.exit(main())
