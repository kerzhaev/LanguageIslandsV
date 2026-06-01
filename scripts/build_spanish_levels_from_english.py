from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGLISH_ROOT = ROOT / "themes"
SPANISH_ROOT = ROOT / "themes" / "spanish"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def target_text(entry: dict) -> str:
    return str(entry.get("en") or entry.get("text") or "").strip()


def google_translate(text: str, source: str = "en", target: str = "es") -> str:
    query = urllib.parse.quote(text)
    url = (
        "https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl={source}&tl={target}&dt=t&q={query}"
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    translated = "".join(part[0] for part in payload[0] if part and part[0])
    return translated.strip()


def find_english_theme(number: int, level: str) -> Path:
    candidates = sorted(ENGLISH_ROOT.glob(f"theme-{number:02d}__*"))
    for candidate in candidates:
        theme_path = candidate / f"level-{level}" / "theme.json"
        if theme_path.exists():
            return theme_path
    raise FileNotFoundError(f"English theme {number:02d} level-{level} not found")


def find_spanish_basic(number: int) -> Path:
    candidates = sorted(SPANISH_ROOT.glob(f"theme-{number:02d}__*"))
    for candidate in candidates:
        theme_path = candidate / "level-basic" / "theme.json"
        if theme_path.exists():
            return theme_path
    raise FileNotFoundError(f"Spanish basic theme {number:02d} not found")


def build_level(number: int, level: str, pause_seconds: float) -> Path:
    english_path = find_english_theme(number, level)
    spanish_basic_path = find_spanish_basic(number)

    english_theme = read_json(english_path)
    spanish_basic = read_json(spanish_basic_path)

    translated_entries = []
    cache: dict[str, str] = {}
    for entry in english_theme["entries"]:
        english = target_text(entry)
        if english not in cache:
            cache[english] = google_translate(english)
            time.sleep(pause_seconds)
        translated_entries.append(
            {
                "text": cache[english],
                "ru": entry["ru"],
            }
        )

    spanish_theme = {
        "theme_id": spanish_basic["theme_id"],
        "slug": spanish_basic["slug"],
        "theme_label": english_theme["theme_label"],
        "title": google_translate(english_theme["title"]) if level != "basic" else spanish_basic["title"],
        "folder_name": spanish_basic["folder_name"],
        "language": "spanish",
        "level": level,
        "video": english_theme.get("video", spanish_basic.get("video", {})),
        "entries": translated_entries,
    }

    output_path = spanish_basic_path.parent.parent / f"level-{level}" / "theme.json"
    write_json(output_path, spanish_theme)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Spanish advanced/hard themes from English source themes.")
    parser.add_argument("--from", dest="start", type=int, default=1)
    parser.add_argument("--to", dest="end", type=int, default=15)
    parser.add_argument("--levels", nargs="*", default=["advanced", "hard"])
    parser.add_argument("--pause", type=float, default=0.2)
    args = parser.parse_args()

    for level in args.levels:
        for number in range(args.start, args.end + 1):
            path = build_level(number, level, args.pause)
            print(f"Built {path}")


if __name__ == "__main__":
    main()
