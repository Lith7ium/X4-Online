# Native Linux map view comparison

The six-view observation completed in one isolated Linux X4 run on 18 November
2026. Player zoom and restoration worked. The requested cross-sector fixture
focus, its near distance and the requested pan did not match readback. **This
does not pass the intended viewport-visibility test.** The unchanged one-object
list cannot establish either viewport clipping or its absence.

## Measurements

The live player object was `379304`, in sector `370749`; the separately read
fixture was `487472`, in sector `487406`. These are process-local references,
not portable identities. The fixture and sector came from the existing two
ordered, verified fixture reads. The probe checked their native validity and
sector relationship; the player was queried in the current process.

Every view returned exactly `[379304]`: the player object, without the fixture.
Camera fields below are native map values, not a claim about world coordinates.

| Requested view | Observed focus | Camera distance | Camera offset X |
| --- | ---: | ---: | ---: |
| Initial | 379304 | 20000 | -3600000 |
| Player near | 379304 | 20000 | -3600000 |
| Player wide | 379304 | 1999999.75 | -3600000 |
| Fixture near | 0 | 1986161 | -3566726.25 |
| Pan from fixture view | 0 | 1986161 | -3199998.5 |
| Restored | 379304 | 20000 | -3600000 |

The requested pan was +2000000 in X at an intended distance of 20000. Neither
condition was reached. Because the preceding fixture focus also failed, this
cannot be treated as a controlled offscreen-object comparison. Whether map
knowledge, view limits or another condition caused these results is unproven.
The probe did not query `IsKnownToPlayer` or radar visibility.

Each logged view followed at least one second of settling and two samples at
least 0.25 seconds apart with equal raw lists/focus and camera values within the
probe's tolerance. This is sampled stability, not proof that a requested
camera target was reached. The Python evaluator separately reports each effect:
player focus and restoration true; fixture focus, distances and pan false.
Restoration compares position/distance with relative tolerance 1e-6 and absolute
tolerance 0.01; angles use absolute tolerance 1e-4 in native units.

`result.json` has `success=true` for completion of the ordered observation and
cleanup. Its `view_effects` contains the failed requested effects, and
`map_viewport_semantics_proven` remains false. Do not summarize this as a passed
visibility test or infer cross-sector map focus from the phase names.

## Reproduction and scope

Source base: `c8fda4ba`. The private probe extends the prior isolated map
lifecycle runner, reusing its load owner, paused checks, read-only mounts and
disposable windowed profile. It changes only map UI state. The previous native
run was not repeated unchanged, and no full suite was run.

Before launch, the corrected probe passed LuaJIT compilation and an offline
six-phase lifecycle harness. The final harness used the real event-ID resolver
and a uint64 fixture above 2^53. Its output passed the Python parser; malformed
counts, fields, duplicate records and nonfinite cameras were rejected. Native
API behavior remained outside this synthetic check.

Private retained artifacts and SHA-256:

| Artifact | SHA-256 |
| --- | --- |
| `.local/map-view-native-20261118-01/result.json` | `5e7c7be0a247b359e1444cd9df88d65094922224293feac12e397bdc7d632350` |
| `.local/map-view-native-20261118-01/case/home/.config/EgoSoft/X4/45841/engine-output.log` | `215a96b4fadaa995cc4e12256a16ab13e11e8c4fe4acf14fcd90bbceb230f9ff` |
| `.local/map-view-native-prep-20261118/run_map_probe.py` | `186d0ce517b9a2842499bcaf819854017b4b4b0b2e5895c5f9ded17e63cac672` |
| `.local/map-view-native-prep-20261118/map_probe.lua` | `c90626df462787a68ca2ddffb3b71fb37cede62db26bba81e4c5d3bf34869ceb` |

Invocation: the prior report's command with preparation directory
`map-view-native-prep-20261118` and output `map-view-native-20261118-01`, still
using display `:0`, timeout 300 and the pinned installed Linux X4. The original
sampler hash remains unchanged. Output directories are single-use.

Final checks confirmed owned-process cleanup, protected overlay/staged-save
identity and checked Steam identity. An independent follow-up found no X4
process or temporary X4 lock. No Windows, Internet, network interest or gameplay
was tested. Sampled pause checks do not prove continuous pause.

## Next decision and experiment

Do not connect this raw list directly to server subscriptions. Besides its
unproven visibility semantics, a client object list derived from stale local
positions cannot by itself discover all objects newly entering a viewed area.
The proposal to report the viewed area and select relevant ships on the server
has been submitted to the user; it is not yet approved or implemented.

Before another native visibility test, establish known/radar-visible objects
and reset to the confirmed player near view before attempting a pan. Verify
the actual camera effect independently of the list. A fixture that cannot be
focused is not a valid substitute for an offscreen control object. Selected
objects, map filters, multiple visible NPCs and actual screen clipping remain
untested.
