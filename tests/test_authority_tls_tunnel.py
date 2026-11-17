"""Local TLS transport tests; all keys below are public test fixtures."""
import asyncio
import hashlib
from pathlib import Path
import socket
import ssl
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]

from authority.experimental_tls_tunnel import start_client, start_server
from test_authority_tls_tunnel_integration import TEST_CERTIFICATE, TEST_PRIVATE_KEY


def listener():
    result = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result.bind(('127.0.0.1', 0))
    result.listen(16)
    return result


class TunnelTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        certificate = Path(self.temp.name) / 'cert.pem'
        private_key = Path(self.temp.name) / 'key.pem'
        certificate.write_text(TEST_CERTIFICATE)
        private_key.write_text(TEST_PRIVATE_KEY)
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(certificate, private_key)
        self.fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(TEST_CERTIFICATE)).hexdigest()
        self.tunnels = []
        self.servers = []
        self.backend_connections = []
        self.addAsyncCleanup(self.cleanup_network)

    async def cleanup_network(self):
        for tunnel in reversed(self.tunnels):
            await tunnel.close()
        for server in self.servers:
            server.close()
            await server.wait_closed()

    async def endpoint(self, prefix):
        async def handler(reader, writer):
            self.backend_connections.append(prefix)
            try:
                payload = await reader.read()
                writer.write(prefix + payload)
                await writer.drain()
                writer.write_eof()
            finally:
                writer.close()
                await writer.wait_closed()
        server = await asyncio.start_server(handler, '127.0.0.1', 0)
        self.servers.append(server)
        return server.sockets[0].getsockname()[1]

    async def make_pair(self, *, key=b'a' * 32, fingerprint=None, max_connections=8):
        control_port = await self.endpoint(b'control:')
        file_port = await self.endpoint(b'file:')
        host = listener()
        host_port = host.getsockname()[1]
        server = await start_server(listener=host, ssl_context=self.context,
                                    shared_key=b'a' * 32, control_port=control_port,
                                    file_port=file_port, max_connections=max_connections,
                                    idle_timeout=5)
        self.tunnels.append(server)
        control, files = listener(), listener()
        client_ports = control.getsockname()[1], files.getsockname()[1]
        client = await start_client(control_listener=control, file_listener=files,
                                    server_host='127.0.0.1', server_port=host_port,
                                    server_fingerprint=fingerprint or self.fingerprint,
                                    shared_key=key, max_connections=max_connections,
                                    idle_timeout=5)
        self.tunnels.append(client)
        return client_ports

    async def exchange(self, port, payload):
        reader, writer = await asyncio.open_connection('127.0.0.1', port)
        writer.write(payload)
        await writer.drain()
        writer.write_eof()
        response = await asyncio.wait_for(reader.read(), 10)
        writer.close()
        await writer.wait_closed()
        return response

    async def test_large_transfer_and_both_listeners_with_single_slot(self):
        control, files = await self.make_pair(max_connections=1)
        payload = bytes(range(256)) * 2048
        self.assertEqual(await self.exchange(files, payload), b'file:' + payload)
        self.assertEqual(await self.exchange(control, b'command'), b'control:command')

    async def test_wrong_key_never_reaches_backend(self):
        control, _ = await self.make_pair(key=b'b' * 32)
        self.assertEqual(await self.exchange(control, b'command'), b'')
        self.assertEqual(self.backend_connections, [])

    async def test_wrong_fingerprint_sends_no_shared_key(self):
        received = asyncio.get_running_loop().create_future()

        async def impersonator(reader, writer):
            try:
                received.set_result(await reader.read(64))
            finally:
                writer.close()
                await writer.wait_closed()

        fake = await asyncio.start_server(impersonator, '127.0.0.1', 0, ssl=self.context)
        self.servers.append(fake)
        control, files = listener(), listener()
        client = await start_client(control_listener=control, file_listener=files,
                                    server_host='127.0.0.1', server_port=fake.sockets[0].getsockname()[1],
                                    server_fingerprint='0' * 64, shared_key=b'a' * 32)
        self.tunnels.append(client)
        await self.exchange(control.getsockname()[1], b'command')
        self.assertEqual(await asyncio.wait_for(received, 5), b'')

    async def test_listener_failure_closes_tunnel_and_is_reported(self):
        host = listener()
        tunnel = await start_server(listener=host, ssl_context=self.context,
                                    shared_key=b'a' * 32, control_port=1, file_port=2)
        self.tunnels.append(tunnel)
        loop = asyncio.get_running_loop()
        with patch.object(loop, 'sock_accept', side_effect=OSError('private detail')):
            with self.assertRaisesRegex(RuntimeError, '^tunnel listener stopped$'):
                await asyncio.wait_for(tunnel.wait(), 5)
        self.assertEqual(host.fileno(), -1)

    async def reject_bad_frame(self, frame, *, close_tls):
        received = asyncio.get_running_loop().create_future()

        async def backend(reader, writer):
            try:
                received.set_result(await reader.read())
            finally:
                writer.close()
                await writer.wait_closed()

        service = await asyncio.start_server(backend, '127.0.0.1', 0)
        self.servers.append(service)
        host = listener()
        port = host.getsockname()[1]
        tunnel = await start_server(listener=host, ssl_context=self.context,
                                    shared_key=b'a' * 32,
                                    control_port=service.sockets[0].getsockname()[1],
                                    file_port=service.sockets[0].getsockname()[1])
        self.tunnels.append(tunnel)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        reader, writer = await asyncio.open_connection('127.0.0.1', port, ssl=context, server_hostname='')
        writer.write(b'X4TUN01\0' + b'a' * 32 + b'\x01')
        await writer.drain()
        self.assertEqual(await asyncio.wait_for(reader.readexactly(1), 5), b'\x01')
        writer.write(frame)
        await writer.drain()
        if close_tls:
            writer.close()
            await writer.wait_closed()
        else:
            self.assertEqual(await asyncio.wait_for(reader.read(), 5), b'')
            writer.close()
            await writer.wait_closed()
        self.assertEqual(await asyncio.wait_for(received, 5), b'')

    async def test_oversize_frame_is_rejected_without_backend_data(self):
        await self.reject_bad_frame(struct.pack('!BI', 1, 65537), close_tls=False)

    async def test_truncated_frame_is_rejected_without_backend_data(self):
        await self.reject_bad_frame(struct.pack('!BI', 1, 4) + b'ab', close_tls=True)


if __name__ == '__main__':
    unittest.main()
