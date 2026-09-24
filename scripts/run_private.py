from __future__ import annotations

import ctypes
import argparse
import os
import sys
from pathlib import Path

from private_runtime import configure_private_environment, is_within, workspace_root


REQUIRED_ELEMENTS = (
    "appsrc", "parsebin", "queue", "valve", "clocksync", "typefind",
    "tsdemux", "qtdemux", "h264parse", "aacparse", "d3d11h264dec",
    "d3d11download", "mfaacdec", "audioconvert", "audioresample",
    "ndisinkcombiner", "ndisink",
)


def loaded_module_path(name: str) -> Path | None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_module = kernel32.GetModuleHandleW
    get_module.argtypes = [ctypes.c_wchar_p]
    get_module.restype = ctypes.c_void_p
    handle = get_module(name)
    if not handle:
        return None
    get_path = kernel32.GetModuleFileNameW
    get_path.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32]
    get_path.restype = ctypes.c_uint32
    buffer = ctypes.create_unicode_buffer(32768)
    length = get_path(handle, buffer, len(buffer))
    return Path(buffer.value) if length else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check-only", action="store_true",
        help="Verify isolated GStreamer and NDI runtime loading without opening the UI.",
    )
    args = parser.parse_args()

    root = workspace_root()
    sys.path.insert(0, str(root / "src"))
    gst_root, ndi_root = configure_private_environment(root)

    from twitch_to_ndi.main import load_gst

    Gst, _GLib = load_gst()
    Gst.init(None)
    print(f"Private GStreamer: {Gst.version_string()}")
    print(f"Private plugin path: {os.environ['GST_PLUGIN_PATH_1_0']}")
    print(f"Private scanner: {os.environ['GST_PLUGIN_SCANNER']}")
    print(f"Private registry: {os.environ['GST_REGISTRY']}")
    print(f"System plugin path: {os.environ['GST_PLUGIN_SYSTEM_PATH_1_0']!r}")

    core_path = loaded_module_path("gstreamer-1.0-0.dll")
    if core_path is None or not is_within(core_path, gst_root):
        raise RuntimeError(f"GStreamer core did not load from the private runtime: {core_path}")
    print(f"Loaded GStreamer core: {core_path}")

    missing: list[str] = []
    registry = Gst.Registry.get()
    for element in REQUIRED_ELEMENTS:
        factory = Gst.ElementFactory.find(element)
        if factory is None:
            missing.append(element)
            continue
        plugin_name = factory.get_plugin_name()
        plugin = registry.find_plugin(plugin_name)
        filename = Path(plugin.get_filename()) if plugin else Path()
        if not is_within(filename, gst_root / "lib" / "gstreamer-1.0"):
            raise RuntimeError(f"Element {element} resolved outside Private Runtime: {filename}")
        print(f"Element {element}: {plugin_name} ({filename.name})")

    if missing:
        raise RuntimeError("Required Private Runtime elements are missing: " + ", ".join(missing))

    ndi_library = ndi_root / "Processing.NDI.Lib.x64.dll"
    if not ndi_library.is_file():
        raise RuntimeError(
            "NDI Runtime was not found in NDI_RUNTIME_DIR_V6 or runtime/ndi."
        )
    ctypes.WinDLL(str(ndi_library))
    ndi_path = loaded_module_path(ndi_library.name)
    if ndi_path is None or not is_within(ndi_path, ndi_root):
        raise RuntimeError(f"NDI Runtime did not load from the selected environment directory: {ndi_path}")
    print(f"Loaded NDI Runtime: {ndi_path}")

    if args.check_only:
        print("Private GStreamer and environment NDI Runtime checks passed.")
        return 0

    from twitch_to_ndi.ui import main as ui_main

    ui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
