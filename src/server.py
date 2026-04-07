"""
FastAPI server for accompy.

Endpoints:
  GET  /                        → serve the web UI
  GET  /api/scores              → list available scores
  GET  /api/scores/{name}       → score data as JSON
  GET  /api/scores/{name}/sheet → sheet music HTML
  GET  /api/corpus/search?q=    → search music21 corpus
  POST /api/convert             → convert a corpus piece
"""

import os
import re
import importlib.util
from functools import lru_cache
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI()


# ── Corpus index (built once on first search) ─────────────────────────────────

@lru_cache(maxsize=1)
def _corpus_index():
    """Return list of {path, composer, title} for all .mxl files in the corpus."""
    from music21 import corpus
    pkg_dir = os.path.dirname(corpus.__file__)
    entries = []
    for p in corpus.getPaths():
        s = str(p)
        if not s.endswith('.mxl'):
            continue
        rel   = os.path.relpath(s, pkg_dir).replace(os.sep, '/').replace('.mxl', '')
        parts = rel.split('/')
        composer = parts[0] if len(parts) >= 2 else ''
        title    = '/'.join(parts[1:]) if len(parts) >= 2 else rel
        entries.append({'path': rel, 'composer': composer, 'title': title})
    return entries

SCORES_DIR = "scores"

# In-memory score cache: name → (mtime, module)
# Invalidated automatically when the .py file changes on disk.
_score_cache: dict[str, tuple[float, object]] = {}
_measure_cache: dict[str, tuple[float, list[float]]] = {}


def load_score_module(name: str):
    path = os.path.join(SCORES_DIR, f"{name}.py")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Score '{name}' not found")

    mtime = os.path.getmtime(path)
    cached = _score_cache.get(name)
    if cached and cached[0] == mtime:
        return cached[1]

    spec = importlib.util.spec_from_file_location("_score", path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _score_cache[name] = (mtime, mod)
    return mod


def load_measure_beats(name: str) -> list[float]:
    path = os.path.join(SCORES_DIR, f"{name}.py")
    if not os.path.exists(path):
        return []

    mtime = os.path.getmtime(path)
    cached = _measure_cache.get(name)
    if cached and cached[0] == mtime:
        return cached[1]

    try:
        with open(path, "r") as f:
            first_line = f.readline().strip()
    except OSError:
        return []

    prefixes = ("# Auto-generated: ", "# Auto-generated score: ")
    source_ref = None
    for prefix in prefixes:
        if first_line.startswith(prefix):
            source_ref = first_line[len(prefix):].strip()
            break

    if not source_ref:
        return []

    try:
        from music21 import corpus as m21corpus, converter

        if source_ref.startswith("corpus:"):
            score = m21corpus.parse(source_ref[len("corpus:"):])
        else:
            try:
                score = converter.parse(source_ref)
            except Exception:
                # Older generated scores may store a bare music21 corpus path.
                score = m21corpus.parse(source_ref)

        first_part = score.parts[0] if score.parts else score
        measure_beats = [float(m.offset) for m in first_part.getElementsByClass('Measure')]
    except Exception:
        return []

    _measure_cache[name] = (mtime, measure_beats)
    return measure_beats


@app.get("/api/corpus/search")
def search_corpus(q: str = ""):
    index   = _corpus_index()
    q_lower = q.lower().strip()
    if not q_lower:
        # Return a sample: first 5 from each composer
        from collections import defaultdict
        by_composer = defaultdict(list)
        for e in index:
            by_composer[e['composer']].append(e)
        results = []
        for entries in by_composer.values():
            results.extend(entries[:5])
        return {"results": results[:60]}

    results = [
        e for e in index
        if q_lower in e['path'].lower()
        or q_lower in e['composer'].lower()
        or q_lower in e['title'].lower()
    ]
    return {"results": results[:60]}


@app.get("/api/scores")
def list_scores():
    names = sorted(
        f[:-3] for f in os.listdir(SCORES_DIR) if f.endswith(".py")
    )
    return {"scores": names}


@app.get("/api/scores/{name}")
def get_score(name: str):
    mod = load_score_module(name)
    has_sheet = os.path.exists(os.path.join(SCORES_DIR, f"{name}.html"))

    # New format: PARTS list
    if hasattr(mod, "PARTS"):
        parts = mod.PARTS
    else:
        # Legacy format (e.g. twinkle.py) — wrap in a single part
        parts = [
            {"name": "Melody",        "notes": [[p, b] for p, b in mod.RIGHT_HAND]},
            {"name": "Accompaniment", "notes": [[p, b] for p, b in mod.LEFT_HAND]},
        ]

    return {
        "name":      name,
        "parts":     parts,
        "has_sheet": has_sheet,
        "measure_beats": load_measure_beats(name),
        # keep legacy fields for CLI compatibility
        "right_hand": mod.RIGHT_HAND,
        "left_hand":  mod.LEFT_HAND,
    }


class InstrumentUpdate(BaseModel):
    part_index: int
    instrument: str


@app.patch("/api/scores/{name}/instrument")
def update_instrument(name: str, req: InstrumentUpdate):
    """Persist an instrument change for a part in the score .py file."""
    mod  = load_score_module(name)
    path = os.path.join(SCORES_DIR, f"{name}.py")

    if not hasattr(mod, "PARTS"):
        raise HTTPException(status_code=400, detail="Score has no PARTS (legacy format)")
    parts = mod.PARTS
    if req.part_index < 0 or req.part_index >= len(parts):
        raise HTTPException(status_code=400, detail="Invalid part index")

    parts[req.part_index]["instrument"] = req.instrument

    # Rewrite the file preserving everything, just updating PARTS
    with open(path, "r") as f:
        content = f.read()

    import ast
    # Replace just the PARTS line
    new_parts_line = f"PARTS = {parts!r}"
    lines = content.splitlines()
    new_lines = []
    for line in lines:
        if line.startswith("PARTS = "):
            new_lines.append(new_parts_line)
        else:
            new_lines.append(line)
    with open(path, "w") as f:
        f.write("\n".join(new_lines) + "\n")

    _score_cache.pop(name, None)
    _measure_cache.pop(name, None)
    return {"updated": True}


@app.delete("/api/scores/{name}")
def delete_score(name: str):
    removed = []
    for ext in (".py", ".html"):
        path = os.path.join(SCORES_DIR, f"{name}{ext}")
        if os.path.exists(path):
            os.remove(path)
            removed.append(path)
    _score_cache.pop(name, None)
    _measure_cache.pop(name, None)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Score '{name}' not found")
    return {"deleted": removed}


@app.get("/api/scores/{name}/meta")
def get_score_meta(name: str):
    path = os.path.join(SCORES_DIR, f"{name}.py")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Score '{name}' not found")
    return {"name": name, "mtime": os.path.getmtime(path)}


@app.get("/api/scores/{name}/sheet")
def get_sheet(name: str):
    path = os.path.join(SCORES_DIR, f"{name}.html")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No sheet music for this score")
    return FileResponse(path, media_type="text/html")


class ConvertRequest(BaseModel):
    corpus_path: str
    name: str


@app.post("/api/convert")
def convert_score(req: ConvertRequest):
    import re
    from music21 import corpus as m21corpus
    from music21 import converter, note, chord
    from src.convert_score import _detect_instrument

    name = re.sub(r"[^a-zA-Z0-9_]+", "_", req.name).strip("_").lower()
    out_py   = os.path.join(SCORES_DIR, f"{name}.py")
    out_html = os.path.join(SCORES_DIR, f"{name}.html")

    try:
        mxl_path = str(m21corpus.getWork(req.corpus_path))
        score    = m21corpus.parse(req.corpus_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    score_parts = score.parts
    if len(score_parts) < 1:
        raise HTTPException(status_code=400, detail="No parts found in score")

    parts_data = []
    for p in score_parts:
        part_name  = p.partName or f"Part {len(parts_data) + 1}"
        instrument = _detect_instrument(p)
        notes = []
        for el in p.flatten().notesAndRests:
            if isinstance(el, note.Note):
                notes.append([el.pitch.midi, float(el.offset)])
            elif isinstance(el, chord.Chord):
                top = max(n.pitch.midi for n in el.notes)
                notes.append([top, float(el.offset)])
        notes.sort(key=lambda x: x[1])
        parts_data.append({"name": part_name, "instrument": instrument, "notes": notes})

    # Write .py
    lines = [
        f'# Auto-generated: {req.corpus_path}',
        f'PARTS = {parts_data!r}',
        f'RIGHT_HAND = PARTS[0]["notes"] if PARTS else []',
        f'LEFT_HAND  = []',
        f'for _p in PARTS[1:]:',
        f'    LEFT_HAND.extend([[n[0] if isinstance(n[0], list) else [n[0]], n[1]] for n in _p["notes"]])',
        f'LEFT_HAND.sort(key=lambda x: x[1])',
    ]
    with open(out_py, "w") as f:
        f.write("\n".join(lines) + "\n")

    # Bust the in-memory cache so the next GET picks up the new file
    _score_cache.pop(name, None)
    _measure_cache.pop(name, None)

    # Write .html via verovio
    try:
        import verovio
        tk = verovio.toolkit()
        tk.setOptions({"pageWidth": 2100, "pageHeight": 2970,
                       "spacingSystem": 12, "adjustPageHeight": 0, "footer": "none"})
        tk.loadFile(mxl_path)
        svgs = [tk.renderToSVG(i + 1) for i in range(tk.getPageCount())]
        page_divs = "\n".join(f'<div class="page">{s}</div>' for s in svgs)
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body{{margin:0;background:#eee}} .page{{background:white;width:210mm;margin:1rem auto;box-shadow:0 2px 6px rgba(0,0,0,.3)}} .page svg{{width:100%;height:auto;display:block}}
  @media print{{body{{background:white}} .page{{margin:0;box-shadow:none;width:100%}}}}
</style></head><body>{page_divs}</body></html>"""
        with open(out_html, "w") as f:
            f.write(html)
    except Exception:
        pass

    total_notes = sum(len(p["notes"]) for p in parts_data)
    return {"name": name, "parts": len(parts_data), "total_notes": total_notes,
            "has_sheet": os.path.exists(out_html)}


# Serve static files and fallback to index.html
app.mount("/", StaticFiles(directory="static", html=True), name="static")
