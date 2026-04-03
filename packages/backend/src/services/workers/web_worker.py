"""
Web Worker - Specialized agent for web content fetching and scraping.
Uses the configured agent model for content summarization and extraction.

Capabilities:
- Fetch URL content
- Extract main text from HTML
- Summarize web pages
- Extract structured data (links, images, metadata)

ReAct mode: Iteratively fetch → analyze → extract from web pages.
"""
import json
import requests
from bs4 import BeautifulSoup
from typing import Any, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urljoin, urlparse

from src.models.database import AgentWorkerTask
from src.services.workers.base_worker import BaseWorker
from src.services.workers.react_loop import ToolDefinition, ToolResult


class WebWorker(BaseWorker):
    """Worker for web content fetching and scraping with ReAct loop."""

    # ── ReAct Configuration ──
    REACT_ENABLED = True
    REACT_MAX_ITERATIONS = 3  # Web ops are slower, fewer iterations
    REACT_TOKEN_BUDGET = 4000

    ROLE_PROMPT = (
        "[ROLE: Web Content Analyst]\n"
        "You fetch, parse, and analyze web page content.\n"
        "Extract the most relevant information, ignoring navigation/ads/boilerplate.\n"
        "For summaries: capture key points in 2-3 paragraphs.\n"
        "For data extraction: return structured JSON matching the requested schema.\n"
        "Always include the source URL in your output."
    )

    def __init__(self, llm_service):
        super().__init__(
            llm_service=llm_service,
            worker_type="Web",
            default_model="LITE"
        )
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

    def get_tools(self) -> list[ToolDefinition]:
        """Define tools for ReAct mode."""
        return [
            ToolDefinition(
                name="fetch_page",
                description="Fetch a URL and return its text content, title, and metadata. Input: {\"url\": str}",
                parameters={
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"]
                },
                handler=self._tool_fetch_page,
            ),
            ToolDefinition(
                name="summarize_text",
                description="Summarize text content using LLM. Input: {\"text\": str, \"title\": str}",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "title": {"type": "string"}
                    },
                    "required": ["text"]
                },
                handler=self._tool_summarize_text,
            ),
            ToolDefinition(
                name="extract_links",
                description="Extract all links from previously fetched page HTML. Input: {\"url\": str}",
                parameters={
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"]
                },
                handler=self._tool_extract_links,
            ),
        ]

    # ── ReAct Tool Handlers ──────────────────────────────────────────

    async def _tool_fetch_page(self, params: dict) -> ToolResult:
        """Tool wrapper for page fetch."""
        try:
            result = await self._fetch_page(params.get("url", ""))
            if result.get("error"):
                return ToolResult(tool_name="fetch_page", success=False, output="", error=result["error"])
            text = result.get("text", "")[:3000]  # Truncate for context budget
            return ToolResult(
                tool_name="fetch_page", success=True,
                output=f"Title: {result.get('title', '')}\nURL: {result.get('url')}\n"
                       f"Status: {result.get('status_code')}\nLength: {result.get('text_length', 0)} chars\n\n{text}"
            )
        except Exception as e:
            return ToolResult(tool_name="fetch_page", success=False, output="", error=str(e))

    async def _tool_summarize_text(self, params: dict) -> ToolResult:
        """Tool wrapper for text summarization via LLM."""
        try:
            page_data = {"text": params.get("text", ""), "title": params.get("title", "")}
            result = await self._summarize_page(page_data, None)
            analysis = result.get("analysis", {})
            if isinstance(analysis, dict):
                summary = analysis.get("summary", "")
                points = analysis.get("key_points", [])
                output = f"Summary: {summary}\n\nKey points:\n" + "\n".join(f"- {p}" for p in points)
            else:
                output = str(analysis)
            return ToolResult(tool_name="summarize_text", success=True, output=output)
        except Exception as e:
            return ToolResult(tool_name="summarize_text", success=False, output="", error=str(e))

    async def _tool_extract_links(self, params: dict) -> ToolResult:
        """Tool wrapper for link extraction."""
        try:
            url = params.get("url", "")
            page_data = await self._fetch_page(url)
            if page_data.get("error"):
                return ToolResult(tool_name="extract_links", success=False, output="", error=page_data["error"])
            result = await self._extract_links(page_data, url)
            links = result.get("links", {})
            count = links.get("count", {})
            all_links = links.get("all", [])[:20]  # Limit to 20
            listing = "\n".join(f"- [{l.get('text', 'no text')[:50]}]({l.get('url', '')})" for l in all_links)
            return ToolResult(
                tool_name="extract_links", success=True,
                output=f"Found {count.get('total', 0)} links ({count.get('internal', 0)} internal, {count.get('external', 0)} external)\n\n{listing}"
            )
        except Exception as e:
            return ToolResult(tool_name="extract_links", success=False, output="", error=str(e))

    async def execute(
        self,
        db: AsyncSession,
        execution_id: int,
        input_data: Dict[str, Any]
    ) -> AgentWorkerTask:
        """
        Fetch and process web content.

        Input format:
        {
            "url": "https://example.com",
            "action": "fetch" | "summarize" | "extract_links" | "extract_data",
            "extract_schema": {...} (optional, for structured extraction)
        }
        """
        import time
        start_time = time.time()
        task = await self._create_task_record(db, execution_id, input_data)

        try:
            url = input_data.get("url", "")
            action = input_data.get("action", "fetch")

            # Fetch page
            page_data = await self._fetch_page(url)

            if page_data.get("error"):
                return await self._fail_task(db, task, page_data["error"], start_time)

            # Process based on action
            if action == "summarize":
                result = await self._summarize_page(page_data, db)
            elif action == "extract_links":
                result = await self._extract_links(page_data, url)
            elif action == "extract_data":
                result = await self._extract_structured_data(page_data, input_data, db)
            else:  # fetch
                result = page_data

            tokens = self._estimate_tokens(str(result))
            return await self._complete_task(db, task, result, tokens, start_time)

        except Exception as e:
            return await self._fail_task(db, task, str(e), start_time)

    MAX_RESPONSE_SIZE = 50 * 1024 * 1024  # 50MB

    async def _fetch_page(self, url: str) -> Dict[str, Any]:
        """Fetch and parse HTML page."""
        try:
            response = requests.get(url, headers=self.headers, timeout=15, stream=True)
            response.raise_for_status()

            # Check Content-Length before downloading
            content_length = response.headers.get('Content-Length')
            if content_length and int(content_length) > self.MAX_RESPONSE_SIZE:
                return {"error": f"Response too large: {int(content_length)} bytes (max {self.MAX_RESPONSE_SIZE})"}

            # Read with size limit
            content = b""
            for chunk in response.iter_content(chunk_size=8192):
                content += chunk
                if len(content) > self.MAX_RESPONSE_SIZE:
                    return {"error": f"Response exceeded {self.MAX_RESPONSE_SIZE} bytes limit"}
            response._content = content

            soup = BeautifulSoup(response.text, 'html.parser')

            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()

            # Get text
            text = soup.get_text()

            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)

            # Get metadata
            title = soup.find('title')
            title_text = title.string if title else ""

            meta_description = soup.find('meta', attrs={'name': 'description'})
            description = meta_description.get('content', '') if meta_description else ""

            return {
                "url": url,
                "title": title_text,
                "description": description,
                "text": text,
                "text_length": len(text),
                "status_code": response.status_code,
                "html": response.text
            }

        except requests.RequestException as e:
            return {"error": f"Failed to fetch URL: {str(e)}"}

    async def _summarize_page(self, page_data: Dict, db: AsyncSession) -> Dict[str, Any]:
        """Summarize web page content using LLM."""
        text = page_data.get("text", "")
        title = page_data.get("title", "")

        # Limit text to avoid token overflow (first 8000 chars)
        text_sample = text[:8000]

        prompt = f"""Resuma o conteúdo da seguinte página web:

Título: {title}

Conteúdo:
{text_sample}

Forneça um resumo estruturado em JSON:
{{
    "summary": "resumo conciso em 2-3 parágrafos",
    "key_points": ["ponto1", "ponto2", "ponto3"],
    "main_topic": "tópico principal",
    "sentiment": "positive|neutral|negative",
    "is_article": true/false
}}
"""

        response = await self._call_llm(
            prompt=prompt,
            model=self.default_model,
            schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "key_points": {"type": "array", "items": {"type": "string"}},
                    "main_topic": {"type": "string"},
                    "sentiment": {"type": "string"},
                    "is_article": {"type": "boolean"}
                },
                "required": ["summary", "key_points", "main_topic"]
            }
        )

        return {
            **page_data,
            "analysis": response
        }

    async def _extract_links(self, page_data: Dict, base_url: str) -> Dict[str, Any]:
        """Extract all links from page."""
        html = page_data.get("html", "")
        soup = BeautifulSoup(html, 'html.parser')

        links = []
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            absolute_url = urljoin(base_url, href)
            text = a_tag.get_text(strip=True)

            links.append({
                "url": absolute_url,
                "text": text,
                "is_external": urlparse(absolute_url).netloc != urlparse(base_url).netloc
            })

        # Categorize links
        internal = [l for l in links if not l["is_external"]]
        external = [l for l in links if l["is_external"]]

        return {
            "url": page_data.get("url"),
            "title": page_data.get("title"),
            "links": {
                "all": links,
                "internal": internal,
                "external": external,
                "count": {
                    "total": len(links),
                    "internal": len(internal),
                    "external": len(external)
                }
            }
        }

    async def _extract_structured_data(
        self,
        page_data: Dict,
        input_data: Dict,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Extract structured data based on schema using LLM."""
        text = page_data.get("text", "")[:8000]
        extract_schema = input_data.get("extract_schema", {})

        prompt = f"""Extraia os seguintes dados estruturados da página web:

Schema desejado: {extract_schema}

Conteúdo da página:
{text}

Retorne os dados extraídos no formato JSON especificado pelo schema.
Se algum campo não for encontrado, use null.
"""

        response = await self._call_llm(
            prompt=prompt,
            model=self.default_model,
            schema=extract_schema if extract_schema else None
        )

        return {
            "url": page_data.get("url"),
            "extracted_data": response
        }
