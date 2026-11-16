"""Opt-in one-client diagnostic inside the recovered server's owner thread.

Caller owns the global X4 lock, both process records, server and its cleanup.
This module does not launch on import and is Linux/loopback-only. After the
bounded first connection ends, the caller may continue its normal accept loop.
Neither Windows, internet, gameplay nor exact bytes consumed by X4 are proven.
"""
from pathlib import Path
import socket
import time

import authority_recovered_remote_load_pair_live as combined
import authority_recovery_tcp_join_live as recovery


class ServerClient(combined.RecoveredRemoteParticipant):
    """Reuse the paired runner without ever closing the server's control."""
    def cleanup_diagnostic(self):
        errors = []
        for helper in reversed(self.helpers):
            try: helper.stop()
            except BaseException as error: errors.append(error)
        for name in ('remote_ipc', 'ipc', 'client_tcp', 'second', 'sock'):
            obj = getattr(self, name, None)
            if obj is not None:
                try: obj.close()
                except BaseException as error: errors.append(error)
                else: setattr(self, name, None)
        self.fault = True
        if errors:
            raise RuntimeError('diagnostic helper or socket cleanup unconfirmed') from errors[0]
        return True


def record_client_evidence(result, ticket, marker):
    """Record only noncredential correlation data after final checks succeed."""
    fields = recovery.base.client.FIELDS
    if (type(ticket) is not dict or set(ticket) != set(fields) or
            type(marker) is not str):
        raise ValueError('invalid diagnostic correlation data')
    result.update(client_ticket={field: ticket[field] for field in fields},
                  client_loaded_marker=marker,
                  client_checkpoint_id=ticket['checkpoint_id'],
                  client_checkpoint_sha256=ticket['sha256'],
                  client_final_log_and_inputs_verified=True,
                  client_owned_process_stopped=True)


def run_one(participant, *, args, out, game, home, uid, steam, auth, user,
            processes, server_proc, server_started, server_identity, checkpoint,
            recovery_target, server_expected, recovery_watch, listener, host, service,
            world, session, control, check_server):
    """Load one genuine local client, confirm admission/resume and disconnect.

    Must run on the server's owner/main thread; it registers its X4 in the
    caller's process list. The caller MUST run cleanup_diagnostic before owned
    X4 cleanup and must retain the global lock if that cleanup is uncertain.
    """
    base = recovery.base
    deadline = participant.run_deadline
    participant.checkpoint = checkpoint
    participant.target = recovery_target
    participant.server_expected = server_expected
    participant.recovery_watch = recovery_watch
    participant.server_library = out/'case/extensions/x4_lan_lab/native/x4lan_net.so'
    participant.session, participant.control, participant.host = session, control, host
    participant.participants = world._participants
    client_out = out/'client'; client_out.mkdir(mode=0o700)
    case, profile, binds, lock = base.snapshot.prepare_case(client_out, game, home)
    if any((profile/'save').iterdir()): raise ValueError('private client profile not empty')
    participant.client_tcp = socket.create_connection(listener.getsockname(), timeout=min(1, recovery.marked.remaining(deadline)))
    accepted, address = listener.accept()
    if address != participant.client_tcp.getsockname() or address[0] != '127.0.0.1':
        accepted.close(); raise ValueError('unexpected diagnostic peer')
    participant.server_tcp = accepted
    try:
        handle = host.adopt(accepted)
    except BaseException:
        accepted.close()
        raise
    # Do not ask for an offer until this first join's pause/save completed.
    for operation in ('pause', 'save'):
        check_server()
        pending = world.session.pending
        if pending is None or pending.operation != operation: raise RuntimeError('unexpected diagnostic join operation')
        host.tick(min(.1, recovery.marked.remaining(deadline)))
        check_server()
    ticket, target = participant.offer_and_download(world, service, handle, client_out, profile)
    config = base.client.install_probe(case, profile, ticket)
    recovery.marked.identity.inject(case, 'load')
    participant.install(case)
    protected = [config, case/'extensions/x4_lan_lab/ui.xml', profile/'content.xml', profile/'config.xml']
    protected += [case/'extensions/x4_lan_lab/ui'/name for name in
                  ('client_load_barrier.lua', 'x4_client_load_engine.lua', 'authority_download_load_probe.lua')]
    protected += participant.protected(case)
    expected = {path:base.live.sha(path) for path in protected}
    command = base.load.readonly_save_command(case, game, binds, lock, args.display, auth, user, args.seed, target)
    pos = command.index('--die-with-parent')
    for path in protected:
        command[pos:pos] = ['--ro-bind', str(path), str(path)]; pos += 3
    proc, started = base.spawn_owned_gated(command, client_out/'process.log', processes)
    watch = base.client.ReceiptWatch(profile/'engine-output.log', ticket)
    client_identity = None
    result = {'client_admitted':False, 'exact_loaded_file_proven':False}
    while True:
        recovery.marked.remaining(deadline)
        check_server()
        actual = base.client.game_identity(proc, started, game)
        if actual is not None:
            if client_identity is not None and actual != client_identity: raise RuntimeError('client X4 changed')
            client_identity = actual
        elif client_identity is not None: raise RuntimeError('client X4 disappeared')
        if base.live.steam_identity(home, uid) != steam: raise RuntimeError('Steam identity changed')
        if any(base.live.sha(path) != digest for path, digest in expected.items()):
            raise ValueError('client protected configuration changed')
        participant.pump_loading()
        caught_up = watch.poll()
        if watch.stage and client_identity is None: raise RuntimeError('receipt without owned client X4')
        if caught_up and watch.stage == 2:
            if base.live.sha(target) != ticket['sha256']: raise ValueError('client staged save changed')
            def check_protected():
                check_server()
                return base.check_live_context(deadline=deadline, server_proc=server_proc,
                    server_started=server_started, server_identity=server_identity, client_proc=proc,
                    client_started=started, client_identity=client_identity, game=game, home=home,
                    uid=uid, steam=steam, target=target, ticket=ticket, expected=expected)
            original_accept = session.accept
            try:
                participant.on_ready(world=world, handle=handle, ticket=ticket, target=target,
                    server_identity=server_identity, server_proc=server_proc, server_started=server_started,
                    client_identity=client_identity, client_proc=proc, client_started=started,
                    game=game, out=out, deadline=deadline, result=result, check_protected=check_protected)
            finally:
                # TCPMarkedParticipant temporarily wraps accept with a guard for
                # this particular client. Never leak that guard to later joins.
                session.accept = original_accept
            if (result.get('client_admitted') is not True or
                    result.get('native_server_and_client_resume_confirmed') is not True or
                    result.get('tcp_claim_used') is not True or
                    result.get('helper_clean_exit') is not True):
                raise RuntimeError('diagnostic admission or participant resume not confirmed')
            # Stop helpers before X4, then verify final evidence while the server
            # stays alive. Keep the process registered until stop is confirmed.
            participant.cleanup_diagnostic()
            remaining = base.snapshot.stop_owned(proc, started)
            if remaining: raise RuntimeError('diagnostic client X4 stop unconfirmed')
            matches = [index for index, record in enumerate(processes)
                       if len(record) == 2 and record[0] is proc and record[1] == started]
            if len(matches) != 1: raise RuntimeError('diagnostic process registration changed')
            del processes[matches[0]]
            check_server()
            if (base.live.sha(target) != ticket['sha256'] or
                    any(base.live.sha(path) != digest for path, digest in expected.items())):
                raise ValueError('final client inputs changed')
            relative_log = Path('case/home/.config/EgoSoft/X4/45841/engine-output.log')
            participant.verify_logs(out/'server'/relative_log, out/'client'/relative_log, ticket, participant.marker)
            check_server()
            participant.redact()
            participant.config = None
            record_client_evidence(result, ticket, participant.marker)
            return result
        time.sleep(.1)
