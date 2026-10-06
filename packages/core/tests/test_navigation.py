"""Navigation analysis validates hierarchy and anchors results to source timings."""

import json
import unittest
from unittest.mock import patch

from transcripts.llm import LLMError
from transcripts.models import AnalysisStatus, Transcript, Utterance, Word
from transcripts.navigation import analyze_navigation, occurrence_from_range, source_segments


SUMMARY = "Source passages explain learning concepts and practical examples, connecting recurring costs, savings, decisions, and conclusions through concrete discussion and evidence."


def sample_transcript(count=6):
    utterances = [Utterance("A", f"Source passage {index}.", 1250 + index * 5000, 4500 + index * 5000)
                  for index in range(count)]
    return Transcript(video_url="https://youtu.be/abcdefghijk", title="Learning", utterances=utterances)


def chapter(title, first, last, children=None):
    return {"title": title, "summary": SUMMARY, "start_segment": first,
            "end_segment": last, "children": children or []}


def topic(title, ranges=None, children=None):
    return {"title": title, "summary": SUMMARY, "ranges": ranges or [], "children": children or []}


class TestNavigationAnalysis(unittest.TestCase):
    def test_timeline_hierarchy_and_source_timestamps(self):
        result = {"summary": "The discussion progresses.", "nodes": [
            chapter("Beginning", 0, 2, [chapter("Intro", 0, 0), chapter("Concept", 1, 2)]),
            chapter("Practice", 3, 5),
        ]}
        with patch("transcripts.navigation.request_json", return_value=result) as request:
            analysis = analyze_navigation(sample_transcript(), "video", "timeline", "key")
        self.assertEqual(analysis.status, AnalysisStatus.COMPLETED, analysis.error)
        self.assertEqual(request.call_count, 1)
        node = analysis.nodes[0]
        self.assertEqual(node["start"], 1250)
        self.assertEqual(node["end"], 14500)
        passage = node["children"][1]["occurrences"][0]
        self.assertEqual(passage["utterance_start"], 1)
        self.assertEqual(passage["utterance_end"], 2)
        self.assertEqual(passage["text"], "Source passage 1. Source passage 2.")
        self.assertEqual(passage["start"], 6250)
        self.assertEqual(passage["end"], 14500)
        self.assertEqual(analysis.to_dict()["view"], "timeline")

    def test_topics_group_repeated_passages(self):
        result = {"summary": "Cost comes up twice.", "nodes": [topic("Cost", children=[
            topic("Savings", [[0, 1], [4, 5]])
        ])]}
        with patch("transcripts.navigation.request_json", return_value=result) as request:
            analysis = analyze_navigation(sample_transcript(), "video", "topics")
        self.assertEqual(analysis.status, AnalysisStatus.COMPLETED, analysis.error)
        self.assertIn("recurring", request.call_args[0][0])
        occurrences = analysis.nodes[0]["occurrences"]
        self.assertEqual(len(occurrences), 2)
        self.assertEqual(occurrences[1]["start"], 21250)
        self.assertEqual(occurrences[1]["end"], 29500)
        self.assertEqual(occurrences[1]["text"], "Source passage 4. Source passage 5.")

    def test_invalid_timeline_hierarchy_fails_without_partial_result(self):
        invalids = [
            [chapter("Gap", 1, 5)],
            [chapter("Missing end", 0, 4)],
            [chapter("Outside", 0, 6)],
            [chapter("Parent", 0, 5, [chapter("Child", 0, 2)])],
            [chapter("Overlap", 0, 3), chapter("Again", 3, 5)],
            [chapter("Noninteger", False, 5)],
            [chapter("Fraction", 0, 5.0)],
        ]
        for nodes in invalids:
            with self.subTest(nodes=nodes), patch("transcripts.navigation.request_json", return_value={"nodes": nodes}):
                analysis = analyze_navigation(sample_transcript(), "video", "timeline")
            self.assertEqual(analysis.status, AnalysisStatus.FAILED)
            self.assertEqual(analysis.nodes, [])
            self.assertTrue(analysis.error)

    def test_invalid_topic_ranges_and_parent_hierarchy_fail(self):
        invalids = [
            [topic("Out of bounds", [[0, 6]])],
            [topic("Empty")],
            [topic("Overlap", [[0, 2], [2, 4]])],
            [topic("Parent", [[0, 1]], [topic("Outside child", [[3, 4]])])],
            [topic("String index", [["0", 1]])],
        ]
        for nodes in invalids:
            with self.subTest(nodes=nodes), patch("transcripts.navigation.request_json", return_value={"nodes": nodes}):
                analysis = analyze_navigation(sample_transcript(), "video", "topics")
            self.assertEqual(analysis.status, AnalysisStatus.FAILED)
            self.assertEqual(analysis.nodes, [])

    def test_each_view_uses_its_own_analysis_prompt(self):
        with patch("transcripts.navigation.request_json", side_effect=[
            {"nodes": [chapter("All", 0, 5)]},
            {"nodes": [topic("All", [[0, 5]])]},
        ]) as request:
            timeline = analyze_navigation(sample_transcript(), "video", "timeline")
            topics = analyze_navigation(sample_transcript(), "video", "topics")
        self.assertEqual(timeline.status, AnalysisStatus.COMPLETED)
        self.assertEqual(topics.status, AnalysisStatus.COMPLETED)
        self.assertNotEqual(request.call_args_list[0][0][0], request.call_args_list[1][0][0])

    def test_long_transcript_timeline_has_complete_global_chunk_indexes(self):
        responses = [
            {"summary": "First half", "nodes": [chapter("First", 0, 2)]},
            {"summary": "Second half", "nodes": [chapter("Second", 3, 5)]},
            {"summary": "Whole video", "nodes": [chapter("Whole", 0, 1)]},
        ]
        with patch("transcripts.navigation.MAX_CHUNK_SEGMENTS", 3), patch("transcripts.navigation.request_json", side_effect=responses) as request:
            analysis = analyze_navigation(sample_transcript(), "video", "timeline")
        self.assertEqual(analysis.status, AnalysisStatus.COMPLETED, analysis.error)
        self.assertEqual(request.call_count, 3)
        second_input = json.loads(request.call_args_list[1][0][1])
        self.assertEqual([item["index"] for item in second_input["segments"]], [3, 4, 5])
        root = analysis.nodes[0]
        self.assertEqual((root["start"], root["end"]), (1250, 29500))
        self.assertEqual(len(root["children"]), 2)
        self.assertEqual(root["occurrences"][0]["utterance_end"], 5)

    def test_long_transcript_merges_recurring_topics_across_chunks(self):
        responses = [
            {"nodes": [topic("Cost", [[0, 1]]), topic("Practice", [[2, 2]])]},
            {"nodes": [topic("Prices", [[3, 4]]), topic("Conclusion", [[5, 5]])]},
            {"nodes": [
                {"title": "Cost", "summary": "Recurring costs", "source_ids": [0, 2], "children": []},
                {"title": "Practice", "source_ids": [1], "children": []},
                {"title": "Conclusion", "source_ids": [3], "children": []},
            ]},
        ]
        with patch("transcripts.navigation.MAX_CHUNK_SEGMENTS", 3), patch("transcripts.navigation.request_json", side_effect=responses):
            analysis = analyze_navigation(sample_transcript(), "video", "topics")
        self.assertEqual(analysis.status, AnalysisStatus.COMPLETED, analysis.error)
        costs = analysis.nodes[0]["occurrences"]
        self.assertEqual(len(costs), 2)
        self.assertEqual([item["utterance_start"] for item in costs], [0, 3])

    def test_regrouping_cannot_drop_or_duplicate_source_topics(self):
        for ids in ([0], [0, 0], [0, 2]):
            responses = [
                {"nodes": [topic("A", [[0, 2]])]},
                {"nodes": [topic("B", [[3, 5]])]},
                {"nodes": [{"title": "Group", "source_ids": ids, "children": []}]},
            ]
            with self.subTest(ids=ids), patch("transcripts.navigation.MAX_CHUNK_SEGMENTS", 3), patch("transcripts.navigation.request_json", side_effect=responses):
                analysis = analyze_navigation(sample_transcript(), "video", "topics")
            self.assertEqual(analysis.status, AnalysisStatus.FAILED)
            self.assertIn("source", analysis.error)

    def test_recurring_subtopics_are_regrouped_across_chunk_hierarchies(self):
        responses = [
            {"nodes": [topic("Cost", children=[topic("Savings", [[0, 1]])]), topic("Practice", [[2, 2]])]},
            {"nodes": [topic("Prices", children=[topic("Savings", [[3, 4]])]), topic("Conclusion", [[5, 5]])]},
            {"nodes": [
                {"title": "Cost", "source_ids": [], "children": [
                    {"title": "Savings", "summary": SUMMARY, "source_ids": [0, 2], "children": []}]},
                {"title": "Practice", "source_ids": [1], "children": []},
                {"title": "Conclusion", "source_ids": [3], "children": []},
            ]},
        ]
        with patch("transcripts.navigation.MAX_CHUNK_SEGMENTS", 3), patch("transcripts.navigation.request_json", side_effect=responses) as request:
            analysis = analyze_navigation(sample_transcript(), "video", "topics")
        self.assertEqual(analysis.status, AnalysisStatus.COMPLETED, analysis.error)
        records = json.loads(request.call_args_list[2][0][1])
        self.assertEqual(records[0]["title"], "Cost / Savings")
        self.assertEqual(records[2]["title"], "Prices / Savings")
        child = analysis.nodes[0]["children"][0]
        self.assertEqual(child["title"], "Savings")
        self.assertEqual([item["utterance_start"] for item in child["occurrences"]], [0, 3])

    def test_continuous_lecture_splits_using_original_word_times(self):
        words = [Word(f"word{index}", 2000 + index * 450, 2300 + index * 450) for index in range(300)]
        transcript = Transcript(video_url="url", title="Lecture", words=words)
        segments = source_segments(transcript)
        self.assertEqual(len(segments), 3)
        self.assertEqual([item.utterance_start for item in segments], [0, 0, 0])
        second = occurrence_from_range(segments, 1, 1, "p")
        self.assertEqual(second["word_start"], 120)
        self.assertEqual(second["word_end"], 239)
        self.assertEqual(second["start"], words[120].start)
        self.assertEqual(second["end"], words[239].end)
        self.assertEqual(second["text"], " ".join(word.text for word in words[120:240]))

    def test_missing_timing_and_llm_errors_are_actionable(self):
        with patch("transcripts.navigation.request_json") as request:
            empty = analyze_navigation(Transcript(video_url="url", title="Title", transcript_text="Text"), "video", "timeline")
        request.assert_not_called()
        self.assertEqual(empty.status, AnalysisStatus.FAILED)
        self.assertIn("timed passages", empty.error)
        with patch("transcripts.navigation.request_json", side_effect=LLMError("Kimi API error 429")):
            failed = analyze_navigation(sample_transcript(), "video", "timeline")
        self.assertEqual(failed.status, AnalysisStatus.FAILED)
        self.assertIn("429", failed.error)


if __name__ == "__main__":
    unittest.main()
