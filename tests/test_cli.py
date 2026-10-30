import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_transcript import RAW

from kartuli_transcribe.cli import main


class CliTests(unittest.TestCase):
    def run_cli(self, args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            code = main(args)
        return code, json.loads(output.getvalue())

    def test_argument_errors_are_json(self):
        for args in [
            ["unknown"],
            ["read"],
            ["read", "missing.json", "--start", "nan"],
            ["read", "missing.json", "--start", "5", "--end", "4"],
        ]:
            with self.subTest(args=args):
                code, data = self.run_cli(args)
                self.assertEqual(code, 2)
                self.assertFalse(data["ok"])
                self.assertIn("code", data["error"])

    def test_doctor_never_reveals_key_and_works_without_auth(self):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "hidden-test-secret"}):
            code, data = self.run_cli(["--json", "doctor"])
        self.assertEqual(code, 0)
        self.assertTrue(data["auth"]["available"])
        self.assertNotIn("hidden-test-secret", json.dumps(data))
        with patch.dict(os.environ, {}, clear=True):
            code, data = self.run_cli(["doctor", "--json"])
        self.assertEqual(code, 0)
        self.assertFalse(data["ready"])
        self.assertTrue(data["offline_commands_ready"])

    def test_transcribe_cache_and_offline_search(self):
        with tempfile.TemporaryDirectory() as folder:
            media = Path(folder) / "input.mp4"
            out = Path(folder) / "transcript.json"
            media.write_bytes(b"source")
            args = ["transcribe", str(media), "--start", "10:00", "--end", "10:02", "--out", str(out)]
            with (
                patch.dict(os.environ, {"ELEVENLABS_API_KEY": "secret"}),
                patch("kartuli_transcribe.media.extract", return_value=2),
                patch("kartuli_transcribe.provider.transcribe", return_value=RAW),
            ):
                code, result = self.run_cli(args)
            self.assertEqual(code, 0)
            self.assertFalse(result["cached"])
            self.assertEqual(json.loads(out.read_text())["words"][0]["start"], 600.1)
            with patch.dict(os.environ, {}, clear=True):
                code, result = self.run_cli(args)
            self.assertEqual(code, 0)
            self.assertTrue(result["cached"])
            code, result = self.run_cli(["search", str(out), "როგორ ხარ?"])
            self.assertEqual(code, 0)
            self.assertEqual(result["matches"][0]["start"], 600.6)
            media.write_bytes(b"changed-source")
            code, result = self.run_cli(args)
            self.assertEqual(code, 2)
            self.assertEqual(result["error"]["code"], "output_exists")

    def test_output_cannot_replace_source(self):
        with tempfile.TemporaryDirectory() as folder:
            media = Path(folder) / "source.wav"
            media.write_bytes(b"source")
            code, data = self.run_cli(["transcribe", str(media), "--out", str(media), "--force"])
            self.assertEqual(code, 2)
            self.assertEqual(media.read_bytes(), b"source")

    def test_explicit_env_file_and_environment_precedence(self):
        with tempfile.TemporaryDirectory() as folder:
            env = Path(folder) / "keys.env"
            env.write_text("ELEVENLABS_API_KEY=file-secret\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                _, result = self.run_cli(["doctor", "--env-file", str(env)])
                self.assertEqual(result["auth"], {"available": True, "source": "env_file"})
                self.assertNotIn("ELEVENLABS_API_KEY", os.environ)
            with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "env-secret"}):
                _, result = self.run_cli(["doctor", "--env-file", str(env)])
                self.assertEqual(result["auth"]["source"], "env")


if __name__ == "__main__":
    unittest.main()
