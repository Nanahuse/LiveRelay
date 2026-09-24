# LiveRelay

Minimal Twitch live stream to NDI relay for Windows.

## Requirements

- Python 3.14 or newer, managed with `uv`
- GStreamer 1.28.6 MSVC x86_64 installed at the existing GStreamer path
- Matching `gstreamer-python` bindings (declared in the script metadata)
- GStreamer elements: `parsebin`, `d3d11h264dec`, `d3d11download`, `mfaacdec`, `ndisinkcombiner`, and `ndisink`
- NDI Runtime installed

Install the locked dependencies and launch the Tkinter interface:

```powershell
uv sync
uv run twitch-to-ndi
```

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
