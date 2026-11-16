"""Read-only clock witness for the opt-in isolated overlap diagnostic."""
import math
from pathlib import Path
import re
import secrets
import shutil
import socket
import time

ROOT = Path(__file__).resolve().parents[2]
TOKEN = re.compile(r'[0-9a-f]{32}\Z')


def _replace(text, old, new):
    if text.count(old) != 1: raise ValueError('clock installation hook differs')
    return text.replace(old, new)


def install(case, port):
    """Modify only an already isolated, unlaunched diagnostic case."""
    if type(port) is not int or not 1 <= port <= 65535: raise ValueError('invalid observer port')
    lab = Path(case)/'extensions/x4_lan_lab'; ui = lab/'ui'
    observer = ui/'authority_overlap_clock.lua'
    shutil.copyfile(ROOT/'tools/dev/authority_overlap_clock.lua', observer)
    config = ui/'config.lua'
    config.write_text(_replace(config.read_text(encoding='ascii'), 'X4LAN_CONFIG = {',
        f'X4LAN_CONFIG = {{authority_overlap_clock=true,authority_overlap_clock_port={port},'), encoding='ascii')
    probe = ui/'authority_world_bridge_probe.lua'
    probe.write_text(_replace(probe.read_text(encoding='utf-8'), ' X4LAN_AUTHORITY_RECOVERY_UPDATE()\n',
        ' X4LAN_AUTHORITY_RECOVERY_UPDATE()\n X4LAN_AUTHORITY_OVERLAP_CLOCK_UPDATE()\n'), encoding='utf-8')
    layout = lab/'ui.xml'
    old = '<file name="ui/authority_world_bridge_probe.lua" />'
    # Preserve the generated layout and make the factory available before the caller.
    layout.write_text(_replace(layout.read_text(encoding='utf-8'), old,
        '<file name="ui/authority_overlap_clock.lua" />\n    '+old), encoding='utf-8')
    return observer


class OverlapClock:
    def __init__(self, sock, lease):
        if (type(sock) is not socket.socket or sock.family != socket.AF_INET or
                sock.type != socket.SOCK_DGRAM or sock.getsockname()[0] != '127.0.0.1' or
                type(lease) is not str or not TOKEN.fullmatch(lease)):
            raise ValueError('isolated loopback clock socket required')
        self.sock=sock;self.lease=lease;self.peer=None
        sock.setblocking(False)

    def _read(self, deadline, tick, verify, expected=None):
        while time.monotonic() < deadline:
            verify();tick();verify()
            for _ in range(256):
                try: raw,peer=self.sock.recvfrom(769)
                except BlockingIOError: break
                if peer[0]!='127.0.0.1' or len(raw)>768: raise ValueError('foreign clock peer')
                if raw==('CLOCK_READY|'+self.lease).encode('ascii'):
                    if self.peer is not None and self.peer!=peer: raise ValueError('clock peer changed')
                    self.peer=peer
                    if expected is None: return None
                    continue
                if expected is None or peer!=self.peer: raise ValueError('unexpected clock packet')
                parts=raw.split(b'|')
                if len(parts)!=4 or parts[:3]!=[b'CLOCK_RESULT',expected.encode('ascii'),b'running']:
                    raise ValueError('unexpected or paused clock result')
                try: game=float(parts[3].decode('ascii'))
                except (ValueError,UnicodeError): raise ValueError('invalid clock result') from None
                if not math.isfinite(game) or game<0: raise ValueError('invalid clock result')
                verify()
                if time.monotonic()>=deadline: raise TimeoutError('clock result arrived after deadline')
                return game
        raise TimeoutError('clock observation timed out')

    def sample(self, deadline, tick, verify):
        if self.peer is None: self._read(deadline,tick,verify)
        # The native observer advertises readiness while two clients load.
        # Drain that bounded UDP backlog before asking for a fresh sample so
        # the result cannot be dropped behind a full receive queue.
        for _ in range(8192):
            try: raw,peer=self.sock.recvfrom(769)
            except BlockingIOError: break
            if peer!=self.peer or raw!=('CLOCK_READY|'+self.lease).encode('ascii'):
                raise ValueError('unexpected queued clock packet')
        else: raise RuntimeError('clock ready backlog did not drain')
        verify()
        if time.monotonic()>=deadline: raise TimeoutError('clock request deadline passed')
        nonce=secrets.token_hex(16)
        data=('CLOCK|'+nonce).encode('ascii')
        if self.sock.sendto(data,self.peer)!=len(data): raise RuntimeError('clock request failed')
        return self._read(deadline,tick,verify,nonce)

    def observe(self, deadline, tick, verify, *, interval=.25):
        first=self.sample(deadline,tick,verify)
        until=time.monotonic()+interval
        while time.monotonic()<until:
            if time.monotonic()>=deadline: raise TimeoutError('clock interval timed out')
            verify();tick();verify()
        second=self.sample(deadline,tick,verify)
        if second<=first: raise ValueError('native game clock did not advance')
        return {'server_game_time_before':first,'server_game_time_after':second}
