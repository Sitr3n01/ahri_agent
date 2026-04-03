"""
PlanCache - LRU cache for agent execution plans.

Caches plans by normalized goal text to avoid redundant LLM planning calls.
Saves ~5K tokens and ~500ms per cache hit for repeated or similar goals.

Plans with low success rates (< 50% after 3+ uses) are evicted.
"""
import re
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("ahri.plan_cache")

MAX_CACHE_SIZE = 100


@dataclass
class CachedPlan:
    """A cached plan with usage metadata."""
    plan: dict
    use_count: int = 0
    success_count: int = 0
    failure_count: int = 0

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 1.0


class PlanCache:
    """
    LRU cache for execution plans keyed by normalized goal.

    Usage:
        cache = PlanCache()

        # Before planning:
        cached = cache.get(goal)
        if cached:
            plan = cached  # Skip LLM call

        # After execution:
        cache.record_outcome(goal, success=True)
    """

    def __init__(self, max_size: int = MAX_CACHE_SIZE):
        self._cache: OrderedDict[str, CachedPlan] = OrderedDict()
        self._max_size = max_size

    def get(self, goal: str) -> Optional[dict]:
        """
        Look up a cached plan by normalized goal.

        Returns the plan dict if found and healthy, None otherwise.
        """
        key = self._normalize(goal)
        entry = self._cache.get(key)

        if entry is None:
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        entry.use_count += 1

        # Evict plans with poor success rate after enough data
        if entry.use_count >= 3 and entry.success_rate < 0.5:
            logger.info(f"[PlanCache] Evicting low-success plan: rate={entry.success_rate:.0%}")
            del self._cache[key]
            return None

        logger.info(f"[PlanCache] Cache hit (uses={entry.use_count}, rate={entry.success_rate:.0%})")
        return entry.plan

    def store(self, goal: str, plan: dict) -> None:
        """Store a plan in the cache."""
        key = self._normalize(goal)

        if key in self._cache:
            # Update existing entry
            self._cache[key].plan = plan
            self._cache.move_to_end(key)
        else:
            # Evict oldest if at capacity
            if len(self._cache) >= self._max_size:
                evicted_key, _ = self._cache.popitem(last=False)
                logger.debug(f"[PlanCache] LRU eviction: {evicted_key[:50]}")

            self._cache[key] = CachedPlan(plan=plan)

    def record_outcome(self, goal: str, success: bool) -> None:
        """Record whether an execution using this plan succeeded or failed."""
        key = self._normalize(goal)
        entry = self._cache.get(key)
        if entry:
            if success:
                entry.success_count += 1
            else:
                entry.failure_count += 1

    def clear(self) -> None:
        """Clear all cached plans."""
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)

    def _normalize(self, goal: str) -> str:
        """
        Normalize a goal for cache key matching.

        - Lowercase
        - Strip whitespace
        - Remove common filler words
        - Collapse multiple spaces
        """
        text = goal.lower().strip()
        # Remove filler words
        fillers = {"please", "can you", "could you", "i want", "i need", "help me"}
        for filler in fillers:
            text = text.replace(filler, "")
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text
