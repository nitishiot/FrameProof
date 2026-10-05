#!/usr/bin/env python3
"""Sample frames from a video on a fixed interval, then drop near-duplicates.

Fixed-interval sampling beats ffmpeg scene detection for screen recordings:
scene detection misses slow slide builds and over-fires on cursor movement or
a webcam overlay. We sample densely and let perceptual hashing collapse the
runs of identical slides.

Usage:
    python extract_frames.py recording.mp4 --out work/ [--interval 5] [--threshold 6]

Writes work/frames/NNNN.jpg and work/frames.json (timestamps + paths).
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image


def dhash(path, size=8):
    """Difference hash: compare each pixel to its right neighbour.

    Returns an int whose bits encode horizontal gradients. Robust to
    compression noise and small cursor movement, sensitive to real content
    change. Avoids depending on the `imagehash` package.
    """
    img = Image.open(path).convert("L").resize((size + 1, size), Image.LANCZOS)
    px = img.tobytes()  # grayscale: one byte per pixel, row-major
    bits = 0
    for row in range(size):
        for col in range(size):
            left = px[row * (size + 1) + col]
            right = px[row * (size + 1) + col + 1]
            bits = (bits << 1) | int(left > right)
    return bits


def hamming(a, b):
    return bin(a ^ b).count("1")


def duration_seconds(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", default="work")
    ap.add_argument("--interval", type=float, default=5.0,
                    help="seconds between sampled frames (default 5)")
    ap.add_argument("--threshold", type=int, default=6,
                    help="hamming distance below which frames count as duplicates")
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found. Install it: brew install ffmpeg / apt install ffmpeg")

    video = Path(args.video)
    if not video.exists():
        sys.exit(f"No such file: {video}")

    out = Path(args.out)
    raw = out / "_raw"
    keep = out / "frames"
    raw.mkdir(parents=True, exist_ok=True)
    keep.mkdir(parents=True, exist_ok=True)

    total = duration_seconds(video)
    print(f"Video is {total/60:.1f} min. Sampling every {args.interval}s...")

    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(video),
         "-vf", f"fps=1/{args.interval}", "-q:v", "3",
         str(raw / "%05d.jpg")],
        check=True,
    )

    sampled = sorted(raw.glob("*.jpg"))
    print(f"Sampled {len(sampled)} frames. Deduplicating...")

    kept = []
    last_hash = None
    for i, frame in enumerate(sampled):
        h = dhash(frame)
        if last_hash is not None and hamming(h, last_hash) < args.threshold:
            continue
        last_hash = h
        # Frame i covers the window starting at i * interval.
        ts = i * args.interval
        dest = keep / f"{len(kept):04d}.jpg"
        shutil.copy(frame, dest)
        kept.append({"index": len(kept), "timestamp": round(ts, 1), "path": str(dest)})

    shutil.rmtree(raw, ignore_errors=True)

    manifest = out / "frames.json"
    manifest.write_text(json.dumps({"video": str(video), "duration": total,
                                    "interval": args.interval, "frames": kept}, indent=2))

    print(f"Kept {len(kept)} distinct frames (from {len(sampled)}) -> {keep}")
    print(f"Manifest: {manifest}")
    if len(kept) > 80:
        print("\nNote: that's a lot of frames for one video. If the recording has a "
              "webcam overlay or animated background, raise --threshold to 10-12.")


if __name__ == "__main__":
    main()
