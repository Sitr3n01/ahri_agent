"""
TPM (Tokens Per Minute) + RPM (Requests Per Minute) Manager.

Dual rate limiting for LLM APIs:
- TPM: Token quota (e.g., 250k TPM for Gemini Flash Lite)
- RPM: Request quota (e.g., 15 req/min for Gemini Flash Lite free tier)

Both limits are checked atomically under a single lock.
"""
import time
import hashlib
import threading
import uuid
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import TPMQuota


class TPMManager:
    """
    Manages dual rate limiting: TPM (tokens/min) + RPM (requests/min).

    Uses sliding window algorithm over 60-second windows.
    Thread-safe: single threading.Lock guards both TPM and RPM checks atomically.
    """

    def __init__(
        self,
        limit_tpm: int = 250000,
        limit_rpm: int = 15,
        window_seconds: int = 60
    ):
        """
        Args:
            limit_tpm: Maximum tokens per minute (default: 250000 for Gemini Flash Lite)
            limit_rpm: Maximum requests per minute (default: 15 for free tier)
            window_seconds: Sliding window duration in seconds (default: 60)
        """
        self.limit_tpm = limit_tpm
        self.limit_rpm = limit_rpm
        self.window_seconds = window_seconds

        # In-memory logs for fast rate limiting
        # token_log entries: (timestamp, token_count, request_id)
        self.token_log: deque[tuple[float, int, str]] = deque()
        self.request_log: deque[float] = deque()             # timestamps of requests

        # Single lock guards both logs atomically
        self._lock = threading.Lock()

    def _hash_api_key(self, api_key: str) -> str:
        """Hash API key for privacy (SHA256)."""
        return hashlib.sha256(api_key.encode()).hexdigest()

    def _generate_request_id(self) -> str:
        """Generate a unique request ID for token tracking."""
        return uuid.uuid4().hex[:12]

    def _prune_logs(self, now: float) -> None:
        """Remove entries older than the sliding window. Must hold _lock."""
        cutoff = now - self.window_seconds
        while self.token_log and self.token_log[0][0] < cutoff:
            self.token_log.popleft()
        while self.request_log and self.request_log[0] < cutoff:
            self.request_log.popleft()

    def request_tokens(self, estimated_tokens: int) -> float:
        """
        Check if a request can proceed (legacy TPM-only check).
        Kept for backward compatibility. Prefer request_permission().

        Returns:
            wait_seconds: 0 if request can proceed, >0 to wait
        """
        result = self.request_permission(estimated_tokens)
        if isinstance(result, tuple):
            return result[0]  # Return just the wait time for backward compat
        return result

    def request_permission(self, estimated_tokens: int) -> float | tuple[float, str]:
        """
        Atomically check BOTH RPM and TPM limits.

        Thread-safe: acquires lock to prevent race conditions between
        concurrent workers checking limits simultaneously.

        Args:
            estimated_tokens: Estimated tokens for this request

        Returns:
            If wait needed: wait_seconds (float > 0)
            If allowed: tuple(0.0, request_id) where request_id can be used
                        in update_actual_tokens() for precise matching
        """
        with self._lock:
            now = time.time()
            self._prune_logs(now)

            wait_tpm = 0.0
            wait_rpm = 0.0

            # --- Check TPM ---
            current_tokens = sum(count for _, count, _ in self.token_log)
            if current_tokens + estimated_tokens > self.limit_tpm:
                if self.token_log:
                    oldest = self.token_log[0][0]
                    wait_tpm = max(0, (oldest + self.window_seconds) - now)

            # --- Check RPM ---
            if len(self.request_log) >= self.limit_rpm:
                if self.request_log:
                    oldest = self.request_log[0]
                    wait_rpm = max(0, (oldest + self.window_seconds) - now)

            # If either limit exceeded, return the max wait
            max_wait = max(wait_tpm, wait_rpm)
            if max_wait > 0:
                return max_wait

            # Both limits OK — record this request with unique ID
            request_id = self._generate_request_id()
            self.token_log.append((now, estimated_tokens, request_id))
            self.request_log.append(now)
            return (0.0, request_id)

    async def record_usage(
        self,
        db: AsyncSession,
        api_key: str,
        provider: str,
        model: str,
        tokens_used: int
    ) -> None:
        """
        Record token usage in database for long-term tracking and analytics.

        Args:
            db: Database session
            api_key: API key used (will be hashed)
            provider: Provider name (google_ai_studio, deepinfra, ollama)
            model: Model name
            tokens_used: Number of tokens consumed
        """
        api_key_hash = self._hash_api_key(api_key)
        now = datetime.utcnow()
        window_start = now.replace(second=0, microsecond=0)
        window_end = window_start + timedelta(minutes=1)

        stmt = select(TPMQuota).where(
            and_(
                TPMQuota.api_key_hash == api_key_hash,
                TPMQuota.provider == provider,
                TPMQuota.model == model,
                TPMQuota.window_start == window_start
            )
        )
        result = await db.execute(stmt)
        quota_record = result.scalar_one_or_none()

        if quota_record:
            quota_record.tokens_used += tokens_used
        else:
            quota_record = TPMQuota(
                api_key_hash=api_key_hash,
                provider=provider,
                model=model,
                tokens_used=tokens_used,
                window_start=window_start,
                window_end=window_end
            )
            db.add(quota_record)

        await db.commit()

    async def get_usage_stats(
        self,
        db: AsyncSession,
        api_key: str,
        provider: str,
        model: str,
        hours: int = 1
    ) -> dict:
        """
        Get token usage statistics for the last N hours.

        Returns:
            {total_tokens, avg_tpm, peak_tpm, quota_limit}
        """
        api_key_hash = self._hash_api_key(api_key)
        cutoff = datetime.utcnow() - timedelta(hours=hours)

        stmt = select(TPMQuota).where(
            and_(
                TPMQuota.api_key_hash == api_key_hash,
                TPMQuota.provider == provider,
                TPMQuota.model == model,
                TPMQuota.window_start >= cutoff
            )
        )
        result = await db.execute(stmt)
        records = result.scalars().all()

        total_tokens = sum(r.tokens_used for r in records)
        peak_tpm = max((r.tokens_used for r in records), default=0)
        avg_tpm = total_tokens / (hours * 60) if records else 0

        return {
            "total_tokens": total_tokens,
            "avg_tpm": round(avg_tpm, 2),
            "peak_tpm": peak_tpm,
            "quota_limit": self.limit_tpm
        }

    def update_actual_tokens(self, estimated_tokens: int, actual_tokens: int, request_id: str = "") -> None:
        """
        Replace a pre-estimated token entry with actual usage after a worker completes.

        Thread-safe. If request_id is provided, matches precisely by ID.
        Otherwise falls back to matching by estimated token count (legacy).
        If the entry already expired, adds a new entry with actual tokens.
        """
        with self._lock:
            now = time.time()
            self._prune_logs(now)

            for i in range(len(self.token_log) - 1, -1, -1):
                ts, count, rid = self.token_log[i]
                if request_id and rid == request_id:
                    self.token_log[i] = (ts, actual_tokens, rid)
                    return
                elif not request_id and count == estimated_tokens:
                    self.token_log[i] = (ts, actual_tokens, rid)
                    return

            # If no match found (expired), add a new entry with actual tokens
            self.token_log.append((now, actual_tokens, self._generate_request_id()))
            self.request_log.append(now)

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count from text (heuristic: 1 token ~ 4 chars).
        Conservative (overestimates) to stay under quota.
        """
        return len(text) // 4 + 10

    def get_status(self) -> dict:
        """Get current TPM+RPM status for monitoring. Thread-safe."""
        with self._lock:
            now = time.time()
            self._prune_logs(now)

            tokens_used = sum(count for _, count, _ in self.token_log)
            requests_used = len(self.request_log)
            tokens_remaining = max(0, self.limit_tpm - tokens_used)
            requests_remaining = max(0, self.limit_rpm - requests_used)

            return {
                "tokens_used_window": tokens_used,
                "tokens_remaining": tokens_remaining,
                "limit_tpm": self.limit_tpm,
                "utilization_percent": round((tokens_used / self.limit_tpm) * 100, 1) if self.limit_tpm > 0 else 0,
                "requests_used": requests_used,
                "requests_remaining": requests_remaining,
                "limit_rpm": self.limit_rpm,
                "rpm_utilization_percent": round((requests_used / self.limit_rpm) * 100, 1) if self.limit_rpm > 0 else 0,
            }

    def update_keys(self, keys: list[str]) -> None:
        """Hot-reload API keys (e.g., after settings change). Thread-safe."""
        with self._lock:
            pass  # TPMManager doesn't track per-key; see AgentKeyRotator


class AgentKeyRotator:
    """
    Round-robin API key rotation for agent mode.

    Distributes requests across multiple API keys, each with independent
    RPM limits. With 5 keys × 15 RPM = 75 RPM total throughput.

    Thread-safe: uses threading.Lock for concurrent worker access.
    """

    def __init__(self, keys: list[str], rpm_per_key: int = 15, window_seconds: int = 60):
        """
        Args:
            keys: List of API keys to rotate through
            rpm_per_key: Max requests per minute per key (default: 15)
            window_seconds: Sliding window duration (default: 60)
        """
        self.keys = keys if keys else []
        self.rpm_per_key = rpm_per_key
        self.window_seconds = window_seconds
        self._lock = threading.Lock()

        # Per-key request logs: {key_index: deque[float]}
        self._request_logs: dict[int, deque[float]] = {
            i: deque() for i in range(len(self.keys))
        }
        # Round-robin counter
        self._next_index = 0

    def _prune_key_log(self, key_idx: int, now: float) -> None:
        """Remove entries older than the sliding window for a specific key."""
        cutoff = now - self.window_seconds
        log = self._request_logs.get(key_idx)
        if log:
            while log and log[0] < cutoff:
                log.popleft()

    def get_next_key(self) -> tuple[str, float]:
        """
        Get the next available API key using round-robin rotation.

        Thread-safe: acquires lock for the entire selection process.

        Returns:
            (api_key, wait_seconds): The key to use and how long to wait
                                     (0 if immediately available)
        """
        if not self.keys:
            return ("", 0.0)

        with self._lock:
            now = time.time()
            n = len(self.keys)

            # Try round-robin: check each key starting from _next_index
            best_key_idx = self._next_index
            best_wait = float('inf')

            for offset in range(n):
                idx = (self._next_index + offset) % n
                self._prune_key_log(idx, now)

                log = self._request_logs[idx]
                if len(log) < self.rpm_per_key:
                    # This key is available — use it immediately
                    log.append(now)
                    self._next_index = (idx + 1) % n
                    return (self.keys[idx], 0.0)

                # Key is at limit — calculate wait time
                oldest = log[0]
                wait = max(0, (oldest + self.window_seconds) - now)
                if wait < best_wait:
                    best_wait = wait
                    best_key_idx = idx

            # All keys at limit — return the one with shortest wait
            return (self.keys[best_key_idx], best_wait)

    def record_request(self, key: str) -> None:
        """Manually record a request for a specific key. Thread-safe."""
        with self._lock:
            try:
                idx = self.keys.index(key)
                self._request_logs[idx].append(time.time())
            except ValueError:
                pass  # Key not in rotation

    def get_status(self) -> dict:
        """Get status of all keys for monitoring. Thread-safe."""
        with self._lock:
            now = time.time()
            key_statuses = []
            for i, key in enumerate(self.keys):
                self._prune_key_log(i, now)
                used = len(self._request_logs[i])
                key_statuses.append({
                    "key_index": i + 1,
                    "key_masked": f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***",
                    "requests_used": used,
                    "requests_remaining": max(0, self.rpm_per_key - used),
                })
            return {
                "total_keys": len(self.keys),
                "rpm_per_key": self.rpm_per_key,
                "total_rpm": self.rpm_per_key * len(self.keys),
                "keys": key_statuses,
            }

