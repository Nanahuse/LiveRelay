from __future__ import annotations

import importlib.metadata
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


PYTHON_LICENSES = {
    "attrs": "MIT",
    "certifi": "MPL-2.0",
    "cffi": "MIT-0",
    "charset-normalizer": "MIT",
    "h11": "MIT",
    "idna": "BSD-3-Clause",
    "isodate": "BSD-3-Clause",
    "lxml": "BSD-3-Clause (including separately documented bundled native components)",
    "outcome": "MIT OR Apache-2.0",
    "packaging": "Apache-2.0 OR BSD-2-Clause",
    "pycountry": "LGPL-2.1-only",
    "pycparser": "BSD-3-Clause",
    "pycryptodome": "BSD and Public Domain",
    "pysocks": "BSD",
    "requests": "Apache-2.0",
    "sniffio": "MIT OR Apache-2.0",
    "sortedcontainers": "Apache-2.0",
    "streamlink": "BSD-2-Clause",
    "trio": "MIT OR Apache-2.0",
    "trio-websocket": "MIT",
    "urllib3": "MIT",
    "websocket-client": "Apache-2.0",
    "wsproto": "MIT",
    "pygobject": "LGPL-2.1-or-later",
    "pycairo": "LGPL-2.1-only OR MPL-1.1",
}

PYTHON_URLS = {
    "attrs": "https://github.com/python-attrs/attrs",
    "certifi": "https://github.com/certifi/python-certifi",
    "cffi": "https://github.com/python-cffi/cffi",
    "charset-normalizer": "https://github.com/jawah/charset_normalizer",
    "h11": "https://github.com/python-hyper/h11",
    "idna": "https://github.com/kjd/idna",
    "isodate": "https://github.com/gweis/isodate",
    "lxml": "https://github.com/lxml/lxml",
    "outcome": "https://github.com/python-trio/outcome",
    "packaging": "https://github.com/pypa/packaging",
    "pycountry": "https://github.com/pycountry/pycountry",
    "pycparser": "https://github.com/eliben/pycparser",
    "pycryptodome": "https://github.com/Legrandin/pycryptodome",
    "pysocks": "https://github.com/Anorov/PySocks",
    "requests": "https://github.com/psf/requests",
    "sniffio": "https://github.com/python-trio/sniffio",
    "sortedcontainers": "https://github.com/grantjenks/python-sortedcontainers",
    "streamlink": "https://github.com/streamlink/streamlink",
    "trio": "https://github.com/python-trio/trio",
    "trio-websocket": "https://github.com/python-trio/trio-websocket",
    "urllib3": "https://github.com/urllib3/urllib3",
    "websocket-client": "https://github.com/websocket-client/websocket-client",
    "wsproto": "https://github.com/python-hyper/wsproto",
    "pygobject": "https://github.com/GNOME/pygobject",
    "pycairo": "https://github.com/pygobject/pycairo",
}

# Some native components omit their license files from the bundled Windows
# runtime. Fetch their exact upstream versioned files into dist at build time;
# SHA-256 pins prevent a moved tag or changed upstream file from silently
# changing the license text included in a release.
UPSTREAM_LICENSES = {
    "LGPL-2.0.txt": (
        "https://ftp.gnu.org/pub/gnu/Licenses/lgpl-2.0.txt",
        "cc535c21133c895b56b374c8a1dc1eb948d99003ed2b47372069456b62f42b24",
    ),
    "MPL-1.1.txt": (
        "https://raw.githubusercontent.com/pygobject/pycairo/v1.28.0/COPYING-MPL-1.1",
        "53692a2ed6c6a2c6ec9b32dd0b820dfae91e0a1fcdf625ca9ed0bdf8705fcc4f",
    ),
    "libffi-LICENSE.txt": (
        "https://raw.githubusercontent.com/libffi/libffi/v3.4.6/LICENSE",
        "67894089811f93fca47a76f85e017da6f8582d4ba0905963c6e0f1ad6df7a195",
    ),
    "ORC-COPYING.txt": (
        "https://raw.githubusercontent.com/GStreamer/orc/0.4.42/COPYING",
        "4f5dabb1b44bb6fc5cd53820b1f103147ad61b395a57903991325bd1b85d97bf",
    ),
    "PCRE2-LICENCE.txt": (
        "https://raw.githubusercontent.com/PCRE2Project/pcre2/pcre2-10.42/LICENCE",
        "87d884eceb7fc54611470ce9f74280d28612b0c877adfc767e9676892a638987",
    ),
    "zlib-LICENSE.txt": (
        "https://raw.githubusercontent.com/madler/zlib/v1.3.1/LICENSE",
        "845efc77857d485d91fb3e0b884aaa929368c717ae8186b66fe1ed2495753243",
    ),
}

NATIVE_COMPONENTS = [
    ("Python runtime", "3.14.6", "PSF-2.0", "https://www.python.org/", ["python314.dll"], "python"),
    ("OpenSSL", "3.5.7", "Apache-2.0", "https://github.com/openssl/openssl", ["libcrypto-3-x64.dll", "libssl-3-x64.dll"], "openssl"),
    ("libffi (Python runtime)", "3.4.6", "MIT", "https://github.com/libffi/libffi", ["libffi-8.dll"], "libffi"),
    ("zlib-ng (Python runtime)", "1.3.1.zlib-ng", "Zlib", "https://github.com/zlib-ng/zlib-ng", ["zlib1.dll"], "zlib"),
    ("Tcl/Tk", "8.6.14", "Tcl/Tk license", "https://www.tcl-lang.org/software/tcltk/", ["tcl86t.dll", "tk86t.dll"], "tcltk"),
    ("Microsoft Visual C++ Runtime", "14.44.35211.0", "Microsoft software license terms", "https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files", ["vcruntime140.dll", "vcruntime140_1.dll"], "msvc"),
]

GST_SOURCES = {
    "coreelements": "gstreamer",
    "app": "gst-plugins-base",
    "playback": "gst-plugins-base",
    "typefindfunctions": "gst-plugins-base",
    "mpegtsdemux": "gst-plugins-bad",
    "isomp4": "gst-plugins-good",
    "videoparsersbad": "gst-plugins-bad",
    "audioparsers": "gst-plugins-good",
    "d3d11": "gst-plugins-bad",
    "mediafoundation": "gst-plugins-bad",
    "audioconvert": "gst-plugins-base",
    "audioresample": "gst-plugins-base",
    "ndi": "gst-plugin-ndi",
}


def _source_url(name: str, version: str) -> str:
    if name == "gst-plugin-ndi":
        return "https://github.com/GStreamer/gst-plugins-rs/tree/gstreamer-1.28.6/net/ndi"
    return f"https://gstreamer.freedesktop.org/src/{name}/{name}-{version}.tar.xz"


def _copy_license_files(dist: importlib.metadata.Distribution, destination: Path) -> list[Path]:
    copied: list[Path] = []
    for item in dist.files or ():
        filename = Path(str(item)).name
        if not filename.casefold().startswith(("license", "copying", "notice")):
            continue
        source = Path(dist.locate_file(item))
        if source.is_file():
            target = destination / filename
            if target.exists() and target.read_bytes() != source.read_bytes():
                target = destination / f"{Path(str(item)).parent.name}-{filename}"
            shutil.copy2(source, target)
            copied.append(target)
    return copied


def _package_record(
    output_root: Path,
    dist: importlib.metadata.Distribution,
    *,
    name: str | None = None,
    license_name: str | None = None,
    url: str | None = None,
    fallback_names: tuple[str, ...] = (),
) -> tuple[str, str, str, list[str], str]:
    distribution_name = dist.metadata.get("Name", name or "unknown")
    canonical = distribution_name.casefold()
    version = dist.version
    license_name = license_name or PYTHON_LICENSES.get(canonical)
    if not license_name:
        raise RuntimeError(f"No reviewed license mapping for bundled Python package {distribution_name}")
    licenses_root = output_root / "licenses" / "python"
    destination = licenses_root / f"{distribution_name}-{version}"
    destination.mkdir(parents=True, exist_ok=True)
    copied = _copy_license_files(dist, destination)
    if canonical in {"pygobject", "pycairo"} and not copied:
        # These bindings are nested inside the gstreamer-python wheel and omit
        # license files. The installed pycountry runtime distribution carries
        # the complete LGPL-2.1 text needed by both bindings.
        lgpl_dist = importlib.metadata.distribution("pycountry")
        lgpl_file = next(
            (
                Path(lgpl_dist.locate_file(item))
                for item in lgpl_dist.files or ()
                if Path(str(item)).name.casefold().startswith(("license", "copying"))
                and Path(lgpl_dist.locate_file(item)).is_file()
            ),
            None,
        )
        if lgpl_file is not None:
            target = destination / "LGPL-2.1.txt"
            shutil.copy2(lgpl_file, target)
            copied.append(target)
    for filename in fallback_names:
        source = output_root / "licenses" / "runtime" / filename
        if source.is_file():
            target = destination / filename
            shutil.copy2(source, target)
            copied.append(target)
    if not copied:
        raise RuntimeError(f"No license text found for bundled Python package {distribution_name} {version}")
    source_url = url or PYTHON_URLS.get(canonical) or dist.metadata.get("Home-page")
    if not source_url:
        source_url = next(
            (value.split(", ", 1)[1] for key, value in dist.metadata.items() if key == "Project-URL" and value.startswith(("Source", "Repository"))),
            "",
        )
    if not source_url:
        raise RuntimeError(f"No source URL recorded for bundled Python package {distribution_name}")
    relative_files = [path.relative_to(output_root).as_posix() for path in copied]
    return distribution_name if name is None else name, version, license_name, relative_files, source_url


def _write_package_licenses(output_root: Path, package_names: set[str]) -> list[tuple[str, str, str, list[str], str]]:
    records = []
    for name in sorted(package_names, key=str.casefold):
        if name.casefold() == "gstreamer_python":
            continue
        try:
            dist = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            raise RuntimeError(f"Bundled Python distribution metadata is missing: {name}") from None
        if dist.metadata["Name"].casefold() in {"setuptools", "wheel", "pyinstaller"}:
            raise RuntimeError(f"Build-only distribution was collected into the runtime: {dist.metadata['Name']}")
        records.append(_package_record(output_root, dist))

    wheel_site = Path(sys.prefix) / "Lib" / "site-packages" / "gstreamer_python" / "Lib" / "site-packages"
    for name in ("PyGObject", "pycairo"):
        dist = next(iter(importlib.metadata.Distribution.discover(path=[str(wheel_site)], name=name)), None)
        if dist is None:
            raise RuntimeError(f"Bundled Python distribution metadata is missing: {name}")
        fallback = ("MPL-1.1.txt",) if name.casefold() == "pycairo" else ()
        records.append(_package_record(output_root, dist, fallback_names=fallback))

    gst_site = Path(sys.prefix) / "Lib" / "site-packages"
    gst_python_dist = next(iter(importlib.metadata.Distribution.discover(path=[str(gst_site)], name="gstreamer_python")), None)
    if gst_python_dist is None or not gst_python_dist.metadata.get("License"):
        raise RuntimeError("Bundled gstreamer-python wheel metadata or license expression is missing")
    # Its wheel metadata combines licenses for the shipped bindings and support
    # files; each underlying package is inventoried separately above.
    wheel_record = _package_record(
        output_root,
        gst_python_dist,
        name="gstreamer-python wheel",
        license_name=gst_python_dist.metadata["License"],
        url=f"https://pypi.org/project/gstreamer-python/{gst_python_dist.version}/",
        fallback_names=("LGPL-2.0.txt",),
    )
    wheel_license_files = list(wheel_record[3])
    for package in ("certifi", "pycountry", "idna", "attrs", "PyGObject", "pycairo"):
        component = next((record for record in records if record[0].casefold() == package.casefold()), None)
        if component:
            wheel_license_files.extend(component[3])
    records.append((*wheel_record[:3], list(dict.fromkeys(wheel_license_files)), wheel_record[4]))
    return records


def _pyz_packages(root: Path) -> set[str]:
    from PyInstaller.archive.readers import ZlibArchiveReader

    pyz = root / "build" / "LiveRelay" / "PYZ-00.pyz"
    archive = ZlibArchiveReader(str(pyz))
    roots = {
        name.split(".", 1)[0]
        for name in archive.toc
        if isinstance(name, str) and not name.startswith("__main__")
    }
    if "setuptools" in roots:
        raise RuntimeError("setuptools is build-only; ensure PyInstaller excludes it from the application archive")
    package_names = set()
    for module, distributions in importlib.metadata.packages_distributions().items():
        if module in roots:
            package_names.update(distributions or ())
    return {name for name in package_names if name.casefold() not in {"liverelay", "twitch-to-ndi"}}


def _private_gst_env(runtime: Path, root: Path) -> dict[str, str]:
    bin_dir = runtime / "bin"
    env = os.environ.copy()
    env.update(
        {
            "PATH": str(bin_dir) + os.pathsep + env.get("PATH", ""),
            "GST_PLUGIN_PATH_1_0": str(runtime / "lib" / "gstreamer-1.0"),
            "GST_PLUGIN_SYSTEM_PATH_1_0": "",
            "GST_PLUGIN_SCANNER": str(runtime / "libexec" / "gstreamer-1.0" / "gst-plugin-scanner.exe"),
            "GST_REGISTRY": str(root / "cache" / "license-gst-registry.bin"),
        }
    )
    return env


def _inspect_plugins(root: Path, output_root: Path) -> list[tuple[str, str, str, str, str]]:
    manifest = json.loads((root / "runtime-manifest.json").read_text(encoding="utf-8"))
    runtime = output_root / "runtime" / "gstreamer"
    inspect = runtime / "bin" / "gst-inspect-1.0.exe"
    if not inspect.is_file():
        raise RuntimeError(f"Bundled gst-inspect tool is missing: {inspect}")
    records = []
    env = _private_gst_env(runtime, root)
    for plugin in manifest["plugins"]:
        result = subprocess.run([str(inspect), plugin], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
        match = re.search(r"Plugin Details:\s*\n\s*Name\s+([^\n]+)\n\s*Description\s+([^\n]*)\n\s*Filename\s+([^\n]+)\n\s*Version\s+([^\n]+)\n\s*License\s+([^\n]+)", result.stdout)
        if not match:
            raise RuntimeError(f"Unable to parse gst-inspect metadata for plugin {plugin}")
        name, _description, filename, version, license_id = (part.strip() for part in match.groups())
        if re.search(r"\b(?:AGPL|GPL)(?:v?\d(?:\.\d)?)?(?:\+|-\w+)?\b", license_id, re.IGNORECASE):
            raise RuntimeError(f"Forbidden GPL-family GStreamer plugin detected: {plugin} ({license_id})")
        if name != plugin or not Path(filename).resolve().is_file() or not Path(filename).resolve().is_relative_to(runtime.resolve()):
            raise RuntimeError(f"Plugin {plugin} did not resolve to its bundled binary: {filename}")
        source = GST_SOURCES.get(plugin)
        if source is None:
            raise RuntimeError(f"No source-module mapping for GStreamer plugin {plugin}")
        license_name = "MPL-2.0" if plugin == "ndi" else "LGPL-2.1-or-later"
        if (plugin == "ndi" and not license_id.casefold().startswith("mpl")) or (plugin != "ndi" and "lgpl" not in license_id.casefold()):
            raise RuntimeError(f"Unexpected GStreamer plugin license: {plugin}: {license_id}")
        records.append((plugin, version, license_name, source, filename))
    return records


def _record_license_path(records: list[tuple[str, str, str, list[str], str]], package: str) -> str:
    record = next((item for item in records if item[0].casefold() == package.casefold()), None)
    if record is None or not record[3]:
        raise RuntimeError(f"No extracted license text available for {package}")
    return record[3][0]


def _copy_runtime_licenses(
    output_root: Path,
    package_records: list[tuple[str, str, str, list[str], str]],
) -> list[str]:
    python_root = Path(sys.base_prefix)
    destination = output_root / "licenses" / "runtime"
    destination.mkdir(parents=True, exist_ok=True)
    copies = [
        (python_root / "LICENSE.txt", destination / "Python-PSF-2.0.txt"),
        (python_root / "tcl" / "tk8.6" / "license.terms", destination / "Tcl-Tk-license.terms"),
    ]
    copies.extend(
        [
            (output_root / _record_license_path(package_records, "pycountry"), destination / "GStreamer-LGPL-2.1.txt"),
            (output_root / _record_license_path(package_records, "certifi"), destination / "GStreamer-NDI-MPL-2.0.txt"),
        ]
    )
    for source, target in copies:
        if not source.is_file():
            raise RuntimeError(f"License source for bundled native runtime is missing: {source}")
        shutil.copy2(source, target)
    bundled_names = {path.name.casefold() for path in output_root.rglob("*.dll")}
    required = {
        "python314.dll": "Python-PSF-2.0.txt",
        "tk86t.dll": "Tcl-Tk-license.terms",
        "tcl86t.dll": "Tcl-Tk-license.terms",
    }
    for filename, license_filename in required.items():
        if filename in bundled_names and not (destination / license_filename).is_file():
            raise RuntimeError(f"License text for bundled native component {filename} is missing")
    copied = [str(target.relative_to(output_root)).replace("\\", "/") for _, target in copies]
    copied.extend(
        f"licenses/runtime/{filename}"
        for filename in UPSTREAM_LICENSES
    )
    return copied


def _download_upstream_licenses(output_root: Path) -> None:
    destination = output_root / "licenses" / "runtime"
    destination.mkdir(parents=True, exist_ok=True)
    for filename, (url, expected_sha256) in UPSTREAM_LICENSES.items():
        request = urllib.request.Request(url, headers={"User-Agent": "LiveRelay license inventory"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                content = response.read()
        except OSError as error:
            raise RuntimeError(f"Unable to download upstream license {filename} from {url}: {error}") from error
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if actual_sha256 != expected_sha256:
            raise RuntimeError(
                f"Upstream license checksum changed for {filename}: expected {expected_sha256}, got {actual_sha256}"
            )
        (destination / filename).write_bytes(content)


def generate(root: Path, output_root: Path) -> None:
    _download_upstream_licenses(output_root)
    package_records = _write_package_licenses(output_root, _pyz_packages(root))
    gst_records = _inspect_plugins(root, output_root)
    runtime_license_files = _copy_runtime_licenses(output_root, package_records)

    lines = [
        "LiveRelay Third-Party Notices",
        "==============================",
        "",
        "LiveRelay application code is licensed under MIT; see LICENSE.",
        "This inventory covers components included in this onedir distribution.",
        "Bundled third-party components retain their respective licenses.",
        "",
        "Python runtime dependencies",
        "----------------------------",
    ]
    for name, version, license_name, license_files, url in sorted(package_records, key=lambda record: record[0].casefold()):
        lines.extend([f"- {name} {version} — {license_name}", f"  Source: {url}"])
        lines.extend(f"  License text: {item}" for item in license_files)
    lines.extend(["", "GStreamer plugins (queried using the bundled gst-inspect-1.0)", "-------------------------------------------------------------"])
    gst_version = json.loads((root / "runtime-manifest.json").read_text(encoding="utf-8"))["gstreamer_version"]
    for plugin, version, license_name, source, filename in gst_records:
        lines.extend(
            [
                f"- {plugin} plugin {version} — {license_name}; source module {source}",
                f"  Source: {_source_url(source, gst_version)}",
                f"  Binary: {Path(filename).resolve().relative_to((output_root / 'runtime' / 'gstreamer').resolve()).as_posix()}",
            ]
        )
    lines.extend(["", "GStreamer runtime libraries", "----------------------------"])
    gstreamer_bin = output_root / "runtime" / "gstreamer" / "bin"
    gst_native = {
        "ffi-7.dll": ("libffi", "3.2.9999.5", "MIT", "https://gitlab.freedesktop.org/gstreamer/meson-ports/libffi", "libffi-LICENSE.txt"),
        "gio-2.0-0.dll": ("GLib", "2.82.4", "LGPL-2.1-or-later", "https://gitlab.gnome.org/GNOME/glib", ""),
        "girepository-1.0-1.dll": ("GLib", "2.82.4", "LGPL-2.1-or-later", "https://gitlab.gnome.org/GNOME/glib", ""),
        "glib-2.0-0.dll": ("GLib", "2.82.4", "LGPL-2.1-or-later", "https://gitlab.gnome.org/GNOME/glib", ""),
        "gmodule-2.0-0.dll": ("GLib", "2.82.4", "LGPL-2.1-or-later", "https://gitlab.gnome.org/GNOME/glib", ""),
        "gobject-2.0-0.dll": ("GLib", "2.82.4", "LGPL-2.1-or-later", "https://gitlab.gnome.org/GNOME/glib", ""),
        "intl-8.dll": ("proxy-libintl", "0.5", "LGPL-2.1-or-later", "https://github.com/frida/proxy-libintl", ""),
        "orc-0.4-0.dll": ("ORC", "0.4.42", "BSD-2-Clause AND BSD-3-Clause", "https://github.com/GStreamer/orc/tree/orc-0.4.42", "ORC-COPYING.txt"),
        "pcre2-8-0.dll": ("PCRE2", "10.42", "BSD-3-Clause", "https://github.com/PCRE2Project/pcre2", "PCRE2-LICENCE.txt"),
        "z-1.dll": ("zlib", "1.3.1", "Zlib", "https://zlib.net/", "zlib-LICENSE.txt"),
    }
    for filename in sorted(gstreamer_bin.glob("*.dll")):
        if filename.name in gst_native:
            name, version, license_name, url, license_file = gst_native[filename.name]
            lines.append(f"- {filename.name} — {name} {version}, {license_name}; {url}")
            if license_file:
                lines.append(f"  License text: licenses/runtime/{license_file}")
        else:
            lines.append(f"- {filename.name} — GStreamer {gst_version}, LGPL-2.1-or-later; https://gstreamer.freedesktop.org/src/")
    lines.extend(
        [
            "  GStreamer LGPL text: licenses/runtime/GStreamer-LGPL-2.1.txt",
            "  NDI plugin MPL text: licenses/runtime/GStreamer-NDI-MPL-2.0.txt",
            "  Separate DLLs are replaceable; no GStreamer libraries are statically linked.",
        ]
    )
    lines.extend(["", "Native runtime libraries", "-------------------------"])
    dll_names = {path.name.casefold() for path in output_root.rglob("*.dll")}
    for name, version, license_name, url, files, license_key in NATIVE_COMPONENTS:
        present = [filename for filename in files if filename.casefold() in dll_names]
        if present:
            lines.extend([f"- {name} {version} — {license_name}", f"  Source/terms: {url}", f"  Files: {', '.join(present)}"])
            if license_key == "python":
                lines.append("  License text: licenses/runtime/Python-PSF-2.0.txt")
            elif license_key == "openssl":
                lines.append(f"  License text: {_record_license_path(package_records, 'requests')}")
            elif license_key == "libffi":
                lines.append("  License text: licenses/runtime/libffi-LICENSE.txt")
            elif license_key == "zlib":
                lines.append("  License text: licenses/runtime/zlib-LICENSE.txt")
            elif license_key == "tcltk":
                lines.append("  License text: licenses/runtime/Tcl-Tk-license.terms")
    if "vcruntime140.dll" in dll_names:
        lines.extend(["", "Microsoft Visual C++ runtime redistribution is subject to the linked Microsoft software license terms."])
    lines.extend(["", "Runtime license texts", "---------------------"])
    lines.extend(f"- {item}" for item in runtime_license_files)
    lines.extend(
        [
            "",
            "NDI attribution",
            "----------------",
            "NDI® is a registered trademark of Vizrt NDI AB. NDI Runtime is not included; LiveRelay uses the installed runtime selected by NDI_RUNTIME_DIR_V6. See https://ndi.video/ and the NDI SDK/runtime terms.",
            "",
            "LGPL replacement information",
            "----------------------------",
            "The GStreamer LGPL libraries and plugins are separate replaceable DLL files under runtime/gstreamer. A recipient can replace these DLLs with compatible modified builds; corresponding source modules are linked above. No GStreamer libraries are statically linked.",
            "",
        ]
    )
    notice_path = output_root / "THIRD_PARTY_NOTICES.txt"
    notice_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    shutil.copy2(root / "LICENSE", output_root / "LICENSE")
    print(f"Generated third-party inventory: {notice_path}")
    print(f"Inventoried {len(package_records)} Python runtime distributions and {len(gst_records)} GStreamer plugins.")


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[1]
    generate(project_root, project_root / "dist" / "LiveRelay")
