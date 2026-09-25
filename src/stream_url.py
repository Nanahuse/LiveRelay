from __future__ import annotations

import re
from urllib.parse import unquote, urlparse


_TWITCH_HOSTS = {"twitch.tv", "www.twitch.tv"}
_USER_ID_PATTERN = re.compile(r"[A-Za-z0-9_]+\Z")


def extract_twitch_account_name(url: str) -> str:
    """Return the account login from a Twitch channel URL."""
    if not url or not url.strip():
        raise ValueError("Invalid Twitch channel URL.")

    try:
        parsed = urlparse(url.strip())
        host = parsed.hostname
    except ValueError:
        host = None
        parsed = None

    if (
        parsed is None
        or parsed.scheme.casefold() not in {"http", "https"}
        or host is None
        or host.casefold() not in _TWITCH_HOSTS
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("Invalid Twitch channel URL.")

    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        raise ValueError("Invalid Twitch channel URL.")

    account_name = unquote(path_parts[0])
    if len(account_name) > 25 or not _USER_ID_PATTERN.fullmatch(account_name):
        raise ValueError("Invalid Twitch channel URL.")
    return account_name
