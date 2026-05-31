"""Generate Spanish TTS audio using edge-tts (Microsoft Edge neural voices).

This is a fallback when NaturalReaders browser automation is not available.
Uses es-ES-ElviraNeural (female, friendly) as the closest equivalent to
NaturalReaders Plus Voices for Spanish (Spain).
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import edge_tts

VOICE = "es-ES-ElviraNeural"
RATE = "-5%"  # Slightly slower for learning


async def generate_mp3(
    text: str, output_path: Path, voice: str = VOICE, rate: str = RATE
) -> None:
    """Generate MP3 from text using edge-tts."""
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(str(output_path))
    print(f"Generated: {output_path.name} ({output_path.stat().st_size} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Spanish TTS audio with edge-tts"
    )
    parser.add_argument(
        "target_dir", type=Path, help="Output directory with txt input files"
    )
    args = parser.parse_args()

    target_dir: Path = args.target_dir

    # Find input files
    files = list(target_dir.iterdir())
    once_input = next(
        (
            f
            for f in files
            if f.name.endswith("__04a__shadowing_es__naturalreaders_input.txt")
        ),
        None,
    )
    repeat_input = next(
        (
            f
            for f in files
            if f.name.endswith("__06a__shadowing_es_repeat__naturalreaders_input.txt")
        ),
        None,
    )

    if not once_input or not repeat_input:
        print("Spanish input files not found in:", target_dir)
        raise SystemExit(1)

    once_text = once_input.read_text(encoding="utf-8").strip()
    repeat_text = repeat_input.read_text(encoding="utf-8").strip()

    once_mp3 = target_dir / once_input.name.replace(
        "__04a__shadowing_es__naturalreaders_input.txt", "__04__shadowing_es.mp3"
    )
    repeat_mp3 = target_dir / repeat_input.name.replace(
        "__06a__shadowing_es_repeat__naturalreaders_input.txt",
        "__06__shadowing_es_repeat.mp3",
    )

    print(f"Voice: {VOICE}")
    print(f"Rate: {RATE}")
    print(f"Once text length: {len(once_text)} chars")
    print(f"Repeat text length: {len(repeat_text)} chars")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    if not once_mp3.exists():
        print("\nGenerating once MP3...")
        loop.run_until_complete(generate_mp3(once_text, once_mp3))
    else:
        print(f"Once MP3 already exists: {once_mp3.name}")

    if not repeat_mp3.exists():
        print("\nGenerating repeat MP3...")
        loop.run_until_complete(generate_mp3(repeat_text, repeat_mp3))
    else:
        print(f"Repeat MP3 already exists: {repeat_mp3.name}")

    loop.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
