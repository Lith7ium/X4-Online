#!/usr/bin/env python3
"""Opt-in recovery and one Linux client over loopback; importing starts nothing.

The source is one fixed, previously recorded checkpoint. This experiment checks
load/marker/pause and a cooperative TCP claim plus native participant controls.
It does not prove exact X4 load bytes, gameplay, Windows or internet operation.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tools/dev')]
import authority_recovery_join_source as source
import authority_recovery_bridge_live as recovery_bridge
import authority_recovery_live as recovery
import authority_tcp_native_live as tcp
import authority_trusted_marked_live as marked
from authority.checkpoints import CheckpointStore
from authority.recovery import stage_confirmed_recovery

base = marked.base
live = base.live
snapshot = base.snapshot
load = base.load


def check_separate(out, store):
    out = snapshot.output_path(out).resolve()
    store = load.local_directory(store)
    if store != source.DEFAULT_STORE.resolve():
        raise ValueError('only the recorded recovery source is supported')
    origin = store.parent
    if out.is_relative_to(origin) or origin.is_relative_to(out):
        raise ValueError('output and source experiment must be separate')
    return out, store


def check_client_log(path, ticket, marker):
    data = marked.file_evidence._read_regular(path, marked.file_evidence.MAX_LOG, collect=True)
    content = data[2]
    if content and not content.endswith(b'\n'): raise ValueError('client log incomplete')
    actors = marked.identity_evidence.observations_bytes(content, 'load')
    watch = base.client.ReceiptWatch(path, ticket)
    rows = []
    for line in content.splitlines():
        if len(line) > watch.MAX_LINE: raise ValueError('client log line too long')
        if base.client.TAG in line: rows.append(('load', line.split(base.client.TAG, 1)[1].strip()))
        if b'AUTH_MARKER ' in line: rows.append(('marker', line.split(b'AUTH_MARKER ', 1)[1].strip()))
        if b'[X4LAN] AUTH_IDENTITY load ' in line:
            rows.append(('identity', line.split(b'[X4LAN] AUTH_IDENTITY load ', 1)[1].strip()))
    expected = [('load', watch.expected[0]), ('marker', b'load INSPECTED '+marker.encode('ascii')),
                *[('identity', ('ACTOR %d id=%s name=%s macro=%s' %
                   (i, actor['id'], actor['name'], actor['macro'])).encode('ascii'))
                  for i, actor in enumerate(actors, 1)], ('identity', b'READY'),
                ('load', watch.expected[1])]
    if rows != expected: raise ValueError('client load and marker receipts differ')
    if marked.file_evidence._read_regular(path, marked.file_evidence.MAX_LOG, collect=True) != data:
        raise ValueError('client log changed during observation')


class RecoveredParticipant(tcp.TCPMarkedParticipant):
    def __init__(self, deadline, store):
        super().__init__(deadline, first_resume_only=True)
        self.source_store = store
        self.checkpoint = self.target = self.recovery_watch = None
        self.server_expected = None

    def install_recovery_server(self, case, profile, port, lease, epoch):
        stage = case.parent/'staged-profile'
        stage.mkdir(mode=0o700)
        checkpoint, staged = stage_confirmed_recovery(CheckpointStore(self.source_store), stage)
        fixture = source.verify(self.source_store, checkpoint, profile)
        target = profile/'save/save_008.xml.gz'
        if any(target.parent.iterdir()): raise ValueError('server save directory is not empty')
        os.link(staged, target, follow_symlinks=False); target.chmod(0o400)
        if live.sha(target) != checkpoint.sha256: raise ValueError('recovery save changed')
        protected = recovery_bridge.install_probe(case, profile, port, lease, epoch)
        protected.append(recovery_bridge.install_saved_identity_fixture(case, fixture))
        self.checkpoint, self.target, self.server_case = checkpoint, target, case
        self.server_expected = {p: live.sha(p) for p in protected}

    def check_server_files(self):
        if (self.checkpoint is None or self.server_expected is None or
                live.sha(self.target) != self.checkpoint.sha256 or
                any(live.sha(p) != digest for p, digest in self.server_expected.items())):
            raise ValueError('recovery save or server configuration changed')
        return True

    def recovery_server_command(self, case, game, binds, lock, display, auth, user, seed):
        if case != self.server_case: raise ValueError('unexpected server case')
        self.check_server_files()
        command = load.readonly_save_command(case, game, binds, lock, display, auth, user, seed, self.target)
        pos = command.index('--die-with-parent')
        for path in self.server_expected:
            command[pos:pos] = ['--ro-bind', str(path), str(path)]; pos += 3
        return command

    def enroll_recovered_server(self, *, sock, lease, epoch, deadline, server_proc, server_started,
                                game, steam, home, uid, profile):
        deadline = min(deadline, self.run_deadline)
        watch = recovery.RecoveryWatch(profile/'engine-output.log', self.checkpoint.marker)
        identity = None
        def check():
            nonlocal identity
            if time.monotonic() >= deadline: raise TimeoutError('recovery deadline expired')
            current = base.client.game_identity(server_proc, server_started, game)
            if current is not None:
                if identity is not None and current != identity: raise RuntimeError('recovered X4 changed')
                identity = current
            elif identity is not None: raise RuntimeError('recovered X4 disappeared')
            if live.steam_identity(home, uid) != steam: raise RuntimeError('Steam identity changed')
            if watch.stage and identity is None: raise RuntimeError('recovery evidence without owned X4')
        def verify():
            check()
            if identity is None: raise RuntimeError('recovery evidence without owned X4')
            self.check_server_files(); check()
        peer = recovery_bridge.activate(sock, watch, lease, epoch, deadline, check, verify)
        self.recovery_watch = watch
        return peer, identity

    def verify_logs(self, server_log, client_log, ticket, marker):
        if self.recovery_watch is None or not self.recovery_watch.poll() or self.recovery_watch.stage != 3:
            raise ValueError('recovered server marker/pause observation changed')
        check_client_log(client_log, ticket, marker)
        if not self.recovery_watch.poll() or self.recovery_watch.stage != 3:
            raise ValueError('recovered server log changed')

    def offer_and_download(self, world, service, handle, out, profile):
        ticket, target = super().offer_and_download(world, service, handle, out, profile)
        if (self.checkpoint is None or ticket['checkpoint_id'] == self.checkpoint.checkpoint_id or
                self.marker == self.checkpoint.marker):
            raise ValueError('join checkpoint is not fresh relative to recovery source')
        return ticket, target

    def on_ready(self, **kwargs):
        client_guard = kwargs['check_protected']
        def combined():
            if client_guard() is not True: return False
            self.check_server_files()
            return client_guard() is True
        kwargs['check_protected'] = combined
        return super().on_ready(**kwargs)


def run(args):
    out, store = check_separate(args.out, source.DEFAULT_STORE)
    participant = RecoveredParticipant(time.monotonic()+args.timeout, store)
    old_client = base.client.install_probe
    def install_client(case, profile, ticket):
        config = old_client(case, profile, ticket)
        marked.identity.inject(case, 'load')
        participant.install(case)
        return config
    result = None
    original_error = None
    try:
        base.client.install_probe = install_client
        result = base.run(args, experiment=participant)
    except BaseException as error:
        original_error = error
        try: participant.cleanup_before_owned_processes()
        except BaseException as cleanup: error.add_note('participant cleanup failed: '+str(cleanup))
        raise
    finally:
        base.client.install_probe = old_client
        errors = []
        for name, action in (('participant close',participant.close), ('client redaction',participant.redact)):
            try: action()
            except BaseException as error: errors.append(name+': '+str(error))
        if errors:
            detail = '; '.join(errors)
            if result is not None:
                result.update(success=False, cleanup_error=detail)
            elif original_error is not None: original_error.add_note(detail)
            else: raise RuntimeError(detail)
    if result.get('success'):
        profile = Path('case/home/.config/EgoSoft/X4/45841/engine-output.log')
        try: participant.verify_logs(out/'server'/profile, out/'client'/profile, participant.ticket, participant.marker)
        except (OSError,ValueError) as error: result.update(success=False, error='final evidence invalid: '+str(error))
    result.update(scope='recovered isolated Linux server and one Linux client; loopback TCP; no gameplay or Internet',
        source_checkpoint_id=source.CHECKPOINT_ID, source_sha256=source.SHA256,
        exact_loaded_file_proven=False, windows_tested=False, internet_tested=False, gameplay_tested=False)
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',type=Path,required=True); parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--display',required=True); parser.add_argument('--timeout',type=float,default=600)
    parser.add_argument('--seed',type=int,default=276944566)
    try: result = run(parser.parse_args())
    except (OSError,ValueError,RuntimeError) as error: parser.exit(1,'REFUSED: '+str(error)+'\n')
    print(json.dumps(result,indent=2)); return 0 if result['success'] else 1


if __name__ == '__main__': sys.exit(main())
