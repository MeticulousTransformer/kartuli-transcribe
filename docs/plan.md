# kartuli-transcribe v0.1

Approved scope: a separate Python CLI derived from CapForge's ElevenLabs
transcription path. Audio/video in; Georgian text, speaker labels and source
timestamps out. Four commands: doctor, transcribe, read, search.

Keep it small: no editor integration, web server, provider framework, local
models, semantic search, or automatic timeline edits.

## Implementation

- [x] Test normalization, source offsets, phrase search and bounded reads first.
  Implement `transcript.py` with a versioned JSON document and word/segment data.
- [x] Test audio extraction and provider failures first. Implement `media.py`
  with FFmpeg and `provider.py` with streamed multipart upload via httpx.
- [x] Test CLI JSON errors, cache reuse and range validation first. Implement
  `cli.py`: argparse, environment key, optional explicit env file, required output
  path, no automatic retries of billable uploads.
- [x] Add install instructions, a sample transcript and a small companion skill.
  Install and smoke-test outside this directory, review, then create and push
  the authorized separate public GitHub repository (publication is the final step).

## Checks that matter

Georgian stays Unicode. Missing/nonfinite/reversed times fail instead of being
invented. Range start is added to every provider time. Speaker IDs are anonymous
and local to a request. Reads/searches are offline and bounded. Existing output
is reused only when source path/size/mtime and request options match. A changed
source or different range requires another output path or explicit --force.
Provider errors never print keys or response bodies. JSON goes only to stdout;
diagnostics go to stderr. A synthetic-media FFmpeg test and mocked provider
transport test exercise the pipeline without paying for transcription.

## Decisions

Python 3.10+ and one runtime dependency, httpx. Installed entry point is
`kartuli-transcribe`. API key comes from ELEVENLABS_API_KEY, optionally loaded
from --env-file (existing environment wins). No secrets are copied from CapForge.
Provider model is scribe_v2; ka is default; en and auto are supported.
Times accept seconds or HH:MM:SS.sss, never editor frame timecode.
No performance benchmark claims: speed improvements come from extracting only
requested audio, lazy HTTP imports, streamed upload and reusing saved results.

## Validation, 2026-10-30

17 unittest cases pass on macOS / Python 3.13, including real synthetic-video
extraction and mocked provider uploads. Installed CLI help, doctor, read and
search work from /private/tmp. Companion skill passes its validator.
Independent review found delayed-audio source offsets and eager per-match search
context construction; both were reproduced with failing tests and fixed. Delayed
audio is padded with silence during extraction; search builds context only for
the requested page. All 17 tests pass after those fixes.
Real Georgian API transcription still requires validation with user media/key.
