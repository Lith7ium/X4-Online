import json
from pathlib import Path
import socket
import sys
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from authority.ship_state import Position  # noqa: E402
from authority.transport import ShipExchange  # noqa: E402


class Peer:
    def __init__(self, address, name):
        self.socket = socket.create_connection(address, timeout=3)
        self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.file = self.socket.makefile("rwb")
        self.hello = self.send({"op": "hello", "peer": name})

    def send(self, message):
        self.file.write(json.dumps(message).encode() + b"\n")
        self.file.flush()
        return json.loads(self.file.readline())

    def close(self):
        self.file.close()
        self.socket.close()


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.exchange = ShipExchange(("127.0.0.1", 0), "world-1")
        self.thread = threading.Thread(target=self.exchange.serve_forever, daemon=True)
        self.thread.start()
        self.peers = []

    def tearDown(self):
        for peer in self.peers:
            peer.close()
        self.exchange.shutdown()
        self.exchange.server_close()
        self.thread.join(timeout=3)

    def peer(self, name):
        peer = Peer(self.exchange.server_address, name)
        self.peers.append(peer)
        return peer

    def wait_until(self, predicate):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.01)
        self.fail("connection state did not change")

    def test_delegation_updates_and_disconnect_fence(self):
        server, client = self.peer("server"), self.peer("client1")
        pos = {"sector": "S", "x": 1, "y": 2, "z": 3}
        create = {"op": "create", "world_epoch": "world-1", "ship_id": "ship1",
                  "generation": 1, "position": pos}
        self.assertTrue(server.send(create)["ok"])
        assign = {"op": "assign", "world_epoch": "world-1", "ship_id": "ship1",
                  "generation": 1, "authority_epoch": 1, "owner": "client1"}
        self.assertEqual(server.send(assign)["value"]["ship"]["authority_epoch"], 2)
        update = {"op": "update", "world_epoch": "world-1", "ship_id": "ship1",
                  "generation": 1, "authority_epoch": 2, "sequence": 1,
                  "position": {**pos, "x": 50}}
        self.assertFalse(server.send(update)["ok"])
        self.assertTrue(client.send(update)["ok"])
        self.assertFalse(client.send(update)["ok"])
        client.close()
        self.peers.remove(client)
        self.wait_until(lambda: "client1" not in self.exchange.peers)
        replacement = self.peer("client1")
        self.assertFalse(replacement.send({**update, "sequence": 2})["ok"])
        snapshot = server.send({"op": "snapshot", "offset": 0, "revision": None})["value"]
        self.assertEqual(snapshot["ships"][0]["owner"], "offline:client1")
        self.assertEqual(snapshot["ships"][0]["authority_epoch"], 3)
        assign.update(authority_epoch=3, owner=None)
        self.assertEqual(server.send(assign)["value"]["ship"]["authority_epoch"], 4)
        self.assertTrue(server.send({**update, "authority_epoch": 4, "sequence": 1})["ok"])

    def test_frozen_paginated_snapshot_progresses_during_updates(self):
        server, client = self.peer("server"), self.peer("reader")
        with self.exchange.lock:
            for i in range(130):
                self.exchange.registry.create(f"s{i:03d}", 1, Position("S", i, 0, 0))
            self.exchange.revision += 1
        first = client.send({"op": "snapshot", "offset": 0, "revision": None})["value"]
        self.assertEqual(len(first["ships"]), 128)
        message = {"op": "update", "world_epoch": "world-1", "ship_id": "s129", "generation": 1,
                   "authority_epoch": 1, "sequence": 1,
                   "position": {"sector": "S", "x": 999, "y": 0, "z": 0}}
        self.assertTrue(server.send(message)["ok"])
        second = client.send({"op": "snapshot", "offset": first["next_offset"],
                              "revision": first["revision"]})["value"]
        self.assertEqual(second["revision"], first["revision"])
        self.assertEqual(second["ships"][-1]["position"]["x"], 129)
        self.assertIsNone(second["next_offset"])
        fresh = client.send({"op": "snapshot", "offset": 0, "revision": None})["value"]
        self.assertGreater(fresh["revision"], first["revision"])

    def test_server_disconnect_ends_epoch_and_flags_snapshot(self):
        reader = self.peer("reader")
        before = reader.send({"op": "snapshot", "offset": 0, "revision": None})["value"]
        self.assertFalse(before["server_online_at_capture"])
        server = self.peer("server")
        server.close()
        self.peers.remove(server)
        self.wait_until(lambda: self.exchange.server_departed)
        after = reader.send({"op": "snapshot", "offset": 0, "revision": None})["value"]
        self.assertFalse(after["server_online"])
        self.assertFalse(self.peer("server").hello["ok"])

    def test_loopback_only_and_wrong_epoch(self):
        with self.assertRaises(ValueError):
            ShipExchange(("0.0.0.0", 0), "world-1")
        server = self.peer("server")
        response = server.send({"op": "create", "world_epoch": "old", "ship_id": "1",
                                "generation": 1, "position": {"sector": "S", "x": 0, "y": 0, "z": 0}})
        self.assertFalse(response["ok"])
        self.assertEqual(self.exchange.registry.snapshot(), ())


if __name__ == "__main__":
    unittest.main()
