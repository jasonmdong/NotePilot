import importlib.util
import hashlib
import os
from pathlib import Path
from datetime import datetime, timezone

import requests
from fastapi import HTTPException

from src.paths import get_scores_dir


def _score_row_to_payload(row: dict) -> dict:
    score_data = row.get("score_data") or {}
    parts = score_data.get("parts") or []
    right_hand = parts[0]["notes"] if parts else []
    left_hand = []
    for part in parts[1:]:
        for event in part.get("notes", []):
            pitches = event[0] if isinstance(event[0], list) else [event[0]]
            left_hand.append([pitches, event[1]])
    left_hand.sort(key=lambda event: event[1])
    return {
        "name": row.get("slug") or row.get("id"),
        "title": row.get("title") or row.get("slug") or row.get("id"),
        "parts": parts,
        "has_sheet": bool(row.get("sheet_html")),
        "measure_beats": row.get("measure_beats") or [],
        "right_hand": right_hand,
        "left_hand": left_hand,
        "sheet_html": row.get("sheet_html") or "",
    }


class LocalScoreStore:
    def __init__(self):
        self.scores_dir = Path(get_scores_dir())

    def list_scores(self):
        names = sorted(f.stem for f in self.scores_dir.glob("*.py"))
        return {
            "scores": names,
            "items": [
                {
                    "name": name,
                    "has_sheet": (self.scores_dir / f"{name}.html").exists(),
                }
                for name in names
            ],
        }

    def load_score(self, name: str):
        path = self.scores_dir / f"{name}.py"
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Score '{name}' not found")
        spec = importlib.util.spec_from_file_location("_score", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        parts = getattr(mod, "PARTS", [
            {"name": "Melody", "notes": [[p, b] for p, b in mod.RIGHT_HAND]},
            {"name": "Accompaniment", "notes": [[p, b] for p, b in mod.LEFT_HAND]},
        ])
        return {
            "name": name,
            "title": name,
            "parts": parts,
            "has_sheet": (self.scores_dir / f"{name}.html").exists(),
            "measure_beats": list(getattr(mod, "MEASURE_BEATS", [])),
            "right_hand": mod.RIGHT_HAND,
            "left_hand": mod.LEFT_HAND,
            "sheet_html": (self.scores_dir / f"{name}.html").read_text(encoding="utf-8") if (self.scores_dir / f"{name}.html").exists() else "",
        }


class SupabaseScoreStore:
    def __init__(self, url: str, service_role_key: str):
        self.base_url = url.rstrip("/")
        self.rest_url = f"{self.base_url}/rest/v1"
        self.headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, *, params=None, json_body=None, headers=None):
        response = requests.request(
            method,
            f"{self.rest_url}/{path.lstrip('/')}",
            params=params,
            json=json_body,
            headers={**self.headers, **(headers or {})},
            timeout=20,
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=500, detail=f"Supabase error: {response.text}")
        if not response.text:
            return None
        return response.json()

    def list_scores(self, user_id: str):
        rows = self._request(
            "GET",
            "scores",
            params={
                "select": "slug,sheet_html",
                "user_id": f"eq.{user_id}",
                "order": "created_at.desc",
            },
        ) or []
        names = [row["slug"] for row in rows if row.get("slug")]
        return {
            "scores": names,
            "items": [
                {
                    "name": row["slug"],
                    "has_sheet": bool(row.get("sheet_html")),
                }
                for row in rows if row.get("slug")
            ],
        }

    def load_score(self, user_id: str, name: str):
        rows = self._request(
            "GET",
            "scores",
            params={
                "select": "id,user_id,slug,title,source_type,score_data,measure_beats,sheet_html,created_at",
                "user_id": f"eq.{user_id}",
                "slug": f"eq.{name}",
                "limit": "1",
            },
        ) or []
        if not rows:
            raise HTTPException(status_code=404, detail=f"Score '{name}' not found")
        return _score_row_to_payload(rows[0])

    def save_score(self, user_id: str, payload: dict):
        row = {
            "user_id": user_id,
            "slug": payload["name"],
            "title": payload.get("title") or payload["name"],
            "source_type": payload.get("source_type") or "converted",
            "score_data": {
                "parts": payload["parts"],
            },
            "measure_beats": payload.get("measure_beats") or [],
            "sheet_html": payload.get("sheet_html") or "",
        }
        existing = self._request(
            "GET",
            "scores",
            params={
                "select": "id",
                "user_id": f"eq.{user_id}",
                "slug": f"eq.{payload['name']}",
                "limit": "1",
            },
        ) or []
        if existing:
            result = self._request(
                "PATCH",
                "scores",
                params={
                    "user_id": f"eq.{user_id}",
                    "slug": f"eq.{payload['name']}",
                    "select": "id,user_id,slug,title,source_type,score_data,measure_beats,sheet_html,created_at",
                },
                json_body=row,
                headers={"Prefer": "return=representation"},
            ) or []
        else:
            result = self._request(
                "POST",
                "scores",
                params={"select": "id,user_id,slug,title,source_type,score_data,measure_beats,sheet_html,created_at"},
                json_body=row,
                headers={"Prefer": "return=representation"},
            ) or []
        return _score_row_to_payload(result[0]) if result else payload

    def delete_score(self, user_id: str, name: str):
        self._request(
            "DELETE",
            "scores",
            params={
                "user_id": f"eq.{user_id}",
                "slug": f"eq.{name}",
            },
            headers={"Prefer": "return=minimal"},
        )

    def get_app_user_by_username(self, username: str):
        rows = self._request(
            "GET",
            "app_users",
            params={
                "select": "id,username,password_hash,created_at",
                "username": f"eq.{username}",
                "limit": "1",
            },
        ) or []
        return rows[0] if rows else None

    def create_app_user(self, username: str, password_hash: str):
        result = self._request(
            "POST",
            "app_users",
            params={"select": "id,username,password_hash,created_at"},
            json_body={
                "username": username,
                "password_hash": password_hash,
            },
            headers={"Prefer": "return=representation"},
        ) or []
        return result[0] if result else None

    def create_app_session(self, user_id: str, token_hash: str, expires_at_iso: str):
        result = self._request(
            "POST",
            "app_sessions",
            params={"select": "id,user_id,token_hash,expires_at,created_at"},
            json_body={
                "user_id": user_id,
                "token_hash": token_hash,
                "expires_at": expires_at_iso,
            },
            headers={"Prefer": "return=representation"},
        ) or []
        return result[0] if result else None

    def get_app_session_user(self, raw_token: str):
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        rows = self._request(
            "GET",
            "app_sessions",
            params={
                "select": "id,user_id,expires_at",
                "token_hash": f"eq.{token_hash}",
                "limit": "1",
            },
        ) or []
        if not rows:
            return None
        session = rows[0]
        expires_at = session.get("expires_at")
        if expires_at:
            expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expires_dt <= datetime.now(timezone.utc):
                self.delete_app_session(raw_token)
                return None
        users = self._request(
            "GET",
            "app_users",
            params={
                "select": "id,username,created_at",
                "id": f"eq.{session['user_id']}",
                "limit": "1",
            },
        ) or []
        if not users:
            return None
        user = users[0]
        user["session_id"] = session.get("id")
        return user

    def delete_app_session(self, raw_token: str):
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        self._request(
            "DELETE",
            "app_sessions",
            params={"token_hash": f"eq.{token_hash}"},
            headers={"Prefer": "return=minimal"},
        )


def create_score_store():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if url and key:
        return SupabaseScoreStore(url, key)
    return LocalScoreStore()
