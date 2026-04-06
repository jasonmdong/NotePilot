"""
Convert a MusicXML file into a score.py for accompy.

Usage:
    python convert_score.py mysong.mxl
    python convert_score.py mysong.xml --out score.py

The script expects:
  - Part 0 (first staff / treble): right-hand melody
  - Part 1 (second staff / bass): left-hand accompaniment

If the piece only has one part, the left hand will be empty.
"""

import sys
import argparse
from music21 import converter, note, chord, stream


def beat_to_float(beat) -> float:
    """Convert a music21 beat (may be a Fraction) to a plain float."""
    # music21 measures start at beat 1; we want 0-indexed quarter-note offsets.
    # 'offset' (not 'beat') is what we use — it's already 0-indexed from the
    # start of the piece in quarter-note units.
    return float(beat)


def extract_melody(part) -> list:
    """Return [[midi_pitch, offset], ...] — top note of each chord, no rests."""
    notes = []
    for el in part.flatten().notesAndRests:
        if isinstance(el, note.Note):
            notes.append([el.pitch.midi, beat_to_float(el.offset)])
        elif isinstance(el, chord.Chord):
            top = max(n.pitch.midi for n in el.notes)
            notes.append([top, beat_to_float(el.offset)])
    notes.sort(key=lambda x: x[1])
    return notes


def extract_accompaniment(part) -> list:
    """Return [[pitches_list, offset], ...] — all notes/chords, no rests."""
    events = []
    for el in part.flatten().notesAndRests:
        if isinstance(el, note.Note):
            events.append([[el.pitch.midi], beat_to_float(el.offset)])
        elif isinstance(el, chord.Chord):
            events.append([sorted(n.pitch.midi for n in el.notes), beat_to_float(el.offset)])
    events.sort(key=lambda x: x[1])
    return events


def write_score_py(parts_data: list, out_path: str, title: str):
    """
    parts_data: [{"name": str, "notes": [[pitch, beat], ...]}, ...]
    Writes PARTS, and also RIGHT_HAND/LEFT_HAND defaulting to part 0 / rest.
    """
    # Default RIGHT_HAND = part 0 melody, LEFT_HAND = all other parts merged
    right = parts_data[0]['notes'] if parts_data else []
    left  = []
    for p in parts_data[1:]:
        left.extend([[n[0] if isinstance(n[0], list) else [n[0]], n[1]] for n in p['notes']])
    left.sort(key=lambda x: x[1])

    lines = [
        f'# Auto-generated score: {title}',
        f'# Beat positions are in quarter-note units from the start.',
        f'',
        f'# All parts — each note is [midi_pitch, beat]',
        f'PARTS = {parts_data!r}',
        f'',
        f'# Defaults: part 0 = melody, remaining parts = accompaniment',
        f'RIGHT_HAND = PARTS[0]["notes"] if PARTS else []',
        f'LEFT_HAND  = []',
        f'for _p in PARTS[1:]:',
        f'    LEFT_HAND.extend([[n[0] if isinstance(n[0], list) else [n[0]], n[1]] for n in _p["notes"]])',
        f'LEFT_HAND.sort(key=lambda x: x[1])',
    ]

    with open(out_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"Written to {out_path}")
    for p in parts_data:
        print(f"  {p['name']}: {len(p['notes'])} notes")


def main():
    parser = argparse.ArgumentParser(description="Convert MusicXML to an accompy score")
    parser.add_argument("input", help="Path to .mxl/.xml file, or corpus:<path>")
    parser.add_argument("--name", help="Score name (default: auto-derived from input)")
    parser.add_argument("--out", help="Explicit output path (overrides --name and scores/ folder)")
    args = parser.parse_args()

    print(f"Parsing {args.input} ...")
    if args.input.startswith("corpus:"):
        from music21 import corpus as m21corpus
        corpus_path = args.input[len("corpus:"):]
        mxl_path = str(m21corpus.getWork(corpus_path))
        score = m21corpus.parse(corpus_path)
    else:
        mxl_path = args.input
        score = converter.parse(args.input)

    score_parts = score.parts
    print(f"Found {len(score_parts)} part(s):")
    for i, p in enumerate(score_parts):
        print(f"  [{i}] {p.partName or '(unnamed)'}")

    if len(score_parts) == 0:
        print("No parts found — is this a valid MusicXML file?")
        sys.exit(1)

    parts_data = []
    for p in score_parts:
        part_name = p.partName or f"Part {len(parts_data) + 1}"
        notes = extract_melody(p)
        parts_data.append({"name": part_name, "notes": notes})

    title = score.metadata.title if score.metadata and score.metadata.title else args.input

    if args.out:
        out_path = args.out
    else:
        import re, os
        raw = args.name if args.name else args.input
        name = os.path.splitext(os.path.basename(raw))[0]
        name = re.sub(r'[^a-zA-Z0-9_]+', '_', name).strip('_').lower()
        out_path = os.path.join("scores", f"{name}.py")

    write_score_py(parts_data, out_path, title)

    score_name = os.path.splitext(os.path.basename(out_path))[0]
    print(f"\nPlay it with:  python main.py --score {score_name}")

    # Render sheet music to HTML (open in browser → print to PDF)
    render_html(mxl_path, os.path.join("scores", f"{score_name}.html"), title)


def render_html(mxl_path: str, out_path: str, title: str):
    """Render MusicXML to a printable HTML file using Verovio."""
    try:
        import verovio
    except ImportError:
        print("(Skipping sheet music render — run: pip install verovio)")
        return

    tk = verovio.toolkit()
    tk.setOptions({
        "pageWidth":  2100,
        "pageHeight": 2970,   # A4 in tenths (~210mm × 297mm at 10 tenths/mm)
        "spacingSystem": 12,
        "adjustPageHeight": 0,
        "footer": "none",
    })
    tk.loadFile(mxl_path)

    page_count = tk.getPageCount()
    svgs = [tk.renderToSVG(i + 1) for i in range(page_count)]

    page_divs = "\n".join(
        f'<div class="page">{svg}</div>' for svg in svgs
    )

    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>
    body {{ margin: 0; background: #eee; font-family: sans-serif; }}
    h1   {{ text-align: center; padding: 1rem; font-size: 1.1rem; color: #333; }}
    .page {{
      background: white;
      width: 210mm;
      margin: 1rem auto;
      box-shadow: 0 2px 6px rgba(0,0,0,.3);
      page-break-after: always;
    }}
    .page svg {{ width: 100%; height: auto; display: block; }}
    @media print {{
      body {{ background: white; }}
      h1   {{ display: none; }}
      .page {{ margin: 0; box-shadow: none; width: 100%; }}
    }}
  </style>
</head>
<body>
  <h1>{title} — open in browser and use File → Print to save as PDF</h1>
  {page_divs}
</body>
</html>"""

    with open(out_path, "w") as f:
        f.write(html)

    print(f"Sheet music : {out_path}  (open in browser → File → Print → Save as PDF)")


def show_melody(name: str = None):
    """Print the RIGHT_HAND from scores/<name>.py as note names + keyboard keys."""
    import importlib.util, os
    if not name:
        print("Usage: python convert_score.py --show <score_name>")
        sys.exit(1)
    path = os.path.join("scores", f"{name}.py")
    if not os.path.exists(path):
        print(f"Score not found: {path}")
        sys.exit(1)
    spec = importlib.util.spec_from_file_location("_score", path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    RIGHT_HAND = mod.RIGHT_HAND

    _NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']

    KEY_TO_PITCH = {
        'z':48,'x':50,'c':52,'v':53,'b':55,'n':57,'m':59,
        'a':60,'s':62,'d':64,'f':65,'g':67,'h':69,'j':71,
        'q':72,'w':74,'e':76,'r':77,'t':79,'y':81,'u':83,
        'i':84,
    }
    PITCH_TO_KEY = {v: k for k, v in KEY_TO_PITCH.items()}

    def pitch_name(midi):
        return _NAMES[midi % 12] + str((midi // 12) - 1)

    print("\nKeyboard layout:")
    print("  Low  (C3–B3):  z=C3 x=D3 c=E3 v=F3 b=G3 n=A3 m=B3")
    print("  Mid  (C4–B4):  a=C4 s=D4 d=E4 f=F4 g=G4 h=A4 j=B4")
    print("  High (C5–B5):  q=C5 w=D5 e=E5 r=F5 t=G5 y=A5 u=B5  i=C6")
    print()
    print("Right-hand melody:")
    print(f"  {'Beat':>6}  {'Note':>5}  Key")
    print(f"  {'----':>6}  {'----':>5}  ---")
    for pitch, beat in RIGHT_HAND:
        name = pitch_name(pitch)
        key  = PITCH_TO_KEY.get(pitch, '?')
        print(f"  {beat:>6.2f}  {name:>5}  {key}")


if __name__ == "__main__":
    if "--show" in sys.argv:
        # Accept optional score name: --show mozart_k545
        idx = sys.argv.index("--show")
        name = sys.argv[idx + 1] if idx + 1 < len(sys.argv) and not sys.argv[idx + 1].startswith("--") else None
        show_melody(name)
    else:
        main()
