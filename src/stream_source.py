from __future__ import annotations

from typing import Any

from streamlink.exceptions import NoPluginError

from stream_url import extract_twitch_account_name


def select_stream(
    plugin: Any, streams: dict[str, Any], minimum_resolution: str = "480p",
) -> tuple[str, Any]:
    threshold, _ = plugin.stream_weight(minimum_resolution)
    candidates = []
    for name, stream in streams.items():
        weight, group = plugin.stream_weight(name)
        if group == "pixels" and weight >= threshold:
            candidates.append((weight, name, stream))
    if not candidates:
        raise ValueError(f"No pixel stream at {minimum_resolution} or higher is available.")
    _, name, stream = min(candidates, key=lambda candidate: (candidate[0], candidate[1]))
    return name, stream


def resolve_stream(session: Any, url: str, ndi_name: str = "") -> tuple[str, Any, str, str]:
    """Resolve a supported live provider and choose its effective NDI name."""
    url = url.strip()
    if not url:
        raise ValueError("Enter a Stream URL.")

    try:
        plugin_name, plugin_class, resolved_url = session.resolve_url(url)
    except NoPluginError as error:
        raise ValueError("This streaming service is not supported.") from error
    provider = str(plugin_name).casefold()
    if provider not in {"twitch", "youtube"}:
        raise ValueError("This streaming service is not supported.")

    ndi_name = ndi_name.strip()
    if provider == "youtube" and not ndi_name:
        raise ValueError("Enter an NDI Source Name for YouTube.")
    if provider == "twitch" and not ndi_name:
        for candidate in (resolved_url, url):
            try:
                ndi_name = extract_twitch_account_name(candidate)
                break
            except ValueError:
                pass
        if not ndi_name:
            raise ValueError(
                "Could not determine the Twitch account name. "
                "Enter an NDI Source Name manually."
            )

    options = {"low-latency": True} if provider == "twitch" else {}
    plugin = plugin_class(session, resolved_url, options=options)
    return provider, plugin, resolved_url, ndi_name
