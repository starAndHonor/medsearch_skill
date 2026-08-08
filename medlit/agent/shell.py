"""Interactive terminal shell for MedLit."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from getpass import getpass
from pathlib import Path
from typing import Any

from medlit.agent.approval import ApprovalPolicy
from medlit.agent.config import AgentConfig
from medlit.agent.codex_runner import CodexResearchRunner
from medlit.agent.planner import ExternalCodexPlanner, OpenAIPlanner, Planner, codex_login_status, find_codex_executable, quick_connectivity_probe
from medlit.agent.tools import ToolRunner
from medlit.state.store import StateStore


ROOT = Path(__file__).resolve().parents[2]


class AgentShell:
    def __init__(self):
        self.config = AgentConfig.load()
        self.session_api_key = ""
        detected_codex = find_codex_executable(self.config.codex_path)
        if detected_codex and self.config.backend == "openai-api" and not self.config.api_key():
            self.config.backend = "external-codex"
            self.config.codex_path = detected_codex
        self.runner = ToolRunner(ROOT, self.config.state_path)

    def run(self) -> int:
        self._banner()
        while True:
            try:
                text = input("\nmedlit> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[bye]")
                return 0
            if not text:
                continue
            if text in {"/exit", "/quit", "exit", "quit"}:
                print("[bye]")
                return 0
            self._handle(text)

    def _handle(self, text: str) -> None:
        if text == "/help":
            self._help()
        elif text in {"/config", "/api", "/login", "/account"}:
            self._configure_account()
        elif text == "/status":
            self._print_status()
        elif text == "/doctor":
            self._doctor()
        elif text == "/sandbox":
            self._sandbox_check()
        elif text == "/reconnect":
            self._reconnect()
        elif text.startswith("/debug"):
            self._debug(text)
        elif text == "/step":
            self._agent_step()
        elif text.startswith("/auto"):
            parts = text.split()
            limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else self.config.max_agent_steps
            self._auto(limit)
        elif text.startswith("/run "):
            self._start_question(text[5:].strip())
            self._codex_agent_run(text[5:].strip())
        else:
            self._handle_free_text(text)

    def _start_question(self, question: str) -> None:
        if not question:
            print("[!!] empty question")
            return
        result = self.runner.run("init", ["--question", question])
        self._show(result)

    def _auto(self, limit: int) -> None:
        for idx in range(limit):
            print(f"\n[..] agent step {idx + 1}/{limit}")
            stop = self._agent_step()
            if stop:
                return
        print("[!!] step budget reached; run /status or /auto N if you want to continue")

    def _agent_step(self) -> bool:
        diag_result = self.runner.run("diagnose")
        diagnostics = diag_result.json_payload() or {}
        self._show_diagnostics(diagnostics)
        if diagnostics.get("blocked"):
            print("[BLOCKED] 我先停下，避免在无法解决的问题上继续消耗额度。")
            return True
        state_summary = self._state_summary()
        planner = self._planner()
        action = planner.next_action(diagnostics, state_summary)
        next_action = action.get("action", "diagnose")
        if next_action == "stop":
            if action.get("blocker_kind"):
                self._show_codex_blocker({"message": action.get("reason"), "blocker_kind": action.get("blocker_kind")})
            else:
                print(f"[OK] stopped: {action.get('reason', 'done')}")
            return True
        if not ApprovalPolicy(self.config.approval_mode).ask(next_action):
            print("[!!] action skipped by approval policy")
            return True
        if next_action == "decompose":
            self._codex_decompose()
        else:
            result = self.runner.run(next_action, list(action.get("args") or []))
            self._show(result)
        if next_action in {"report", "verify"}:
            return False
        return False

    def _planner(self) -> Planner:
        if self.config.backend == "external-codex":
            return ExternalCodexPlanner(self.config, ROOT)
        if self.config.backend == "openai-api":
            return OpenAIPlanner(self.config, self.config.api_key(self.session_api_key))
        return ExternalCodexPlanner(self.config, ROOT)

    def _handle_free_text(self, text: str) -> None:
        if self.config.backend != "external-codex":
            decision = self._planner().classify_user_input(text)
            if decision.get("intent") == "research":
                question = decision.get("question") or text
                self._start_question(question)
                self._auto(self.config.max_agent_steps)
                return
            if decision.get("intent") == "blocked":
                self._show_codex_blocker(decision)
                return
            print(decision.get("message") or "我在。给我一个医学文献调研任务，我会开始工作。")
            return

        self._start_question(text)
        self._codex_agent_run(text)

    def _codex_agent_run(self, question: str) -> None:
        if not question:
            print("[!!] empty question")
            return
        if self.config.approval_mode in {"on-network", "on-step"}:
            sandbox_note = f"当前 Codex sandbox={self.config.codex_sandbox_mode}。"
            if self.config.codex_sandbox_mode == "danger-full-access":
                sandbox_note += "这是全权限模式，只应在你明确接受本地执行风险时使用。"
            print(f"[APPROVE] 本次 Codex 研究 run 会写入项目 workspace，并可能访问 PubMed/PMC/开放全文来源。{sandbox_note}")
            if input("允许启动 Codex agent？[y/N] ").strip().lower() not in {"y", "yes"}:
                print("[!!] 已取消。")
                return
        print("[..] 正在把任务交给 Codex agent。后续由 Codex 自行读取状态、调用本地工具并判断何时停止。")
        print("[..] 为了保持控制台清爽，Codex 原始输出会写入 workspace/latest/codex_run.log。")
        print(f"[..] 最长等待 {self.config.agent_timeout_seconds}s；如果代理很慢，可以先等它完成，必要时 Ctrl+C 中断。")
        result = CodexResearchRunner(self.config, ROOT).run(question)
        if result.ok:
            print("[OK] Codex agent run 结束。")
            if result.message:
                print(result.message)
            self._print_status()
            return
        self._record_agent_blocker(result.blocker_kind, result.message)
        self._show_codex_blocker({"message": result.message, "blocker_kind": result.blocker_kind})

    def _record_agent_blocker(self, kind: str, message: str) -> None:
        path = ROOT / self.config.state_path
        if not path.exists():
            return
        store = StateStore(path)
        state = store.load()
        state.setdefault("blockers", []).append({
            "kind": kind or "codex_unavailable",
            "stage": "codex-agent-run",
            "message": message,
            "advice": self._blocker_advice(kind),
        })
        state["status"] = "blocked"
        store.save(state)

    def _codex_decompose(self) -> None:
        path = ROOT / self.config.state_path
        if not path.exists():
            print("[BLOCKED] 还没有研究状态，无法拆解问题。")
            return
        store = StateStore(path)
        state = store.load()
        planner = self._planner()
        if not isinstance(planner, ExternalCodexPlanner):
            print("[BLOCKED] PICO 拆解必须由 Codex 完成。请在 /account 中选择 external-codex 并登录。")
            return
        result = planner.decompose_question(state.get("question", ""))
        if not result.get("ok"):
            kind = result.get("blocker_kind", "codex_unavailable")
            state.setdefault("blockers", []).append({
                "kind": kind,
                "stage": "decompose",
                "message": result.get("message", "Codex PICO planner failed."),
                "advice": self._blocker_advice(kind),
            })
            store.save(state)
            self._show_codex_blocker({"message": result.get("message"), "blocker_kind": kind})
            return
        state["pico"] = result["pico"]
        store.save(state)
        pico = result["pico"]
        bits = [pico.get("population"), pico.get("intervention_or_exposure"), pico.get("outcome")]
        print("[OK] Codex 已完成医学问题拆解：" + "；".join(str(b) for b in bits if b))

    def _state_summary(self) -> dict[str, Any]:
        path = ROOT / self.config.state_path
        if not path.exists():
            return {}
        state = json.loads(path.read_text(encoding="utf-8"))
        return {
            "status": state.get("status"),
            "records": len(state.get("records", [])),
            "evidence": len(state.get("evidence", [])),
            "blockers": state.get("blockers", [])[-3:],
            "last_pmids": state.get("last_pmids", []),
            "report_path": state.get("report_path", ""),
        }

    def _configure(self) -> None:
        self._configure_account()

    def _configure_account(self) -> None:
        print("\nCurrent config:")
        safe = dict(self.config.__dict__)
        safe["api_key"] = "set" if self.config.api_key(self.session_api_key) else "not set"
        safe["detected_codex"] = find_codex_executable(self.config.codex_path) or "not found"
        if safe["detected_codex"] != "not found":
            safe["codex_login"] = codex_login_status(safe["detected_codex"])
        print(json.dumps(safe, ensure_ascii=False, indent=2))
        print("\nAccount / model setup")
        print("- ChatGPT account login is used through the external Codex CLI, not through an API key.")
        print("- API key mode is optional for users who have OPENAI_API_KEY.")
        print("- Session API keys are kept in memory only and are not written to disk.")
        backend = input("Backend [external-codex/openai-api] (blank keep): ").strip()
        if backend:
            if backend == "external-codex" and not shutil.which("codex"):
                detected = find_codex_executable(self.config.codex_path)
                if detected:
                    self.config.codex_path = detected
                    print(f"[OK] detected Codex CLI: {detected}")
                else:
                    print("[!!] Codex CLI not found; workflow will be blocked until Codex is configured")
            self.config.backend = backend
        model_label = self.config.model or "<Codex default>"
        model = input(f"Model (blank keep {model_label}): ").strip()
        if model:
            self.config.model = model
        if self.config.backend == "external-codex":
            detected = find_codex_executable(self.config.codex_path)
            if detected:
                self.config.codex_path = detected
            codex_path = input(f"Codex path (blank keep {self.config.codex_path or '<auto>'}): ").strip()
            if codex_path:
                self.config.codex_path = codex_path
            if input("Run `codex login` now? [y/N] ").strip().lower() in {"y", "yes"}:
                self._codex_login()
            timeout = input(f"Codex agent timeout seconds (blank keep {self.config.agent_timeout_seconds}): ").strip()
            if timeout.isdigit():
                self.config.agent_timeout_seconds = int(timeout)
            sandbox = input(f"Codex sandbox [danger-full-access/workspace-write/read-only] (blank keep {self.config.codex_sandbox_mode}): ").strip()
            if sandbox:
                self.config.codex_sandbox_mode = sandbox
        if self.config.backend == "openai-api":
            api_base = input(f"API base (blank keep {self.config.api_base}): ").strip()
            if api_base:
                self.config.api_base = api_base
            if input("Set/replace session API key now? [y/N] ").strip().lower() in {"y", "yes"}:
                try:
                    self.session_api_key = getpass("OpenAI API key: ").strip()
                except Exception:
                    self.session_api_key = input("OpenAI API key: ").strip()
                print("[OK] session API key set in memory only" if self.session_api_key else "[OK] no session key set")
        approval = input(f"Approval mode [never/on-network/on-step] (blank keep {self.config.approval_mode}): ").strip()
        if approval:
            self.config.approval_mode = approval
        state_path = input(f"State path (blank keep {self.config.state_path}): ").strip()
        if state_path:
            self.config.state_path = state_path
            self.runner = ToolRunner(ROOT, self.config.state_path)
        self.config.save()
        print("[OK] config saved without secrets")

    def _login(self) -> None:
        self._configure_account()

    def _codex_login(self) -> None:
        codex = find_codex_executable(self.config.codex_path)
        if not codex:
            print("[!!] Codex CLI executable not found. Install/open the ChatGPT/Codex extension first.")
            return
        import subprocess
        print("[..] launching Codex login. Follow the browser/account flow if prompted.")
        try:
            completed = subprocess.run([codex, "login"], cwd=str(ROOT), text=True, encoding="utf-8", errors="replace", check=False)
        except KeyboardInterrupt:
            print("\n[!!] Codex 登录已取消。")
            return
        print("[OK] codex login command finished" if completed.returncode == 0 else f"[!!] codex login exited with code {completed.returncode}")

    def _print_tool(self, action: str) -> None:
        self._show(self.runner.run(action))

    def _show(self, result) -> None:
        if self.config.debug_json:
            if result.stderr:
                print(result.stderr)
            if result.stdout:
                print(result.stdout)
            return
        self._summarize_tool(result)

    def _show_raw(self, result) -> None:
        if result.stderr:
            print(result.stderr)
        if result.stdout:
            print(result.stdout)
        if result.returncode not in {0, 1, 5, 7, 8, 9}:
            print(f"[!!] tool returned code {result.returncode}")

    def _summarize_tool(self, result) -> None:
        payload = result.json_payload()
        action = result.action
        if action == "init" and isinstance(payload, dict):
            print(f"[OK] 已创建研究任务：{payload.get('question', '')}")
            return
        if action == "decompose" and isinstance(payload, dict):
            bits = [payload.get("population"), payload.get("intervention_or_exposure"), payload.get("outcome")]
            print("[OK] 我把问题拆成了可检索的医学要素：" + "；".join(b for b in bits if b))
            return
        if action == "plan-terms" and isinstance(payload, dict):
            n = len(payload.get("concepts", []))
            print(f"[OK] 我规划了 {n} 组检索概念。")
            return
        if action == "validate-mesh" and isinstance(payload, list):
            valid = sum(1 for x in payload if x.get("status") in {"valid", "entry_term"})
            fallback = len(payload) - valid
            print(f"[OK] MeSH 校验完成：{valid} 个可用，{fallback} 个降级为标题/摘要词。")
            return
        if action == "build-query" and isinstance(payload, list):
            print(f"[OK] 我生成了 {len(payload)} 个 PubMed 检索式候选。")
            return
        if action == "search-pubmed" and isinstance(payload, dict):
            print(f"[OK] PubMed 检索完成：返回 {len(payload.get('pmids', []))} 个 PMID，总命中 {payload.get('count', 0)}。")
            return
        if action == "fetch-records" and isinstance(payload, list):
            print(f"[OK] 我抓取了 {len(payload)} 条 PubMed 文献记录。")
            return
        if action == "localize-fulltext" and isinstance(payload, list):
            got = sum(1 for x in payload if str(x.get("fulltext_status", "")).endswith("downloaded"))
            abstract = sum(1 for x in payload if x.get("fulltext_status") == "abstract_only")
            print(f"[OK] 全文本地化完成：{got} 篇拿到全文，{abstract} 篇降级为摘要。")
            return
        if action == "parse-fulltext" and isinstance(payload, list):
            ok = sum(1 for x in payload if x.get("status") == "parsed")
            print(f"[OK] 我解析了 {ok}/{len(payload)} 个本地来源。")
            return
        if action == "extract-evidence" and isinstance(payload, list):
            ok = sum(1 for x in payload if x.get("extraction_status") == "ok")
            print(f"[OK] 我抽取了 {ok}/{len(payload)} 条结构化证据。")
            return
        if action == "report" and isinstance(payload, dict):
            print(f"[OK] 报告已生成：{payload.get('report_path')}")
            return
        if action == "verify" and isinstance(payload, dict):
            print("[OK] 引用校验通过。" if payload.get("ok") else "[!!] 引用校验发现问题，请用 /debug on 查看细节。")
            return
        if action == "status" and isinstance(payload, dict):
            self._show_status_payload(payload)
            return
        if result.returncode in {7, 8}:
            print("[BLOCKED] 工具报告了阻塞。用 /status 查看摘要，/debug on 查看细节。")
            return
        if result.returncode != 0:
            print(f"[!!] {action} 没有成功完成。用 /debug on 查看原始输出。")
            return
        print(f"[OK] {action} 完成。")

    def _show_diagnostics(self, diagnostics: dict[str, Any]) -> None:
        status = diagnostics.get("status", "unknown")
        metrics = diagnostics.get("metrics", {})
        if diagnostics.get("blocked"):
            print(f"[BLOCKED] 当前无法继续：{diagnostics.get('reason') or status}")
            return
        if diagnostics.get("termination_ready"):
            print(f"[OK] 当前状态可以收尾：{status}")
            return
        next_actions = ", ".join(diagnostics.get("recommended_next_actions", []))
        print(
            f"[..] 我检查了进度：{status}。"
            f" 已有文献 {metrics.get('records', 0)} 篇，证据 {metrics.get('evidence_items', 0)} 条。"
            f" 下一步：{next_actions or '继续诊断'}。"
        )

    def _print_status(self) -> None:
        if self.config.backend == "external-codex":
            codex = find_codex_executable(self.config.codex_path)
            login = codex_login_status(codex) if codex else {"logged_in": False, "message": "Codex CLI not found"}
            print(f"[..] Codex CLI：{'已检测到' if codex else '未找到'}；登录：{'已登录' if login.get('logged_in') else '未登录'}；sandbox：{self.config.codex_sandbox_mode}")
            if not login.get("logged_in"):
                print(f"[!!] {login.get('message')}")
        result = self.runner.run("status")
        payload = result.json_payload()
        if isinstance(payload, dict):
            self._show_status_payload(payload)
        else:
            self._show(result)

    def _show_status_payload(self, payload: dict[str, Any]) -> None:
        if payload.get("status") == "no_state":
            print("[..] 还没有研究任务。直接输入一个医学调研问题即可开始。")
            return
        print(
            f"[..] 状态：{payload.get('status')} / {payload.get('diagnostic_status')}；"
            f"文献 {payload.get('records', 0)} 篇；证据 {payload.get('evidence', 0)} 条；"
            f"阻塞 {payload.get('blockers', 0)} 个。"
        )
        if payload.get("report_path"):
            print(f"[OK] 报告：{payload.get('report_path')}")

    def _debug(self, text: str) -> None:
        parts = text.split()
        if len(parts) == 1:
            print(f"[..] debug_json is {'on' if self.config.debug_json else 'off'}")
            return
        value = parts[1].lower()
        self.config.debug_json = value in {"on", "true", "1", "yes"}
        self.config.save()
        print(f"[OK] debug_json {'on' if self.config.debug_json else 'off'}")

    def _banner(self) -> None:
        print("MedLit CLI Agent")
        codex = find_codex_executable(self.config.codex_path)
        if self.config.backend == "external-codex":
            if codex:
                login = codex_login_status(codex)
                print("[OK] Codex CLI detected: " + codex)
                print("[OK] Codex login: logged in" if login.get("logged_in") else f"[!!] Codex login: not logged in ({login.get('message')})")
                print("[..] Connectivity: use /doctor for Codex's real proxy-aware check.")
            else:
                print("[!!] Codex CLI not found. Use /account to configure.")
        elif self.config.backend == "openai-api" and not self.config.api_key(self.session_api_key):
            print("[!!] OpenAI API key 未配置。你也可以用 /account 切换到 external-codex，使用 ChatGPT 账号登录的 Codex。")
        model_label = self.config.model or "<Codex default>"
        print(f"Model: {model_label} | Backend: {self.config.backend} | Approval: {self.config.approval_mode}")
        if self.config.backend == "external-codex":
            print(f"Codex sandbox: {self.config.codex_sandbox_mode}")
        print("Type a medical research question, or /help. Use /account for Codex login/model settings.")
        print("The reusable skill remains in SKILL.md + scripts/; this shell is only the project entrypoint.")

    def _help(self) -> None:
        print(
            """
Commands:
  <question>       Start a new research run and let the agent proceed.
  /run <question>  Same as above.
  /step            Developer tool: run one legacy diagnose -> action step.
  /auto [N]        Developer tool: run up to N legacy tool steps.
  /status          Show concise state status.
  /doctor          Run Codex doctor and show auth/network diagnostics.
  /sandbox         Test Codex's local Windows sandbox command execution.
  /reconnect       Re-check Codex login and network status.
  /config          Configure backend, model, approval mode, state path.
  /account         Configure ChatGPT-account Codex CLI or API mode.
  /api, /login     Alias for /account.
  /debug on/off    Show or hide raw tool JSON.
  /exit            Quit.

Backends:
  external-codex   Uses your logged-in Codex CLI / ChatGPT account.
  openai-api       Uses OpenAI Responses API if you have OPENAI_API_KEY.

Default mode:
  In external-codex mode, free-text questions start one Codex agent run.
  Codex owns the workflow and calls the local CLI toolbox itself.
"""
        )

    def _show_codex_blocker(self, info: dict[str, Any]) -> None:
        kind = info.get("blocker_kind", "codex_unavailable")
        message = info.get("message", "")
        print(f"[BLOCKED] {message}")
        print(self._blocker_advice(kind))

    def _blocker_advice(self, kind: str) -> str:
        if kind == "codex_not_logged_in":
            return "Codex CLI 已检测到，但尚未登录。请运行 /account 并执行 Codex 登录。"
        if kind == "codex_timeout":
            return "Codex 已登录，但本次响应超时。代理环境下可能只是慢；请运行 /doctor 确认连通性，必要时在 /account 增大 agent timeout 后重试。"
        if kind == "codex_no_work":
            return "Codex 子进程没有报网络或登录错误，但没有调用任何 MedLit 工具。请先看 workspace/latest/codex_run.log；如果只看到很短的确认语，说明 prompt 传递或 agent 启动参数仍有问题。"
        if kind == "codex_network_unavailable":
            return "Codex 登录凭证可能没问题，但网络/证书/代理不可用。请运行 /doctor 查看具体原因。"
        if kind == "codex_cli_missing":
            return "未找到 Codex CLI。请打开 ChatGPT/Codex 扩展或在 /account 中配置路径。"
        if kind == "codex_sandbox_unavailable":
            return "这是 Codex 子进程的 Windows sandbox 层故障，不是 MedLit 工具故障。请运行 /sandbox 查看最小复现和修复建议；修好前我不会自动绕过沙箱。"
        if kind == "interrupted":
            return "任务已被用户中断。状态已保留，确认环境后可以重新输入问题或继续用开发工具检查 state。"
        return "请运行 /doctor 查看 Codex 诊断；问题解决后再用 /step 继续。"

    def _reconnect(self) -> None:
        codex = find_codex_executable(self.config.codex_path)
        login = codex_login_status(codex) if codex else {"logged_in": False, "message": "Codex CLI not found"}
        probe = quick_connectivity_probe()
        print(f"[..] Codex CLI：{'已检测到' if codex else '未找到'}")
        print(f"[..] 登录状态：{'已登录' if login.get('logged_in') else '未登录'}")
        if not login.get("logged_in"):
            print(f"[!!] {login.get('message')}")
        print(f"[..] 直连探针：{'可达' if probe.get('ok') else '不可达'}")
        if not probe.get("ok"):
            print(f"[!!] {probe.get('message')}；代理环境下请以 /doctor 的 websocket/reachability 为准。")

    def _doctor(self) -> None:
        codex = find_codex_executable(self.config.codex_path)
        if not codex:
            print("[BLOCKED] Codex CLI not found.")
            return
        print("[..] running codex doctor...")
        completed = subprocess.run([codex, "doctor"], cwd=str(ROOT), stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=60, check=False)
        print((completed.stdout or completed.stderr).strip())

    def _sandbox_check(self) -> None:
        codex = find_codex_executable(self.config.codex_path)
        if not codex:
            print("[BLOCKED] 未找到 Codex CLI。")
            return
        print("[APPROVE] sandbox 自检会启动一次最小 Codex exec，用于测试真实 workspace-write 命令执行层，会消耗少量 token。")
        if input("允许运行 sandbox 自检？[y/N] ").strip().lower() not in {"y", "yes"}:
            print("[!!] 已取消。")
            return
        print("[..] 正在测试 Codex Windows sandbox helper：workspace-write + 最小 pwd 命令。")
        cmd = [
            codex,
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "-C",
            str(ROOT),
            "--color",
            "never",
            "Run exactly one shell command to print the current directory. Then reply only DONE.",
        ]
        try:
            completed = subprocess.run(cmd, cwd=str(ROOT), stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=120, check=False)
        except subprocess.TimeoutExpired:
            print("[BLOCKED] sandbox 自检超时。Codex 可以启动，但本地命令执行层没有及时返回。")
            print(self._sandbox_repair_advice(codex))
            return
        text = (completed.stdout + "\n" + completed.stderr).strip()
        if completed.returncode == 0 and "windows sandbox: helper_unknown_error" not in text and "setup refresh had errors" not in text:
            print("[OK] Codex exec sandbox 自检通过。可以继续使用 workspace-write。")
            return
        print("[BLOCKED] Codex exec sandbox 自检失败。")
        if "SetNamedSecurityInfoW failed: 5" in text or "setup refresh had errors" in text:
            print("[!!] 根因很可能是项目目录 ACL 无法被 sandbox helper 临时修改。请用管理员 PowerShell 修复项目目录 owner/权限。")
        elif "windows sandbox: helper_unknown_error" in text:
            print("[!!] 错误：windows sandbox helper_unknown_error: setup refresh had errors")
        else:
            print((text[-1000:] if text else f"Codex exited with code {completed.returncode}"))
        print(self._sandbox_repair_advice(codex))

    def _legacy_sandbox_profile_check(self) -> None:
        codex = find_codex_executable(self.config.codex_path)
        if not codex:
            print("[BLOCKED] 未找到 Codex CLI。")
            return
        cmd = [
            codex,
            "sandbox",
            "-P",
            "workspace-write",
            "-C",
            str(ROOT),
            "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
            "-NoProfile",
            "-Command",
            "pwd",
        ]
        try:
            completed = subprocess.run(cmd, cwd=str(ROOT), stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=90, check=False)
        except subprocess.TimeoutExpired:
            print("[BLOCKED] sandbox 自检超时。Codex 可以启动，但本地命令执行层没有及时返回。")
            print(self._sandbox_repair_advice(codex))
            return
        text = (completed.stdout + "\n" + completed.stderr).strip()
        if completed.returncode == 0 and "windows sandbox: helper_unknown_error" not in text:
            print("[OK] Codex sandbox 自检通过。可以继续使用 workspace-write。")
            return
        print("[BLOCKED] Codex sandbox 自检失败。")
        if "default_permissions requires" in text:
            print("[!!] Codex 无法解析 sandbox permission profile：缺少 [permissions] 配置。")
            print(self._sandbox_profile_advice())
            return
        if "windows sandbox: helper_unknown_error" in text:
            print("[!!] 错误：windows sandbox helper_unknown_error: setup refresh had errors")
        else:
            print((text[-1000:] if text else f"Codex exited with code {completed.returncode}"))
        print(self._sandbox_repair_advice(codex))

    def _sandbox_profile_advice(self) -> str:
        return "\n".join([
            "这一步还没测到真正的 Windows helper，而是卡在 Codex CLI 的权限 profile 配置解析。",
            "建议：",
            "1. 先处理 `codex doctor` 的 install/update 失败：当前 running package root 和 npm global package root 不一致。",
            "2. 让 PATH、npm prefix、nvm 当前 Node 版本指向同一个全局 npm 目录后，再运行 `npm install -g @openai/codex` 或 `codex update`。",
            "3. 重启 VS Code/PowerShell，运行 `where codex` 和 `codex doctor`，确认 install/update 不再失败。",
            "4. 再回到本工具运行 /sandbox。",
            "5. 不建议手写未知的 [permissions] 配置；格式不匹配会让 Codex CLI 更难诊断。",
            "6. 如果 doctor 明确给出配置迁移命令，按它的提示迁移后再试。",
        ])

    def _sandbox_repair_advice(self, codex: str) -> str:
        npm_cmd = shutil.which("codex.cmd") or shutil.which("codex.CMD")
        lines = [
            "建议按顺序处理：",
            "1. 用管理员身份打开 PowerShell。",
            "2. 执行：takeown /F \"D:\\GZIC_study\\SRP\\medlit-cli\" /R /D Y",
            "3. 执行：icacls \"D:\\GZIC_study\\SRP\\medlit-cli\" /setowner \"monikoa\\CGOMI\" /T /C",
            "4. 执行：icacls \"D:\\GZIC_study\\SRP\\medlit-cli\" /grant \"monikoa\\CGOMI:(OI)(CI)F\" /T /C",
            "5. 重新打开普通 PowerShell，回到项目目录后运行 /sandbox。",
        ]
        if npm_cmd and Path(codex).name.lower() != "codex.cmd":
            lines.append(f"   当前也可在 /account 的 Codex path 中填入：{npm_cmd}")
        lines.extend([
            "6. 如果仍失败，检查 Windows 安全软件/受控文件夹访问/企业策略是否拦截 ACL 修改。",
            "7. 只有在你明确接受风险时，才手动把 Codex sandbox 改为 danger-full-access；本工具不会自动替你绕过。",
        ])
        return "\n".join(lines)



def main() -> int:
    return AgentShell().run()
