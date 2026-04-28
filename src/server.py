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
import shlex
import tempfile
import subprocess
import hashlib
import hmac
import secrets
import threading
import time
from pathlib import Path
from functools import lru_cache
from datetime import datetime, timedelta, timezone
import requests
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from src.env import load_local_env
from src.convert_score import convert_score_source, render_html, slugify_score_name
from src.fingering import apply_auto_fingering, normalize_fingering_state
from src.paths import get_static_dir
from src.storage import create_score_store, SupabaseScoreStore, _score_row_to_payload

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

STATIC_DIR = str(get_static_dir())
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
ALLOWED_PDF_SUFFIXES = {".pdf"}
ALLOWED_MUSICXML_SUFFIXES = {".xml", ".mxl", ".musicxml"}
_score_store = create_score_store()
SESSION_COOKIE_NAME = "accompy_session"
SESSION_DAYS = 30
_fingering_jobs: dict[str, dict] = {}
_active_fingering_jobs: dict[tuple[str, str], str] = {}
_fingering_jobs_lock = threading.Lock()
_session_user_cache: dict[str, tuple[float, dict | None]] = {}
_session_user_cache_lock = threading.Lock()
SESSION_USER_CACHE_TTL_SEC = 60


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


def _get_cached_app_user(raw_token: str) -> dict | None:
    with _session_user_cache_lock:
        cached = _session_user_cache.get(raw_token)
        if not cached:
            return None
        expires_at, user = cached
        if expires_at <= time.monotonic():
            _session_user_cache.pop(raw_token, None)
            return None
        return dict(user) if user else None


def _cache_app_user(raw_token: str, user: dict | None):
    with _session_user_cache_lock:
        _session_user_cache[raw_token] = (
            time.monotonic() + SESSION_USER_CACHE_TTL_SEC,
            dict(user) if user else None,
        )


def _clear_cached_app_user(raw_token: str):
    with _session_user_cache_lock:
        _session_user_cache.pop(raw_token, None)


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
            user = _get_cached_app_user(token)
            if user is None:
                user = _score_store.get_app_session_user(token)
                _cache_app_user(token, user)
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
    user = _get_cached_app_user(token)
    if user is None:
        user = _score_store.get_app_session_user(token)
        _cache_app_user(token, user)
    return user


def score_name_from_input(raw: str) -> str:
    return slugify_score_name(raw)


def ensure_fingering_state(score: dict) -> dict:
    normalized = dict(score)
    has_fingered_sheet = bool(
        normalized.get("has_fingered_sheet")
        or normalized.get("fingered_musicxml_source")
        or normalized.get("fingered_sheet_html")
    )
    fingering = normalize_fingering_state(
        normalized.get("parts") or [],
        normalized.get("fingering"),
        has_fingered_sheet=has_fingered_sheet,
    )
    normalized["fingering"] = fingering
    normalized["has_sheet"] = bool(normalized.get("has_sheet") or normalized.get("musicxml_source"))
    normalized["has_fingered_sheet"] = has_fingered_sheet
    return normalized


def render_sheet_html_from_musicxml_text(score_name: str, title: str, xml_text: str) -> str:
    if not (xml_text or "").strip():
        return ""
    with tempfile.TemporaryDirectory(prefix="accompy_sheet_variant_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        xml_path = tmp_path / f"{score_name}.musicxml"
        html_path = tmp_path / f"{score_name}.html"
        xml_path.write_text(xml_text, encoding="utf-8")
        render_html(str(xml_path), str(html_path), title)
        return html_path.read_text(encoding="utf-8") if html_path.exists() else ""


def build_fingered_score_variant(score: dict, progress_callback=None) -> tuple[str, str, dict]:
    progress = progress_callback or (lambda *_args, **_kwargs: None)
    musicxml_source = (score.get("musicxml_source") or "").strip()
    if not musicxml_source:
        raise HTTPException(status_code=400, detail="This score has no MusicXML source to annotate.")

    score_name = score.get("name") or "score"
    title = score.get("title") or score_name
    with tempfile.TemporaryDirectory(prefix="accompy_fingering_") as tmp_dir:
        work_dir = Path(tmp_dir)
        base_path = work_dir / f"{score_name}.musicxml"
        progress(10, "Preparing MusicXML")
        base_path.write_text(musicxml_source, encoding="utf-8")

        fingered_path, fingering = apply_auto_fingering(
            str(base_path),
            out_dir=str(work_dir),
            score_name=score_name,
            parts_data=score.get("parts") or [],
            progress_callback=progress,
        )
        if not fingering.get("applied"):
            reason = fingering.get("reason") or "generation_failed"
            if reason == "unsupported_parts":
                detail = "Automatic fingering is currently limited to scores with one or two parts."
            elif reason == "missing_dependency":
                detail = "PianoPlayer is not installed in the backend environment."
            else:
                detail = f"Could not generate fingering ({reason})."
            raise HTTPException(status_code=400, detail=detail)

        fingered_html_path = work_dir / f"{score_name}__fingered.html"
        progress(80, "Rendering fingered sheet")
        render_html(str(fingered_path), str(fingered_html_path), title)

        progress(92, "Finalizing output")
        fingered_musicxml_source = Path(fingered_path).read_text(encoding="utf-8")
        fingered_sheet_html = fingered_html_path.read_text(encoding="utf-8") if fingered_html_path.exists() else ""
        return fingered_musicxml_source, fingered_sheet_html, fingering


def _fingering_job_public_payload(job: dict) -> dict:
    return {
        "id": job["id"],
        "score_name": job["score_name"],
        "status": job["status"],
        "progress": job["progress"],
        "message": job["message"],
        "error": job.get("error"),
        "annotations": job.get("annotations") or 0,
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
    }


def _update_fingering_job(job_id: str, **updates) -> dict | None:
    with _fingering_jobs_lock:
        job = _fingering_jobs.get(job_id)
        if not job:
            return None
        job.update(updates)
        job["updated_at"] = datetime.now(timezone.utc).isoformat()
        return dict(job)


def _create_or_get_active_fingering_job(user_id: str, score_name: str) -> tuple[dict, bool]:
    with _fingering_jobs_lock:
        active_job_id = _active_fingering_jobs.get((user_id, score_name))
        if active_job_id:
            active_job = _fingering_jobs.get(active_job_id)
            if active_job and active_job.get("status") in {"queued", "running"}:
                return dict(active_job), False
            _active_fingering_jobs.pop((user_id, score_name), None)

        now_iso = datetime.now(timezone.utc).isoformat()
        job_id = secrets.token_urlsafe(12)
        job = {
            "id": job_id,
            "user_id": user_id,
            "score_name": score_name,
            "status": "queued",
            "progress": 0,
            "message": "Queued",
            "error": None,
            "annotations": 0,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        _fingering_jobs[job_id] = job
        _active_fingering_jobs[(user_id, score_name)] = job_id
        return dict(job), True


def _load_fingering_job_for_user(user_id: str, score_name: str, job_id: str) -> dict:
    with _fingering_jobs_lock:
        job = _fingering_jobs.get(job_id)
        if not job or job.get("user_id") != user_id or job.get("score_name") != score_name:
            raise HTTPException(status_code=404, detail="Fingering job not found.")
        return dict(job)


def _finish_fingering_job(job_id: str):
    with _fingering_jobs_lock:
        job = _fingering_jobs.get(job_id)
        if not job:
            return
        _active_fingering_jobs.pop((job["user_id"], job["score_name"]), None)


def _run_fingering_job(job_id: str):
    job = _fingering_jobs.get(job_id)
    if not job:
        return

    user_id = job["user_id"]
    score_name = job["score_name"]

    try:
        _update_fingering_job(job_id, status="running", progress=5, message="Loading score")
        score = ensure_fingering_state(_score_store.load_score(user_id, score_name))
        if score.get("fingering", {}).get("applied"):
            _update_fingering_job(
                job_id,
                status="completed",
                progress=100,
                message="Fingering already generated",
                annotations=(score.get("fingering") or {}).get("annotations") or 0,
            )
            return

        fingered_musicxml_source, fingered_sheet_html, fingering = build_fingered_score_variant(
            score,
            progress_callback=lambda percent, message: _update_fingering_job(
                job_id,
                status="running",
                progress=max(0, min(99, int(percent))),
                message=message,
            ),
        )
        _update_fingering_job(job_id, progress=96, message="Saving fingering")
        _score_store.save_score(user_id, {
            "name": score["name"],
            "title": score.get("title") or score["name"],
            "parts": score.get("parts") or [],
            "measure_beats": score.get("measure_beats") or [],
            "sheet_html": score.get("sheet_html") or "",
            "musicxml_source": score.get("musicxml_source") or "",
            "fingered_sheet_html": fingered_sheet_html,
            "fingered_musicxml_source": fingered_musicxml_source,
            "fingering": fingering,
            "source_type": score.get("source_type") or "converted",
        })
        _update_fingering_job(
            job_id,
            status="completed",
            progress=100,
            message="Fingering ready",
            annotations=fingering.get("annotations") or 0,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        _update_fingering_job(job_id, status="failed", progress=100, message=detail, error=detail)
    except Exception as exc:
        _update_fingering_job(
            job_id,
            status="failed",
            progress=100,
            message="Fingering generation failed.",
            error=str(exc),
        )
    finally:
        _finish_fingering_job(job_id)


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
    if suffixes & ALLOWED_MUSICXML_SUFFIXES:
        if len(upload_paths) != 1 or not suffixes <= ALLOWED_MUSICXML_SUFFIXES:
            raise HTTPException(status_code=400, detail="Upload one MusicXML file, one PDF, or one/more image files.")
        return upload_paths[0]

    if suffixes & ALLOWED_PDF_SUFFIXES:
        if len(upload_paths) != 1 or not suffixes <= ALLOWED_PDF_SUFFIXES:
            raise HTTPException(status_code=400, detail="Upload one MusicXML file, one PDF, or one/more image files.")
        return upload_paths[0]

    if not suffixes or not suffixes <= ALLOWED_IMAGE_SUFFIXES:
        raise HTTPException(status_code=400, detail="Supported uploads are MusicXML (.xml, .mxl, .musicxml), PDF, PNG, JPG, and JPEG.")

    return combine_images_to_pdf(upload_paths, work_dir / "input.pdf")


def run_audiveris(input_path: Path, output_dir: Path):
    audiveris_bin = os.getenv("AUDIVERIS_BIN", "audiveris").strip() or "audiveris"
    command = [
        *shlex.split(audiveris_bin),
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
    _cache_app_user(session_token, {"id": created["id"], "username": created["username"]})
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
    _cache_app_user(session_token, {"id": user["id"], "username": user["username"]})
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
            _clear_cached_app_user(token)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/api/scores")
def list_scores(request: Request):
    user_id = require_supabase_user_id(request, "score listing")
    return _score_store.list_scores(user_id)


@app.get("/api/scores/{name}")
def get_score(name: str, request: Request):
    user_id = require_supabase_user_id(request, "score loading")
    return ensure_fingering_state(_score_store.load_score(user_id, name))


class InstrumentUpdate(BaseModel):
    part_index: int
    instrument: str


@app.patch("/api/scores/{name}/instrument")
def update_instrument(name: str, req: InstrumentUpdate, request: Request):
    """Persist an instrument change for a part in the stored score."""
    user_id = require_supabase_user_id(request, "score updates")
    score = ensure_fingering_state(_score_store.load_score(user_id, name))
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
        "musicxml_source": score.get("musicxml_source") or "",
        "fingering": score.get("fingering") or {},
        "source_type": score.get("source_type") or "converted",
    })
    return {"updated": True}


@app.delete("/api/scores/{name}")
def delete_score(name: str, request: Request):
    user_id = require_supabase_user_id(request, "deletes")
    _score_store.delete_score(user_id, name)
    return {"deleted": [name]}


@app.get("/api/scores/{name}/meta")
def get_score_meta(name: str, request: Request):
    return {"name": name, "mtime": 0}


@app.get("/api/scores/{name}/sheet")
def get_sheet(name: str, request: Request, variant: str = "base"):
    user_id = require_supabase_user_id(request, "sheet loading")
    row = _score_store.load_score_row(user_id, name)
    score = ensure_fingering_state(_score_row_to_payload(row))
    title = score.get("title") or score.get("name") or name
    score_data = row.get("score_data") or {}
    if variant == "fingered":
        html = (score_data.get("fingered_sheet_html") or "").strip()
        if (not html or "<svg" not in html) and score.get("fingered_musicxml_source"):
            html = render_sheet_html_from_musicxml_text(
                score.get("name") or name,
                title,
                score.get("fingered_musicxml_source") or "",
            )
    else:
        html = (row.get("sheet_html") or score.get("sheet_html") or "").strip()
        if (not html or "<svg" not in html) and score.get("musicxml_source"):
            html = render_sheet_html_from_musicxml_text(
                score.get("name") or name,
                title,
                score.get("musicxml_source") or "",
            )
    if not html or "<svg" not in html:
        raise HTTPException(status_code=404, detail="No sheet music for this score")
    html = re.sub(r"\s*<h1>.*?</h1>\s*", "\n", html, count=1, flags=re.IGNORECASE | re.DOTALL)
    return HTMLResponse(content=html)


@app.post("/api/scores/{name}/fingering/generate")
def generate_score_fingering(name: str, request: Request):
    user_id = require_supabase_user_id(request, "fingering generation")
    score = ensure_fingering_state(_score_store.load_score(user_id, name))
    if score.get("fingering", {}).get("applied"):
        raise HTTPException(status_code=400, detail="This score already has generated fingering.")

    job, created = _create_or_get_active_fingering_job(user_id, name)
    if created:
        worker = threading.Thread(target=_run_fingering_job, args=(job["id"],), daemon=True)
        worker.start()
    return JSONResponse(content=_fingering_job_public_payload(job), status_code=202)


@app.get("/api/scores/{name}/fingering/jobs/{job_id}")
def get_score_fingering_job(name: str, job_id: str, request: Request):
    user_id = require_supabase_user_id(request, "fingering status checks")
    job = _load_fingering_job_for_user(user_id, name, job_id)
    return _fingering_job_public_payload(job)


class ConvertRequest(BaseModel):
    corpus_path: str
    name: str


@app.post("/api/convert")
def convert_score(req: ConvertRequest, request: Request):
    temp_dir = tempfile.TemporaryDirectory(prefix="accompy_convert_")
    out_dir = temp_dir.name
    try:
        result = convert_score_source(f"corpus:{req.corpus_path}", name=score_name_from_input(req.name), out_dir=out_dir)
    except Exception as exc:
        temp_dir.cleanup()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user_id = require_supabase_user_id(request, "score saving")
    saved = _score_store.save_score(user_id, {
        "name": result["name"],
        "title": result["title"],
        "parts": result["parts"],
        "measure_beats": result["measure_beats"],
        "sheet_html": Path(result["out_html"]).read_text(encoding="utf-8") if os.path.exists(result["out_html"]) else "",
        "musicxml_source": Path(result["render_source_path"]).read_text(encoding="utf-8") if os.path.exists(result["render_source_path"]) else "",
        "fingered_sheet_html": "",
        "fingered_musicxml_source": "",
        "fingering": result.get("fingering") or {},
        "source_type": "corpus",
    })
    temp_dir.cleanup()
    return {
        "name": saved["name"],
        "parts": len(saved["parts"]),
        "total_notes": sum(len(part.get("notes", [])) for part in saved["parts"]),
        "has_sheet": saved["has_sheet"],
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
        import_input = prepare_omr_input(upload_paths, work_dir)
        if import_input.suffix.lower() in ALLOWED_MUSICXML_SUFFIXES:
            musicxml_path = import_input
        else:
            run_audiveris(import_input, output_dir)
            musicxml_path = find_musicxml_output(output_dir)

        try:
            result = convert_score_source(str(musicxml_path), name=score_name, out_dir=str(output_dir))
        except Exception as exc:
            source_label = "uploaded MusicXML" if musicxml_path.suffix.lower() in ALLOWED_MUSICXML_SUFFIXES else "Audiveris output"
            raise HTTPException(status_code=400, detail=f"Could not convert {source_label}: {exc}") from exc

        user_id = require_supabase_user_id(request, "score saving")
        saved = _score_store.save_score(user_id, {
            "name": result["name"],
            "title": result["title"],
            "parts": result["parts"],
            "measure_beats": result["measure_beats"],
            "sheet_html": Path(result["out_html"]).read_text(encoding="utf-8") if os.path.exists(result["out_html"]) else "",
            "musicxml_source": Path(result["render_source_path"]).read_text(encoding="utf-8") if os.path.exists(result["render_source_path"]) else "",
            "fingered_sheet_html": "",
            "fingered_musicxml_source": "",
            "fingering": result.get("fingering") or {},
            "source_type": "upload",
        })
    return {
        "name": saved["name"],
        "parts": len(saved["parts"]),
        "total_notes": sum(len(part.get("notes", [])) for part in saved["parts"]),
        "has_sheet": saved["has_sheet"],
    }


# Serve static files and fallback to index.html
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
