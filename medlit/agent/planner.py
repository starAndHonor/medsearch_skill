"""Planner backends for the interactive shell."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from medlit.agent.config import AgentConfig


class Planner:
    def classify_user_input(self, text: str) -> dict[str, Any]:
        stripped = text.strip()
        if not stripped:
            return {"intent": "chat", "message": "我在。"}
        return {"intent": "blocked", "message": "Codex planner is not available. Please log in or configure Codex first."}

    def next_action(self, diagnostics: dict[str, Any], state_summary: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


@dataclass
class OpenAIPlanner(Planner):
    config: AgentConfig
    api_key: str

    def next_action(self, diagnostics: dict[str, Any], state_summary: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            return {"action": "stop", "reason": "OpenAI API key is not configured. Use /account or switch to external-codex."}

        prompt = {
            "role": "user",
            "content": (
                "You are the Codex-style controller for a biomedical literature CLI toolbox. "
                "Choose exactly one next action as JSON. Allowed actions are: decompose, plan-terms, "
                "validate-mesh, build-query, search-pubmed, fetch-records, localize-fulltext, "
                "parse-fulltext, extract-evidence, evolve, report, verify, diagnose, stop. "
                "Stop if diagnostics says blocked or termination_ready and report exists. "
                "Do not retry network actions when blocked is true.\n\n"
                f"Diagnostics:\n{json.dumps(diagnostics, ensure_ascii=False)}\n\n"
                f"State summary:\n{json.dumps(state_summary, ensure_ascii=False)}\n\n"
                "Return only JSON like {\"action\":\"search-pubmed\",\"args\":[\"--retmax\",\"20\"],\"reason\":\"...\"}."
            ),
        }
        payload = {
            "model": self.config.model,
            "input": [prompt],
            "text": {"verbosity": self.config.verbosity},
        }
        req = urllib.request.Request(
            f"{self.config.api_base.rstrip('/')}/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            text = self._extract_text(data)
            return self._parse_action(text)
        except Exception as exc:
            return {"action": "stop", "reason": f"OpenAI planner unavailable. {exc}"}

    def classify_user_input(self, text: str) -> dict[str, Any]:
        if not self.api_key:
            return {"intent": "blocked", "message": "OpenAI API key is not configured. Use /account or switch to external-codex."}
        payload = {
            "model": self.config.model,
            "input": [{
                "role": "user",
                "content": (
                    "Classify the user's input for a biomedical literature research terminal agent. "
                    "Return only JSON. If the user is asking for biomedical literature research, "
                    "return {\"intent\":\"research\",\"question\":\"...\"}. If it is casual chat, "
                    "weather, setup/config, or not a research task, return {\"intent\":\"chat\",\"message\":\"...\"}. "
                    f"User input: {text}"
                ),
            }],
            "text": {"verbosity": "low"},
        }
        req = urllib.request.Request(
            f"{self.config.api_base.rstrip('/')}/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            return self._parse_action(self._extract_text(data))
        except Exception:
            return {"intent": "blocked", "message": "OpenAI classifier unavailable. Configure Codex/API before continuing."}

    def _extract_text(self, data: dict[str, Any]) -> str:
        chunks = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"}:
                    chunks.append(content.get("text", ""))
        return "\n".join(chunks).strip()

    def _parse_action(self, text: str) -> dict[str, Any]:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(text[start:end + 1])
            data.setdefault("args", [])
            return data
        return {"action": "diagnose", "args": [], "reason": "Model did not return JSON."}


@dataclass
class ExternalCodexPlanner(Planner):
    config: AgentConfig
    root: Path

    def next_action(self, diagnostics: dict[str, Any], state_summary: dict[str, Any]) -> dict[str, Any]:
        codex = find_codex_executable(self.config.codex_path)
        if not codex:
            return {"action": "stop", "reason": "Codex CLI executable not found. Use /account to configure Codex.", "blocker_kind": "codex_cli_missing"}
        login = codex_login_status(codex)
        if not login.get("logged_in"):
            return {"action": "stop", "reason": "Codex is not logged in. Run /account and choose codex login.", "blocker_kind": "codex_not_logged_in"}
        prompt = (
            "You are choosing the next action for a biomedical literature CLI toolbox. "
            "You are NOT performing the research yourself. Return only one JSON object.\n\n"
            "Allowed actions: decompose, plan-terms, validate-mesh, build-query, search-pubmed, "
            "fetch-records, localize-fulltext, parse-fulltext, extract-evidence, evolve, report, "
            "verify, diagnose, stop.\n\n"
            "Rules: if diagnostics.blocked is true, return stop. If termination_ready is true and "
            "report_path exists, return stop. If a network action is suggested, keep args minimal. "
            "Do not propose repeating an action that cannot change state.\n\n"
            f"Diagnostics:\n{json.dumps(diagnostics, ensure_ascii=False)}\n\n"
            f"State summary:\n{json.dumps(state_summary, ensure_ascii=False)}\n\n"
            "Return JSON exactly like {\"action\":\"build-query\",\"args\":[],\"reason\":\"...\"}."
        )
        cmd = [codex, "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only", "-C", str(self.root)]
        if self.config.model:
            cmd.extend(["--model", self.config.model])
        cmd.append(prompt)
        try:
            completed = subprocess.run(cmd, cwd=str(self.root), stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=self.config.planner_timeout_seconds, check=False)
            text = completed.stdout.strip() or completed.stderr.strip()
            if completed.returncode != 0:
                return {"action": "stop", "reason": f"Codex CLI planner failed. {text[:300]}", "blocker_kind": classify_codex_failure(text)}
            return self._parse_action(text)
        except subprocess.TimeoutExpired:
            return {"action": "stop", "reason": f"Codex is logged in, but the planner timed out after {self.config.planner_timeout_seconds}s.", "blocker_kind": "codex_timeout"}
        except Exception as exc:
            return {"action": "stop", "reason": f"Codex CLI planner unavailable. {exc}", "blocker_kind": "codex_unavailable"}

    def classify_user_input(self, text: str) -> dict[str, Any]:
        codex = find_codex_executable(self.config.codex_path)
        if not codex:
            return {"intent": "blocked", "message": "Codex CLI executable not found. Use /account to configure Codex.", "blocker_kind": "codex_cli_missing"}
        login = codex_login_status(codex)
        if not login.get("logged_in"):
            return {"intent": "blocked", "message": "Codex is not logged in. Run /account and choose codex login.", "blocker_kind": "codex_not_logged_in"}
        prompt = (
            "Classify the user's input for a biomedical literature research terminal agent. "
            "Return only one JSON object and nothing else.\n\n"
            "If the user is asking for biomedical literature research, literature investigation, "
            "PubMed search, evidence review, paper reading, or a medical research question, return:\n"
            "{\"intent\":\"research\",\"question\":\"<the user's research question>\"}\n\n"
            "If the user is greeting, chatting, asking unrelated things like weather, or not giving "
            "a research task, return:\n"
            "{\"intent\":\"chat\",\"message\":\"<brief helpful reply>\"}\n\n"
            f"User input:\n{text}"
        )
        cmd = [codex, "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only", "-C", str(self.root)]
        if self.config.model:
            cmd.extend(["--model", self.config.model])
        cmd.append(prompt)
        try:
            completed = subprocess.run(cmd, cwd=str(self.root), stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=self.config.planner_timeout_seconds, check=False)
            text_out = completed.stdout.strip() or completed.stderr.strip()
            if completed.returncode != 0:
                return {"intent": "blocked", "message": f"Codex CLI classifier failed. {text_out[:300]}", "blocker_kind": classify_codex_failure(text_out)}
            return self._parse_action(text_out)
        except subprocess.TimeoutExpired:
            return {"intent": "uncertain", "message": f"Codex is logged in, but classification timed out after {self.config.planner_timeout_seconds}s.", "blocker_kind": "codex_timeout"}
        except Exception as exc:
            return {"intent": "blocked", "message": f"Codex CLI classifier unavailable. {exc}", "blocker_kind": "codex_unavailable"}

    def decompose_question(self, question: str) -> dict[str, Any]:
        codex = find_codex_executable(self.config.codex_path)
        if not codex:
            return {"ok": False, "message": "Codex CLI executable not found."}
        login = codex_login_status(codex)
        if not login.get("logged_in"):
            return {"ok": False, "message": "Codex is not logged in."}
        prompt = (
            "You are a biomedical research planner. Decompose the question into a precise PICO/PECO JSON object. "
            "Return only JSON with keys: framework, population, intervention_or_exposure, comparator, outcome, assumptions. "
            "Use the original language when useful, but include standard biomedical terms in English inside the field values when they help PubMed retrieval. "
            "Do not invent facts.\n\n"
            f"Question:\n{question}"
        )
        cmd = [codex, "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only", "-C", str(self.root)]
        if self.config.model:
            cmd.extend(["--model", self.config.model])
        cmd.append(prompt)
        try:
            completed = subprocess.run(cmd, cwd=str(self.root), stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=self.config.planner_timeout_seconds, check=False)
            text = completed.stdout.strip() or completed.stderr.strip()
            if completed.returncode != 0:
                return {"ok": False, "message": f"Codex PICO planner failed. {text[:300]}", "blocker_kind": classify_codex_failure(text)}
            data = self._parse_action(text)
            if "intent" in data or "action" in data:
                # _parse_action is generic; direct JSON may not be an action.
                start = text.find("{")
                end = text.rfind("}")
                data = json.loads(text[start:end + 1])
            return {"ok": True, "pico": data}
        except subprocess.TimeoutExpired:
            return {"ok": False, "message": f"Codex is logged in, but PICO planning timed out after {self.config.planner_timeout_seconds}s.", "blocker_kind": "codex_timeout"}
        except Exception as exc:
            return {"ok": False, "message": f"Codex PICO planner unavailable. {exc}", "blocker_kind": "codex_unavailable"}

    def _parse_action(self, text: str) -> dict[str, Any]:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(text[start:end + 1])
            data.setdefault("args", [])
            return data
        return {"action": "diagnose", "args": [], "reason": "Codex CLI did not return JSON."}


def find_codex_executable(configured: str = "") -> str:
    if configured and Path(configured).exists() and not configured.lower().endswith(".ps1"):
        return configured
    env_path = os.environ.get("CODEX_CLI_PATH", "")
    if env_path and Path(env_path).exists():
        return env_path
    found_cmd = shutil.which("codex.cmd") or shutil.which("codex.CMD")
    if found_cmd:
        return found_cmd
    found_exe = shutil.which("codex.exe")
    if found_exe:
        return found_exe
    home = Path.home()
    candidates = sorted(home.glob(".vscode/extensions/openai.chatgpt-*/bin/windows-x86_64/codex.exe"), reverse=True)
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    found = shutil.which("codex")
    if found and not found.lower().endswith(".ps1"):
        return found
    return ""


def codex_login_status(codex: str) -> dict[str, Any]:
    try:
        completed = subprocess.run([codex, "login", "status"], stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=10, check=False)
        text = (completed.stdout + "\n" + completed.stderr).strip()
        return {"logged_in": completed.returncode == 0 and "not logged in" not in text.lower(), "message": text, "returncode": completed.returncode}
    except Exception as exc:
        return {"logged_in": False, "message": str(exc), "returncode": -1}


def classify_codex_failure(text: str) -> str:
    lower = (text or "").lower()
    if "not logged in" in lower or "no codex credentials" in lower or "auth" in lower and "no" in lower:
        return "codex_not_logged_in"
    if "timed out" in lower or "timeout" in lower:
        return "codex_timeout"
    if "network" in lower or "certificate" in lower or "unknownissuer" in lower or "unreachable" in lower or "connect failed" in lower:
        return "codex_network_unavailable"
    return "codex_unavailable"


def quick_connectivity_probe(host: str = "chatgpt.com", port: int = 443, timeout: float = 3.0) -> dict[str, Any]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"ok": True, "message": f"{host}:{port} reachable"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
