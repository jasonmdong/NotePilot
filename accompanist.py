"""
Schedules and sends left-hand MIDI events based on the tracker's position.

Design:
  - Maintains a queue of upcoming left-hand events.
  - A background thread fires notes at the right real-time moment.
  - After each right-hand note match, we recompute the schedule for the
    next few beats so the accompaniment stays in sync.
"""

import time
import threading
import rtmidi
from score import LEFT_HAND

NOTE_ON  = 0x90
NOTE_OFF = 0x80
CHANNEL  = 0          # MIDI channel 0 (channel 1 in 1-indexed terms)
VELOCITY = 64         # Default velocity for left-hand notes
NOTE_DURATION = 0.18  # Seconds to hold each left-hand note

# How many beats ahead to schedule at a time.
SCHEDULE_HORIZON = 4.0


class Accompanist:
    def __init__(self, midi_out: rtmidi.MidiOut):
        self.midi_out = midi_out
        self._lock = threading.Lock()
        self._pending: list[tuple[float, list[int]]] = []  # (fire_at_realtime, pitches)
        self._last_scheduled_beat = -1.0
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._fire_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def update(self, tracker):
        """
        Call this after every right-hand note match.
        Re-schedules upcoming left-hand events within SCHEDULE_HORIZON beats.
        """
        current_beat = tracker.current_beat_position()
        bps = tracker.beats_per_second()

        schedule_up_to = current_beat + SCHEDULE_HORIZON

        new_events = []
        for (pitches, beat) in LEFT_HAND:
            if beat <= self._last_scheduled_beat:
                continue
            if beat > schedule_up_to:
                break
            fire_at = time.perf_counter() + tracker.seconds_until_beat(beat)
            if fire_at > time.perf_counter() - 0.05:  # skip events in the past
                new_events.append((fire_at, pitches))
                self._last_scheduled_beat = beat

        with self._lock:
            # Remove stale events that are now in the past.
            now = time.perf_counter()
            self._pending = [(t, p) for (t, p) in self._pending if t > now - 0.05]
            self._pending.extend(new_events)
            self._pending.sort(key=lambda x: x[0])

    def _fire_loop(self):
        """Background thread: fires notes when their scheduled time arrives."""
        while self._running:
            now = time.perf_counter()
            to_fire = []

            with self._lock:
                remaining = []
                for event in self._pending:
                    fire_at, pitches = event
                    if fire_at <= now + 0.002:  # 2ms early threshold
                        to_fire.append(pitches)
                    else:
                        remaining.append(event)
                self._pending = remaining

            for pitches in to_fire:
                self._play_chord(pitches)

            time.sleep(0.001)  # 1ms polling loop

    def _play_chord(self, pitches: list[int]):
        for pitch in pitches:
            self.midi_out.send_message([NOTE_ON | CHANNEL, pitch, VELOCITY])
        # Schedule note-off in a separate thread to avoid blocking the fire loop.
        def note_off():
            time.sleep(NOTE_DURATION)
            for pitch in pitches:
                self.midi_out.send_message([NOTE_OFF | CHANNEL, pitch, 0])
        threading.Thread(target=note_off, daemon=True).start()
