from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from private_runtime import configure_private_environment, workspace_root


ELEMENTS = (
    "appsrc", "parsebin", "queue", "valve", "clocksync", "typefind",
    "tsdemux", "qtdemux", "h264parse", "aacparse", "d3d11h264dec",
    "d3d11download", "mfaacdec", "audioconvert", "audioresample",
    "ndisinkcombiner", "ndisink",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("elements", nargs="*", default=list(ELEMENTS))
    args = parser.parse_args()

    root = workspace_root()
    gst_root, _ndi_root = configure_private_environment(root)
    inspect = gst_root / "bin" / "gst-inspect-1.0.exe"
    failed = False
    for element in args.elements:
        result = subprocess.run(
            [str(inspect), element], env=os.environ.copy(), text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        plugin_name = next(
            (line.split("Name", 1)[1].strip() for line in result.stdout.splitlines()
             if line.startswith("  Name ")),
            "unknown",
        )
        filename = next(
            (line.split("Filename", 1)[1].strip() for line in result.stdout.splitlines()
             if line.startswith("  Filename ")),
            "unknown",
        )
        private = filename.casefold().startswith(str(gst_root).casefold())
        status = "OK" if result.returncode == 0 and private else "FAIL"
        print(f"{status}: element={element} plugin={plugin_name} file={filename}")
        if status != "OK":
            failed = True
            if result.returncode:
                print(result.stdout)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
