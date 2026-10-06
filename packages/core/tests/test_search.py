"""Verify grounded search and request routing without any network calls."""

import json
import unittest
from unittest.mock import patch

from transcripts.llm import LLMError
from transcripts.models import Transcript, Utterance, Word
from transcripts.search import search_transcript


def sample_transcript():
    return Transcript(
        video_url="https://www.youtube.com/watch?v=abcdefghijk",
        title="Learning about costs",
        words=[
            Word("We", 100, 200, speaker="A"),
            Word("reduce", 250, 450, speaker="A"),
            Word("COSTS,", 500, 750, speaker="A"),
            Word("by", 800, 950, speaker="B"),
            Word("sharing", 1000, 1250, speaker="B"),
            Word("resources.", 1300, 1600, speaker="B"),
            Word("A", 5000, 5100, speaker="A"),
            Word("different", 5200, 5400, speaker="A"),
            Word("discussion.", 5500, 5900, speaker="A"),
        ],
        utterances=[
            Utterance("A", "We reduce COSTS,", 100, 750),
            Utterance("B", "by sharing resources.", 800, 1600),
            Utterance("A", "A different discussion.", 5000, 5900),
        ],
    )


class TestSearch(unittest.TestCase):
    def test_exact_phrase_crosses_turns_and_keeps_precise_match_times(self):
        with patch("transcripts.search.request_json") as request:
            matches = search_transcript(sample_transcript(), "costs by SHARING")
        request.assert_not_called()
        assert len(matches) == 1
        assert matches[0]["start"] == 100
        assert matches[0]["end"] == 1600
        assert matches[0]["match_start"] == 500
        assert matches[0]["match_end"] == 1250
        assert matches[0]["utterance_start"] == 0
        assert matches[0]["utterance_end"] == 1
        assert matches[0]["word_start"] == 0
        assert matches[0]["word_end"] == 5
        assert "COSTS, by sharing" in matches[0]["text"]
        assert "different discussion" not in matches[0]["text"]


    def test_exact_whole_words_and_casefold(self):
        transcript = sample_transcript()
        assert search_transcript(transcript, "cost") == []
        assert search_transcript(transcript, "COSTS")[0]["match_start"] == 500
        assert search_transcript(transcript, "resources")[0]["match_end"] == 1600


    def test_exact_context_is_focused_and_result_count_is_bounded(self):
        words = [Word("target" if index % 3 == 1 else "context", index * 100, index * 100 + 80) for index in range(300)]
        transcript = Transcript("url", "title", words=words)
        matches = search_transcript(transcript, "target")
        assert len(matches) == 20
        assert len(matches[0]["text"].split()) <= 23
        assert len({(match["start"], match["end"]) for match in matches}) == 20


    def test_exact_without_words_uses_existing_utterance_boundaries(self):
        transcript = sample_transcript()
        transcript.words = []
        matches = search_transcript(transcript, "costs by")
        assert matches[0]["start"] == 100
        assert matches[0]["end"] == 1600
        assert matches[0]["utterance_start"] == 0
        assert matches[0]["utterance_end"] == 1


    def test_exact_derives_turns_only_when_source_turns_are_missing(self):
        transcript = sample_transcript()
        transcript.utterances = []
        matches = search_transcript(transcript, "by sharing")
        assert matches[0]["utterance_start"] == 1
        assert matches[0]["utterance_end"] == 1
        assert matches[0]["start"] == 800


    def test_semantic_routes_to_llm_and_rebuilds_source_text(self):
        transcript = sample_transcript()
        model_result = {
            "matches": [{
                "segment_start": 0, "segment_end": 1, "relevance": 0.93,
                "text": "Fabricated quotation", "start": 999999,
            }],
        }
        with patch("transcripts.search.request_json", return_value=model_result) as request:
            matches = search_transcript(transcript, "how they lower expenses", "semantic", api_key="test-key")
        request.assert_called_once()
        system_prompt, user_prompt = request.call_args[0]
        payload = json.loads(user_prompt)
        assert "untrusted data" in system_prompt
        assert payload["query"] == "how they lower expenses"
        assert payload["segments"][0]["segment_id"] == 0
        assert payload["segments"][0]["text"] == transcript.utterances[0].text
        assert request.call_args.kwargs["api_key"] == "test-key"
        assert matches[0]["start"] == 100
        assert matches[0]["end"] == 1600
        assert matches[0]["utterance_start"] == 0
        assert matches[0]["utterance_end"] == 1
        assert "We reduce COSTS," in matches[0]["text"]
        assert "Fabricated" not in matches[0]["text"]


    def test_semantic_rejects_invalid_source_ranges_and_scores(self):
        invalid_matches = [
            {"segment_start": -1, "segment_end": 0, "relevance": 0.9},
            {"segment_start": 0, "segment_end": 99, "relevance": 0.9},
            {"segment_start": 1, "segment_end": 0, "relevance": 0.9},
            {"segment_start": True, "segment_end": 1, "relevance": 0.9},
            {"segment_start": "0", "segment_end": 1, "relevance": 0.9},
            {"segment_start": 0, "segment_end": 1, "relevance": 2},
            {"segment_start": 0, "segment_end": 1, "relevance": float("nan")},
        ]
        for match in invalid_matches:
            with self.subTest(match=match), patch("transcripts.search.request_json", return_value={"matches": [match]}):
                with self.assertRaises(LLMError):
                    search_transcript(sample_transcript(), "a remembered idea", "semantic")


    def test_semantic_empty_result_and_network_errors_are_preserved(self):
        with patch("transcripts.search.request_json", return_value={"matches": []}):
            assert search_transcript(sample_transcript(), "unrelated idea", "semantic") == []
        with patch("transcripts.search.request_json", side_effect=LLMError("Provider unavailable")):
            with self.assertRaisesRegex(LLMError, "Provider unavailable"):
                search_transcript(sample_transcript(), "idea", "semantic")


    def test_semantic_chunks_preserve_original_ids_and_deduplicate_overlap(self):
        transcript = sample_transcript()
        calls = []

        def respond(system_prompt, user_prompt, api_key=None):
            payload = json.loads(user_prompt)
            calls.append(payload)
            rows = payload["segments"]
            return {"matches": [{
                "segment_start": row["segment_id"], "segment_end": row["segment_id"],
                "relevance": 0.8 if row["segment_id"] == 1 else 0.3,
            } for row in rows]}

        with patch("transcripts.search._MAX_CHUNK_CHARS", 130), patch("transcripts.search.request_json", side_effect=respond):
            matches = search_transcript(transcript, "sharing resources", "semantic")
        assert len(calls) >= 2
        assert {row["segment_id"] for payload in calls for row in payload["segments"]} == {0, 1, 2}
        assert len(matches) == 1
        assert matches[0]["utterance_start"] == 1
        assert matches[0]["start"] == 800


    def test_semantic_long_turn_is_word_anchored_without_reindexing_utterances(self):
        words = [Word("word{}".format(index), index * 100, index * 100 + 80) for index in range(250)]
        transcript = Transcript(
            "url", "lecture", words=words,
            utterances=[Utterance("SPEAKER", " ".join(word.text for word in words), 0, 24980)],
        )
        with patch("transcripts.search.request_json", return_value={"matches": [
            {"segment_start": 1, "segment_end": 1, "relevance": 0.9},
        ]}):
            matches = search_transcript(transcript, "remembered lecture detail", "semantic")
        assert matches[0]["utterance_start"] == matches[0]["utterance_end"] == 0
        assert matches[0]["word_start"] == 120
        assert matches[0]["word_end"] == 239
        assert matches[0]["start"] == 12000
        assert matches[0]["end"] == 23980
        assert matches[0]["text"] == " ".join(word.text for word in words[120:240])


    def test_semantic_references_must_belong_to_the_current_chunk(self):
        with patch("transcripts.search._MAX_CHUNK_CHARS", 70), patch(
            "transcripts.search.request_json", return_value={"matches": [
                {"segment_start": 2, "segment_end": 2, "relevance": 0.9},
            ]},
        ):
            with self.assertRaisesRegex(LLMError, "outside its source"):
                search_transcript(sample_transcript(), "idea", "semantic")


    def test_invalid_input_never_calls_llm(self):
        invalid_inputs = [("", "exact"), ("  ", "semantic"), ("??", "exact"), ("idea", "other"), ("x" * 1001, "semantic")]
        for query, mode in invalid_inputs:
            with self.subTest(query=query, mode=mode), patch("transcripts.search.request_json") as request:
                with self.assertRaises(ValueError):
                    search_transcript(sample_transcript(), query, mode)
            request.assert_not_called()


    def test_empty_timed_transcript_never_calls_llm(self):
        with patch("transcripts.search.request_json") as request:
            assert search_transcript(Transcript("url", "title"), "idea", "semantic") == []
        request.assert_not_called()
