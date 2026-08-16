from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from medlit.cli import (
    cmd_build_query,
    cmd_status,
    cmd_validate_mesh,
)
from medlit.evolution.diagnostics import Diagnoser
from medlit.pubmed.query import TermPlanner
from medlit.state.store import StateStore


QUESTION = "What is the effect of home blood pressure monitoring on hypertension?"


class CaptureConsole:
    def __init__(self):
        self.payloads = []
        self.blocked_messages = []

    def step(self, _message):
        pass

    def ok(self, _message):
        pass

    def blocked(self, message):
        self.blocked_messages.append(message)

    def json(self, payload):
        self.payloads.append(payload)


class OptionalMeshWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temp_dir.name) / "state.json"
        self.store = StateStore(self.state_path)
        state = self.store.init(QUESTION)
        state["pico"] = {
            "question": QUESTION,
            "population": QUESTION,
            "intervention_or_exposure": "",
            "comparator": "",
            "outcome": "",
        }
        state["term_plan"] = TermPlanner().plan(state["pico"])
        self.store.save(state)

    def tearDown(self):
        self.temp_dir.cleanup()

    def args(self, **values):
        return argparse.Namespace(state=str(self.state_path), **values)

    def test_default_path_skips_mesh_validation(self):
        before = Diagnoser().diagnose(self.store.load())
        self.assertEqual(before["status"], "needs_query")
        self.assertEqual(before["recommended_next_actions"], ["build-query"])

        rc = cmd_build_query(self.args(use_mesh=False), CaptureConsole())
        self.assertEqual(rc, 0)
        state = self.store.load()
        self.assertFalse(state["query_configuration"]["mesh_enabled"])
        self.assertTrue(state["query_ladder"])
        after = Diagnoser().diagnose(state)
        self.assertEqual(after["status"], "needs_pubmed_search")
        self.assertNotIn("validate-mesh", after["recommended_next_actions"])

    def test_explicit_mesh_requires_completed_validation(self):
        console = CaptureConsole()
        rc = cmd_build_query(self.args(use_mesh=True), console)
        self.assertEqual(rc, 5)
        state = self.store.load()
        self.assertTrue(state["query_configuration"]["mesh_enabled"])
        self.assertEqual(state["query_ladder"], [])
        diagnostic = Diagnoser().diagnose(state)
        self.assertEqual(diagnostic["status"], "needs_mesh_validation")
        self.assertEqual(diagnostic["recommended_next_actions"], ["validate-mesh"])

    def test_explicit_mesh_accepts_completed_zero_candidate_validation(self):
        cmd_build_query(self.args(use_mesh=True), CaptureConsole())
        with patch("medlit.cli.MeshValidator") as validator:
            validator.return_value.validate_term_plan.return_value = []
            self.assertEqual(cmd_validate_mesh(self.args(), CaptureConsole()), 0)

        state = self.store.load()
        self.assertTrue(state["mesh_validation_status"]["completed"])
        diagnostic = Diagnoser().diagnose(state)
        self.assertEqual(diagnostic["status"], "needs_query")
        self.assertEqual(
            diagnostic["recommended_next_actions"],
            ["build-query --use-mesh"],
        )
        self.assertEqual(cmd_build_query(self.args(use_mesh=True), CaptureConsole()), 0)
        state = self.store.load()
        self.assertTrue(state["query_configuration"]["mesh_enabled"])
        self.assertTrue(state["query_ladder"])

    def test_status_recomputes_instead_of_using_stale_diagnostics(self):
        cmd_build_query(self.args(use_mesh=False), CaptureConsole())
        state = self.store.load()
        state["diagnostics"] = {
            "status": "needs_mesh_validation",
            "recommended_next_actions": ["validate-mesh"],
        }
        self.store.save(state)

        console = CaptureConsole()
        self.assertEqual(cmd_status(self.args(), console), 0)
        payload = console.payloads[-1]
        self.assertEqual(payload["diagnostic_status"], "needs_pubmed_search")
        self.assertNotIn("validate-mesh", payload["next"])
        self.assertFalse(payload["mesh_enabled"])


if __name__ == "__main__":
    unittest.main()
