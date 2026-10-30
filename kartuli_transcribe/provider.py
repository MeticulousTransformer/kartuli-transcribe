"""CapForge's Scribe request, without the panel or local web server."""

import httpx


def transcribe(audio, *, key, language, model, diarize):
    data = {
        "model_id": model,
        "timestamps_granularity": "word",
        "diarize": "true" if diarize else "false",
        "tag_audio_events": "false",
    }
    if language != "auto":
        data["language_code"] = language
    try:
        # httpx streams the multipart file instead of loading a long WAV into RAM.
        with httpx.Client(timeout=httpx.Timeout(900, connect=30), follow_redirects=False) as client:
            with open(audio, "rb") as handle:
                response = client.post(
                    "https://api.elevenlabs.io/v1/speech-to-text",
                    headers={"xi-api-key": key},
                    data=data,
                    files={"file": ("audio.wav", handle, "audio/wav")},
                )
    except httpx.HTTPError as error:
        raise RuntimeError(
            "ElevenLabs connection failed or timed out. No automatic retry was made; "
            "the provider may have processed the request."
        ) from error
    if not response.is_success:
        hints = {
            401: "Check ELEVENLABS_API_KEY.",
            403: "Check the key's transcription permission.",
            402: "Check your ElevenLabs credits.",
            429: "Check quota or try again later.",
        }
        raise RuntimeError(
            f"ElevenLabs HTTP {response.status_code}. "
            + hints.get(response.status_code, "Check provider status and request settings.")
        )
    try:
        raw = response.json()
    except ValueError as error:
        raise RuntimeError("ElevenLabs returned invalid JSON.") from error
    if not isinstance(raw, dict):
        raise RuntimeError("ElevenLabs returned an unexpected JSON response.")
    return raw
