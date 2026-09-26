from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from controller import StreamController


DELAY_STEPS_MS = (5000, 1000, 500, 100)
MINIMUM_RESOLUTIONS = ("144p", "240p", "360p", "480p", "720p", "1080p")


class RelayWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.controller = StreamController()
        self._closing = False
        self._refresh_id: str | None = None
        self._local_error: str | None = None
        self._delay_buttons: list[tuple[tk.Button, int]] = []

        root.title("LiveRelay")
        root.geometry("660x560")
        root.minsize(620, 510)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.url_var = tk.StringVar(value="")
        self.ndi_var = tk.StringVar(value="")
        self.minimum_resolution_var = tk.StringVar(value="480p")
        self.status_var = tk.StringVar(value="Status: Stopped")
        self.quality_var = tk.StringVar(value="-")
        self.video_var = tk.StringVar(value="-")
        self.audio_var = tk.StringVar(value="-")
        self.ndi_info_var = tk.StringVar(value="-")
        self.delay_var = tk.StringVar(value="0.0 s")
        self.adjusting_var = tk.StringVar(value="")
        self.video_buffer_var = tk.StringVar(value="-")
        self.audio_buffer_var = tk.StringVar(value="-")
        self.error_var = tk.StringVar(value="")

        body = tk.Frame(root, padx=16, pady=12)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="Stream URL").grid(row=0, column=0, sticky="w", pady=(0, 3))
        self.url_entry = tk.Entry(body, textvariable=self.url_var, width=72)
        self.url_entry.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 9))

        tk.Label(body, text="NDI Source Name").grid(row=2, column=0, sticky="w", pady=(0, 3))
        self.ndi_entry = tk.Entry(body, textvariable=self.ndi_var, width=48)
        self.ndi_entry.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 9))

        self.start_button = tk.Button(body, text="Start", width=12, command=self.on_start)
        self.start_button.grid(row=3, column=3, sticky="e", padx=(12, 0), pady=(0, 9))

        tk.Label(body, text="Minimum Resolution").grid(row=4, column=0, sticky="w", pady=(0, 3))
        self.minimum_resolution_combo = ttk.Combobox(
            body, textvariable=self.minimum_resolution_var,
            values=MINIMUM_RESOLUTIONS, state="readonly", width=12,
        )
        self.minimum_resolution_combo.grid(row=5, column=0, sticky="w", pady=(0, 9))

        self.status_label = tk.Label(body, textvariable=self.status_var, anchor="w")
        self.status_label.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(2, 8))

        info = tk.Frame(body)
        info.grid(row=7, column=0, columnspan=4, sticky="ew", pady=(0, 12))
        self._info_row(info, 0, "Quality", self.quality_var)
        self._info_row(info, 1, "Video", self.video_var)
        self._info_row(info, 2, "Audio", self.audio_var)
        self._info_row(info, 3, "NDI", self.ndi_info_var)

        tk.Label(body, text="Delay").grid(row=8, column=0, sticky="w", pady=(0, 6))
        delay_row = tk.Frame(body)
        delay_row.grid(row=9, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        for step_ms in DELAY_STEPS_MS:
            seconds = step_ms / 1000
            button = tk.Button(
                delay_row,
                text=f"-{seconds:g}s",
                width=6,
                command=lambda amount=step_ms: self.on_delay(-amount),
            )
            button.pack(side="left", padx=(0, 4))
            self._delay_buttons.append((button, -step_ms))

        tk.Label(delay_row, textvariable=self.delay_var, width=8, anchor="center", font=("TkDefaultFont", 16, "bold")).pack(side="left", padx=8)
        for step_ms in reversed(DELAY_STEPS_MS):
            seconds = step_ms / 1000
            button = tk.Button(
                delay_row,
                text=f"+{seconds:g}s",
                width=6,
                command=lambda amount=step_ms: self.on_delay(amount),
            )
            button.pack(side="left", padx=(4, 0))
            self._delay_buttons.append((button, step_ms))

        self.adjusting_label = tk.Label(body, textvariable=self.adjusting_var, anchor="w")
        self.adjusting_label.grid(row=10, column=0, columnspan=4, sticky="w", pady=(0, 4))
        buffers = tk.Frame(body)
        buffers.grid(row=11, column=0, columnspan=4, sticky="ew", pady=(0, 8))
        tk.Label(buffers, text="Video buffer", width=16, anchor="w").grid(row=0, column=0, sticky="w")
        tk.Label(buffers, textvariable=self.video_buffer_var, anchor="w").grid(row=0, column=1, sticky="w")
        tk.Label(buffers, text="Audio buffer", width=16, anchor="w").grid(row=1, column=0, sticky="w")
        tk.Label(buffers, textvariable=self.audio_buffer_var, anchor="w").grid(row=1, column=1, sticky="w")

        self.error_label = tk.Label(body, textvariable=self.error_var, anchor="w", justify="left", wraplength=620)
        self.error_label.grid(row=12, column=0, columnspan=4, sticky="ew", pady=(4, 0))

        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_columnconfigure(2, weight=1)
        body.grid_columnconfigure(3, weight=0)
        self.refresh_ui()

    @staticmethod
    def _info_row(parent: tk.Frame, row: int, title: str, variable: tk.StringVar) -> None:
        tk.Label(parent, text=title, width=16, anchor="w").grid(row=row, column=0, sticky="w")
        tk.Label(parent, textvariable=variable, anchor="w").grid(row=row, column=1, sticky="w")

    def on_start(self) -> None:
        self._local_error = None
        try:
            self.controller.start(
                self.url_var.get(), self.ndi_var.get(), self.minimum_resolution_var.get(),
            )
        except (RuntimeError, ValueError) as error:
            self._local_error = str(error)
        self.refresh_ui()

    def on_stop(self) -> None:
        self._local_error = None
        self.controller.stop()
        self.refresh_ui()

    def on_delay(self, amount_ms: int) -> None:
        self._local_error = None
        try:
            self.controller.change_delay_ms(amount_ms)
        except (RuntimeError, ValueError) as error:
            self._local_error = str(error)
        self.refresh_ui()

    def refresh_ui(self) -> None:
        if self._refresh_id is not None:
            self.root.after_cancel(self._refresh_id)
            self._refresh_id = None
        if self._closing:
            return
        snapshot = self.controller.snapshot()
        state = snapshot.state
        display_state = {
            "stopped": "Stopped",
            "starting": "Starting...",
            "running": "Running",
            "adjusting": "Adjusting Delay",
            "stopping": "Stopping...",
            "error": "Error",
        }.get(state, "Stopped")
        self.status_var.set(f"Status: {display_state}")
        if self._local_error:
            self.status_var.set("Status: Error")
        elif snapshot.error:
            self.status_var.set("Status: Error")

        active = state in ("starting", "running", "adjusting", "stopping")
        editable = not active
        self.url_entry.config(state="normal" if editable else "disabled")
        self.ndi_entry.config(state="normal" if editable else "disabled")
        self.minimum_resolution_combo.config(state="readonly" if editable else "disabled")

        if state in ("running", "adjusting"):
            self.start_button.config(text="Stop", state="normal", command=self.on_stop)
        elif state == "starting":
            self.start_button.config(text="Starting...", state="disabled", command=self.on_start)
        elif state == "stopping":
            self.start_button.config(text="Stopping...", state="disabled", command=self.on_start)
        else:
            self.start_button.config(text="Start", state="normal", command=self.on_start)

        self.quality_var.set(snapshot.selected_quality or "-")
        if snapshot.width and snapshot.height:
            if snapshot.fps:
                fps = f"{snapshot.fps:.0f}" if abs(snapshot.fps - round(snapshot.fps)) < 0.05 else f"{snapshot.fps:.1f}"
                self.video_var.set(f"{snapshot.width}×{snapshot.height} / {fps} fps")
            else:
                self.video_var.set(f"{snapshot.width}×{snapshot.height}")
        else:
            self.video_var.set("-")
        self.audio_var.set(f"{snapshot.audio_rate / 1000:g} kHz" if snapshot.audio_rate else "-")
        self.ndi_info_var.set(snapshot.ndi_name if active else "-")
        self.delay_var.set(f"{snapshot.display_delay_ms / 1000:.1f} s")
        adjusting = snapshot.adjusting_delay or state == "adjusting"
        pending = snapshot.requested_delay_ms is not None
        self.adjusting_var.set("Adjusting..." if adjusting or pending else "")

        if active and state not in ("starting", "stopping"):
            self.video_buffer_var.set(f"{snapshot.video_buffer_ms / 1000:.2f} s")
            self.audio_buffer_var.set(f"{snapshot.audio_buffer_ms / 1000:.2f} s")
        else:
            self.video_buffer_var.set("-")
            self.audio_buffer_var.set("-")
        self.error_var.set(self._local_error or snapshot.error or "")

        controls_ready = state in ("stopped", "error", "running", "adjusting")
        for button, amount_ms in self._delay_buttons:
            allowed = controls_ready and 0 <= snapshot.display_delay_ms + amount_ms <= 30_000
            button.config(state="normal" if allowed else "disabled")

        self._refresh_id = self.root.after(200, self.refresh_ui)

    def on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self._refresh_id is not None:
            self.root.after_cancel(self._refresh_id)
            self._refresh_id = None
        for widget in (self.url_entry, self.ndi_entry, self.minimum_resolution_combo, self.start_button):
            widget.config(state="disabled")
        for button, _amount in self._delay_buttons:
            button.config(state="disabled")
        self.controller.stop()
        self._wait_until_stopped()

    def _wait_until_stopped(self) -> None:
        if self.controller.shutdown_complete:
            self.root.destroy()
        else:
            self.root.after(100, self._wait_until_stopped)


def main() -> None:
    root = tk.Tk()
    RelayWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
