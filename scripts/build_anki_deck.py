from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import genanki
import imageio_ffmpeg

from build_island import (
    OUTPUT_ROOT,
    aligned_subtitle_blocks,
    load_theme,
    native_text,
    target_text,
    theme_prefix,
)


ANKI_OUTPUT_ROOT = OUTPUT_ROOT / "Anki"
IMAGE_MODEL = "gpt-image-1"
HIGHLIGHT_STYLE = "#ff6b6b; font-weight: bold;"


def stable_id(seed: str) -> int:
    return int(hashlib.md5(seed.encode("utf-8")).hexdigest()[:8], 16)


def parse_srt_blocks(srt_path: Path) -> list[dict]:
    text = srt_path.read_text(encoding="utf-8-sig")
    chunks = re.split(r"\r?\n\r?\n", text.strip())
    blocks: list[dict] = []
    for chunk in chunks:
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        idx = int(lines[0])
        start_raw, end_raw = [part.strip() for part in lines[1].split("-->")]
        blocks.append(
            {
                "index": idx,
                "start_seconds": parse_srt_time(start_raw),
                "end_seconds": parse_srt_time(end_raw),
                "text": " ".join(lines[2:]),
            }
        )
    return blocks


def parse_srt_time(value: str) -> float:
    hours, minutes, seconds_ms = value.split(":")
    seconds, millis = seconds_ms.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000.0


def resolve_theme_asset_dir(theme_file: Path, theme: dict) -> Path:
    prefix = theme_prefix(theme)
    folder_name = str(theme.get("folder_name", "")).strip()
    candidates: list[Path] = []
    if folder_name:
        candidates.append(OUTPUT_ROOT / folder_name)
    level = theme.get("level")
    if folder_name and level:
        candidates.insert(0, OUTPUT_ROOT / folder_name / f"level-{level}")
    for candidate in candidates:
        if (candidate / f"{prefix}__04__shadowing_en.mp3").exists():
            return candidate
    matches = list(OUTPUT_ROOT.rglob(f"{prefix}__04__shadowing_en.mp3"))
    if len(matches) == 1:
        return matches[0].parent
    if not matches:
        raise FileNotFoundError(f"Cannot find once MP3 for {theme_file}")
    raise RuntimeError(f"Multiple output folders found for {theme_file}: {matches}")


def theme_hint(theme: dict) -> str:
    theme_number = str(theme["theme_id"]).replace("theme-", "").zfill(2)
    return f"Theme {theme_number}: {theme['title']}"


def visual_focus_text(sentence: str) -> str:
    patterns = [
        r"\bhave got\b",
        r"\bhas got\b",
        r"\bthe only child\b",
        r"\bten years old\b",
        r"\bfourth form\b",
        r"\bAfter school\b",
        r"\bon the twenty-fourth of July\b",
        r"\bas presents\b",
        r"\bwith\b",
        r"\bin\b",
        r"\bon\b",
        r"\bcute, clever and beautiful\b",
        r"\bsubjects are\b",
        r"\bpurple and blue\b",
        r"\ban apple, a banana, watermelon and blueberries\b",
        r"\bdrawing, dancing, singing, reading and playing\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, sentence, flags=re.IGNORECASE)
        if match:
            return (
                sentence[: match.start()]
                + f'<span style="color: {HIGHLIGHT_STYLE}">{sentence[match.start():match.end()]}</span>'
                + sentence[match.end():]
            )

    words = re.findall(r"\b[\w-]+\b", sentence)
    focus = words[-1] if words else sentence
    match = re.search(re.escape(focus), sentence)
    if not match:
        return sentence
    return (
        sentence[: match.start()]
        + f'<span style="color: {HIGHLIGHT_STYLE}">{sentence[match.start():match.end()]}</span>'
        + sentence[match.end():]
    )


def build_image_search_prompt(sentence: str) -> str:
    short = sentence.rstrip(".")
    short = short.replace("My favourite ", "favorite ")
    short = short.replace("I have got ", "")
    short = short.replace("My family has got ", "family with ")
    return f"{short}, bright cartoon style"


def maybe_generate_image(
    sentence_id: int,
    sentence: str,
    out_dir: Path,
    skip_images: bool,
) -> tuple[Path | None, str | None]:
    image_name = f"theme-01__{sentence_id:03d}__image.png"
    image_path = out_dir / image_name
    if image_path.exists():
        return image_path, None
    if skip_images:
        return None, "image generation skipped by flag"
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None, "OPENAI_API_KEY not set"

    payload = {
        "model": IMAGE_MODEL,
        "size": "1024x1024",
        "quality": "medium",
        "background": "opaque",
        "prompt": (
            "Create a child-safe, simple, warm illustration for an Anki flashcard. "
            f"Main sentence meaning: {sentence}. "
            "Use one clear scene, no text, no watermark, no collage, friendly colors."
        ),
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/images/generations",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return None, f"image generation HTTP error: {exc.code}"
    except Exception as exc:
        return None, f"image generation error: {exc}"

    data = (result.get("data") or [{}])[0]
    b64 = data.get("b64_json")
    if not b64:
        return None, "image generation returned no b64_json"
    image_path.write_bytes(base64.b64decode(b64))
    return image_path, None


def extract_audio_segment(source_mp3: Path, target_mp3: Path, start_seconds: float, end_seconds: float) -> None:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    start_seconds = max(0.0, float(start_seconds))
    end_seconds = max(start_seconds, float(end_seconds))
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i",
        str(source_mp3),
        "-af",
        f"atrim=start={start_seconds:.3f}:end={end_seconds:.3f},asetpts=PTS-STARTPTS",
        "-map",
        "0:a:0",
        "-vn",
        "-acodec",
        "libmp3lame",
        "-q:a",
        "4",
        str(target_mp3),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def anki_model() -> genanki.Model:
    return genanki.Model(
        stable_id("language-islands-anki-model-v2"),
        "Language Islands Sentence Model",
        fields=[
            {"name": "SentenceId"},
            {"name": "ThemeHint"},
            {"name": "EnglishSentence"},
            {"name": "RussianTranslation"},
            {"name": "VisualFocus"},
            {"name": "ImageSearchPrompt"},
            {"name": "ImageHtml"},
            {"name": "AudioTag"},
            {"name": "AudioFile"},
        ],
        templates=[
            {
                "name": "RU -> EN recall",
                "qfmt": """
                <div class="card card-ru-en">
                  <div class="theme">{{ThemeHint}}</div>
                  <div class="prompt prompt-ru">{{RussianTranslation}}</div>
                  {{ImageHtml}}
                  <div class="audio-manual">
                    <audio controls preload="none">
                      <source src="{{AudioFile}}" type="audio/mpeg">
                    </audio>
                  </div>
                  <div class="hint">Say the sentence in English.</div>
                </div>
                """,
                "afmt": """
                <div class="card card-ru-en">
                  <div class="theme">{{ThemeHint}}</div>
                  <div class="prompt prompt-ru">{{RussianTranslation}}</div>
                  {{ImageHtml}}
                  <div class="answer answer-en">{{EnglishSentence}}</div>
                  <div class="audio-auto">{{AudioTag}}</div>
                </div>
                """,
            },
            {
                "name": "EN -> RU recognition",
                "qfmt": """
                <div class="card card-en-ru">
                  <div class="theme">{{ThemeHint}}</div>
                  <div class="prompt prompt-en">{{VisualFocus}}</div>
                  {{ImageHtml}}
                  <div class="audio-auto">{{AudioTag}}</div>
                </div>
                """,
                "afmt": """
                <div class="card card-en-ru">
                  <div class="theme">{{ThemeHint}}</div>
                  <div class="prompt prompt-en">{{VisualFocus}}</div>
                  {{ImageHtml}}
                  <div class="answer answer-ru">{{RussianTranslation}}</div>
                </div>
                """,
            },
        ],
        css="""
        .card {
          font-family: Arial, sans-serif;
          font-size: 24px;
          text-align: center;
          color: #222222;
          background: #f8f5ee;
          padding: 24px;
        }
        .theme {
          font-size: 14px;
          color: #827362;
          margin-bottom: 18px;
          letter-spacing: 0.03em;
        }
        .prompt {
          line-height: 1.35;
          margin-bottom: 22px;
        }
        .prompt-ru, .answer-ru {
          font-size: 30px;
          font-family: Arial, sans-serif;
          font-weight: 700;
        }
        .prompt-en, .answer-en {
          font-size: 28px;
          font-family: Georgia, serif;
          font-weight: 700;
        }
        .prompt-en span {
          color: #ff6b6b;
          font-weight: 700;
        }
        .answer {
          margin-top: 24px;
          line-height: 1.35;
        }
        .image-wrap {
          margin: 18px 0 20px;
        }
        .image-wrap img {
          max-width: 100%;
          max-height: 260px;
          border-radius: 14px;
          box-shadow: 0 6px 18px rgba(0, 0, 0, 0.12);
        }
        .hint {
          margin-top: 14px;
          font-size: 16px;
          color: #8a8073;
        }
        .audio-manual {
          margin: 10px 0 0;
        }
        .audio-manual audio {
          width: 220px;
          height: 36px;
        }
        """,
    )


def build_manifest(
    deck_name: str,
    apkg_path: Path,
    tsv_path: Path,
    theme_file: Path,
    asset_dir: Path,
    notes_meta: list[dict],
    skipped_images: list[dict],
) -> dict:
    return {
        "deck_name": deck_name,
        "apkg_path": str(apkg_path),
        "tsv_path": str(tsv_path),
        "theme_file": str(theme_file),
        "asset_dir": str(asset_dir),
        "timing_source": "aligned_subtitle_blocks",
        "note_count": len(notes_meta),
        "notes": notes_meta,
        "skipped_images": skipped_images,
    }


def verify_apkg(apkg_path: Path, expected_notes: int) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        with zipfile.ZipFile(apkg_path) as zf:
            zf.extractall(tmp)
        media_map = json.loads((tmp / "media").read_text(encoding="utf-8"))
        collection_path = tmp / "collection.anki2"
        conn = sqlite3.connect(collection_path)
        try:
            note_count = conn.execute("select count(*) from notes").fetchone()[0]
            card_count = conn.execute("select count(*) from cards").fetchone()[0]
        finally:
            conn.close()
    return {
        "note_count": note_count,
        "card_count": card_count,
        "media_file_count": len(media_map),
        "expected_notes": expected_notes,
    }


def write_tsv(tsv_path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "Theme_Hint",
        "English_Sentence",
        "Russian_Translation",
        "Visual_Focus",
        "Image_Search_Prompt",
    ]
    with tsv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Anki deck from a language island theme.")
    parser.add_argument("theme_file", type=Path, help="Path to English theme.json")
    parser.add_argument("--skip-images", action="store_true", help="Skip image generation")
    args = parser.parse_args()

    theme_file = args.theme_file.resolve()
    theme = load_theme(theme_file)
    if theme.get("level"):
        raise ValueError("Anki v1 currently supports the English basic theme source only")

    asset_dir = resolve_theme_asset_dir(theme_file, theme)
    prefix = theme_prefix(theme)
    once_mp3 = asset_dir / f"{prefix}__04__shadowing_en.mp3"
    srt_path = asset_dir / f"{prefix}__13__shadowing_ru.srt"
    if not once_mp3.exists():
        raise FileNotFoundError(f"Missing once MP3: {once_mp3}")
    if not srt_path.exists():
        raise FileNotFoundError(f"Missing SRT: {srt_path}")

    entries = theme["entries"]
    blocks = [
        {
            "index": idx,
            "start_seconds": start,
            "end_seconds": end,
            "text": text,
        }
        for idx, (start, end, text) in enumerate(
            aligned_subtitle_blocks(entries, once_mp3),
            start=1,
        )
    ]
    if len(blocks) != len(entries):
        raise ValueError(
            f"Aligned timing block count {len(blocks)} does not match theme entry count {len(entries)}"
        )
    srt_blocks = parse_srt_blocks(srt_path)
    if len(srt_blocks) != len(entries):
        raise ValueError(
            f"SRT block count {len(srt_blocks)} does not match theme entry count {len(entries)}"
        )

    deck_name = f"English Basic - Theme {str(theme['theme_id']).split('-')[-1]}"
    ANKI_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    debug_dir = ANKI_OUTPUT_ROOT / f"{theme['theme_id']}-debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    deck_path = ANKI_OUTPUT_ROOT / f"{deck_name}.apkg"
    tsv_path = ANKI_OUTPUT_ROOT / f"{theme['theme_id']}__anki_import.tsv"

    model = anki_model()
    deck = genanki.Deck(stable_id(f"{theme['theme_id']}::anki-v2::deck"), deck_name)
    media_files: list[str] = []
    notes_meta: list[dict] = []
    skipped_images: list[dict] = []
    tsv_rows: list[dict] = []
    current_theme_hint = theme_hint(theme)

    for idx, entry in enumerate(entries, start=1):
        block = blocks[idx - 1]
        english_sentence = target_text(entry)
        russian_translation = native_text(entry)
        visual_focus = visual_focus_text(english_sentence)
        image_search_prompt = build_image_search_prompt(english_sentence)

        audio_name = f"{theme['theme_id']}__{idx:03d}__audio.mp3"
        audio_path = debug_dir / audio_name
        extract_audio_segment(once_mp3, audio_path, block["start_seconds"], block["end_seconds"])
        media_files.append(str(audio_path))

        image_path, image_error = maybe_generate_image(
            sentence_id=idx,
            sentence=english_sentence,
            out_dir=debug_dir,
            skip_images=args.skip_images,
        )
        image_html = ""
        if image_path and image_path.exists():
            media_files.append(str(image_path))
            image_html = f'<div class="image-wrap"><img src="{image_path.name}" alt="Sentence illustration"></div>'
        else:
            skipped_images.append({"sentence_id": idx, "reason": image_error or "image not available"})

        note = genanki.Note(
            model=model,
            fields=[
                str(idx),
                current_theme_hint,
                english_sentence,
                russian_translation,
                visual_focus,
                image_search_prompt,
                image_html,
                f"[sound:{audio_name}]",
                audio_name,
            ],
            guid=f"{theme['theme_id']}::{idx}",
            tags=[str(theme["theme_id"]), "english", "basic", "anki"],
        )
        deck.add_note(note)

        tsv_rows.append(
            {
                "Theme_Hint": current_theme_hint,
                "English_Sentence": english_sentence,
                "Russian_Translation": russian_translation,
                "Visual_Focus": visual_focus,
                "Image_Search_Prompt": image_search_prompt,
            }
        )
        notes_meta.append(
            {
                "sentence_id": idx,
                "theme_hint": current_theme_hint,
                "english": english_sentence,
                "russian": russian_translation,
                "visual_focus": visual_focus,
                "image_search_prompt": image_search_prompt,
                "audio_file": audio_name,
                "image_file": image_path.name if image_path else None,
                "start_seconds": block["start_seconds"],
                "end_seconds": block["end_seconds"],
            }
        )

    package = genanki.Package(deck)
    package.media_files = media_files
    package.write_to_file(deck_path)
    write_tsv(tsv_path, tsv_rows)

    manifest_path = debug_dir / "manifest.json"
    manifest = build_manifest(deck_name, deck_path, tsv_path, theme_file, asset_dir, notes_meta, skipped_images)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    verification = verify_apkg(deck_path, expected_notes=len(entries))
    verification_path = debug_dir / "verification.json"
    verification_path.write_text(json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Deck: {deck_path}")
    print(f"TSV: {tsv_path}")
    print(f"Debug dir: {debug_dir}")
    print(json.dumps(verification, ensure_ascii=False))


if __name__ == "__main__":
    main()
