"""
Plays the left-hand chord that corresponds to the current beat position.
When the player matches a right-hand note, call play_for_beat(beat) and
the left-hand chord fires immediately — no scheduling, no latency.
"""

from score import LEFT_HAND
from synth import play_chord

# Build a direct lookup: beat_position → list of pitches
_left_hand_map: dict[float, list[int]] = {beat: pitches for pitches, beat in LEFT_HAND}


class Accompanist:
    def play_for_beat(self, beat: float):
        """Play the left-hand chord for this beat right now."""
        pitches = _left_hand_map.get(beat)
        if pitches:
            play_chord(pitches)

    # ── stubs kept so main() doesn't need changes ──
    def start(self): pass
    def stop(self):  pass
