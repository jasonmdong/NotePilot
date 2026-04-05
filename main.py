"""
Main entry point for the real-time piano accompanist.

Usage:
    python main.py

The script will list available MIDI ports and prompt you to choose
an input port (your keyboard) and an output port (synthesizer or loopback).

Play the right-hand melody of Twinkle Twinkle Little Star and the
left-hand accompaniment will follow your tempo automatically.
"""

import sys
import time
import rtmidi
from tracker import ScoreTracker
from accompanist import Accompanist

NOTE_ON_MASK = 0x90
NOTE_OFF_MASK = 0x80


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
    accompanist = Accompanist(midi_out)
    accompanist.start()

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
                accompanist.update(tracker)
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
    main()
