import unittest
from unittest.mock import patch

from streamlink import Streamlink
from streamlink.plugins.twitch import Twitch, TwitchHLSStream
from streamlink.plugins.youtube import YouTube

from stream_source import resolve_stream


class LowLatencyTests(unittest.TestCase):
    def test_twitch_enables_low_latency_before_stream_discovery(self):
        for initial, expected in ((3, 2), (5, 2), (1, 1)):
            with self.subTest(initial=initial):
                session = Streamlink()
                session.set_option('hls-live-edge', initial)
                with patch.object(session, 'resolve_url', return_value=(
                    'twitch', Twitch, 'https://www.twitch.tv/example',
                )):
                    provider, plugin, _, name = resolve_stream(session, 'https://www.twitch.tv/example')
                self.assertEqual((provider, name), ('twitch', 'example'))
                self.assertTrue(plugin.get_option('low-latency'))
                self.assertEqual(session.get_option('hls-live-edge'), expected)
                self.assertTrue(session.get_option('hls-segment-stream-data'))
                # Keep the real Twitch discovery implementation; intercept only
                # playlist I/O to inspect the options used to create HLS streams.
                with patch.object(TwitchHLSStream, 'parse_variant_playlist', return_value={}) as parse:
                    plugin._get_hls_streams('https://example.invalid/live.m3u8', [])
                self.assertTrue(parse.call_args.kwargs['low_latency'])

    def test_youtube_keeps_default_options_in_its_own_session(self):
        twitch_session = Streamlink()
        with patch.object(twitch_session, 'resolve_url', return_value=(
            'twitch', Twitch, 'https://www.twitch.tv/example',
        )):
            resolve_stream(twitch_session, 'https://www.twitch.tv/example')
        session = Streamlink()
        before = (session.get_option('hls-live-edge'), session.get_option('hls-segment-stream-data'))
        with patch.object(session, 'resolve_url', return_value=(
            'youtube', YouTube, 'https://www.youtube.com/watch?v=abcdefghijk',
        )):
            _, plugin, _, _ = resolve_stream(session, 'https://www.youtube.com/watch?v=abcdefghijk', 'Runner')
        self.assertFalse(plugin.get_option('low-latency'))
        self.assertEqual((session.get_option('hls-live-edge'), session.get_option('hls-segment-stream-data')), before)
