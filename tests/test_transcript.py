import unittest

from kartuli_transcribe.transcript import normalize, read_segments, search

RAW = {
    "language_code": "ka",
    "language_probability": 0.98,
    "text": "გამარჯობა, როგორ ხარ? კარგად.",
    "words": [
        {"text": "გამარჯობა", "start": 0.1, "end": 0.5, "type": "word", "speaker_id": "speaker_0"},
        {"text": ",", "start": 0.5, "end": 0.5, "type": "word", "speaker_id": "speaker_0"},
        {"text": " ", "start": 0.5, "end": 0.6, "type": "spacing"},
        {"text": "როგორ", "start": 0.6, "end": 0.9, "type": "word", "speaker_id": "speaker_0"},
        {"text": "ხარ?", "start": 0.95, "end": 1.2, "type": "word", "speaker_id": "speaker_0"},
        {"text": "(laughs)", "start": 1.2, "end": 1.3, "type": "audio_event"},
        {"text": "კარგად.", "start": 1.4, "end": 1.8, "type": "word", "speaker_id": "speaker_1"},
    ],
}


class TranscriptTests(unittest.TestCase):
    def test_small_search_page_does_not_scan_context_for_all_matches(self):
        class CountedWords(list):
            visits = 0

            def __iter__(self):
                for item in super().__iter__():
                    self.visits += 1
                    yield item

        words = CountedWords({"id": i, "text": "hello", "start": i, "end": i + 0.5} for i in range(2000))
        result = search({"words": words}, "hello", limit=1, offset=0, context=3)
        self.assertEqual(result["total"], 2000)
        self.assertEqual(len(result["matches"]), 1)
        self.assertLess(words.visits, 5 * len(words))

    # Omitting source offset would send an editor to the wrong moment.
    def test_georgian_source_times_speakers_and_punctuation(self):
        doc = normalize(RAW, start=600, duration=2)
        self.assertEqual(
            doc["words"][0],
            {
                "id": 0,
                "text": "გამარჯობა,",
                "start": 600.1,
                "end": 600.5,
                "speaker": "speaker_0",
            },
        )
        self.assertEqual(len(doc["words"]), 4)
        self.assertEqual(doc["segments"][0]["text"], "გამარჯობა, როგორ ხარ?")
        self.assertEqual(doc["segments"][1]["speaker"], "speaker_1")

    def test_phrase_search_crosses_sentence_and_speaker_boundaries(self):
        doc = normalize(RAW, start=600, duration=2)
        result = search(doc, "ხარ?   კარგად.", limit=10, offset=0, context=1)
        self.assertEqual(result["matches"][0]["start"], 600.95)
        self.assertEqual(result["matches"][0]["end"], 601.8)
        self.assertEqual(result["matches"][0]["text"], "ხარ? კარგად.")
        self.assertIsNone(result["next_offset"])

    def test_read_range_uses_overlap_and_pagination(self):
        doc = normalize(RAW, start=600, duration=2)
        result = read_segments(doc, start=601, end=602, limit=1, offset=0)
        self.assertEqual(len(result["segments"]), 1)
        self.assertEqual(result["next_offset"], 1)
        self.assertEqual(result["segments"][0]["start"], 600.1)

    def test_missing_or_invalid_word_times_are_rejected(self):
        for token in [
            {"text": "test"},
            {"text": "test", "start": 1, "end": 0},
            {"text": "test", "start": float("nan"), "end": 1},
            {"text": "test", "start": -1, "end": 1},
            {"text": "test", "start": 0, "end": 20},
        ]:
            with self.subTest(token=token), self.assertRaises(ValueError):
                normalize({"words": [token]}, start=0, duration=2)

    def test_text_without_word_times_is_not_silence(self):
        with self.assertRaises(ValueError):
            normalize({"text": "speech", "words": []}, start=0, duration=2)
        self.assertEqual(normalize({"text": "", "words": []}, start=0, duration=2)["words"], [])

    def test_search_pagination_and_casefold(self):
        raw = {
            "words": [
                {"text": "Hello", "start": 0, "end": 1},
                {"text": "hello", "start": 1, "end": 2},
            ]
        }
        doc = normalize(raw, start=0, duration=2)
        result = search(doc, "HELLO", limit=1, offset=0, context=0)
        self.assertEqual(result["next_offset"], 1)
        self.assertEqual(search(doc, "hello", limit=1, offset=1, context=0)["matches"][0]["start"], 1)


if __name__ == "__main__":
    unittest.main()
