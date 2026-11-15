# Two simultaneous X4 instances and saved fixture references

`tools/dev/authority_two_x4_identity_live.py` extends the disposable two-X4
checkpoint supervisor. The server's isolated X4 process creates and names two
fixture ships and waits for their properties before enrolling its control
bridge. The coordinator pauses and saves that X4 world. It then offers the
checkpoint over local TCP to a separate isolated client profile. The second X4
loads the offered slot and queries the two MD-held references from the save;
it checks the distinct fixture names and expected macro before producing its
pause observation. The supervisor checks that both owned X4 processes remain
alive through that observation. It does not admit the client to the session.

The fixture MD and Lua files are read-only inside the client sandbox. The
server and client logs are checked for ordered, distinct, operational fixture
objects with matching expected names and macros. Runtime IDs are reported only
for comparison and are not treated as durable identity. This bounded test does
not establish global uniqueness or synchronization of arbitrary new and
existing ships, destruction, full world state, Windows, Internet, or gameplay.
The fixture properties strengthen the observation that the loaded world
contains the saved references; they do not independently prove the exact bytes
read by X4.

With the pinned local X4 installation, running Steam, Bubblewrap and a
separately provisioned virtual display and Xauthority:

```sh
python tools/dev/authority_two_x4_identity_live.py --game /path/to/X4 \
  --out .local/two-x4-identity-experiment --display :2 --timeout 600
```

The output must be a fresh private path under `.local`. The underlying
supervisor owns and cleans up only its launched processes and test lock.
Importing this script starts no game. The focused Python tests check fixture
hook placement, receipt validation, and wrapper operation with doubles; they
do not launch X4.

On 2026-11-15, one isolated Linux/Linux run completed the sequence: both
fixture references resolved on the client to distinct operational ships with
the expected names and macro, before its paused-player receipt. Both local
runtime IDs differed from the corresponding server IDs. The client process
was observed holding a descriptor for the staged save, but that observation
does not establish a complete read or exact world identity. The client was not
admitted, no gameplay was performed, and both owned process groups were cleaned
up. The broader limitations above still apply.
