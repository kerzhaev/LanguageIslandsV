from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile

import imageio_ffmpeg
from mutagen.mp3 import MP3

try:
    from pypdf import PdfReader, PdfWriter
except Exception:
    from PyPDF2 import PdfReader, PdfWriter


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "output"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def numbered_theme_dirs() -> list[Path]:
    return sorted(
        [path for path in OUTPUT_ROOT.iterdir() if path.is_dir() and path.name[:1].isdigit()],
        key=lambda path: int(path.name.split(".", 1)[0]),
    )


def level_dir(theme_dir: Path, level: str) -> Path:
    candidate = theme_dir / f"level-{level}"
    return candidate if candidate.exists() else theme_dir


def find_file(folder: Path, suffix: str) -> Path:
    matches = sorted(path for path in folder.iterdir() if path.is_file() and path.name.endswith(suffix))
    if not matches:
        raise FileNotFoundError(f"Missing {suffix} in {folder}")
    return matches[0]


def combine_pdfs(paths: list[Path], target: Path) -> None:
    writer = PdfWriter()
    for path in paths:
        reader = PdfReader(str(path))
        for page in reader.pages:
            writer.add_page(page)
    with target.open("wb") as handle:
        writer.write(handle)


def concat_media(paths: list[Path], target: Path) -> None:
    with NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
        list_path = Path(handle.name)
        for path in paths:
            escaped = path.as_posix().replace("'", "'\\''")
            handle.write(f"file '{escaped}'\n")
    try:
        subprocess.run(
            [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(target)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    finally:
        list_path.unlink(missing_ok=True)


def mp3_duration_seconds(path: Path) -> float:
    return float(MP3(str(path)).info.length)


def parse_srt_timestamp(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(",")
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(millis) / 1000.0
    )


def format_srt_timestamp(seconds: float) -> str:
    millis = max(0, int(round(seconds * 1000)))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def combine_srts(srt_paths: list[Path], mp3_paths: list[Path], target: Path) -> None:
    timestamp_re = re.compile(r"^(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})$")
    blocks: list[str] = []
    cue_index = 1
    offset = 0.0

    for srt_path, mp3_path in zip(srt_paths, mp3_paths):
        content = srt_path.read_text(encoding="utf-8-sig").strip()
        sections = [section.strip() for section in content.split("\n\n") if section.strip()]

        for section in sections:
            lines = section.splitlines()
            if len(lines) < 3:
                continue
            match = timestamp_re.match(lines[1].strip())
            if not match:
                continue
            start = parse_srt_timestamp(match.group(1)) + offset
            end = parse_srt_timestamp(match.group(2)) + offset
            text_lines = lines[2:]
            blocks.extend(
                [
                    str(cue_index),
                    f"{format_srt_timestamp(start)} --> {format_srt_timestamp(end)}",
                    *text_lines,
                    "",
                ]
            )
            cue_index += 1

        offset += mp3_duration_seconds(mp3_path)

    target.write_text("\n".join(blocks).strip() + "\n", encoding="utf-8-sig")


def build_level(level: str) -> None:
    dirs = [level_dir(theme_dir, level) for theme_dir in numbered_theme_dirs()]
    mp3s = [find_file(folder, "__04__shadowing_en.mp3") for folder in dirs]
    mp4s = [find_file(folder, "__14__shadowing_video_en.mp4") for folder in dirs]
    srts = [find_file(folder, "__13__shadowing_ru.srt") for folder in dirs]

    if level in {"advanced", "hard"}:
        bilingual = [find_file(folder, "__03__bilingual_study.pdf") for folder in dirs]
        active = [find_file(folder, "__05__active_recall.pdf") for folder in dirs]
        combine_pdfs(bilingual, OUTPUT_ROOT / f"all-themes-{level}-bilingual-study.pdf")
        combine_pdfs(active, OUTPUT_ROOT / f"all-themes-{level}-active-recall.pdf")

    concat_media(mp3s, OUTPUT_ROOT / f"all-themes-{level}-shadowing.mp3")
    concat_media(mp4s, OUTPUT_ROOT / f"all-themes-{level}-shadowing-video.mp4")
    combine_srts(srts, mp3s, OUTPUT_ROOT / f"all-themes-{level}-shadowing_ru.srt")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build combined outputs for basic / advanced / hard levels.")
    parser.add_argument("levels", nargs="*", default=["hard", "advanced", "basic"])
    args = parser.parse_args()

    for level in args.levels:
        build_level(level)
        print(f"Built combined outputs for {level}")


if __name__ == "__main__":
    main()
