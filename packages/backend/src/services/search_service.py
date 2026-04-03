"""
Search Service - Web search via Google Custom Search Engine.
Portar de WebSearch (brain.py linhas 580-634).
"""
import logging
from datetime import date
from typing import Optional

import requests
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.models.database import SearchQuota

logger = logging.getLogger("ahri.search")


class SearchService:
    """Servico de busca na web."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()
        self.enabled = bool(self.settings.cse_api_key and self.settings.cse_cx)

    async def check_quota(self) -> tuple[bool, int]:
        """Verifica e retorna (pode_buscar, restante)."""
        if not self.db:
            return True, 90  # No DB session — skip quota check

        today = date.today().isoformat()
        max_daily = 90

        result = await self.db.execute(select(SearchQuota).where(SearchQuota.id == 1))
        quota = result.scalar_one_or_none()

        if quota is None:
            return True, max_daily

        if quota.date != today:
            return True, max_daily

        remaining = max_daily - quota.count
        return remaining > 0, remaining

    async def _increment_quota(self):
        """Incrementa o contador de quota."""
        if not self.db:
            return  # No DB session — skip quota tracking

        today = date.today().isoformat()

        result = await self.db.execute(select(SearchQuota).where(SearchQuota.id == 1))
        quota = result.scalar_one_or_none()

        if quota is None:
            quota = SearchQuota(id=1, date=today, count=1)
            self.db.add(quota)
        elif quota.date != today:
            quota.date = today
            quota.count = 1
        else:
            quota.count += 1

        await self.db.commit()

    async def search(self, query: str, max_results: int = 5) -> dict:
        """Executa busca no Google CSE."""
        if not self.enabled:
            return {"error": "WebSearch disabled (no API keys).", "results": [], "remaining_quota": 0}

        can_search, remaining = await self.check_quota()
        if not can_search:
            return {"error": "Daily quota exceeded.", "results": [], "remaining_quota": 0}

        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": self.settings.cse_api_key,
            "cx": self.settings.cse_cx,
            "q": query,
            "num": min(max_results, 10),
        }

        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()

            await self._increment_quota()
            _, new_remaining = await self.check_quota()

            if "items" not in data:
                return {"results": [], "remaining_quota": new_remaining}

            results = [
                {
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                }
                for item in data["items"][:max_results]
            ]

            return {"results": results, "remaining_quota": new_remaining}

        except Exception as e:
            logger.error(f"Search error: {e}")
            return {"error": str(e), "results": [], "remaining_quota": remaining}
