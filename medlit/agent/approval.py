"""Approval policy for terminal actions."""

from __future__ import annotations

from dataclasses import dataclass

from medlit.agent.tools import NETWORK_ACTIONS


@dataclass
class ApprovalPolicy:
    mode: str = "on-network"

    def needs_approval(self, action: str) -> bool:
        if self.mode == "never":
            return False
        if self.mode == "on-network":
            return action in NETWORK_ACTIONS
        if self.mode == "on-step":
            return True
        return action in NETWORK_ACTIONS

    def ask(self, action: str, reason: str = "") -> bool:
        if not self.needs_approval(action):
            return True
        label = f"Allow action `{action}`"
        if reason:
            label += f" ({reason})"
        answer = input(f"[APPROVE] {label}? [y/N] ").strip().lower()
        return answer in {"y", "yes"}

