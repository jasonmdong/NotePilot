"""
Tracks the player's position in the score and estimates current tempo.

Strategy (Option A — event-driven):
  - Maintain an ordered list of expected right-hand pitches.
  - When a new MIDI note arrives, try to match it to the next expected note
    (with a small pitch-tolerance window for transpositions or octave errors).
  - Record real-time timestamps for each matched note.
  - Estimate beats-per-second from recent inter-note timing.
"""

import time
from collections import deque

# How many recent inter-note intervals to average for tempo estimation.
TEMPO_WINDOW = 4

class ScoreTracker:
    def __init__(self, right_hand: list, initial_bps: float = 2.0):
        self.score = right_hand          # [(pitch, beat), ...]
        self.position = 0                # index into self.score for next expected note
        self.timestamps = deque()        # (real_time, beat) for recent matches
        self._default_bps = initial_bps

    def on_note(self, pitch: int) -> float | None:
        """
        Call this when the player plays a note.
        Returns the current beat position if matched, or None if unrecognized.
        """
        matched_idx = self._find_match(pitch)
        if matched_idx is None:
            return None

        self.position = matched_idx + 1
        beat = self.score[matched_idx][1]
        now = time.perf_counter()

        self.timestamps.append((now, beat))
        if len(self.timestamps) > TEMPO_WINDOW + 1:
            self.timestamps.popleft()

        return beat

    def current_beat_position(self) -> float:
        """Best estimate of the current beat, interpolated from last match."""
        if not self.timestamps:
            return 0.0
        last_time, last_beat = self.timestamps[-1]
        elapsed = time.perf_counter() - last_time
        return last_beat + elapsed * self.beats_per_second()

    def beats_per_second(self) -> float:
        """Estimate BPS from recent matched notes."""
        ts = list(self.timestamps)
        if len(ts) < 2:
            return self._default_bps

        # Compute BPS from each consecutive pair and average.
        rates = []
        for i in range(1, len(ts)):
            dt = ts[i][0] - ts[i-1][0]
            db = ts[i][1] - ts[i-1][1]
            if dt > 0 and db > 0:
                rates.append(db / dt)

        return sum(rates) / len(rates) if rates else self._default_bps

    def seconds_until_beat(self, target_beat: float) -> float:
        """How many seconds from now until a given beat position."""
        current = self.current_beat_position()
        remaining_beats = target_beat - current
        return remaining_beats / self.beats_per_second()

    def is_finished(self) -> bool:
        return self.position >= len(self.score)

    def _find_match(self, pitch: int) -> int | None:
        """
        Match only the next expected score note.
        Returns the matched index in self.score, or None.
        """
        if self.position >= len(self.score):
            return None
        expected_pitch = self.score[self.position][0]
        return self.position if pitch == expected_pitch else None
