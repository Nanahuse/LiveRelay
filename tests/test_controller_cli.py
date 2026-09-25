from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

import controller
import main


class _IdleThread:
    def __init__(self, **_kwargs: object) -> None:
        pass

    def start(self) -> None:
        pass

    def is_alive(self) -> bool:
        return False


class ControllerAndCliTests(unittest.TestCase):
    def test_controller_accepts_manual_ndi_name_and_recalculates_after_restart(self) -> None:
        instance = controller.SingleStreamController()
        with patch("controller.threading.Thread", _IdleThread):
            instance.start("https://www.twitch.tv/foo", "Runner A")
            self.assertEqual(instance.snapshot().ndi_name, "Runner A")

            # Simulate completion of the first worker before a second start.
            with instance._lock:
                instance._state = "stopped"
                instance._worker = None
            instance.start("https://www.twitch.tv/bar", "Runner B")
            self.assertEqual(instance.snapshot().ndi_name, "Runner B")

    def test_controller_rejects_empty_url_before_starting_worker(self) -> None:
        instance = controller.SingleStreamController()
        with patch("controller.threading.Thread") as thread_type:
            with self.assertRaisesRegex(ValueError, "Enter a Stream URL"):
                instance.start("  ")
        thread_type.assert_not_called()

    def test_cli_accepts_url_without_manual_ndi_name(self) -> None:
        with (
            patch.object(sys, "argv", ["liverelay-cli", "https://www.twitch.tv/example"]),
            patch.object(main, "run", return_value=0) as run,
        ):
            with self.assertRaises(SystemExit) as result:
                main.main()
        self.assertEqual(result.exception.code, 0)
        run.assert_called_once_with("https://www.twitch.tv/example", "")

    def test_cli_accepts_manual_ndi_name(self) -> None:
        with (
            patch.object(
                sys,
                "argv",
                ["liverelay-cli", "https://www.twitch.tv/example", "--ndi-name", "manual"],
            ),
            patch.object(main, "run") as run,
        ):
            with self.assertRaises(SystemExit) as result:
                main.main()
        self.assertEqual(result.exception.code, 0)
        run.assert_called_once_with("https://www.twitch.tv/example", "manual")

    def test_invalid_url_fails_before_loading_gstreamer(self) -> None:
        with patch.object(main, "load_gst") as load_gst:
            self.assertEqual(main.run("https://www.twitch.tv/"), 1)
        load_gst.assert_not_called()


if __name__ == "__main__":
    unittest.main()
