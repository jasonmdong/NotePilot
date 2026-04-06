"""
Main entry point for the real-time piano accompanist.

Usage:
    python main.py              # MIDI keyboard input
    python main.py --keyboard   # Computer keyboard input

MIDI mode: choose input/output ports when prompted, then play the
right-hand melody on your MIDI keyboard.

Keyboard mode: press these keys to play notes (home row = white keys):
    a=C  s=D  d=E  f=F  g=G  h=A  j=B  k=C(high)

Play the right-hand melody of Twinkle Twinkle Little Star and the
left-hand accompaniment will follow your tempo automatically.
"""

import sys
import os
import importlib.util
import time
import threading
import queue
import tty
import termios
import rtmidi
from .tracker import ScoreTracker
from .accompanist import Accompanist
from .synth import play_note as synth_play_note


def load_score(name: str):
    """Load RIGHT_HAND and LEFT_HAND from scores/<name>.py"""
    path = os.path.join("scores", f"{name}.py")
    if not os.path.exists(path):
        print(f"Score not found: {path}")
        print("Available scores:")
        list_scores()
        sys.exit(1)
    spec = importlib.util.spec_from_file_location("_score", path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.RIGHT_HAND, mod.LEFT_HAND


def list_scores():
    files = sorted(f[:-3] for f in os.listdir("scores") if f.endswith(".py"))
    for f in files:
        print(f"  {f}")


def get_score_name() -> str:
    """Return the score name from --score flag, defaulting to 'twinkle'."""
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--score" and i < len(sys.argv):
            return sys.argv[i + 1]
        if arg.startswith("--score="):
            return arg.split("=", 1)[1]
    return "twinkle"

NOTE_ON_MASK = 0x90
NOTE_OFF_MASK = 0x80

# Computer keyboard → MIDI note mapping
#
#   White keys:        z x c v b n m  (C3–B3)
#                      a s d f g h j  (C4–B4)
#                      q w e r t y u  (C5–B5)  i=C6
#
#   Sharps (Shift+white key):
#                      Z X   V B N    (C#3 D#3  F#3 G#3 A#3)
#                      A S   F G H    (C#4 D#4  F#4 G#4 A#4)
#                      Q W   R T Y    (C#5 D#5  F#5 G#5 A#5)
#
KEY_TO_PITCH = {
    # C3 octave — whites
    'z': 48, 'x': 50, 'c': 52, 'v': 53, 'b': 55, 'n': 57, 'm': 59,
    # C3 octave — sharps (Shift)
    'Z': 49, 'X': 51,           'V': 54, 'B': 56, 'N': 58,
    # C4 octave — whites
    'a': 60, 's': 62, 'd': 64, 'f': 65, 'g': 67, 'h': 69, 'j': 71,
    # C4 octave — sharps (Shift)
    'A': 61, 'S': 63,           'F': 66, 'G': 68, 'H': 70,
    # C5 octave — whites
    'q': 72, 'w': 74, 'e': 76, 'r': 77, 't': 79, 'y': 81, 'u': 83,
    # C5 octave — sharps (Shift)
    'Q': 73, 'W': 75,           'R': 78, 'T': 80, 'Y': 82,
    # C6
    'i': 84,
}

_NOTE_NAMES_ALL = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']

def _pitch_name(midi: int) -> str:
    return _NOTE_NAMES_ALL[midi % 12] + str((midi // 12) - 1)

NOTE_NAMES = {v: _pitch_name(v) for v in KEY_TO_PITCH.values()}


def list_ports(midi_obj, label: str) -> list[str]:
    ports = [midi_obj.get_port_name(i) for i in range(midi_obj.get_port_count())]
    print(f"\nAvailable {label} ports:")
    for i, name in enumerate(ports):
        print(f"  [{i}] {name}")
    return ports


def choose_port(ports: list[str], label: str) -> int:
    if not ports:
        print(f"No {label} ports found. Connect a MIDI device and try again.")
        sys.exit(1)
    if len(ports) == 1:
        print(f"Auto-selecting only {label} port: {ports[0]}")
        return 0
    while True:
        try:
            idx = int(input(f"Choose {label} port number: "))
            if 0 <= idx < len(ports):
                return idx
        except ValueError:
            pass
        print("Invalid choice, try again.")


def _read_keys(note_queue: queue.Queue, stop_event: threading.Event):
    """Background thread: read single keypresses from stdin in raw mode."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while not stop_event.is_set():
            # Non-blocking read with a short timeout via select
            import select
            ready, _, _ = select.select([sys.stdin], [], [], 0.05)
            if ready:
                ch = sys.stdin.read(1)
                if ch == '\x03':  # Ctrl+C
                    note_queue.put(None)  # sentinel to stop main loop
                    break
                if ch in KEY_TO_PITCH:
                    note_queue.put(KEY_TO_PITCH[ch])
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def prompt_bpm() -> float:
    while True:
        try:
            val = input("Starting BPM (press Enter for 60): ").strip()
            if val == "":
                return 60.0
            bpm = float(val)
            if 20 <= bpm <= 300:
                return bpm
        except ValueError:
            pass
        print("Please enter a number between 20 and 300.")


def main_keyboard():
    right, left = load_score(get_score_name())
    initial_bps = prompt_bpm() / 60.0

    tracker     = ScoreTracker(right, initial_bps=initial_bps)
    accompanist = Accompanist(left, right, initial_bps=initial_bps)
    accompanist.start()

    print("\nKeyboard mode — play the melody (left hand will follow your tempo):")
    print("  Low  (C3–B3):  z x c v b n m")
    print("  Mid  (C4–B4):  a s d f g h j")
    print("  High (C5–B5):  q w e r t y u   i=C6")
    print("Press Ctrl+C to stop.\n")

    note_queue: queue.Queue = queue.Queue()
    stop_event = threading.Event()
    reader = threading.Thread(target=_read_keys, args=(note_queue, stop_event), daemon=True)
    reader.start()

    try:
        while not tracker.is_finished():
            try:
                pitch = note_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if pitch is None:  # Ctrl+C from reader thread
                break

            beat = tracker.on_note(pitch)
            synth_play_note(pitch)
            if beat is not None:
                bps = tracker.beats_per_second()
                accompanist.on_rh_note(beat, bps)
                sys.stdout.write(f"  {NOTE_NAMES.get(pitch, pitch):<3}  beat={beat:.1f}  tempo={bps*60:.0f} BPM\r\n")
            else:
                sys.stdout.write(f"  {NOTE_NAMES.get(pitch, pitch):<3}  (no match)\r\n")
            sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        accompanist.stop()
        print("\r\nStopping.")


def main():
    midi_in  = rtmidi.MidiIn()
    midi_out = rtmidi.MidiOut()

    in_ports  = list_ports(midi_in,  "INPUT")
    out_ports = list_ports(midi_out, "OUTPUT")

    in_idx  = choose_port(in_ports,  "INPUT")
    out_idx = choose_port(out_ports, "OUTPUT")

    midi_in.open_port(in_idx)
    midi_out.open_port(out_idx)

    # Ignore SysEx, timing, and active sensing messages.
    midi_in.ignore_types(sysex=True, timing=True, active_sense=True)

    right, left = load_score(get_score_name())
    initial_bps = prompt_bpm() / 60.0

    tracker     = ScoreTracker(right, initial_bps=initial_bps)
    accompanist = Accompanist(left, right, initial_bps=initial_bps)
    accompanist.start()

    print("\nReady. Play the right-hand melody — left hand will follow your tempo.")
    print("Press Ctrl+C to stop.\n")

    try:
        while not tracker.is_finished():
            msg_and_dt = midi_in.get_message()
            if msg_and_dt is None:
                time.sleep(0.001)
                continue

            msg, _ = msg_and_dt
            if len(msg) < 3:
                continue

            status, pitch, velocity = msg[0], msg[1], msg[2]

            # Only react to note-on messages with non-zero velocity.
            is_note_on = (status & 0xF0) == NOTE_ON_MASK and velocity > 0
            if not is_note_on:
                continue

            beat = tracker.on_note(pitch)
            if beat is not None:
                bps = tracker.beats_per_second()
                print(f"  note={pitch:3d}  beat={beat:.1f}  tempo={bps*60:.0f} BPM")
                accompanist.on_rh_note(beat, bps)
            else:
                print(f"  note={pitch:3d}  (no match)")

    except KeyboardInterrupt:
        pass
    finally:
        print("\nStopping.")
        accompanist.stop()
        midi_in.close_port()
        midi_out.close_port()


if __name__ == "__main__":
    if "--list" in sys.argv:
        print("Available scores:")
        list_scores()
    elif "--keyboard" in sys.argv or "-k" in sys.argv:
        main_keyboard()
    else:
        main()
