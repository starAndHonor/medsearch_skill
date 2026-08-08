"""One-shot Codex agent runner for the MedLit terminal entrypoint."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from dataclasses import dataclass
import json
from pathlib import Path

from medlit.agent.config import AgentConfig
from medlit.agent.planner import codex_login_status, find_codex_executable


@dataclass
class CodexRunResult:
    ok: bool
    returncode: int
    message: str
    blocker_kind: str = ""
    log_path: str = ""
    final_message_path: str = ""


class CodexResearchRunner:
    """Delegate a research task to Codex once, with the CLI toolbox as tools."""

    def __init__(self, config: AgentConfig, root: Path):
        self.config = config
        self.root = root

    def run(self, question: str) -> CodexRunResult:
        codex = find_codex_executable(self.config.codex_path)
        if not codex:
            return CodexRunResult(False, 127, "未找到 Codex CLI。", "codex_cli_missing")
        login = codex_login_status(codex)
        if not login.get("logged_in"):
            return CodexRunResult(False, 1, f"Codex 未登录：{login.get('message')}", "codex_not_logged_in")

        prompt = self._prompt(question)
        cmd = self._build_command(codex)
        log_path, final_path = self._run_paths()
        process: subprocess.Popen[str] | None = None
        try:
            log_lines: list[str] = []
            log_path.parent.mkdir(parents=True, exist_ok=True)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            process = subprocess.Popen(
                cmd,
                cwd=str(self.root),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            reader = threading.Thread(target=self._consume_output, args=(process, log_path, log_lines), daemon=True)
            reader.start()
            if process.stdin is not None:
                try:
                    process.stdin.write(prompt)
                    process.stdin.close()
                except BrokenPipeError:
                    pass
            start = time.monotonic()
            next_heartbeat = start + 15
            while process.poll() is None:
                elapsed = int(time.monotonic() - start)
                if elapsed >= self.config.agent_timeout_seconds:
                    process.kill()
                    return CodexRunResult(
                        False,
                        124,
                        f"Codex 研究 run 超过 {self.config.agent_timeout_seconds}s 未完成，已停止以避免继续消耗额度。日志：{log_path}",
                        "codex_timeout",
                        str(log_path),
                        str(final_path),
                    )
                if time.monotonic() >= next_heartbeat:
                    print(f"[..] Codex agent 仍在工作，已等待 {elapsed}s。原始日志写入：{log_path}")
                    next_heartbeat += 15
                time.sleep(0.25)
            reader.join(timeout=5)
        except KeyboardInterrupt:
            if process is not None:
                try:
                    process.kill()
                except Exception:
                    pass
            return CodexRunResult(False, 130, f"用户中断了 Codex 研究 run。日志：{log_path}", "interrupted", str(log_path), str(final_path))
        except Exception as exc:
            return CodexRunResult(False, 1, f"Codex 研究 run 启动失败：{exc}", "codex_unavailable")

        output = "".join(log_lines)
        final_message = self._read_final_message(final_path)
        if "windows sandbox: helper_unknown_error" in output:
            return CodexRunResult(
                False,
                process.returncode if process else -1,
                f"Codex 已连接，但本地 Windows sandbox helper 无法启动命令。请先运行 /sandbox 自检并按提示修复。日志：{log_path}",
                "codex_sandbox_unavailable",
                str(log_path),
                str(final_path),
            )
        if self._looks_blocked(final_message):
            return CodexRunResult(
                False,
                process.returncode if process else 1,
                f"{final_message}\n\n日志：{log_path}",
                "codex_reported_blocker",
                str(log_path),
                str(final_path),
            )
        if process and process.returncode == 0:
            if self._looks_no_work(final_message):
                return CodexRunResult(
                    False,
                    0,
                    f"Codex agent 已连接并正常退出，但没有执行 MedLit 研究工具，也没有推进状态。"
                    f"这通常表示任务提示没有被 Codex 正确接收，或 Codex 过早结束。日志：{log_path}",
                    "codex_no_work",
                    str(log_path),
                    str(final_path),
                )
            return CodexRunResult(True, 0, final_message or f"Codex 研究 run 已结束。日志：{log_path}", "", str(log_path), str(final_path))
        return CodexRunResult(False, process.returncode if process else 1, f"Codex 研究 run 退出码：{process.returncode if process else 'unknown'}。日志：{log_path}", "codex_unavailable", str(log_path), str(final_path))

    def _build_command(self, codex: str) -> list[str]:
        cmd = [
            codex,
            "-a",
            self._codex_approval_policy(),
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            self._sandbox_mode(),
            "-C",
            str(self.root),
            "--color",
            "never",
            "--output-last-message",
            str(self._run_paths()[1]),
            "-",
        ]
        if self.config.model:
            prompt_arg = cmd.pop()
            cmd.extend(["--model", self.config.model, prompt_arg])
        return cmd

    def _sandbox_mode(self) -> str:
        allowed = {"read-only", "workspace-write", "danger-full-access"}
        return self.config.codex_sandbox_mode if self.config.codex_sandbox_mode in allowed else "workspace-write"

    def _codex_approval_policy(self) -> str:
        if self.config.approval_mode == "never":
            return "never"
        return "on-request"

    def _run_paths(self) -> tuple[Path, Path]:
        state_dir = (self.root / self.config.state_path).parent
        return state_dir / "codex_run.log", state_dir / "codex_final.md"

    def _consume_output(self, process: subprocess.Popen[str], log_path: Path, log_lines: list[str]) -> None:
        with log_path.open("w", encoding="utf-8", errors="replace") as handle:
            if process.stdout is None:
                return
            for line in process.stdout:
                log_lines.append(line)
                handle.write(line)
                handle.flush()

    def _read_final_message(self, path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="replace").strip()

    def _looks_blocked(self, text: str) -> bool:
        markers = ["精确阻塞", "未能生成报告", "无法继续", "blocked", "BLOCKED"]
        return any(marker in text for marker in markers)

    def _looks_no_work(self, final_message: str) -> bool:
        state_path = self.root / self.config.state_path
        if not state_path.exists():
            return True
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            return False
        has_progress = any(
            [
                bool(state.get("pico")),
                bool(state.get("records")),
                bool(state.get("fulltexts")),
                bool(state.get("parsed_sources")),
                bool(state.get("evidence")),
                bool(state.get("report_path")),
            ]
        )
        if has_progress:
            return False
        lowered = final_message.lower()
        ack_markers = ["understood", "working context", "收到", "明白", "好的"]
        return not final_message.strip() or any(marker in lowered for marker in ack_markers)

    def _prompt(self, question: str) -> str:
        py = Path(sys.executable).as_posix()
        state = self.config.state_path.replace("\\", "/")
        return f"""
You are Codex running the MedLit CLI skill as the agent core.

User biomedical literature question:
{question}

Hard requirements:
- Do not answer from memory. Use the local CLI toolbox and the shared JSON state.
- Do not use MCP. Do not use a local heuristic PICO decomposition.
- You own the workflow: inspect state, choose tools, retry only when useful, degrade honestly, and stop when done or blocked.
- Before any costly retry, run diagnose and obey blocked/termination_ready.
- Do not bypass paywalls. Open-access full text, PubMed/PMC metadata, and abstract fallback are allowed.
- Keep work bounded. If infrastructure/network/dependency blockers repeat, stop and explain the blocker instead of looping.

Important files:
- SKILL.md
- references/termination_policy.md
- references/fulltext_download_policy.md
- state file: {state}

Available commands:
1. Check current state first:
   "{py}" scripts/medlit_cli.py --state {state} status
   "{py}" scripts/medlit_cli.py --state {state} diagnose
2. Initialize only if status says no_state:
   "{py}" scripts/medlit_cli.py --state {state} init --question "<question>"
3. PICO:
   Create a small UTF-8 JSON file under workspace/latest/, then run:
   "{py}" scripts/medlit_cli.py --state {state} decompose --pico-file workspace/latest/pico.json
4. Retrieval and evidence tools:
   "{py}" scripts/medlit_cli.py --state {state} plan-terms
   "{py}" scripts/medlit_cli.py --state {state} validate-mesh
   "{py}" scripts/medlit_cli.py --state {state} build-query
   "{py}" scripts/medlit_cli.py --state {state} search-pubmed --retmax 20
   "{py}" scripts/medlit_cli.py --state {state} fetch-records
   "{py}" scripts/medlit_cli.py --state {state} localize-fulltext
   "{py}" scripts/medlit_cli.py --state {state} parse-fulltext
   "{py}" scripts/medlit_cli.py --state {state} extract-evidence
   "{py}" scripts/medlit_cli.py --state {state} evolve
   "{py}" scripts/medlit_cli.py --state {state} report
   "{py}" scripts/medlit_cli.py --state {state} verify

Run the research task now. Show concise progress in Chinese. Finish with the report path if generated, or the exact blocker if not.
""".strip()
