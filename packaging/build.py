from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PyInstaller.__main__ import run


ROOT = Path(__file__).resolve().parents[1]
GST_RUNTIME = ROOT / "runtime" / "gstreamer"
GI_SITE_PACKAGES = (
    Path(sys.prefix)
    / "Lib"
    / "site-packages"
    / "gstreamer_python"
    / "Lib"
    / "site-packages"
)


def main() -> None:
    if sys.platform != "win32":
        raise RuntimeError("The LiveRelay onedir bundle must be built on Windows.")
    if not (GST_RUNTIME / "bin" / "gst-launch-1.0.exe").is_file():
        raise FileNotFoundError(
            f"Private GStreamer Runtime is missing: {GST_RUNTIME}. "
            "Run `uv run python scripts/prepare_gstreamer_runtime.py` first."
        )
    if not (GI_SITE_PACKAGES / "gi" / "__init__.py").is_file():
        raise FileNotFoundError(f"gstreamer-python GI modules are missing: {GI_SITE_PACKAGES}")

    run(
        [
            "--clean",
            "--noconfirm",
            "--onedir",
            "--windowed",
            "--contents-directory",
            ".",
            "--name",
            "LiveRelay",
            "--paths",
            str(ROOT / "src"),
            "--paths",
            str(ROOT / "scripts"),
            "--collect-all",
            "streamlink",
            "--copy-metadata",
            "streamlink",
            "--add-data",
            f"{GI_SITE_PACKAGES};gstreamer-python",
            str(ROOT / "scripts" / "run_private.py"),
        ]
    )

    # Keep the complete GStreamer tree as data in its intended subdirectory.
    # PyInstaller otherwise reclassifies DLL data as binaries and flattens it
    # into the executable directory, ahead of the private DLL search path.
    output_root = ROOT / "dist" / "LiveRelay"
    shutil.copytree(GST_RUNTIME, output_root / "runtime" / "gstreamer", dirs_exist_ok=True)
    for source in (GST_RUNTIME / "bin").glob("*.dll"):
        (output_root / source.name).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
