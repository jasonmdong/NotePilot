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
import shutil
import tempfile
import subprocess
import zipfile
import hashlib
import hmac
import secrets
import threading
import time
from pathlib import Path
from functools import lru_cache
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape
import requests
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel
from src.env import load_local_env
from src.convert_score import convert_lilypond_parts_to_musicxml, convert_score_source, render_html, slugify_score_name
from src.fingering import apply_auto_fingering, normalize_fingering_state, stack_fingering_chord_numbers_in_html
from src.paths import get_static_dir
from src.storage import create_score_store, SupabaseScoreStore, _score_row_to_payload

load_local_env()

app = FastAPI()


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            headers = dict(scope.get("headers") or [])
            accept = headers.get(b"accept", b"").decode("latin-1")
            if exc.status_code == 404 and "text/html" in accept:
                return await super().get_response("index.html", scope)
            raise


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
ALLOWED_MUSESCORE_SUFFIXES = {".mscx", ".mscz"}
ALLOWED_LILYPOND_SUFFIXES = {".ily", ".ly"}
ALLOWED_ZIP_SUFFIXES = {".zip"}
ALLOWED_DIRECT_SCORE_SUFFIXES = ALLOWED_MUSICXML_SUFFIXES | ALLOWED_MUSESCORE_SUFFIXES
LILYPOND_HELPER_STEMS = {"global", "music", "midi"}
_score_store = create_score_store()
SESSION_COOKIE_NAME = "accompy_session"
SESSION_DAYS = 30
_fingering_jobs: dict[str, dict] = {}
_active_fingering_jobs: dict[tuple[str, str], str] = {}
_fingering_jobs_lock = threading.Lock()
_import_jobs: dict[str, dict] = {}
_import_jobs_lock = threading.Lock()
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


def set_app_session_cookie(response: Response, session_token: str):
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


def create_app_session_response(response: Response, user: dict) -> dict:
    session_token = create_session_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    _score_store.create_app_session(
        user["id"],
        hashlib.sha256(session_token.encode("utf-8")).hexdigest(),
        expires_at.isoformat(),
    )
    public_user = {"id": user["id"], "username": user["username"]}
    _cache_app_user(session_token, public_user)
    set_app_session_cookie(response, session_token)
    return {"ok": True, "user": public_user}


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


def render_sheet_html_from_musicxml_text(
    score_name: str,
    title: str,
    xml_text: str,
    *,
    stack_fingering_chords: bool = False,
) -> str:
    if not (xml_text or "").strip():
        return ""
    with tempfile.TemporaryDirectory(prefix="accompy_sheet_variant_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        xml_path = tmp_path / f"{score_name}.musicxml"
        html_path = tmp_path / f"{score_name}.html"
        xml_path.write_text(xml_text, encoding="utf-8")
        render_html(str(xml_path), str(html_path), title)
        html = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
        return stack_fingering_chord_numbers_in_html(html) if stack_fingering_chords else html


def parse_sheet_part_indices(raw: str | None) -> list[int] | None:
    if raw is None:
        return None
    indices = []
    for item in str(raw).split(","):
        item = item.strip()
        if not item:
            continue
        try:
            idx = int(item)
        except ValueError:
            continue
        if idx >= 0 and idx not in indices:
            indices.append(idx)
    return indices or None


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def filter_musicxml_parts(xml_text: str, part_indices: list[int] | None) -> str:
    if not part_indices:
        return xml_text
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        return ""

    part_list = next((child for child in list(root) if _xml_local_name(child.tag) == "part-list"), None)
    if part_list is None:
        return ""

    score_parts = [child for child in list(part_list) if _xml_local_name(child.tag) == "score-part"]
    selected_ids = {
        score_parts[idx].attrib.get("id")
        for idx in part_indices
        if 0 <= idx < len(score_parts) and score_parts[idx].attrib.get("id")
    }
    if not selected_ids:
        return ""
    if len(selected_ids) == len(score_parts):
        return xml_text

    for child in list(part_list):
        if _xml_local_name(child.tag) == "score-part" and child.attrib.get("id") not in selected_ids:
            part_list.remove(child)

    for child in list(root):
        if _xml_local_name(child.tag) == "part" and child.attrib.get("id") not in selected_ids:
            root.remove(child)

    return ET.tostring(root, encoding="unicode")


def midi_to_musicxml_pitch(midi: int) -> str:
    steps = [
        ("C", 0),
        ("C", 1),
        ("D", 0),
        ("D", 1),
        ("E", 0),
        ("F", 0),
        ("F", 1),
        ("G", 0),
        ("G", 1),
        ("A", 0),
        ("A", 1),
        ("B", 0),
    ]
    midi = int(midi)
    step, alter = steps[midi % 12]
    octave = midi // 12 - 1
    alter_xml = f"<alter>{alter}</alter>" if alter else ""
    return f"<pitch><step>{step}</step>{alter_xml}<octave>{octave}</octave></pitch>"


def event_pitches(event) -> list[int]:
    if not isinstance(event, list) or not event:
        return []
    raw = event[0]
    pitches = raw if isinstance(raw, list) else [raw]
    result = []
    for pitch in pitches:
        try:
            result.append(int(pitch))
        except (TypeError, ValueError):
            continue
    return result


def synthesize_selected_parts_musicxml(score: dict, part_indices: list[int], title: str) -> str:
    parts = score.get("parts") or []
    selected = [
        (idx, parts[idx])
        for idx in part_indices
        if 0 <= idx < len(parts)
    ]
    if not selected:
        return ""

    divisions = 480
    measure_starts = [
        float(beat)
        for beat in (score.get("measure_beats") or [])
        if isinstance(beat, (int, float))
    ]
    max_end = 0.0
    for _, part in selected:
        for event in part.get("notes") or []:
            if not isinstance(event, list) or len(event) < 2:
                continue
            beat = float(event[1] or 0)
            duration = float(event[2] or 1) if len(event) > 2 else 1
            max_end = max(max_end, beat + max(duration, 0))
    if not measure_starts:
        measure_starts = [0.0]
        while measure_starts[-1] < max_end:
            measure_starts.append(measure_starts[-1] + 4.0)
    if len(measure_starts) == 1 or measure_starts[-1] < max_end:
        span = 4.0
        if len(measure_starts) >= 2:
            spans = [b - a for a, b in zip(measure_starts, measure_starts[1:]) if b > a]
            if spans:
                span = sorted(spans)[len(spans) // 2]
        while measure_starts[-1] < max_end:
            measure_starts.append(measure_starts[-1] + span)

    def duration_xml(beats: float) -> str:
        duration = max(1, int(round(max(0.0, beats) * divisions)))
        return f"<duration>{duration}</duration>"

    def rest_xml(beats: float) -> str:
        if beats <= 0.0001:
            return ""
        return f"<note><rest />{duration_xml(beats)}<voice>1</voice></note>"

    part_list_xml = []
    parts_xml = []
    for output_idx, (_part_idx, part) in enumerate(selected, start=1):
        part_id = f"P{output_idx}"
        part_name = xml_escape(str(part.get("name") or f"Part {output_idx}"))
        part_list_xml.append(f'<score-part id="{part_id}"><part-name>{part_name}</part-name></score-part>')
        events = sorted(
            [event for event in (part.get("notes") or []) if isinstance(event, list) and len(event) >= 2],
            key=lambda event: float(event[1] or 0),
        )
        measures_xml = []
        for measure_idx, start in enumerate(measure_starts):
            end = measure_starts[measure_idx + 1] if measure_idx + 1 < len(measure_starts) else max(max_end, start + 4.0)
            attrs = ""
            if measure_idx == 0:
                attrs = (
                    f"<attributes><divisions>{divisions}</divisions>"
                    "<key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time>"
                    "<clef><sign>G</sign><line>2</line></clef></attributes>"
                )
            cursor = start
            notes_xml = []
            for event in events:
                beat = float(event[1] or 0)
                if beat < start - 0.0001 or beat >= end - 0.0001:
                    continue
                if beat > cursor:
                    notes_xml.append(rest_xml(beat - cursor))
                event_duration = float(event[2] or 1) if len(event) > 2 else 1
                clipped_duration = max(0.0, min(event_duration, end - beat))
                pitches = event_pitches(event)
                for pitch_idx, pitch in enumerate(pitches):
                    chord = "<chord />" if pitch_idx else ""
                    notes_xml.append(
                        f"<note>{chord}{midi_to_musicxml_pitch(pitch)}"
                        f"{duration_xml(clipped_duration)}<voice>1</voice></note>"
                    )
                cursor = max(cursor, beat + clipped_duration)
            if cursor < end:
                notes_xml.append(rest_xml(end - cursor))
            measures_xml.append(
                f'<measure number="{measure_idx + 1}">{attrs}{"".join(notes_xml)}</measure>'
            )
        parts_xml.append(f'<part id="{part_id}">{"".join(measures_xml)}</part>')

    escaped_title = xml_escape(title or "Selected parts")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<score-partwise version="3.1">'
        f"<movement-title>{escaped_title}</movement-title>"
        f"<part-list>{''.join(part_list_xml)}</part-list>"
        f"{''.join(parts_xml)}"
        "</score-partwise>"
    )


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


def _import_job_public_payload(job: dict) -> dict:
    return {
        "id": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "message": job["message"],
        "error": job.get("error"),
        "result": job.get("result"),
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
    }


def _create_import_job(user_id: str, score_name: str, upload_paths: list[Path], work_dir: Path, output_dir: Path) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    job_id = secrets.token_urlsafe(12)
    job = {
        "id": job_id,
        "user_id": user_id,
        "score_name": score_name,
        "upload_paths": [str(path) for path in upload_paths],
        "work_dir": str(work_dir),
        "output_dir": str(output_dir),
        "status": "queued",
        "progress": 4,
        "message": "Queued import",
        "error": None,
        "result": None,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    with _import_jobs_lock:
        _import_jobs[job_id] = job
    return dict(job)


def _update_import_job(job_id: str, **updates) -> dict | None:
    with _import_jobs_lock:
        job = _import_jobs.get(job_id)
        if not job:
            return None
        job.update(updates)
        job["updated_at"] = datetime.now(timezone.utc).isoformat()
        return dict(job)


def _load_import_job_for_user(user_id: str, job_id: str) -> dict:
    with _import_jobs_lock:
        job = _import_jobs.get(job_id)
        if not job or job.get("user_id") != user_id:
            raise HTTPException(status_code=404, detail="Import job not found.")
        return dict(job)


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


def extract_lilypond_zip(zip_path: Path, work_dir: Path) -> list[Path]:
    lily_dir = work_dir / "lilypond"
    lily_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            lily_members = [
                member for member in zf.infolist()
                if not member.is_dir()
                and not member.filename.startswith("__MACOSX/")
                and Path(member.filename).suffix.lower() == ".ily"
            ]
            members = lily_members or [
                member for member in zf.infolist()
                if not member.is_dir()
                and not member.filename.startswith("__MACOSX/")
                and Path(member.filename).suffix.lower() == ".ly"
            ]
            if not members:
                raise HTTPException(status_code=400, detail="The .zip file must contain one or more .ily or .ly files.")

            extracted = []
            part_members = [
                member for member in members
                if Path(member.filename).stem.lower() not in LILYPOND_HELPER_STEMS
            ] or members
            for index, member in enumerate(sorted(part_members, key=lambda item: item.filename.lower())):
                safe_stem = score_name_from_input(Path(member.filename).stem or f"part_{index + 1}")
                dest = lily_dir / f"{index:02d}_{safe_stem}{Path(member.filename).suffix.lower()}"
                with zf.open(member) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
                extracted.append(dest)
            return extracted
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="The uploaded .zip file could not be read.") from exc


def prepare_omr_input(upload_paths: list[Path], work_dir: Path) -> Path | list[Path]:
    suffixes = {path.suffix.lower() for path in upload_paths}
    if suffixes & ALLOWED_DIRECT_SCORE_SUFFIXES:
        if len(upload_paths) != 1 or not suffixes <= ALLOWED_DIRECT_SCORE_SUFFIXES:
            raise HTTPException(status_code=400, detail="Upload one MusicXML/MuseScore file, LilyPond file set, .zip bundle, one PDF, or one/more image files.")
        return upload_paths[0]

    if suffixes & ALLOWED_LILYPOND_SUFFIXES:
        if not suffixes <= ALLOWED_LILYPOND_SUFFIXES:
            raise HTTPException(status_code=400, detail="Upload only .ily/.ly files when importing LilyPond parts.")
        part_paths = [
            path for path in upload_paths
            if path.stem.lower() not in LILYPOND_HELPER_STEMS
        ] or upload_paths
        return sorted(part_paths)

    if suffixes & ALLOWED_ZIP_SUFFIXES:
        if len(upload_paths) != 1 or not suffixes <= ALLOWED_ZIP_SUFFIXES:
            raise HTTPException(status_code=400, detail="Upload one .zip bundle, not a mix of .zip and other files.")
        return extract_lilypond_zip(upload_paths[0], work_dir)

    if suffixes & ALLOWED_PDF_SUFFIXES:
        if len(upload_paths) != 1 or not suffixes <= ALLOWED_PDF_SUFFIXES:
            raise HTTPException(status_code=400, detail="Upload one MusicXML/MuseScore file, LilyPond file set, .zip bundle, one PDF, or one/more image files.")
        return upload_paths[0]

    if not suffixes or not suffixes <= ALLOWED_IMAGE_SUFFIXES:
        raise HTTPException(status_code=400, detail="Supported uploads are MusicXML (.xml, .mxl, .musicxml), MuseScore (.mscx, .mscz), LilyPond (.ily/.ly or .zip), PDF, PNG, JPG, and JPEG.")

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


def convert_and_save_import(
    user_id: str,
    score_name: str,
    upload_paths: list[Path],
    work_dir: Path,
    output_dir: Path,
    progress_callback=None,
) -> dict:
    def progress(percent: int, message: str):
        if progress_callback:
            progress_callback(max(0, min(99, int(percent))), message)

    progress(10, "Preparing upload")
    import_input = prepare_omr_input(upload_paths, work_dir)
    if isinstance(import_input, list):
        progress(34, f"Preparing {len(import_input)} LilyPond parts")
        musicxml_path = Path(convert_lilypond_parts_to_musicxml(
            [str(path) for path in import_input],
            str(output_dir),
            score_name,
            progress_callback=progress,
        ))
    elif import_input.suffix.lower() in ALLOWED_DIRECT_SCORE_SUFFIXES:
        progress(34, "Reading uploaded score")
        musicxml_path = import_input
    else:
        progress(20, "Starting Audiveris")
        run_audiveris(import_input, output_dir)
        progress(68, "Collecting Audiveris output")
        musicxml_path = find_musicxml_output(output_dir)

    try:
        progress(76, "Building NotePilot score")
        result = convert_score_source(str(musicxml_path), name=score_name, out_dir=str(output_dir))
    except Exception as exc:
        suffix = musicxml_path.suffix.lower()
        source_label = "uploaded MusicXML/MuseScore file" if suffix in ALLOWED_DIRECT_SCORE_SUFFIXES else "Audiveris output"
        raise HTTPException(status_code=400, detail=f"Could not convert {source_label}: {exc}") from exc

    progress(92, "Saving imported score")
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


def _run_import_job(job_id: str):
    with _import_jobs_lock:
        job = dict(_import_jobs.get(job_id) or {})
    if not job:
        return

    work_dir = Path(job["work_dir"])
    try:
        _update_import_job(job_id, status="running", progress=8, message="Preparing upload")
        result = convert_and_save_import(
            job["user_id"],
            job["score_name"],
            [Path(path) for path in job["upload_paths"]],
            work_dir,
            Path(job["output_dir"]),
            progress_callback=lambda percent, message: _update_import_job(
                job_id,
                status="running",
                progress=percent,
                message=message,
            ),
        )
        _update_import_job(
            job_id,
            status="completed",
            progress=100,
            message="Import complete",
            result=result,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        _update_import_job(job_id, status="failed", progress=100, message=detail, error=detail)
    except Exception as exc:
        _update_import_job(
            job_id,
            status="failed",
            progress=100,
            message="Import failed.",
            error=str(exc),
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


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
        "google_auth_enabled": bool(
            isinstance(_score_store, SupabaseScoreStore)
            and os.getenv("SUPABASE_URL", "").strip()
            and os.getenv("SUPABASE_ANON_KEY", "").strip()
        ),
    }


class SimpleAuthRequest(BaseModel):
    username: str
    password: str


class SupabaseTokenRequest(BaseModel):
    access_token: str


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
    return create_app_session_response(response, created)


@app.post("/api/login")
def login(req: SimpleAuthRequest, response: Response):
    if not isinstance(_score_store, SupabaseScoreStore):
        raise HTTPException(status_code=400, detail="Login requires Supabase-backed storage.")
    username = req.username.strip()
    password = req.password
    user = _score_store.get_app_user_by_username(username)
    if not user or not verify_password(password, user.get("password_hash") or ""):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return create_app_session_response(response, user)


@app.get("/api/auth/google/start")
def start_google_auth(request: Request):
    if not isinstance(_score_store, SupabaseScoreStore):
        raise HTTPException(status_code=400, detail="Google sign-in requires Supabase-backed storage.")
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    anon_key = os.getenv("SUPABASE_ANON_KEY", "").strip()
    if not (supabase_url and anon_key):
        raise HTTPException(status_code=400, detail="Google sign-in requires SUPABASE_URL and SUPABASE_ANON_KEY.")

    origin = public_app_origin(request)
    redirect_to = f"{origin}/auth/callback"
    auth_url = (
        f"{supabase_url}/auth/v1/authorize"
        f"?provider=google"
        f"&redirect_to={quote(redirect_to, safe='')}"
    )
    return RedirectResponse(auth_url, status_code=302)


def public_app_origin(request: Request) -> str:
    configured_origin = os.getenv("APP_PUBLIC_URL", "").strip().rstrip("/")
    if configured_origin:
        return configured_origin

    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    forwarded_host = request.headers.get("x-forwarded-host", "").split(",", 1)[0].strip()
    forwarded_port = request.headers.get("x-forwarded-port", "").split(",", 1)[0].strip()
    if forwarded_proto and forwarded_host:
        host = forwarded_host
        if forwarded_port and ":" not in host and forwarded_port not in {"80", "443"}:
            host = f"{host}:{forwarded_port}"
        return f"{forwarded_proto}://{host}"

    for header_name in ("x-original-host", "x-real-host", "host"):
        host = request.headers.get(header_name, "").split(",", 1)[0].strip()
        if host and not host.startswith(("127.0.0.1", "localhost")):
            proto = forwarded_proto or "https"
            return f"{proto}://{host}"

    space_host = os.getenv("SPACE_HOST", "").strip().rstrip("/")
    if space_host:
        return space_host if space_host.startswith(("http://", "https://")) else f"https://{space_host}"

    space_id = os.getenv("SPACE_ID", "").strip()
    if "/" in space_id:
        owner, space = space_id.split("/", 1)
        return f"https://{owner}-{space.replace('_', '-')}.hf.space"

    return str(request.base_url).rstrip("/")


@app.post("/api/auth/supabase-token")
def login_with_supabase_token(req: SupabaseTokenRequest, response: Response):
    if not isinstance(_score_store, SupabaseScoreStore):
        raise HTTPException(status_code=400, detail="Google sign-in requires Supabase-backed storage.")
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    anon_key = os.getenv("SUPABASE_ANON_KEY", "").strip()
    access_token = req.access_token.strip()
    if not (supabase_url and anon_key and access_token):
        raise HTTPException(status_code=400, detail="Missing Google sign-in token.")

    auth_response = requests.get(
        f"{supabase_url}/auth/v1/user",
        headers={
            "apikey": anon_key,
            "Authorization": f"Bearer {access_token}",
        },
        timeout=15,
    )
    if auth_response.status_code != 200:
        raise HTTPException(status_code=401, detail="Google sign-in token was not accepted.")

    supabase_user = auth_response.json()
    app_metadata = supabase_user.get("app_metadata") or {}
    user_metadata = supabase_user.get("user_metadata") or {}
    provider = app_metadata.get("provider")
    providers = app_metadata.get("providers") or []
    issuer = str(user_metadata.get("iss") or "")
    if provider != "google" and "google" not in providers and "accounts.google.com" not in issuer:
        raise HTTPException(status_code=400, detail="This sign-in token is not from Google.")

    supabase_id = str(supabase_user.get("id") or "").replace("-", "")
    if not supabase_id:
        raise HTTPException(status_code=400, detail="Google sign-in did not return a user id.")
    email = str(supabase_user.get("email") or user_metadata.get("email") or "").strip().lower()
    username = email or f"google_{supabase_id[:24]}"
    user = _score_store.get_app_user_by_username(username)
    if not user:
        user = _score_store.create_app_user(username, hash_password(secrets.token_urlsafe(32)))
    if not user:
        raise HTTPException(status_code=500, detail="Could not create Google user.")
    return create_app_session_response(response, user)


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
    return ensure_fingering_state(_score_store.load_score(user_id, name, include_sheet_assets=False))


class InstrumentUpdate(BaseModel):
    part_index: int
    instrument: str


class ScoreTitleUpdate(BaseModel):
    title: str


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


@app.patch("/api/scores/{name}/title")
def update_score_title(name: str, req: ScoreTitleUpdate, request: Request):
    user_id = require_supabase_user_id(request, "score renaming")
    title = req.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty.")
    if len(title) > 120:
        raise HTTPException(status_code=400, detail="Title must be 120 characters or fewer.")
    renamed = _score_store.rename_score_title(user_id, name, title)
    return {"name": renamed["name"], "title": renamed["title"]}


@app.delete("/api/scores/{name}")
def delete_score(name: str, request: Request):
    user_id = require_supabase_user_id(request, "deletes")
    _score_store.delete_score(user_id, name)
    return {"deleted": [name]}


@app.get("/api/scores/{name}/meta")
def get_score_meta(name: str, request: Request):
    return {"name": name, "mtime": 0}


@app.get("/api/scores/{name}/sheet")
def get_sheet(name: str, request: Request, variant: str = "base", parts: str | None = None):
    user_id = require_supabase_user_id(request, "sheet loading")
    row = _score_store.load_score_row(user_id, name)
    score = ensure_fingering_state(_score_row_to_payload(row))
    title = score.get("title") or score.get("name") or name
    score_data = row.get("score_data") or {}
    part_indices = parse_sheet_part_indices(parts)
    cached_base_html = (row.get("sheet_html") or score.get("sheet_html") or "").strip()
    cached_fingered_html = (score_data.get("fingered_sheet_html") or "").strip()

    def render_filtered_source(xml_source: str, *, stack_fingering_chords: bool = False) -> str:
        filtered_source = filter_musicxml_parts(xml_source, part_indices)
        if not filtered_source:
            return ""
        return render_sheet_html_from_musicxml_text(
            score.get("name") or name,
            title,
            filtered_source,
            stack_fingering_chords=stack_fingering_chords,
        )

    if variant == "fingered":
        html = ""
        if score.get("fingered_musicxml_source"):
            html = render_filtered_source(
                score.get("fingered_musicxml_source") or "",
                stack_fingering_chords=True,
            )
        if (not html or "<svg" not in html) and not part_indices:
            html = stack_fingering_chord_numbers_in_html(cached_fingered_html)
    else:
        html = "" if part_indices else cached_base_html
        if (not html or "<svg" not in html) and score.get("musicxml_source"):
            html = render_filtered_source(score.get("musicxml_source") or "")
            if html and "<svg" in html and not part_indices:
                try:
                    _score_store.update_score_sheet_html(user_id, name, html)
                except Exception as exc:
                    print(f"Could not cache rendered sheet HTML for {name}: {exc}")
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
        user_id = require_supabase_user_id(request, "score saving")
        return convert_and_save_import(user_id, score_name, upload_paths, work_dir, output_dir)


@app.post("/api/import/start")
async def start_import_score(
    request: Request,
    files: list[UploadFile] = File(...),
    name: str = Form(""),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    user_id = require_supabase_user_id(request, "score saving")
    score_name = score_name_from_input(name or Path(files[0].filename or "imported_score").stem)
    work_dir = Path(tempfile.mkdtemp(prefix="accompy_import_"))
    uploads_dir = work_dir / "uploads"
    output_dir = work_dir / "audiveris"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        upload_paths = [await save_uploaded_file(upload, uploads_dir, idx) for idx, upload in enumerate(files)]
        job = _create_import_job(user_id, score_name, upload_paths, work_dir, output_dir)
        thread = threading.Thread(target=_run_import_job, args=(job["id"],), daemon=True)
        thread.start()
        return _import_job_public_payload(job)
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise


@app.get("/api/import/jobs/{job_id}")
def get_import_job(job_id: str, request: Request):
    user_id = require_supabase_user_id(request, "score importing")
    return _import_job_public_payload(_load_import_job_for_user(user_id, job_id))


# Serve static files and fallback to index.html for browser-routed score URLs.
app.mount("/", SPAStaticFiles(directory=STATIC_DIR, html=True), name="static")
