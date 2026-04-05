"""
Minimal software synthesizer with a persistent mixing stream.
All voices are mixed together in one OutputStream callback — no conflicting
sd.play() calls, no audio glitches.
"""

import threading
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 44100
BLOCK_SIZE  = 256   # ~5.8 ms latency


def midi_to_hz(pitch: int) -> float:
    return 440.0 * (2.0 ** ((pitch - 69) / 12.0))


def _render_note(pitch: int, velocity: int, duration: float = 1.2) -> np.ndarray:
    hz  = midi_to_hz(pitch)
    n   = int(SAMPLE_RATE * duration)
    t   = np.linspace(0, duration, n, endpoint=False)

    wave = (
        np.sin(2 * np.pi * hz * t) * 0.7
        + np.sin(2 * np.pi * hz * 2 * t) * 0.2
        + np.sin(2 * np.pi * hz * 3 * t) * 0.1
    )

    attack = int(SAMPLE_RATE * 0.008)
    envelope = np.exp(-3.5 * t)
    envelope[:attack] = np.linspace(0, 1, attack)

    amp = (velocity / 127.0) * 0.35
    return (wave * envelope * amp).astype(np.float32)


# ── Mixer ──────────────────────────────────────────────────────────────────
_voices: list[list] = []   # each entry: [samples_array, current_pos]
_lock   = threading.Lock()


def _callback(outdata, frames, time_info, status):
    mixed = np.zeros(frames, dtype=np.float32)
    with _lock:
        alive = []
        for voice in _voices:
            samples, pos = voice
            remaining = len(samples) - pos
            if remaining <= 0:
                continue
            n = min(frames, remaining)
            mixed[:n] += samples[pos : pos + n]
            voice[1] = pos + n
            if voice[1] < len(samples):
                alive.append(voice)
        _voices[:] = alive

    peak = np.max(np.abs(mixed))
    if peak > 1.0:
        mixed /= peak
    outdata[:, 0] = mixed


_stream = sd.OutputStream(
    samplerate=SAMPLE_RATE,
    channels=1,
    dtype="float32",
    blocksize=BLOCK_SIZE,
    callback=_callback,
)
_stream.start()


# ── Public API ─────────────────────────────────────────────────────────────

def play_note(pitch: int, velocity: int = 80):
    samples = _render_note(pitch, velocity)
    with _lock:
        _voices.append([samples, 0])


def play_chord(pitches: list, velocity: int = 64):
    if not pitches:
        return
    for pitch in pitches:
        samples = _render_note(pitch, velocity)
        with _lock:
            _voices.append([samples, 0])
