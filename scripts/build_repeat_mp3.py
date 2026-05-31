"""Build repeat MP3 from once MP3 by splitting into phrase segments.

Uses silence detection to find phrase boundaries in the once MP3,
then assembles a repeat MP3 where each phrase is repeated 5 times
with a short pause between repetitions and a longer pause between groups.
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import imageio_ffmpeg


def detect_silences(mp3_path: Path, threshold_db: int = -35, min_silence: float = 0.18):
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
    starts = [float(m) for m in re.findall(r"silence_start:\s*([0-9.]+)", output)]
    ends = [float(m) for m in re.findall(r"silence_end:\s*([0-9.]+)", output)]
    return list(zip(starts, ends))


def speech_chunks(total_seconds: float, silences):
    chunks = []
    cursor = 0.0
    for silence_start, silence_end in silences:
        if silence_start > cursor + 0.05:
            chunks.append((cursor, silence_start))
        cursor = max(cursor, silence_end)
    if total_seconds > cursor + 0.05:
        chunks.append((cursor, total_seconds))
    return chunks


def get_duration(mp3_path: Path) -> float:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ffmpeg_exe, "-i", str(mp3_path), "-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    match = re.search(r"Duration:\s*([0-9:.]+)", output)
    if not match:
        raise RuntimeError("Cannot determine duration")
    parts = match.group(1).split(":")
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])


def extract_segment(mp3_path: Path, start: float, end: float, out_path: Path):
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe,
        "-y",
        "-i",
        str(mp3_path),
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-c",
        "copy",
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def main():
    if len(sys.argv) < 3:
        print(
            "Usage: python build_repeat_mp3.py <once_mp3> <output_repeat_mp3> [phrase_count]"
        )
        sys.exit(1)

    once_mp3 = Path(sys.argv[1])
    out_mp3 = Path(sys.argv[2])
    phrase_count = int(sys.argv[3]) if len(sys.argv) > 3 else None

    if not once_mp3.exists():
        print(f"Once MP3 not found: {once_mp3}")
        sys.exit(1)

    print(f"Once MP3: {once_mp3.name}")
    print(f"Output: {out_mp3.name}")

    total = get_duration(once_mp3)
    print(f"Duration: {total:.2f}s")

    silences = detect_silences(once_mp3)
    print(f"Silences detected: {len(silences)}")

    chunks = speech_chunks(total, silences)
    print(f"Speech chunks: {len(chunks)}")

    if phrase_count and len(chunks) != phrase_count:
        print(f"WARNING: Expected {phrase_count} phrases, found {len(chunks)} chunks")

    # Extract each phrase to a temp file
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        segments = []
        for i, (start, end) in enumerate(chunks):
            seg_path = tmp / f"seg_{i:03d}.mp3"
            extract_segment(once_mp3, start, end, seg_path)
            segments.append(seg_path)

        # Build concat list: each phrase 5 times with 0.6s silence between
        # and 1.5s silence between groups
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        concat_list = tmp / "concat.txt"
        silence_short = tmp / "silence_short.mp3"
        silence_long = tmp / "silence_long.mp3"

        # Generate short silence (0.6s)
        subprocess.run(
            [
                ffmpeg_exe,
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=r=24000:cl=mono",
                "-t",
                "0.6",
                "-q:a",
                "9",
                str(silence_short),
            ],
            capture_output=True,
            check=True,
        )

        # Generate long silence (1.5s)
        subprocess.run(
            [
                ffmpeg_exe,
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=r=24000:cl=mono",
                "-t",
                "1.5",
                "-q:a",
                "9",
                str(silence_long),
            ],
            capture_output=True,
            check=True,
        )

        with open(concat_list, "w") as f:
            for i, seg in enumerate(segments):
                for rep in range(5):
                    f.write(f"file '{seg}'\n")
                    if rep < 4:
                        f.write(f"file '{silence_short}'\n")
                if i < len(segments) - 1:
                    f.write(f"file '{silence_long}'\n")

        # Concatenate
        cmd = [
            ffmpeg_exe,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            str(out_mp3),
        ]
        subprocess.run(cmd, capture_output=True, check=True)

    size = out_mp3.stat().st_size
    dur = get_duration(out_mp3)
    print(f"Repeat MP3: {size:,} bytes, {dur:.1f}s")
    print("Done!")


if __name__ == "__main__":
    main()
