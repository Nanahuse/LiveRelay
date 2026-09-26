from __future__ import annotations

import importlib
import os
import queue
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any


MAX_DELAY_MS = 30_000
INITIAL_DELAY_MS = 0
QUEUE_MAX_TIME_NS = 35_000_000_000
QUEUE_MAX_BYTES = 0
QUEUE_MAX_BUFFERS = 0
OUTPUT_TIMING_TOLERANCE_NS = 50_000_000
QUEUE_POLL_INTERVAL_MS = 50
QUEUE_STALL_WARNING_SECONDS = 10
CHUNK_SIZE = 64 * 1024
APP_SOURCE_MAX_BYTES = 1024 * 1024
DIAGNOSTIC_INTERVAL_SECONDS = 0.25
DIAGNOSTICS_ENABLED = os.environ.get("TWITCH_TO_NDI_DIAGNOSTICS") == "1"
_DLL_DIRECTORY_HANDLES: list[Any] = []


def load_gst() -> tuple[Any, Any]:
    """Load the GStreamer introspection bindings from the installed runtime."""
    private_runtime = os.environ.get("TWITCH_TO_NDI_PRIVATE_RUNTIME") == "1"
    if private_runtime:
        private_root = os.environ.get("TWITCH_TO_NDI_GSTREAMER_ROOT")
        gst_bin = os.path.join(private_root or "", "bin", "gst-launch-1.0.exe")
        if not private_root or not os.path.isfile(gst_bin):
            raise RuntimeError("Private GStreamer Runtime is missing or incomplete.")
    else:
        gst_bin = shutil.which("gst-launch-1.0")
        if gst_bin is None and os.name == "nt":
            local_app_data = os.environ.get("LOCALAPPDATA")
            gst_bin = os.path.join(
                local_app_data or "",
                "Programs", "gstreamer", "1.0", "msvc_x86_64", "bin", "gst-launch-1.0.exe",
            )
    if gst_bin and os.name == "nt":
        gst_bin_dir = os.path.dirname(gst_bin)
        os.environ["PATH"] = gst_bin_dir + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(gst_bin_dir))
        if not private_runtime:
            runtime_root = os.path.dirname(gst_bin_dir)
            os.environ.setdefault("PYGI_DLL_DIRS", gst_bin_dir)
            os.environ.setdefault("GI_TYPELIB_PATH", os.path.join(runtime_root, "lib", "girepository-1.0"))
            runtime_plugins = os.path.join(runtime_root, "lib", "gstreamer-1.0")
            os.environ.setdefault("GST_PLUGIN_PATH_1_0", runtime_plugins)
            os.environ.setdefault("GST_PLUGIN_SYSTEM_PATH_1_0", runtime_plugins)
        # Frozen builds get the namespaced GI modules from the onedir bundle.
        # Source runs use the official wheel's Python path while keeping its
        # GStreamer plugins and typelibs excluded in private mode.
        if not (private_runtime and getattr(sys, "frozen", False)):
            try:
                gst_python = importlib.import_module("gstreamer_python")
                binding_paths = gst_python.environment["PYTHONPATH"].split(os.pathsep)
                for path in reversed(binding_paths):
                    if path not in sys.path:
                        sys.path.insert(0, path)
                if not private_runtime:
                    binding_root = os.path.join(os.path.dirname(gst_python.__file__), "Lib")
                    binding_typelibs = os.path.join(binding_root, "girepository-1.0")
                    os.environ["GI_TYPELIB_PATH"] = os.pathsep.join(
                        [binding_typelibs, os.environ["GI_TYPELIB_PATH"]]
                    )
                    binding_plugins = os.path.join(binding_root, "gstreamer-1.0")
                    os.environ["GST_PLUGIN_PATH_1_0"] = os.pathsep.join(
                        [binding_plugins, os.environ["GST_PLUGIN_PATH_1_0"]]
                    )
                    os.environ["GST_PLUGIN_SYSTEM_PATH_1_0"] = os.pathsep.join(
                        [runtime_plugins, binding_plugins]
                    )
            except ImportError:
                pass
    try:
        gi = importlib.import_module("gi")
        gi.require_version("Gst", "1.0")
        gi.require_version("GLib", "2.0")
        return importlib.import_module("gi.repository.Gst"), importlib.import_module("gi.repository.GLib")
    except (ImportError, ValueError) as error:
        raise RuntimeError(
            "GStreamer Python introspection bindings (PyGObject/Gst typelib) are not available. "
            "Install bindings compatible with the installed GStreamer runtime."
        ) from error


def build_pipeline(
    Gst: Any,
    ndi_name: str,
    initial_delay_ms: int = INITIAL_DELAY_MS,
    on_media_info: Any = None,
) -> tuple[Any, dict[str, Any]]:
    pipeline = Gst.Pipeline.new("liverelay")
    if pipeline is None:
        raise RuntimeError("Could not create GStreamer pipeline")

    appsrc = Gst.ElementFactory.make("appsrc", "stream_input")
    parser = Gst.ElementFactory.make("parsebin", "stream_parser")
    combiner = Gst.ElementFactory.make("ndisinkcombiner", "av_combiner")
    sync = Gst.ElementFactory.make("clocksync", "delay_sync")
    valve = Gst.ElementFactory.make("valve", "output_valve")
    sink = Gst.ElementFactory.make("ndisink", "ndi_output")
    video_queue = Gst.ElementFactory.make("queue", "video_delay_queue")
    video_decoder = Gst.ElementFactory.make("d3d11h264dec", "video_decoder")
    video_download = Gst.ElementFactory.make("d3d11download", "video_download")
    video_caps = Gst.ElementFactory.make("capsfilter", "ndi_video_caps")
    audio_queue = Gst.ElementFactory.make("queue", "audio_delay_queue")
    audio_decoder = Gst.ElementFactory.make("mfaacdec", "audio_decoder")
    audio_convert = Gst.ElementFactory.make("audioconvert", "audio_convert")
    audio_resample = Gst.ElementFactory.make("audioresample", "audio_resample")

    elements = {
        "appsrc": appsrc, "parsebin": parser, "ndisinkcombiner": combiner,
        "delay_sync": sync, "output_valve": valve, "ndisink": sink,
        "video_delay_queue": video_queue, "d3d11h264dec": video_decoder,
        "d3d11download": video_download, "ndi_video_caps": video_caps,
        "audio_delay_queue": audio_queue,
        "mfaacdec": audio_decoder, "audioconvert": audio_convert,
        "audioresample": audio_resample,
    }
    missing = [name for name, element in elements.items() if element is None]
    if missing:
        raise RuntimeError("Missing GStreamer elements: " + ", ".join(missing))

    for name in ("video_delay_queue", "audio_delay_queue"):
        element = elements[name]
        for prop in ("current-level-time", "current-level-bytes", "max-size-time", "max-size-bytes", "max-size-buffers"):
            if element.find_property(prop) is None:
                raise RuntimeError(f"Required property {prop} is not available on {name}")
        element.set_property("max-size-time", QUEUE_MAX_TIME_NS)
        element.set_property("max-size-bytes", QUEUE_MAX_BYTES)
        element.set_property("max-size-buffers", QUEUE_MAX_BUFFERS)

    appsrc.set_property("is-live", True)
    appsrc.set_property("format", Gst.Format.TIME)
    appsrc.set_property("block", True)
    appsrc.set_property("max-bytes", APP_SOURCE_MAX_BYTES)
    appsrc.set_property("stream-type", 0)  # GST_APP_STREAM_TYPE_STREAM
    sink.set_property("ndi-name", ndi_name)
    sync.set_property("ts-offset", initial_delay_ms * 1_000_000)
    valve.set_property("drop", False)

    for element in elements.values():
        pipeline.add(element)

    if not appsrc.link(parser):
        raise RuntimeError("Could not link appsrc to parsebin")
    if not combiner.link(sync) or not sync.link(valve) or not valve.link(sink):
        raise RuntimeError("Could not link the NDI output path")
    if not video_queue.link_filtered(
        video_decoder, Gst.Caps.from_string("video/x-h264")
    ):
        raise RuntimeError("Could not link H.264 queue to decoder")
    video_caps.set_property("caps", Gst.Caps.from_string("video/x-raw,format=NV12"))
    if not video_decoder.link(video_download) or not video_download.link(video_caps):
        raise RuntimeError("Could not link video decoder to NDI combiner")
    video_pad = combiner.get_static_pad("video")
    if video_pad is None or video_caps.get_static_pad("src").link(video_pad) != Gst.PadLinkReturn.OK:
        raise RuntimeError("Could not link video to NDI combiner request pad")
    if not audio_queue.link_filtered(
        audio_decoder, Gst.Caps.from_string("audio/mpeg,mpegversion=4")
    ):
        raise RuntimeError("Could not link AAC queue to decoder")
    if not audio_decoder.link(audio_convert) or not audio_convert.link(audio_resample):
        raise RuntimeError("Could not link audio decoder chain")
    audio_caps = Gst.ElementFactory.make("capsfilter", "ndi_audio_caps")
    if audio_caps is None:
        raise RuntimeError("Missing GStreamer capsfilter")
    audio_caps.set_property("caps", Gst.Caps.from_string(
        "audio/x-raw,format=F32LE,layout=interleaved,rate=48000,channels=2"
    ))
    pipeline.add(audio_caps)
    if not audio_resample.link(audio_caps):
        raise RuntimeError("Could not link audio chain to NDI combiner")
    audio_pad = combiner.request_pad_simple("audio")
    if audio_pad is None or audio_caps.get_static_pad("src").link(audio_pad) != Gst.PadLinkReturn.OK:
        raise RuntimeError("Could not link audio to NDI combiner request pad")

    linked_pads: set[int] = set()
    reported_media: set[str] = set()

    def report_caps(media: str, caps: Any) -> None:
        if on_media_info is None or media in reported_media or caps is None or caps.get_size() == 0:
            return
        structure = caps.get_structure(0)
        info: dict[str, Any] = {"media": media}
        if media == "video":
            info["width"] = structure.get_value("width")
            info["height"] = structure.get_value("height")
            fps = structure.get_value("framerate")
            try:
                info["fps"] = float(fps.num) / float(fps.denom)
            except (AttributeError, TypeError, ZeroDivisionError):
                info["fps"] = None
        elif media == "audio":
            info["audio_rate"] = structure.get_value("rate")
        on_media_info(info)
        reported_media.add(media)

    def on_demux_pad(_element: Any, pad: Any) -> None:
        caps = pad.get_current_caps() or pad.query_caps(None)
        if caps is None or caps.get_size() == 0:
            return
        media_type = caps.get_structure(0).get_name()
        if media_type == "video/x-h264":
            target = video_queue.get_static_pad("sink")
        elif media_type == "audio/mpeg":
            target = audio_queue.get_static_pad("sink")
        else:
            return
        if target is None or hash(target) in linked_pads or target.is_linked():
            return
        result = pad.link(target)
        if result == Gst.PadLinkReturn.OK:
            linked_pads.add(hash(target))
            print(f"Linked parsed {media_type} stream", flush=True)
        else:
            print(f"Could not link parsed {media_type} stream: {result.value_nick}", file=sys.stderr, flush=True)

    parser.connect("pad-added", on_demux_pad)
    if on_media_info is not None:
        for media, caps_element in (("video", video_caps), ("audio", audio_caps)):
            src_pad = caps_element.get_static_pad("src")

            def report_negotiated_caps(pad: Any, _info: Any, selected_media: str = media) -> Any:
                report_caps(selected_media, pad.get_current_caps())
                return Gst.PadProbeReturn.OK

            src_pad.add_probe(Gst.PadProbeType.BUFFER, report_negotiated_caps)
    elements["ndi_audio_caps"] = audio_caps
    return pipeline, elements


@dataclass
class Adjustment:
    old_delay_ms: int
    new_delay_ms: int
    direction: str
    started_at: float
    stall_warning_emitted: bool = False


class DelayController:
    def __init__(self, GLib: Any, elements: dict[str, Any], initial_delay_ms: int = INITIAL_DELAY_MS, *, Gst: Any) -> None:
        self.Gst = Gst
        self.GLib = GLib
        self.elements = elements
        self.delay_ms = initial_delay_ms
        self.adjustment: Adjustment | None = None
        self._poll_id: int | None = None
        self._output_probe: tuple[Any, int] | None = None
        self._generation = 0
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._generation += 1
            if self._poll_id is not None:
                self.GLib.source_remove(self._poll_id)
                self._poll_id = None
            self._remove_output_probe()
            self.adjustment = None

    def _remove_output_probe(self) -> None:
        if self._output_probe is not None:
            pad, probe_id = self._output_probe
            self._output_probe = None
            pad.remove_probe(probe_id)

    @staticmethod
    def _validate(delay_ms: int) -> int:
        if not 0 <= delay_ms <= MAX_DELAY_MS:
            raise ValueError(f"Delay must be between 0 and {MAX_DELAY_MS} ms")
        return delay_ms

    def set_delay_ms(self, delay_ms: int) -> None:
        with self._lock:
            self._validate(delay_ms)
            old_delay_ms = self.delay_ms
            if delay_ms == old_delay_ms:
                return
            self.close()
            try:
                self._apply_delay_ms(old_delay_ms, delay_ms)
            except Exception:
                self.close()
                self.delay_ms = old_delay_ms
                try:
                    self.elements["delay_sync"].set_property("ts-offset", old_delay_ms * 1_000_000)
                    self.elements["output_valve"].set_property("drop", False)
                except Exception as rollback_error:
                    raise RuntimeError(f"Delay change failed and could not restore output: {rollback_error}")
                raise

    def _apply_delay_ms(self, old_delay_ms: int, delay_ms: int) -> None:
        # Replace both the setting and completion observer on every request.
        # Old callbacks must never reopen the valve or finish a newer adjustment.
        generation = self._generation
        ready = threading.Event()
        remaining = 2
        sync = self.elements["delay_sync"]
        latency_query = self.Gst.Query.new_latency()
        upstream_latency_ns = 0
        if sync.get_static_pad("sink").peer_query(latency_query):
            live, minimum, _maximum = latency_query.parse_latency()
            if live:
                upstream_latency_ns = minimum

        def on_output(pad: Any, info: Any) -> Any:
            nonlocal remaining
            measured = self._output_delay_ns(pad, info, upstream_latency_ns)
            # Queue depth includes prefetched input and is not output latency.
            # Only buffers synchronized to the latest target prove completion.
            if measured is not None and abs(measured - delay_ms * 1_000_000) <= OUTPUT_TIMING_TOLERANCE_NS:
                remaining -= 1
            else:
                remaining = 2
            if remaining <= 0:
                ready.set()
            return self.Gst.PadProbeReturn.OK

        direction = "increasing" if delay_ms > old_delay_ms else "decreasing"
        adjustment = Adjustment(old_delay_ms, delay_ms, direction, time.monotonic())
        self.elements["delay_sync"].set_property("ts-offset", delay_ms * 1_000_000)
        self.delay_ms = delay_ms
        self.adjustment = adjustment
        # Always release a previous decrease's valve when reversing direction.
        self.elements["output_valve"].set_property("drop", direction == "decreasing")
        pad = self.elements["delay_sync"].get_static_pad("src")
        if pad is None:
            raise RuntimeError("Could not monitor Delay output")
        probe_id = pad.add_probe(
            self.Gst.PadProbeType.BUFFER | self.Gst.PadProbeType.BUFFER_LIST, on_output,
        )
        if not probe_id:
            raise RuntimeError("Could not monitor Delay output")
        self._output_probe = (pad, probe_id)

        def poll() -> bool:
            with self._lock:
                if generation != self._generation:
                    return False
                if ready.is_set():
                    self.elements["output_valve"].set_property("drop", False)
                    self._remove_output_probe()
                    self.adjustment = None
                    self._poll_id = None
                    print(f"Delay adjustment complete: {delay_ms}ms", flush=True)
                    return False
                elapsed = time.monotonic() - adjustment.started_at
                if elapsed >= QUEUE_STALL_WARNING_SECONDS and not adjustment.stall_warning_emitted:
                    adjustment.stall_warning_emitted = True
                    # Missing/late timestamps must not leave NDI muted forever.
                    # Keep observing progress without claiming it is complete.
                    self.elements["output_valve"].set_property("drop", False)
                    print(f"Warning: Delay {delay_ms}ms timing not confirmed; output unmuted", file=sys.stderr, flush=True)
                return True

        self._poll_id = self.GLib.timeout_add(QUEUE_POLL_INTERVAL_MS, poll)
        print(f"Delay adjustment: {old_delay_ms}ms -> {delay_ms}ms", flush=True)

    def _output_delay_ns(self, pad: Any, info: Any, upstream_latency_ns: int) -> int | None:
        if info.type & self.Gst.PadProbeType.BUFFER_LIST:
            buffers = info.get_buffer_list()
            buffer = buffers.get(0) if buffers is not None and buffers.length() else None
        else:
            buffer = info.get_buffer()
        if buffer is None:
            return None
        timestamp = buffer.dts if buffer.dts != self.Gst.CLOCK_TIME_NONE else buffer.pts
        event = pad.get_sticky_event(self.Gst.EventType.SEGMENT, 0)
        if timestamp == self.Gst.CLOCK_TIME_NONE or event is None:
            return None
        segment = event.parse_segment()
        if segment.format != self.Gst.Format.TIME:
            return None
        timestamp = segment.to_running_time(self.Gst.Format.TIME, timestamp)
        now = self.elements["delay_sync"].get_current_running_time()
        if timestamp == self.Gst.CLOCK_TIME_NONE or now == self.Gst.CLOCK_TIME_NONE:
            return None
        return now - timestamp - upstream_latency_ns


@dataclass(frozen=True)
class SetDelayRequest:
    request_id: int
    target_delay_ms: int


@dataclass(frozen=True)
class RuntimeEvent:
    stream_id: str
    session_id: int
    event_type: str
    payload: Any = None
    request_id: int | None = None


class Runtime:
    def __init__(
        self,
        Gst: Any,
        GLib: Any,
        pipeline: Any,
        elements: dict[str, Any],
        initial_delay_ms: int = INITIAL_DELAY_MS,
        notify: Any = None,
        stream_id: str = "primary",
        session_id: int = 0,
    ) -> None:
        self.stream_id = stream_id
        self.session_id = session_id
        self.Gst = Gst
        self.GLib = GLib
        self.pipeline = pipeline
        self.elements = elements
        self.loop = GLib.MainLoop()
        self.commands: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._pending_delay_request: SetDelayRequest | None = None
        self.failed: BaseException | None = None
        self.controller = DelayController(GLib, elements, initial_delay_ms, Gst=Gst)
        self.notify = notify
        self._diagnostic_started_at = time.monotonic()
        self._last_diagnostic_at = 0.0
        self._bus = pipeline.get_bus()
        self._bus.add_signal_watch()
        self._bus_handler = self._bus.connect("message", self._on_bus_message)
        self._command_id = GLib.timeout_add(25, self._drain_commands)
        self._snapshot_id = None
        if self.notify is not None or DIAGNOSTICS_ENABLED:
            self._snapshot_id = GLib.timeout_add(200, self._publish_snapshot)

    def emit(self, event_type: str, payload: Any = None, request_id: int | None = None) -> None:
        if self.notify is not None:
            self.notify(RuntimeEvent(self.stream_id, self.session_id, event_type, payload, request_id))

    def close(self) -> None:
        """Detach sources from the shared GLib context before another stream starts."""
        self.notify = None
        self._pending_delay_request = None
        for attribute in ("_command_id", "_snapshot_id"):
            source_id = getattr(self, attribute)
            if source_id is not None:
                self.GLib.source_remove(source_id)
                setattr(self, attribute, None)
        self.controller.close()
        if self._bus_handler is not None:
            self._bus.disconnect(self._bus_handler)
            self._bus.remove_signal_watch()
            self._bus_handler = None

    def _on_bus_message(self, _bus: Any, message: Any) -> None:
        if message.type == self.Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            self.failed = RuntimeError(f"GStreamer error: {error}; {debug or ''}")
            if self.notify is not None:
                self.emit("error", str(error))
            self.loop.quit()
        elif message.type == self.Gst.MessageType.EOS:
            self.loop.quit()
        elif message.type == self.Gst.MessageType.STATE_CHANGED and message.src == self.pipeline:
            _old, new, _pending = message.parse_state_changed()
            if new == self.Gst.State.PLAYING and self.notify is not None:
                self.emit("running")

    def _publish_snapshot(self) -> bool:
        try:
            now = time.monotonic()
            snapshot = {
                "adjusting_delay": self.controller.adjustment is not None,
                "appsrc_buffer_bytes": int(self.elements["appsrc"].get_property("current-level-bytes")),
                "video_buffer_ms": int(self.elements["video_delay_queue"].get_property("current-level-time")) // 1_000_000,
                "audio_buffer_ms": int(self.elements["audio_delay_queue"].get_property("current-level-time")) // 1_000_000,
            }
            if DIAGNOSTICS_ENABLED and now - self._last_diagnostic_at >= DIAGNOSTIC_INTERVAL_SECONDS:
                self._last_diagnostic_at = now
                print(
                    f"DIAG pipeline t={now - self._diagnostic_started_at:.3f}s "
                    f"appsrc_bytes={snapshot['appsrc_buffer_bytes']} "
                    f"video_queue_ms={snapshot['video_buffer_ms']} "
                    f"audio_queue_ms={snapshot['audio_buffer_ms']} "
                    f"delay_ms={self.controller.delay_ms} "
                    f"adjusting={snapshot['adjusting_delay']}",
                    flush=True,
                )
            if self.notify is not None:
                self.emit("runtime_snapshot", snapshot)
        except Exception as error:
            print(f"Could not read GStreamer status: {error}", file=sys.stderr, flush=True)
        return True

    def _drain_commands(self) -> bool:
        while True:
            try:
                command, value = self.commands.get_nowait()
            except queue.Empty:
                break
            if command == "set_delay":
                previous = self._pending_delay_request
                self._pending_delay_request = value
                if previous is not None:
                    self.emit("delay_change_failed", {
                        "error": "Superseded by a newer Delay request",
                    }, previous.request_id)
            elif command == "quit":
                self._pending_delay_request = None
                self._command_id = None
                self.loop.quit()
                return False

        # Coalesce requests received within this tick, then retarget immediately,
        # even when the previous adjustment is still in progress.
        if self._pending_delay_request is None:
            return True
        request = self._pending_delay_request
        self._pending_delay_request = None
        try:
            self.controller.set_delay_ms(request.target_delay_ms)
            self.emit("delay_changed", {
                "delay_ms": self.controller.delay_ms,
                "adjusting_delay": self.controller.adjustment is not None,
            }, request.request_id)
        except Exception as error:
            self.emit("delay_change_failed", {"error": str(error)}, request.request_id)
            print(f"Error: {error}", file=sys.stderr, flush=True)
        return True


def pump_stream(stream_io: Any, appsrc: Any, Gst: Any, stop: threading.Event, errors: queue.Queue[BaseException]) -> None:
    started_at = time.monotonic()
    last_read_at = started_at
    total_bytes = 0
    read_count = 0
    window_started_at = started_at
    window_read_count = 0
    window_bytes = 0
    window_max_read_ms = 0.0
    window_max_gap_ms = 0.0
    try:
        while not stop.is_set():
            read_started_at = time.monotonic()
            chunk = stream_io.read(CHUNK_SIZE)
            read_completed_at = time.monotonic()
            if not chunk:
                print("DIAG stream-eof", flush=True)
                appsrc.emit("end-of-stream")
                return
            read_ms = (read_completed_at - read_started_at) * 1000
            gap_ms = (read_completed_at - last_read_at) * 1000
            last_read_at = read_completed_at
            total_bytes += len(chunk)
            read_count += 1
            window_read_count += 1
            window_bytes += len(chunk)
            window_max_read_ms = max(window_max_read_ms, read_ms)
            window_max_gap_ms = max(window_max_gap_ms, gap_ms)
            if DIAGNOSTICS_ENABLED and read_completed_at - window_started_at >= 1.0:
                print(
                    f"DIAG stream-window t={read_completed_at - started_at:.3f}s "
                    f"reads={window_read_count} bytes={window_bytes} "
                    f"max_read_ms={window_max_read_ms:.1f} max_gap_ms={window_max_gap_ms:.1f}",
                    flush=True,
                )
                window_started_at = read_completed_at
                window_read_count = 0
                window_bytes = 0
                window_max_read_ms = 0.0
                window_max_gap_ms = 0.0
            elif not DIAGNOSTICS_ENABLED and gap_ms >= 1000:
                print(
                    f"DIAG stream-stall t={read_completed_at - started_at:.3f}s "
                    f"read_ms={read_ms:.1f} gap_ms={gap_ms:.1f} chunk_bytes={len(chunk)}",
                    flush=True,
                )
            buffer = Gst.Buffer.new_allocate(None, len(chunk), None)
            buffer.fill(0, chunk)
            result = appsrc.emit("push-buffer", buffer)
            if result != Gst.FlowReturn.OK:
                if not stop.is_set() and result != Gst.FlowReturn.FLUSHING:
                    errors.put(RuntimeError(f"GStreamer appsrc rejected data: {result.value_nick}"))
                return
        print(f"DIAG stream-stopped reads={read_count} total_bytes={total_bytes}", flush=True)
    except BaseException as error:
        if not stop.is_set():
            errors.put(error)
