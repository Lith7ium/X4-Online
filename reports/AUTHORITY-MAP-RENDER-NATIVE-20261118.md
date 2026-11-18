# Native Linux map renderer observation

One isolated Linux X4 run passed the closed/open/closed map observation on
18 November 2026. The opened map returned one raw local component ID,
`379303`. This establishes the basic menu/FFI read path for this case. It does
not establish viewport clipping, radar knowledge, component type, ship coverage,
portable identity or network interest behavior.

## Observed result

After the existing ordered checkpoint-load, marker, fixture-read and pause
receipts, the private probe emitted:

```text
AUTH_MAP_RENDER CLOSED_BEFORE count=0
AUTH_MAP_RENDER OPEN count=1 ids=379303
AUTH_MAP_RENDER CLOSED_AFTER count=0
AUTH_MAP_RENDER DONE
```

The final validator accepted these records after stopping the owned process
group. The loaded fixture reader reported game time `3.014`; all map records
carried X4's displayed time `3.01`. The probe checked the private save path and
paused state before observations and around map operations. These sampled
checks do not prove continuous pause or exact runtime/save actor binding.

The runner confirmed no owned processes remained, unchanged protected files
and staged save, and unchanged checked Steam identity. A subsequent independent
process check found no X4 executable, and the temporary X4 lock was absent.
The run used the existing read-only host/game mounts, a new disposable 45841
profile and an 800x600 window. No save, ship order or ship-position write was
requested by the map probe.

## Reproduction and retained evidence

Tested source base: `9a993dfef01c9ccf71a9be7a8b2e9b3fb5092af9` on the authority
fork. The private runner extends `authority_sector_read_live.py` with the
reviewed sampler and a single map lifecycle probe. It retains the existing
load/update owner and uses the archived, independently pinned registry script.
The installed X4 binary was checked against the runner's pinned Linux image.

Private artifacts, retained locally and excluded from Git:

| Artifact | SHA-256 |
| --- | --- |
| `.local/map-render-native-20261118-01/result.json` | `3937407bce780924d2c7d525da56fd80386bb6ec4f4ce83bc81bf6e368250659` |
| `.local/map-render-native-20261118-01/case/home/.config/EgoSoft/X4/45841/engine-output.log` | `0319aa8224ac142365bc8dc1c3e6bbef3a066dcd55881120ddcbec9dfd4c9eb8` |
| `.local/map-render-native-prep-20261118/run_map_probe.py` | `e84ab267abfb17ec21fae82aecd5fb2f438b383bf2dff799d84a6f94b69aab29` |
| `.local/map-render-native-prep-20261118/map_probe.lua` | `f0db395a24adfe00248ce4189d026a08c8ed844a52e658661c1a9678f2234d3a` |
| `src/authority/lua/map_render_observation.lua` | `496467e7ca9d604724e4e807954ed26664fbed1cefcea1361a87d6c0a477760f` |

The invocation was:

```sh
.local/validation-venv/bin/python \
  .local/map-render-native-prep-20261118/run_map_probe.py \
  --game '/var/home/bazzite/.local/share/Steam/steamapps/common/X4 Foundations' \
  --out .local/map-render-native-20261118-01 --display :0 --timeout 300
```

The output directory must be new for another invocation. Before this run,
Python/Lua syntax checks, a targeted receipt-parser and installer dry check,
and an independent read-only integration review completed. This was one native
game run; the full suite was not repeated. Historical suite failures remain
unresolved by this work.

## Next boundary

Vary map focus, pan, zoom, filters and offscreen selection in a disposable
client, with identified local components and readback of the camera state.
One returned component is insufficient to infer visibility policy. The local
map source exposes `GetMapState`/`SetMapState`, `GetMapFocusComponent`,
`SetFocusMapComponent` and `ZoomMap`; their use by a later probe still needs
native validation. Resolve any sector reference in the current process rather
than reusing a historical numeric ID.

No Windows, Internet, server/client movement, gameplay or interest subscription
was tested here. Server graphics work remains deferred at the user's request.
