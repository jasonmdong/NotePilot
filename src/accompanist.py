"""
Left-hand scheduler with tempo tracking and right-hand sync.

How it works:
  - A background thread fires LEFT_HAND events according to a running tempo clock.
  - The clock is anchored to the last matched right-hand note (sync point).
  - Before playing any LH event at beat B, the scheduler checks whether B has
    reached the next expected RH beat. If so, it pauses and waits for the player.
  - When the player hits the RH note, the clock resyncs to that beat, tempo
    updates via moving average, and the scheduler resumes.
  - If the player jumps ahead, LH events that are now in the past are skipped.
"""

import time
import threading
from .synth import play_chord


class Accompanist:
    def __init__(self, left_hand: list, right_hand: list, initial_bps: float = 2.0):
        self._events      = sorted(left_hand,  key=lambda x: x[1])
        # Sorted unique beat positions of every right-hand note (sync points).
        self._rh_beats    = sorted({event[1] for event in right_hand})

        self._bps         = initial_bps
        self._sync_beat   = 0.0
        self._sync_time   = None          # None = waiting for first RH note
        self._next_sync   = self._rh_beats[0] if self._rh_beats else float('inf')

        self._lh_idx      = 0
        self._lock        = threading.Lock()
        self._resume      = threading.Event()
        self._running     = False
        self._thread      = None

    # ── Public API ────────────────────────────────────────────────────────

    def start(self):
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self._resume.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def on_rh_note(self, beat: float, bps: float):
        """Call this whenever the player matches a right-hand note."""
        with self._lock:
            self._bps       = bps
            self._sync_beat = beat
            self._sync_time = time.perf_counter()

            # Next sync point is the first RH beat strictly after this one.
            self._next_sync = next(
                (b for b in self._rh_beats if b > beat + 0.01),
                float('inf')
            )

            # Skip LH events that are now in the past (player jumped ahead).
            while (self._lh_idx < len(self._events)
                   and self._events[self._lh_idx][1] < beat - 0.05):
                self._lh_idx += 1

        self._resume.set()

    # ── Internal ──────────────────────────────────────────────────────────

    def _current_beat(self) -> float:
        if self._sync_time is None:
            return 0.0
        return self._sync_beat + (time.perf_counter() - self._sync_time) * self._bps

    def _loop(self):
        while self._running:
            # ── Wait for the first RH note before doing anything ──
            with self._lock:
                started = self._sync_time is not None
            if not started:
                self._resume.wait(timeout=0.1)
                self._resume.clear()
                continue

            # ── All LH events played → done ──
            with self._lock:
                if self._lh_idx >= len(self._events):
                    break
                pitches, beat = self._events[self._lh_idx][:2]
                next_sync     = self._next_sync

            # ── Pause before the next RH sync point ──
            if beat >= next_sync - 0.01:
                self._resume.wait(timeout=5.0)
                self._resume.clear()
                continue

            # ── Fire when the clock reaches this event's beat ──
            current = self._current_beat()
            if current >= beat - 0.003:
                play_chord(pitches)
                with self._lock:
                    self._lh_idx += 1
            else:
                with self._lock:
                    bps = self._bps
                wait = max(0.0, (beat - current) / bps * 0.85)
                time.sleep(min(wait, 0.05))
