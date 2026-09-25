from __future__ import annotations

import unittest

from stream_url import extract_twitch_account_name


class ExtractTwitchAccountNameTests(unittest.TestCase):
    def test_extracts_channel_from_supported_urls(self) -> None:
        cases = (
            "https://www.twitch.tv/example",
            "https://www.twitch.tv/example/",
            "https://twitch.tv/example",
            "https://www.twitch.tv/example?foo=bar",
        )
        for url in cases:
            with self.subTest(url=url):
                self.assertEqual(extract_twitch_account_name(url), "example")

    def test_rejects_empty_or_non_channel_urls(self) -> None:
        cases = (
            ("https://www.twitch.tv/", "Invalid Twitch channel URL."),
            ("https://example.com/example", "Invalid Twitch channel URL."),
            ("https://www.twitch.tv/thisusernameistoolongforatwitchlogin", "Invalid Twitch channel URL."),
        )
        for url, message in cases:
            with self.subTest(url=url):
                with self.assertRaisesRegex(ValueError, message):
                    extract_twitch_account_name(url)


if __name__ == "__main__":
    unittest.main()
