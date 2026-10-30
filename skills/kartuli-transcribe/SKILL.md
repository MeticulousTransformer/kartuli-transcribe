---
name: kartuli-transcribe
description: Transcribe Georgian or English source media and find speech with source timestamps using the kartuli-transcribe CLI. Use to understand spoken content before editing a timeline.
---

Check `command -v kartuli-transcribe`, then run `kartuli-transcribe doctor`.
If missing, install from https://github.com/MeticulousTransformer/kartuli-transcribe
using `uv tool install git+https://github.com/MeticulousTransformer/kartuli-transcribe.git`.
All operational output is JSON; check `ok`, exit status, and `doctor.ready`.

Use ELEVENLABS_API_KEY from the environment, or pass an explicitly identified
`--env-file` to doctor/transcribe. Never display keys. Offline read/search need
neither auth nor network.

Transcribe the source media once to a task-owned output file. Repeating identical
settings with the same output reuses it. Transcribing a range still returns source
seconds. Use bounded search/read to retrieve only relevant speech; follow
`next_offset` when needed. `read --words` exposes individual word boundaries.

```sh
kartuli-transcribe transcribe "/media/interview.mp4" --out interview.transcript.json
kartuli-transcribe search interview.transcript.json "როგორ ხარ" --limit 5
kartuli-transcribe read interview.transcript.json --start 600 --end 630 --words
```

Use `--start`/`--end` on transcribe to limit an upload, and `--language en` for
English. Search is a literal substring match with case/whitespace normalization;
try shorter words or read nearby segments if phrasing differs. No match does not
prove speech is absent. Read the saved JSON directly for full data.

Map source seconds through the editor's clip source-in and sequence start.
Account separately for retiming or nesting. Anonymous speaker IDs are local to
each request, and ASR timings are estimates to review before a precise cut.

Transcribe uploads extracted audio to ElevenLabs and may cost money. Work within
the user's transcription request; reuse existing output. Do not use --force to
repeat paid work or overwrite a transcript unless that replacement is intended.
Do not retry uploads automatically. This CLI does not change the timeline;
perform edits through the editor only within the user's editing request.
