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
import tempfile
import subprocess
import importlib.util
import hashlib
import hmac
import secrets
from pathlib import Path
from functools import lru_cache
from datetime import datetime, timedelta, timezone
import requests
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from src.env import load_local_env
from src.convert_score import convert_score_source, slugify_score_name
from src.paths import get_scores_dir, get_static_dir
from src.storage import create_score_store, LocalScoreStore, SupabaseScoreStore

load_local_env()

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

SCORES_DIR = str(get_scores_dir())
STATIC_DIR = str(get_static_dir())
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
ALLOWED_PDF_SUFFIXES = {".pdf"}

# In-memory score cache: name → (mtime, module)
# Invalidated automatically when the .py file changes on disk.
_score_cache: dict[str, tuple[float, object]] = {}
_measure_cache: dict[str, tuple[float, list[float]]] = {}
_score_store = create_score_store()
SESSION_COOKIE_NAME = "accompy_session"
SESSION_DAYS = 30


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    calculated = hash_password(password, salt).split("$", 1)[1]
    return hmac.compare_digest(calculated, digest)


def create_session_token() -> str:
    return secrets.token_urlsafe(48)


def require_supabase_user_id(request: Request, action: str) -> str:
    user_id = current_user_id_for_request(request)
    if user_id:
        return user_id
    raise HTTPException(
        status_code=401,
        detail=f"Authenticated user is required for Supabase-backed {action}."
    )


def current_user_id_for_request(request: Request) -> str | None:
    if isinstance(_score_store, SupabaseScoreStore):
        token = request.cookies.get(SESSION_COOKIE_NAME, "").strip()
        if token:
            user = _score_store.get_app_session_user(token)
            if user:
                return user.get("id")
    auth_header = request.headers.get("authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        if token and os.getenv("SUPABASE_URL", "").strip():
            response = requests.get(
                f"{os.getenv('SUPABASE_URL').rstrip('/')}/auth/v1/user",
                headers={
                    "apikey": os.getenv("SUPABASE_ANON_KEY", "").strip(),
                    "Authorization": f"Bearer {token}",
                },
                timeout=15,
            )
            if response.status_code == 200:
                return response.json().get("id")
            raise HTTPException(status_code=401, detail="Invalid Supabase session.")
    return None


def current_app_user_for_request(request: Request) -> dict | None:
    if not isinstance(_score_store, SupabaseScoreStore):
        return None
    token = request.cookies.get(SESSION_COOKIE_NAME, "").strip()
    if not token:
        return None
    return _score_store.get_app_session_user(token)


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
    try:
        mod = load_score_module(name)
        if hasattr(mod, "MEASURE_BEATS"):
            return list(mod.MEASURE_BEATS)
    except HTTPException:
        return []

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


def invalidate_score_cache(name: str):
    _score_cache.pop(name, None)
    _measure_cache.pop(name, None)


def score_name_from_input(raw: str) -> str:
    return slugify_score_name(raw)


async def save_uploaded_file(upload: UploadFile, directory: Path, index: int) -> Path:
    suffix = Path(upload.filename or "").suffix.lower()
    stem = score_name_from_input(Path(upload.filename or f"upload_{index}").stem)
    dest = directory / f"{index:02d}_{stem}{suffix}"
    data = await upload.read()
    dest.write_bytes(data)
    await upload.close()
    return dest


def combine_images_to_pdf(image_paths: list[Path], out_path: Path) -> Path:
    import fitz

    doc = fitz.open()
    try:
        for image_path in image_paths:
            img = fitz.open(image_path)
            try:
                pdf_bytes = img.convert_to_pdf()
            finally:
                img.close()
            img_pdf = fitz.open("pdf", pdf_bytes)
            try:
                doc.insert_pdf(img_pdf)
            finally:
                img_pdf.close()
        doc.save(out_path)
    finally:
        doc.close()
    return out_path


def prepare_omr_input(upload_paths: list[Path], work_dir: Path) -> Path:
    suffixes = {path.suffix.lower() for path in upload_paths}
    if suffixes & ALLOWED_PDF_SUFFIXES:
        if len(upload_paths) != 1 or not suffixes <= ALLOWED_PDF_SUFFIXES:
            raise HTTPException(status_code=400, detail="Upload either one PDF or one/more image files, not both.")
        return upload_paths[0]

    if not suffixes or not suffixes <= ALLOWED_IMAGE_SUFFIXES:
        raise HTTPException(status_code=400, detail="Supported uploads are PDF, PNG, JPG, and JPEG.")

    return combine_images_to_pdf(upload_paths, work_dir / "input.pdf")


def run_audiveris(input_path: Path, output_dir: Path):
    audiveris_bin = os.getenv("AUDIVERIS_BIN", "audiveris")
    command = [
        audiveris_bin,
        "-batch",
        "-transcribe",
        "-export",
        "-output",
        str(output_dir),
        str(input_path),
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail="Audiveris is not installed or AUDIVERIS_BIN is not set.",
        ) from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "Audiveris failed").strip()
        raise HTTPException(status_code=500, detail=f"Audiveris failed: {message}") from exc
    return completed


def find_musicxml_output(output_dir: Path) -> Path:
    candidates = sorted(
        [
            *output_dir.rglob("*.mxl"),
            *output_dir.rglob("*.musicxml"),
            *output_dir.rglob("*.xml"),
        ],
        key=lambda path: (path.suffix.lower() != ".mxl", -path.stat().st_size, str(path)),
    )
    for candidate in candidates:
        if candidate.name.lower().endswith("opus.xml"):
            continue
        return candidate
    raise HTTPException(status_code=500, detail="Audiveris completed but no MusicXML output was found.")


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


@app.get("/api/config")
def get_config():
    return {
        "supabase_enabled": isinstance(_score_store, SupabaseScoreStore),
        "auth_enabled": isinstance(_score_store, SupabaseScoreStore),
    }


class SimpleAuthRequest(BaseModel):
    username: str
    password: str


@app.get("/api/session")
def get_session(request: Request):
    user = current_app_user_for_request(request)
    return {
        "authenticated": bool(user),
        "user": {
            "id": user["id"],
            "username": user["username"],
        } if user else None,
    }


@app.post("/api/signup")
def signup(req: SimpleAuthRequest, response: Response):
    if not isinstance(_score_store, SupabaseScoreStore):
        raise HTTPException(status_code=400, detail="Signup requires Supabase-backed storage.")
    username = req.username.strip()
    password = req.password
    if not re.fullmatch(r"[A-Za-z0-9_]{3,32}", username):
        raise HTTPException(status_code=400, detail="Username must be 3-32 characters using letters, numbers, or underscore.")
    if len(password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters.")
    existing = _score_store.get_app_user_by_username(username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists.")
    created = _score_store.create_app_user(username, hash_password(password))
    if not created:
        raise HTTPException(status_code=500, detail="Could not create user.")
    session_token = create_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    _score_store.create_app_session(created["id"], hashlib.sha256(session_token.encode("utf-8")).hexdigest(), expires_at.isoformat())
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        expires=SESSION_DAYS * 24 * 60 * 60,
        path="/",
    )
    return {"ok": True, "user": {"id": created["id"], "username": created["username"]}}


@app.post("/api/login")
def login(req: SimpleAuthRequest, response: Response):
    if not isinstance(_score_store, SupabaseScoreStore):
        raise HTTPException(status_code=400, detail="Login requires Supabase-backed storage.")
    username = req.username.strip()
    password = req.password
    user = _score_store.get_app_user_by_username(username)
    if not user or not verify_password(password, user.get("password_hash") or ""):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    session_token = create_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    _score_store.create_app_session(user["id"], hashlib.sha256(session_token.encode("utf-8")).hexdigest(), expires_at.isoformat())
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        expires=SESSION_DAYS * 24 * 60 * 60,
        path="/",
    )
    return {"ok": True, "user": {"id": user["id"], "username": user["username"]}}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    if isinstance(_score_store, SupabaseScoreStore):
        token = request.cookies.get(SESSION_COOKIE_NAME, "").strip()
        if token:
            _score_store.delete_app_session(token)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/api/scores")
def list_scores(request: Request):
    if isinstance(_score_store, SupabaseScoreStore):
        user_id = require_supabase_user_id(request, "score listing")
        return _score_store.list_scores(user_id)
    return _score_store.list_scores()


@app.get("/api/scores/{name}")
def get_score(name: str, request: Request):
    if isinstance(_score_store, SupabaseScoreStore):
        user_id = require_supabase_user_id(request, "score loading")
        return _score_store.load_score(user_id, name)
    return _score_store.load_score(name)


class InstrumentUpdate(BaseModel):
    part_index: int
    instrument: str


@app.patch("/api/scores/{name}/instrument")
def update_instrument(name: str, req: InstrumentUpdate, request: Request):
    """Persist an instrument change for a part in the score .py file."""
    if isinstance(_score_store, SupabaseScoreStore):
        user_id = require_supabase_user_id(request, "score updates")
        score = _score_store.load_score(user_id, name)
        parts = score["parts"]
        if req.part_index < 0 or req.part_index >= len(parts):
            raise HTTPException(status_code=400, detail="Invalid part index")
        parts[req.part_index]["instrument"] = req.instrument
        _score_store.save_score(user_id, {
            "name": score["name"],
            "title": score.get("title") or score["name"],
            "parts": parts,
            "measure_beats": score.get("measure_beats") or [],
            "sheet_html": score.get("sheet_html") or "",
            "source_type": "converted",
        })
        return {"updated": True}

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
def delete_score(name: str, request: Request):
    if isinstance(_score_store, SupabaseScoreStore):
        user_id = current_user_id_for_request(request)
        if not user_id:
            raise HTTPException(status_code=500, detail="Authenticated user is required for Supabase-backed deletes.")
        _score_store.delete_score(user_id, name)
        return {"deleted": [name]}
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
def get_score_meta(name: str, request: Request):
    if isinstance(_score_store, SupabaseScoreStore):
        return {"name": name, "mtime": 0}
    path = os.path.join(SCORES_DIR, f"{name}.py")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Score '{name}' not found")
    return {"name": name, "mtime": os.path.getmtime(path)}


@app.get("/api/scores/{name}/sheet")
def get_sheet(name: str, request: Request):
    if isinstance(_score_store, SupabaseScoreStore):
        user_id = require_supabase_user_id(request, "sheet loading")
        html = _score_store.load_score(user_id, name).get("sheet_html") or ""
        if not html:
            raise HTTPException(status_code=404, detail="No sheet music for this score")
        html = re.sub(r"\s*<h1>.*?</h1>\s*", "\n", html, count=1, flags=re.IGNORECASE | re.DOTALL)
        return HTMLResponse(content=html)
    path = os.path.join(SCORES_DIR, f"{name}.html")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No sheet music for this score")
    try:
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
    except OSError:
        raise HTTPException(status_code=500, detail="Could not read sheet music")

    # Older generated sheet pages include a print/save heading that looks out of
    # place inside the app iframe. Strip it at serve time so existing scores do
    # not need to be regenerated.
    html = re.sub(r"\s*<h1>.*?</h1>\s*", "\n", html, count=1, flags=re.IGNORECASE | re.DOTALL)
    return HTMLResponse(content=html)


class ConvertRequest(BaseModel):
    corpus_path: str
    name: str


@app.post("/api/convert")
def convert_score(req: ConvertRequest, request: Request):
    out_dir = SCORES_DIR
    temp_dir = None
    if isinstance(_score_store, SupabaseScoreStore):
        temp_dir = tempfile.TemporaryDirectory(prefix="accompy_convert_")
        out_dir = temp_dir.name
    try:
        result = convert_score_source(f"corpus:{req.corpus_path}", name=score_name_from_input(req.name), out_dir=out_dir)
    except Exception as exc:
        if temp_dir:
            temp_dir.cleanup()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if isinstance(_score_store, SupabaseScoreStore):
        user_id = require_supabase_user_id(request, "score saving")
        saved = _score_store.save_score(user_id, {
            "name": result["name"],
            "title": result["title"],
            "parts": result["parts"],
            "measure_beats": result["measure_beats"],
            "sheet_html": Path(result["out_html"]).read_text(encoding="utf-8") if os.path.exists(result["out_html"]) else "",
            "source_type": "corpus",
        })
        if temp_dir:
            temp_dir.cleanup()
        return {
            "name": saved["name"],
            "parts": len(saved["parts"]),
            "total_notes": sum(len(part.get("notes", [])) for part in saved["parts"]),
            "has_sheet": saved["has_sheet"],
    }

    invalidate_score_cache(result["name"])
    return {
        "name": result["name"],
        "parts": result["parts_count"],
        "total_notes": result["total_notes"],
        "has_sheet": result["has_sheet"],
    }


@app.post("/api/import")
async def import_score(
    request: Request,
    files: list[UploadFile] = File(...),
    name: str = Form(""),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    score_name = score_name_from_input(name or Path(files[0].filename or "imported_score").stem)

    with tempfile.TemporaryDirectory(prefix="accompy_import_") as tmp_dir:
        work_dir = Path(tmp_dir)
        uploads_dir = work_dir / "uploads"
        output_dir = work_dir / "audiveris"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        upload_paths = [await save_uploaded_file(upload, uploads_dir, idx) for idx, upload in enumerate(files)]
        omr_input = prepare_omr_input(upload_paths, work_dir)
        run_audiveris(omr_input, output_dir)
        musicxml_path = find_musicxml_output(output_dir)

        try:
            out_dir = output_dir if isinstance(_score_store, SupabaseScoreStore) else SCORES_DIR
            result = convert_score_source(str(musicxml_path), name=score_name, out_dir=str(out_dir))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not convert Audiveris output: {exc}") from exc

    if isinstance(_score_store, SupabaseScoreStore):
        user_id = require_supabase_user_id(request, "score saving")
        saved = _score_store.save_score(user_id, {
            "name": result["name"],
            "title": result["title"],
            "parts": result["parts"],
            "measure_beats": result["measure_beats"],
            "sheet_html": Path(result["out_html"]).read_text(encoding="utf-8") if os.path.exists(result["out_html"]) else "",
            "source_type": "upload",
        })
        return {
            "name": saved["name"],
            "parts": len(saved["parts"]),
            "total_notes": sum(len(part.get("notes", [])) for part in saved["parts"]),
            "has_sheet": saved["has_sheet"],
        }

    invalidate_score_cache(result["name"])
    return {
        "name": result["name"],
        "parts": result["parts_count"],
        "total_notes": result["total_notes"],
        "has_sheet": result["has_sheet"],
    }


# Serve static files and fallback to index.html
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
