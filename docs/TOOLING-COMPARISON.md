# Tooling comparison — why this folder has its own pipeline

Decision record, written 2026-08-31. The user asked whether the off-the-shelf
video/document → markdown projects on GitHub are worth adopting instead of the pipeline in
this folder, naming [markitdown](https://github.com/microsoft/markitdown) and
[docling](https://github.com/docling-project/docling).

**Short answer: no, not as a replacement — but there is one narrow place where an external
OCR engine could still earn its keep, and it is worth testing before Days 12–19.**

> **Status, 2026-10-05.** The decision stands. The "before Days 12–19" window has passed: all
> 19 recordings were delivered on the in-house pipeline, and the external-OCR test below was not
> run. The in-house tesseract census has since re-read 8,492 grid cells across 8 recordings, so the
> test remains optional, not pending. Everything below is the record as written on 2026-08-31.

> ⚠ **Confidence note.** The assessments of markitdown and docling below are written from
> general knowledge of what those projects do, **not** from reading their source — no code
> was downloaded. The *architectural* claim (both are document converters, neither is a
> screen-recording pipeline) is solid and is what the decision rests on. The
> *feature-level* details are the part to re-verify if you act on this. See
> "How to re-check this" at the end.

## What the problem here actually is

This matters more than any feature list, because it is the thing that rules the candidates
out. The deliverable is **one self-contained `.md` per lecture that captures both what the
instructor says and what was on his screen**, with no image links and no references back to
the video.

The recordings are 2–3 hour screen shares of a live trading terminal. That forces a
pipeline shaped like this:

| Stage | What it has to do | Why it is not generic |
|---|---|---|
| Sample | 5 s grid over ~150 min → ~1,700 frames | rate is tuned to content: PDF page-flips needed a 1 s re-sample |
| Mask | black out the title-bar clock, ticker strip, taskbar **before** hashing | without it, dedupe keys on a clock that changes every second |
| Dedupe | masked 256-bit dHash, threshold 12 → 1,698 frames to **606** | the threshold curve is flat here; the screen genuinely changes every ~14 s |
| Classify | which application is on screen, per frame | the sample lecture has **four** surfaces: charts, a PDF viewer, a drawing app, a windowed data panel |
| Thin | keep the last frame of each contiguous run — the settled state | the instructor narrates while drawing; mid-drawing frames are noise |
| Extract | read overlays as **tables**, not prose descriptions | entry/stop/target prices, dialog fields, replicated level names |
| Merge | interleave with a timestamped transcript on one timeline | speech and screen frequently disagree, and both must survive |
| Verify | V0–V6: arithmetic, geometry, OCR census, blind re-read | staged checks, each catching a different class of error |

**The load-bearing fact:** the visual stream carries figures that appear nowhere in the
audio. In an illustrative case, the instructor says *"I have set this limit a little bit wide"* and
never speaks a number, while the screen shows a base value of 120.40 and the limit walked
117.10 → 117.30 → 117.50 (invented figures, not from any real lecture). A transcript-only
output does not merely lose detail — it loses the lesson. This was established empirically.

## The candidates

### markitdown (Microsoft)

Converts file formats to Markdown for LLM consumption — PDF, Office documents, HTML,
CSV/JSON/XML, images, audio. Its audio path is speech-to-text.

**Verdict: does not address this problem.** Given an `.mp4` screen recording it produces, at
best, a transcript. That is the exact output this project already established is
insufficient. It also has no frame sampling, no dedupe, no surface classification, and no
timeline merge — six of the eight stages above are simply absent.

It is a good tool for what it is for. This is not that.

### docling (IBM Research)

Substantially deeper *document* understanding: PDF layout analysis, genuine table-structure
recognition, several pluggable OCR backends, formula and code recognition. Also has an
audio/ASR path.

**Verdict: does not replace the pipeline, but is the more interesting of the two.** It is
still document-first — it has no concept of a video timeline, a frame budget, or a screen
whose meaning depends on when it appeared. But its OCR and table components are real
engineering and are the one part with a plausible use here (below).

### What neither does

Sampling a video, deduping frames, classifying what application is on screen, and merging
the result against a timestamped transcript. As of this writing no off-the-shelf tool was
identified that does this. That is why the pipeline exists.

## Capability matrix

Rows are the eight stages above. ✅ = does it, ⚠ = partial/adjacent, ❌ = absent.

| Stage | This pipeline | markitdown | docling |
|---|---|---|---|
| Video frame sampling | ✅ `extract_frames_masked.py` | ❌ | ❌ |
| Region masking before hashing | ✅ `--profile grid\|chart\|auto` | ❌ | ❌ |
| Perceptual dedupe | ✅ masked dHash, tuned | ❌ | ❌ |
| On-screen app classification | ✅ `split_apps.py`, measured discriminators | ❌ | ❌ |
| Thinning to settled states | ✅ run-based, `s2_thin.json` | ❌ | ❌ |
| Reading screens as tables | ✅ (model read, V2/V3/V4-verified) | ⚠ images only, no structure | ✅ strong on documents |
| OCR | ✅ tesseract census, tuned for 11 px UI text | ⚠ | ✅ multiple backends |
| Audio transcription | ✅ Whisper `large-v3` on Colab | ⚠ weaker | ⚠ |
| Timeline merge (speech × screen) | ✅ | ❌ | ❌ |
| Accuracy verification stack | ✅ V0–V6, mostly model-free | ❌ | ❌ |

The last row is worth calling out. Neither candidate ships anything like V0–V6 — the
arithmetic gate, the geometric back-projection census, the OCR census, the blind re-read.
Adopting an external converter would mean giving up the accuracy statement this project is
three layers into building.

## The one place an external tool could genuinely help

**V3's unresolved cells.** The OCR census finished at 93.2 % cell agreement using tesseract
5.4.0, and left **127 grid cells that no tesseract setting could read** — concentrated in the
`Open` column, which renders white text on saturated red, and in long quantities. Those
cells are currently unverified in either direction and are reported as such in the V3 report.

Neural OCR (EasyOCR, RapidOCR — both drivable by docling) fails *differently* from
tesseract's LSTM on 11 px UI text. It might read some of that residue.

This is a bounded, cheap experiment:

- `onnxruntime` 1.24.2 is **already installed** on this machine, so
  `pip install rapidocr-onnxruntime` needs no admin and no source download. Docling itself
  is not required to test the idea.
- The V3 harness is already factored for it: **`hard_read()` in
  the V3 adjudication script is the only function that would change.** The cropping,
  masking, upscaling, voting and diffing all stay.
- Success criterion: does it cut the 127-cell residue materially? If it reads fewer than a
  few dozen of them, it is not worth the dependency.

**Do not do this now.** Do it before Days 12–19, where the marginal cost compounds over
eight more videos.

## Decision

1. **Keep the pipeline.** It solves a problem neither candidate addresses, it is already
   built and measured, and it carries a verification stack that has found real errors
   (three in V3 alone, one in V2).
2. **Do not re-architect mid-verification.** The sample lecture is delivered with V0–V3 passing; V4–V6
   are open. Swapping toolchains now would invalidate the accuracy statement in progress.
3. **Revisit before the remaining lectures**, and when you do, ask the narrow question — *"does a
   different OCR engine cut the unresolved-cell count?"* — not the broad one.

## What would change this decision

A tool that **samples video frames, dedupes them, and extracts on-screen structure against a
timeline**. That is the missing capability. A better document converter is not it, however
good it is at documents.

Two weaker signals that would also justify a re-look:

- A vision-language model pipeline that reads a *sequence* of screenshots with temporal
  context, rather than each frame independently — that would attack the thinning and merge
  stages, which are currently the most hand-tuned parts.
- Anything that removes the Colab round-trip for transcription without sacrificing
  `large-v3` quality. The current constraint is hardware (i7-1355U, no CUDA), not software.

## How to re-check this

The feature-level claims above were not verified against source. Before acting on any of
them:

1. Read the candidate's README and its **input format list** — the question to answer is
   whether `.mp4` is an input at all, and if so whether it yields anything but a transcript.
2. Search the repo for frame sampling / perceptual hashing / scene detection. Absence of
   those is decisive: without them there is no visual pipeline, whatever else is present.
3. Only then look at OCR and table modules, which are the parts with a real use here.

Do not evaluate these tools by their output on a *document*. Evaluate them on a two-hour
screen recording of a trading terminal, which is the actual input.

---

# Capability inventory — what this pipeline actually does

Added 2026-08-31, so the project can be benchmarked against candidates without re-reading
the code. There are **two separable products** here:

- **the corpus pipeline in this folder** — ~2,540 lines of Python across 24 scripts, numpy +
  PIL only, no OpenCV and no torch dependency (sections A–F);
- **the `video-to-markdown` skill** — 735 lines, account-level and reusable on any recording
  (section G).

Score a candidate against the skill for general capability, and against A–F only if the job
is a corpus like this one.

Each row gives the capability, how it is implemented here, and — the useful part when
shopping — **the vocabulary that will actually find comparable tools**. Searching for
"video to markdown" mostly returns document converters; these are the terms that do not.

## A. Video to frame corpus

| # | Capability | Here | Search vocabulary |
|---|---|---|---|
| A1 | Fixed-rate frame sampling from long video | 5 s grid, ~1,700 frames per 2.5 h | `keyframe extraction`, `ffmpeg fps filter`, `video frame sampling` |
| A2 | **Adaptive re-sampling of dense regions** | non-TradeTiger windows re-sampled at 1 s, because PDF pages flip in ~40 s | `adaptive sampling`, `content-aware frame selection` |
| A3 | **Region masking before hashing** | blacks out the title-bar clock, index ticker and OS taskbar so dedupe cannot key on them | `region of interest masking`, `ROI exclusion`, `screencast diffing` |
| A4 | Perceptual dedupe | masked 256-bit dHash, tuned threshold (12) | `perceptual hashing`, `dHash` / `pHash`, `imagehash`, `near-duplicate frame detection` |
| A5 | **Profile switching per recording** | `--profile grid｜chart｜auto`; the mask that is right for a windowed grid hides the chart title on a maximised chart | `layout-aware preprocessing` |
| A6 | Scene / shot change detection | `scenes.py` | `PySceneDetect`, `shot boundary detection` |

## B. Understanding what is on screen

| # | Capability | Here | Search vocabulary |
|---|---|---|---|
| B1 | **On-screen application classification** | measured pixel discriminators separate PDF viewer / chart / drawing app / grid at 1920x1080 | `GUI screenshot classification`, `screen understanding`, `UI element detection` |
| B2 | **Temporal thinning to settled states** | keep the last frame of each contiguous run — the finished drawing, not the drawing in progress | `temporal redundancy removal`, `stable frame selection` |
| B3 | Grid geometry detection from pixels | column separators from the header band, row phase from the blank separators, re-derived per frame | `table detection`, `line detection`, `document layout analysis` |
| B4 | OCR tuned for small UI text | background-relative masking (white-on-green *and* black-on-grey), grayscale upscaling, multi-setting vote | `OCR small text`, `screenshot OCR`, `UI text recognition`, `tesseract psm` |
| B5 | Structured extraction as **tables, not prose** | every dialog, watchlist and level set kept as a table | `document AI`, `table structure recognition`, `TableFormer`, `PubTabNet` |
| B6 | Chart overlay reading | entry / stop / target, horizontal level names and values read off candlestick charts | `chart understanding`, `ChartQA`, `plot-to-table`, `chart derendering` |

## C. Audio

| # | Capability | Here | Search vocabulary |
|---|---|---|---|
| C1 | Batch audio extraction, resumable | 16 kHz mono 32 kbps MP3, ~400 MB to ~32 MB per video | `ffmpeg audio extraction` |
| C2 | Timestamped ASR | Whisper `large-v3` on a Colab T4, ~10–15 min per video | `Whisper`, `faster-whisper`, `WhisperX`, `ASR with timestamps`, `VTT` |
| C3 | **Speech translation, not transcription** | Hindi speech to English text in one pass (`TASK='translate'`) | `speech translation`, `S2TT`, `SeamlessM4T` |
| C4 | Crash-safe resume | keys on the `.json` marker rather than the `.vtt`, and flushes every segment | `resumable batch transcription` |

## D. The merge — where speech and screen meet

| # | Capability | Here | Search vocabulary |
|---|---|---|---|
| D1 | **Timeline interleave of transcript and visuals** | one timeline, timestamps as inline anchors | `multimodal alignment`, `temporal grounding`, `video-text alignment` |
| D2 | Transcript condensation | 170 KB of 2-second cues to 92 KB of per-minute prose, so a 2 h lecture fits one context window | `transcript segmentation`, `VAD re-chunking` |
| D3 | **Conflict preservation** | where speech and screen disagree on a number, both are kept and the authoritative one is named | *rare — see note below* |
| D4 | Shared-document deduplication | the 62-page course PDF extracted **once**, cited by page number from every day file | `cross-document coreference`, `deduplication` |

## E. The verification stack — the part nothing off-the-shelf has

This is the differentiator. Most tools stop at D. Searching here is the fastest way to find
out whether a candidate is serious.

| # | Layer | Mechanism | Search vocabulary |
|---|---|---|---|
| E1 | V0 merge integrity | every figure traceable to a source; every quote word-contained in a transcript window; every trade row satisfies RR = reward/risk | `groundedness`, `faithfulness metric`, `attribution`, `citation verification`, `hallucination detection` |
| E2 | V1 timestamp attribution | every cited timestamp checked against what was actually on screen at that moment | `temporal grounding evaluation` |
| E3 | **V2 geometric back-projection** | fit claimed prices against the horizontal lines actually drawn in the pixels; a misread digit breaks the linear fit | *effectively unique — see note* |
| E4 | V3 OCR census | independent mechanical re-read of 1,109 grid cells, every disagreement adjudicated | `OCR post-correction`, `consensus OCR`, `ensemble OCR` |
| E5 | V4 blind model re-read | subagents with clean context, never shown the document, **gated on a calibration set** before their verdicts count | `LLM-as-judge calibration`, `blind evaluation`, `inter-annotator agreement` |
| E6 | V5 translation fidelity | the 82 quotes re-checked against a Devanagari `transcribe` run | `back-translation evaluation`, `COMET`, `round-trip translation` |
| E7 | Internal consistency identities | `Current = Close x (1 + %Chg)`, `Low <= Open, Current <= High` — 134 of 134 hold | `constraint checking`, `data validation`, `Great Expectations` |

**Two capabilities to weigh heavily, because they are the ones least likely to exist
elsewhere:**

- **D3, conflict preservation.** Almost every summarisation tool silently resolves a
  speech/screen disagreement by preferring one source. This one keeps both and says which is
  authoritative — the instructor said "down 6-7 %" while the terminal printed −11.58 %, and
  both are in the document.
- **E3, geometric back-projection.** Verifying a *number read off a chart* by checking it
  against the pixel position of the line it labels. It caught an injected digit transposition
  and independently re-derived a real error. If a candidate has anything resembling it, it is
  a serious tool.

## F. Operational

| # | Capability | Search vocabulary |
|---|---|---|
| F1 | Resumable at every stage, with completion markers | `checkpointing`, `idempotent pipeline` |
| F2 | Runs on a 15 W laptop with no GPU; only ASR is offloaded | `CPU inference`, `edge deployment` |
| F3 | Deterministic and scriptable — no interactive steps | `reproducible pipeline` |
| F4 | Self-documenting failure — skipped stages declared at the top of the output | `provenance`, `data lineage` |

## G. The reusable skill — `video-to-markdown`

**This is a separable product in its own right and should be counted as one.** It is an
account-level Claude Code skill, not part of this folder: **362 lines of `SKILL.md` plus 373
lines across three scripts (735 total)**, at
`~/.claude/skills/synced/<uuid>_<uuid>/video-to-markdown`.

The relationship to everything above matters when comparing against other products. The
skill is the **generic** pipeline — it works on any screen recording or talk. This folder
holds the **corpus-specific** tuning that the skill cannot know: the TradeTiger mask
profiles, the four-surface app discriminators, the thinning rule, and the whole V0–V6
verification stack. A candidate tool should be scored against the skill for general
capability, and against A–F above only if the job is this corpus.

| # | Capability | Here | Search vocabulary |
|---|---|---|---|
| G1 | **Packaged, model-invocable workflow** | a skill that triggers on intent ("turn this talk into notes", an `.mp4` drop) rather than requiring a CLI | `LLM skills`, `agent skills`, `tool manifest`, `MCP server` |
| G2 | Fixed-interval sampling **chosen over scene detection** | recorded rationale: scene detection misses slow slide builds and over-fires on cursor movement and webcam overlays | `scene detection limitations`, `slide build detection` |
| G3 | Perceptual dedupe with tunable masking | `extract_frames.py` (this folder's `extract_frames_masked.py` adds the masking the skill lacks) | `perceptual hashing`, `frame dedupe` |
| G4 | **Extraction prompting, not description prompting** | `describe_frames.py` asks for a bar chart as a *data table*, a slide as its *text*; frames with nothing to extract return `NONE` and are dropped | `visual question answering`, `image-to-table`, `structured extraction prompt` |
| G5 | Transcript × frame interleave | `build_notes.py`, with `--embed-images` so each table sits beside its source frame | `multimodal alignment` |
| G6 | **Environment preflight** | checks up front whether the machine can actually fetch model weights, and hands transcription back to the user when it cannot | `dependency preflight`, `graceful degradation` |
| G7 | **Estimation honesty as a rule** | figures read off unlabelled charts must be flagged as estimated, and the warning may never be dropped during synthesis; frames cited by estimated tables are kept for checking | `uncertainty communication`, `confidence calibration`, `provenance` |
| G8 | Partial-output protocol | a blocked or skipped stage is declared at the top of the document, so a partial result cannot read as a complete one | `graceful degradation`, `provenance` |

**G4 and G7 are the two worth weighing.** G4 is the difference between a document full of
data tables and one full of "a person is speaking next to a chart" — most captioning tools
do the latter. G7 is an explicit stance that a confidently wrong figure is worse than no
figure, enforced as a rule rather than left to judgement; the skill's own words are *"a
confidently wrong revenue figure in someone's notes is worse than no figure."*

**Independent corroboration of this document's verdict:** the skill's opening paragraph,
written before this comparison was asked for, states that *"off-the-shelf converters
(MarkItDown, Whisper alone) discard the video track entirely."* That conclusion was reached
while building the skill and reached again here from the candidates' architecture — two
separate routes to the same place.

### When comparing against other products

Score a candidate on G1 and G4 specifically. A tool that produces frame *descriptions*
rather than frame *extractions* is solving a different problem, however good its captions
are — and that difference is invisible in a feature list, so it has to be tested on a real
chart-heavy recording.

## How to use this list when evaluating a candidate

1. **Score A1–A6 and B1–B2 first.** A tool with none of these is a document converter and
   cannot do this job, whatever its table extraction looks like. This is the fast reject, and
   it is where both markitdown and docling fall out.
2. **Then B3–B6.** This is where docling-class tools are genuinely strong, and where a
   component could be *borrowed* rather than adopting the whole framework.
3. **Then E.** Anything scoring here deserves real attention; most projects score zero.
4. **Then G1 and G4.** A tool that produces frame *descriptions* rather than frame
   *extractions* is solving a different problem, and that difference does not show up in a
   feature list — it has to be tested on a real chart-heavy recording.
5. **Ignore C.** Whisper is Whisper — nobody wins on that row and it is already solved.

**The single best search framing** is not "video to markdown" but *screen recording to
structured knowledge*. Try `screencast to documentation`, `lecture video to structured
notes`, `video understanding pipeline`, `GUI video analysis`, `video RAG`, and `long-form
video understanding`. Adding `agentic` or `VLM` to those finds the newer work.

**A caveat on the search vocabulary itself:** these are the right technical terms for the
concepts, but they are not a promise that a matching project exists under each one. Treat
them as query seeds, not as a reading list.
