# FrameProof

Context for Claude Code working in this repo. Budget: **this file ≤ 10 KB**; nothing auto-loaded may grow per session.

## What this repo is

**Public** open-source Claude Code skill (`skills/video-to-markdown/`, MIT) that turns a screen recording into
markdown keeping both speech and on-screen content. Scope is the tool only: its scripts, `SKILL.md`, README and
the tooling comparison.

⛔ Out of scope here, because anything committed is downloadable by anyone: write-ups, drafts, channel plans,
handover notes, account details, n8n workflows. Those live in a separate private repo. The verification stack
(V0-V6) is private too and is never copied in.

## Session rules

1. **Say the model out loud.** Open and close every session naming the model as `<picker name> · effort <level>`,
   with a one-clause reason.
2. **Ground truth from disk.** Before saying what is done or next, run `git status` and `git log -5`.
3. **Check before committing.** Every commit is public. No emails, tokens, API keys, personal paths or
   lecture/trading content from private recordings.
4. **Never create `.claude/rules/`.** It is auto-loaded into every session and subagent on every call.
5. **Subagents:** at most 3 at once; they write results incrementally, not at the end.

## Shell habits (user, 2026-09-25)

No `cd … &&` prefixes (change directory once, on its own); relative paths, not `C:/…`; one command per call;
never `python -c` or `python -`; use the Write tool for long Markdown, never a heredoc.
On Windows write files as explicit UTF-8.
