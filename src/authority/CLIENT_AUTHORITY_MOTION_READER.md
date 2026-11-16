# Experimental client-authority motion reader

`lua/client_authority_motion_reader.lua` is a default-off, read-only local
building block for test client authority over saved registry index 1318 in
`cluster_115_sector001_macro`. It uses the existing saved-baseline bootstrap
and source motion sampler without a job receipt or any X4 write. The caller
must supply a still-valid explicit test grant and a context/checkpoint guard;
these callbacks assert the surrounding session context, they do not prove it.

The X4 session must own the only update hook and route matching descriptor
responses to `event()`, using `expected_request()`. The `stage_sample`
callback is provisional: the owner must keep its actor-free snapshot local and
must not publish it unless `event()` subsequently returns true. Grant loss,
context failure, overlapping/reentrant work, changed actor, sector or
correlation faults the reader. The first velocity is unknown; later velocity,
when available, is inferred from two positions per client game second. The
sample and its times are non-atomic and carry no common-frame assertion.

This module installs no hooks, socket, transport, scheduler or server writer.
It is not yet connected to an actual participant session and does not implement
client departure/handover. The user-approved policy is that another present
client takes over, or the server does when none remains; the mechanics and
correct transfer remain unimplemented. The accompanying tests use actual Lua
bootstrap and sampler state machines but simulated MD/FFI, not X4.
