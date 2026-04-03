"""
SemanticMemoryService - Dual-Layer Memory Architecture (v3.2.0)

Layer 1: UserPreferences — explicit, user-controlled, AI never writes here.
Layer 2: SemanticMemoryTier — AI-managed hierarchical memory with decay.

Six tiers (priority order for prompt injection):
  immediate_context    → emotional state, today's events           (decay: 48h)
  top_of_mind          → active projects, recurring concerns        (decay: 7d)
  recent_history       → significant events last 7-14 days         (decay: 30d → long_term)
  work_context         → professional background, tech stack        (stable, synthesis-refreshed)
  personal_context     → relationships, hobbies, interests          (stable, synthesis-refreshed)
  long_term_background → stable biographical facts, core values     (no decay)
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import UserPreferences, SemanticMemoryTier, UserProfile

logger = logging.getLogger("ahri.semantic_memory")

VALID_TIERS = {
    "immediate_context",
    "top_of_mind",
    "recent_history",
    "work_context",
    "personal_context",
    "long_term_background",
}

# Decay rules: (tier) → (days_since_reinforced, new_tier)
# None as new_tier means delete the item (shouldn't happen; we always demote)
DECAY_RULES = {
    "immediate_context": (2, "top_of_mind"),
    "top_of_mind": (7, "recent_history"),
    "recent_history": (30, "long_term_background"),
    # work_context and personal_context only decay importance, not tier
}


class SemanticMemoryService:
    """
    Manages the dual-layer memory architecture.
    Layer 1: UserPreferences (user-controlled)
    Layer 2: SemanticMemoryTier (AI-managed with decay)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # Layer 1 — UserPreferences
    # =========================================================================

    async def get_preferences(self) -> dict:
        """Returns the singleton UserPreferences record, creating it if missing."""
        result = await self.db.execute(
            select(UserPreferences).where(UserPreferences.id == 1)
        )
        prefs = result.scalar_one_or_none()

        if prefs is None:
            # Seed from UserProfile if it exists (one-time bootstrap)
            profile_result = await self.db.execute(
                select(UserProfile).where(UserProfile.id == 1)
            )
            profile = profile_result.scalar_one_or_none()

            prefs = UserPreferences(
                id=1,
                display_name=profile.name if profile else "Usuário",
                pronouns="",
                occupation=profile.occupation if profile else "",
                location="",
                custom_instructions=profile.custom_instructions if profile else "",
                topics_to_avoid="",
                persona_style="",
            )
            self.db.add(prefs)
            await self.db.commit()
            await self.db.refresh(prefs)

        return self._prefs_to_dict(prefs)

    async def update_preferences(self, data: dict) -> dict:
        """Full or partial update of UserPreferences."""
        result = await self.db.execute(
            select(UserPreferences).where(UserPreferences.id == 1)
        )
        prefs = result.scalar_one_or_none()

        if prefs is None:
            prefs = UserPreferences(id=1)
            self.db.add(prefs)

        updatable = {
            "display_name", "pronouns", "occupation", "location",
            "custom_instructions", "topics_to_avoid", "persona_style",
        }
        for key, value in data.items():
            if key in updatable and value is not None:
                setattr(prefs, key, value)

        prefs.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(prefs)

        # Sync display_name back to UserProfile.name so existing code keeps working
        if "display_name" in data and data["display_name"]:
            await self._sync_name_to_profile(data["display_name"])

        return self._prefs_to_dict(prefs)

    async def _sync_name_to_profile(self, name: str):
        """Keep UserProfile.name in sync with UserPreferences.display_name."""
        result = await self.db.execute(
            select(UserProfile).where(UserProfile.id == 1)
        )
        profile = result.scalar_one_or_none()
        if profile:
            profile.name = name
            await self.db.commit()

    def _prefs_to_dict(self, prefs: UserPreferences) -> dict:
        return {
            "display_name": prefs.display_name or "",
            "pronouns": prefs.pronouns or "",
            "occupation": prefs.occupation or "",
            "location": prefs.location or "",
            "custom_instructions": prefs.custom_instructions or "",
            "topics_to_avoid": prefs.topics_to_avoid or "",
            "persona_style": prefs.persona_style or "",
        }

    # =========================================================================
    # Layer 2 — SemanticMemoryTier
    # =========================================================================

    async def get_tiers(self) -> dict:
        """Returns all tier items grouped by tier name, sorted by importance desc."""
        result = await self.db.execute(
            select(SemanticMemoryTier).order_by(
                SemanticMemoryTier.importance.desc(),
                SemanticMemoryTier.last_reinforced.desc(),
            )
        )
        items = result.scalars().all()

        grouped: dict = {tier: [] for tier in VALID_TIERS}
        for item in items:
            if item.tier in grouped:
                grouped[item.tier].append(self._item_to_dict(item))

        return grouped

    async def get_tier(self, tier_name: str) -> list:
        """Returns items for a single tier."""
        result = await self.db.execute(
            select(SemanticMemoryTier)
            .where(SemanticMemoryTier.tier == tier_name)
            .order_by(
                SemanticMemoryTier.importance.desc(),
                SemanticMemoryTier.last_reinforced.desc(),
            )
        )
        return [self._item_to_dict(i) for i in result.scalars().all()]

    async def add_or_reinforce_fact(
        self,
        tier: str,
        content: str,
        source_session_id: Optional[int] = None,
        importance: int = 5,
        tags: list = None,
    ) -> dict:
        """
        Inserts a new memory fact, or reinforces an existing near-duplicate.

        Duplicate detection: simple case-insensitive substring check within the
        same tier. Good enough for MVP; can be upgraded to embedding similarity.
        """
        if tier not in VALID_TIERS:
            raise ValueError(f"Invalid tier: {tier}. Must be one of {VALID_TIERS}")

        tags = tags or []
        content_lower = content.strip().lower()

        # Fetch existing items in this tier for duplicate/conflict check
        existing_result = await self.db.execute(
            select(SemanticMemoryTier).where(SemanticMemoryTier.tier == tier)
        )
        existing = existing_result.scalars().all()

        # Check for near-duplicate (>70% word overlap or direct substring)
        for item in existing:
            if self._is_near_duplicate(content_lower, item.content.lower()):
                # Reinforce: update timestamp and bump importance slightly
                item.last_reinforced = datetime.utcnow()
                item.importance = min(10, max(item.importance, importance))
                if source_session_id and not item.source_session_id:
                    item.source_session_id = source_session_id
                await self.db.commit()
                await self.db.refresh(item)
                logger.debug(f"Reinforced memory fact id={item.id} in tier={tier}")
                return self._item_to_dict(item)

        # New fact — determine decay_date based on tier
        decay_date = self._compute_decay_date(tier)

        new_item = SemanticMemoryTier(
            tier=tier,
            content=content.strip(),
            source_session_id=source_session_id,
            created_at=datetime.utcnow(),
            last_reinforced=datetime.utcnow(),
            decay_date=decay_date,
            is_flagged=False,
            conflict_note="",
            importance=importance,
            tags=tags,
        )
        self.db.add(new_item)
        await self.db.commit()
        await self.db.refresh(new_item)
        logger.info(f"Added new memory fact id={new_item.id} tier={tier}: {content[:60]}...")
        return self._item_to_dict(new_item)

    async def delete_fact(self, fact_id: int) -> bool:
        """Deletes a single memory fact by ID. Returns True if found and deleted."""
        result = await self.db.execute(
            select(SemanticMemoryTier).where(SemanticMemoryTier.id == fact_id)
        )
        item = result.scalar_one_or_none()
        if not item:
            return False
        await self.db.delete(item)
        await self.db.commit()
        return True

    async def delete_tier(self, tier_name: str) -> int:
        """Clears all items from a tier. Returns the count deleted."""
        result = await self.db.execute(
            select(SemanticMemoryTier).where(SemanticMemoryTier.tier == tier_name)
        )
        items = result.scalars().all()
        count = len(items)
        for item in items:
            await self.db.delete(item)
        await self.db.commit()
        return count

    async def run_decay_pass(self) -> int:
        """
        Evaluates all items with a passed decay_date and demotes them to lower tiers.
        Returns the number of items that changed tier.
        """
        now = datetime.utcnow()
        result = await self.db.execute(
            select(SemanticMemoryTier).where(
                SemanticMemoryTier.decay_date <= now,
                SemanticMemoryTier.decay_date.is_not(None),
            )
        )
        items = result.scalars().all()
        changed = 0

        for item in items:
            days_since_reinforced = (now - item.last_reinforced).days

            # High-importance items resist decay — just push out the date
            if item.importance >= 8:
                item.decay_date = now + timedelta(days=14)
                continue

            rule = DECAY_RULES.get(item.tier)
            if rule:
                threshold_days, new_tier = rule
                if days_since_reinforced >= threshold_days:
                    logger.info(
                        f"Decaying item id={item.id} from {item.tier} → {new_tier}"
                    )
                    item.tier = new_tier
                    item.decay_date = self._compute_decay_date(new_tier)
                    changed += 1
                else:
                    # Not ready yet; push decay date forward
                    item.decay_date = now + timedelta(days=max(1, threshold_days - days_since_reinforced))
            elif item.tier in ("work_context", "personal_context"):
                # Stable tiers: decay importance, not tier
                days_since_reinforced_check = (now - item.last_reinforced).days
                if days_since_reinforced_check >= 60:
                    item.importance = max(1, item.importance - 1)
                item.decay_date = now + timedelta(days=30)
            else:
                # long_term_background or unknown: no decay
                item.decay_date = None

        if items:
            await self.db.commit()

        return changed

    # =========================================================================
    # One-time Legacy Migration
    # =========================================================================

    async def migrate_legacy(self) -> int:
        """
        One-time migration from UserProfile legacy fields to the new architecture.
        Idempotent — checks migration_v2_done flag before running.
        Returns the number of facts migrated.
        """
        profile_result = await self.db.execute(
            select(UserProfile).where(UserProfile.id == 1)
        )
        profile = profile_result.scalar_one_or_none()

        if not profile:
            logger.warning("No UserProfile found — nothing to migrate.")
            return 0

        # Check if already migrated (column may not exist in older DBs — handle gracefully)
        try:
            if getattr(profile, "migration_v2_done", False):
                logger.info("Legacy migration already done — skipping.")
                return 0
        except Exception:
            pass

        migrated = 0

        # Step 1: Seed UserPreferences from UserProfile
        await self.get_preferences()  # This bootstraps from UserProfile if needed

        # Step 2: Convert narrative columns → tier rows
        tier_mappings = [
            ("work_context",         profile.work_context,    "work_context",         6, None),
            ("personal_context",     profile.personal_context, "personal_context",    6, None),
            ("top_of_mind",          profile.top_of_mind,     "top_of_mind",          7, timedelta(days=7)),
            ("brief_history",        profile.brief_history,   "long_term_background", 5, None),
        ]

        for field_name, value, tier, importance, extra_decay in tier_mappings:
            if value and value.strip():
                await self.add_or_reinforce_fact(
                    tier=tier,
                    content=value.strip(),
                    importance=importance,
                )
                migrated += 1

        # Step 3: Convert session_log[-20] → recent_history
        session_log = profile.session_log or []
        for entry in session_log[-20:]:
            if isinstance(entry, str) and entry.strip():
                await self.add_or_reinforce_fact(
                    tier="recent_history",
                    content=entry.strip(),
                    importance=4,
                )
                migrated += 1

        # Step 4: Convert attributes dict → tier rows based on key semantics
        attributes = profile.attributes or {}
        stable_keys = {"name", "bio", "age", "location", "pronoun", "mother_tongue"}
        work_keys = {"occupation", "tech_stack", "languages", "skills"}
        personal_keys = {"interests", "music", "hobbies", "personality", "dislikes", "foods"}

        for key, value in attributes.items():
            if not value:
                continue
            value_str = str(value) if not isinstance(value, (list, dict)) else ", ".join(str(v) for v in (value if isinstance(value, list) else value.values()))
            if not value_str.strip():
                continue

            content = f"{key}: {value_str}"
            key_lower = key.lower()

            if any(k in key_lower for k in stable_keys):
                target_tier = "long_term_background"
                imp = 6
            elif any(k in key_lower for k in work_keys):
                target_tier = "work_context"
                imp = 6
            elif any(k in key_lower for k in personal_keys):
                target_tier = "personal_context"
                imp = 5
            else:
                target_tier = "recent_history"
                imp = 4

            await self.add_or_reinforce_fact(tier=target_tier, content=content, importance=imp)
            migrated += 1

        # Mark migration as done
        try:
            profile.migration_v2_done = True
            await self.db.commit()
        except Exception as e:
            logger.warning(f"Could not set migration_v2_done flag: {e}")

        logger.info(f"Legacy migration complete — {migrated} facts migrated.")
        return migrated

    # =========================================================================
    # Prompt Context Builder
    # =========================================================================

    def build_prompt_context(self, prefs: dict, tiers: dict, total_budget: int = 4800) -> str:
        """
        Builds the memory context string for injection into the system prompt.

        Token budget allocation (chars ≈ tokens * 4):
          Layer 1                → 800 chars  (always injected)
          immediate_context      → 600 chars  (always if present)
          top_of_mind            → 800 chars  (always if present)
          recent_history         → 600 chars
          work_context           → 600 chars
          personal_context       → 600 chars
          long_term_background   → 800 chars
        """
        parts = []

        # --- Layer 1: Always inject ---
        layer1_lines = ["[PREFERÊNCIAS DO USUÁRIO]"]
        if prefs.get("display_name"):
            layer1_lines.append(f"Nome: {prefs['display_name']}")
        if prefs.get("pronouns"):
            layer1_lines.append(f"Pronomes: {prefs['pronouns']}")
        if prefs.get("occupation"):
            layer1_lines.append(f"Ocupação: {prefs['occupation']}")
        if prefs.get("location"):
            layer1_lines.append(f"Localização: {prefs['location']}")
        if prefs.get("custom_instructions"):
            layer1_lines.append(f"Instruções:\n{prefs['custom_instructions']}")
        if prefs.get("topics_to_avoid"):
            layer1_lines.append(f"Evitar: {prefs['topics_to_avoid']}")
        if prefs.get("persona_style"):
            layer1_lines.append(f"Estilo: {prefs['persona_style']}")

        layer1_block = "\n".join(layer1_lines)
        parts.append(self._truncate(layer1_block, 800))

        # --- Layer 2: Priority-ordered tiers ---
        tier_config = [
            ("immediate_context",    "CONTEXTO IMEDIATO",       600),
            ("top_of_mind",          "FOCO ATUAL",              800),
            ("recent_history",       "HISTÓRICO RECENTE",       600),
            ("work_context",         "CONTEXTO PROFISSIONAL",   600),
            ("personal_context",     "CONTEXTO PESSOAL",        600),
            ("long_term_background", "HISTÓRICO DE LONGO PRAZO", 800),
        ]

        chars_used = len(layer1_block)
        for tier_key, label, allotment in tier_config:
            if chars_used >= total_budget:
                break

            items = tiers.get(tier_key, [])
            if not items:
                continue

            # Sort: importance desc, last_reinforced desc
            sorted_items = sorted(
                items,
                key=lambda x: (-x.get("importance", 5), x.get("last_reinforced", "")),
            )

            tier_lines = [f"[{label}]"]
            budget_left = min(allotment, total_budget - chars_used)
            current_len = len(f"[{label}]\n")

            for item in sorted_items:
                flag = " ⚠" if item.get("is_flagged") else ""
                line = f"- {item['content']}{flag}\n"
                if current_len + len(line) > budget_left:
                    break
                tier_lines.append(f"- {item['content']}{flag}")
                current_len += len(line)

            if len(tier_lines) > 1:  # has at least one item
                block = "\n".join(tier_lines)
                parts.append(block)
                chars_used += len(block)

        return "\n\n".join(parts)

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _compute_decay_date(self, tier: str) -> Optional[datetime]:
        now = datetime.utcnow()
        decay_offsets = {
            "immediate_context": timedelta(days=2),
            "top_of_mind": timedelta(days=7),
            "recent_history": timedelta(days=30),
            "work_context": timedelta(days=60),
            "personal_context": timedelta(days=60),
            "long_term_background": None,
        }
        offset = decay_offsets.get(tier)
        return now + offset if offset else None

    def _is_near_duplicate(self, new_content: str, existing_content: str) -> bool:
        """
        Returns True if the two strings are near-duplicates.
        Strategy: direct substring OR significant word overlap (>60%).
        """
        if new_content in existing_content or existing_content in new_content:
            return True

        new_words = set(new_content.split())
        existing_words = set(existing_content.split())
        if not new_words:
            return False

        overlap = len(new_words & existing_words) / len(new_words)
        return overlap > 0.6

    def _item_to_dict(self, item: SemanticMemoryTier) -> dict:
        return {
            "id": item.id,
            "tier": item.tier,
            "content": item.content,
            "source_session_id": item.source_session_id,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "last_reinforced": item.last_reinforced.isoformat() if item.last_reinforced else None,
            "decay_date": item.decay_date.isoformat() if item.decay_date else None,
            "is_flagged": item.is_flagged,
            "conflict_note": item.conflict_note or "",
            "importance": item.importance,
            "tags": item.tags or [],
        }

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars - 3] + "..."
