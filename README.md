# LiveRelay

Minimal Twitch live stream to NDI relay for Windows.

## Requirements

- Python 3.14 or newer, managed with `uv`
- GStreamer 1.28.6 MSVC x86_64 Full Runtime in `runtime/gstreamer` (or at the existing GStreamer path for the conventional launcher)
- Matching `gstreamer-python` bindings (declared in the script metadata)
- GStreamer elements: `parsebin`, `d3d11h264dec`, `d3d11download`, `mfaacdec`, `ndisinkcombiner`, and `ndisink`
- NDI Runtime installed

Install the locked dependencies and launch the Tkinter interface:

```powershell
uv sync
uv run twitch-to-ndi
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
`runtime/gstreamer`. For local testing it uses the installed NDI runtime
selected by `NDI_RUNTIME_DIR_V6`; otherwise it can use `runtime/ndi`. It never
falls back to a system GStreamer installation. Check both runtimes without
opening the UI with:

```powershell
uv run python scripts/run_private.py --check-only
```

For future redistribution, follow the [NDI SDK software distribution
guide](https://docs.ndi.video/all/developing-with-ndi/sdk/software-distribution)
and [licensing guide](https://docs.ndi.video/all/developing-with-ndi/sdk/licensing),
including the required NDI attribution and license coverage.

## Build the Windows onedir application

Build on Windows with Python 3.14. The private GStreamer runtime and the
`gstreamer-python` wheel must be available in the checkout. The installed NDI
Runtime is resolved through `NDI_RUNTIME_DIR_V6` when the application starts;
it is not copied from the build machine into the bundle.

```powershell
uv sync --group build
uv run --group build python packaging/build.py
```

The onedir output is `dist/TwitchToNDI/TwitchToNDI.exe`, with
`runtime/gstreamer` beside the executable. Run the bundled dependency check
with:

```powershell
.\dist\TwitchToNDI\TwitchToNDI.exe --check-only
```

The windowed executable writes diagnostics to
`%LOCALAPPDATA%\LiveRelay\logs\twitch-to-ndi.log` and stores its private
GStreamer registry under `%LOCALAPPDATA%\LiveRelay\cache`.

The previous command-line interface remains available:

```powershell
twitch-to-ndi-cli https://www.twitch.tv/example --ndi-name "Runner A"
```

The GUI selects the lowest Twitch pixel-weight quality at 480p or higher and requests Streamlink's Twitch low-latency mode. Twitch broadcasters must enable low-latency streaming for their channels; regular streams may buffer with this option. The GUI starts with a 0-second delay, supports 0–30 seconds in 0.1-second steps or larger buttons, and stops the stream when the window closes. Reducing delay drops the combined NDI output while the compressed queues drain; H.264/AAC buffers continue through their decoders.

For detailed Streamlink read and GStreamer queue timing in the terminal, enable diagnostics before launch:

```powershell
$env:TWITCH_TO_NDI_DIAGNOSTICS = "1"
uv run twitch-to-ndi
```

Check the GStreamer prerequisites with:

```powershell
gst-inspect-1.0 parsebin d3d11h264dec d3d11download mfaacdec ndisinkcombiner ndisink
```
