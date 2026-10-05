#!/usr/bin/env python3
"""Interleave a timestamped transcript with extracted frame content.

What the speaker says while a chart is on screen is usually the interpretation
of that chart, so keeping the two adjacent is most of the value. This produces
a raw merged document; the summarising and restructuring pass happens after.

Usage:
    python build_notes.py work/frame_content.json transcript.vtt --out notes-raw.md
"""

import argparse
import json
import re
from pathlib import Path

TS = re.compile(r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[.,](\d{3})")


def parse_transcript(path):
    """Parse WebVTT or SRT into [(start_seconds, text)]."""
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    cues, start, buf = [], None, []

    def flush():
        if start is not None and buf:
            text = " ".join(b.strip() for b in buf if b.strip())
            text = re.sub(r"<[^>]+>", "", text)          # strip VTT inline tags
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                cues.append((start, text))

    for line in lines:
        m = TS.search(line)
        if m:
            flush()
            buf = []
            h, mi, s, ms = (int(m.group(i)) for i in range(1, 5))
            start = h * 3600 + mi * 60 + s + ms / 1000
        elif line.strip().isdigit() and not buf:
            continue                                       # SRT cue number
        elif line.strip().upper().startswith("WEBVTT"):
            continue
        else:
            buf.append(line)
    flush()

    # Auto-captions repeat rolling text; drop cues fully contained in the previous.
    deduped = []
    for ts, text in cues:
        if deduped and (text in deduped[-1][1] or deduped[-1][1].endswith(text)):
            continue
        deduped.append((ts, text))
    return deduped


def hhmmss(seconds):
    s = int(seconds)
    return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frame_content")
    ap.add_argument("transcript", nargs="?", help="VTT or SRT file (optional)")
    ap.add_argument("--out", default="notes-raw.md")
    ap.add_argument("--embed-images", action="store_true",
                    help="link each frame image next to its extracted content")
    args = ap.parse_args()

    fc = json.loads(Path(args.frame_content).read_text())
    frames = fc["frames"]
    cues = parse_transcript(args.transcript) if args.transcript else []

    events = [{"t": f["timestamp"], "kind": "frame", "data": f} for f in frames]
    events += [{"t": t, "kind": "speech", "data": text} for t, text in cues]
    events.sort(key=lambda e: (e["t"], 0 if e["kind"] == "frame" else 1))

    out, speech_buf = [], []

    def flush_speech():
        if speech_buf:
            out.append(" ".join(speech_buf))
            out.append("")
            speech_buf.clear()

    out.append("# Recording notes (raw merge)\n")
    out.append("<!-- Transcript and on-screen content interleaved by timestamp. "
               "Not yet summarised. -->\n")

    for ev in events:
        if ev["kind"] == "speech":
            speech_buf.append(ev["data"])
        else:
            flush_speech()
            f = ev["data"]
            out.append(f"### On screen at {hhmmss(f['timestamp'])}\n")
            if args.embed_images:
                out.append(f"![frame {f['index']}]({f['path']})\n")
            out.append(f["content"])
            out.append("")
    flush_speech()

    Path(args.out).write_text("\n".join(out), encoding="utf-8")
    print(f"Merged {len(frames)} screen captures and {len(cues)} transcript cues -> {args.out}")


if __name__ == "__main__":
    main()
