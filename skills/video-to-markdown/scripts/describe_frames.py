#!/usr/bin/env python3
"""Send kept frames to a vision model and extract their content as markdown.

The prompt asks for extraction, not description. A frame showing a bar chart
should come back as a data table; a frame showing a slide should come back as
its text. Frames with nothing to extract return NONE and are dropped, which is
what keeps the final document from filling up with "a person is speaking".

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python describe_frames.py work/frames.json [--model claude-sonnet-5-5] [--ocr]

Writes work/frame_content.json. Frames that fail after retries (rate limits, truncated
or refused replies) go to work/failed_frames.json and the script exits non-zero;
re-run with --retry-failed to process only those and merge them into frame_content.json.
"""

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API_URL = "https://api.anthropic.com/v1/messages"
MAX_TOKENS = 8000  # headroom for model thinking plus a dense table; 1500 truncated silently
MAX_ATTEMPTS = 5
RETRYABLE = {408, 409, 429, 500, 502, 503, 504, 529}

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
        "max_tokens": MAX_TOKENS,
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
    for attempt in range(MAX_ATTEMPTS):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            if e.code not in RETRYABLE or attempt == MAX_ATTEMPTS - 1:
                raise
            delay = float(e.headers.get("retry-after") or 2 ** attempt)
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == MAX_ATTEMPTS - 1:
                raise
            delay = 2 ** attempt
        time.sleep(min(delay, 60))

    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
    # A truncated, refused or empty reply must not be saved as if it were the frame's content.
    if data.get("stop_reason") in ("max_tokens", "refusal") or not text:
        raise ValueError(f"unusable reply (stop_reason={data.get('stop_reason')}, {len(text)} chars)")
    return text


def hhmmss(seconds):
    s = int(seconds)
    return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", help="work/frames.json from extract_frames.py")
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--ocr", action="store_true",
                    help="run tesseract and pass the text alongside the image")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--retry-failed", action="store_true",
                    help="re-run only the frames in failed_frames.json and merge them "
                         "into the existing frame_content.json")
    args = ap.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Set ANTHROPIC_API_KEY first.")

    out = Path(args.manifest).parent / "frame_content.json"
    fail_path = out.parent / "failed_frames.json"
    kept = []  # results already saved by an earlier run (--retry-failed only)

    if args.retry_failed:
        if not fail_path.exists() or not out.exists():
            sys.exit(f"--retry-failed needs both {fail_path.name} and {out.name} from an earlier run.")
        frames = [{k: v for k, v in f.items() if k != "error"}
                  for f in json.loads(fail_path.read_text())["frames"]]
        kept = json.loads(out.read_text())["frames"]
        print(f"Retrying {len(frames)} failed frames with {args.model}...")
    else:
        frames = json.loads(Path(args.manifest).read_text())["frames"]
        print(f"Extracting content from {len(frames)} frames with {args.model}...")

    failed = []

    def work(frame):
        img_b64 = base64.b64encode(Path(frame["path"]).read_bytes()).decode()
        hint = ocr_text(frame["path"]) if args.ocr else ""
        try:
            content = call_api(api_key, args.model, img_b64, hhmmss(frame["timestamp"]), hint)
        except urllib.error.HTTPError as e:
            reason = f"API error {e.code}: {e.read().decode()[:300]}"
        except Exception as e:
            reason = str(e)
        else:
            if content.upper().startswith("NONE"):
                print(f"  frame {frame['index']:>3}  {hhmmss(frame['timestamp'])}  (skipped)")
                return None
            print(f"  frame {frame['index']:>3}  {hhmmss(frame['timestamp'])}  kept")
            return {**frame, "content": content}

        print(f"  frame {frame['index']:>3}  FAILED: {reason}")
        failed.append({**frame, "error": reason})
        return None

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = [r for r in pool.map(work, frames) if r]

    new_idx = {r["index"] for r in results}
    results = [r for r in kept if r["index"] not in new_idx] + results
    results.sort(key=lambda r: r["timestamp"])
    out.write_text(json.dumps({"model": args.model, "frames": results}, indent=2))
    print(f"\n{len(results)} frames had extractable content -> {out}")

    if failed:
        failed.sort(key=lambda r: r["timestamp"])
        fail_path.write_text(json.dumps({"frames": failed}, indent=2))
        print(f"WARNING: {len(failed)} frames FAILED and are missing from the notes -> {fail_path}\n"
              f"Run again with --retry-failed (and a lower --workers if you hit rate limits) "
              f"before building the notes.")
        sys.exit(1)
    fail_path.unlink(missing_ok=True)  # this script's own output; nothing left to retry


if __name__ == "__main__":
    main()
