"""
Search Worker - Specialized agent for web search via Google Custom Search Engine.

Uses the existing SearchService to perform web searches and optionally
synthesizes results with an LLM for a coherent summary.

Capabilities:
- Web search via Google CSE API
- Result synthesis with LLM summarization
- Quota-aware (respects daily search limits)

ReAct mode: Search → analyze results → refine search if needed.
"""
import time
import json
import logging
from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import AgentWorkerTask
from src.services.workers.base_worker import BaseWorker
from src.services.workers.react_loop import ToolDefinition, ToolResult
from src.services.search_service import SearchService

logger = logging.getLogger("ahri.worker.search")


class SearchWorker(BaseWorker):
    """Worker for web search via Google CSE with ReAct loop."""

    # ── ReAct Configuration ──
    REACT_ENABLED = True
    REACT_MAX_ITERATIONS = 3  # Search is quota-limited, fewer iterations
    REACT_TOKEN_BUDGET = 4000

    ROLE_PROMPT = (
        "[ROLE: Research Analyst]\n"
        "You perform web searches and synthesize findings into actionable answers.\n"
        "Prioritize authoritative sources. Cross-reference multiple results.\n"
        "Distinguish facts from opinions. Note when information may be outdated.\n"
        "If initial search results are insufficient, refine your query and search again."
    )

    def __init__(self, llm_service):
        super().__init__(
            llm_service=llm_service,
            worker_type="Search",
            default_model="LITE"
        )
        self._last_search_results = []  # Cache for synthesis tool

    def get_tools(self) -> list[ToolDefinition]:
        """Define tools for ReAct mode."""
        return [
            ToolDefinition(
                name="web_search",
                description="Search the web via Google. Input: {\"query\": str, \"max_results\": int}",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer"}
                    },
                    "required": ["query"]
                },
                handler=self._tool_web_search,
            ),
            ToolDefinition(
                name="synthesize_results",
                description="Synthesize the last search results into a summary. Input: {\"focus\": str}",
                parameters={
                    "type": "object",
                    "properties": {
                        "focus": {"type": "string"}
                    },
                    "required": ["focus"]
                },
                handler=self._tool_synthesize,
            ),
        ]

    # ── ReAct Tool Handlers ──────────────────────────────────────────

    async def _tool_web_search(self, params: dict) -> ToolResult:
        """Tool wrapper for web search."""
        try:
            query = params.get("query", "")
            max_results = params.get("max_results", 5)
            if not query:
                return ToolResult(tool_name="web_search", success=False, output="", error="Empty query")

            # Note: SearchService needs a db session, but for tool mode we create a minimal one
            # The search itself doesn't write to DB, so we pass None and handle inside
            from src.services.search_service import SearchService
            search_service = SearchService(None)
            search_result = await search_service.search(query, max_results=max_results)

            if search_result.get("error"):
                return ToolResult(tool_name="web_search", success=False, output="", error=search_result["error"])

            results = search_result.get("results", [])
            self._last_search_results = results

            listing = "\n\n".join(
                f"{i+1}. **{r.get('title', 'No title')}**\n   URL: {r.get('link', '')}\n   {r.get('snippet', '')}"
                for i, r in enumerate(results)
            )
            return ToolResult(
                tool_name="web_search", success=True,
                output=f"Found {len(results)} results for '{query}':\n\n{listing}"
            )
        except Exception as e:
            return ToolResult(tool_name="web_search", success=False, output="", error=str(e))

    async def _tool_synthesize(self, params: dict) -> ToolResult:
        """Tool wrapper for synthesizing search results."""
        try:
            if not self._last_search_results:
                return ToolResult(
                    tool_name="synthesize_results", success=False, output="",
                    error="No search results to synthesize. Run web_search first."
                )

            focus = params.get("focus", "general summary")
            results_text = "\n\n".join(
                f"**{r.get('title', '')}** ({r.get('link', '')})\n{r.get('snippet', '')}"
                for r in self._last_search_results
            )

            prompt = (
                f"Synthesize these search results with focus on: {focus}\n\n"
                f"{results_text}\n\n"
                f"Provide a clear, concise summary in 3-5 sentences."
            )
            summary = await self._call_llm(prompt, model=self.default_model)
            return ToolResult(tool_name="synthesize_results", success=True, output=summary)
        except Exception as e:
            return ToolResult(tool_name="synthesize_results", success=False, output="", error=str(e))

    async def execute(
        self,
        db: AsyncSession,
        execution_id: int,
        input_data: Dict[str, Any]
    ) -> AgentWorkerTask:
        """
        Perform a web search and optionally synthesize results.

        Input format:
        {
            "query": "search terms",
            "max_results": 5,           (optional, default: 5)
            "synthesize": true,          (optional, default: true)
            "_orchestrator_params": {}   (injected by orchestrator)
        }
        """
        task = await self._create_task_record(db, execution_id, input_data)
        start_time = time.time()

        try:
            query = input_data.get("query", "")
            max_results = input_data.get("max_results", 5)
            synthesize = input_data.get("synthesize", True)

            if not query:
                return await self._fail_task(db, task, "No search query provided", start_time)

            # Extract orchestrator params
            orch_params = input_data.get("_orchestrator_params", {})
            api_key = orch_params.get("api_key")
            thinking_budget = orch_params.get("thinking_budget", 0)

            logger.info(f"[SearchWorker] Searching: '{query}' (max: {max_results})")

            # Use SearchService to perform the search
            search_service = SearchService(db)
            search_result = await search_service.search(query, max_results=max_results)

            if search_result.get("error"):
                return await self._fail_task(
                    db, task,
                    f"Search failed: {search_result['error']}",
                    start_time
                )

            results = search_result.get("results", [])
            remaining_quota = search_result.get("remaining_quota", 0)

            output = {
                "query": query,
                "results": results,
                "result_count": len(results),
                "remaining_quota": remaining_quota,
            }

            # Optionally synthesize results with LLM
            if synthesize and results:
                results_text = "\n\n".join(
                    f"**{r['title']}** ({r['link']})\n{r['snippet']}"
                    for r in results
                )
                synthesis_prompt = (
                    f"Based on these web search results for '{query}', "
                    f"provide a concise, informative summary:\n\n{results_text}\n\n"
                    f"Summarize the key findings in 2-4 sentences."
                )

                summary = await self._call_llm(
                    synthesis_prompt,
                    model=self.llm.settings.google_model_search,
                    api_key=api_key,
                    thinking_budget=thinking_budget,
                )
                output["summary"] = summary

            tokens_used = len(query) // 4 + sum(len(str(r)) for r in results) // 4
            return await self._complete_task(db, task, output, tokens_used, start_time)

        except Exception as e:
            logger.error(f"[SearchWorker] Error: {e}")
            return await self._fail_task(db, task, str(e), start_time)
