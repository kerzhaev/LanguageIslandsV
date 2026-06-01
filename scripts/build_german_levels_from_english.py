from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGLISH_ROOT = ROOT / "themes"
SPANISH_ROOT = ROOT / "themes" / "spanish"
GERMAN_ROOT = ROOT / "themes" / "german"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def target_text(entry: dict) -> str:
    return str(entry.get("en") or entry.get("text") or "").strip()


def google_translate(text: str, source: str = "en", target: str = "de") -> str:
    query = urllib.parse.quote(text)
    url = (
        "https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl={source}&tl={target}&dt=t&q={query}"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    last_error: Exception | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return "".join(part[0] for part in payload[0] if part and part[0]).strip()
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Translation failed for: {text}") from last_error


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return ascii_text or "theme"


def find_english_theme(number: int, level: str) -> Path:
    candidates = sorted(ENGLISH_ROOT.glob(f"theme-{number:02d}__*"))
    for candidate in candidates:
        if level == "basic":
            root_theme = candidate / "theme.json"
            if root_theme.exists():
                return root_theme
        level_theme = candidate / f"level-{level}" / "theme.json"
        if level_theme.exists():
            return level_theme
    raise FileNotFoundError(f"English theme {number:02d} level-{level} not found")


def find_spanish_basic(number: int) -> Path:
    candidates = sorted(SPANISH_ROOT.glob(f"theme-{number:02d}__*"))
    for candidate in candidates:
        theme_path = candidate / "level-basic" / "theme.json"
        if theme_path.exists():
            return theme_path
    raise FileNotFoundError(f"Spanish basic theme {number:02d} not found")


def find_existing_german_theme(number: int) -> Path | None:
    candidates = sorted(GERMAN_ROOT.glob(f"theme-{number:02d}__*"))
    for candidate in candidates:
        basic_theme = candidate / "level-basic" / "theme.json"
        if basic_theme.exists():
            return basic_theme
    return None


def german_folder_name(number: int, english_title: str, existing_basic: dict | None) -> str:
    if number == 1 and existing_basic:
        return str(existing_basic["folder_name"])
    return f"German\\{number}. {english_title}"


def build_level(number: int, level: str, pause_seconds: float, title_cache: dict[str, str]) -> Path:
    english_path = find_english_theme(number, level)
    english_theme = read_json(english_path)
    spanish_basic = read_json(find_spanish_basic(number))
    german_basic_existing = find_existing_german_theme(number)
    german_basic = read_json(german_basic_existing) if german_basic_existing else None

    entries = []
    cache: dict[str, str] = {}
    for entry in english_theme["entries"]:
        english = target_text(entry)
        if english not in cache:
            cache[english] = google_translate(english)
            time.sleep(pause_seconds)
        entries.append({"text": cache[english], "ru": entry["ru"]})

    english_title = str(english_theme["title"])
    if english_title not in title_cache:
        title_cache[english_title] = google_translate(english_title)
        time.sleep(pause_seconds)
    german_title = title_cache[english_title]

    if number == 1 and german_basic:
        slug = german_basic["slug"]
    else:
        slug = slugify(german_title)

    theme = {
        "theme_id": f"theme-{number:02d}-de",
        "slug": slug,
        "theme_label": english_theme["theme_label"],
        "title": german_title,
        "folder_name": german_folder_name(number, english_title, german_basic),
        "language": "german",
        "level": level,
        "video": english_theme.get("video", {}),
        "entries": entries,
    }

    theme_dir = GERMAN_ROOT / f"theme-{number:02d}__{slug}"
    output_path = theme_dir / f"level-{level}" / "theme.json"
    write_json(output_path, theme)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build German basic/advanced/hard themes from English source themes.")
    parser.add_argument("--from", dest="start", type=int, default=1)
    parser.add_argument("--to", dest="end", type=int, default=15)
    parser.add_argument("--levels", nargs="*", default=["basic", "advanced", "hard"])
    parser.add_argument("--pause", type=float, default=0.15)
    args = parser.parse_args()

    title_cache: dict[str, str] = {}
    for level in args.levels:
        for number in range(args.start, args.end + 1):
            path = build_level(number, level, args.pause, title_cache)
            print(f"Built {path}")


if __name__ == "__main__":
    main()
