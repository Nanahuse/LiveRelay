"""Exercise real clocksync with input prebuffering and measure output delay."""
import sys
import time
from pathlib import Path
from statistics import median

from private_runtime import configure_private_environment
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'src'))
configure_private_environment(root)
from stream_runtime import load_gst, Runtime
from controller import StreamController

Gst, GLib = load_gst()
Gst.init(None)
pipeline = Gst.parse_launch('appsrc name=source is-live=true format=time ! queue name=video max-size-buffers=0 max-size-bytes=0 max-size-time=35000000000 ! clocksync name=sync ! valve name=valve ! fakesink name=sink sync=false signal-handoffs=true')
outputs = []
def handoff(_sink, buffer, _pad):
    outputs.append((time.monotonic(), (pipeline.get_current_running_time() - buffer.pts) / 1e6))
pipeline.get_by_name('sink').connect('handoff', handoff)
controller = StreamController()
runtime = Runtime(Gst, GLib, pipeline, {
    'appsrc': pipeline.get_by_name('source'), 'delay_sync': pipeline.get_by_name('sync'),
    'output_valve': pipeline.get_by_name('valve'), 'video_delay_queue': pipeline.get_by_name('video'),
    'audio_delay_queue': pipeline.get_by_name('video'),
}, notify=controller._on_runtime_event)
controller._runtime = runtime
controller._state = 'running'
context = GLib.MainContext.default()
pts = 0

def wait_until(predicate, timeout=5):
    global pts
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # Keep 800ms of prefetched input, independently of the output Delay.
        running = pipeline.get_current_running_time()
        while pts < running + 800_000_000:
            buffer = Gst.Buffer.new_allocate(None, 32, None)
            buffer.pts = pts
            buffer.duration = 33_333_333
            pts += buffer.duration
            pipeline.get_by_name('source').emit('push-buffer', buffer)
        while context.pending():
            context.iteration(False)
        if predicate():
            return
        time.sleep(.005)
    queued = pipeline.get_by_name('video').get_property('current-level-time') / 1e6
    raise AssertionError(f'Timeout: adjusting={runtime.controller.adjustment}, queue={queued:.0f}ms, output_count={len(outputs)}')

def target(value):
    controller.change_delay_ms(value - controller.snapshot().display_delay_ms)
    wait_until(lambda: runtime.controller.delay_ms == value, .2)

def check_output(value):
    wait_until(lambda: runtime.controller.adjustment is None)
    start = len(outputs)
    wait_until(lambda: len(outputs) >= start + 10)
    measured = median(delay for _, delay in outputs[-10:])
    assert abs(measured - value) < 100, (value, measured)
    assert not pipeline.get_by_name('valve').get_property('drop')
    queued = pipeline.get_by_name('video').get_property('current-level-time') / 1e6
    print(f'PASS target={value}ms measured={measured:.1f}ms queue={queued:.1f}ms with prefetched input')

try:
    pipeline.set_state(Gst.State.PLAYING)
    wait_until(lambda: len(outputs) >= 5)
    target(800)
    check_output(800)
    target(300)
    check_output(300)
    for values in ((1200, 900, 600, 100), (800, 0, 600, 200), (1000, 300, 500, 0)):
        for value in values:
            target(value)
            until = time.monotonic() + .08
            wait_until(lambda: time.monotonic() >= until)
        check_output(values[-1])
finally:
    runtime.close()
    pipeline.set_state(Gst.State.NULL)
