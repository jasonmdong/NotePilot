# Accompy

A real-time piano accompanist. You play the right-hand melody — accompy tracks your tempo and plays the left hand automatically.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install rtmidi numpy sounddevice music21 fastapi uvicorn verovio
```

## Web UI

```bash
uvicorn server:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000) to browse scores, add new pieces, and play.

## CLI

```bash
# Computer keyboard
python main.py --keyboard --score twinkle

# USB MIDI keyboard (e.g. Yamaha P-71)
python main.py --score mozart_k545

# List available scores
python main.py --list
```

You'll be prompted for a starting BPM. The left hand plays between your notes and waits at each melody note until you play it.

### Keyboard layout

```
Low  (C3–B3):  z x c v b n m
Mid  (C4–B4):  a s d f g h j
High (C5–B5):  q w e r t y u   i = C6
```

## Adding pieces

Via the web UI — click **+ Add piece** and search the built-in library (535 pieces).

Or via CLI:

```bash
# Built-in corpus
python convert_score.py corpus:mozart/k545/movement1_exposition --name mozart_k545

# Downloaded MusicXML
python convert_score.py ~/Downloads/mysong.mxl --name mysong

# Show notes + keyboard keys for a score
python convert_score.py --show mozart_k545
```

Free MusicXML sources: [IMSLP](https://imslp.org) · [Flat.io](https://flat.io)

## Structure

```
main.py            # CLI entry point
server.py          # Web server
convert_score.py   # MusicXML → scores/ converter
src/
  tracker.py       # Score position + tempo tracking
  accompanist.py   # Left-hand scheduler
  synth.py         # Software synthesizer
scores/            # Saved pieces (.py + .html per piece)
static/            # Web UI
```
