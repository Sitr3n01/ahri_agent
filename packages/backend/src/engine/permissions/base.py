"""
Permission manager for tool execution.
Evaluates whether a tool call should be allowed, denied, or needs user confirmation.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

from ..types import PermissionDecision

logger = logging.getLogger("ahri.engine.permissions")


class RuleAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


@dataclass
class PermissionRule:
    """A single permission rule."""
    tool_pattern: str           # Glob pattern for tool name (e.g., "file_*", "shell_*")
    action: RuleAction
    arg_patterns: dict = field(default_factory=dict)  # argument name → regex pattern
    reason: str = ""
    priority: int = 0           # Higher priority rules evaluated first


# Dangerous patterns in tool arguments
DANGEROUS_PATTERNS = [
    (r"rm\s+-rf", "Recursive forced deletion"),
    (r"format\s+[A-Z]:", "Disk formatting"),
    (r"mkfs\.", "Filesystem creation"),
    (r"dd\s+if=", "Direct disk write"),
    (r">\s*/dev/sd", "Write to block device"),
    (r"shutdown|reboot|halt", "System shutdown/reboot"),
    (r"DROP\s+TABLE|DROP\s+DATABASE", "Database destruction"),
    (r"DELETE\s+FROM\s+\w+\s*;?\s*$", "Unfiltered DELETE (no WHERE)"),
]


class PermissionManager:
    """
    Evaluates tool permissions using layered rules.

    Evaluation order:
    1. Check permission mode (trust → always allow, ask → always ask)
    2. Check explicit rules (highest priority first)
    3. Check dangerous argument patterns
    4. Fall back to tool's default permission level
    """

    def __init__(self, mode: str = "auto"):
        """
        Args:
            mode: "auto" (use rules + defaults), "ask" (always ask), "trust" (always allow)
        """
        self.mode = mode
        self.rules: list[PermissionRule] = []
        self._compile_dangerous_patterns()

    def _compile_dangerous_patterns(self):
        self._dangerous = [(re.compile(p, re.IGNORECASE), desc) for p, desc in DANGEROUS_PATTERNS]

    def add_rule(self, rule: PermissionRule):
        """Add a permission rule."""
        self.rules.append(rule)
        self.rules.sort(key=lambda r: -r.priority)

    async def check(self, tool_name: str, arguments: dict) -> PermissionDecision:
        """
        Check if a tool call is allowed.

        Returns:
            PermissionDecision.ALLOW, DENY, or ASK
        """
        # Mode overrides
        if self.mode == "trust":
            return PermissionDecision.ALLOW
        if self.mode == "ask":
            return PermissionDecision.ASK

        # Check explicit rules
        for rule in self.rules:
            if self._matches_tool(rule.tool_pattern, tool_name):
                if self._matches_args(rule.arg_patterns, arguments):
                    return PermissionDecision(rule.action.value)

        # Check dangerous patterns in arguments
        args_str = str(arguments)
        for pattern, description in self._dangerous:
            if pattern.search(args_str):
                logger.warning(f"Dangerous pattern detected in {tool_name}: {description}")
                return PermissionDecision.DENY

        # Fall back to tool's default permission level
        # Tools define their own default permission levels if no rules override them
        # Let's assume tool registry dictates it, for now we just return ALLOW if it isn't dangerous
        return PermissionDecision.ALLOW

    def _matches_tool(self, pattern: str, tool_name: str) -> bool:
        """Check if tool name matches a glob pattern."""
        import fnmatch
        return fnmatch.fnmatch(tool_name, pattern)

    def _matches_args(self, arg_patterns: dict, arguments: dict) -> bool:
        """Check if arguments match the rule's arg patterns."""
        if not arg_patterns:
            return True
        for key, pattern in arg_patterns.items():
            value = str(arguments.get(key, ""))
            if not re.search(pattern, value):
                return False
        return True
