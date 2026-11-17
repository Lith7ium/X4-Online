# Graphics arena lifetime after drawing suppression

2026-11-17. Internal, bounded static investigation; no game launched or engine
bytes changed by this task. This note records addresses and control-flow
observations, not Egosoft code or disassembly.

## Outcome

The native no-draw branch omits graphics arena rotation, cursor reset and
fence-ordered retirement that normally occur inside `0x21eddf0`. A standalone
safe housekeeping entry point has **not** been established. Resetting the
allocator cursor or advancing its index alone would discard required ordering
with pending copy commands and deferred destruction.

The inspected installed Linux executable has SHA-256
`113f73d74570084f6ce18a659b365009eccf579fb66dbabb5dad2b1718045f20`,
build ID `77cf7ac0ff32d88ffd3db7eb6ea2e025aecb711d` (X4 9.00/611726).

## Observed failure and scope

Private trial `headless-scheduler-native-20261117-02` records 2,274 mesh-buffer
update failures: radar 1,098, stardust 1,087, text meshes 89. First occurrence is
engine-output line 93, game time 7.29; last is line 6999, game time 62.14. The
first armed scheduler record accompanies game time 0.985643. The retained H0
software-rendered baseline has no matching warning. Different scene/configuration
prevents treating that comparison as controlled causal proof.

The exact warning string is at `0x2e38d50`, logged at `0x224c5fa` inside mesh
update function `0x224c180`. It returns failure status 2 after buffer cleanup.
The warning is an actual failed update, not normal diagnostic chatter.

## Proven static edges

- Mesh helper `0x224ba00` gets its staging arena through `0x21e3160` at
  `0x224ba2e`. That selector returns `0x72a1de0 + 0x7fd0 + 0x30 * graphics_slot`,
  where the slot is the integer global `0x72be278`.
- `0x2266fa0`, called at `0x224ba51`, performs bounded aligned allocation:
  capacity is arena offset 0, cursor offset 8, alignment mask offset 16.
  Successful allocation advances the cursor; insufficient space returns false.
  This mesh helper is one route into the mesh-update failure path; the observed
  native run did not record which individual allocation/check failed.
- After copying CPU data, that helper records `vkCmdCopyBuffer` at `0x224bae6`
  and `vkCmdPipelineBarrier` at `0x224bb5a`. Reusing staging bytes can therefore
  overwrite data still referenced by unsubmitted or incomplete commands.
- The ordinary graphics completion function `0x21eddf0` submits current-slot
  commands through `vkQueueSubmit` at `0x21ee398`, using the current slot's fence
  at `0x72aa2a0 + slot * 0x980 + 0x968`. Fence reset occurs through
  `0x21ee290 -> 0x225eab0 -> vkResetFences`.
- Its later rotation tail computes the next slot modulo two at
  `0x21edf7f..0x21edf94`. It waits on that next slot's fence at `0x21edfb3`
  through `0x225ea70 -> vkWaitForFences` (timeout retry, effectively unbounded).
- After that wait, `0x21ee05a -> 0x2268890` begins command recording using
  `vkBeginCommandBuffer` and clears wrapper bookkeeping. No command-pool reset
  is claimed by this observation.
- `0x21ee082` resets exactly the next slot's arena cursor at
  `0x72a1de0 + next_slot * 0x30 + 0x7fd8`.
- Before publishing the next slot at `0x21ee1dd`, the tail drains deferred
  resources. Proven callees include `0x2221050` (`vkDestroyBuffer`),
  `0x22210f0` (`vkDestroyImageView`), `0x2221190` (`vkDestroyImage`) and
  `0x2221230` (`vkFreeMemory`), plus two earlier wrapper-object lists.
- The native no-draw route `0x2025430` calls `0x21e78d0` and `0x2022810`;
  those do not execute this tail. `0x224eb00`, omitted on no-draw frames, only
  clears 16 bytes at receiver offset 8 and has no retirement calls.

## Smallest defensible next boundary

A viable graphics housekeeping route must finish pending copy commands, submit
necessary transfer work without swapchain dependencies, wait for completion of
resources selected for reuse, retire deferred resources, and only then restart
recording/reset arenas/publish the slot. Calling the existing completion
function wholesale also enters acquire/present handling. Jumping directly into
its rotation tail would bypass current submissions and depends on stack/register
state established earlier in that function.

The next bounded static task is to map the two command buffers used at
`0x21ee2e1..0x21ee398`: identify which receives dynamic-mesh copies, and whether
its submission can run independently of the acquired-image wait/signal
semaphores. Then identify an existing callable retirement wrapper, or establish
that an authored split is required. No safe new native probe is authorized by
this note. Preserved semaphore pairing and advancing UI/MD counters do not prove
graphics-resource lifetime correctness or stable server acceptance.
