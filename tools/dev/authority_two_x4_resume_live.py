#!/usr/bin/env python3
"""Disposable two-Linux-X4 admission/resume diagnostic; no gameplay.

TEST ASSUMPTION: native paused-load receipt, immutable hashed staged bytes and
matching fixture references are treated as an exact-load confirmation. They do
not prove all bytes consumed. This assumption MUST NOT be used for real clients.
The participant confirmations are native, not simulated. Import starts nothing.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import stat
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
import authority_two_x4_identity_live as identity
import authority_two_x4_live as base
from lockstep.launcher import extension


class Participant:
    """Single serialized loopback diagnostic, fenced on any uncertain receipt."""
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', 0)); self.sock.settimeout(.25)
        self.lease = secrets.token_hex(16)
        self.peer = self.epoch = self.handle = None
        self.next_id = 1
        self.fault = False
        self.config = self.config_identity = None

    def install(self, case):
        lab = case/'extensions/x4_lan_lab'; ui = lab/'ui'
        for source, name in ((ROOT/'src/authority/lua/control_state.lua', 'authority_control_state.lua'),
                             (ROOT/'src/authority/lua/x4_control_engine.lua', 'x4_control_engine.lua'),
                             (ROOT/'tools/dev/authority_two_x4_participant_probe.lua', 'authority_two_x4_participant_probe.lua')):
            shutil.copyfile(source, ui/name)
        server_lib = case.parent.parent/'server/case/extensions/x4_lan_lab/native/x4lan_net.so'
        shutil.copyfile(server_lib, lab/'native/x4lan_net.so')
        config = ui/'config.lua'; text = config.read_text(encoding='ascii')
        if not text.endswith('}\n'): raise ValueError('unexpected client config')
        st = config.lstat()
        if not stat.S_ISREG(st.st_mode): raise ValueError('client config is not a regular file')
        self.config, self.config_identity = config, (st.st_dev, st.st_ino)
        config.write_text(text[:-2]+f',authority_participant_port={self.sock.getsockname()[1]},'
                          f'authority_participant_lease="{self.lease}"'+'}\n', encoding='ascii')
        files = [*extension.BASE_UI, 'ui/client_load_barrier.lua', 'ui/x4_client_load_engine.lua',
                 'ui/authority_identity_probe.lua', 'ui/authority_download_load_probe.lua',
                 'ui/authority_control_state.lua', 'ui/x4_control_engine.lua',
                 'ui/authority_two_x4_participant_probe.lua']
        (lab/'ui.xml').write_text(extension.ui_xml(files), encoding='utf-8')

    def redact(self):
        if self.config is None: return
        fd = os.open(self.config, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or (st.st_dev, st.st_ino) != self.config_identity or st.st_size > 65536:
                raise ValueError('owned client config changed before redaction')
            text = os.read(fd, 65537).decode('ascii')
            original = f'authority_participant_lease="{self.lease}"'
            if text.count(original) != 1: raise ValueError('client lease missing or repeated')
            data = text.replace(original, 'authority_participant_lease="redacted"').encode('ascii')
            os.lseek(fd, 0, os.SEEK_SET)
            written = 0
            while written < len(data):
                n = os.write(fd, data[written:])
                if n <= 0: raise OSError('short config write')
                written += n
            os.ftruncate(fd, len(data))
        finally:
            os.close(fd)

    def protected(self, case):
        lab = case/'extensions/x4_lan_lab'
        return [lab/'ui'/name for name in ('authority_control_state.lua', 'x4_control_engine.lua',
                                           'authority_two_x4_participant_probe.lua')] + [lab/'native/x4lan_net.so']

    def enroll(self, epoch, deadline):
        self.epoch = epoch
        expected = f'HELLO|{self.lease}|{epoch}'.encode('ascii')
        while time.monotonic() < deadline:
            try: data, peer = self.sock.recvfrom(769)
            except socket.timeout: continue
            if data == expected and peer[0] == '127.0.0.1':
                self.peer = peer; return
        raise TimeoutError('participant enrollment timed out')

    def request(self, operation):
        if self.fault or self.peer is None: raise RuntimeError('participant unavailable')
        self.fault = True
        number = self.next_id; self.next_id += 1
        prefix = f'{self.lease}|{self.epoch}|{number}'
        self.sock.sendto(f'CMD|{prefix}|{operation}'.encode('ascii'), self.peer)
        expected = f'RECEIPT|{prefix}|{operation}|confirmed'.encode('ascii')
        hello = f'HELLO|{self.lease}|{self.epoch}'.encode('ascii')
        deadline = time.monotonic()+130
        while time.monotonic() < deadline:
            try: data, peer = self.sock.recvfrom(769)
            except socket.timeout: continue
            if peer != self.peer: continue
            if data == hello: continue
            if data != expected: raise RuntimeError('unexpected participant receipt')
            self.fault = False; return
        raise TimeoutError('participant state indeterminate')

    def pause(self, handles):
        if handles != (self.handle,): raise ValueError('unexpected participant set')
        self.request('pause'); return True

    def resume(self, handles):
        if handles != (self.handle,): raise ValueError('unexpected participant set')
        self.request('resume'); return True

    def on_ready(self, *, world, handle, ticket, target, server_identity, server_proc, server_started,
                 client_identity, client_proc, client_started, game, out, deadline, result):
        # This callback is reached only after the two ordered ticket-bound load
        # receipts, a transfer size/hash check and protected-file checks.
        profile = Path('case/home/.config/EgoSoft/X4/45841/engine-output.log')
        identity.compare_observations(out/'server'/profile, out/'client'/profile)
        if base.live.sha(target) != ticket['sha256']: raise ValueError('staged bytes changed')
        def check_processes():
            if (base.client.game_identity(server_proc, server_started, game) != server_identity or
                    base.client.game_identity(client_proc, client_started, game) != client_identity):
                raise RuntimeError('owned X4 process changed')
        check_processes()
        self.handle = handle
        self.enroll(ticket['world_epoch'], deadline)
        self.request('pause')
        check_processes()
        # Explicit diagnostic assumption, not a proof of all bytes read.
        world.mark_loaded(ticket['world_epoch'], handle, ticket['baseline_id'], ticket['load_generation'],
                          ticket['checkpoint_id'], ticket['sha256'], trusted_confirmation=True)
        if world.session.pending is None or world.session.pending.operation != 'resume':
            raise RuntimeError('resume not scheduled')
        world.step()  # Native server and client both confirm advancing game time.
        check_processes()
        if world.session.state != 'running': raise RuntimeError('world did not resume')
        world.join('isolated-pause-probe')
        if world.session.pending is None or world.session.pending.operation != 'pause':
            raise RuntimeError('pause not scheduled')
        world.step()  # Both native controllers confirm a stable paused game clock.
        check_processes()
        result.update(client_admitted=True, native_server_and_client_resume_confirmed=True,
                      native_server_and_client_pause_confirmed=True,
                      load_confirmation='TEST ASSUMPTION: full X4 file consumption not proven',
                      server_state='paused')


def run(args):
    # Reject pre-existing or out-of-scope paths before registering cleanup.
    out = base.snapshot.output_path(args.out)
    participant = Participant()
    old_inject, old_run = identity.inject, base.run
    def inject(case, phase):
        old_inject(case, phase)
        if phase == 'load': participant.install(case)
    def run_base(arguments): return old_run(arguments, experiment=participant)
    result = None
    try:
        identity.inject, base.run = inject, run_base
        result = identity.run(args)
    finally:
        identity.inject, base.run = old_inject, old_run
        participant.sock.close()
        try:
            participant.redact()
        except (OSError, UnicodeError, ValueError) as error:
            if result is None:
                raise RuntimeError('client lease cleanup failed') from error
            result.update(success=False, cleanup_error='client lease cleanup failed')
    result['scope'] = ('two isolated Linux X4 processes; assumed exact load; native admission, '
                       'resume and pause; no gameplay, Windows or internet')
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--game', required=True, type=Path); p.add_argument('--out', required=True, type=Path)
    p.add_argument('--display', required=True); p.add_argument('--timeout', type=float, default=600)
    p.add_argument('--seed', type=int, default=276944566)
    try: result = run(p.parse_args())
    except (OSError, ValueError, RuntimeError) as error: p.exit(1, 'REFUSED: '+str(error)+'\n')
    print(json.dumps(result, indent=2)); return 0 if result['success'] else 1

if __name__ == '__main__': sys.exit(main())
