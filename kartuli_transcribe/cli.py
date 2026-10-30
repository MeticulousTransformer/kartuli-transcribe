"""JSON-first commands for agents; help stays readable for people."""

import argparse
import importlib.util
import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path

from . import __version__
from .transcript import load_document, normalize, read_segments, search


class CliError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CliError("usage_error", message)


def time_value(value):
    try:
        parts = [float(p) for p in value.split(":")]
        if not 1 <= len(parts) <= 3 or any(not math.isfinite(p) or p < 0 for p in parts):
            raise ValueError
        if len(parts) > 1 and (parts[-1] >= 60 or any(p != int(p) for p in parts[:-1])):
            raise ValueError
        if len(parts) == 3 and parts[1] >= 60:
            raise ValueError
        return sum(p * 60**i for i, p in enumerate(reversed(parts)))
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use nonnegative seconds or HH:MM:SS.sss (no frames).") from error


def bounded_integer(value):
    try:
        number = int(value)
        if not 1 <= number <= 1000:
            raise ValueError
        return number
    except ValueError as error:
        raise argparse.ArgumentTypeError("Limit must be 1–1000.") from error


def nonnegative_integer(value):
    try:
        number = int(value)
        if number < 0:
            raise ValueError
        return number
    except ValueError as error:
        raise argparse.ArgumentTypeError("Offset must be a nonnegative integer.") from error


def parser():
    root = Parser(
        prog="kartuli-transcribe",
        description="Georgian speech and source timestamps for editing agents. JSON output by default.",
    )
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--json", action="store_true", help="JSON is already the default")
    root.add_argument("--env-file", type=Path, help="Explicit key file; existing environment wins")
    commands = root.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="Check local setup without network requests or charges")
    transcribe = commands.add_parser(
        "transcribe", help="Upload audio to ElevenLabs and save a word-timed transcript"
    )
    read = commands.add_parser("read", help="Read a bounded range of saved transcript segments, offline")
    find = commands.add_parser("search", help="Find literal phrases in a saved transcript, offline")
    for sub in (doctor, transcribe, read, find):
        sub.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    for sub in (doctor, transcribe):
        sub.add_argument(
            "--env-file",
            type=Path,
            default=argparse.SUPPRESS,
            help="Read ELEVENLABS_API_KEY from this file; environment wins",
        )
    transcribe.add_argument("media", type=Path)
    transcribe.add_argument(
        "--out", required=True, type=Path, help="Saved transcript JSON; matching runs reuse it"
    )
    transcribe.add_argument("--language", choices=("ka", "en", "auto"), default="ka")
    transcribe.add_argument("--model", choices=("scribe_v2", "scribe_v1"), default="scribe_v2")
    transcribe.add_argument("--no-diarize", action="store_true", help="Disable anonymous speaker labels")
    transcribe.add_argument(
        "--force", action="store_true", help="Replace existing output and make a fresh paid request"
    )
    for sub in (transcribe, read):
        sub.add_argument("--start", type=time_value, default=0, help="Source seconds or HH:MM:SS.sss")
        sub.add_argument(
            "--end", type=time_value, help="Exclusive source end; defaults to end of media/transcript"
        )
    for sub, default_limit in ((read, 30), (find, 20)):
        sub.add_argument("transcript", type=Path)
        sub.add_argument("--limit", type=bounded_integer, default=default_limit)
        sub.add_argument("--offset", type=nonnegative_integer, default=0)
    read.add_argument("--words", action="store_true", help="Include word timings for the returned segments")
    find.add_argument("phrase", help="Literal phrase; case and whitespace are normalized")
    find.add_argument(
        "--context", type=time_value, default=3, help="Seconds of nearby speech (default 3, maximum 30)"
    )
    return root


def api_key(env_file):
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if key:
        return key, "env"
    if env_file:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.strip().partition("=")
            if sep and name.strip() == "ELEVENLABS_API_KEY":
                value = value.strip().strip("\"'")
                if value:
                    return value, "env_file"
    return "", "missing"


def doctor(args):
    key, source = api_key(args.env_file)
    ffmpeg = shutil.which("ffmpeg")
    http = importlib.util.find_spec("httpx") is not None
    missing = []
    if not key:
        missing.append("Set ELEVENLABS_API_KEY or use --env-file.")
    if not ffmpeg:
        missing.append("Install FFmpeg and add it to PATH.")
    if not http:
        missing.append("Install kartuli-transcribe with its httpx dependency.")
    return {
        "version": __version__,
        "ready": not missing,
        "offline_commands_ready": True,
        "auth": {"available": bool(key), "source": source},
        "ffmpeg": ffmpeg,
        "http_dependency": http,
        "network_checked": False,
        "next_steps": missing,
    }


def _summary(doc, out, cached):
    return {
        "out": str(out),
        "cached": cached,
        "word_count": len(doc["words"]),
        "segment_count": len(doc["segments"]),
        "audio": doc["audio"],
        "timestamp_basis": "source_seconds",
        "warnings": doc.get("warnings", []),
    }


def run_transcribe(args):
    media, out = args.media.expanduser().resolve(), args.out.expanduser().resolve()
    if media == out:
        raise CliError("invalid_input", "Output path must be different from the source media.")
    if not media.is_file():
        raise CliError("invalid_input", f"Media file not found: {media}")
    stat = media.stat()
    source = {"path": str(media), "size_bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    request = {
        "start": args.start,
        "end": args.end,
        "language": args.language,
        "model": args.model,
        "diarize": not args.no_diarize,
    }
    if out.exists() and not args.force:
        try:
            doc = load_document(out)
        except (ValueError, OSError):
            doc = {}
        if doc.get("source") == source and doc.get("request") == request:
            return _summary(doc, out, True)
        raise CliError(
            "output_exists",
            "Output already exists for different media or settings. "
            "Choose another --out path, or use --force for a fresh request.",
        )
    key, _ = api_key(args.env_file)
    if not key:
        raise CliError("missing_api_key", "Set ELEVENLABS_API_KEY or use --env-file.")
    # Keep HTTP imports out of offline commands and help startup.
    from .media import extract

    try:
        from .provider import transcribe
    except ImportError as error:
        raise CliError(
            "missing_dependency", "Install kartuli-transcribe with its httpx dependency."
        ) from error
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.is_dir():
        raise CliError("invalid_input", "Output path points to a directory.")
    # Confirm a writable destination before making a billable request.
    with tempfile.TemporaryDirectory(prefix=".kartuli-", dir=out.parent) as folder:
        audio = Path(folder) / "audio.wav"
        print("Preparing requested audio…", file=sys.stderr)
        duration = extract(media, audio, start=args.start, end=args.end)
        print(f"Transcribing {duration:.1f}s with ElevenLabs…", file=sys.stderr)
        raw = transcribe(
            audio, key=key, language=args.language, model=args.model, diarize=not args.no_diarize
        )
        doc = normalize(raw, start=args.start, duration=duration)
        doc.update({"source": source, "request": request, "model": args.model, "tool_version": __version__})
        destination = Path(folder) / "transcript.json"
        destination.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        os.replace(destination, out)
    return _summary(doc, out, False)


def dispatch(args):
    if hasattr(args, "end") and args.end is not None and args.end <= args.start:
        raise CliError("invalid_range", "--end must be greater than --start.")
    if args.command == "doctor":
        return doctor(args)
    if args.command == "transcribe":
        return run_transcribe(args)
    doc = load_document(args.transcript.expanduser())
    metadata = {
        "source": doc.get("source"),
        "language": doc.get("language"),
        "timestamp_basis": "source_seconds",
    }
    if args.command == "read":
        return {
            **metadata,
            **read_segments(
                doc,
                start=args.start,
                end=args.end,
                limit=args.limit,
                offset=args.offset,
                include_words=args.words,
            ),
        }
    if args.context > 30:
        raise CliError("invalid_input", "--context must be at most 30 seconds.")
    return {
        **metadata,
        **search(doc, args.phrase, limit=args.limit, offset=args.offset, context=args.context),
    }


def main(argv=None):
    try:
        data = dispatch(parser().parse_args(argv))
        print(json.dumps({"ok": True, **data}, ensure_ascii=False, allow_nan=False))
        return 0
    except KeyboardInterrupt:
        code, message, status = (
            "interrupted",
            "Interrupted. An upload may already have been processed; check before retrying.",
            130,
        )
    except CliError as error:
        code, message, status = error.code, str(error), 2
    except (OSError, ValueError, RuntimeError) as error:
        code, message, status = "processing_error", str(error), 2
    except (KeyError, TypeError):
        code, message, status = "invalid_document", "Malformed transcript or provider response.", 2
    print(json.dumps({"ok": False, "error": {"code": code, "message": message}}, ensure_ascii=False))
    return status
