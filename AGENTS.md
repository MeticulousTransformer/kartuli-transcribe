# kartuli-transcribe

Small WIP. Keep changes narrow and explain them plainly.

For transcription tasks, start with `kartuli-transcribe doctor`. All operational
commands return JSON by default. `doctor` is offline and reports `ready`.
Use `transcribe MEDIA --out FILE` once, then `search FILE PHRASE` or `read FILE`.
Read README.md for exact options and JSON shapes. The companion skill lives in
skills/kartuli-transcribe/SKILL.md.

Preserve Georgian Unicode. Timestamps are source seconds, including for range
transcription. Do not treat source time as sequence time. Speaker IDs are
anonymous and are not stable across transcription requests. Never invent timing
or confidence. Search is literal; no matches is not evidence of absent speech.

Reuse saved transcripts. A fresh transcribe uploads audio and can incur charges;
--force is an explicit fresh request. Do not print keys or read unrelated secrets.
Never automatically retry a paid upload. This tool does not edit timelines.

Modules: cli.py handles commands/cache/files; media.py extracts audio;
provider.py handles ElevenLabs; transcript.py normalizes and queries speech.
Keep HTTP imports lazy so offline commands start quickly.

Test with `python -m unittest discover -s tests -v` in the installed environment.
Use synthetic audio and mocked provider transport for routine checks.
