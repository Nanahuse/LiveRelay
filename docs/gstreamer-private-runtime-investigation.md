# GStreamer Private Runtime Investigation

## Result

The allowlisted GStreamer 1.28.6 MSVC x86_64 runtime was generated from the
official Full Runtime snapshot in `runtime-source/gstreamer-full`. The source
snapshot was not modified. The minimal runtime occupies 23,465,344 bytes
(22.4 MiB) across 52 files. The source snapshot contains 828 files and
345,667,490 bytes (329.6 MiB); its installer uninstaller files are excluded
from the application runtime.

The generated runtime contains 13 plugin DLLs, 26 DLLs in `bin` (25
transitive PE-import dependencies plus `girepository-1.0-1.dll`), 10 typelibs,
the private `gst-plugin-scanner.exe`, and `gst-inspect-1.0.exe` /
`gst-launch-1.0.exe`. The GStreamer registry is generated in the local cache
at `cache/gstreamer-registry.bin`; the plugin scanner and registry paths are
set explicitly at launch.

## Plugin allowlist and element mapping

| Plugin DLL | Required elements |
| --- | --- |
| `gstapp.dll` | `appsrc` |
| `gstplayback.dll` | `parsebin` |
| `gstcoreelements.dll` | `typefind`, `queue`, `valve`, `clocksync` |
| `gstmpegtsdemux.dll` | `tsdemux` |
| `gstisomp4.dll` | `qtdemux` |
| `gstvideoparsersbad.dll` | `h264parse` |
| `gstaudioparsers.dll` | `aacparse` |
| `gstd3d11.dll` | `d3d11h264dec`, `d3d11download` |
| `gstmediafoundation.dll` | `mfaacdec` |
| `gstaudioconvert.dll` | `audioconvert` |
| `gstaudioresample.dll` | `audioresample` |
| `gstndi.dll` | `ndisinkcombiner`, `ndisink` |
| `gsttypefindfunctions.dll` | Container and stream type detection |

The element presence and plugin file locations were checked with both
`scripts/run_private.py --check-only` and `scripts/inspect_gstreamer.py`.
Every required element resolved from `runtime/gstreamer`; the system plugin
path was empty. The runtime also includes MPEG-TS and ISO BMFF/fMP4 demuxers,
H.264/AAC parsers, the D3D11 H.264 decoder, and the Media Foundation AAC
decoder.

## Live stream verification

On 2026-09-25, the user-provided Twitch channel was live and was tested through
the private-runtime launcher. Streamlink selected `480p30`; GStreamer linked
both parsed `video/x-h264` and `audio/mpeg` streams. Video and audio queue
levels advanced together. Delay was changed from 0 to 5,000 ms and back to 0;
the reduction completed and returned to steady state without a pipeline error.
This confirms that the application can receive both media streams and
exercise runtime delay adjustment with this broadcast.

The local NDI Runtime selected by `NDI_RUNTIME_DIR_V6` was loaded successfully.
No NDI Runtime DLLs are included in the generated private runtime. The test
did not use a separate NDI receiver to independently verify rendered video and
audible audio at the receiving end. The live test also did not identify which
container demuxer Twitch used; both demuxer plugins were verified present.

## Isolation and remaining validation

The launcher sets `GST_PLUGIN_PATH_1_0` to the generated runtime,
`GST_PLUGIN_SYSTEM_PATH_1_0` to an empty string, and selects its own scanner,
registry, and typelib directories. The GStreamer core and all required plugin
files resolved from the private runtime. NDI remains an installed machine
dependency.

A clean Windows machine without GStreamer was not available for this
investigation. Therefore this verifies runtime isolation on the development
machine, but does not establish operation on an independently provisioned
clean machine. Decoder availability and output quality can also depend on the
Windows media components and GPU drivers.
