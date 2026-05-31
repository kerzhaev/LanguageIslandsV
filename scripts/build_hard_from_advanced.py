from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THEMES_ROOT = ROOT / "themes"


def load_theme(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def merge_entries(entries: list[dict]) -> list[dict]:
    merged: list[list[dict]] = []
    current: list[dict] = []
    current_chars = 0

    for entry in entries:
        text = str(entry["en"]).strip()
        text_len = len(text)

        if not current:
            current = [entry]
            current_chars = text_len
            continue

        too_long_alone = current_chars >= 115
        combined_too_long = current_chars + 1 + text_len > 210
        if len(current) >= 2 or too_long_alone or combined_too_long:
            merged.append(current)
            current = [entry]
            current_chars = text_len
            continue

        current.append(entry)
        current_chars += 1 + text_len

    if current:
        merged.append(current)

    return [
        {
            "en": " ".join(str(item["en"]).strip() for item in group),
            "ru": " ".join(str(item["ru"]).strip() for item in group),
        }
        for group in merged
    ]


def build_hard_theme(advanced_theme: dict) -> dict:
    return {
        "theme_id": advanced_theme["theme_id"],
        "slug": advanced_theme["slug"],
        "theme_label": advanced_theme["theme_label"],
        "title": advanced_theme["title"],
        "folder_name": advanced_theme["folder_name"],
        "level": "hard",
        "video": advanced_theme.get(
            "video",
            {
                "width": 1280,
                "height": 720,
                "fps": 24,
                "background_color": "#F6F0E5",
            },
        ),
        "entries": merge_entries(advanced_theme["entries"]),
    }


def write_theme(path: Path, theme: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(theme, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create level-hard themes from level-advanced themes.")
    parser.add_argument("--from", dest="start", type=int, default=2)
    parser.add_argument("--to", dest="end", type=int, default=15)
    args = parser.parse_args()

    for number in range(args.start, args.end + 1):
        candidates = sorted(THEMES_ROOT.glob(f"theme-{number:02d}__*"))
        theme_dir = next(
            candidate
            for candidate in candidates
            if (candidate / "level-advanced" / "theme.json").exists()
        )
        advanced_path = theme_dir / "level-advanced" / "theme.json"
        hard_path = theme_dir / "level-hard" / "theme.json"
        advanced_theme = load_theme(advanced_path)
        hard_theme = build_hard_theme(advanced_theme)
        write_theme(hard_path, hard_theme)
        print(f"Wrote {hard_path}")


if __name__ == "__main__":
    main()
