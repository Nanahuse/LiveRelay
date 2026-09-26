# LiveRelay

Relay Twitch and YouTube live streams to an NDI source on Windows.

LiveRelay supports Twitch Live and YouTube Live URLs. YouTube VODs and regular
videos are not supported. Twitch can use the account name as the NDI source
name when NDI Source Name is blank; YouTube requires an explicit NDI source name.

## Requirements

- Python 3.14 or newer, managed with `uv`
- GStreamer 1.28.6 MSVC x86_64 Full Runtime source in `runtime-source/gstreamer-full`; generate the private runtime under `runtime/gstreamer`
- Matching `gstreamer-python` bindings (declared in the project dependencies)
- GStreamer elements: `parsebin`, `d3d11h264dec`, `d3d11download`, `mfaacdec`, `ndisinkcombiner`, and `ndisink`
- NDI Runtime installed locally and selected through `NDI_RUNTIME_DIR_V6`

Install the locked dependencies and launch the Tkinter interface:

```powershell
uv sync
uv run liverelay
```

## Private Runtime investigation

The official GStreamer 1.28.6 Full Runtime baseline is kept in the ignored
`runtime-source/gstreamer-full` directory. Build the allowlisted private
runtime from its dependency manifest with:

```powershell
uv run python scripts/prepare_gstreamer_runtime.py
```

Use `--full` only to copy the full baseline instead of the minimal runtime.

The private launch and element inspection configure an explicit plugin path,
an empty system plugin path, a private plugin scanner, registry cache, and
typelib directory before loading the Python bindings:

```powershell
uv run python scripts/inspect_gstreamer.py
uv run python scripts/run_private.py
```

The launch checks that required GStreamer modules resolve inside
`runtime/gstreamer` and uses the installed NDI runtime selected through
`NDI_RUNTIME_DIR_V6`. It never falls back to a system GStreamer installation.
Check both runtimes without
opening the UI with:

```powershell
uv run python scripts/run_private.py --check-only
```

For future redistribution, follow the [NDI SDK software distribution
guide](https://docs.ndi.video/all/developing-with-ndi/sdk/software-distribution)
and [licensing guide](https://docs.ndi.video/all/developing-with-ndi/sdk/licensing),
including the required NDI attribution and license coverage.

NDI® is a registered trademark of Vizrt NDI AB. See [ndi.video](https://ndi.video/).

## License

LiveRelay itself is licensed under the MIT License. Third-party components
distributed with LiveRelay remain under their respective licenses. See
the generated `THIRD_PARTY_NOTICES.txt` and `licenses/` in distributed builds
for details. The onedir build bundles LGPL libraries in replaceable files under
`runtime/gstreamer`; those files can be replaced with modified compatible
builds. NDI Runtime remains an installed machine dependency and is not included
in the bundle.

## Build the Windows onedir application

Build on Windows with Python 3.14. The private GStreamer runtime and the
`gstreamer-python` wheel must be available in the checkout. The installed NDI
Runtime is resolved through `NDI_RUNTIME_DIR_V6` when the application starts;
it is not copied from the build machine into the bundle.

```powershell
uv sync --group build
uv run --group build python packaging/build.py
```

The onedir output is `dist/LiveRelay/LiveRelay.exe`, with
`runtime/gstreamer` beside the executable. Run the bundled dependency check
with:

```powershell
.\dist\LiveRelay\LiveRelay.exe --check-only
```

The build downloads six version-pinned native license texts from upstream and
checks their SHA-256 hashes, so an internet connection is required during the
build.

The windowed executable writes diagnostics to
`%LOCALAPPDATA%\LiveRelay\logs\liverelay.log` and stores its private
GStreamer registry under `%LOCALAPPDATA%\LiveRelay\cache`.

The GUI's Minimum Resolution selector offers 144p, 240p, 360p, 480p, 720p,
and 1080p. It defaults to 480p each time the application opens and is not saved.
Both providers use Streamlink's pixel weights to select the lowest quality at
or above the selected minimum, including qualities such as 720p60. An exact
match is not required: a 720p minimum selects 1080p if it is the lowest available
candidate. If no qualifying pixel stream exists, startup fails with an error
that includes the selected minimum.
Only qualities classified as `pixels` by the provider's Streamlink
`stream_weight()` are eligible; other groups are excluded.

Minimum Resolution is editable only while Stopped or in Error. Changes apply
on the next Start; running streams do not change quality.

Twitch automatically enables Streamlink's low-latency mode, caps the HLS live
edge at 2 segments, and streams segment data as it arrives instead of waiting
for a full segment download. Startup logs confirm that the mode is enabled.
These settings follow [Streamlink's Twitch low-latency mode](https://streamlink.github.io/cli/plugins/twitch.html#low-latency-streaming).
YouTube uses Streamlink's default settings. Twitch broadcasters must enable low-latency streaming for their
channels; regular streams may buffer with this option. The GUI starts with a
0-second delay, supports 0–30 seconds in 0.1-second steps or larger buttons,
and stops the stream when the window closes. Reducing delay drops the combined
NDI output while the compressed queues drain; H.264/AAC buffers continue
through their decoders.

For detailed Streamlink read and GStreamer queue timing in the terminal, enable diagnostics before launch:

```powershell
$env:TWITCH_TO_NDI_DIAGNOSTICS = "1"
uv run liverelay
```

Check the GStreamer prerequisites with:

```powershell
gst-inspect-1.0 parsebin d3d11h264dec d3d11download mfaacdec ndisinkcombiner ndisink
```
