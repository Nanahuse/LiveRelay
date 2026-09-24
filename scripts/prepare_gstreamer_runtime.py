from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import subprocess
from pathlib import Path

from private_runtime import is_within, workspace_root


def _read_c_string(data: bytes, offset: int) -> str:
    end = data.find(b"\0", offset)
    if end < 0:
        raise ValueError("unterminated PE import name")
    return data[offset:end].decode("ascii", errors="strict")


def pe_imports(path: Path) -> set[str]:
    data = path.read_bytes()
    if data[:2] != b"MZ":
        raise ValueError(f"Not a PE image: {path}")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_offset:pe_offset + 4] != b"PE\0\0":
        raise ValueError(f"Invalid PE signature: {path}")

    file_header = pe_offset + 4
    section_count = struct.unpack_from("<H", data, file_header + 2)[0]
    optional_size = struct.unpack_from("<H", data, file_header + 16)[0]
    optional = file_header + 20
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic == 0x20B:
        directories = optional + 112
        image_base = struct.unpack_from("<Q", data, optional + 24)[0]
    elif magic == 0x10B:
        directories = optional + 96
        image_base = struct.unpack_from("<I", data, optional + 28)[0]
    else:
        raise ValueError(f"Unsupported PE optional header {magic:#x}: {path}")

    sections_offset = optional + optional_size
    sections: list[tuple[int, int, int, int]] = []
    for index in range(section_count):
        offset = sections_offset + index * 40
        virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from("<IIII", data, offset + 8)
        sections.append((virtual_address, virtual_size, raw_pointer, raw_size))

    def rva_to_offset(rva: int) -> int:
        for virtual_address, virtual_size, raw_pointer, raw_size in sections:
            span = max(virtual_size, raw_size)
            if virtual_address <= rva < virtual_address + span:
                offset = raw_pointer + (rva - virtual_address)
                if offset >= len(data):
                    break
                return offset
        if rva < len(data):
            return rva
        raise ValueError(f"RVA {rva:#x} is outside PE sections: {path}")

    def read_names(directory_index: int, delay: bool = False) -> set[str]:
        directory = directories + directory_index * 8
        rva, size = struct.unpack_from("<II", data, directory)
        if not rva or not size:
            return set()
        result: set[str] = set()
        offset = rva_to_offset(rva)
        stride = 32 if delay else 20
        max_entries = min(size // stride + 1, 1_000_000)
        for index in range(max_entries):
            entry = offset + index * stride
            if entry + stride > len(data):
                break
            if delay:
                attributes, name_value = struct.unpack_from("<II", data, entry)
                if attributes & 1:
                    name_rva = name_value
                else:
                    name_rva = name_value - image_base
            else:
                descriptor = struct.unpack_from("<IIIII", data, entry)
                if not any(descriptor):
                    break
                name_rva = descriptor[3]
            if not name_rva:
                continue
            result.add(_read_c_string(data, rva_to_offset(name_rva)))
        return result

    return read_names(1) | read_names(13, delay=True)


def windows_system_dlls() -> set[str]:
    system32 = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32"
    try:
        return {entry.name.casefold() for entry in system32.iterdir() if entry.is_file()}
    except OSError:
        return set()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a GStreamer Full or allowlisted Private Runtime.")
    parser.add_argument("--full", action="store_true", help="Copy the complete official runtime baseline.")
    args = parser.parse_args()

    root = workspace_root()
    manifest = json.loads((root / "runtime-manifest.json").read_text(encoding="utf-8"))
    source = (root / manifest["source_directory"]).resolve()
    target = (root / "runtime" / "gstreamer").resolve()
    if not source.is_dir() or not is_within(source, root / "runtime-source"):
        raise FileNotFoundError(f"Official GStreamer Full Runtime source is missing: {source}")
    if not is_within(target, root / "runtime"):
        raise RuntimeError(f"Refusing to write outside runtime/: {target}")

    inspect_source = source / "bin" / "gst-inspect-1.0.exe"
    if not inspect_source.is_file():
        raise FileNotFoundError(f"Full Runtime gst-inspect is missing: {inspect_source}")
    version_result = subprocess.run(
        [str(inspect_source), "--version"],
        env={
            **os.environ,
            "PATH": str(source / "bin") + os.pathsep + os.environ.get("PATH", ""),
            "GST_PLUGIN_PATH_1_0": str(source / "lib" / "gstreamer-1.0"),
            "GST_PLUGIN_SYSTEM_PATH_1_0": "",
            "GST_PLUGIN_SCANNER": str(source / "libexec" / "gstreamer-1.0" / "gst-plugin-scanner.exe"),
            "GST_REGISTRY": str(root / "cache" / "full-version-check.bin"),
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    if manifest["gstreamer_version"] not in version_result.stdout:
        raise RuntimeError(
            f"Runtime version mismatch: expected {manifest['gstreamer_version']}, got {version_result.stdout.strip()}"
        )

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    if args.full:
        def ignore_uninstaller(directory: str, names: list[str]) -> set[str]:
            return {name for name in names if name.casefold() in {"unins000.exe", "unins000.dat"}}

        shutil.copytree(source, target, dirs_exist_ok=True, ignore=ignore_uninstaller)
        print(f"Copied official GStreamer {manifest['gstreamer_version']} Full Runtime to {target}")
        print("The source remained unchanged; uninstaller files were omitted.")
        return 0

    source_plugins = source / "lib" / "gstreamer-1.0"
    target_plugins = target / "lib" / "gstreamer-1.0"
    target_bin = target / "bin"
    target_typelibs = target / "lib" / "girepository-1.0"
    target_scanner = target / "libexec" / "gstreamer-1.0"
    for directory in (target_plugins, target_bin, target_typelibs, target_scanner):
        directory.mkdir(parents=True, exist_ok=True)

    plugin_paths: list[Path] = []
    for plugin in manifest["plugins"]:
        filename = source_plugins / f"gst{plugin}.dll"
        if not filename.is_file():
            raise FileNotFoundError(f"Manifest plugin {plugin!r} is missing: {filename}")
        destination = target_plugins / filename.name
        shutil.copy2(filename, destination)
        plugin_paths.append(destination)

    tool_paths: list[Path] = []
    for tool in manifest["tools"]:
        source_tool = source / "bin" / tool
        if not source_tool.is_file():
            raise FileNotFoundError(f"Manifest tool is missing: {source_tool}")
        destination = target_bin / tool
        shutil.copy2(source_tool, destination)
        tool_paths.append(destination)

    scanner = source / "libexec" / "gstreamer-1.0" / "gst-plugin-scanner.exe"
    if not scanner.is_file():
        raise FileNotFoundError(f"Plugin scanner is missing: {scanner}")
    shutil.copy2(scanner, target_scanner / scanner.name)
    tool_paths.append(target_scanner / scanner.name)

    for typelib in manifest["typelibs"]:
        source_typelib = source / "lib" / "girepository-1.0" / typelib
        if not source_typelib.is_file():
            raise FileNotFoundError(f"Manifest typelib is missing: {source_typelib}")
        shutil.copy2(source_typelib, target_typelibs / typelib)

    for item in manifest.get("runtime_files", []):
        relative_source = Path(item["source"])
        relative_destination = Path(item.get("destination", item["source"]))
        source_file = source / relative_source
        if not source_file.is_file():
            raise FileNotFoundError(f"Manifest runtime file is missing: {source_file}")
        destination = target / relative_destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination)

    dependency_roots = (
        source / "bin",
        source / "lib" / "gstreamer-1.0",
        source / "libexec" / "gstreamer-1.0",
    )
    dll_index: dict[str, Path] = {}
    for directory in dependency_roots:
        for candidate in directory.rglob("*.dll"):
            dll_index.setdefault(candidate.name.casefold(), candidate)
    os_dlls = windows_system_dlls()
    manifest_external = {name.casefold() for name in manifest.get("allowed_external_dlls", [])}
    pending = list(plugin_paths) + tool_paths
    inspected: set[Path] = set()
    copied_dependencies: set[str] = set()
    unresolved: set[str] = set()
    while pending:
        binary = pending.pop()
        resolved_binary = binary.resolve()
        if resolved_binary in inspected:
            continue
        inspected.add(resolved_binary)
        for imported in pe_imports(binary):
            key = imported.casefold()
            if key in os_dlls or key.startswith(("api-ms-win-", "ext-ms-win-")):
                continue
            dependency = dll_index.get(key)
            if dependency is None:
                if key not in manifest_external:
                    unresolved.add(imported)
                continue
            destination = target_bin / dependency.name
            if not destination.exists():
                shutil.copy2(dependency, destination)
                copied_dependencies.add(dependency.name)
                pending.append(destination)

    if unresolved:
        raise RuntimeError(
            "Unresolved non-Windows DLL imports. Add an explicitly licensed dependency to runtime-manifest.json "
            "or provide it in the official Full Runtime source: " + ", ".join(sorted(unresolved))
        )

    print(f"Created allowlisted Private Runtime: {target}")
    print(f"Plugins: {len(plugin_paths)}; tools/scanner: {len(tool_paths)}")
    print(f"Typelibs: {len(manifest['typelibs'])}; transitive DLLs: {len(copied_dependencies)}")
    if manifest_external:
        print("External DLLs deliberately not bundled: " + ", ".join(sorted(manifest_external)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
