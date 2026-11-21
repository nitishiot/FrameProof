# Tooling comparison — why this skill has its own pipeline

Decision record, 2026-08-31: are off-the-shelf converters
([markitdown](https://github.com/microsoft/markitdown),
[docling](https://github.com/docling-project/docling)) worth adopting instead of this skill?

**Short answer: no, not as a replacement — but there is one narrow place where an external
OCR engine could still earn its keep.**

> ⚠ **Confidence note.** The assessments of markitdown and docling below are written from
> general knowledge of what those projects do, **not** from reading their source — no code
> was downloaded. The *architectural* claim (both are document converters, neither is a
> screen-recording pipeline) is solid and is what the decision rests on. The
> *feature-level* details are the part to re-verify if you act on this. See
> "How to re-check this" at the end.

## What the problem here actually is

This matters more than any feature list, because it is the thing that rules the candidates
out. The deliverable is **one self-contained `.md` per recording that keeps both what is said
and what is on screen**, with no image links and no references back to the video.

The inputs are long screen recordings: slides, documents, charts and live applications. That
forces a pipeline shaped like this:

| Stage | What it has to do | Why it is not generic |
|---|---|---|
| Sample | take frames on a fixed time grid across the whole recording | the right rate depends on the content: fast page-flips need a denser re-sample |
| Mask | black out volatile regions (clocks, status strips, taskbar) **before** hashing | without it, dedupe keys on a clock that changes every second |
| Dedupe | drop near-duplicate frames with a perceptual hash | the threshold has to be tuned per recording: too tight drops the dialogs that matter, too loose keeps dozens of identical screens |
| Classify | which application is on screen, per frame | one recording can switch between several surfaces, and each needs different handling |
| Thin | keep the last frame of each contiguous run — the settled state | the speaker talks while drawing or typing; the in-between frames are noise |
| Extract | read on-screen content as **tables**, not prose descriptions | dialog fields, chart labels and values are data, not scenery |
| Merge | interleave with a timestamped transcript on one timeline | speech and screen frequently disagree, and both must survive |
| Verify | staged checks of the output | each check catches a different class of error |

**The load-bearing fact:** the visual stream carries figures that appear nowhere in the
audio. In an illustrative case, the speaker says *"I have set this a little wider"* and never
says a number, while the screen shows the value. (Invented example.) A transcript-only output
does not merely lose detail — it loses the substance.

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

| Stage | This skill | markitdown | docling |
|---|---|---|---|
| Video frame sampling | ✅ `extract_frames.py --interval` | ❌ | ❌ |
| Region masking before hashing | ⚠ not in the script; `SKILL.md` gives a snippet | ❌ | ❌ |
| Perceptual dedupe | ✅ dHash in `extract_frames.py`, `--threshold` | ❌ | ❌ |
| On-screen app classification | ❌ not in the public skill | ❌ | ❌ |
| Thinning to settled states | ❌ not in the public skill | ❌ | ❌ |
| Reading screens as tables | ✅ `describe_frames.py` (extraction prompt) | ⚠ images only, no structure | ✅ strong on documents |
| OCR | ⚠ tesseract text passed alongside the image, `describe_frames.py --ocr` | ⚠ | ✅ multiple backends |
| Audio transcription | ✅ local Whisper, timestamped VTT | ⚠ weaker | ⚠ |
| Timeline merge (speech × screen) | ✅ `build_notes.py` | ❌ | ❌ |
| Accuracy verification stack | ❌ not in the public skill | ❌ | ❌ |

## The one place an external tool could help

A neural OCR engine (EasyOCR, RapidOCR) may read small UI text that tesseract misses; untested.

## Decision

**Keep the skill.** It solves a problem neither candidate addresses, and it is already built
and measured.

## What would change this decision

A tool that **samples video frames, dedupes them, and extracts on-screen structure against a
timeline**. That is the missing capability. A better document converter is not it, however
good it is at documents.

A weaker signal that would also justify a re-look:

- A vision-language model pipeline that reads a *sequence* of screenshots with temporal
  context, rather than each frame independently — that would attack the thinning and merge
  stages, which are currently the most hand-tuned parts.

## How to re-check this

The feature-level claims above were not verified against source. Before acting on any of
them:

1. Read the candidate's README and its **input format list** — the question to answer is
   whether `.mp4` is an input at all, and if so whether it yields anything but a transcript.
2. Search the repo for frame sampling / perceptual hashing / scene detection. Absence of
   those is decisive: without them there is no visual pipeline, whatever else is present.
3. Only then look at OCR and table modules, which are the parts with a real use here.

Do not evaluate these tools by their output on a *document*. Evaluate them on a long,
chart-heavy screen recording, which is the actual input.

---

# Capability inventory — what the skill does

Each row gives the capability, how the skill implements it, and — the useful part when
shopping — **the vocabulary that will actually find comparable tools**. Searching for
"video to markdown" mostly returns document converters; these are the terms that do not.

## The skill — `video-to-markdown`

A Claude Code skill: `SKILL.md` plus three scripts, installed under `~/.claude/skills/` or a
project's `.claude/skills/`. It is a **generic** pipeline — it works on any screen recording
or talk.

| # | Capability | Here | Search vocabulary |
|---|---|---|---|
| G1 | **Packaged, model-invocable workflow** | a skill that triggers on intent ("turn this talk into notes", an `.mp4` drop) rather than requiring a CLI | `LLM skills`, `agent skills`, `tool manifest`, `MCP server` |
| G2 | Fixed-interval sampling **chosen over scene detection** | recorded rationale: scene detection misses slow slide builds and over-fires on cursor movement and webcam overlays | `scene detection limitations`, `slide build detection` |
| G3 | Perceptual dedupe with tunable masking | `extract_frames.py`; masking is not in the script, `SKILL.md` gives a snippet | `perceptual hashing`, `frame dedupe` |
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

1. **Score the Sample, Mask and Dedupe stages first** (stage table above). A tool with none
   of these is a document converter and cannot do this job, whatever its table extraction
   looks like. This is the fast reject, and it is where both markitdown and docling fall out.
2. **Then the Extract stage and OCR.** This is where docling-class tools are genuinely
   strong, and where a component could be *borrowed* rather than adopting the whole
   framework.
3. **Then G1 and G4.** A tool that produces frame *descriptions* rather than frame
   *extractions* is solving a different problem, and that difference does not show up in a
   feature list — it has to be tested on a real chart-heavy recording.
4. **Then G7 and G8.** Ask whether the tool flags estimated figures and declares skipped
   stages, or whether a partial or guessed result reads as a complete one.
5. **Ignore transcription.** Whisper is Whisper — nobody wins on that row and it is already
   solved.

**The single best search framing** is not "video to markdown" but *screen recording to
structured knowledge*. Try `screencast to documentation`, `lecture video to structured
notes`, `video understanding pipeline`, `GUI video analysis`, `video RAG`, and `long-form
video understanding`. Adding `agentic` or `VLM` to those finds the newer work.

**A caveat on the search vocabulary itself:** these are the right technical terms for the
concepts, but they are not a promise that a matching project exists under each one. Treat
them as query seeds, not as a reading list.
