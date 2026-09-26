import unittest
from unittest.mock import Mock

from controller import SingleStreamController
from stream_runtime import Runtime


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
        return Runtime(Mock(), glib, Mock(), elements, delay, notify)

    def test_restart_does_not_publish_previous_delay(self):
        glib = FakeGLib()
        controller = SingleStreamController()
        published = []

        def notify(event, value):
            controller._on_runtime_event(event, value)
            if event == "runtime_snapshot":
                published.append(controller.snapshot().target_delay_ms)

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
        glib.tick()
        self.assertEqual(len(glib.callbacks), 2)
        runtime.close()
        self.assertEqual(glib.callbacks, {})
