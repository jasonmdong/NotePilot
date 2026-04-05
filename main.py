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
import time
import threading
import queue
import tty
import termios
import rtmidi
from tracker import ScoreTracker
from accompanist import Accompanist
from synth import play_note as synth_play_note

NOTE_ON_MASK = 0x90
NOTE_OFF_MASK = 0x80

# Computer keyboard → MIDI note mapping (white keys, C major)
KEY_TO_PITCH = {
    'a': 60,  # C4
    's': 62,  # D4
    'd': 64,  # E4
    'f': 65,  # F4
    'g': 67,  # G4
    'h': 69,  # A4
    'j': 71,  # B4
    'k': 72,  # C5
}

NOTE_NAMES = {60: 'C', 62: 'D', 64: 'E', 65: 'F', 67: 'G', 69: 'A', 71: 'B', 72: 'C5'}


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


def main_keyboard():
    tracker = ScoreTracker()
    accompanist = Accompanist()

    print("\nKeyboard mode — play the Twinkle Twinkle melody:")
    print("  a=C  s=D  d=E  f=F  g=G  h=A  j=B  k=C(high)")
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
            # Play right hand + left hand simultaneously
            synth_play_note(pitch)
            if beat is not None:
                accompanist.play_for_beat(beat)
                bps = tracker.beats_per_second()
                sys.stdout.write(f"  {NOTE_NAMES.get(pitch, pitch):<3}  beat={beat:.1f}  tempo={bps*60:.0f} BPM\r\n")
            else:
                sys.stdout.write(f"  {NOTE_NAMES.get(pitch, pitch):<3}  (no match)\r\n")
            sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
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

    tracker     = ScoreTracker()
    accompanist = Accompanist()

    print("\nReady. Play the right-hand melody — left hand will follow.")
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
                accompanist.play_for_beat(beat)
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
    if "--keyboard" in sys.argv or "-k" in sys.argv:
        main_keyboard()
    else:
        main()
