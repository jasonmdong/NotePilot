import contextlib
import importlib.util
import io
import logging
import re
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


def _tag_has_class(tag: str, class_name: str) -> bool:
    class_match = re.search(r"""\bclass\s*=\s*(['"])(.*?)\1""", tag, re.IGNORECASE | re.DOTALL)
    return bool(class_match and class_name in class_match.group(2).split())


def _extract_balanced_tag_fragments(markup: str, tag_name: str, class_name: str | None = None) -> list[tuple[int, int]]:
    fragments = []
    token_re = re.compile(rf"<(/?){re.escape(tag_name)}\b[^>]*>", re.IGNORECASE)
    search_from = 0
    while True:
        start_match = token_re.search(markup, search_from)
        if not start_match:
            break
        if start_match.group(1):
            search_from = start_match.end()
            continue
        if start_match.group(0).rstrip().endswith("/>"):
            search_from = start_match.end()
            continue
        if class_name and not _tag_has_class(start_match.group(0), class_name):
            search_from = start_match.end()
            continue

        depth = 1
        end_pos = start_match.end()
        for match in token_re.finditer(markup, start_match.end()):
            if match.group(0).rstrip().endswith("/>"):
                continue
            depth += -1 if match.group(1) else 1
            if depth == 0:
                end_pos = match.end()
                break
        else:
            break

        fragments.append((start_match.start(), end_pos))
        search_from = end_pos

    return fragments


def _attr_value(tag: str, name: str) -> str | None:
    match = re.search(rf"""\b{re.escape(name)}\s*=\s*(['"])(.*?)\1""", tag, re.IGNORECASE | re.DOTALL)
    return match.group(2) if match else None


def _set_attr_value(tag: str, name: str, value: str) -> str:
    attr_re = re.compile(rf"""(\b{re.escape(name)}\s*=\s*)(['"])(.*?)\2""", re.IGNORECASE | re.DOTALL)
    if attr_re.search(tag):
        return attr_re.sub(lambda match: f"{match.group(1)}{match.group(2)}{value}{match.group(2)}", tag, count=1)
    return tag[:-1] + f' {name}="{value}">'


def _format_svg_number(value: float) -> str:
    return str(round(value, 2)).rstrip("0").rstrip(".")


def _stack_chord_verses_in_fragment(chord_markup: str) -> tuple[str, int]:
    text_nodes = []
    for verse_start, verse_end in _extract_balanced_tag_fragments(chord_markup, "g", "verse"):
        verse_markup = chord_markup[verse_start:verse_end]
        text_match = re.search(r"<text\b[^>]*>", verse_markup, re.IGNORECASE | re.DOTALL)
        if not text_match:
            continue
        text_tag = text_match.group(0)
        x_value = _attr_value(text_tag, "x")
        y_value = _attr_value(text_tag, "y")
        if x_value is None or y_value is None:
            continue
        try:
            text_nodes.append({
                "start": verse_start + text_match.start(),
                "end": verse_start + text_match.end(),
                "tag": text_tag,
                "x": float(x_value),
                "y": float(y_value),
            })
        except ValueError:
            continue

    if len(text_nodes) <= 1:
        return chord_markup, 0

    x = min(node["x"] for node in text_nodes)
    base_y = max(node["y"] for node in text_nodes)
    line_gap = 360
    center_index = (len(text_nodes) - 1) / 2

    rebuilt = chord_markup
    for index, node in reversed(list(enumerate(text_nodes))):
        y = base_y + ((center_index - index) * line_gap)
        tag = _set_attr_value(node["tag"], "x", _format_svg_number(x))
        tag = _set_attr_value(tag, "y", _format_svg_number(y))
        rebuilt = rebuilt[:node["start"]] + tag + rebuilt[node["end"]:]

    return rebuilt, len(text_nodes)


def stack_fingering_chord_numbers_in_html(html: str) -> str:
    if "class=\"chord\"" not in html and "class='chord'" not in html:
        return html

    fragments = _extract_balanced_tag_fragments(html, "g", "chord")
    if not fragments:
        return html

    rebuilt = html
    total_changed = 0
    for start, end in reversed(fragments):
        replacement, changed = _stack_chord_verses_in_fragment(rebuilt[start:end])
        rebuilt = rebuilt[:start] + replacement + rebuilt[end:]
        total_changed += changed

    return rebuilt if total_changed else html


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
