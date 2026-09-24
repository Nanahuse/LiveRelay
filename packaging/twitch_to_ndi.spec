# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata


ROOT = Path(SPECPATH).resolve().parent
GST_RUNTIME = ROOT / "runtime" / "gstreamer"
GI_SITE_PACKAGES = (
    Path(sys.prefix)
    / "Lib"
    / "site-packages"
    / "gstreamer_python"
    / "Lib"
    / "site-packages"
)

if not (GST_RUNTIME / "bin" / "gst-launch-1.0.exe").is_file():
    raise FileNotFoundError(
        f"Private GStreamer Runtime is missing: {GST_RUNTIME}. "
        "Run `uv run python scripts/prepare_gstreamer_runtime.py` first."
    )
if not (GI_SITE_PACKAGES / "gi" / "__init__.py").is_file():
    raise FileNotFoundError(f"gstreamer-python GI modules are missing: {GI_SITE_PACKAGES}")

streamlink_datas, streamlink_binaries, streamlink_hiddenimports = collect_all("streamlink")
streamlink_metadata = copy_metadata("streamlink", recursive=True)

a = Analysis(
    [str(ROOT / "scripts" / "run_private.py")],
    pathex=[str(ROOT / "scripts"), str(ROOT / "src")],
    binaries=streamlink_binaries,
    datas=[
        *streamlink_datas,
        *streamlink_metadata,
    ],
    hiddenimports=[
        *streamlink_hiddenimports,
        "gi",
        "gi.repository",
        "gi.repository.GLib",
        "gi.repository.Gst",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
a.datas += Tree(str(GST_RUNTIME), prefix="runtime/gstreamer")
a.datas += Tree(str(GI_SITE_PACKAGES), prefix="gstreamer-python")

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TwitchToNDI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory=".",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TwitchToNDI",
)
