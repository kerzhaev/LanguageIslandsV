from __future__ import annotations

import argparse
import io
import json
import math
import re
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

import imageio_ffmpeg
from mutagen.mp3 import MP3
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

try:
    from pypdf import PdfReader
except Exception:
    from PyPDF2 import PdfReader


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "output"
FONT_REGULAR = "ArialUnicodeFallback"
FONT_BOLD = "ArialUnicodeFallbackBold"
LANGUAGE_INFO = {
    "english": {"name": "English", "code": "en"},
    "spanish": {"name": "Spanish", "code": "es"},
    "german": {"name": "German", "code": "de"},
    "french": {"name": "French", "code": "fr"},
    "italian": {"name": "Italian", "code": "it"},
    "japanese": {"name": "Japanese", "code": "ja"},
}


def load_theme(path: Path) -> dict:
    theme = json.loads(path.read_text(encoding="utf-8-sig"))
    validate_theme_text_integrity(theme, path)
    return theme


def validate_theme_text_integrity(theme: dict, path: Path) -> None:
    entries = theme.get("entries", [])
    for index, entry in enumerate(entries, start=1):
        ru = native_text(entry)
        if not ru:
            raise ValueError(f"{path}: entry {index} has empty Russian text")
        if "???" in ru:
            raise ValueError(f"{path}: entry {index} contains damaged Russian text placeholder '???'")
        if "�" in ru:
            raise ValueError(f"{path}: entry {index} contains replacement characters in Russian text")
        if not re.search(r"[А-Яа-яЁё]", ru):
            raise ValueError(f"{path}: entry {index} Russian text has no Cyrillic characters")


def theme_prefix(theme: dict) -> str:
    return f"{theme['theme_id']}__{theme['slug']}"


def theme_language_key(theme: dict) -> str:
    value = str(theme.get("language", "english")).strip().lower()
    return value if value else "english"


def theme_language_name(theme: dict) -> str:
    return LANGUAGE_INFO.get(theme_language_key(theme), {}).get("name", theme_language_key(theme).replace("-", " ").title())


def theme_language_code(theme: dict) -> str:
    return LANGUAGE_INFO.get(theme_language_key(theme), {}).get("code", theme_language_key(theme)[:2])


def target_text(entry: dict) -> str:
    return str(entry.get("text") or entry.get("target") or entry.get("en") or "").strip()


def native_text(entry: dict) -> str:
    return str(entry.get("ru") or "").strip()


def output_dir(theme: dict) -> Path:
    folder = OUTPUT_ROOT / theme["folder_name"]
    level = theme.get("level")
    if level:
        folder = folder / f"level-{level}"
    return folder


def ensure_pdf_fonts() -> None:
    if FONT_REGULAR not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_REGULAR, r"C:\Windows\Fonts\arial.ttf"))
    if FONT_BOLD not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_BOLD, r"C:\Windows\Fonts\arialbd.ttf"))


def build_styles():
    ensure_pdf_fonts()
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "IslandTitle",
            parent=styles["Title"],
            fontName=FONT_BOLD,
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#1E2430"),
            spaceAfter=8,
        ),
        "subtitle": ParagraphStyle(
            "IslandSubtitle",
            parent=styles["BodyText"],
            fontName=FONT_REGULAR,
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#4F5B6B"),
            spaceAfter=10,
        ),
        "cell": ParagraphStyle(
            "IslandCell",
            parent=styles["BodyText"],
            fontName=FONT_REGULAR,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#1F2933"),
        ),
        "cell_bold": ParagraphStyle(
            "IslandCellBold",
            parent=styles["BodyText"],
            fontName=FONT_BOLD,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#111827"),
        ),
    }


def as_paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text.replace("&", "&amp;"), style)


def numbered_text(index: int, text: str) -> str:
    return f"<b>{index}.</b> {text}"


def pdf_layout_candidates(theme: dict) -> list[dict]:
    entry_count = len(theme["entries"])
    compact = entry_count >= 20
    base = {
        "left_margin": 9 * mm if compact else 11 * mm,
        "right_margin": 9 * mm if compact else 11 * mm,
        "top_margin": 9 * mm if compact else 11 * mm,
        "bottom_margin": 9 * mm if compact else 11 * mm,
        "title_font_size": 14.5 if compact else 17,
        "title_leading": 16.5 if compact else 20,
        "title_space_after": 4.2 if compact else 6,
        "subtitle_font_size": 7.7 if compact else 8.8,
        "subtitle_leading": 9.2 if compact else 11.4,
        "subtitle_space_after": 5.0 if compact else 6.5,
        "cell_font_size": 8.15 if compact else 9.55,
        "cell_leading": 9.35 if compact else 12.2,
        "header_hint_size": 6.2 if compact else 7.2,
        "cell_padding_x": 4.0 if compact else 4.6,
        "cell_padding_y": 2.45 if compact else 3.3,
    }

    if entry_count >= 20:
        scales = [1.30, 1.24, 1.18, 1.12, 1.06, 1.00, 0.96]
    elif entry_count >= 15:
        scales = [1.48, 1.40, 1.32, 1.24, 1.16, 1.08, 1.00]
    else:
        scales = [1.70, 1.58, 1.46, 1.34, 1.22, 1.10, 1.00]

    layouts = []
    for scale in scales:
        layouts.append(
            {
                "left_margin": max(7 * mm, base["left_margin"] - (scale - 1.0) * 2.5 * mm),
                "right_margin": max(7 * mm, base["right_margin"] - (scale - 1.0) * 2.5 * mm),
                "top_margin": max(7 * mm, base["top_margin"] - (scale - 1.0) * 2.0 * mm),
                "bottom_margin": max(7 * mm, base["bottom_margin"] - (scale - 1.0) * 2.0 * mm),
                "title_font_size": round(base["title_font_size"] * scale, 2),
                "title_leading": round(base["title_leading"] * scale, 2),
                "title_space_after": round(base["title_space_after"] * scale, 2),
                "subtitle_font_size": round(base["subtitle_font_size"] * scale, 2),
                "subtitle_leading": round(base["subtitle_leading"] * scale, 2),
                "subtitle_space_after": round(base["subtitle_space_after"] * scale, 2),
                "cell_font_size": round(base["cell_font_size"] * scale, 2),
                "cell_leading": round(base["cell_leading"] * scale, 2),
                "header_hint_size": round(base["header_hint_size"] * scale, 2),
                "cell_padding_x": round(base["cell_padding_x"] * min(scale, 1.2), 2),
                "cell_padding_y": round(base["cell_padding_y"] * min(scale, 1.15), 2),
            }
        )
    return layouts


def pdf_styles(layout: dict):
    ensure_pdf_fonts()
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "IslandTitlePdf",
            parent=styles["Title"],
            fontName=FONT_BOLD,
            fontSize=layout["title_font_size"],
            leading=layout["title_leading"],
            textColor=colors.HexColor("#1E2430"),
            spaceAfter=layout["title_space_after"],
        ),
        "subtitle": ParagraphStyle(
            "IslandSubtitlePdf",
            parent=styles["BodyText"],
            fontName=FONT_REGULAR,
            fontSize=layout["subtitle_font_size"],
            leading=layout["subtitle_leading"],
            textColor=colors.HexColor("#4F5B6B"),
            spaceAfter=layout["subtitle_space_after"],
        ),
        "cell": ParagraphStyle(
            "IslandCellPdf",
            parent=styles["BodyText"],
            fontName=FONT_REGULAR,
            fontSize=layout["cell_font_size"],
            leading=layout["cell_leading"],
            textColor=colors.HexColor("#1F2933"),
        ),
        "cell_bold": ParagraphStyle(
            "IslandCellBoldPdf",
            parent=styles["BodyText"],
            fontName=FONT_BOLD,
            fontSize=layout["cell_font_size"],
            leading=layout["cell_leading"],
            textColor=colors.HexColor("#111827"),
        ),
    }


def make_pdf_table(rows: list[list[Paragraph]], layout: dict, doc: SimpleDocTemplate, mode: str) -> Table:
    col_width = doc.width / 2
    table = Table(rows, colWidths=[col_width, col_width], repeatRows=1)
    if mode == "bilingual":
        header_bg = colors.HexColor("#E6EEF8")
        header_text = colors.HexColor("#1B3A57")
        grid = colors.HexColor("#C9D4E3")
        row_bgs = [colors.white, colors.HexColor("#FAFCFE")]
    else:
        header_bg = colors.HexColor("#FCE8D6")
        header_text = colors.HexColor("#6E3B00")
        grid = colors.HexColor("#E5D0BC")
        row_bgs = [colors.white, colors.HexColor("#FFF9F4")]
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), header_bg),
                ("TEXTCOLOR", (0, 0), (-1, 0), header_text),
                ("GRID", (0, 0), (-1, -1), 0.35, grid),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), row_bgs),
                ("LEFTPADDING", (0, 0), (-1, -1), layout["cell_padding_x"]),
                ("RIGHTPADDING", (0, 0), (-1, -1), layout["cell_padding_x"]),
                ("TOPPADDING", (0, 0), (-1, -1), layout["cell_padding_y"]),
                ("BOTTOMPADDING", (0, 0), (-1, -1), layout["cell_padding_y"]),
            ]
        )
    )
    return table


def pdf_story(theme: dict, layout: dict, mode: str, doc: SimpleDocTemplate) -> list:
    styles = pdf_styles(layout)
    target_language = theme_language_name(theme)
    if mode == "bilingual":
        story = [
            Paragraph(f"{theme['theme_label']}<br/>{theme['title']} - Bilingual Study", styles["title"]),
            Paragraph(
                f"Read across both columns. Use {target_language} as the main track and Russian only as support.",
                styles["subtitle"],
            ),
        ]
        rows = [
            [
                as_paragraph(
                    f"{target_language}<br/><font size='{layout['header_hint_size']}'>Primary text</font>",
                    styles["cell_bold"],
                ),
                as_paragraph(
                    f"Russian<br/><font size='{layout['header_hint_size']}'>Reference meaning</font>",
                    styles["cell_bold"],
                ),
            ]
        ]
    else:
        story = [
            Paragraph(f"{theme['theme_label']}<br/>{theme['title']} - Active Recall", styles["title"]),
            Paragraph(
                f"Read the Russian prompt first, answer aloud in {target_language}, then uncover and check.",
                styles["subtitle"],
            ),
        ]
        rows = [
            [
                as_paragraph(
                    f"{target_language} answer<br/><font size='{layout['header_hint_size']}'>Keep covered while recalling</font>",
                    styles["cell_bold"],
                ),
                as_paragraph(
                    f"Russian prompt<br/><font size='{layout['header_hint_size']}'>Read first and answer from memory</font>",
                    styles["cell_bold"],
                ),
            ]
        ]
    for index, entry in enumerate(theme["entries"], start=1):
        if mode == "bilingual":
            rows.append(
                [
                    as_paragraph(numbered_text(index, target_text(entry)), styles["cell"]),
                    as_paragraph(numbered_text(index, native_text(entry)), styles["cell"]),
                ]
            )
        else:
            rows.append(
                [
                    as_paragraph(numbered_text(index, target_text(entry)), styles["cell"]),
                    as_paragraph(numbered_text(index, native_text(entry)), styles["cell"]),
                ]
            )
    table = make_pdf_table(rows, layout, doc, mode)
    story.append(table)
    return story


def build_pdf_with_best_layout(theme: dict, target: Path, mode: str) -> None:
    best_layout = pdf_layout_candidates(theme)[-1]
    for layout in pdf_layout_candidates(theme):
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=layout["left_margin"],
            rightMargin=layout["right_margin"],
            topMargin=layout["top_margin"],
            bottomMargin=layout["bottom_margin"],
        )
        story = pdf_story(theme, layout, mode, doc)
        doc.build(story)
        buffer.seek(0)
        if len(PdfReader(buffer).pages) <= 1:
            best_layout = layout
            break

    doc = SimpleDocTemplate(
        str(target),
        pagesize=A4,
        leftMargin=best_layout["left_margin"],
        rightMargin=best_layout["right_margin"],
        topMargin=best_layout["top_margin"],
        bottomMargin=best_layout["bottom_margin"],
    )
    story = pdf_story(theme, best_layout, mode, doc)
    doc.build(story)


def build_bilingual_pdf(theme: dict, target: Path) -> None:
    build_pdf_with_best_layout(theme, target, mode="bilingual")


def build_active_recall_pdf(theme: dict, target: Path) -> None:
    build_pdf_with_best_layout(theme, target, mode="active_recall")


def write_text(path: Path, lines: list[str]) -> None:
    text = "\n".join(lines).strip() + "\n"
    encoding = "utf-8-sig" if path.suffix.lower() in {".txt", ".srt"} else "utf-8"
    path.write_text(text, encoding=encoding)
    roundtrip = path.read_text(encoding=encoding)
    if roundtrip != text:
        raise ValueError(f"Encoding roundtrip failed for {path}")


def build_naturalreaders_inputs(theme: dict, target_once: Path, target_repeat: Path) -> None:
    once_lines = [target_text(entry) for entry in theme["entries"]]
    repeat_lines: list[str] = []
    for entry in theme["entries"]:
        repeat_lines.extend([target_text(entry)] * 5)
        repeat_lines.append("")
    write_text(target_once, once_lines)
    write_text(target_repeat, repeat_lines)


def mp3_duration_seconds(path: Path) -> float:
    return float(MP3(str(path)).info.length)


def subtitle_weights(entries: list[dict]) -> list[float]:
    weights = []
    for entry in entries:
        text = target_text(entry)
        words = max(1, len(text.split()))
        chars = len(text)
        weights.append(words * 1.4 + chars * 0.06)
    return weights


def subtitle_blocks(entries: list[dict], total_seconds: float) -> list[tuple[float, float, str]]:
    weights = subtitle_weights(entries)
    total_weight = sum(weights)
    blocks = []
    cursor = 0.0
    for entry, weight in zip(entries, weights):
        duration = total_seconds * (weight / total_weight)
        start = cursor
        end = start + duration
        blocks.append((start, end, target_text(entry)))
        cursor = end
    if blocks:
        start, _, text = blocks[-1]
        blocks[-1] = (start, total_seconds, text)
    return blocks


def expected_start_times(entries: list[dict], total_seconds: float) -> list[float]:
    weights = subtitle_weights(entries)
    total_weight = sum(weights)
    starts = [0.0]
    cursor = 0.0
    for weight in weights[:-1]:
        cursor += total_seconds * (weight / total_weight)
        starts.append(cursor)
    return starts


def detect_silences(mp3_path: Path, threshold_db: int = -35, min_silence: float = 0.18) -> list[tuple[float, float]]:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe,
        "-i",
        str(mp3_path),
        "-af",
        f"silencedetect=n={threshold_db}dB:d={min_silence:.2f}",
        "-f",
        "null",
        "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")

    starts = [float(match) for match in re.findall(r"silence_start:\s*([0-9.]+)", output)]
    ends = [float(match) for match in re.findall(r"silence_end:\s*([0-9.]+)", output)]
    return list(zip(starts, ends))


def speech_chunks_from_silences(total_seconds: float, silences: list[tuple[float, float]]) -> list[tuple[float, float]]:
    chunks: list[tuple[float, float]] = []
    cursor = 0.0
    for silence_start, silence_end in silences:
        if silence_start > cursor + 0.05:
            chunks.append((cursor, silence_start))
        cursor = max(cursor, silence_end)
    if total_seconds > cursor + 0.05:
        chunks.append((cursor, total_seconds))
    return chunks


def best_speech_chunks(entries: list[dict], mp3_path: Path, total_seconds: float) -> list[tuple[float, float]]:
    phrase_count = len(entries)
    candidates: list[tuple[int, float, list[tuple[float, float]]]] = []
    for min_silence in [0.40, 0.35, 0.30, 0.26, 0.22, 0.18]:
        silences = detect_silences(mp3_path, threshold_db=-35, min_silence=min_silence)
        chunks = speech_chunks_from_silences(total_seconds, silences)
        candidates.append((len(chunks), min_silence, chunks))

    enough = [item for item in candidates if item[0] >= phrase_count]
    if enough:
        best_count, _, best_chunks = min(enough, key=lambda item: (item[0] - phrase_count, -item[1]))
        if best_count <= phrase_count + max(4, phrase_count // 4):
            return best_chunks

    return max(candidates, key=lambda item: item[0])[2]


def exact_chunk_blocks(
    entries: list[dict], mp3_path: Path, total_seconds: float
) -> list[tuple[float, float, str]] | None:
    phrase_count = len(entries)
    for min_silence in [0.45, 0.42, 0.40, 0.38, 0.35, 0.32, 0.30]:
        silences = detect_silences(mp3_path, threshold_db=-35, min_silence=min_silence)
        chunks = speech_chunks_from_silences(total_seconds, silences)
        if len(chunks) != phrase_count:
            continue

        durations = [end - start for start, end in chunks]
        median_duration = sorted(durations)[len(durations) // 2]
        if max(durations) > median_duration * 1.55 or min(durations) < median_duration * 0.45:
            continue

        blocks: list[tuple[float, float, str]] = []
        previous_end = 0.0
        for index, (start, end) in enumerate(chunks):
            start = max(previous_end, start - 0.10)
            if index + 1 < len(chunks):
                next_start = chunks[index + 1][0]
                end = min(total_seconds, next_start - 0.03)
            else:
                end = total_seconds
            if end <= start:
                end = min(total_seconds, start + 0.20)
            blocks.append((start, end, target_text(entries[index])))
            previous_end = end
        return blocks
    return None


def timing_quality_score(
    blocks: list[tuple[float, float, str]], entries: list[dict], total_seconds: float
) -> float:
    expected_starts = expected_start_times(entries, total_seconds)
    starts = [start for start, _, _ in blocks]
    durations = [end - start for start, end, _ in blocks]
    median_duration = sorted(durations)[len(durations) // 2]
    avg_chars = sum(len(target_text(entry)) for entry in entries) / max(1, len(entries))
    dense_mode = avg_chars >= 110

    score = sum((actual - expected) ** 2 for actual, expected in zip(starts, expected_starts))
    score += (max(durations) - min(durations)) ** 2 * 2

    min_duration = 5.5 if dense_mode else 3.8
    for duration in durations:
        if duration < min_duration:
            score += (min_duration - duration) ** 2 * 30
        if duration > median_duration * 1.6:
            score += (duration - median_duration * 1.6) ** 2 * 8
    return score


def partition_chunks(
    entries: list[dict], chunks: list[tuple[float, float]], total_seconds: float
) -> list[tuple[float, float, str]] | None:
    phrase_count = len(entries)
    chunk_count = len(chunks)
    if chunk_count < phrase_count:
        return None

    chunk_durations = [end - start for start, end in chunks]
    weights = subtitle_weights(entries)
    total_weight = sum(weights)
    weight_targets = [weight / total_weight * total_seconds for weight in weights]
    dense_mode = sum(len(target_text(entry)) for entry in entries) / max(1, phrase_count) >= 110

    prefix = [0.0]
    for duration in chunk_durations:
        prefix.append(prefix[-1] + duration)

    dp = [[math.inf] * (chunk_count + 1) for _ in range(phrase_count + 1)]
    prev: list[list[tuple[int, int] | None]] = [[None] * (chunk_count + 1) for _ in range(phrase_count + 1)]
    dp[0][0] = 0.0

    for phrase_idx in range(1, phrase_count + 1):
        remaining_phrases = phrase_count - phrase_idx
        for end_idx in range(phrase_idx, chunk_count - remaining_phrases + 1):
            best_cost = math.inf
            best_start_idx: int | None = None
            for start_idx in range(phrase_idx - 1, end_idx):
                actual = prefix[end_idx] - prefix[start_idx]
                target = weight_targets[phrase_idx - 1]
                cost = dp[phrase_idx - 1][start_idx] + (actual - target) ** 2
                if actual < target * 0.65:
                    cost += (target * 0.65 - actual) ** 2 * 4
                if actual > target * 1.65:
                    cost += (actual - target * 1.65) ** 2 * 2
                if dense_mode and actual < 5.5:
                    cost += (5.5 - actual) ** 2 * 20
                if cost < best_cost:
                    best_cost = cost
                    best_start_idx = start_idx
            dp[phrase_idx][end_idx] = best_cost
            if best_start_idx is not None:
                prev[phrase_idx][end_idx] = (phrase_idx - 1, best_start_idx)

    if not math.isfinite(dp[phrase_count][chunk_count]):
        return None

    groups: list[tuple[int, int]] = []
    phrase_idx = phrase_count
    end_idx = chunk_count
    while phrase_idx > 0:
        pointer = prev[phrase_idx][end_idx]
        if pointer is None:
            return None
        _, start_idx = pointer
        groups.append((start_idx, end_idx))
        phrase_idx -= 1
        end_idx = start_idx
    groups.reverse()

    blocks = []
    previous_end = 0.0
    for idx, (start_idx, end_idx) in enumerate(groups):
        start = max(previous_end, chunks[start_idx][0] - 0.12)
        end = min(total_seconds, chunks[end_idx - 1][1] + 0.18)
        if idx + 1 < len(groups):
            next_start = chunks[groups[idx + 1][0]][0]
            midpoint = (chunks[end_idx - 1][1] + next_start) / 2
            end = min(end, midpoint)
        if end <= start:
            end = min(total_seconds, start + 0.2)
        blocks.append((start, end, target_text(entries[idx])))
        previous_end = end

    if blocks:
        last_start, _, text = blocks[-1]
        blocks[-1] = (last_start, total_seconds, text)
    return blocks


def aligned_subtitle_blocks(entries: list[dict], mp3_path: Path) -> list[tuple[float, float, str]]:
    total_seconds = mp3_duration_seconds(mp3_path)
    exact = exact_chunk_blocks(entries, mp3_path, total_seconds)
    if exact:
        return exact

    candidates: list[list[tuple[float, float, str]]] = []
    for min_silence in [0.40, 0.38, 0.35, 0.32, 0.30, 0.26, 0.22, 0.18]:
        silences = detect_silences(mp3_path, threshold_db=-35, min_silence=min_silence)
        chunks = speech_chunks_from_silences(total_seconds, silences)
        aligned = partition_chunks(entries, chunks, total_seconds)
        if aligned:
            candidates.append(aligned)

    if candidates:
        return min(candidates, key=lambda blocks: timing_quality_score(blocks, entries, total_seconds))

    avg_chars = sum(len(target_text(entry)) for entry in entries) / max(1, len(entries))
    if avg_chars >= 110:
        return subtitle_blocks(entries, total_seconds)
    return subtitle_blocks(entries, total_seconds)


def srt_timestamp(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def build_srt(theme: dict, mp3_path: Path, srt_path: Path, language: str, numbered: bool = False) -> None:
    blocks = aligned_subtitle_blocks(theme["entries"], mp3_path)
    lines = []
    for idx, (start, end, _) in enumerate(blocks, start=1):
        entry = theme["entries"][idx - 1]
        text = target_text(entry) if language == "target" else native_text(entry)
        if numbered:
            text = f"{idx}. {text}"
        lines.extend(
            [
                str(idx),
                f"{srt_timestamp(start)} --> {srt_timestamp(end)}",
                text,
                "",
            ]
        )
    write_text(srt_path, lines)


def escape_subtitles_path(path: Path) -> str:
    unixy = path.resolve().as_posix()
    if len(unixy) > 1 and unixy[1] == ":":
        unixy = unixy[0] + "\\:" + unixy[2:]
    return unixy.replace("'", r"\'")


def render_video(theme: dict, mp3_path: Path, srt_path: Path, target: Path) -> None:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    duration = mp3_duration_seconds(mp3_path)
    video_cfg = theme.get("video", {})
    width = int(video_cfg.get("width", 1280))
    height = int(video_cfg.get("height", 720))
    fps = int(video_cfg.get("fps", 24))
    bg = str(video_cfg.get("background_color", "#F6F0E5")).lstrip("#")
    subtitles_path = escape_subtitles_path(srt_path)
    style = (
        "FontName=Arial,"
        "FontSize=22,"
        "PrimaryColour=&H00222222,"
        "OutlineColour=&H00F8F8F8,"
        "BackColour=&H00000000,"
        "BorderStyle=3,"
        "Outline=1,"
        "Shadow=0,"
        "Alignment=2,"
        "MarginV=82"
    )
    vf = f"subtitles='{subtitles_path}':force_style='{style}'"
    cmd = [
        ffmpeg_exe,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x{bg}:s={width}x{height}:r={fps}:d={duration:.3f}",
        "-i",
        str(mp3_path),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(target),
    ]
    subprocess.run(cmd, check=True)


def build_zip(bundle_path: Path, files: list[Path]) -> None:
    existing = [path for path in files if path.exists()]
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in existing:
            zf.write(path, arcname=path.name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a language island package.")
    parser.add_argument("theme_file", type=Path, help="Path to theme.json")
    args = parser.parse_args()

    theme = load_theme(args.theme_file)
    out_dir = output_dir(theme)
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = theme_prefix(theme)
    lang_code = theme_language_code(theme)

    pdf_bilingual = out_dir / f"{prefix}__03__bilingual_study.pdf"
    pdf_active = out_dir / f"{prefix}__05__active_recall.pdf"
    txt_once = out_dir / f"{prefix}__04a__shadowing_{lang_code}__naturalreaders_input.txt"
    txt_repeat = out_dir / f"{prefix}__06a__shadowing_{lang_code}_repeat__naturalreaders_input.txt"
    mp3_once = out_dir / f"{prefix}__04__shadowing_{lang_code}.mp3"
    mp3_repeat = out_dir / f"{prefix}__06__shadowing_{lang_code}_repeat.mp3"
    srt_path = out_dir / f"{prefix}__13__shadowing_ru.srt"
    video_path = out_dir / f"{prefix}__14__shadowing_video_{lang_code}.mp4"
    zip_name = datetime.now().strftime("%d-%m-%Y_%H-%M-%S.zip")
    zip_path = out_dir / zip_name
    legacy_srt_path = out_dir / f"{prefix}__13__shadowing_{lang_code}.srt"

    build_bilingual_pdf(theme, pdf_bilingual)
    build_active_recall_pdf(theme, pdf_active)
    build_naturalreaders_inputs(theme, txt_once, txt_repeat)

    if mp3_once.exists():
        build_srt(theme, mp3_once, srt_path, language="ru", numbered=True)
        with tempfile.NamedTemporaryFile(prefix=f"{prefix}__burn_{lang_code}__", suffix=".srt", delete=False) as temp_file:
            burn_srt_path = Path(temp_file.name)
        try:
            build_srt(theme, mp3_once, burn_srt_path, language="target", numbered=True)
            render_video(theme, mp3_once, burn_srt_path, video_path)
        finally:
            burn_srt_path.unlink(missing_ok=True)
        legacy_srt_path.unlink(missing_ok=True)
    else:
        print(f"Skip video: missing {mp3_once.name}")

    build_zip(
        zip_path,
        [
            pdf_bilingual,
            mp3_once,
            pdf_active,
            mp3_repeat,
            srt_path,
            video_path,
        ],
    )

    print(f"Output: {out_dir}")
    print(f"NaturalReaders input: {txt_once.name}")
    print(f"NaturalReaders repeat input: {txt_repeat.name}")
    print(f"Expected MP3: {mp3_once.name}")
    print(f"Expected repeat MP3: {mp3_repeat.name}")
    if video_path.exists():
        print(f"Video: {video_path.name}")
    else:
        print("Video not built yet.")


if __name__ == "__main__":
    main()
