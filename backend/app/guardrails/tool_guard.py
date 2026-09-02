"""MCP Tool Guard.

Every tool invocation passes through :func:`authorize` before it reaches the
MCP client. The guard answers a single question - *may this agent call this
tool with these arguments right now?* - and it denies by default.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.config import get_settings
from app.core.constants import EVENT_TOOL_CALL_BLOCKED
from app.guardrails import pii_guard
from app.guardrails.policies import (
    AUTONOMOUS_OPERATIONS,
    FORBIDDEN_ARGUMENT_KEYS,
    get_policy,
)
from app.observability.logging import get_logger
from app.observability.tracing import current_context

logger = get_logger("journeymesh.tool_guard")


@dataclass
class ToolDecision:
    """Result of a tool authorization check."""

    allowed: bool
    tool: str
    agent: str
    reason: Optional[str] = None
    rule: Optional[str] = None
    operation: Optional[str] = None
    risk: Optional[str] = None
    requires_confirmation: bool = False
    sanitized_arguments: dict[str, Any] = field(default_factory=dict)
    redactions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": "tool",
            "tool": self.tool,
            "agent": self.agent,
            "allowed": self.allowed,
            "rule": self.rule,
            "reason": self.reason,
            "operation": self.operation,
            "risk": self.risk,
            "requires_confirmation": self.requires_confirmation,
            "redactions": self.redactions,
        }


class ToolGuard:
    """Stateful guard - call counts are tracked per graph run."""

    def __init__(self) -> None:
        self._call_counts: dict[str, int] = defaultdict(int)
        self.decisions: list[ToolDecision] = []

    def reset(self) -> None:
        self._call_counts.clear()
        self.decisions.clear()

    # ---- public API -----------------------------------------------------
    def authorize(
        self,
        *,
        tool: str,
        agent: str,
        arguments: Optional[dict[str, Any]] = None,
        user_confirmed: bool = False,
    ) -> ToolDecision:
        settings = get_settings()
        arguments = dict(arguments or {})

        if not settings.tool_guard_enabled:
            decision = ToolDecision(
                allowed=True,
                tool=tool,
                agent=agent,
                rule="guard_disabled",
                reason="Tool guard is disabled by configuration.",
                sanitized_arguments=arguments,
            )
            self._remember(decision)
            return decision

        policy = get_policy(tool)
        if policy is None:
            return self._deny(tool, agent, "not_allowlisted", f"Tool '{tool}' is not allowlisted.")

        if not policy.get("enabled", True):
            return self._deny(tool, agent, "tool_disabled", f"Tool '{tool}' is not enabled.")

        if agent not in policy.get("allowed_agents", []):
            return self._deny(
                tool,
                agent,
                "agent_not_authorized",
                f"Agent '{agent}' is not authorised to call '{tool}'.",
            )

        operation = policy.get("operation", "read")
        risk = policy.get("risk", "low")
        requires_confirmation = bool(policy.get("requires_confirmation", False))

        if operation not in AUTONOMOUS_OPERATIONS and not user_confirmed:
            return self._deny(
                tool,
                agent,
                "confirmation_required",
                f"'{tool}' performs a {operation} operation and needs explicit user confirmation.",
                operation=operation,
                risk=risk,
                requires_confirmation=True,
            )

        forbidden = sorted(set(arguments) & FORBIDDEN_ARGUMENT_KEYS)
        if forbidden:
            return self._deny(
                tool,
                agent,
                "forbidden_argument",
                f"Arguments {forbidden} must never be sent to an external tool.",
                operation=operation,
                risk=risk,
            )

        schema_error = _validate_arguments(arguments, policy.get("argument_schema", {}))
        if schema_error:
            return self._deny(
                tool, agent, "invalid_arguments", schema_error, operation=operation, risk=risk
            )

        limit = policy.get("max_calls_per_run")
        key = f"{agent}:{tool}"
        if limit is not None and self._call_counts[key] >= int(limit):
            return self._deny(
                tool,
                agent,
                "call_budget_exceeded",
                f"'{tool}' exceeded its call budget of {limit} for this run.",
                operation=operation,
                risk=risk,
            )

        sanitized, redactions = pii_guard.sanitize_payload(arguments)
        if redactions:
            logger.info(
                "tool arguments redacted before dispatch",
                extra={"tool": tool, "agent": agent, "categories": redactions, **current_context()},
            )

        self._call_counts[key] += 1
        decision = ToolDecision(
            allowed=True,
            tool=tool,
            agent=agent,
            rule="allowed",
            operation=operation,
            risk=risk,
            requires_confirmation=requires_confirmation,
            sanitized_arguments=sanitized,
            redactions=redactions,
        )
        self._remember(decision)
        return decision

    # ---- internals ------------------------------------------------------
    def _deny(
        self,
        tool: str,
        agent: str,
        rule: str,
        reason: str,
        *,
        operation: Optional[str] = None,
        risk: Optional[str] = None,
        requires_confirmation: bool = False,
    ) -> ToolDecision:
        decision = ToolDecision(
            allowed=False,
            tool=tool,
            agent=agent,
            rule=rule,
            reason=reason,
            operation=operation,
            risk=risk,
            requires_confirmation=requires_confirmation,
        )
        logger.warning(
            EVENT_TOOL_CALL_BLOCKED,
            extra={"tool": tool, "agent": agent, "rule": rule, **current_context()},
        )
        self._remember(decision)
        return decision

    def _remember(self, decision: ToolDecision) -> None:
        self.decisions.append(decision)
        if len(self.decisions) > 200:
            del self.decisions[:-200]


def _validate_arguments(arguments: dict[str, Any], schema: dict[str, Any]) -> Optional[str]:
    if not schema:
        return None

    for name, rule in schema.items():
        required = rule.get("required", False)
        if name not in arguments or arguments[name] is None:
            if required:
                return f"missing required argument '{name}'"
            continue

        value = arguments[name]
        expected = rule.get("type")
        if expected == "string":
            if not isinstance(value, str):
                return f"argument '{name}' must be a string"
            max_length = rule.get("max_length")
            if max_length and len(value) > int(max_length):
                return f"argument '{name}' exceeds {max_length} characters"
        elif expected == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                return f"argument '{name}' must be an integer"
        elif expected == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return f"argument '{name}' must be a number"

        if expected in {"integer", "number"}:
            minimum = rule.get("min")
            maximum = rule.get("max")
            if minimum is not None and value < minimum:
                return f"argument '{name}' must be >= {minimum}"
            if maximum is not None and value > maximum:
                return f"argument '{name}' must be <= {maximum}"

    unknown = sorted(set(arguments) - set(schema))
    if unknown:
        return f"unexpected argument(s): {', '.join(unknown)}"
    return None


_default_guard = ToolGuard()


def get_tool_guard() -> ToolGuard:
    """Return the process-wide guard instance."""
    return _default_guard
