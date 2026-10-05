# FrameProof

Turn a screen recording into a markdown document that keeps **both** what was said
and what was on screen — slides, charts, tables, code and terminal output.

Off-the-shelf converters (MarkItDown, Whisper on its own) drop the video track. For a
slide talk or a chart-heavy demo, that loses most of the content. FrameProof runs the
audio and the visuals through separate pipelines and merges them on one timeline.

```
recording.mp4
  ├─ audio ─> whisper ───────────> transcript.vtt   (timestamped)
  └─ video ─> sample + dedupe ───> frames/          (distinct screens only)
                 └─> vision model ─> markdown per frame
                                         │
                              merge on timestamp ─> notes-raw.md ─> notes.md
```

## Contents

| Path | What it is |
|---|---|
| [`skills/video-to-markdown/`](skills/video-to-markdown/) | Claude Code skill: [`SKILL.md`](skills/video-to-markdown/SKILL.md) plus three scripts |
| [`docs/frameproof.html`](docs/frameproof.html) | Write-up of the approach |
| [`docs/TOOLING-COMPARISON.md`](docs/TOOLING-COMPARISON.md) | Why not markitdown or docling |

## Quick start

Requires `ffmpeg`, Python 3, and an Anthropic API key. `tesseract` is optional (improves small text).

```bash
pip install pillow openai-whisper
export ANTHROPIC_API_KEY=sk-ant-...

cd skills/video-to-markdown
whisper recording.mp4 --model medium --output_format vtt --output_dir work/
python scripts/extract_frames.py  recording.mp4 --out work/ --interval 5
python scripts/describe_frames.py work/frames.json --ocr
python scripts/build_notes.py     work/frame_content.json work/recording.vtt --out notes-raw.md
```

`notes-raw.md` is the full interleaved record. [`SKILL.md`](skills/video-to-markdown/SKILL.md)
covers the synthesis pass to `notes.md`, tuning the dedupe threshold for screen recordings,
and a preflight check for blocked model-weight hosts.

## Using it as a Claude Code skill

Copy `skills/video-to-markdown/` into `~/.claude/skills/` (or a project's `.claude/skills/`).
Claude will pick it up when asked to turn a recording into notes.

## Licence

[MIT](LICENSE)
