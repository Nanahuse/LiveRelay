from __future__ import annotations

import logging
import queue
import sys
import threading
from dataclasses import dataclass
from typing import Any

from streamlink import Streamlink
from streamlink.exceptions import StreamlinkError

from stream_runtime import (
    DIAGNOSTICS_ENABLED,
    INITIAL_DELAY_MS,
    MAX_DELAY_MS,
    Runtime,
    RuntimeEvent,
    SetDelayRequest,
    build_pipeline,
    load_gst,
    pump_stream,
)
from stream_source import resolve_stream, select_stream


@dataclass(frozen=True)
class StreamSnapshot:
    state: str
    stream_url: str
    ndi_name: str
    selected_quality: str | None
    width: int | None
    height: int | None
    fps: float | None
    audio_rate: int | None
    confirmed_delay_ms: int
    requested_delay_ms: int | None
    display_delay_ms: int
    adjusting_delay: bool
    video_buffer_ms: int
    audio_buffer_ms: int
    error: str | None


class StreamController:
    """Owns one Streamlink session and its GStreamer pipeline."""

    def __init__(self, stream_id: str = "primary") -> None:
        self.stream_id = stream_id
        self.session_id = 0
        self.latest_delay_request_id = 0
        self._confirmed_request_id = 0
        self._completed_delay_request_id = 0
        self._lock = threading.RLock()
        self._state = "stopped"
        self._url = ""
        self._ndi_name = ""
        self._minimum_resolution = "480p"
        self._quality: str | None = None
        self._width: int | None = None
        self._height: int | None = None
        self._fps: float | None = None
        self._audio_rate: int | None = None
        self._confirmed_delay_ms = INITIAL_DELAY_MS
        self._requested_delay_ms: int | None = None
        self._adjusting = False
        self._video_buffer_ms = 0
        self._audio_buffer_ms = 0
        self._error: str | None = None
        self._stop_event = threading.Event()
        self._runtime: Runtime | None = None
        self._worker: threading.Thread | None = None

    def snapshot(self) -> StreamSnapshot:
        with self._lock:
            return StreamSnapshot(
                state=self._state,
                stream_url=self._url,
                ndi_name=self._ndi_name,
                selected_quality=self._quality,
                width=self._width,
                height=self._height,
                fps=self._fps,
                audio_rate=self._audio_rate,
                confirmed_delay_ms=self._confirmed_delay_ms,
                requested_delay_ms=self._requested_delay_ms,
                display_delay_ms=self._display_delay_ms,
                adjusting_delay=self._adjusting,
                video_buffer_ms=self._video_buffer_ms,
                audio_buffer_ms=self._audio_buffer_ms,
                error=self._error,
            )

    @property
    def _display_delay_ms(self) -> int:
        return self._requested_delay_ms if self._requested_delay_ms is not None else self._confirmed_delay_ms

    @property
    def shutdown_complete(self) -> bool:
        with self._lock:
            return self._state in ("stopped", "error") and (
                self._worker is None or not self._worker.is_alive()
            )

    def start(
        self, stream_url: str, ndi_name: str = "", minimum_resolution: str = "480p",
    ) -> None:
        stream_url = stream_url.strip()
        if not stream_url:
            raise ValueError("Enter a Stream URL.")
        with self._lock:
            if self._state not in ("stopped", "error"):
                raise RuntimeError("The stream is already starting or running.")
            if self._worker is not None and self._worker.is_alive():
                raise RuntimeError("The previous stream is still stopping.")
            self._url = stream_url
            self._ndi_name = ndi_name.strip()
            self._minimum_resolution = minimum_resolution
            self._quality = None
            self._width = None
            self._height = None
            self._fps = None
            self._audio_rate = None
            self._video_buffer_ms = 0
            self._audio_buffer_ms = 0
            self._error = None
            self._adjusting = False
            self._requested_delay_ms = None
            self.session_id += 1
            self._state = "starting"
            self._stop_event = threading.Event()
            worker = threading.Thread(target=self._run_stream, args=(self.session_id,), name="single-stream-controller", daemon=True)
            self._worker = worker
            worker.start()

    def stop(self) -> None:
        with self._lock:
            if self._state in ("stopped", "error"):
                if self._state == "error":
                    self._state = "stopped"
                    self._error = None
                return
            self._state = "stopping"
            self._stop_event.set()
            runtime = self._runtime
            if runtime is not None:
                runtime.commands.put(("quit", None))

    def change_delay_ms(self, amount_ms: int) -> None:
        if amount_ms == 0:
            return
        with self._lock:
            if self._state in ("starting", "stopping"):
                raise RuntimeError("Delay controls are unavailable while the stream is starting or stopping.")
            target = self._display_delay_ms + amount_ms
            if not 0 <= target <= MAX_DELAY_MS:
                raise ValueError(f"Delay must stay between 0.0 and {MAX_DELAY_MS / 1000:.1f} seconds.")
            if self._state in ("stopped", "error"):
                self._confirmed_delay_ms = target
                self._requested_delay_ms = None
                return
            runtime = self._runtime
            if runtime is None:
                raise RuntimeError("Stream controls are not ready yet.")
            self.latest_delay_request_id += 1
            self._requested_delay_ms = target
            self._error = None
            self._log_delay("set_delay", self.latest_delay_request_id)
            runtime.commands.put(("set_delay", SetDelayRequest(self.latest_delay_request_id, target)))

    def _log_delay(self, event_type: str, request_id: int | None, *, stale: bool = False) -> None:
        message = (
            f"event_type={event_type} stream_id={self.stream_id} session_id={self.session_id} "
            f"request_id={request_id} requested_delay_ms={self._requested_delay_ms} "
            f"confirmed_delay_ms={self._confirmed_delay_ms} stale={stale}"
        )
        logging.getLogger(__name__).debug(message)
        if DIAGNOSTICS_ENABLED:
            print(f"DIAG {message}", flush=True)

    def _on_media_info(self, info: dict[str, Any]) -> None:
        with self._lock:
            if info["media"] == "video":
                self._width = info.get("width")
                self._height = info.get("height")
                self._fps = info.get("fps")
            elif info["media"] == "audio":
                self._audio_rate = info.get("audio_rate")

    def _on_runtime_event(self, message: RuntimeEvent) -> None:
        with self._lock:
            if message.stream_id != self.stream_id or message.session_id != self.session_id:
                logging.getLogger(__name__).debug("Ignoring stale runtime event: %s", message)
                self._log_delay(message.event_type, message.request_id, stale=True)
                if DIAGNOSTICS_ENABLED:
                    print(f"DIAG ignored stream_id={message.stream_id} session_id={message.session_id}", flush=True)
                return
            event, value = message.event_type, message.payload
            if event in ("delay_changed", "delay_change_failed"):
                request_id = message.request_id
                if (request_id is None or request_id <= max(self._confirmed_request_id, self._completed_delay_request_id)
                        or request_id > self.latest_delay_request_id
                        or self._requested_delay_ms is None):
                    self._log_delay(event, request_id, stale=True)
                    return
                # Keep an accepted intermediate value as fallback without changing the display.
                if event == "delay_changed":
                    self._confirmed_delay_ms = int(value["delay_ms"])
                    self._confirmed_request_id = request_id
                    if "adjusting_delay" in value:
                        self._adjusting = bool(value["adjusting_delay"])
                        if self._state not in ("stopping", "error"):
                            self._state = "adjusting" if self._adjusting else "running"
                if request_id == self.latest_delay_request_id:
                    self._completed_delay_request_id = request_id
                    self._requested_delay_ms = None
                    if event == "delay_change_failed":
                        self._error = self._short_error(value["error"])
                self._log_delay(event, request_id, stale=request_id != self.latest_delay_request_id)
            elif event == "media_info":
                self._on_media_info(value)
            elif event == "running":
                if self._state == "starting":
                    self._state = "running"
            elif event == "error":
                self._error = self._short_error(value)
                self._requested_delay_ms = None
                self._state = "error"
            elif event == "runtime_snapshot":
                self._video_buffer_ms = int(value["video_buffer_ms"])
                self._audio_buffer_ms = int(value["audio_buffer_ms"])
                self._adjusting = bool(value["adjusting_delay"])
                if self._state not in ("stopped", "stopping", "error"):
                    self._state = "adjusting" if self._adjusting else "running"

    @staticmethod
    def _short_error(error: Any) -> str:
        message = str(error).strip().splitlines()[0] if error else "Stream failed."
        return message[:180]

    def _run_stream(self, session_id: int) -> None:
        stream_io = None
        runtime: Runtime | None = None
        pump_thread: threading.Thread | None = None
        pump_errors: queue.Queue[BaseException] = queue.Queue()
        try:
            session = Streamlink()
            provider, plugin, _resolved_url, resolved_ndi_name = resolve_stream(
                session, self._url, self._ndi_name
            )
            with self._lock:
                self._ndi_name = resolved_ndi_name
            Gst, GLib = load_gst()
            Gst.init(None)
            streams = plugin.streams()
            if not streams:
                raise ValueError(f"No live stream is available for this {provider.title()} URL.")
            selected_name, selected_stream = select_stream(plugin, streams, self._minimum_resolution)
            with self._lock:
                self._quality = selected_name
                initial_delay_ms = self._confirmed_delay_ms
            print(f"Selected {provider.title()} quality: {selected_name}", flush=True)
            if self._stop_event.is_set():
                return

            pipeline, elements = build_pipeline(
                Gst, self._ndi_name, initial_delay_ms,
                lambda info: self._on_runtime_event(RuntimeEvent(self.stream_id, session_id, "media_info", info))
            )
            runtime = Runtime(
                Gst, GLib, pipeline, elements,
                initial_delay_ms=initial_delay_ms,
                notify=self._on_runtime_event,
                stream_id=self.stream_id, session_id=session_id,
            )
            with self._lock:
                self._runtime = runtime
            stream_io = selected_stream.open()
            if self._stop_event.is_set():
                return
            result = pipeline.set_state(Gst.State.PLAYING)
            if result == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError("Could not start GStreamer pipeline.")
            pump_thread = threading.Thread(
                target=pump_stream,
                args=(stream_io, elements["appsrc"], Gst, self._stop_event, pump_errors),
                name="streamlink-pump",
                daemon=True,
            )
            pump_thread.start()
            watcher_id = GLib.timeout_add(100, lambda: self._check_pump_error(runtime, pump_errors))
            try:
                runtime.loop.run()
            finally:
                GLib.source_remove(watcher_id)
            if runtime.failed is not None:
                raise runtime.failed
            if not self._stop_event.is_set():
                raise RuntimeError("The live stream ended.")
        except (StreamlinkError, OSError, ValueError, RuntimeError) as error:
            print(f"Error: {error}", file=sys.stderr, flush=True)
            with self._lock:
                if not self._stop_event.is_set():
                    self._error = self._short_error(error)
                    self._state = "error"
        except Exception as error:
            print(f"Unexpected error: {error}", file=sys.stderr, flush=True)
            with self._lock:
                if not self._stop_event.is_set():
                    self._error = self._short_error(error)
                    self._state = "error"
        finally:
            self._stop_event.set()
            if runtime is not None:
                runtime.close()
                runtime.pipeline.set_state(runtime.Gst.State.NULL)
            if stream_io is not None:
                try:
                    stream_io.close()
                except Exception:
                    pass
            if pump_thread is not None:
                pump_thread.join(timeout=2)
            with self._lock:
                self._runtime = None
                self._adjusting = False
                self._requested_delay_ms = None
                if self._state != "error":
                    self._state = "stopped"

    def _check_pump_error(self, runtime: Runtime, errors: queue.Queue[BaseException]) -> bool:
        try:
            error = errors.get_nowait()
        except queue.Empty:
            return True
        runtime.failed = RuntimeError(f"Streamlink input error: {error}")
        runtime.emit("error", str(runtime.failed))
        runtime.loop.quit()
        return False


# Compatibility for existing single-stream callers.
SingleStreamController = StreamController
