from __future__ import annotations

import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
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
    "setuptools": "MIT",
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
    "pyinstaller": "GPL-2.0-or-later with PyInstaller exception",
    "pyinstaller-hooks-contrib": "Apache-2.0",
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
    "setuptools": "https://github.com/pypa/setuptools",
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
    "pyinstaller": "https://github.com/pyinstaller/pyinstaller",
    "pyinstaller-hooks-contrib": "https://github.com/pyinstaller/pyinstaller-hooks-contrib",
}

LICENSE_FALLBACKS = {
    "pygobject": ["LGPL-2.1.txt"],
    "pycairo": ["LGPL-2.1.txt", "MPL-1.1.txt"],
}

NATIVE_COMPONENTS = [
    ("Python runtime", "3.14.6", "PSF-2.0", "https://www.python.org/", ["python314.dll"], "python"),
    ("OpenSSL", "3.5.7", "Apache-2.0", "https://github.com/openssl/openssl", ["libcrypto-3-x64.dll", "libssl-3-x64.dll"], "openssl"),
    ("libffi (Python runtime)", "3.4.6", "MIT", "https://github.com/libffi/libffi", ["libffi-8.dll"], "libffi"),
    ("zlib-ng (Python runtime)", "1.3.1.zlib-ng", "Zlib", "https://github.com/zlib-ng/zlib-ng", ["zlib1.dll"], "zlib"),
    ("Tcl/Tk", "8.6.14", "Tcl/Tk license", "https://www.tcl-lang.org/software/tcltk/", ["tcl86t.dll", "tk86t.dll"], "tcltk"),
    ("Microsoft Visual C++ Runtime", "14.44.35211.0", "Microsoft software license terms", "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist", ["vcruntime140.dll", "vcruntime140_1.dll"], "msvc"),
    ("GStreamer", "1.28.6", "LGPL-2.1-or-later", "https://gstreamer.freedesktop.org/src/", [], "gstreamer"),
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


def _write_package_licenses(root: Path, package_names: set[str]) -> list[tuple[str, str, str, list[str], str]]:
    records: list[tuple[str, str, str, list[str], str]] = []
    licenses_root = root / "licenses" / "python"
    if licenses_root.exists():
        shutil.rmtree(licenses_root)
    licenses_root.mkdir(parents=True, exist_ok=True)
    for name in sorted(package_names, key=str.casefold):
        try:
            if name.casefold() == "gstreamer_python":
                continue
            dist = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            raise RuntimeError(f"Bundled Python distribution metadata is missing: {name}") from None
        canonical = dist.metadata["Name"].casefold()
        license_name = PYTHON_LICENSES.get(canonical)
        if not license_name:
            raise RuntimeError(f"No reviewed license mapping for bundled Python package {dist.metadata['Name']}")
        destination = licenses_root / f"{dist.metadata['Name']}-{dist.version}"
        destination.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        for item in dist.files or ():
            leaf = Path(str(item)).name.casefold()
            if not (leaf.startswith(("license", "copying", "notice"))):
                continue
            source = Path(dist.locate_file(item))
            if source.is_file():
                target = destination / Path(str(item)).name
                shutil.copy2(source, target)
                copied.append(str(target.relative_to(root)).replace("\\", "/"))
        for fallback in LICENSE_FALLBACKS.get(canonical, []):
            source = root / "licenses" / "common" / fallback
            if source.is_file():
                target = destination / fallback
                shutil.copy2(source, target)
                copied.append(str(target.relative_to(root)).replace("\\", "/"))
        if not copied:
            raise RuntimeError(f"No license text found for bundled Python package {dist.metadata['Name']} {dist.version}")
        url = PYTHON_URLS.get(canonical) or dist.metadata.get("Home-page")
        if not url:
            url = next((v.split(", ", 1)[1] for k, v in dist.metadata.items() if k == "Project-URL" and v.startswith(("Source", "Repository"))), "")
        if not url:
            raise RuntimeError(f"No source URL recorded for bundled Python package {dist.metadata['Name']}")
        records.append((dist.metadata["Name"], dist.version, license_name, copied, url))

    # setuptools embeds these distributions inside its own namespace. Keep each
    # package's own version, source link, license expression, and text visible.
    from PyInstaller.archive.readers import ZlibArchiveReader

    archive = ZlibArchiveReader(str(root / "build" / "LiveRelay" / "PYZ-00.pyz"))
    vendor_roots = {str(name).split(".")[2] for name in archive.toc if str(name).startswith("setuptools._vendor.")}
    vendor_info = {
        "backports": [("backports.tarfile", "MIT", "https://github.com/aresch/backports.tarfile")],
        "jaraco": [
            ("jaraco.context", "MIT", "https://github.com/jaraco/jaraco.context"),
            ("jaraco.functools", "MIT", "https://github.com/jaraco/jaraco.functools"),
            ("jaraco.text", "MIT", "https://github.com/jaraco/jaraco.text"),
        ],
        "more_itertools": [("more-itertools", "MIT", "https://github.com/more-itertools/more-itertools")],
        "packaging": [("packaging", "Apache-2.0 OR BSD-2-Clause", "https://github.com/pypa/packaging")],
        "tomli": [("tomli", "MIT", "https://github.com/hukkin/tomli")],
        "wheel": [("wheel", "MIT", "https://github.com/pypa/wheel")],
    }
    vendor_site = Path(sys.prefix) / "Lib" / "site-packages" / "setuptools" / "_vendor"
    for module, distributions in vendor_info.items():
        if module not in vendor_roots:
            continue
        for distribution_name, license_name, url in distributions:
            dist = next(iter(importlib.metadata.Distribution.discover(path=[str(vendor_site)], name=distribution_name)), None)
            if dist is None:
                raise RuntimeError(f"Vendored setuptools distribution metadata is missing: {distribution_name}")
            destination = licenses_root / f"{dist.metadata['Name']}-{dist.version}"
            destination.mkdir(parents=True, exist_ok=True)
            copied = []
            for item in dist.files or ():
                if Path(str(item)).name.casefold().startswith(("license", "copying", "notice")):
                    source = Path(dist.locate_file(item))
                    if source.is_file():
                        target = destination / Path(str(item)).name
                        shutil.copy2(source, target)
                        copied.append(str(target.relative_to(root)).replace("\\", "/"))
            if not copied:
                raise RuntimeError(f"No license text found for vendored package {dist.metadata['Name']} {dist.version}")
            records.append((dist.metadata["Name"], dist.version, license_name, copied, url))

    # This wheel carries two additional Python distributions in its data tree;
    # they are shipped beside, rather than inside, the main environment.
    wheel_site = Path(sys.prefix) / "Lib" / "site-packages" / "gstreamer_python" / "Lib" / "site-packages"
    for name in ("PyGObject", "pycairo"):
        dist = next(iter(importlib.metadata.Distribution.discover(path=[str(wheel_site)], name=name)), None)
        if dist is None:
            raise RuntimeError(f"Bundled Python distribution metadata is missing: {name}")
        canonical = dist.metadata["Name"].casefold()
        destination = licenses_root / f"{dist.metadata['Name']}-{dist.version}"
        destination.mkdir(parents=True, exist_ok=True)
        copied = []
        for item in dist.files or ():
            if Path(str(item)).name.casefold().startswith(("license", "copying", "notice")):
                source = Path(dist.locate_file(item))
                if source.is_file():
                    target = destination / Path(str(item)).name
                    shutil.copy2(source, target)
                    copied.append(str(target.relative_to(root)).replace("\\", "/"))
        for fallback in LICENSE_FALLBACKS.get(canonical, []):
            source = root / "licenses" / "common" / fallback
            if source.is_file():
                target = destination / fallback
                shutil.copy2(source, target)
                copied.append(str(target.relative_to(root)).replace("\\", "/"))
        if not copied:
            raise RuntimeError(f"No license text found for bundled Python package {dist.metadata['Name']} {dist.version}")
        license_name = PYTHON_LICENSES[canonical]
        records.append((dist.metadata["Name"], dist.version, license_name, copied, PYTHON_URLS[canonical]))
    gst_python_dist = next(
        iter(importlib.metadata.Distribution.discover(path=[str(Path(sys.prefix) / "Lib" / "site-packages")], name="gstreamer_python")),
        None,
    )
    if gst_python_dist is None:
        raise RuntimeError("Bundled gstreamer-python wheel metadata is missing")
    if not gst_python_dist.metadata.get("License"):
        raise RuntimeError("gstreamer-python wheel license expression is missing")
    composite_files = [
        "licenses/common/MPL-1.1.txt",
        "licenses/common/LGPL-2.1.txt",
        "licenses/common/BSD-3-Clause.txt",
        "licenses/common/LGPL-2.0.txt",
        "licenses/common/MIT.txt",
    ]
    for relative in composite_files:
        if not (root / relative).is_file():
            raise RuntimeError(f"gstreamer-python declared license text is missing: {relative}")
    records.append(
        (
            "gstreamer-python wheel",
            gst_python_dist.version,
            gst_python_dist.metadata["License"],
            composite_files,
            f"https://pypi.org/project/gstreamer-python/{gst_python_dist.version}/",
        )
    )
    return records


def _pyz_packages(root: Path) -> set[str]:
    from PyInstaller.archive.readers import ZlibArchiveReader

    pyz = root / "build" / "LiveRelay" / "PYZ-00.pyz"
    archive = ZlibArchiveReader(str(pyz))
    roots: set[str] = set()
    for name in archive.toc:
        if not isinstance(name, str) or name.startswith("__main__"):
            continue
        roots.add(name.split(".", 1)[0])
    packages: set[str] = set()
    for module, distributions in importlib.metadata.packages_distributions().items():
        if module in roots:
            packages.update(distributions or ())
    packages = {p for p in packages if p.casefold() not in {"liverelay", "twitch-to-ndi"}}
    # These are loaded by the PyInstaller bootloader/runtime rather than PYZ.
    packages.add("pyinstaller")
    return packages


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
    result_records = []
    env = _private_gst_env(runtime, root)
    for plugin in manifest["plugins"]:
        result = subprocess.run([str(inspect), plugin], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
        text = result.stdout
        match = re.search(r"Plugin Details:\s*\n\s*Name\s+([^\n]+)\n\s*Description\s+([^\n]*)\n\s*Filename\s+([^\n]+)\n\s*Version\s+([^\n]+)\n\s*License\s+([^\n]+)", text)
        if not match:
            raise RuntimeError(f"Unable to parse gst-inspect metadata for plugin {plugin}")
        name, _description, filename, version, license_id = (part.strip() for part in match.groups())
        if re.search(r"\b(?:AGPL|GPL)(?:v?\d(?:\.\d)?)?(?:\+|-\w+)?\b", license_id, re.IGNORECASE):
            raise RuntimeError(f"Forbidden GPL-family GStreamer plugin detected: {plugin} ({license_id})")
        if name != plugin:
            raise RuntimeError(f"Plugin identity mismatch: expected {plugin}, gst-inspect reports {name}")
        if not Path(filename).resolve().is_file():
            raise RuntimeError(f"Plugin binary is missing: {filename}")
        if not Path(filename).resolve().is_relative_to(runtime.resolve()):
            raise RuntimeError(f"Plugin resolves outside the bundled private runtime: {filename}")
        source = GST_SOURCES.get(plugin)
        if source is None:
            raise RuntimeError(f"No source-module mapping for GStreamer plugin {plugin}")
        expected_license = "MPL-2.0" if plugin == "ndi" else "LGPL-2.1-or-later"
        if plugin == "ndi" and not license_id.casefold().startswith("mpl"):
            raise RuntimeError(f"Unexpected gst-plugin-ndi license: {license_id}")
        if plugin != "ndi" and "lgpl" not in license_id.casefold():
            raise RuntimeError(f"Unexpected GStreamer plugin license: {plugin}: {license_id}")
        result_records.append((plugin, version, expected_license, source, filename))
    return result_records


def _copy_python_runtime_licenses(root: Path, output_root: Path) -> list[str]:
    python_root = Path(sys.base_prefix)
    copied: list[str] = []
    destination = root / "licenses" / "runtime"
    destination.mkdir(parents=True, exist_ok=True)
    sources = [
        (python_root / "LICENSE.txt", destination / "Python-PSF-2.0.txt"),
        (python_root / "tcl" / "tk8.6" / "license.terms", destination / "Tcl-Tk-license.terms"),
    ]
    for source, target in sources:
        if source.is_file():
            shutil.copy2(source, target)
            copied.append(str(target.relative_to(root)).replace("\\", "/"))
    bundled_names = {p.name.casefold() for p in output_root.rglob("*.dll")}
    required = {"python314.dll": "Python-PSF-2.0.txt", "tk86t.dll": "Tcl-Tk-license.terms", "tcl86t.dll": "Tcl-Tk-license.terms"}
    for filename, license_filename in required.items():
        if filename in bundled_names and not any(Path(p).name == license_filename for p in copied):
            raise RuntimeError(f"License text for bundled native component {filename} is missing")
    common = root / "licenses" / "common"
    common.mkdir(parents=True, exist_ok=True)
    lgpl = common / "LGPL-2.1.txt"
    if lgpl.is_file():
        shutil.copy2(lgpl, destination / "GStreamer-LGPL-2.1.txt")
        copied.append("licenses/runtime/GStreamer-LGPL-2.1.txt")
    mpl = common / "MPL-2.0.txt"
    if mpl.is_file():
        shutil.copy2(mpl, destination / "GStreamer-NDI-MPL-2.0.txt")
        copied.append("licenses/runtime/GStreamer-NDI-MPL-2.0.txt")
    return copied


def generate(root: Path, output_root: Path) -> None:
    packages = _pyz_packages(root)
    python_records = _write_package_licenses(root, packages)
    gst_records = _inspect_plugins(root, output_root)
    runtime_license_files = _copy_python_runtime_licenses(root, output_root)
    lines = [
        "LiveRelay Third-Party Notices",
        "==============================",
        "",
        "LiveRelay application code is licensed under MIT; see LICENSE.",
        "This inventory is generated from Python modules and GStreamer plugins in the built onedir artifact.",
        "Bundled third-party components retain their respective licenses.",
        "",
        "Python distributions",
        "--------------------",
    ]
    for name, version, license_name, license_files, url in sorted(python_records, key=lambda record: record[0].casefold()):
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
        "ffi-7.dll": ("libffi", "3.2.9999.5", "MIT", "https://gitlab.freedesktop.org/gstreamer/meson-ports/libffi"),
        "gio-2.0-0.dll": ("GLib", "2.82.4", "LGPL-2.1-or-later", "https://gitlab.gnome.org/GNOME/glib"),
        "girepository-1.0-1.dll": ("GLib", "2.82.4", "LGPL-2.1-or-later", "https://gitlab.gnome.org/GNOME/glib"),
        "glib-2.0-0.dll": ("GLib", "2.82.4", "LGPL-2.1-or-later", "https://gitlab.gnome.org/GNOME/glib"),
        "gmodule-2.0-0.dll": ("GLib", "2.82.4", "LGPL-2.1-or-later", "https://gitlab.gnome.org/GNOME/glib"),
        "gobject-2.0-0.dll": ("GLib", "2.82.4", "LGPL-2.1-or-later", "https://gitlab.gnome.org/GNOME/glib"),
        "intl-8.dll": ("proxy-libintl", "0.5", "LGPL-2.1-or-later", "https://github.com/frida/proxy-libintl"),
        "orc-0.4-0.dll": ("ORC", "0.4.42", "BSD-2-Clause AND BSD-3-Clause", "https://github.com/GStreamer/orc/tree/orc-0.4.42"),
        "pcre2-8-0.dll": ("PCRE2", "10.42", "BSD-3-Clause", "https://github.com/PCRE2Project/pcre2"),
        "z-1.dll": ("zlib", "1.3.1", "Zlib", "https://zlib.net/"),
    }
    for filename in sorted(gstreamer_bin.glob("*.dll")):
        if filename.name in gst_native:
            name, version, license_name, url = gst_native[filename.name]
            license_files = {
                "ffi-7.dll": "licenses/common/libffi-MIT.txt",
                "intl-8.dll": "licenses/runtime/GStreamer-LGPL-2.1.txt",
                "orc-0.4-0.dll": "licenses/common/ORC-COPYING.txt",
                "pcre2-8-0.dll": "licenses/common/PCRE2-BSD-3-Clause.txt",
                "z-1.dll": "licenses/common/zlib-Zlib.txt",
            }
            lines.append(f"- {filename.name} — {name} {version}, {license_name}; {url}")
            lines.append(f"  License text: {license_files.get(filename.name, 'licenses/runtime/GStreamer-LGPL-2.1.txt')}")
        else:
            lines.append(f"- {filename.name} — GStreamer {gst_version}, LGPL-2.1-or-later; https://gstreamer.freedesktop.org/src/")
    lines.extend(
        [
            "  License text: licenses/runtime/GStreamer-LGPL-2.1.txt",
            "  NDI plugin license text: licenses/runtime/GStreamer-NDI-MPL-2.0.txt",
            "  Separate DLLs are replaceable; no GStreamer libraries are statically linked.",
        ]
    )
    lines.extend(["", "Native runtimes", "---------------"])
    dll_names = {p.name.casefold() for p in output_root.rglob("*.dll")}
    for name, version, license_name, url, files, license_key in NATIVE_COMPONENTS:
        present = [f for f in files if f.casefold() in dll_names]
        if license_key == "gstreamer":
            present = ["runtime/gstreamer/bin/*.dll"]
        if present:
            lines.extend([f"- {name} {version} — {license_name}", f"  Source/terms: {url}", f"  Files: {', '.join(present)}"])
            if license_key == "openssl":
                lines.append("  License text: licenses/common/OpenSSL-Apache-2.0.txt")
            elif license_key == "libffi":
                lines.append("  License text: licenses/common/libffi-MIT.txt")
            elif license_key == "zlib":
                lines.append("  License text: licenses/common/zlib-Zlib.txt")
    if runtime_license_files:
        lines.extend(["", "Runtime license texts", "---------------------"])
        lines.extend(f"- {item}" for item in runtime_license_files)
    lines.extend(
        [
            "",
            "Windows system libraries",
            "-------------------------",
            "Windows API Set forwarders and ucrtbase.dll are operating-system components. They are not intended to be app-local; the build removes copies that PyInstaller discovers in Windows SDK/tool directories. Windows supplies the applicable system components.",
        ]
    )
    lines.extend(
        [
            "",
            "NDI",
            "---",
            "The NDI® trademark is owned by Vizrt NDI AB. NDI Runtime is not included in this package; the application uses an existing NDI Runtime selected by NDI_RUNTIME_DIR_V6. See https://ndi.video/ and the NDI SDK/runtime terms for the installed runtime.",
            "",
            "LGPL replacement and relinking information",
            "------------------------------------------",
            "The GStreamer LGPL libraries and plugins are distributed as separate replaceable DLL files under runtime/gstreamer. Python bytecode/application modules are not statically linked into those libraries. A recipient may replace those DLLs with compatible modified versions; rebuild the private runtime from corresponding source modules and preserve the same directory layout.",
            "",
            "PyInstaller",
            "-----------",
            "PyInstaller is used to construct this executable and its bootloader. Its GPL license includes the PyInstaller exception permitting distribution of the generated application under its own license.",
            "",
        ]
    )
    notice = "\n".join(lines)
    notice_path = root / "THIRD_PARTY_NOTICES.txt"
    notice_path.write_text(notice, encoding="utf-8", newline="\n")
    bundle_licenses = output_root / "licenses"
    shutil.copytree(root / "licenses", bundle_licenses, dirs_exist_ok=True)
    shutil.copy2(root / "LICENSE", output_root / "LICENSE")
    shutil.copy2(notice_path, output_root / "THIRD_PARTY_NOTICES.txt")
    if not (root / "licenses").is_dir() or not any((root / "licenses").rglob("*")):
        raise RuntimeError("License text directory is empty")
    print(f"Generated third-party inventory: {notice_path}")
    print(f"Inventoried {len(python_records)} Python distributions and {len(gst_records)} GStreamer plugins.")


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[1]
    generate(project_root, project_root / "dist" / "LiveRelay")
