import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import httpx

from kartuli_transcribe.media import extract
from kartuli_transcribe.provider import transcribe


class MediaTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg not installed")
    def test_delayed_audio_preserves_source_time_with_silence(self):
        with tempfile.TemporaryDirectory() as folder:
            media = Path(folder) / "delayed.mkv"
            audio = Path(folder) / "audio.wav"
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=s=16x16:r=10:d=3",
                    "-itsoffset",
                    "2",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=1",
                    "-c:v",
                    "mpeg4",
                    "-c:a",
                    "pcm_s16le",
                    str(media),
                ],
                check=True,
                capture_output=True,
            )
            for start in (0, 1, 2):
                with self.subTest(start=start):
                    duration = extract(media, audio, start=start, end=3)
                    self.assertAlmostEqual(duration, 3 - start, places=2)
                    with wave.open(str(audio), "rb") as handle:
                        leading_silence = not any(handle.readframes(1000))
                    self.assertEqual(leading_silence, start < 2)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg not installed")
    def test_video_range_produces_only_requested_audio(self):
        with tempfile.TemporaryDirectory() as folder:
            media = Path(folder) / "video with spaces.mp4"
            audio = Path(folder) / "audio.wav"
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=s=16x16:r=10:d=3",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=3",
                    "-c:v",
                    "mpeg4",
                    "-c:a",
                    "aac",
                    "-shortest",
                    str(media),
                ],
                check=True,
                capture_output=True,
            )
            duration = extract(media, audio, start=1, end=2)
            self.assertAlmostEqual(duration, 1, places=2)
            with wave.open(str(audio), "rb") as handle:
                self.assertEqual(handle.getnchannels(), 1)
                self.assertEqual(handle.getframerate(), 16000)
            with self.assertRaises(RuntimeError):
                extract(media, audio, start=10, end=11)


class ProviderTests(unittest.TestCase):
    def call(self, handler):
        client_type = httpx.Client
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "audio.wav"
            audio.write_bytes(b"test-audio")
            with patch(
                "kartuli_transcribe.provider.httpx.Client",
                side_effect=lambda **kw: client_type(transport=httpx.MockTransport(handler), **kw),
            ):
                return transcribe(audio, key="test-secret", language="ka", model="scribe_v2", diarize=True)

    def test_upload_contract_and_returned_words(self):
        def handler(request):
            self.assertEqual(str(request.url), "https://api.elevenlabs.io/v1/speech-to-text")
            self.assertEqual(request.headers["xi-api-key"], "test-secret")
            body = request.read()
            for field in [
                b'name="file"',
                b"test-audio",
                b'name="language_code"\r\n\r\nka',
                b'name="diarize"\r\n\r\ntrue',
                b'name="model_id"\r\n\r\nscribe_v2',
                b'name="timestamps_granularity"\r\n\r\nword',
            ]:
                self.assertIn(field, body)
            return httpx.Response(200, json={"words": [{"text": "გამარჯობა", "start": 0, "end": 1}]})

        self.assertEqual(self.call(handler)["words"][0]["text"], "გამარჯობა")

    def test_provider_error_is_redacted_and_not_retried(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(429, text="test-secret leaked in response")

        with self.assertRaisesRegex(RuntimeError, "429") as error:
            self.call(handler)
        self.assertNotIn("test-secret", str(error.exception))
        self.assertEqual(len(calls), 1)

    def test_invalid_provider_json_is_actionable(self):
        with self.assertRaisesRegex(RuntimeError, "JSON"):
            self.call(lambda request: httpx.Response(200, text="<html>not JSON</html>"))


if __name__ == "__main__":
    unittest.main()
