"""Normalize provider words and query saved transcripts without network access."""

import bisect
import json
import math
import string
import unicodedata
from pathlib import Path


def seconds(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Word timestamps must be numbers.")
    if not math.isfinite(value) or value < 0:
        raise ValueError("Timestamps must be finite, nonnegative seconds.")
    return float(value)


def normalize(raw, *, start, duration):
    if not isinstance(raw, dict) or not isinstance(raw.get("words"), list):
        raise ValueError("Provider response has no word list.")
    words = []
    for token in raw["words"]:
        if not isinstance(token, dict):
            raise ValueError("Provider returned an invalid word.")
        if token.get("type", "word") != "word":
            continue
        text = str(token.get("text") or "").strip()
        if not text:
            continue
        # CapForge's rule: punctuation tokens belong to the preceding word.
        if all(unicodedata.category(char).startswith("P") or char in string.punctuation for char in text):
            if words:
                words[-1]["text"] += text
            continue
        begin, end = seconds(token.get("start")), seconds(token.get("end"))
        if end < begin or end > duration + 0.1:
            raise ValueError("Provider word times fall outside the extracted audio.")
        if words and begin + start < words[-1]["start"] - 0.001:
            raise ValueError("Provider word times are out of order.")
        speaker = token.get("speaker_id")
        words.append(
            {
                "id": len(words),
                "text": text,
                "start": round(start + begin, 6),
                "end": round(start + end, 6),
                "speaker": str(speaker) if speaker is not None else None,
            }
        )
    if not words and str(raw.get("text") or "").strip():
        raise ValueError("Provider returned speech without usable word timestamps.")
    segments = []
    current = []
    for word in words:
        if current and (
            word["speaker"] != current[-1]["speaker"]
            or word["start"] - current[-1]["end"] >= 0.8
            or current[-1]["text"].endswith((".", "?", "!", "…", "。"))
            or word["end"] - current[0]["start"] > 15
        ):
            segments.append(_segment(current, len(segments)))
            current = []
        current.append(word)
    if current:
        segments.append(_segment(current, len(segments)))
    return {
        "schema_version": 1,
        "provider": "elevenlabs",
        "language": raw.get("language_code"),
        "timestamp_basis": "source_seconds",
        "audio": {"start": start, "end": round(start + duration, 6), "duration": duration},
        "text": " ".join(w["text"] for w in words),
        "words": words,
        "segments": segments,
        "warnings": [] if words else ["No speech words returned."],
    }


def _segment(words, index):
    return {
        "id": index,
        "text": " ".join(w["text"] for w in words),
        "start": words[0]["start"],
        "end": max(w["end"] for w in words),
        "speaker": words[0]["speaker"],
        "word_ids": [w["id"] for w in words],
    }


def load_document(path):
    with Path(path).open(encoding="utf-8") as handle:
        doc = json.load(handle)
    if not isinstance(doc, dict) or doc.get("schema_version") != 1:
        raise ValueError("Expected a kartuli-transcribe schema_version 1 transcript.")
    for name in ("words", "segments"):
        if not isinstance(doc.get(name), list):
            raise ValueError(f"Transcript has no {name} list.")
        previous = -1
        for item in doc[name]:
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                raise ValueError(f"Invalid transcript {name} entry.")
            begin, end = seconds(item.get("start")), seconds(item.get("end"))
            if end < begin or begin < previous:
                raise ValueError(f"Invalid or unordered transcript {name} times.")
            previous = begin
    return doc


def _page(items, limit, offset):
    return {
        "total": len(items),
        "offset": offset,
        "next_offset": offset + limit if offset + limit < len(items) else None,
    }


def read_segments(doc, *, start=0, end=None, limit=30, offset=0, include_words=False):
    selected = [s for s in doc["segments"] if s["end"] >= start and (end is None or s["start"] < end)]
    page = selected[offset : offset + limit]
    result = {**_page(selected, limit, offset), "segments": page}
    if include_words:
        ids = {i for segment in page for i in segment["word_ids"]}
        result["words"] = [w for w in doc["words"] if w["id"] in ids]
    return result


def _fold(text):
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def search(doc, query, *, limit=20, offset=0, context=3):
    query = _fold(query)
    if not query:
        raise ValueError("Search phrase must not be empty.")
    words = doc["words"]
    chunks, starts, ends = [], [], []
    cursor = 0
    for word in words:
        chunk = _fold(word["text"])
        starts.append(cursor)
        chunks.append(chunk)
        cursor += len(chunk)
        ends.append(cursor)
        cursor += 1
    text = " ".join(chunks)
    matches = []
    total = 0
    cursor = 0
    while (position := text.find(query, cursor)) >= 0:
        # Count all matches, but only build nearby speech for the requested page.
        if offset <= total < offset + limit:
            first = bisect.bisect_right(ends, position)
            last = bisect.bisect_left(starts, position + len(query)) - 1
            hit = words[first : last + 1]
            begin, end = hit[0]["start"], max(w["end"] for w in hit)
            around = [w for w in words if w["end"] >= begin - context and w["start"] <= end + context]
            matches.append(
                {
                    "start": begin,
                    "end": end,
                    "text": " ".join(w["text"] for w in hit),
                    "word_ids": [w["id"] for w in hit],
                    "context": {
                        "start": around[0]["start"],
                        "end": max(w["end"] for w in around),
                        "text": " ".join(w["text"] for w in around),
                    },
                }
            )
        total += 1
        cursor = position + len(query)
    return {
        "total": total,
        "offset": offset,
        "next_offset": offset + limit if offset + limit < total else None,
        "matches": matches,
    }
