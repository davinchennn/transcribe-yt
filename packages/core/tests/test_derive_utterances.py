"""Tests for derive_utterances function."""

import pytest
from transcripts.models import Word, Utterance, derive_utterances


class TestDeriveUtterances:
    """Test cases for derive_utterances function."""

    def test_empty_words_returns_empty_list(self):
        """Empty words list should return empty utterances."""
        result = derive_utterances([])
        assert result == []

    def test_single_word_creates_single_utterance(self):
        """Single word should create one utterance."""
        words = [Word(text="Hello", start=0, end=500, speaker="A")]
        result = derive_utterances(words)

        assert len(result) == 1
        assert result[0].speaker == "A"
        assert result[0].text == "Hello"
        assert result[0].start == 0
        assert result[0].end == 500

    def test_same_speaker_consecutive_words_grouped(self):
        """Consecutive words by same speaker should be grouped."""
        words = [
            Word(text="Hello", start=0, end=500, speaker="A"),
            Word(text="world", start=550, end=1000, speaker="A"),
            Word(text="today", start=1050, end=1500, speaker="A"),
        ]
        result = derive_utterances(words)

        assert len(result) == 1
        assert result[0].speaker == "A"
        assert result[0].text == "Hello world today"
        assert result[0].start == 0
        assert result[0].end == 1500

    def test_different_speakers_create_separate_utterances(self):
        """Different speakers should create separate utterances."""
        words = [
            Word(text="Hello", start=0, end=500, speaker="A"),
            Word(text="Hi", start=600, end=1000, speaker="B"),
            Word(text="there", start=1050, end=1500, speaker="B"),
        ]
        result = derive_utterances(words)

        assert len(result) == 2
        assert result[0].speaker == "A"
        assert result[0].text == "Hello"
        assert result[1].speaker == "B"
        assert result[1].text == "Hi there"

    def test_long_pause_creates_new_utterance(self):
        """Pause exceeding threshold should create new utterance."""
        words = [
            Word(text="Hello", start=0, end=500, speaker="A"),
            Word(text="world", start=2000, end=2500, speaker="A"),  # 1500ms pause
        ]
        result = derive_utterances(words)

        assert len(result) == 2
        assert result[0].text == "Hello"
        assert result[1].text == "world"

    def test_short_pause_keeps_same_utterance(self):
        """Pause under threshold should keep words in same utterance."""
        words = [
            Word(text="Hello", start=0, end=500, speaker="A"),
            Word(text="world", start=1400, end=1900, speaker="A"),  # 900ms pause
        ]
        result = derive_utterances(words)

        assert len(result) == 1
        assert result[0].text == "Hello world"

    def test_custom_pause_threshold(self):
        """Custom pause threshold should be respected."""
        words = [
            Word(text="Hello", start=0, end=500, speaker="A"),
            Word(text="world", start=1000, end=1500, speaker="A"),  # 500ms pause
        ]

        # Default threshold (1000ms) - should be one utterance
        result = derive_utterances(words)
        assert len(result) == 1

        # Lower threshold (400ms) - should be two utterances
        result = derive_utterances(words, pause_threshold_ms=400)
        assert len(result) == 2

    def test_no_speaker_labels_uses_default(self):
        """Words without speaker labels should use 'SPEAKER' as default."""
        words = [
            Word(text="Hello", start=0, end=500, speaker=None),
            Word(text="world", start=550, end=1000, speaker=None),
        ]
        result = derive_utterances(words)

        assert len(result) == 1
        assert result[0].speaker == "SPEAKER"

    def test_mixed_speaker_and_no_speaker(self):
        """Mixed speaker labels should handle None correctly."""
        words = [
            Word(text="Hello", start=0, end=500, speaker="A"),
            Word(text="Hi", start=600, end=1000, speaker=None),  # Speaker change (A -> None)
        ]
        result = derive_utterances(words)

        assert len(result) == 2
        assert result[0].speaker == "A"
        assert result[1].speaker == "SPEAKER"

    def test_alternating_speakers(self):
        """Rapidly alternating speakers should create separate utterances."""
        words = [
            Word(text="Yes", start=0, end=300, speaker="A"),
            Word(text="No", start=400, end=700, speaker="B"),
            Word(text="Maybe", start=800, end=1200, speaker="A"),
            Word(text="Sure", start=1300, end=1600, speaker="B"),
        ]
        result = derive_utterances(words)

        assert len(result) == 4
        assert [u.speaker for u in result] == ["A", "B", "A", "B"]
        assert [u.text for u in result] == ["Yes", "No", "Maybe", "Sure"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
