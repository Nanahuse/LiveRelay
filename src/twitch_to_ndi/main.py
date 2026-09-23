# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "streamlink>=7.0",
# ]
# ///
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from typing import Any

from streamlink import Streamlink
from streamlink.exceptions import StreamlinkError


CHUNK_SIZE = 64 * 1024


def select_stream(plugin: Any, streams: dict[str, Any]) -> tuple[str, Any]:
    threshold, _ = plugin.stream_weight("480p")
    candidates = []
    for name, stream in streams.items():
        weight, group = plugin.stream_weight(name)
        if group == "pixels" and weight >= threshold:
            candidates.append((weight, name, stream))
    if not candidates:
        raise ValueError("No pixel stream at 480p or higher is available")
    _, name, stream = min(candidates, key=lambda candidate: (candidate[0], candidate[1]))
    return name, stream


def make_pipeline(ndi_name: str) -> list[str]:
    gst_launch = shutil.which("gst-launch-1.0")
    if gst_launch is None and os.name == "nt":
        gst_root = os.environ.get("GSTREAMER_1_0_ROOT_MSVC_X86_64")
        candidates = []
        if gst_root:
            candidates.append(os.path.join(gst_root, "bin", "gst-launch-1.0.exe"))
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(os.path.join(
                local_app_data, "Programs", "gstreamer", "1.0", "msvc_x86_64", "bin", "gst-launch-1.0.exe"
            ))
        gst_launch = next((path for path in candidates if os.path.isfile(path)), None)
    if gst_launch is None:
        raise FileNotFoundError("gst-launch-1.0 was not found on PATH")
    return [
        gst_launch, "-e", "fdsrc", "fd=0", "is-live=true", "!",
        "parsebin", "name=p",
        "ndisinkcombiner", "name=comb", "!", "ndisink", f"ndi-name={ndi_name}",
        "p.", "!", "queue", "!", "video/x-h264", "!", "d3d11h264dec", "!",
        "d3d11download", "!",
        "video/x-raw,format=NV12", "!", "comb.video",
        "p.", "!", "queue", "!", "audio/mpeg,mpegversion=4", "!", "mfaacdec", "!",
        "audioconvert", "!", "audioresample", "!",
        "audio/x-raw,format=F32LE,layout=interleaved,rate=48000,channels=2", "!", "queue", "!", "comb.audio",
    ]


def run(url: str, ndi_name: str) -> int:
    session = Streamlink()
    stream_io = None
    process = None
    try:
        _, plugin_class, resolved_url = session.resolve_url(url)
        plugin = plugin_class(session, resolved_url)
        streams = plugin.streams()
        if not streams:
            raise ValueError("Twitch returned no streams (the channel may be offline)")

        names = list(streams)
        print("Available streams:")
        print(", ".join(names))
        selected_name, selected_stream = select_stream(plugin, streams)
        print("\nSelected:")
        print(selected_name)
        print("\nNDI name:")
        print(ndi_name)

        stream_io = selected_stream.open()
        process = subprocess.Popen(
            make_pipeline(ndi_name),
            stdin=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        assert process.stdin is not None
        while True:
            chunk = stream_io.read(CHUNK_SIZE)
            if not chunk:
                break
            process.stdin.write(chunk)
        process.stdin.close()
        return_code = process.wait()
        if return_code:
            raise RuntimeError(f"GStreamer exited with status {return_code}")
        return 0
    except KeyboardInterrupt:
        print("\nStopping...", file=sys.stderr)
        return 0
    except (StreamlinkError, OSError, ValueError, RuntimeError, BrokenPipeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Unexpected error: {error}", file=sys.stderr)
        return 1
    finally:
        if stream_io is not None:
            try:
                stream_io.close()
            except Exception:
                pass
        if process is not None:
            if process.stdin is not None and not process.stdin.closed:
                try:
                    process.stdin.close()
                except OSError:
                    pass
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def main() -> None:
    parser = argparse.ArgumentParser(prog="twitch-to-ndi")
    parser.add_argument("url", help="Twitch channel URL")
    parser.add_argument("--ndi-name", required=True, help="NDI source name")
    args = parser.parse_args()
    raise SystemExit(run(args.url, args.ndi_name))


if __name__ == "__main__":
    main()
