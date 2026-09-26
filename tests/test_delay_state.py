import queue
import unittest
from unittest.mock import Mock, patch

from controller import StreamController
from stream_runtime import RuntimeEvent, SetDelayRequest
import test_runtime_lifecycle as lifecycle


class DelayStateTests(unittest.TestCase):
    def setUp(self):
        self.controller = StreamController()
        self.controller.change_delay_ms(5000)
        self.controller._state = 'running'
        self.controller._runtime = Mock(commands=queue.Queue())

    def event(self, kind, payload=None, request_id=None, **ids):
        self.controller._on_runtime_event(RuntimeEvent(
            ids.get('stream_id', 'primary'), ids.get('session_id', 0), kind, payload, request_id))

    def snapshot_event(self):
        self.event('runtime_snapshot', dict(delay_ms=0, adjusting_delay=False,
                                           video_buffer_ms=123, audio_buffer_ms=456))

    def test_pending_and_confirmed_display_survive_periodic_snapshots(self):
        self.controller.change_delay_ms(1000)
        command, request = self.controller._runtime.commands.get_nowait()
        self.assertEqual((command, request), ('set_delay', SetDelayRequest(1, 6000)))
        for _ in range(5):
            self.snapshot_event()
            self.assertEqual(self.controller.snapshot().display_delay_ms, 6000)
        self.event('delay_changed', {'delay_ms': 6000}, 1)
        for _ in range(5):
            self.snapshot_event()
            snap = self.controller.snapshot()
            self.assertEqual(snap.confirmed_delay_ms, 6000)
            self.assertIsNone(snap.requested_delay_ms)
            self.assertEqual(snap.display_delay_ms, 6000)

    def test_failure_restores_confirmed_and_reports_error(self):
        self.controller.change_delay_ms(1000)
        self.event('delay_change_failed', {'error': 'rejected'}, 1)
        snap = self.controller.snapshot()
        self.assertIsNone(snap.requested_delay_ms)
        self.assertEqual(snap.display_delay_ms, 5000)
        self.assertEqual(snap.error, 'rejected')

    def test_rapid_requests_ignore_stale_success_and_failure(self):
        for _ in range(3):
            self.controller.change_delay_ms(100)
        self.event('delay_changed', {'delay_ms': 5100}, 1)
        self.event('delay_change_failed', {'error': 'old failure'}, 2)
        self.snapshot_event()
        self.assertEqual(self.controller.snapshot().display_delay_ms, 5300)
        self.assertIsNone(self.controller.snapshot().error)
        self.event('delay_changed', {'delay_ms': 5300}, 3)
        self.event('delay_changed', {'delay_ms': 5200}, 2)
        self.event('delay_change_failed', {'error': 'old failure'}, 1)
        self.assertEqual(self.controller.snapshot().display_delay_ms, 5300)
        self.assertIsNone(self.controller.snapshot().error)

    def test_latest_failure_uses_last_accepted_value(self):
        self.controller.change_delay_ms(100)
        self.controller.change_delay_ms(100)
        self.event('delay_changed', {'delay_ms': 5100}, 1)
        self.event('delay_change_failed', {'error': 'busy'}, 2)
        self.assertEqual(self.controller.snapshot().display_delay_ms, 5100)
        self.controller.change_delay_ms(100)
        self.event('delay_changed', {'delay_ms': 5200}, 2)
        self.assertEqual(self.controller.snapshot().confirmed_delay_ms, 5100)

    def test_all_events_from_other_sessions_and_streams_are_ignored(self):
        self.controller.change_delay_ms(100)
        before = self.controller.snapshot()
        for ids in ({'session_id': -1}, {'stream_id': 'other'}):
            for kind, payload in (
                ('runtime_snapshot', dict(adjusting_delay=True, video_buffer_ms=999, audio_buffer_ms=999)),
                ('delay_changed', {'delay_ms': 9000}),
                ('delay_change_failed', {'error': 'old'}), ('running', None), ('error', 'old'),
                ('media_info', {'media': 'video', 'width': 99}),
            ):
                self.event(kind, payload, 1, **ids)
                self.assertEqual(self.controller.snapshot(), before)

    def test_start_increments_session_and_request_ids_remain_monotonic(self):
        with patch('controller.threading.Thread') as thread:
            thread.return_value.is_alive.return_value = False
            for expected in (1, 2):
                self.controller._state = 'stopped'
                self.controller.start('https://www.twitch.tv/foo')
                self.assertEqual(self.controller.session_id, expected)
                self.controller._state = 'running'
                self.controller.change_delay_ms(100)
                self.assertEqual(self.controller.latest_delay_request_id, expected)

    def test_two_streams_have_independent_state(self):
        other = StreamController('other')
        other.change_delay_ms(2000)
        before = other.snapshot()
        self.controller.change_delay_ms(1000)
        event = RuntimeEvent('primary', 0, 'delay_changed', {'delay_ms': 6000}, 1)
        self.controller._on_runtime_event(event)
        other._on_runtime_event(event)
        self.assertEqual(other.snapshot(), before)


class RuntimeDelayTests(unittest.TestCase):
    def make_runtime(self, notify):
        return lifecycle.RuntimeLifecycleTests().make_runtime(lifecycle.FakeGLib(), notify, delay=5000)

    def test_success_and_adjusting_are_separate_from_snapshot(self):
        events = []
        runtime = self.make_runtime(events.append)
        runtime.commands.put(('set_delay', SetDelayRequest(42, 2000)))
        runtime._drain_commands()
        self.assertEqual(events[0], RuntimeEvent('primary', 0, 'delay_changed',
                                               {'delay_ms': 2000, 'adjusting_delay': True}, 42))
        runtime._publish_snapshot()
        self.assertNotIn('delay_ms', events[-1].payload)
        self.assertTrue(events[-1].payload['adjusting_delay'])
        runtime.commands.put(('set_delay', SetDelayRequest(43, 1000)))
        runtime._drain_commands()
        self.assertIsNone(runtime._pending_delay_request)
        self.assertEqual(runtime.controller.delay_ms, 1000)
        runtime.GLib.tick()
        runtime.GLib.tick()
        self.assertTrue(any(e.event_type == 'delay_changed' and e.request_id == 43 for e in events))
        runtime.close()

    def test_increase_then_decreases_retarget_without_waiting_for_output(self):
        controller = StreamController()
        events = []
        def notify(event):
            events.append(event)
            controller._on_runtime_event(event)
        runtime = self.make_runtime(notify)
        controller.change_delay_ms(5000)
        controller._runtime = runtime
        controller._state = 'running'
        controller.change_delay_ms(1000)
        runtime._drain_commands()
        pad = runtime.elements['delay_sync'].get_static_pad.return_value
        old_output = pad.add_probe.call_args.args[1]
        old_poll = runtime.GLib.callbacks[runtime.controller._poll_id]
        for target in (5900, 5800, 5700):
            controller.change_delay_ms(-100)
            runtime._drain_commands()
            self.assertEqual(runtime.controller.delay_ms, target)
            self.assertEqual(controller.snapshot().confirmed_delay_ms, target)
            self.assertIsNone(controller.snapshot().requested_delay_ms)
        self.assertTrue(controller.snapshot().adjusting_delay)
        new_adjustment = runtime.controller.adjustment
        old_output(*lifecycle.output_sample(runtime))
        old_output(*lifecycle.output_sample(runtime))
        self.assertFalse(old_poll())
        self.assertIs(runtime.controller.adjustment, new_adjustment)
        on_output = pad.add_probe.call_args.args[1]
        on_output(*lifecycle.output_sample(runtime))
        runtime.GLib.tick()
        self.assertIsNotNone(runtime.controller.adjustment)
        on_output(*lifecycle.output_sample(runtime))
        runtime.GLib.tick()
        runtime._publish_snapshot()
        self.assertFalse(controller.snapshot().adjusting_delay)
        runtime.elements['output_valve'].set_property.assert_called_with('drop', False)
        self.assertEqual([e.payload['delay_ms'] for e in events if e.event_type == 'delay_changed'],
                         [6000, 5900, 5800, 5700])
        runtime.close()

    def test_decrease_to_increase_releases_valve_immediately(self):
        runtime = self.make_runtime(Mock())
        runtime.controller.set_delay_ms(2000)
        old_poll = runtime.GLib.callbacks[runtime.controller._poll_id]
        runtime.controller.set_delay_ms(4000)
        runtime.elements['output_valve'].set_property.assert_called_with('drop', False)
        self.assertEqual(runtime.controller.delay_ms, 4000)
        self.assertFalse(old_poll())
        self.assertEqual(runtime.controller.adjustment.new_delay_ms, 4000)
        self.assertEqual(len(runtime.GLib.callbacks), 3)
        runtime.close()

    def test_decrease_completion_uses_output_timing_despite_prefetched_queues(self):
        runtime = self.make_runtime(Mock())
        runtime.controller.set_delay_ms(10000)
        runtime.controller.set_delay_ms(3000)
        for name in ('video_delay_queue', 'audio_delay_queue'):
            runtime.elements[name].get_property.return_value = 8_000_000_000
        pad = runtime.elements['delay_sync'].get_static_pad.return_value
        callback = pad.add_probe.call_args.args[1]
        callback(*lifecycle.output_sample(runtime))
        callback(*lifecycle.output_sample(runtime))
        runtime.GLib.tick()
        self.assertIsNone(runtime.controller.adjustment)
        runtime.elements['output_valve'].set_property.assert_called_with('drop', False)
        runtime.close()

    def test_requests_before_first_drain_coalesce_to_latest(self):
        events = []
        runtime = self.make_runtime(events.append)
        for request_id, target in enumerate((6000, 5900, 5800), 1):
            runtime.commands.put(('set_delay', SetDelayRequest(request_id, target)))
        runtime._drain_commands()
        self.assertEqual(runtime.controller.delay_ms, 5800)
        self.assertEqual([e.request_id for e in events if e.event_type == 'delay_changed'], [3])
        runtime.close()

    def test_stale_output_timing_does_not_complete_adjustment(self):
        runtime = self.make_runtime(Mock())
        runtime.controller.set_delay_ms(3000)
        pad = runtime.elements['delay_sync'].get_static_pad.return_value
        callback = pad.add_probe.call_args.args[1]
        for _ in range(3):
            callback(*lifecycle.output_sample(runtime, delay_ms=5000))
        runtime.GLib.tick()
        self.assertIsNotNone(runtime.controller.adjustment)
        callback(*lifecycle.output_sample(runtime, delay_ms=3000))
        callback(*lifecycle.output_sample(runtime, delay_ms=3000))
        runtime.GLib.tick()
        self.assertIsNone(runtime.controller.adjustment)
        runtime.close()

    def test_output_measurement_handles_dts_segment_latency_and_buffer_lists(self):
        runtime = self.make_runtime(Mock())
        pad, info = lifecycle.output_sample(runtime)
        info.type = runtime.Gst.PadProbeType.BUFFER_LIST
        info.get_buffer_list.return_value.length.return_value = 1
        info.get_buffer_list.return_value.get.return_value = Mock(dts=12_000_000_000, pts=13_000_000_000)
        segment = pad.get_sticky_event.return_value.parse_segment.return_value
        segment.to_running_time.side_effect = lambda _format, timestamp: timestamp - 10_000_000_000
        runtime.elements['delay_sync'].get_current_running_time.return_value = 5_100_000_000
        self.assertEqual(runtime.controller._output_delay_ns(pad, info, 100_000_000), 3_000_000_000)
        runtime.close()

    def test_missing_timestamps_cannot_leave_output_muted_forever(self):
        runtime = self.make_runtime(Mock())
        with patch('stream_runtime.time.monotonic', return_value=0):
            runtime.controller.set_delay_ms(3000)
        pad, info = lifecycle.output_sample(runtime)
        info.get_buffer.return_value.pts = runtime.Gst.CLOCK_TIME_NONE
        callback = pad.add_probe.call_args.args[1]
        callback(pad, info)
        with patch('stream_runtime.time.monotonic', return_value=11):
            runtime.GLib.tick()
        self.assertIsNotNone(runtime.controller.adjustment)
        runtime.elements['output_valve'].set_property.assert_called_with('drop', False)
        callback(*lifecycle.output_sample(runtime))
        callback(*lifecycle.output_sample(runtime))
        runtime.GLib.tick()
        self.assertIsNone(runtime.controller.adjustment)
        runtime.close()

    def test_quit_discards_pending_target_during_adjustment(self):
        runtime = self.make_runtime(Mock())
        runtime.controller.set_delay_ms(6000)
        runtime.commands.put(('set_delay', SetDelayRequest(1, 4000)))
        runtime._drain_commands()
        runtime.commands.put(('quit', None))
        self.assertFalse(runtime._drain_commands())
        self.assertIsNone(runtime._pending_delay_request)
        self.assertEqual(runtime.controller.delay_ms, 4000)
        runtime.close()

    def test_stop_during_increase_removes_probe_and_timer(self):
        runtime = self.make_runtime(Mock())
        runtime.controller.set_delay_ms(6000)
        pad = runtime.elements['delay_sync'].get_static_pad.return_value
        on_output = pad.add_probe.call_args.args[1]
        runtime.close()
        runtime.close()
        pad.remove_probe.assert_called_once()
        self.assertEqual(runtime.GLib.callbacks, {})
        on_output(*lifecycle.output_sample(runtime))  # A late callback only touches its detached local event.
        on_output(*lifecycle.output_sample(runtime))
        self.assertIsNone(runtime.controller.adjustment)

    def test_property_failure_is_reported_and_delay_restored(self):
        events = []
        runtime = self.make_runtime(events.append)
        runtime.elements['delay_sync'].set_property.side_effect = [OSError('broken'), None]
        runtime.commands.put(('set_delay', SetDelayRequest(1, 6000)))
        runtime._drain_commands()
        self.assertEqual(events[-1].event_type, 'delay_change_failed')
        self.assertEqual(events[-1].payload['error'], 'broken')
        self.assertEqual(runtime.controller.delay_ms, 5000)
        runtime.close()
