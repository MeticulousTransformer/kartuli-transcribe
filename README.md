# kartuli-transcribe

A small command-line version of [CapForge's transcription backend](https://github.com/MeticulousTransformer/Georgian-Kartuli-After-Effects-Transcribtion-Tool), for agents editing Georgian timelines.

Give it an audio/video file. Get Georgian text, individual word timestamps and
anonymous speaker labels in a saved JSON file. Agents can read a time range or
find a phrase without uploading the media again.

**v0.1:** Python 3.10+, FFmpeg, one HTTP dependency (`httpx`), ElevenLabs Scribe.
Georgian (`ka`) is the default; English (`en`) and automatic language detection
(`auto`) are also available. No After Effects installation or running server is
needed. This tool transcribes source media; it does not open or modify timelines.

## Install

With [uv](https://docs.astral.sh/uv/):

```sh
uv tool install git+https://github.com/MeticulousTransformer/kartuli-transcribe.git
kartuli-transcribe --help
```

Alternatively use `pipx install git+https://github.com/MeticulousTransformer/kartuli-transcribe.git`.
For a local checkout, use `uv tool install .` or `make install-local`.
If the command is missing, run `uv tool update-shell` and open a new terminal.
For an installed Git version, update with `uv tool upgrade kartuli-transcribe`.

Install FFmpeg separately (on macOS: `brew install ffmpeg`; on other platforms,
install [FFmpeg](https://ffmpeg.org/download.html) and put it on PATH).

Set `ELEVENLABS_API_KEY` in your environment, or pass an existing key file:

```sh
kartuli-transcribe doctor --env-file /absolute/path/to/backend/.env
```

The file may be your existing CapForge `backend/.env`. Only ELEVENLABS_API_KEY is
read; values in the environment take precedence. Key files are never loaded
automatically, modified, or included in output. The simple file reader accepts
`ELEVENLABS_API_KEY=value` with optional surrounding quotes; it does not evaluate
shell commands or expand variables. `--env-file` works before the command or after
`doctor` / `transcribe`. `doctor` checks local setup only; it does not validate the
key with ElevenLabs or make a paid request.

## Agent workflow

```sh
# 1. Check setup (always JSON).
kartuli-transcribe doctor

# 2. Transcribe a source file once. This uploads extracted audio to ElevenLabs.
kartuli-transcribe transcribe "/media/interview.mp4" --out interview.transcript.json

# Or transcribe only 10:00–12:00 in the source media.
kartuli-transcribe transcribe "/media/interview.mp4" \
  --start 10:00 --end 12:00 --out interview-range.transcript.json

# 3. Find a literal Georgian phrase, with nearby speech and source times.
kartuli-transcribe search interview.transcript.json "როგორ ხარ" --limit 5

# 4. Read a specific source interval, including individual words if needed.
kartuli-transcribe read interview.transcript.json --start 600 --end 630 --words
```

`transcribe` returns a small receipt containing the absolute output path, cache
status and word/segment counts. Full text and timings are in the saved file.
Speaker labels are enabled by default; use `--no-diarize` to disable them.
Use `--language en` or `--language auto` when appropriate. The default model is
`scribe_v2`; `--model scribe_v1` is an explicit alternative, with no silent model
fallbacks or automatic retries of paid requests.

### Source time versus timeline time

Every word and segment uses **seconds from the start of the source media**.
Transcribing `--start 600` adds 600 seconds to every returned provider timestamp.
`--start` / `--end` accept seconds, `MM:SS.sss` or `HH:MM:SS.sss`; they do not accept
frame timecode. The end argument is exclusive. Reads return whole segments that
overlap the range, so the first/last returned segment may extend beyond it.

For a normal-speed clip, an editing agent maps a word to the timeline with:

```text
timeline_seconds = clip_timeline_start + word_source_seconds - clip_source_in
```

Retimed, reversed, nested or otherwise transformed clips need the editor's actual
time mapping. Speaker IDs are predictions, not names, and are local to one request;
`speaker_0` in two separate ranges need not identify the same person. Review ASR
text and boundaries before making consequential edits.

### Fast repeated use

- FFmpeg extracts only the requested interval as 16 kHz mono PCM WAV, preserving
  delayed audio positions and timestamp gaps with silence.
- The upload streams from disk instead of buffering a long WAV in memory.
- A matching saved output is reused before extraction, authentication or upload.
- `read`, `search`, help and `doctor` do not import the HTTP client or contact a service.
- Reads default to 30 segments; search defaults to 20 matches. Both accept
  `--limit 1..1000` and `--offset`, and return `total` plus `next_offset`.

Reuse checks the source's absolute path, size, modification time and request
options. This is a fast file-identity check, not a content hash. Moving/changing a
source or changing request options requires a new `--out` path or `--force`.
`--force` replaces the output after a successful fresh request and can incur
another charge. Keep one writer per output file. Outputs are written atomically;
temporary extracted audio is removed on normal completion or interruption.

`search` uses literal substring matching with Unicode normalization, case folding
and collapsed whitespace. Punctuation still matters. It searches across segment
and speaker boundaries and returns the entire matching words, with three seconds
of nearby speech by default (`--context 0..30`). It does not interpret paraphrases
or translate queries. An empty result means that text was not found in this
transcript; it is not proof that the audio lacks the speech.

## JSON contract

Command output is one JSON object on stdout. Progress goes to stderr. `--json` is
accepted for clarity but is already the default. Help and version are plain text.
Success has `ok: true`; errors have `ok: false` and an `error` with `code` and
`message`. Success (including no matches or missing setup reported by doctor)
exits 0; failures exit 2; interruption exits 130. Check `doctor.ready` to determine
whether transcription is configured. Errors omit provider response bodies and
credentials. The provider may have processed an upload even when it times out;
there is no automatic retry.

```json
{"ok": true, "out": "/work/interview.transcript.json", "cached": false, "word_count": 182, "segment_count": 24, "audio": {"start": 600, "end": 720, "duration": 120}, "timestamp_basis": "source_seconds", "warnings": []}
```

```json
{"ok": true, "source": {"path": "/media/interview.mp4", "size_bytes": 1234, "mtime_ns": 1}, "language": "ka", "timestamp_basis": "source_seconds", "total": 1, "offset": 0, "next_offset": null, "segments": [{"id": 0, "text": "გამარჯობა!", "start": 600.1, "end": 600.5, "speaker": "speaker_0", "word_ids": [0]}]}
```

```json
{"ok": true, "source": {"path": "/media/interview.mp4", "size_bytes": 1234, "mtime_ns": 1}, "language": "ka", "timestamp_basis": "source_seconds", "total": 1, "offset": 0, "next_offset": null, "matches": [{"start": 600.1, "end": 600.5, "text": "გამარჯობა!", "word_ids": [0], "context": {"start": 600.1, "end": 600.5, "text": "გამარჯობა!"}}]}
```

```json
{"ok": false, "error": {"code": "missing_api_key", "message": "Set ELEVENLABS_API_KEY or use --env-file."}}
```

The saved document has `schema_version: 1`, `tool_version`, source identity,
request settings, provider/model/language, `timestamp_basis`, audio range, full
`text`, `words`, `segments` and `warnings`. A word has `id`, `text`, `start`, `end`
and nullable `speaker`. Segments group speech by punctuation, pauses, speaker
changes or roughly 15 seconds; they are reading chunks, not subtitle layouts.
Punctuation is preserved; spacing/audio-event tokens do not become words.
Missing or invalid word timestamps cause an error instead of fabricated timing.
No confidence scores are invented.

See [the synthetic Georgian example](examples/georgian.json). Read the saved JSON
directly if the bounded commands do not expose what you need. There is no raw
HTTP command or editor API in this version.

## For future agents

[AGENTS.md](AGENTS.md) is the quick entry point. A portable companion skill is in
[skills/kartuli-transcribe/SKILL.md](skills/kartuli-transcribe/SKILL.md). To install
it for Codex, copy its folder into `~/.codex/skills/`.

## Development and validation

```sh
uv venv
uv pip install --python .venv/bin/python -e .
.venv/bin/python -m unittest discover -s tests -v
```

On Windows use `.venv\Scripts\python.exe`. FFmpeg tests generate a tiny synthetic
video and exercise real range extraction; they skip if FFmpeg is absent. Provider
tests use an HTTP mock transport, and the pipeline test substitutes provider
results. No API key or paid API call is needed for the suite. A real Georgian
transcription and its timing quality still need validation with your media/key.
No measured transcription speedup or speech-accuracy benchmark is claimed.

CapForge's ElevenLabs request, audio preparation and punctuation rules informed
this CLI; the MIT notice is retained. API contract reference:
[ElevenLabs Create transcript](https://elevenlabs.io/docs/api-reference/speech-to-text/convert).
