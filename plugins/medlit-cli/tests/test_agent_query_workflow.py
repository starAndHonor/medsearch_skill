from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from medlit.cli import cmd_accept_query, cmd_search_pubmed, cmd_status
from medlit.evolution.diagnostics import Diagnoser
from medlit.state.store import SCHEMA_VERSION, StateStore


QUESTION = "Which disease is caused by heterozygous UCHL1 loss-of-function variants?"


class CaptureConsole:
    def __init__(self):
        self.payloads = []
        self.blocked_messages = []
        self.failed_messages = []

    def step(self, _message):
        pass

    def ok(self, _message):
        pass

    def blocked(self, message):
        self.blocked_messages.append(message)

    def fail(self, message):
        self.failed_messages.append(message)

    def warn(self, _message):
        pass

    def json(self, payload):
        self.payloads.append(payload)


class AgentQueryWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.state_path = self.root / "state.json"
        self.store = StateStore(self.state_path)
        self.store.init(QUESTION)

    def tearDown(self):
        self.temp_dir.cleanup()

    def args(self, **values):
        return argparse.Namespace(state=str(self.state_path), **values)

    def write_query(self, attempt_id: str, query: str) -> Path:
        path = self.root / f"{attempt_id}.json"
        path.write_text(json.dumps({
            "attempt_id": attempt_id,
            "exact_query": query,
            "reasoning": "Agent-authored test query.",
            "added_terms": [],
        }), encoding="utf-8")
        return path

    def search_result(self, pmids=None):
        pmids = ["22", "11"] if pmids is None else pmids
        return {
            "count": len(pmids),
            "pmids": pmids,
            "effective_query": "effective",
            "query_translation": "translated",
            "translationset": [],
            "warninglist": {},
            "errorlist": {},
            "retmax": 100,
            "sort": "relevance",
        }

    def test_initial_state_requires_agent_authored_query(self):
        state = self.store.load()
        self.assertEqual(state["schema_version"], SCHEMA_VERSION)
        diagnostic = Diagnoser().diagnose(state)
        self.assertEqual(diagnostic["status"], "needs_pubmed_query")
        self.assertEqual(
            diagnostic["recommended_next_actions"],
            ["author_and_run_pubmed_query"],
        )

    def test_search_records_attempt_and_feedback_without_accepting(self):
        query_file = self.write_query(
            "q1",
            "UCHL1[Title/Abstract] AND heterozygous[Title/Abstract]",
        )
        feedback = [{"pmid": "22", "title": "Relevant title", "abstract": "Text"}]
        with patch("medlit.cli.PubMedClient") as client_class:
            client = client_class.return_value
            client.search.return_value = self.search_result()
            client.fetch_records.return_value = feedback
            rc = cmd_search_pubmed(
                self.args(
                    query_file=str(query_file),
                    retmax=100,
                    max_date="",
                    feedback_records=1,
                ),
                CaptureConsole(),
            )

        self.assertEqual(rc, 0)
        state = self.store.load()
        self.assertEqual(len(state["query_attempts"]), 1)
        self.assertEqual(state["query_attempts"][0]["feedback_records"], feedback)
        self.assertEqual(state["last_pmids"], ["22", "11"])
        self.assertEqual(state["final_ranked_pmids"], [])
        self.assertEqual(
            Diagnoser().diagnose(state)["status"],
            "needs_query_decision",
        )

    def test_zero_result_is_saved_as_feedback(self):
        query_file = self.write_query("q1", "UCHL1[Title/Abstract]")
        with patch("medlit.cli.PubMedClient") as client_class:
            client = client_class.return_value
            client.search.return_value = self.search_result([])
            rc = cmd_search_pubmed(
                self.args(
                    query_file=str(query_file),
                    retmax=100,
                    max_date="",
                    feedback_records=10,
                ),
                CaptureConsole(),
            )

        self.assertEqual(rc, 0)
        self.assertEqual(self.store.load()["query_attempts"][0]["pmids"], [])

    def test_accept_query_replaces_ranking_and_clears_downstream(self):
        state = self.store.load()
        state["query_attempts"] = [
            {"attempt_id": "q1", "exact_query": "first", "pmids": ["1"]},
            {"attempt_id": "q2", "exact_query": "second", "pmids": ["2", "3"]},
        ]
        state["accepted_query_attempt_id"] = "q1"
        state["final_ranked_pmids"] = ["1"]
        state["records"] = [{"pmid": "1"}]
        state["evidence"] = [{"paper_ref": "1"}]
        state["report_path"] = "report.md"
        self.store.save(state)

        rc = cmd_accept_query(self.args(attempt_id="q2"), CaptureConsole())

        self.assertEqual(rc, 0)
        state = self.store.load()
        self.assertEqual(state["accepted_query_attempt_id"], "q2")
        self.assertEqual(state["final_ranked_pmids"], ["2", "3"])
        self.assertEqual(state["records"], [])
        self.assertEqual(state["evidence"], [])
        self.assertEqual(state["report_path"], "")
        self.assertEqual(Diagnoser().diagnose(state)["status"], "needs_records")

    def test_accept_query_is_idempotent(self):
        state = self.store.load()
        state["query_attempts"] = [
            {"attempt_id": "q1", "exact_query": "query", "pmids": ["1"]}
        ]
        state["accepted_query_attempt_id"] = "q1"
        state["final_ranked_pmids"] = ["1"]
        state["records"] = [{"pmid": "1"}]
        self.store.save(state)

        rc = cmd_accept_query(self.args(attempt_id="q1"), CaptureConsole())

        self.assertEqual(rc, 0)
        self.assertEqual(self.store.load()["records"], [{"pmid": "1"}])

    def test_status_reports_attempt_and_accepted_query(self):
        state = self.store.load()
        state["query_attempts"] = [
            {"attempt_id": "q1", "exact_query": "query", "pmids": ["1"]}
        ]
        state["accepted_query_attempt_id"] = "q1"
        state["final_ranked_pmids"] = ["1"]
        self.store.save(state)

        console = CaptureConsole()
        self.assertEqual(cmd_status(self.args(), console), 0)
        payload = console.payloads[-1]
        self.assertEqual(payload["query_attempts"], 1)
        self.assertEqual(payload["accepted_query_attempt_id"], "q1")
        self.assertEqual(payload["diagnostic_status"], "needs_records")


if __name__ == "__main__":
    unittest.main()
