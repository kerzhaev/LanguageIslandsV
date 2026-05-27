from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THEMES_DIR = ROOT / "themes"


def main() -> None:
    theme_files = sorted(
        path
        for path in THEMES_DIR.rglob("theme.json")
        if "_template" not in path.parts
    )
    if not theme_files:
        print("No theme.json files found.")
        return

    for theme_file in theme_files:
        print(f"Building: {theme_file}")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "build_island.py"), str(theme_file)], check=True)


if __name__ == "__main__":
    main()
