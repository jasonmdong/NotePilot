# Accompy

A real-time piano accompanist. You play the right-hand melody — accompy tracks your tempo and plays the left hand automatically.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Web UI

```bash
uvicorn server:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000) to browse scores, add new pieces, and play.

## CLI

```bash
# Computer keyboard
python -m src.main --keyboard --score twinkle

# USB MIDI keyboard (e.g. Yamaha P-71)
python -m src.main --score mozart_k545

# List available scores
python -m src.main --list
```

You'll be prompted for a starting BPM. The left hand plays between your notes and waits at each melody note until you play it.

### Keyboard layout

```
A = C   S = D   D = E   J = F   K = G   L = A   ; = B
Hold Shift for sharps. The app automatically chooses the octave for the current note.
```

## Adding pieces

Via the web UI — click **+ Add piece** and search the built-in library (535 pieces).

Or via CLI:

```bash
# Built-in corpus
python -m src.convert_score corpus:mozart/k545/movement1_exposition --name mozart_k545

# Downloaded MusicXML
python -m src.convert_score ~/Downloads/mysong.mxl --name mysong

# Show notes + keyboard keys for a score
python -m src.convert_score --show mozart_k545
```

Free MusicXML sources: [IMSLP](https://imslp.org) · [Flat.io](https://flat.io)
