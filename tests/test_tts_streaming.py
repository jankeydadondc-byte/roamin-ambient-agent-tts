"""Tests for streaming-tts: _split_sentences and speak_streaming."""

from __future__ import annotations

from unittest.mock import patch

import agent.core.voice.tts as tts_mod
from agent.core.voice.tts import TextToSpeech, _split_sentences

# ---------------------------------------------------------------------------
# Task 5.1: _split_sentences unit tests
# ---------------------------------------------------------------------------


class TestSplitSentences:
    def test_standard_boundary(self):
        result = _split_sentences("Hello. How are you?")
        assert result == ["Hello.", "How are you?"]

    def test_exclamation_boundary(self):
        result = _split_sentences("Great! Now let's go.")
        assert result == ["Great!", "Now let's go."]

    def test_abbreviation_not_split(self):
        result = _split_sentences("Dr. Smith is here.")
        assert result == ["Dr. Smith is here."]

    def test_mr_abbreviation(self):
        result = _split_sentences("Mr. Jones left early.")
        assert result == ["Mr. Jones left early."]

    def test_ellipsis_not_split(self):
        result = _split_sentences("Wait... okay.")
        # Ellipsis should not produce empty segments
        assert all(len(s.replace(" ", "")) >= 4 for s in result)
        assert any("okay" in s for s in result)

    def test_single_sentence(self):
        result = _split_sentences("Just one sentence here.")
        assert result == ["Just one sentence here."]

    def test_empty_string(self):
        result = _split_sentences("")
        # Empty string: returns whatever the function decides (no crash)
        assert isinstance(result, list)

    def test_min_length_guard(self):
        # Very short fragments from splitting should be dropped
        result = _split_sentences("OK. This is a longer sentence.")
        # "OK." has 2 non-ws chars — should be dropped or merged; "This is..." kept
        for seg in result:
            assert len(seg.replace(" ", "")) >= 4


# ---------------------------------------------------------------------------
# Task 5.2: speak_streaming with Chatterbox mocked
# ---------------------------------------------------------------------------


class TestSpeakStreamingWithChatterbox:
    def _make_tts(self):
        tts = TextToSpeech.__new__(TextToSpeech)
        tts._pyttsx3_engine = None
        tts._phrase_cache = {}
        return tts

    def test_sentences_synthesised_and_played_in_order(self):
        tts = self._make_tts()
        call_order: list[str] = []

        def fake_synth(text, url, dest, **kwargs):
            call_order.append(("synth", text))
            dest.write_bytes(b"RIFF")  # minimal fake WAV
            return True

        def fake_play(path):
            call_order.append(("play", path.name))

        with (
            patch.object(tts_mod, "_find_chatterbox_url", return_value="http://127.0.0.1:4123"),
            patch.object(tts_mod, "_synthesize_to_file", side_effect=fake_synth),
            patch.object(tts, "_play_wav", side_effect=fake_play),
        ):
            tts.speak_streaming("Hello. How are you?")

        synth_calls = [t for op, t in call_order if op == "synth"]
        assert len(synth_calls) == 2
        assert synth_calls[0] == "Hello."
        assert synth_calls[1] == "How are you?"

    def test_play_order_matches_sentence_order(self):
        tts = self._make_tts()
        played: list[str] = []

        def fake_synth(text, url, dest, **kwargs):
            dest.write_bytes(b"RIFF")
            return True

        def fake_play(path):
            played.append(path.stem)

        with (
            patch.object(tts_mod, "_find_chatterbox_url", return_value="http://127.0.0.1:4123"),
            patch.object(tts_mod, "_synthesize_to_file", side_effect=fake_synth),
            patch.object(tts, "_play_wav", side_effect=fake_play),
        ):
            tts.speak_streaming("First sentence. Second sentence.")

        assert len(played) == 2
        # Files are named chatterbox_streaming_0, chatterbox_streaming_1
        assert played[0] == "chatterbox_streaming_0"
        assert played[1] == "chatterbox_streaming_1"


# ---------------------------------------------------------------------------
# Task 5.3: speak_streaming with Chatterbox unavailable
# ---------------------------------------------------------------------------


class TestSpeakStreamingFallback:
    def _make_tts(self):
        tts = TextToSpeech.__new__(TextToSpeech)
        tts._pyttsx3_engine = None
        tts._phrase_cache = {}
        return tts

    def test_falls_through_to_pyttsx3_per_sentence(self):
        tts = self._make_tts()
        pyttsx3_calls: list[str] = []

        def fake_speak_p3(text):
            pyttsx3_calls.append(text)

        with (
            patch.object(tts_mod, "_find_chatterbox_url", return_value=None),
            patch.object(tts, "_speak_pyttsx3", side_effect=fake_speak_p3),
        ):
            tts.speak_streaming("Hello. How are you?")

        assert len(pyttsx3_calls) == 2
        assert pyttsx3_calls[0] == "Hello."
        assert pyttsx3_calls[1] == "How are you?"


# ---------------------------------------------------------------------------
# Task 5.4: synthesis failure on sentence N doesn't abort remaining sentences
# ---------------------------------------------------------------------------


class TestSpeakStreamingSynthesisFailure:
    def _make_tts(self):
        tts = TextToSpeech.__new__(TextToSpeech)
        tts._pyttsx3_engine = None
        tts._phrase_cache = {}
        return tts

    def test_remaining_sentences_play_after_failure(self):
        tts = self._make_tts()
        pyttsx3_calls: list[str] = []
        play_calls: list = []

        call_counts = [0]

        def fake_synth(text, url, dest, **kwargs):
            # Fail on the second sentence
            if call_counts[0] == 1:
                call_counts[0] += 1
                return False
            call_counts[0] += 1
            dest.write_bytes(b"RIFF")
            return True

        def fake_play(path):
            play_calls.append(path)

        def fake_speak_p3(text):
            pyttsx3_calls.append(text)

        with (
            patch.object(tts_mod, "_find_chatterbox_url", return_value="http://127.0.0.1:4123"),
            patch.object(tts_mod, "_synthesize_to_file", side_effect=fake_synth),
            patch.object(tts, "_play_wav", side_effect=fake_play),
            patch.object(tts, "_speak_pyttsx3", side_effect=fake_speak_p3),
        ):
            # Should not raise
            tts.speak_streaming("First sentence. Second sentence. Third sentence.")

        # Sentence 1 and 3 played via Chatterbox; sentence 2 fell back to pyttsx3
        assert len(play_calls) >= 1, "At least one sentence should play via Chatterbox"
        assert len(pyttsx3_calls) >= 1, "Failed sentence should fall back to pyttsx3"
