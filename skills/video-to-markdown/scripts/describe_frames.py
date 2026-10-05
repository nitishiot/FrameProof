#!/usr/bin/env python3
"""Send kept frames to a vision model and extract their content as markdown.

The prompt asks for extraction, not description. A frame showing a bar chart
should come back as a data table; a frame showing a slide should come back as
its text. Frames with nothing to extract return NONE and are dropped, which is
what keeps the final document from filling up with "a person is speaking".

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python describe_frames.py work/frames.json [--model claude-sonnet-5] [--ocr]

Writes work/frame_content.json.
"""

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API_URL = "https://api.anthropic.com/v1/messages"

PROMPT = """This is a frame from a screen recording, captured at {ts}.

Extract the informational content of this frame as markdown. Follow these rules:

- Chart or graph: output a markdown table of the underlying data, with axis
  labels and units. If values are not printed on the chart, estimate them from
  the geometry and add the line `> Values estimated from the chart; verify.`
- Slide, document, or diagram: output the text as markdown, preserving heading
  and bullet structure. For a diagram, also describe the relationships in one
  or two lines.
- Code or terminal output: output it in a fenced code block, verbatim.
- Anything else — a speaker, a webcam, a title card, a blank or decorative
  screen, or a frame whose content you already fully captured in the previous
  frame: output exactly NONE and nothing else.

Do not add commentary, preamble, or a heading of your own. Output only the
extracted content, or NONE.{ocr}"""


def ocr_text(path):
    if not shutil.which("tesseract"):
        return ""
    try:
        out = subprocess.run(["tesseract", str(path), "stdout"],
                             capture_output=True, text=True, timeout=60)
        text = " ".join(out.stdout.split())
        return text[:1500]
    except Exception:
        return ""


def call_api(api_key, model, image_b64, timestamp, ocr_hint):
    ocr_block = ""
    if ocr_hint:
        ocr_block = ("\n\nOCR of this frame, which may help with small or "
                     f"low-contrast type (it is noisy — trust the image where "
                     f"they disagree):\n{ocr_hint}")

    payload = {
        "model": model,
        "max_tokens": 1500,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64",
                                             "media_type": "image/jpeg",
                                             "data": image_b64}},
                {"type": "text", "text": PROMPT.format(ts=timestamp, ocr=ocr_block)},
            ],
        }],
    }

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode(),
        headers={"content-type": "application/json",
                 "x-api-key": api_key,
                 "anthropic-version": "2023-06-01"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()


def hhmmss(seconds):
    s = int(seconds)
    return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", help="work/frames.json from extract_frames.py")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--ocr", action="store_true",
                    help="run tesseract and pass the text alongside the image")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Set ANTHROPIC_API_KEY first.")

    manifest = json.loads(Path(args.manifest).read_text())
    frames = manifest["frames"]
    print(f"Extracting content from {len(frames)} frames with {args.model}...")

    def work(frame):
        img_b64 = base64.b64encode(Path(frame["path"]).read_bytes()).decode()
        hint = ocr_text(frame["path"]) if args.ocr else ""
        try:
            content = call_api(api_key, args.model, img_b64, hhmmss(frame["timestamp"]), hint)
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300]
            print(f"  frame {frame['index']:>3}  API error {e.code}: {body}")
            return None
        except Exception as e:
            print(f"  frame {frame['index']:>3}  failed: {e}")
            return None

        if content.strip().upper().startswith("NONE"):
            print(f"  frame {frame['index']:>3}  {hhmmss(frame['timestamp'])}  (skipped)")
            return None
        print(f"  frame {frame['index']:>3}  {hhmmss(frame['timestamp'])}  kept")
        return {**frame, "content": content}

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = [r for r in pool.map(work, frames) if r]

    results.sort(key=lambda r: r["timestamp"])
    out = Path(args.manifest).parent / "frame_content.json"
    out.write_text(json.dumps({"model": args.model, "frames": results}, indent=2))
    print(f"\n{len(results)} frames had extractable content -> {out}")


if __name__ == "__main__":
    main()
