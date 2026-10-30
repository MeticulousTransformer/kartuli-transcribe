"""Extract only the requested source interval with FFmpeg."""

import shutil
import subprocess
import wave


def extract(media, audio, *, start=0, end=None):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is missing. Install it and run kartuli-transcribe doctor.")
    command = [ffmpeg, "-v", "error", "-nostdin", "-y"]
    if start:
        command += ["-ss", str(start)]
    command += ["-i", str(media)]
    if end is not None:
        command += ["-t", str(end - start)]
    # WAV has no source timestamps. Pad initial silence and preserve timestamp
    # gaps so delayed audio still maps to its position in the source video.
    command += [
        "-map",
        "0:a:0",
        "-vn",
        "-af",
        "aresample=async=1:first_pts=0",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(audio),
    ]
    result = subprocess.run(command, capture_output=True)
    if result.returncode:
        raise RuntimeError(
            "FFmpeg could not extract audio. Check that the file contains a readable audio track."
        )
    try:
        with wave.open(str(audio), "rb") as handle:
            duration = handle.getnframes() / handle.getframerate()
    except (OSError, EOFError, wave.Error) as error:
        raise RuntimeError("FFmpeg did not produce valid audio.") from error
    if duration < 0.1:
        raise RuntimeError("Requested range has less than 0.1 seconds of audio. Check the source times.")
    return duration
