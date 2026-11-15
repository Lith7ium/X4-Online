# Opt-in one-X4 job activation diagnostic

`authority_job_registry_single_live.py` prepares one disposable Linux X4
instance and a private `45841` profile. Import never starts X4. This runner is
not installed as a game extension. One bounded native Linux diagnostic is
recorded below. It is not a multiplayer server or a production protocol.

The runner reuses the existing private case/namespace, world-control bridge,
and owned-process cleanup. It injects its probe only into the fresh overlay and
calls the job host tick through the existing world-bridge update callback. The
host starts with an **empty baseline**, so its `new_registry_entry` label means
only that an observed object was first enrolled in this test's register; it does
not establish a newly built ship. The MD queue observes job activations only,
not every creation path. Events before queue initialization, after the final
status, or not emitted by X4 are outside the observation. The queue continues
through the bounded drain after the nominal window; its records have no event
timestamps and cannot establish a rate or a strict original-window count.

A private loopback UDP channel uses a fresh role lease and epoch. The supervisor
confirms pause, confirms resume, sends START **once**, checks the STARTED
receipt, then consumes ordered event and completion receipts before requesting
another confirmed pause and owned-process cleanup. Missing or out-of-order
event records, malformed or wrong-epoch receipts, and host faults detected
before completion fail the case. Receipts arriving after the accepted DONE are
not inspected. The source is never
reinitialized after uncertain START delivery. Local MD acknowledgment establishes
neither durable delivery nor a client-side object. Zero observed events are
inconclusive, not evidence that no ships appeared.

In `result.json`, `success` and `lifecycle_success` report only successful
completion of this diagnostic's controlled lifecycle and cleanup. A successful
run with zero events has `event_observed=false` and remains inconclusive.
`event_observed=true` means at least one validated event was accepted in a
successful lifecycle; on a failed lifecycle `false` makes no claim that X4
emitted none. `event_coverage_proven` is always false. The supervisor retains
at most 4096 validated events as sequence, index, and classification; actor
identities and leases are omitted. Exceeding the bound fails the diagnostic.
The DONE receipt must report the configured empty baseline exactly as zero.

On 15 November 2026, the isolated Linux run
`.local/authority-job-observe-01` reported a successful lifecycle, a confirmed
pause and owned-process cleanup. Its result records 46 job activations and 46
local acknowledgments against baseline zero; all 46 retained records were
classified `new_registry_entry`. The private configuration specified a 60-second
nominal window and a 5-second drain timeout. As the queue remains active during
the drain and the events have no timestamps, the 46 cannot be attributed
strictly to the nominal 60 seconds. The process log records universe generation;
the event counts and pause/cleanup confirmations come from `result.json`.
The empty baseline makes these first enrollments in this diagnostic's register,
not proof of ship birth. This observation does not establish complete event
coverage, client delivery, or a shared multiplayer world.

The runner issues no bridge checkpoint command (`checkpoint_requested=false`).
This is not a claim that every private filesystem write or game save mechanism
was independently observed. The snapshot harness disables autosave in its
private profile, but no normal profile or user save is used. Process/Steam
identity, bridge deadlines, and cleanup are fenced; the result fails if cleanup
cannot be confirmed. Configuration leases are redacted during normal cleanup;
forced termination of the supervisor can leave its mode-0600 private config.

Example only, after an independent review and a fresh safety preflight:

```sh
python tools/dev/authority_job_registry_single_live.py \
  --game "<pinned X4 directory>" --out .local/<fresh-run-name> \
  --display "<private X11 display>" --window 60 --timeout 180
```

The executable is pinned by the existing harness. This path does not prove
universe coverage, ship birth, client delivery, Windows/internet operation,
combat, trade, boarding, or independent-sector gameplay.
