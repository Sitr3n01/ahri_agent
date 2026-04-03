"""
Memory Worker - Specialized agent for searching and analyzing user memories.
Uses the configured agent model for memory search and synthesis.

Capabilities:
- Search episodic memories (knowledge/ files)
- Search persona memories (session logs)
- Search user profile attributes
- Synthesize memories into coherent answers
"""
from pathlib import Path
from typing import Any, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models.database import AgentWorkerTask, PersonaMemory, UserProfile
from src.services.workers.base_worker import BaseWorker


class MemoryWorker(BaseWorker):
    """Worker for memory search and analysis."""

    ENABLE_EVALUATION = False  # One-shot memory search, no iterative improvement

    ROLE_PROMPT = (
        "[ROLE: Memory Analyst]\n"
        "You search and synthesize information from execution history and knowledge files.\n"
        "Sources: episodic memories (knowledge files), past execution context.\n"
        "Cross-reference sources for comprehensive answers.\n"
        "Flag when information may be outdated.\n"
        "Output: JSON with 'findings', 'sources', and 'memory_type' fields."
    )

    def __init__(self, llm_service):
        super().__init__(
            llm_service=llm_service,
            worker_type="Memory",
            default_model="LITE"
        )
        self.data_dir = Path(__file__).resolve().parent.parent.parent.parent / "data"

    async def execute(
        self,
        db: AsyncSession,
        execution_id: int,
        input_data: Dict[str, Any]
    ) -> AgentWorkerTask:
        """
        Search and analyze memories.

        Input format:
        {
            "query": "what to search for",
            "memory_type": "episodic" | "persona" | "profile" | "all",
            "persona_name": "ahri" (optional, for persona-specific search),
            "limit": 10 (max results)
        }
        """
        import time
        start_time = time.time()
        task = await self._create_task_record(db, execution_id, input_data)

        try:
            query = input_data.get("query", "")
            memory_type = input_data.get("memory_type", "all")
            persona_name = input_data.get("persona_name")
            limit = input_data.get("limit", 10)

            results = {}

            if memory_type in ["episodic", "all"]:
                results["episodic"] = await self._search_episodic(query, persona_name, limit, db)

            # Persona and profile searches disabled in agent mode.
            # Agent mode is a pure function executor — no personality or user profile injection.

            # Synthesize results into coherent answer
            synthesis = await self._synthesize_memories(query, results, db)

            output = {
                "query": query,
                "results": results,
                "synthesis": synthesis,
                "total_matches": sum(len(v) for v in results.values() if isinstance(v, list))
            }
            tokens = self._estimate_tokens(str(output))
            return await self._complete_task(db, task, output, tokens, start_time)

        except Exception as e:
            return await self._fail_task(db, task, str(e), start_time)

    async def _search_episodic(
        self,
        query: str,
        persona_name: str | None,
        limit: int,
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """
        Search episodic memories (knowledge/*.md files).
        """
        matches = []
        personas_dir = self.data_dir / "personas"

        if not personas_dir.exists():
            return []

        # Determine which personas to search
        if persona_name:
            search_personas = [persona_name]
        else:
            search_personas = [p.name for p in personas_dir.iterdir() if p.is_dir()]

        for persona in search_personas:
            knowledge_dir = personas_dir / persona / "knowledge"
            if not knowledge_dir.exists():
                continue

            for md_file in knowledge_dir.glob("*.md"):
                try:
                    content = md_file.read_text(encoding='utf-8')

                    # Simple keyword matching (case-insensitive)
                    query_lower = query.lower()
                    if query_lower in content.lower():
                        # Extract snippet around match
                        idx = content.lower().find(query_lower)
                        start = max(0, idx - 100)
                        end = min(len(content), idx + 200)
                        snippet = content[start:end]

                        matches.append({
                            "persona": persona,
                            "file": md_file.name,
                            "snippet": snippet,
                            "relevance": content.lower().count(query_lower)  # Simple relevance score
                        })

                except Exception:
                    continue

        # Sort by relevance and limit
        matches.sort(key=lambda x: x["relevance"], reverse=True)
        return matches[:limit]

    async def _search_persona_memory(
        self,
        query: str,
        persona_name: str | None,
        limit: int,
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """
        Search persona session logs from database.
        """
        stmt = select(PersonaMemory)
        if persona_name:
            stmt = stmt.where(PersonaMemory.persona_name == persona_name)

        result = await db.execute(stmt)
        memories = result.scalars().all()

        matches = []
        query_lower = query.lower()

        for memory in memories:
            # Search in session_log
            session_log = memory.session_log or []
            for entry in session_log:
                if query_lower in entry.lower():
                    matches.append({
                        "persona": memory.persona_name,
                        "source": "session_log",
                        "content": entry,
                        "type": "log_entry"
                    })

            # Search in session_log_detailed
            detailed = memory.session_log_detailed or []
            for entry in detailed:
                if query_lower in entry.lower():
                    matches.append({
                        "persona": memory.persona_name,
                        "source": "session_log_detailed",
                        "content": entry,
                        "type": "detailed_entry"
                    })

        return matches[:limit]

    async def _search_user_profile(self, query: str, db: AsyncSession) -> Dict[str, Any]:
        """
        Search user profile for relevant attributes.
        """
        result = await db.execute(select(UserProfile).where(UserProfile.id == 1))
        profile = result.scalar_one_or_none()

        if not profile:
            return {"found": False}

        query_lower = query.lower()
        matches = {}

        # Search in attributes
        if profile.attributes:
            attrs = profile.attributes
            if query_lower in str(attrs).lower():
                matches["attributes"] = attrs

        # Search in preferences
        if profile.preferences:
            prefs = profile.preferences
            if query_lower in str(prefs).lower():
                matches["preferences"] = prefs

        # Search in knowledge_tracker
        if profile.knowledge_tracker:
            kt = profile.knowledge_tracker
            if query_lower in str(kt).lower():
                matches["knowledge_tracker"] = kt

        return {
            "found": len(matches) > 0,
            "user_name": profile.name,
            "matches": matches
        }

    async def _synthesize_memories(
        self,
        query: str,
        results: Dict[str, Any],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Use LLM to synthesize memory search results into coherent answer.
        """
        # Build context from results
        context_parts = []

        episodic = results.get("episodic", [])
        if episodic:
            context_parts.append("Knowledge Files:")
            for mem in episodic[:5]:  # Top 5
                context_parts.append(f"- [{mem.get('file', 'unknown')}]: {mem.get('snippet', '')}")

        if not context_parts:
            return {
                "answer": "Nenhuma memória relevante encontrada para essa consulta.",
                "confidence": 0.0
            }

        context = "\n".join(context_parts)

        prompt = f"""Com base nas memórias encontradas, responda a pergunta do usuário de forma concisa e precisa.

Pergunta: {query}

Memórias:
{context}

Forneça uma resposta sintetizada em JSON:
{{
    "answer": "resposta clara e direta",
    "key_points": ["ponto1", "ponto2"],
    "confidence": 0.0-1.0,
    "sources_used": ["fonte1", "fonte2"]
}}
"""

        response = await self._call_llm(
            prompt=prompt,
            model=getattr(self.llm.settings, "google_model_memory", self.default_model),
            schema={
                "type": "object",
                "properties": {
                    "answer": {"type": "string"},
                    "key_points": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                    "sources_used": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["answer", "confidence"]
            }
        )

        return response
