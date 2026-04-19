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
import os
import re
import argparse
from music21 import converter, note, chord, expressions
from src.paths import get_scores_dir


def beat_to_float(beat) -> float:
    """Convert a music21 beat (may be a Fraction) to a plain float."""
    # music21 measures start at beat 1; we want 0-indexed quarter-note offsets.
    # 'offset' (not 'beat') is what we use — it's already 0-indexed from the
    # start of the piece in quarter-note units.
    return float(beat)


def _starts_new_attack(el) -> bool:
    tie = getattr(el, "tie", None)
    if tie is None:
        return True
    return tie.type not in {"stop", "continue"}


def _note_tie_duration(part, start_note) -> float:
    duration = float(start_note.quarterLength)
    tie = getattr(start_note, "tie", None)
    if tie is None or tie.type != "start":
        return duration

    found_start = False
    start_pitch = start_note.pitch.midi
    start_offset = float(start_note.offset)
    for later in part.flatten().notesAndRests:
        if isinstance(later, note.Note):
            members = [later]
        elif isinstance(later, chord.Chord):
            members = list(later.notes)
        else:
            continue

        later_offset = float(later.offset)
        if not found_start:
            if later is start_note or (
                later_offset == start_offset
                and any(member is start_note for member in members)
            ):
                found_start = True
            continue

        for member in members:
            later_tie = getattr(member, "tie", None)
            if member.pitch.midi != start_pitch or later_tie is None:
                continue
            if later_tie.type in {"continue", "stop"}:
                duration += float(member.quarterLength)
                if later_tie.type == "stop":
                    return duration
    return duration


def _pedal_spans(container, anchor=None) -> list[tuple[float, float]]:
    spans = []
    anchor = anchor or container
    for pedal in container.recurse().getElementsByClass(expressions.PedalMark):
        try:
            first = pedal.getFirst()
            last = pedal.getLast()
            if not first or not last:
                continue
            start = float(first.getOffsetInHierarchy(anchor))
            end = float(last.getOffsetInHierarchy(anchor))
            if end < start:
                start, end = end, start
            spans.append((start, end))
        except Exception:
            continue
    spans.sort(key=lambda item: (item[0], item[1]))
    return spans


def _apply_pedal(events: list, pedal_spans: list[tuple[float, float]]) -> list:
    if not events or not pedal_spans:
        return events

    for event in events:
        beat = float(event[1])
        end = beat + float(event[2])
        pedal_release = None
        for pedal_start, pedal_end in pedal_spans:
            if pedal_end <= beat:
                continue
            if pedal_start > end:
                break
            if pedal_start <= beat <= pedal_end or pedal_start <= end <= pedal_end:
                end = max(end, pedal_end)
                pedal_release = max(pedal_release or pedal_end, pedal_end)
        event[2] = max(0.125, end - beat)
        if pedal_release is not None:
            if len(event) > 3:
                event[3] = pedal_release
            else:
                event.append(pedal_release)

    next_attack_by_pitch = {}
    for event in reversed(events):
        beat = float(event[1])
        pitches = event[0] if isinstance(event[0], list) else [event[0]]
        end = beat + float(event[2])
        pedaled = len(event) > 3 and event[3] is not None
        for pitch in pitches:
            next_attack = next_attack_by_pitch.get(pitch)
            if not pedaled and next_attack is not None and next_attack > beat:
                end = min(end, next_attack)
        event[2] = max(0.125, end - beat)
        for pitch in pitches:
            next_attack_by_pitch[pitch] = beat

    return events


def extract_events(part, pedal_spans: list[tuple[float, float]] | None = None) -> list:
    """Return [[midi_pitch|[midi_pitches], offset, duration], ...].

    Tied continuations/stops are treated as sustain, not a fresh attack. That
    keeps held notes from being emitted twice when the notation splits them
    across beats or measures. Pedal spans extend the event duration so sustained
    piano writing does not collapse into short detached notes on playback.
    """
    grouped = {}
    for el in part.flatten().notesAndRests:
        if isinstance(el, note.Note):
            if _starts_new_attack(el):
                beat = beat_to_float(el.offset)
                slot = grouped.setdefault(beat, {"pitches": [], "duration": 0.0})
                slot["pitches"].append(el.pitch.midi)
                slot["duration"] = max(slot["duration"], _note_tie_duration(part, el))
        elif isinstance(el, chord.Chord):
            attacked = [n for n in el.notes if _starts_new_attack(n)]
            pitches = [n.pitch.midi for n in attacked]
            if pitches:
                beat = beat_to_float(el.offset)
                slot = grouped.setdefault(beat, {"pitches": [], "duration": 0.0})
                slot["pitches"].extend(pitches)
                slot["duration"] = max(slot["duration"], max(_note_tie_duration(part, n) for n in attacked))

    events = []
    for beat in sorted(grouped.keys()):
        pitches = sorted(set(grouped[beat]["pitches"]))
        duration = grouped[beat]["duration"]
        if not pitches:
            continue
        payload = pitches[0] if len(pitches) == 1 else pitches
        events.append([payload, beat, duration])

    return _apply_pedal(events, pedal_spans if pedal_spans is not None else _pedal_spans(part))


def slugify_score_name(raw: str) -> str:
    name = os.path.splitext(os.path.basename(raw))[0]
    name = re.sub(r'[^a-zA-Z0-9_]+', '_', name).strip('_').lower()
    return name or "imported_score"


def write_score_py(
    parts_data: list,
    out_path: str,
    title: str,
    source_ref: str | None = None,
    measure_beats: list[float] | None = None,
):
    """
    parts_data: [{"name": str, "notes": [[pitch_or_pitches, beat, duration, pedal_release?], ...]}, ...]
    Writes PARTS, and also RIGHT_HAND/LEFT_HAND defaulting to part 0 / rest.
    """
    # Default RIGHT_HAND = part 0 melody, LEFT_HAND = all other parts merged
    right = parts_data[0]['notes'] if parts_data else []
    left  = []
    for p in parts_data[1:]:
        for n in p['notes']:
            merged = [n[0] if isinstance(n[0], list) else [n[0]], n[1], n[2]]
            if len(n) > 3:
                merged.append(n[3])
            left.append(merged)
    left.sort(key=lambda x: x[1])

    lines = [
        f'# Auto-generated: {source_ref or title}',
        f'# Title: {title}',
        f'# Beat positions are in quarter-note units from the start.',
        f'',
        f'# All parts — each note is [midi_pitch_or_chord, beat, duration, pedal_release?]',
        f'PARTS = {parts_data!r}',
        f'MEASURE_BEATS = {(measure_beats or [])!r}',
        f'',
        f'# Defaults: part 0 = melody, remaining parts = accompaniment',
        f'RIGHT_HAND = PARTS[0]["notes"] if PARTS else []',
        f'LEFT_HAND  = []',
        f'for _p in PARTS[1:]:',
        f'    for n in _p["notes"]:',
        f'        _merged = [n[0] if isinstance(n[0], list) else [n[0]], n[1], n[2]]',
        f'        if len(n) > 3:',
        f'            _merged.append(n[3])',
        f'        LEFT_HAND.append(_merged)',
        f'LEFT_HAND.sort(key=lambda x: x[1])',
    ]

    with open(out_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"Written to {out_path}")
    for p in parts_data:
        print(f"  {p['name']}: {len(p['notes'])} notes")


def build_parts_data(score) -> list:
    score_parts = score.parts
    if len(score_parts) == 0:
        raise ValueError("No parts found — is this a valid MusicXML file?")

    global_pedals = _pedal_spans(score, anchor=score)
    shared_pedal_score = (
        len(score_parts) <= 2
        and any(_detect_instrument(part) == "piano" for part in score_parts)
    )

    parts_data = []
    for p in score_parts:
        part_name = p.partName or f"Part {len(parts_data) + 1}"
        instrument = _detect_instrument(p)
        local_pedals = _pedal_spans(p, anchor=score)
        if shared_pedal_score:
            pedal_spans = sorted(set(local_pedals + global_pedals))
        else:
            pedal_spans = local_pedals
        notes = extract_events(p, pedal_spans=pedal_spans)
        parts_data.append({"name": part_name, "instrument": instrument, "notes": notes})
    return parts_data


def extract_measure_beats(score) -> list[float]:
    first_part = score.parts[0] if score.parts else score
    return [float(m.offset) for m in first_part.getElementsByClass('Measure')]


def convert_score_source(source: str, *, name: str | None = None, out_dir: str | None = None):
    if source.startswith("corpus:"):
        from music21 import corpus as m21corpus
        corpus_path = source[len("corpus:"):]
        mxl_path = str(m21corpus.getWork(corpus_path))
        score = m21corpus.parse(corpus_path)
        title_fallback = source
        render_source_path = mxl_path
    else:
        mxl_path = source
        score = converter.parse(source)
        title_fallback = source
        render_source_path = mxl_path

    parts_data = build_parts_data(score)
    measure_beats = extract_measure_beats(score)
    title = score.metadata.title if score.metadata and score.metadata.title else title_fallback
    score_name = slugify_score_name(name or title_fallback)
    out_dir = out_dir or str(get_scores_dir())
    out_py = os.path.join(out_dir, f"{score_name}.py")
    out_html = os.path.join(out_dir, f"{score_name}.html")

    # Normalize uploaded MusicXML through music21 before sending it to Verovio.
    # Some raw .xml inputs parse fine in music21 but render poorly or blank in
    # Verovio until they are re-exported into canonical MusicXML.
    if not source.startswith("corpus:"):
        normalized_musicxml = os.path.join(out_dir, f"{score_name}__normalized.musicxml")
        try:
            render_source_path = score.write("musicxml", fp=normalized_musicxml)
        except Exception:
            render_source_path = mxl_path

    write_score_py(parts_data, out_py, title, source_ref=source, measure_beats=measure_beats)
    render_html(str(render_source_path), out_html, title)

    total_notes = sum(len(p["notes"]) for p in parts_data)
    return {
        "name": score_name,
        "title": title,
        "parts": parts_data,
        "parts_count": len(parts_data),
        "total_notes": total_notes,
        "out_py": out_py,
        "out_html": out_html,
        "has_sheet": os.path.exists(out_html),
        "source_ref": source,
        "measure_beats": measure_beats,
        "render_source_path": str(render_source_path),
    }


def _detect_instrument(part) -> str:
    """Infer an instrument name from a music21 part."""
    from music21 import instrument as m21i
    try:
        instr = part.getInstrument()
    except Exception:
        instr = None

    if instr is None:
        return "piano"

    name = (part.partName or "").lower()

    # Use class hierarchy first (most reliable)
    if isinstance(instr, m21i.KeyboardInstrument):
        return "piano"
    if isinstance(instr, (m21i.Violin,)):
        return "violin"
    if isinstance(instr, (m21i.Viola,)):
        return "viola"
    if isinstance(instr, (m21i.Violoncello,)):
        return "cello"
    if isinstance(instr, m21i.StringInstrument):
        return "strings"
    if isinstance(instr, (m21i.Flute,)):
        return "flute"
    if isinstance(instr, (m21i.Clarinet,)):
        return "clarinet"
    if isinstance(instr, (m21i.Oboe,)):
        return "oboe"
    if isinstance(instr, m21i.WoodwindInstrument):
        return "flute"
    if isinstance(instr, m21i.BrassInstrument):
        return "strings"  # approximate brass with strings for now

    # Fall back to part name keywords
    for kw, result in [
        ("violin", "violin"), ("viola", "viola"), ("cello", "cello"),
        ("bass", "cello"), ("flute", "flute"), ("clarinet", "clarinet"),
        ("oboe", "oboe"), ("soprano", "flute"), ("alto", "clarinet"),
        ("tenor", "violin"), ("piano", "piano"),
    ]:
        if kw in name:
            return result

    return "piano"


def main():
    parser = argparse.ArgumentParser(description="Convert MusicXML to an accompy score")
    parser.add_argument("input", help="Path to .mxl/.xml file, or corpus:<path>")
    parser.add_argument("--name", help="Score name (default: auto-derived from input)")
    parser.add_argument("--out", help="Explicit output path (overrides --name and default scores folder)")
    args = parser.parse_args()

    print(f"Parsing {args.input} ...")
    out_dir = str(get_scores_dir())
    out_name = args.name
    if args.out:
        out_dir = os.path.dirname(args.out) or "."
        out_name = os.path.splitext(os.path.basename(args.out))[0]
    try:
        result = convert_score_source(args.input, name=out_name, out_dir=out_dir)
    except Exception as exc:
        print(str(exc))
        sys.exit(1)

    print(f"\nPlay it with:  python main.py --score {result['name']}")


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
    if page_count <= 0:
        return

    svgs = [tk.renderToSVG(i + 1) for i in range(page_count)]
    non_empty_svgs = [svg for svg in svgs if svg and "<svg" in svg and len(svg) > 500]
    if not non_empty_svgs:
        return

    page_divs = "\n".join(
        f'<div class="page">{svg}</div>' for svg in non_empty_svgs
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
  {page_divs}
</body>
</html>"""

    with open(out_path, "w") as f:
        f.write(html)

    print(f"Sheet music : {out_path}  (open in browser → File → Print → Save as PDF)")


def show_melody(name: str = None):
    """Print the RIGHT_HAND from the current scores dir as note names + keyboard keys."""
    import importlib.util, os
    if not name:
        print("Usage: python convert_score.py --show <score_name>")
        sys.exit(1)
    path = os.path.join(str(get_scores_dir()), f"{name}.py")
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
    for event in RIGHT_HAND:
        pitch, beat = event[0], event[1]
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
