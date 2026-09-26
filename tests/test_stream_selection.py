import unittest

from streamlink.plugins.twitch import Twitch
from streamlink.plugins.youtube import YouTube
from streamlink.plugin import Plugin

from stream_source import select_stream


class SelectStreamTests(unittest.TestCase):
    def test_minimum_pixel_weight_for_both_providers(self) -> None:
        cases = (
            (None, ("160p", "360p", "480p", "720p60", "1080p60"), "480p"),
            ("360p", ("160p", "360p", "480p", "720p60"), "360p"),
            ("480p", ("160p", "360p", "480p", "720p60"), "480p"),
            ("720p", ("480p", "720p", "720p60", "1080p"), "720p"),
            ("720p", ("360p", "480p", "1080p60"), "1080p60"),
            ("720p", ("480p", "720p60", "1080p60"), "720p60"),
            ("480p", ("480p60", "480p", "720p"), "480p"),
            ("144p", ("160p", "360p"), "160p"),
            ("240p", ("160p", "360p"), "360p"),
            ("1080p", ("720p60", "1080p60"), "1080p60"),
        )
        for plugin in (Plugin, Twitch, YouTube):
            for minimum, names, expected in cases:
                with self.subTest(provider=plugin.__name__, minimum=minimum, names=names):
                    # YouTube classifies FPS-suffixed names as high_frame_rate,
                    # not pixels. Use its pixel names for the shared rule cases.
                    if plugin is YouTube:
                        names = tuple(name.removesuffix("60") for name in names)
                        expected = expected.removesuffix("60")
                    streams = {name: object() for name in (*names, "audio_only", "audio", "best", "worst")}
                    result = select_stream(plugin, streams) if minimum is None else select_stream(plugin, streams, minimum)
                    self.assertEqual(result, (expected, streams[expected]))

    def test_excludes_youtube_non_pixel_high_frame_rate_group(self) -> None:
        streams = {"720p60": object(), "1080p": object()}
        self.assertEqual(select_stream(YouTube, streams, "720p"), ("1080p", streams["1080p"]))

    def test_no_qualifying_pixel_stream_reports_minimum(self) -> None:
        for plugin in (Twitch, YouTube):
            for minimum in ("480p", "720p", "1080p"):
                for names in ((), ("360p",), ("audio_only", "audio", "best", "worst")):
                    with self.subTest(provider=plugin.__name__, minimum=minimum, names=names):
                        with self.assertRaises(ValueError) as error:
                            select_stream(plugin, dict.fromkeys(names, object()), minimum)
                        self.assertEqual(str(error.exception), f"No pixel stream at {minimum} or higher is available.")
