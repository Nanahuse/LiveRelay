# Delay state and Runtime events

`StreamController(stream_id="primary")` owns the state of one stream. The current
UI owns one controller and one refresh timer. A future manager can map stream IDs
to controllers without introducing shared Delay state. `SingleStreamController`
remains an alias for existing callers.

The display uses `requested_delay_ms` while a request is outstanding, otherwise
`confirmed_delay_ms`. While stopped, controls configure the initial value for the
next Runtime. During playback, only `delay_changed` confirms a new setting.
`runtime_snapshot` carries buffer levels and adjustment progress, never Delay.

Each start increments `session_id`. Runtime notifications and media callbacks
carry stream and session IDs; mismatches are ignored before processing payloads.
Delay requests have monotonically increasing IDs. An accepted intermediate
request updates the confirmed fallback without clearing a newer requested value.
Only the latest response clears that value. Responses older than a confirmed or
completed request are ignored. Failures appear in the existing UI error field.

Delay buttons remain usable during adjustment, within the 0-30 second bounds.
Every click updates the requested target immediately. At each 25 ms command tick,
Runtime coalesces queued requests to the latest target and applies it even if an
adjustment is active. Superseded requests receive a failure response that cannot
clear a newer request or show a stale UI error. Quit takes priority.

Each target replaces the old adjustment observer and timer. A generation number
makes old completion callbacks harmless. Reversing to an increase immediately
releases the preceding decrease's output valve. Completion uses measured output
timing, not queue depth: prefetched input can remain in the queues even when
output is already synchronized. This retains clocksync and the NDI pipeline.

A nonblocking source pad probe maps each buffer's DTS (or PTS when DTS is absent)
through its TIME segment. It compares pipeline running time minus that time and
upstream live latency against the requested offset. Two consecutive samples
within 50 ms confirm adjustment completion. Buffer lists use their first buffer,
as clocksync does. Stop and retargeting remove the probe and poll. Acceptance is
acknowledged immediately and remains separate from adjustment progress.

If timing cannot be confirmed within 10 seconds, the valve is reopened to avoid
permanently muting output; adjustment monitoring continues without falsely
claiming completion. A diagnostic warning records this recovery.

Limitation: clocksync's ts-offset setter does not cancel an already scheduled
clock wait. The target changes on the next command tick, but one in-flight
buffer can still wait until its previous deadline. Increasing Delay also needs
time to accumulate data. This implementation does not reset the pipeline or
replace clocksync to interrupt that wait
([GStreamer source](https://raw.githubusercontent.com/GStreamer/gstreamer/1.28/subprojects/gstreamer/plugins/elements/gstclocksync.c)).

Property-setting failures attempt to restore the prior setting and release the
output valve before reporting failure. GLib source removal, bus disconnection,
notification detachment, and adjustment cleanup remain in place.

Set `TWITCH_TO_NDI_DIAGNOSTICS=1` to print request/result and stale-event logs
with stream, session, request, requested and confirmed values. These entries
are also available through Python DEBUG logging for the `controller` logger.

Run the regression tests:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`scripts/check_delay_output.py` checks the bundled real GStreamer with 800 ms of
prefetched input, measuring output buffer times at fakesink. Targets 800, 300,
100, 200, and 0 ms (including rapid reversals) were measured at approximately
801, 301, 101, 201, and 1 ms. Queues could remain larger than the target while
output correctly resumed. This does not cover live Streamlink or NDI.

```powershell
.venv\Scripts\python.exe scripts/check_delay_output.py
```
