---
name: video-to-markdown
description: "Convert a local video recording into a structured markdown document that captures BOTH the spoken audio AND the on-screen visuals — slides, charts, graphs, diagrams, code, and terminal output. Use this skill whenever the user wants notes, a summary, a transcript, or a document out of a video or screen recording, or mentions converting a video/recording/webinar/lecture/demo/meeting recording to markdown or text. Use it especially when the user says the visuals, charts, slides, or \"what's on screen\" matter, or when a plain transcript would lose the point of the recording. Also trigger on \"video to md\", \"transcribe this recording\", \"turn this talk into notes\", \"extract the slides from this video\", or when a user uploads or points at an .mp4/.mov/.mkv/.webm file and wants its content in writing. Prefer this over a plain transcription tool for any recording that shows things on screen."
---

# Video to Markdown

Off-the-shelf converters (MarkItDown, Whisper alone) discard the video track
entirely. For a talk with slides or a chart-heavy demo, that throws away most
of the meaning. This skill runs the audio and the visuals through separate
pipelines and merges them on a shared timeline.

## Pipeline

```
recording.mp4
  ├─ audio ──> whisper ─────────────> transcript.vtt  (timestamped)
  └─ video ──> sample + dedupe ─────> frames/         (distinct screens only)
                    └─> vision model ─> extracted markdown per frame
                                             │
                              merge on timestamp
                                             ↓
                                    notes-raw.md
                                             ↓
                                synthesis pass → notes.md
```

## Before starting

Confirm the input and the goal, because they change the settings:

1. **What kind of recording?** Three cases behave very differently:
   - *Talking head / interview* — almost no visual work; consider skipping
     Steps 2–3 entirely.
   - *Slide deck or chart-heavy demo* — the case this skill is built for.
   - *Screen recording of an application* (IDE, trading terminal, dashboard,
     CAD tool) — the visuals matter, but the default dedupe misbehaves. Read
     "Screen recordings" under Step 2 before running it.
2. **What should the output be?** A faithful record of everything said and
   shown, or a condensed set of notes? This decides how aggressive the final
   synthesis pass should be.
3. **Is the video long?** Over ~90 minutes, warn the user about cost and time
   before starting, and consider a larger `--interval`. Offer to run a short
   slice first (`ffmpeg -ss 0 -t 600`) so settings can be tuned before
   committing to the whole file.

## Setup

```bash
# ffmpeg is required; tesseract is optional but improves small-text fidelity
brew install ffmpeg tesseract        # macOS
sudo apt install ffmpeg tesseract-ocr  # Debian/Ubuntu

pip install pillow openai-whisper
export ANTHROPIC_API_KEY=sk-ant-...
```

If ffmpeg is missing, stop and tell the user — nothing downstream works
without it.

### Preflight: can this environment actually get the model weights?

`pip install` succeeding does **not** mean transcription will work. Whisper
packages ship no weights; they download them on first use, and sandboxed or
corporate-allowlisted environments routinely permit PyPI while blocking the
model hosts. The failure then appears minutes later as an opaque
`httpx.ProxyError: 403 Forbidden`.

Check before extracting anything:

```bash
for host in https://huggingface.co https://openaipublic.azureedge.net; do
    printf '%s -> ' "$host"
    curl -sS -o /dev/null -w '%{http_code}\n' --max-time 12 "$host" || echo unreachable
done
```

`huggingface.co` serves `faster-whisper` weights; `openaipublic.azureedge.net`
serves `openai-whisper` weights. A `000` means the host is blocked.

If both are blocked, say so immediately and offer the real options rather than
burning time on workarounds:

- **Run transcription on the user's own machine** — see the next section. This
  is the best-quality path and normally the right recommendation.
- **Ask for the host to be allowlisted**, if the user controls that.
- **Run the visual pipeline alone** and label the output clearly as
  incomplete (see "Partial output" below).

Do **not** substitute a bundled-weights engine such as `pocketsphinx` and pass
the result off as a transcript. It installs without any download, which makes
it tempting, but its accuracy on accented speech or domain jargon is far too
low to build a document on — a measured sample came back as *"do you call
option than the other / as with is is it the next august it is actually"*. It
is useful only for confirming which language is being spoken.

### Handing transcription back to the user

When the sandbox cannot fetch weights but the user's own machine can, give
them a script rather than a command to improvise around. Write it into the
folder that holds their videos, alongside a double-clickable launcher on
Windows (`.bat` with CRLF line endings, ending in `pause` so the window stays
open). The script should walk the folder and emit `<video name>.vtt` beside
each file.

Four things that decide whether the handoff succeeds:

**Resume on a completion marker, not on the output file.** The `.vtt` is
created the moment work starts, so `if os.path.exists(base + ".vtt"): skip`
will permanently skip any video whose run was interrupted — and the user's
first run is very often interrupted. Write a second file (`.json`) only after
the last segment, and skip on that.

**Flush after every segment and report progress often.** `model.transcribe()`
returns a generator, and the scan before the first segment takes one to three
minutes on a long video. Python's default 8 KB buffering then holds the first
~130 segments in memory. The combined effect is ten minutes of a blank
terminal and a 0-byte output file, which every user reads as a crash. Call
`fh.flush()` each iteration, print a percentage every ~10 segments with an
ETA, and print an explicit "scanning audio, no output for 1-3 min" line before
the loop.

**Warn them about the benign noise up front.** A first run on Windows prints
several alarming-looking warnings that are all harmless: `ct2-*-converter.exe`
and `pyav.exe` "not on PATH", a `huggingface_hub` symlink warning about
Windows Developer Mode, an unauthenticated-HF-Hub / `HF_TOKEN` rate-limit
notice, and a pip upgrade notice. Say in advance that these are expected, and
name the one line that actually indicates progress. Otherwise the first
screenshot you get back is of warnings, not of a failure.

**Skip the ffmpeg install.** `faster-whisper` decodes video directly through
bundled PyAV, so the user does not need ffmpeg on their machine even though
this skill's own Setup section installs it.

Give a realistic time estimate with the model named: `small` on CPU runs a
2-hour video in roughly 20–40 minutes; `medium` is markedly better on accented
speech and markedly slower; an NVIDIA GPU (`device="cuda"`, `float16`) cuts it
to a few minutes.

Then resume at Step 4 with the transcript they produce.

## Step 1 — Transcribe

```bash
whisper recording.mp4 --model medium --output_format vtt --output_dir work/
```

Timestamps are the whole point of the VTT format here; do not use
`--output_format txt`, since the merge step needs them to place visuals.

Model choice: `small` is fine for clear single-speaker audio, `medium` is the
sensible default, `large-v3` for heavy accents, jargon, or cross-talk. On
Apple Silicon, `faster-whisper` or `whisper.cpp` runs several times quicker
with equivalent output.

If the recording has no meaningful audio, skip this step — the rest of the
pipeline works without a transcript.

## Step 2 — Extract distinct frames

```bash
python scripts/extract_frames.py recording.mp4 --out work/ --interval 5
```

This samples one frame every 5 seconds and drops near-duplicates using a
perceptual hash, so a slide held for four minutes yields one frame rather than
48. A typical 40-minute talk collapses to 20–40 distinct frames.

Tune when the output looks wrong:

| Symptom | Fix |
|---|---|
| Hundreds of frames kept | Webcam overlay or animation is firing the hash. Raise `--threshold` to 10–12 |
| A slide you know exists is missing | Lower `--interval` to 2–3 |
| Long recording, cost is a concern | Raise `--interval` to 10–15 |
| Many frames kept but the content is unchanged | A clock, cursor or ticker is firing the hash. Mask it — see below |

### Screen recordings

A perceptual hash over the whole frame assumes the whole frame carries
meaning. That holds for slides. It fails for a recording of a running
application, where a title-bar clock advances every second, a row highlights
under the moving cursor, and a ticker strip updates — all while the content
the user cares about is unchanged. No single threshold separates these:
tightening it drops the dialog boxes that matter, loosening it keeps dozens of
identical screens.

Mask the volatile regions before hashing rather than fighting the threshold:

```python
from PIL import Image

# Fractions of frame width/height. Tune by eye on two or three sample frames.
MASK = [
    (0.00, 0.00, 1.00, 0.02),   # title bar / window clock
    (0.00, 0.96, 1.00, 1.00),   # OS taskbar and its clock
    (0.20, 0.00, 1.00, 0.02),   # market / status ticker strip
]

def masked(path):
    img = Image.open(path).convert("L")
    w, h = img.size
    for x0, y0, x1, y1 in MASK:
        box = (int(x0 * w), int(y0 * h), int(x1 * w), int(y1 * h))
        img.paste(0, box)
    return img
```

Hash `masked(path)` instead of the raw image. Mouse-cursor movement is harder
to mask because it roams; if it still dominates, compare frames on a
downscaled 32×32 grayscale image, where a few cursor pixels cannot shift the
hash.

After tuning, **look at the kept frames before running Step 3** and count how
many are genuinely distinct. On one 10-minute terminal recording, threshold 40
kept 2 frames and missed both dialog boxes that mattered, threshold 8 kept 44,
and threshold 12 kept 21 of which only 4 were distinct screens. Retune here
rather than paying for a vision pass over near-duplicates.

## Step 3 — Extract content from the frames

```bash
python scripts/describe_frames.py work/frames.json --model claude-sonnet-5 --ocr
```

The prompt asks for *extraction*, not description: charts come back as data
tables, slides as markdown text, code as fenced blocks. Anything else — a
speaker's face, a title card, a decorative screen — returns `NONE` and is
dropped. That escape hatch is what keeps the final document from filling up
with "a man is standing at a podium."

`--ocr` runs tesseract and passes the text alongside the image. It measurably
helps on dense slides and small type, and costs nothing but time.

**Model choice.** Use Sonnet for this step. It runs once per frame, so it is
where nearly all the cost sits, and it handles slide and code extraction
essentially as well as the larger models. Reach for Opus or Fable only when
the recording is dominated by hard-to-read charts and the first pass came back
visibly wrong. Do the reverse for Step 4, which runs once.

For application recordings, also capture the surrounding chrome once — menu
bar, ribbon groups, status and message panes. It reads as boilerplate on any
single frame, but as a one-off reference section it maps what the recording is
navigating, and it is the part a viewer cannot reconstruct from the transcript.

## Step 4 — Merge and synthesise

```bash
python scripts/build_notes.py work/frame_content.json work/recording.vtt \
    --out work/notes-raw.md --embed-images
```

This interleaves the two streams by timestamp. What the speaker says while a
chart is on screen is usually the interpretation of that chart, so keeping
them adjacent carries most of the value.

`notes-raw.md` is a faithful merge, not a finished document. Read it and write
the final `notes.md` yourself. This synthesis pass is the one step that
benefits from the strongest available model, since it runs once over the whole
document:

- Give it a title and a short summary of what the recording covers.
- Group the content under topic headings that reflect the actual structure,
  not the clock. Keep timestamps as inline anchors so the user can jump back.
- Turn rambling speech into readable prose. Verbatim transcript is rarely what
  someone wants from "convert this to markdown."
- **Keep every extracted table and code block intact.** These are the reason
  the skill exists. Never paraphrase a data table into a sentence.
- Preserve any `> Values estimated from the chart; verify.` markers verbatim.
- Pull out decisions, action items, and figures into their own section if the
  recording is a meeting or a planning session.

### Partial output

If a stage was skipped or blocked, the document must say so at the top, in a
callout, before any content — not in a footnote. State which stream is
missing, why, and what the reader is therefore not getting. A visual-only
document from a lecture looks superficially complete while omitting the entire
point of the recording, and a reader who does not know that will trust it.

If the run covered only part of the video, put the range in the **filename**,
not just the header — `Lecture 3 [00-00 to 10-00].md`. It is the only cue the
user sees in their file manager, and it makes clear the file is a draft to be
superseded rather than a container that will later fill up.

Close the document with a short pipeline table showing what ran, what was
skipped, and how the dedupe was tuned. It is what makes a rerun cheap.

## Delivering the output

The finished `.md` is the deliverable, and it must stand alone: everything
extracted from the video written out as text and markdown tables, with
timestamps as anchors and no dependency on the frames, the transcript, or the
video. The user should be able to hand that one file to any model and get
useful answers.

Say this explicitly when handing it over, along with two things users
reasonably assume otherwise:

- **Nothing updates itself.** A user who has been asked to run transcription
  on their own machine will often expect the `.md` already in their folder to
  fill in when the transcript finishes. It will not — the merge is a step you
  perform when they tell you the transcript is ready. Say so before they wait
  on it.
- **Keep the `.vtt`, as archive rather than input.** It is small and costs
  hours of compute to regenerate. They never need to supply it alongside the
  `.md`.

Working files (sampled frames, extracted audio, logs) are not deliverables.
Put them in a clearly named scratch subfolder, tell the user it is safe to
delete, and — on a sandboxed filesystem where deletion is not permitted — say
where they were left rather than silently leaving them behind.

## Verifying the result

Chart extraction is genuinely unreliable when a chart has no printed data
labels — the model reads bar heights off pixels and will state wrong values
with complete confidence. Two habits handle this:

- Run `build_notes.py` with `--embed-images` so each extracted table sits next
  to the frame it came from, and tell the user to spot-check the ones that
  matter.
- Never silently drop the estimation warning from a table during synthesis.

Say plainly which numbers are read from labels and which are estimated. A
confidently wrong revenue figure in someone's notes is worse than no figure.

This also decides whether the frames are worth keeping. If every figure in the
document came from a printed label, the frames are disposable. If any came
from reading a chart by eye, keep the frames those tables cite so the user can
check them.

## Common situations

**Recording is mostly a talking head.** Skip Steps 2 and 3 entirely and
synthesise straight from the transcript. Say so rather than burning a vision
pass on 40 frames of the same face.

**Recording is a silent screen capture.** Skip Step 1 and pass no transcript
argument to `build_notes.py`.

**Recording is a live application walkthrough.** Apply the masking in Step 2,
then structure the output around application *states* — which window, dialog
or view is open — rather than around the clock. Long stretches where nothing
changes are worth one line, not one frame each. Warn the user early if the
visuals turn out to be near-static: the result is closer to "transcript with
screen annotations" than to the slide-deck case, and it is better to say so
than to let them expect otherwise.

**User wants the slides only.** Run Steps 2 and 3, then assemble
`frame_content.json` directly without the transcript merge.

**Video is very long.** Process in chunks with `ffmpeg -ss`/`-t`, run the
pipeline per chunk, and concatenate before the synthesis pass.

**A series or course.** Tune on one short slice, confirm the settings with the
user, then run the rest with those settings fixed. Produce one `.md` per
recording — a 2-hour lecture is roughly 20,000 words, which fits one context
window comfortably, while a 19-part course does not fit at all. Once the set
is complete, offer a master index: one file with a paragraph per recording,
its topics, and timestamp pointers. The user then supplies the index plus the
one or two files it points at, which is what makes cross-video questions
possible.