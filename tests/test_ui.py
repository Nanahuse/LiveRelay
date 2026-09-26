import tkinter as tk
import unittest
from unittest.mock import patch

from ui import RelayWindow
from stream_runtime import RuntimeEvent
from unittest.mock import Mock


class MinimumResolutionUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()
        self.window = RelayWindow(self.root)

    def tearDown(self) -> None:
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()

    def test_default_choices_and_start_value(self) -> None:
        self.assertEqual(self.window.minimum_resolution_var.get(), "480p")
        self.assertEqual(
            self.window.minimum_resolution_combo["values"],
            ("144p", "240p", "360p", "480p", "720p", "1080p"),
        )
        self.window.minimum_resolution_var.set("720p")
        self.window.url_var.set("https://www.twitch.tv/foo")
        with patch.object(self.window.controller, "start") as start:
            self.window.on_start()
        start.assert_called_once_with("https://www.twitch.tv/foo", "", "720p")
        second_window = RelayWindow(self.root)
        self.assertEqual(second_window.minimum_resolution_var.get(), "480p")

    def test_editable_only_when_stopped_or_error(self) -> None:
        for state in ("starting", "running", "adjusting", "stopping", "stopped", "error"):
            with self.subTest(state=state):
                self.window.controller._state = state
                self.window.refresh_ui()
                expected = "readonly" if state in ("stopped", "error") else "disabled"
                self.assertEqual(str(self.window.minimum_resolution_combo["state"]), expected)

    def test_delay_clicks_keep_one_refresh_timer(self) -> None:
        for _ in range(5):
            self.window.on_delay(100)
        self.assertEqual(self.window.delay_var.get(), "0.5 s")
        self.assertEqual(len(self.root.tk.call("after", "info")), 1)
        with patch.object(self.root, "destroy"):
            self.window.on_close()
        self.assertEqual(len(self.root.tk.call("after", "info")), 0)

    def test_pending_delay_stays_visible_and_failure_is_shown(self) -> None:
        controller = self.window.controller
        controller.change_delay_ms(5000)
        controller._state = "running"
        controller._runtime = Mock()
        self.window.on_delay(1000)
        self.assertEqual(self.window.delay_var.get(), "6.0 s")
        for button, amount in self.window._delay_buttons:
            expected = 'normal' if 0 <= controller.snapshot().display_delay_ms + amount <= 30000 else 'disabled'
            self.assertEqual(str(button['state']), expected)
        for _ in range(3):
            controller._on_runtime_event(RuntimeEvent("primary", 0, "runtime_snapshot", {
                "adjusting_delay": False, "video_buffer_ms": 0, "audio_buffer_ms": 0,
            }))
            self.window.refresh_ui()
            self.assertEqual(self.window.delay_var.get(), "6.0 s")
        controller._on_runtime_event(RuntimeEvent(
            "primary", 0, "delay_change_failed", {"error": "Delay rejected"}, 1,
        ))
        self.window.refresh_ui()
        self.assertEqual(self.window.delay_var.get(), "5.0 s")
        self.assertEqual(self.window.error_var.get(), "Delay rejected")
        self.assertEqual(len(self.root.tk.call("after", "info")), 1)

    def test_delay_controls_accept_input_during_increase(self) -> None:
        controller = self.window.controller
        controller._state = 'running'
        controller._runtime = Mock()
        self.window.on_delay(1000)
        controller._on_runtime_event(RuntimeEvent('primary', 0, 'delay_changed', {
            'delay_ms': 1000, 'adjusting_delay': True,
        }, 1))
        self.window.refresh_ui()
        for button, amount in self.window._delay_buttons:
            expected = 'normal' if 0 <= controller.snapshot().display_delay_ms + amount <= 30000 else 'disabled'
            self.assertEqual(str(button['state']), expected)
        self.window.on_delay(-100)
        self.assertEqual(self.window.delay_var.get(), '0.9 s')
        self.assertEqual(controller.snapshot().requested_delay_ms, 900)
        controller._on_runtime_event(RuntimeEvent('primary', 0, 'runtime_snapshot', {
            'adjusting_delay': False, 'video_buffer_ms': 1000, 'audio_buffer_ms': 1000,
        }))
        self.window.refresh_ui()
        for button, amount in self.window._delay_buttons:
            if 0 <= 900 + amount <= 30000:
                self.assertEqual(str(button['state']), 'normal')
