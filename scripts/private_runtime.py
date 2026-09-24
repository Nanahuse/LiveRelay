from __future__ import annotations

import os
import sys
from pathlib import Path


_DLL_DIRECTORY_HANDLES: list[object] = []
_GST_PATH_MARKERS = ("gstreamer", "gst-plugin")


def workspace_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def configure_private_environment(root: Path | None = None) -> tuple[Path, Path]:
    if os.name != "nt":
        raise RuntimeError("Private GStreamer runtime isolation is currently supported on Windows only.")

    root = (root or workspace_root()).resolve()
    gst_root = root / "runtime" / "gstreamer"
    private_ndi_root = root / "runtime" / "ndi"
    installed_ndi_root = Path(os.environ.get("NDI_RUNTIME_DIR_V6", "")).resolve()
    installed_ndi_dll = installed_ndi_root / "Processing.NDI.Lib.x64.dll"
    private_ndi_dll = private_ndi_root / "Processing.NDI.Lib.x64.dll"
    if installed_ndi_dll.is_file():
        ndi_root = installed_ndi_root
    elif private_ndi_dll.is_file():
        ndi_root = private_ndi_root.resolve()
    else:
        ndi_root = installed_ndi_root
    gst_bin = gst_root / "bin"
    plugins = gst_root / "lib" / "gstreamer-1.0"
    scanner = gst_root / "libexec" / "gstreamer-1.0" / "gst-plugin-scanner.exe"
    typelibs = gst_root / "lib" / "girepository-1.0"
    if getattr(sys, "frozen", False):
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        cache_root = local_app_data / "LiveRelay" / "cache"
    else:
        cache_root = root / "cache"
    registry = cache_root / "gstreamer-registry.bin"

    required = (gst_bin, plugins, scanner, typelibs)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Private GStreamer Runtime is incomplete. Run uv run python scripts/prepare_gstreamer_runtime.py --full first.\n"
            + "\n".join(missing)
        )

    registry.parent.mkdir(parents=True, exist_ok=True)
    inherited_path = os.environ.get("PATH", "")
    clean_path = [
        entry for entry in inherited_path.split(os.pathsep)
        if entry and not any(marker in entry.casefold() for marker in _GST_PATH_MARKERS)
    ]
    private_dirs = [gst_bin, plugins]
    if ndi_root.is_dir():
        private_dirs.insert(1, ndi_root)
    os.environ["PATH"] = os.pathsep.join([*(str(path) for path in private_dirs), *clean_path])

    if hasattr(os, "add_dll_directory"):
        for path in private_dirs:
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(path)))

    os.environ["TWITCH_TO_NDI_PRIVATE_RUNTIME"] = "1"
    os.environ["TWITCH_TO_NDI_GSTREAMER_ROOT"] = str(gst_root)
    os.environ["TWITCH_TO_NDI_NDI_ROOT"] = str(ndi_root)
    os.environ["NDI_RUNTIME_DIR_V6"] = str(ndi_root)
    os.environ["NDILIB_REDIST_FOLDER"] = str(ndi_root)
    os.environ["GSTREAMER_1_0_ROOT_MSVC_X86_64"] = str(gst_root)
    os.environ["PYGI_DLL_DIRS"] = str(gst_bin)
    os.environ["GST_PLUGIN_PATH_1_0"] = str(plugins)
    os.environ["GST_PLUGIN_SYSTEM_PATH_1_0"] = ""
    os.environ["GST_PLUGIN_PATH"] = ""
    os.environ["GST_PLUGIN_SYSTEM_PATH"] = ""
    os.environ["GST_PLUGIN_SCANNER"] = str(scanner)
    os.environ["GST_REGISTRY"] = str(registry)
    os.environ["GI_TYPELIB_PATH"] = str(typelibs)

    if getattr(sys, "frozen", False):
        binding_site_packages = root / "gstreamer-python"
        if not (binding_site_packages / "gi" / "__init__.py").is_file():
            raise FileNotFoundError(f"Bundled PyGObject modules are missing: {binding_site_packages}")
        if str(binding_site_packages) not in sys.path:
            sys.path.insert(0, str(binding_site_packages))
    else:
        # Resolve the binding wheel only after the private DLL and typelib
        # paths are fixed. Keep its Python modules without inheriting its GStreamer tree.
        if "gstreamer_python" not in sys.modules:
            import gstreamer_python

        binding_paths = sys.modules["gstreamer_python"].environment["PYTHONPATH"].split(os.pathsep)
        for path in binding_paths:
            if path and path not in sys.path:
                sys.path.insert(0, path)

    return gst_root, ndi_root


def is_within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False
