# LiveRelay

Minimal Twitch live stream to NDI relay for Windows.

## Requirements

- Python 3.14 or newer, managed with `uv`
- GStreamer 1.28.6 MSVC x86_64 installed at the existing GStreamer path
- Matching `gstreamer-python` bindings (declared in the script metadata)
- GStreamer elements: `parsebin`, `d3d11h264dec`, `d3d11download`, `mfaacdec`, `ndisinkcombiner`, and `ndisink`
- NDI Runtime installed

Run directly with the dependencies declared in `main.py`'s PEP 723 metadata:

```powershell
uv run .\src\twitch_to_ndi\main.py https://www.twitch.tv/example --ndi-name "Runner A"
```

uv creates an isolated environment from the script's inline dependency list. To install the package and use its console command instead:

```powershell
uv sync
twitch-to-ndi https://www.twitch.tv/example --ndi-name "Runner A"
```

The relay lists available Twitch qualities and selects the lowest Twitch pixel-weight quality at 480p or higher. It defaults to a 5-second delay and accepts these commands while running:

```text
delay 5000
delay 7000
delay 3000
status
quit
```

Delay is limited to 0–30 seconds. Reducing delay drops the combined NDI output while the compressed queues drain; H.264/AAC buffers continue through their decoders. Queue levels are printed by `status` and while a decrease is in progress. Press Ctrl+C or enter `quit` to stop.

Check the GStreamer prerequisites with:

```powershell
gst-inspect-1.0 parsebin d3d11h264dec d3d11download mfaacdec ndisinkcombiner ndisink
```
