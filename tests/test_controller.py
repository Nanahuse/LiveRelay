from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import controller


class ControllerTests(unittest.TestCase):
    def test_controller_rejects_empty_url_before_starting_worker(self) -> None:
        instance = controller.SingleStreamController()
        with patch("controller.threading.Thread") as thread_type:
            with self.assertRaisesRegex(ValueError, "Enter a Stream URL"):
                instance.start("  ")
        thread_type.assert_not_called()

    def test_each_start_passes_minimum_to_worker_selection(self) -> None:
        instance = controller.SingleStreamController()
        plugin = Mock()
        plugin.streams.return_value = {"1080p": Mock()}
        with (
            patch("controller.Streamlink"),
            patch("controller.resolve_stream", return_value=("youtube", plugin, "url", "Runner")),
            patch("controller.load_gst", return_value=(Mock(), Mock())),
            patch("controller.select_stream", side_effect=ValueError("selection stopped")) as select,
            patch("controller.build_pipeline") as build,
        ):
            for minimum in ("360p", "720p", None):
                with self.subTest(minimum=minimum):
                    kwargs = {} if minimum is None else {"minimum_resolution": minimum}
                    instance.start("https://www.youtube.com/live/example", "Runner", **kwargs)
                    instance._worker.join(timeout=5)
                    self.assertTrue(instance.shutdown_complete)
                    select.assert_called_with(plugin, plugin.streams.return_value, minimum or "480p")
                    self.assertEqual(instance.snapshot().state, "error")
            build.assert_not_called()

    def test_controller_accepts_manual_ndi_name_after_restart(self) -> None:
        instance = controller.SingleStreamController()
        with patch("controller.threading.Thread") as thread_type:
            thread_type.return_value.is_alive.return_value = False
            for name in ("Runner A", "Runner B"):
                instance._state = "stopped"
                instance.start("https://www.twitch.tv/foo", name)
                self.assertEqual(instance.snapshot().ndi_name, name)

    def test_no_qualifying_stream_does_not_open_or_build_pipeline(self) -> None:
        instance = controller.SingleStreamController()
        stream = Mock()
        plugin = Mock()
        plugin.streams.return_value = {"360p": stream}
        plugin.stream_weight.side_effect = lambda name: (int(name[:-1]), "pixels")
        with (
            patch("controller.Streamlink"),
            patch("controller.resolve_stream", return_value=("twitch", plugin, "url", "foo")),
            patch("controller.load_gst", return_value=(Mock(), Mock())),
            patch("controller.build_pipeline") as build,
        ):
            instance.start("https://www.twitch.tv/foo", minimum_resolution="720p")
            instance._worker.join(timeout=5)
        self.assertTrue(instance.shutdown_complete)
        self.assertEqual(instance.snapshot().error, "No pixel stream at 720p or higher is available.")
        stream.open.assert_not_called()
        build.assert_not_called()
