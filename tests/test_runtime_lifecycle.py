import unittest
from unittest.mock import Mock

from controller import SingleStreamController
from stream_runtime import Runtime


def output_sample(runtime, delay_ms=None):
    sync = runtime.elements['delay_sync']
    delay_ms = runtime.controller.delay_ms if delay_ms is None else delay_ms
    sync.get_current_running_time.return_value = 1_000_000_000 + delay_ms * 1_000_000
    pad = sync.get_static_pad.return_value
    segment = pad.get_sticky_event.return_value.parse_segment.return_value
    segment.format = runtime.Gst.Format.TIME
    segment.to_running_time.side_effect = lambda _format, timestamp: timestamp
    info = Mock(type=runtime.Gst.PadProbeType.BUFFER)
    info.get_buffer.return_value = Mock(dts=runtime.Gst.CLOCK_TIME_NONE, pts=1_000_000_000)
    return pad, info


class FakeGLib:
    def __init__(self):
        self.callbacks = {}
        self.next_id = 0
        self.MainLoop = Mock

    def timeout_add(self, interval, callback):
        self.next_id += 1
        self.callbacks[self.next_id] = callback
        return self.next_id

    def source_remove(self, source_id):
        del self.callbacks[source_id]

    def tick(self):
        for source_id, callback in list(self.callbacks.items()):
            if not callback():
                self.callbacks.pop(source_id, None)


class RuntimeLifecycleTests(unittest.TestCase):
    def make_runtime(self, glib, notify, delay=0):
        elements = {
            name: Mock() for name in (
                "appsrc", "video_delay_queue", "audio_delay_queue", "delay_sync", "output_valve",
            )
        }
        for element in elements.values():
            element.get_property.return_value = 0
        gst = Mock()
        gst.PadProbeType.BUFFER = 1
        gst.PadProbeType.BUFFER_LIST = 2
        gst.CLOCK_TIME_NONE = 2**64 - 1
        elements['delay_sync'].get_static_pad.return_value.peer_query.return_value = False
        return Runtime(gst, glib, Mock(), elements, delay, notify)

    def test_restart_does_not_publish_previous_delay(self):
        glib = FakeGLib()
        controller = SingleStreamController()
        published = []

        def notify(event):
            controller._on_runtime_event(event)
            if event.event_type == "runtime_snapshot":
                published.append(controller.snapshot().display_delay_ms)

        old = self.make_runtime(glib, notify)
        old.commands.put(("quit", None))
        glib.tick()
        old.close()
        self.assertEqual(glib.callbacks, {})
        old._bus.disconnect.assert_called_once()
        old._bus.remove_signal_watch.assert_called_once()

        current = self.make_runtime(glib, notify)
        controller._runtime = current
        controller._state = "running"
        controller.change_delay_ms(1000)
        published.clear()
        for _ in range(4):
            glib.tick()
        self.assertEqual(published, [1000] * 4)
        current.close()
        current.close()
        self.assertEqual(glib.callbacks, {})

    def test_close_removes_active_delay_adjustment(self):
        glib = FakeGLib()
        runtime = self.make_runtime(glib, Mock(), delay=5000)
        runtime.controller.set_delay_ms(1000)
        self.assertEqual(len(glib.callbacks), 3)
        runtime.close()
        self.assertEqual(glib.callbacks, {})

    def test_close_after_adjustment_completes(self):
        glib = FakeGLib()
        runtime = self.make_runtime(glib, Mock(), delay=5000)
        runtime.controller.set_delay_ms(1000)
        callback = runtime.elements["delay_sync"].get_static_pad.return_value.add_probe.call_args.args[1]
        callback(*output_sample(runtime))
        callback(*output_sample(runtime))
        glib.tick()
        self.assertEqual(len(glib.callbacks), 2)
        runtime.close()
        self.assertEqual(glib.callbacks, {})
