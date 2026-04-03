"""
OutputEvaluator - Quality evaluation and error classification for worker outputs.

Implements the Reflexion pattern: when output is poor, generates natural-language
failure notes that are injected into the retry context, allowing the model to
learn from its mistakes without weight updates.

Error classification follows the pattern:
- TEMPORARY: Rate limits, timeouts → retry as-is after delay
- LOGICAL: Wrong approach, bad arguments → retry with reflexion notes
- PERMANENT: Not supported, blocked → skip or escalate
"""
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger("ahri.evaluator")


# ── Enums ─────────────────────────────────────────────────────────────

class OutputQuality(Enum):
    EXCELLENT = "excellent"
    ADEQUATE = "adequate"
    POOR = "poor"
    FAILED = "failed"


class ErrorType(Enum):
    TEMPORARY = "temporary"
    LOGICAL = "logical"
    PERMANENT = "permanent"


# ── Data Classes ──────────────────────────────────────────────────────

@dataclass
class EvaluationResult:
    quality: OutputQuality
    confidence: float  # 0.0-1.0
    issues: list = field(default_factory=list)
    suggestions: list = field(default_factory=list)
    should_retry: bool = False

    def to_dict(self) -> dict:
        return {
            "quality": self.quality.value,
            "confidence": self.confidence,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "should_retry": self.should_retry,
        }


@dataclass
class ReflexionNote:
    """Natural-language failure note for retry context."""
    attempt: int
    error_type: ErrorType
    what_happened: str
    what_to_change: str

    def to_dict(self) -> dict:
        return {
            "attempt": self.attempt,
            "error_type": self.error_type.value,
            "what_happened": self.what_happened,
            "what_to_change": self.what_to_change,
        }


# ── Error Classification ─────────────────────────────────────────────

# Patterns that indicate temporary errors (safe to retry as-is)
TEMPORARY_PATTERNS = [
    r"rate.?limit", r"429", r"503", r"502", r"timeout",
    r"resource.?exhausted", r"quota.?exceeded", r"too.?many.?requests",
    r"temporarily.?unavailable", r"connection.?reset", r"connection.?refused",
]

# Patterns that indicate permanent errors (no point retrying)
PERMANENT_PATTERNS = [
    r"not.?implemented", r"not.?supported", r"permission.?denied",
    r"blocked", r"unauthorized", r"403", r"401",
    r"invalid.?api.?key", r"model.?not.?found", r"deprecated",
]


class ErrorClassifier:
    """Classifies errors to determine retry strategy."""

    @staticmethod
    def classify(error_str: str) -> ErrorType:
        """Classify an error string into TEMPORARY, LOGICAL, or PERMANENT."""
        if not error_str:
            return ErrorType.LOGICAL

        error_lower = error_str.lower()

        for pattern in TEMPORARY_PATTERNS:
            if re.search(pattern, error_lower):
                return ErrorType.TEMPORARY

        for pattern in PERMANENT_PATTERNS:
            if re.search(pattern, error_lower):
                return ErrorType.PERMANENT

        # Default: assume logical error (fixable by changing approach)
        return ErrorType.LOGICAL


# ── Output Evaluator ──────────────────────────────────────────────────

# Evaluation prompt schema (~300 tokens, efficient for flash-lite)
EVALUATION_SCHEMA = {
    "type": "object",
    "properties": {
        "quality": {
            "type": "string",
            "enum": ["excellent", "adequate", "poor", "failed"],
            "description": "Output quality rating"
        },
        "confidence": {
            "type": "number",
            "description": "Confidence in assessment (0.0-1.0)"
        },
        "issues": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of issues found"
        },
        "suggestions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Suggestions for improvement"
        },
        "should_retry": {
            "type": "boolean",
            "description": "Whether the task should be retried"
        }
    },
    "required": ["quality", "should_retry"]
}


class OutputEvaluator:
    """
    Evaluates the quality of worker outputs using LLM-based assessment.

    The evaluator uses a lightweight prompt (~300 tokens) to assess whether
    the output actually addresses the task, is complete, and is correct.
    This goes beyond JSON schema validation (which only checks structure).
    """

    def __init__(self, error_classifier: Optional[ErrorClassifier] = None):
        self.error_classifier = error_classifier or ErrorClassifier()

    async def evaluate(
        self,
        task_description: str,
        worker_type: str,
        input_data: dict,
        output_data: dict,
        llm_caller: Callable,
    ) -> EvaluationResult:
        """
        Evaluate a worker's output quality.

        Uses a fast LLM call (~300 token prompt) to check if the output
        actually addresses the task requirements.
        """
        # Quick heuristic checks first (no LLM needed)
        quick_result = self._quick_check(output_data)
        if quick_result:
            return quick_result

        # Build compact evaluation prompt
        output_summary = self._summarize_output(output_data, max_chars=1000)
        input_summary = self._summarize_input(input_data, max_chars=500)

        prompt = (
            f"Evaluate this {worker_type} worker output.\n\n"
            f"Task: {task_description[:300]}\n"
            f"Input: {input_summary}\n"
            f"Output: {output_summary}\n\n"
            f"Rate quality (excellent/adequate/poor/failed). "
            f"List issues if any. Should it retry?\n"
            f"Return JSON: {{\"quality\": str, \"confidence\": float, "
            f"\"issues\": [str], \"suggestions\": [str], \"should_retry\": bool}}"
        )

        try:
            result = await llm_caller(
                prompt=prompt,
                schema=EVALUATION_SCHEMA,
            )

            quality = OutputQuality(result.get("quality", "adequate"))
            return EvaluationResult(
                quality=quality,
                confidence=min(1.0, max(0.0, result.get("confidence", 0.5))),
                issues=result.get("issues", []),
                suggestions=result.get("suggestions", []),
                should_retry=result.get("should_retry", quality in (OutputQuality.POOR, OutputQuality.FAILED)),
            )

        except Exception as e:
            logger.warning(f"[Evaluator] LLM evaluation failed: {e}, defaulting to ADEQUATE")
            return EvaluationResult(
                quality=OutputQuality.ADEQUATE,
                confidence=0.3,
                should_retry=False,
            )

    def classify_error(self, error_str: str) -> ErrorType:
        """Classify an error for retry strategy."""
        return self.error_classifier.classify(error_str)

    def create_reflexion_note(
        self,
        attempt: int,
        error_type: ErrorType,
        error_or_evaluation: Any,
    ) -> ReflexionNote:
        """Create a reflexion note from an error or evaluation result."""
        if isinstance(error_or_evaluation, EvaluationResult):
            what_happened = f"Output quality: {error_or_evaluation.quality.value}. " + \
                           "; ".join(error_or_evaluation.issues[:3])
            what_to_change = "; ".join(error_or_evaluation.suggestions[:3]) or \
                           "Improve output quality and completeness"
        elif isinstance(error_or_evaluation, str):
            what_happened = error_or_evaluation[:200]
            what_to_change = self._suggest_fix_for_error(error_or_evaluation, error_type)
        else:
            what_happened = str(error_or_evaluation)[:200]
            what_to_change = "Try a different approach"

        return ReflexionNote(
            attempt=attempt,
            error_type=error_type,
            what_happened=what_happened,
            what_to_change=what_to_change,
        )

    # ── Private Helpers ───────────────────────────────────────────────

    def _quick_check(self, output_data: dict) -> Optional[EvaluationResult]:
        """Quick heuristic checks that don't need LLM."""
        if not output_data:
            return EvaluationResult(
                quality=OutputQuality.FAILED,
                confidence=1.0,
                issues=["Output is empty"],
                should_retry=True,
            )

        # Check if output is just an error
        if "error" in output_data and len(output_data) <= 2:
            return EvaluationResult(
                quality=OutputQuality.FAILED,
                confidence=1.0,
                issues=[f"Output contains only error: {output_data.get('error', '')[:100]}"],
                should_retry=True,
            )

        return None  # Needs LLM evaluation

    def _summarize_output(self, data: dict, max_chars: int = 1000) -> str:
        """Create a compact summary of output data."""
        text = json.dumps(data, ensure_ascii=False, default=str)
        if len(text) > max_chars:
            return text[:max_chars] + "..."
        return text

    def _summarize_input(self, data: dict, max_chars: int = 500) -> str:
        """Create a compact summary of input data, excluding internal keys."""
        clean = {k: v for k, v in data.items() if not k.startswith("_") and k != "dependency_results"}
        text = json.dumps(clean, ensure_ascii=False, default=str)
        if len(text) > max_chars:
            return text[:max_chars] + "..."
        return text

    def _suggest_fix_for_error(self, error: str, error_type: ErrorType) -> str:
        """Generate a suggestion based on error type."""
        if error_type == ErrorType.TEMPORARY:
            return "This was a temporary error. Retry with the same approach."
        elif error_type == ErrorType.PERMANENT:
            return "This error is permanent. Try a completely different approach."
        else:
            return "Review the error and adjust your approach to avoid it."
