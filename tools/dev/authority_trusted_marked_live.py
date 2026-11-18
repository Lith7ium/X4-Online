#!/usr/bin/env python3
"""Opt-in, isolated Linux/Linux trusted-marker admission experiment.

This uses cooperative local client observations, not an independent proof of
the bytes X4 read. It does not exercise multiplayer gameplay or the Internet.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tools/dev')]
import authority_two_x4_live as base
import authority_two_x4_identity_live as identity
import authority_two_x4_resume_live as resume
import authority_identity_live as identity_evidence
import authority_marked_admission_evidence as file_evidence
from authority.experimental_client_load import ExperimentalClientLoad
from authority.load_observations import validate_client_receipts
from authority.save_transfer import receive
from authority.trusted_marker_load_session import TrustedMarkerLoadSession


def remaining(deadline):
    value = deadline - time.monotonic() - 1.0
    if value <= 0: raise TimeoutError('insufficient native control time')
    return value


def accept_claim(session, connection, claim, result, *, guard=None):
    """Record admission immediately, even if a later control step fails."""
    try:
        if guard is None:
            session.accept(connection, claim)
        else:
            session.accept(connection, claim, pre_accept=guard)
    except BaseException:
        result.update(client_admitted=None, admission_state='indeterminate')
        raise
    result.update(client_admitted=True, admission_state='accepted', trusted_client_claim=True,
                  exact_loaded_file_proven=False)


def observe_logs(server_log, client_log, ticket, marker):
    """Compare bounded, stable log snapshots before trusting the local client."""
    before = file_evidence._read_regular(server_log, file_evidence.MAX_LOG, collect=True)
    after = file_evidence._read_regular(client_log, file_evidence.MAX_LOG, collect=True)
    server_ships = identity_evidence.observations_bytes(before[2], 'save')
    client_ships = identity_evidence.observations_bytes(after[2], 'load')
    if [(x['name'], x['macro']) for x in server_ships] != [(x['name'], x['macro']) for x in client_ships]:
        raise ValueError('fixture observations differ')
    if after[2] and not after[2].endswith(b'\n'):
        raise ValueError('client log incomplete')
    validate_client_receipts(after[2], ticket, marker)
    if (file_evidence._read_regular(server_log, file_evidence.MAX_LOG, collect=True) != before or
            file_evidence._read_regular(client_log, file_evidence.MAX_LOG, collect=True) != after):
        raise ValueError('log changed during observation')



def install_marked_load_probe(case):
    """Add marker inspection without injecting the expected marker into X4."""
    lab = case / 'extensions/x4_lan_lab'; ui = lab / 'ui'
    shutil.copyfile(ROOT / 'src/authority/md/checkpoint_marker.xml', lab / 'md/authority_checkpoint_marker.xml')
    shutil.copyfile(ROOT / 'tools/dev/authority_checkpoint_marker_probe.lua', ui / 'authority_checkpoint_marker_probe.lua')
    config = ui / 'config.lua'; text = config.read_text(encoding='ascii')
    if not text.endswith('}\n'): raise ValueError('unexpected client configuration')
    config.write_text(text[:-2] + ', authority_marker_phase="load"}\n', encoding='ascii')
    probe = ui / 'authority_download_load_probe.lua'; text = probe.read_text(encoding='utf-8')
    hook = " elseif state=='observing' then\n"
    if text.count(hook) != 1: raise ValueError('unexpected load probe')
    probe.write_text(text.replace(hook, hook + '  if not X4LAN_AUTHORITY_MARKER_READY() then return end\n'), encoding='utf-8')
    manifest = lab / 'ui.xml'; text = manifest.read_text(encoding='utf-8')
    hook = '    <file name="ui/authority_download_load_probe.lua" />\n'
    if text.count(hook) != 1: raise ValueError('unexpected UI manifest')
    manifest.write_text(text.replace(hook, '    <file name="ui/authority_checkpoint_marker_probe.lua" />\n' + hook), encoding='utf-8')


class GuardedEngine:
    """Recheck process identity and deadline around each native control call."""
    def __init__(self, engine, guard, deadline):
        self.engine, self.guard, self.deadline = engine, guard, deadline

    def _call(self, operation):
        self.guard()
        old = self.engine._timeout
        self.engine._timeout = min(old, remaining(self.deadline))
        try: getattr(self.engine, operation)()
        finally: self.engine._timeout = old
        self.guard()

    def pause(self): self._call('pause')
    def resume(self): self._call('resume')


class MarkedParticipant(resume.Participant):
    marker_required = True
    requires_verification_context = True

    def request(self, operation):
        self.guard()
        old = self.timeout
        self.timeout = min(old, remaining(self.deadline))
        try: super().request(operation)
        finally: self.timeout = old
        self.guard()

    def join(self, world):
        self.connection = object()
        self.session = TrustedMarkerLoadSession(world, enabled=True)
        return self.session.attach(self.connection)

    def offer_and_download(self, world, service, handle, out, profile):
        if any((profile / 'save').iterdir()):
            raise ValueError('private client save directory is not empty')
        bound = self.session.begin(self.connection)
        self.offer, self.marker = bound.offer, bound.marker
        save = world._load_offers[handle].save
        downloaded = receive('127.0.0.1', service.port, service.token, 1, save,
                             out / 'download', retries=0, timeout=60)
        target = profile / 'save' / base.snapshot.SLOT
        if target.exists() or target.is_symlink():
            raise ValueError('client save target appeared during transfer')
        downloaded.rename(target)
        target.chmod(0o400)
        self.client_load = ExperimentalClientLoad(enabled=True, offer=self.offer,
                                                   expected_marker=self.marker)
        self.client_load.verify_staged(target)
        ticket = {key: getattr(self.offer, key) for key in base.client.FIELDS if key != 'slot'}
        ticket['slot'] = 'save_009'
        self.ticket = dict(ticket)
        return ticket, target

    def install(self, case):
        super().install(case)
        install_marked_load_probe(case)

    def protected(self, case):
        lab = case / 'extensions/x4_lan_lab'
        return super().protected(case) + [lab / 'md/authority_checkpoint_marker.xml',
            lab / 'ui/authority_checkpoint_marker_probe.lua', lab / 'md/authority_identity_fixture.xml',
            lab / 'ui/authority_identity_probe.lua']

    def on_ready(self, *, world, handle, ticket, target, server_identity, server_proc, server_started,
                 client_identity, client_proc, client_started, game, out, deadline, result, check_protected):
        profile = Path('case/home/.config/EgoSoft/X4/45841/engine-output.log')
        client_log = out / 'client' / profile
        observe_logs(out / 'server' / profile, client_log, ticket, self.marker)
        attempt = self.offer.attempt_id
        self.client_load.observe_load_requested(attempt)
        self.client_load.observe_loaded_marker(attempt, self.marker)
        self.client_load.observe_pause(attempt, True)
        claim = self.client_load.make_claim(attempt)
        def check_processes():
            if (time.monotonic() >= deadline or
                base.client.game_identity(server_proc, server_started, game) != server_identity or
                base.client.game_identity(client_proc, client_started, game) != client_identity):
                raise RuntimeError('deadline or owned X4 process changed')
        def check_context():
            check_processes()
            if check_protected() is not True: raise RuntimeError('protected files changed')
            return True
        check_context()
        self.guard, self.deadline = check_context, deadline
        self.handle = handle
        self.enroll(ticket['world_epoch'], deadline - 1.0)
        GuardedEngine(world._engine, check_context, deadline).pause()
        self.request('pause')
        check_context()
        observe_logs(out / 'server' / profile, client_log, ticket, self.marker)
        check_context()
        accept_claim(self.session, self.connection, claim, result, guard=check_context)
        check_processes()
        if world.session.pending is None or world.session.pending.operation != 'resume':
            raise RuntimeError('resume not scheduled')
        original_engine = world._engine
        world._engine = GuardedEngine(original_engine, check_context, deadline)
        try:
            result['server_state'] = 'indeterminate'
            world.step()
            check_processes()
            if world.session.state != 'running': raise RuntimeError('world did not resume')
            result.update(server_state='running', native_server_and_client_resume_confirmed=True)
            self.second_connection = object()
            self.session.attach(self.second_connection)
            check_processes()
            if world.session.pending is None or world.session.pending.operation != 'pause':
                raise RuntimeError('pause not scheduled')
            result['server_state'] = 'indeterminate'
            world.step()
            check_processes()
            result.update(server_state='paused', native_server_and_client_pause_confirmed=True)
        finally:
            world._engine = original_engine
        if (world.session.state != 'saving' or world.session.pending is None
                or world.session.pending.operation != 'save'):
            raise RuntimeError('expected a pending save after the join pause')
        result.update(coordinator_state='saving', pending_operation='save')


def run(args):
    out = base.snapshot.output_path(args.out)
    participant = MarkedParticipant()
    old_server, old_client = base.server.install_probe, base.client.install_probe
    def install_server(case, port, lease, epoch, *, marker_required=False):
        old_server(case, port, lease, epoch, marker_required=marker_required)
        identity.inject(case, 'save')
    def install_client(case, profile, ticket):
        config = old_client(case, profile, ticket)
        identity.inject(case, 'load')
        participant.install(case)
        return config
    result = None
    original_error = None
    try:
        base.server.install_probe, base.client.install_probe = install_server, install_client
        result = base.run(args, experiment=participant)
    except BaseException as error:
        original_error = error
        raise
    finally:
        base.server.install_probe, base.client.install_probe = old_server, old_client
        cleanup_errors = []
        for name, action in (('participant close', participant.close),
                             ('client lease redaction', lambda: base.redact_client_after_owned_stop(participant, result))):
            try: action()
            except BaseException as error: cleanup_errors.append(name + ' failed: ' + str(error))
        if cleanup_errors:
            detail = '; '.join(cleanup_errors)
            if result is not None:
                result['success'] = False
                result['cleanup_error'] = '; '.join(filter(None, (result.get('cleanup_error'), detail)))
            elif original_error is not None:
                original_error.add_note(detail)
            else:
                raise RuntimeError(detail)
    if result.get('success'):
        profile = Path('case/home/.config/EgoSoft/X4/45841/engine-output.log')
        try:
            observe_logs(out / 'server' / profile, out / 'client' / profile,
                         participant.ticket, participant.marker)
        except (OSError, ValueError) as error:
            result.update(success=False, error='final marker/identity evidence invalid: ' + str(error))
    result['scope'] = ('two isolated Linux X4 processes; trusted marker claim; '
                       'local admission and native pause/resume; no gameplay or Internet')
    (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--display', required=True)
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--seed', type=int, default=276944566)
    try: result = run(parser.parse_args())
    except (OSError, ValueError, RuntimeError) as error: parser.exit(1, 'REFUSED: ' + str(error) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['success'] else 1


if __name__ == '__main__': sys.exit(main())
