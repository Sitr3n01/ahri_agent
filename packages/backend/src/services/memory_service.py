"""
Memory Service - Gerenciamento de perfil do usuario e memorias.
Portar de MemoryHandler (brain.py linhas 152-372).
"""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import UserProfile, PersonaMemory, SocialGraphEntry, EpisodicMemory

logger = logging.getLogger("ahri.memory")


class MemoryService:
    """Servico de memoria - substitui MemoryHandler com SQLite."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # User Profile
    # =========================================================================

    async def get_profile(self) -> dict:
        """Carrega o perfil do usuario. Cria default se nao existir."""
        result = await self.db.execute(select(UserProfile).where(UserProfile.id == 1))
        profile = result.scalar_one_or_none()

        if profile is None:
            profile = UserProfile(
                id=1,
                name="User",
                occupation="",
                custom_instructions="",
                work_context="",
                personal_context="",
                top_of_mind="",
                brief_history="",
                # Legacy
                archetype="Explorer",
                learning_style="",
                attributes={},
                preferences={},
                knowledge_tracker={"vocabulary_recent": [], "concepts_mastered": []},
                active_quests={},
                session_log=[],
            )
            self.db.add(profile)
            await self.db.commit()
            await self.db.refresh(profile)

        return {
            "name": profile.name,
            "occupation": profile.occupation,
            "custom_instructions": profile.custom_instructions,
            "work_context": profile.work_context,
            "personal_context": profile.personal_context,
            "top_of_mind": profile.top_of_mind,
            "brief_history": profile.brief_history,
            # Legacy
            "archetype": profile.archetype,
            "learning_style": profile.learning_style,
            "attributes": profile.attributes or {},
            "preferences": profile.preferences or {},
            "knowledge_tracker": profile.knowledge_tracker or {},
            "active_quests": profile.active_quests or {},
            "session_log": profile.session_log or [],
        }

    async def save_profile(self, data: dict) -> bool:
        """Salva o perfil do usuario."""
        result = await self.db.execute(select(UserProfile).where(UserProfile.id == 1))
        profile = result.scalar_one_or_none()

        if profile is None:
            profile = UserProfile(id=1)
            self.db.add(profile)

        # Atualiza os novos campos caso estejam presentes
        if "name" in data:
            profile.name = data["name"]
        if "occupation" in data:
            profile.occupation = data["occupation"]
        if "custom_instructions" in data:
            profile.custom_instructions = data["custom_instructions"]
        if "work_context" in data:
            profile.work_context = data["work_context"]
        if "personal_context" in data:
            profile.personal_context = data["personal_context"]
        if "top_of_mind" in data:
            profile.top_of_mind = data["top_of_mind"]
        if "brief_history" in data:
            profile.brief_history = data["brief_history"]

        # Suporte a nested object do legado `user_profile`
        up = data.get("user_profile", {})
        if isinstance(up, dict):
            profile.name = up.get("name", profile.name)
            profile.archetype = up.get("archetype", profile.archetype)
            profile.learning_style = up.get("learning_style", profile.learning_style)

        if "archetype" in data:
            profile.archetype = data["archetype"]
        if "learning_style" in data:
            profile.learning_style = data["learning_style"]

        if "attributes" in data:
            profile.attributes = data["attributes"]
        if "preferences" in data:
            profile.preferences = data["preferences"]
        if "knowledge_tracker" in data:
            profile.knowledge_tracker = data["knowledge_tracker"]
        if "active_quests" in data:
            profile.active_quests = data["active_quests"]
        if "session_log" in data:
            profile.session_log = data["session_log"]

        await self.db.commit()
        return True

    async def update_attribute(self, key: str, value: str) -> None:
        """Atualiza um atributo especifico do perfil."""
        result = await self.db.execute(select(UserProfile).where(UserProfile.id == 1))
        profile = result.scalar_one_or_none()
        if profile:
            attrs = profile.attributes or {}
            attrs[key] = value
            profile.attributes = attrs
            await self.db.commit()

    async def add_fact(self, fact: str) -> None:
        """Adiciona um fato ao knowledge_tracker."""
        from datetime import date

        result = await self.db.execute(select(UserProfile).where(UserProfile.id == 1))
        profile = result.scalar_one_or_none()
        if profile:
            tracker = profile.knowledge_tracker or {}
            recent = tracker.get("vocabulary_recent", [])
            entry = f"[{date.today().strftime('%d/%m')}] {fact}"
            recent.append(entry)
            if len(recent) > 20:
                recent.pop(0)
            tracker["vocabulary_recent"] = recent
            profile.knowledge_tracker = tracker
            await self.db.commit()

    async def add_session_log(self, summary: str) -> None:
        """Adiciona entrada ao session_log."""
        from datetime import date

        result = await self.db.execute(select(UserProfile).where(UserProfile.id == 1))
        profile = result.scalar_one_or_none()
        if profile:
            logs = profile.session_log or []
            logs.append(f"[{date.today()}] {summary}")
            profile.session_log = logs
            await self.db.commit()

    # =========================================================================
    # Social Graph
    # =========================================================================

    async def get_social_graph(self) -> dict:
        """Carrega o social graph completo."""
        result = await self.db.execute(select(SocialGraphEntry))
        entries = result.scalars().all()
        return {entry.platform: entry.data for entry in entries}

    async def update_social_graph(self, platform: str, data: dict) -> None:
        """Atualiza dados de uma plataforma no social graph."""
        result = await self.db.execute(
            select(SocialGraphEntry).where(SocialGraphEntry.platform == platform)
        )
        entry = result.scalar_one_or_none()

        if entry:
            entry.data = data
        else:
            self.db.add(SocialGraphEntry(platform=platform, data=data))

        await self.db.commit()

    # =========================================================================
    # Persona Memory
    # =========================================================================

    async def get_persona_memory(self, persona_name: str) -> dict:
        """Carrega memoria especifica de uma persona."""
        result = await self.db.execute(
            select(PersonaMemory).where(PersonaMemory.persona_name == persona_name.lower())
        )
        memory = result.scalar_one_or_none()

        if memory is None:
            return {
                "active_quests": {},
                "session_log": [],
                "session_log_detailed": [],
                "last_session_buffer": [],
            }

        return {
            "active_quests": memory.active_quests or {},
            "session_log": memory.session_log or [],
            "session_log_detailed": memory.session_log_detailed or [],
            "last_session_buffer": memory.last_session_buffer or [],
        }

    async def save_persona_memory(self, persona_name: str, data: dict) -> None:
        """Salva memoria de persona."""
        name = persona_name.lower()
        result = await self.db.execute(
            select(PersonaMemory).where(PersonaMemory.persona_name == name)
        )
        memory = result.scalar_one_or_none()

        if memory is None:
            memory = PersonaMemory(persona_name=name)
            self.db.add(memory)

        memory.active_quests = data.get("active_quests", memory.active_quests)
        memory.session_log = data.get("session_log", memory.session_log)
        memory.session_log_detailed = data.get("session_log_detailed", memory.session_log_detailed)
        memory.last_session_buffer = data.get("last_session_buffer", memory.last_session_buffer)

        await self.db.commit()

    async def patch_persona_memory(self, persona_name: str, patch: dict) -> list[str]:
        """Remove entries específicas da memória de persona. Retorna lista do que foi removido."""
        result = await self.db.execute(
            select(PersonaMemory).where(PersonaMemory.persona_name == persona_name.lower())
        )
        memory = result.scalar_one_or_none()
        if not memory:
            return []

        removed = []

        # Remove quest keys
        if patch.get("remove_quest_keys"):
            quests = dict(memory.active_quests or {})
            for key in patch["remove_quest_keys"]:
                if key in quests:
                    del quests[key]
                    removed.append(f"quest:{key}")
            memory.active_quests = quests

        # Remove session_log by indices (reverse order)
        if patch.get("remove_session_log_indices"):
            logs = list(memory.session_log or [])
            for idx in sorted(patch["remove_session_log_indices"], reverse=True):
                if 0 <= idx < len(logs):
                    removed.append(f"session_log:{idx}")
                    logs.pop(idx)
            memory.session_log = logs

        # Remove session_log_detailed by indices (reverse order)
        if patch.get("remove_session_log_detailed_indices"):
            detailed = list(memory.session_log_detailed or [])
            for idx in sorted(patch["remove_session_log_detailed_indices"], reverse=True):
                if 0 <= idx < len(detailed):
                    removed.append(f"session_log_detailed:{idx}")
                    detailed.pop(idx)
            memory.session_log_detailed = detailed

        # Clear buffer
        if patch.get("clear_buffer"):
            if memory.last_session_buffer:
                removed.append("last_session_buffer:cleared")
            memory.last_session_buffer = []

        await self.db.commit()
        return removed

    # =========================================================================
    # Episodic Memory (NOVO)
    # =========================================================================

    async def save_episode(
        self,
        persona_name: str,
        topics: list[str],
        emotional_tone: str,
        summary: str,
        importance: int = 5,
        outcomes: Optional[list[str]] = None,
    ) -> None:
        """Salva uma memoria episodica."""
        episode = EpisodicMemory(
            persona_name=persona_name.lower(),
            topics=topics,
            emotional_tone=emotional_tone,
            summary=summary,
            importance=importance,
            outcomes=outcomes or [],
        )
        self.db.add(episode)
        await self.db.commit()

    async def get_recent_episodes(self, persona_name: str, limit: int = 5) -> list[dict]:
        """Retorna episodios recentes de uma persona."""
        result = await self.db.execute(
            select(EpisodicMemory)
            .where(EpisodicMemory.persona_name == persona_name.lower())
            .order_by(EpisodicMemory.date.desc())
            .limit(limit)
        )
        episodes = result.scalars().all()
        return [
            {
                "date": str(ep.date),
                "topics": ep.topics,
                "emotional_tone": ep.emotional_tone,
                "summary": ep.summary,
                "importance": ep.importance,
                "outcomes": ep.outcomes,
            }
            for ep in episodes
        ]

    # =========================================================================
    # Auto-Profile Management (Settings UI)
    # =========================================================================

    async def get_auto_profile(self) -> dict:
        """Retorna os campos narrativos e os legados gerados automaticamente."""
        result = await self.db.execute(select(UserProfile).where(UserProfile.id == 1))
        profile = result.scalar_one_or_none()
        if profile is None:
            return {"attributes": {}, "knowledge_tracker": {}, "active_quests": {}, "session_log": [], "work_context": "", "personal_context": "", "top_of_mind": "", "brief_history": ""}
        return {
            "work_context": profile.work_context or "",
            "personal_context": profile.personal_context or "",
            "top_of_mind": profile.top_of_mind or "",
            "brief_history": profile.brief_history or "",
            "attributes": profile.attributes or {},
            "knowledge_tracker": profile.knowledge_tracker or {},
            "active_quests": profile.active_quests or {},
            "session_log": profile.session_log or [],
        }

    async def patch_auto_profile(self, patch: dict) -> list[str]:
        """Remove entries específicas do perfil automático. Retorna lista do que foi removido."""
        result = await self.db.execute(select(UserProfile).where(UserProfile.id == 1))
        profile = result.scalar_one_or_none()
        if not profile:
            return []

        removed = []

        # Remove attribute keys
        if patch.get("remove_attribute_keys"):
            attrs = dict(profile.attributes or {})
            for key in patch["remove_attribute_keys"]:
                if key in attrs:
                    del attrs[key]
                    removed.append(f"attribute:{key}")
            profile.attributes = attrs

        # Update specific attributes (upsert)
        if patch.get("update_attributes"):
            attrs = dict(profile.attributes or {})
            for key, value in patch["update_attributes"].items():
                attrs[key] = value
                removed.append(f"attribute:updated:{key}")
            profile.attributes = attrs

        # Remove vocabulary_recent by indices (reverse order to preserve indices)
        if patch.get("remove_vocabulary_indices"):
            tracker = dict(profile.knowledge_tracker or {})
            recent = list(tracker.get("vocabulary_recent", []))
            for idx in sorted(patch["remove_vocabulary_indices"], reverse=True):
                if 0 <= idx < len(recent):
                    removed.append(f"vocabulary:{recent[idx]}")
                    recent.pop(idx)
            tracker["vocabulary_recent"] = recent
            profile.knowledge_tracker = tracker

        # Remove concepts_mastered by indices
        if patch.get("remove_concept_indices"):
            tracker = dict(profile.knowledge_tracker or {})
            concepts = list(tracker.get("concepts_mastered", []))
            for idx in sorted(patch["remove_concept_indices"], reverse=True):
                if 0 <= idx < len(concepts):
                    removed.append(f"concept:{concepts[idx]}")
                    concepts.pop(idx)
            tracker["concepts_mastered"] = concepts
            profile.knowledge_tracker = tracker

        # Remove quest keys
        if patch.get("remove_quest_keys"):
            quests = dict(profile.active_quests or {})
            for key in patch["remove_quest_keys"]:
                if key in quests:
                    del quests[key]
                    removed.append(f"quest:{key}")
            profile.active_quests = quests

        # Remove session_log by indices
        if patch.get("remove_session_log_indices"):
            logs = list(profile.session_log or [])
            for idx in sorted(patch["remove_session_log_indices"], reverse=True):
                if 0 <= idx < len(logs):
                    removed.append(f"session_log:{idx}")
                    logs.pop(idx)
            profile.session_log = logs

        await self.db.commit()
        return removed

    async def clear_auto_profile_category(self, category: str) -> bool:
        """Limpa uma categoria inteira do perfil automático."""
        result = await self.db.execute(select(UserProfile).where(UserProfile.id == 1))
        profile = result.scalar_one_or_none()
        if not profile:
            return False

        if category == "attributes":
            profile.attributes = {}
        elif category == "knowledge_tracker":
            profile.knowledge_tracker = {"vocabulary_recent": [], "concepts_mastered": []}
        elif category == "active_quests":
            profile.active_quests = {}
        elif category == "session_log":
            profile.session_log = []
        else:
            return False

        await self.db.commit()
        return True

    # =========================================================================
    # Social Graph Management (Settings UI)
    # =========================================================================

    async def delete_social_graph_platform(self, platform: str) -> bool:
        """Deleta uma entrada do social graph."""
        result = await self.db.execute(
            select(SocialGraphEntry).where(SocialGraphEntry.platform == platform)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            return False
        await self.db.delete(entry)
        await self.db.commit()
        return True

    # =========================================================================
    # Episodic Memory Management (Settings UI)
    # =========================================================================

    async def get_episodes(
        self,
        persona_name: str | None = None,
        min_importance: int | None = None,
        min_date: str | None = None,
        max_date: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Lista memórias episódicas com filtros."""
        from datetime import datetime as dt

        query = select(EpisodicMemory)

        if persona_name:
            query = query.where(EpisodicMemory.persona_name == persona_name.lower())
        if min_importance is not None:
            query = query.where(EpisodicMemory.importance >= min_importance)
        if min_date:
            try:
                query = query.where(EpisodicMemory.date >= dt.fromisoformat(min_date))
            except ValueError:
                pass
        if max_date:
            try:
                query = query.where(EpisodicMemory.date <= dt.fromisoformat(max_date))
            except ValueError:
                pass

        query = query.order_by(EpisodicMemory.date.desc()).offset(offset).limit(limit)
        result = await self.db.execute(query)
        episodes = result.scalars().all()

        return [
            {
                "id": ep.id,
                "persona_name": ep.persona_name,
                "date": str(ep.date),
                "topics": ep.topics or [],
                "emotional_tone": ep.emotional_tone or "",
                "summary": ep.summary or "",
                "importance": ep.importance or 5,
                "outcomes": ep.outcomes or [],
            }
            for ep in episodes
        ]

    async def delete_episode(self, episode_id: int) -> bool:
        """Deleta uma memória episódica."""
        result = await self.db.execute(
            select(EpisodicMemory).where(EpisodicMemory.id == episode_id)
        )
        episode = result.scalar_one_or_none()
        if not episode:
            return False
        await self.db.delete(episode)
        await self.db.commit()
        return True

    async def bulk_delete_episodes(self, ids: list[int]) -> int:
        """Deleta múltiplas memórias episódicas. Retorna quantidade deletada."""
        deleted = 0
        for ep_id in ids:
            result = await self.db.execute(
                select(EpisodicMemory).where(EpisodicMemory.id == ep_id)
            )
            episode = result.scalar_one_or_none()
            if episode:
                await self.db.delete(episode)
                deleted += 1
        await self.db.commit()
        return deleted

    async def forget_from_profile(self, topic: str) -> list[str]:
        """Remove entradas do perfil que correspondem ao tópico.
        Limpa knowledge_tracker e attributes. Retorna lista do que foi removido."""
        result = await self.db.execute(select(UserProfile).where(UserProfile.id == 1))
        profile = result.scalar_one_or_none()
        if not profile:
            return []

        removed = []
        topic_lower = topic.lower()

        # Clean vocabulary_recent
        tracker = dict(profile.knowledge_tracker or {})
        recent = list(tracker.get("vocabulary_recent", []))
        new_recent = [r for r in recent if topic_lower not in r.lower()]
        if len(new_recent) < len(recent):
            removed.extend([f"vocabulary:{r}" for r in recent if topic_lower in r.lower()])
        tracker["vocabulary_recent"] = new_recent

        # Clean concepts_mastered
        concepts = list(tracker.get("concepts_mastered", []))
        new_concepts = [c for c in concepts if topic_lower not in c.lower()]
        if len(new_concepts) < len(concepts):
            removed.extend([f"concept:{c}" for c in concepts if topic_lower in c.lower()])
        tracker["concepts_mastered"] = new_concepts

        profile.knowledge_tracker = tracker

        # Clean attributes
        attrs = dict(profile.attributes or {})
        keys_to_remove = [k for k in attrs if topic_lower in k.lower() or (isinstance(attrs[k], str) and topic_lower in attrs[k].lower())]
        for key in keys_to_remove:
            removed.append(f"attribute:{key}={attrs[key]}")
            del attrs[key]
        profile.attributes = attrs

        await self.db.commit()
        return removed
