"""Cross-build the Lua UDP module into a new, explicitly chosen directory.

This builds artifacts only; it does not install them or demonstrate execution
in X4 or on Windows. Use a disposable output directory outside game profiles.
An interrupted copy can leave a partial caller-owned output directory; remove
that directory before retrying only after verifying it belongs to this build.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zig", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path,
                        help="new, caller-owned output directory; must not exist")
    parser.add_argument("--platform", choices=("linux", "windows", "both"), default="both")
    args = parser.parse_args()
    if args.out.exists() or args.out.is_symlink():
        parser.error("output directory must not already exist")

    root = Path(__file__).resolve().parents[2]
    common = [str(args.zig.resolve()), "cc", "-O2", "-Wall", "-Wextra", "-Werror", "-shared",
              str(root / "src/native/net.c")]
    with tempfile.TemporaryDirectory(prefix="x4lan-build-") as scratch_name:
        scratch = Path(scratch_name)
        artifacts = []
        if args.platform in ("linux", "both"):
            target = scratch / "x4lan_net.so"
            subprocess.run(common + ["-target", "x86_64-linux-gnu.2.17", "-fPIC", "-ldl", "-o", str(target)], check=True)
            artifacts.append(target)
        if args.platform in ("windows", "both"):
            target = scratch / "x4lan_net_64.dll"
            subprocess.run(common + ["-target", "x86_64-windows-gnu", "-lws2_32", "-o", str(target)], check=True)
            artifacts.append(target)
        # Refuse replacement even if another process created the directory while compiling.
        # The caller must keep the parent and new directory exclusively owned.
        args.out.mkdir()
        for artifact in artifacts:
            with artifact.open("rb") as source, (args.out / artifact.name).open("xb") as destination:
                shutil.copyfileobj(source, destination)
    print("Built", args.platform, "module(s) in", args.out)


if __name__ == "__main__":
    main()
