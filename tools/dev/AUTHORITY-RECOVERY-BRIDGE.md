# Experimental recovered-world bridge

`authority_recovery_bridge_live.py` is an opt-in, one-process Linux diagnostic.
It stages a copy of the confirmed marked checkpoint from a completed marked
bridge experiment into a private profile, without writing to that source
experiment. The source must satisfy the existing `authority_recovery_live`
provenance check. The output and source experiment must be disjoint.

The isolated X4 loads slot 008. A host log watcher requires the ordered load
request, the checkpoint's matching marker after the game-load event, and a
confirmed pause. A private bridge remains inactive until it sends READY and
receives the supervisor's lease- and epoch-bound ACTIVATE, after the host checks
that ordered evidence, the same live owned X4, the staged bytes, and protected
configuration. Lua also checks that the recovered game is paused on activation.
A dedicated copy of the load marker observer does not register a `Stored`
listener; the bridge owns that event. Unexpected messages, lost pause, changed
identity or indeterminate bridge operations fail the experiment.

A new coordinator is created with a new epoch. One **synthetic waiting join**
causes it to confirm pause and write a new marked checkpoint to a **fresh output
store** using slot 009. No client is connected or admitted and no resume is
requested. X4 and the private launcher use the newer exec gate and owned cleanup;
normal profiles are not mounted writable. The output records observations and
failures.

The marker is evidence of saved MD state after a load event, not proof that X4
read every staged byte. The exact amount of simulation between loading and pause
is unproven. A fresh server checkpoint does not establish persistence of
client-side actions, crash recovery, gameplay, Windows, internet transport, or
a working multiplayer session. This diagnostic does not alter gameplay state to
prove world-wide state fidelity. All operations assume exclusive local control;
loopback leases are not remote authentication, and file/process checks are
point-in-time observations rather than adversarial atomic OS fencing.

Run focused offline checks with:

```sh
python3 -m unittest tests.test_authority_recovery_bridge_live
```

On 2026-11-15, one isolated Linux run loaded the previously confirmed marked
checkpoint into a new X4 process, observed its marker and pause, activated the
bridge, and let a new coordinator write a fresh confirmed marked checkpoint to
a separate store after a synthetic waiting join. Owned-process cleanup reported
no remaining members. No client was admitted and the limitations above remain.
