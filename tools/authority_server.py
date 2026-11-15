"""Run the experimental local-only ship-state exchange (not an X4 server)."""
import argparse
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from authority.transport import ShipExchange  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=45860)
    args = parser.parse_args()
    with ShipExchange(("127.0.0.1", args.port), secrets.token_hex(16)) as server:
        print(f"Experimental ship exchange on {server.server_address}; world epoch {server.registry.world_epoch}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
