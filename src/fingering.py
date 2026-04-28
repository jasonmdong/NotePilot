import contextlib
import importlib.util
import io
import logging
import xml.etree.ElementTree as ET
from pathlib import Path


logger = logging.getLogger(__name__)

ENGINE_NAME = "pianoplayer"
VALID_HAND_SIZES = {"XXS", "XS", "S", "M", "L", "XL", "XXL"}
FINGERING_LYRIC_NUMBER = "pianoplayer-fingering"


def _hand_size() -> str:
    import os

    size = (os.getenv("ACCOMPY_FINGERING_HAND_SIZE") or "M").strip().upper() or "M"
    return size if size in VALID_HAND_SIZES else "M"


def engine_available() -> bool:
    return importlib.util.find_spec("pianoplayer") is not None


def score_is_eligible(parts_data: list[dict]) -> bool:
    return 0 < len(parts_data) <= 2


def build_fingering_state(parts_data: list[dict]) -> dict:
    return {
        "engine": ENGINE_NAME,
        "available": engine_available(),
        "eligible": score_is_eligible(parts_data),
        "applied": False,
        "hand_size": None,
        "annotations": 0,
        "reason": "not_generated",
    }


def normalize_fingering_state(
    parts_data: list[dict],
    existing: dict | None = None,
    *,
    has_fingered_sheet: bool = False,
) -> dict:
    metadata = build_fingering_state(parts_data)
    if isinstance(existing, dict):
        for key in ("hand_size", "annotations", "reason"):
            if key in existing:
                metadata[key] = existing[key]

    if has_fingered_sheet:
        metadata["applied"] = True
        metadata["reason"] = "generated"
    elif not metadata["eligible"]:
        metadata["reason"] = "unsupported_parts"
    elif not metadata["available"]:
        metadata["reason"] = "missing_dependency"
    else:
        metadata["reason"] = "not_generated"

    if not metadata["applied"]:
        metadata["annotations"] = 0

    return metadata


def _count_fingering_annotations(path: str | Path) -> int:
    tree = ET.parse(path)
    count = 0
    for note_el in tree.iterfind(".//note"):
        technical = note_el.find("./notations/technical/fingering")
        lyric = note_el.find(f"./lyric[@number='{FINGERING_LYRIC_NUMBER}']/text")
        if technical is not None or lyric is not None:
            count += 1
    return count


def apply_auto_fingering(
    source_path: str,
    *,
    out_dir: str,
    score_name: str,
    parts_data: list[dict],
    progress_callback=None,
) -> tuple[str, dict]:
    progress = progress_callback or (lambda *_args, **_kwargs: None)
    metadata = build_fingering_state(parts_data)
    metadata["hand_size"] = _hand_size()

    if not metadata["eligible"]:
        metadata["reason"] = "unsupported_parts"
        return source_path, metadata

    if not metadata["available"]:
        metadata["reason"] = "missing_dependency"
        return source_path, metadata

    from pianoplayer.core import run_annotate

    output_path = Path(out_dir) / f"{score_name}__fingered.musicxml"

    try:
        progress(35, "Analyzing score")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            run_annotate(
                filename=source_path,
                outputfile=str(output_path),
                quiet=True,
                hand_size=metadata["hand_size"],
                below_beam=True,
            )
    except Exception as exc:
        metadata["reason"] = "annotation_failed"
        logger.warning("PianoPlayer fingering failed for %s: %s", source_path, exc)
        return source_path, metadata

    if not output_path.exists():
        metadata["reason"] = "missing_output"
        return source_path, metadata

    try:
        progress(65, "Counting annotations")
        metadata["annotations"] = _count_fingering_annotations(output_path)
    except Exception as exc:
        metadata["reason"] = "annotation_count_failed"
        logger.warning("Could not inspect PianoPlayer output %s: %s", output_path, exc)
        return str(output_path), metadata

    if metadata["annotations"] <= 0:
        metadata["reason"] = "no_annotations"
        return str(output_path), metadata

    metadata["applied"] = True
    metadata["reason"] = "generated"
    return str(output_path), metadata
