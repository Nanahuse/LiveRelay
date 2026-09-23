# LiveRelay

Minimal Twitch live stream to NDI relay for Windows.

## Requirements

- Python 3.14 or newer, managed with `uv`
- GStreamer 1.x `gst-launch-1.0.exe` available on `PATH`
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

The relay lists available Twitch qualities, selects the lowest Twitch pixel-weight quality at 480p or higher, and forwards the compressed stream to GStreamer. Press Ctrl+C to stop.

Check the GStreamer prerequisites with:

```powershell
gst-inspect-1.0 parsebin d3d11h264dec d3d11download mfaacdec ndisinkcombiner ndisink
```
