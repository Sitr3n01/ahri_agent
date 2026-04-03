"""
Browser Worker - Specialized agent for browser automation using Playwright.
Uses Gemini Flash for intelligent navigation and interaction.

Capabilities:
- Navigate to URLs
- Click elements
- Fill forms
- Extract data from dynamic pages
- Take screenshots
- Handle JavaScript-heavy sites
"""
import logging
from typing import Any, Dict, List

logger = logging.getLogger("ahri.worker.browser")
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import AgentWorkerTask
from src.services.workers.base_worker import BaseWorker


class BrowserWorker(BaseWorker):
    """
    Worker for browser automation tasks.

    NOTE: Requires Playwright to be installed:
        pip install playwright
        playwright install chromium
    """

    ROLE_PROMPT = (
        "[ROLE: Browser Automation Agent]\n"
        "You automate browser interactions: navigate, click, fill forms, extract data.\n"
        "Wait for page loads before interacting. Handle dynamic content gracefully.\n"
        "For extraction: use CSS selectors when provided, LLM-guided otherwise.\n"
        "Report navigation state (current URL, page title) after each action.\n"
        "Output: JSON with action results and current browser state."
    )

    def __init__(self, llm_service):
        super().__init__(
            llm_service=llm_service,
            worker_type="Browser",
            default_model="LITE"
        )
        self.browser = None
        self.playwright_available = False

        try:
            from playwright.async_api import async_playwright
            self.async_playwright = async_playwright
            self.playwright_available = True
        except ImportError:
            pass

    async def execute(
        self,
        db: AsyncSession,
        execution_id: int,
        input_data: Dict[str, Any]
    ) -> AgentWorkerTask:
        """
        Execute browser automation task.

        Input format:
        {
            "action": "navigate" | "click" | "fill_form" | "extract" | "screenshot",
            "url": "https://example.com",
            "selector": "CSS selector",       (for click)
            "form_data": {...},               (for fill_form)
            "extract_selectors": {...},       (for extract)
            "wait_for": "selector",           (optional)
            "headless": true/false            (default: true)
        }
        """
        if not self.playwright_available:
            # Return error task
            task = await self._create_task_record(db, execution_id, input_data)
            task.error = "Playwright not installed. Run: pip install playwright && playwright install chromium"
            await db.commit()
            await db.refresh(task)
            return task

        import time
        start_time = time.time()
        task = await self._create_task_record(db, execution_id, input_data)

        try:
            action = input_data.get("action", "navigate")

            # Start Playwright
            async with self.async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=input_data.get("headless", True)
                )
                page = await browser.new_page()

                if action == "navigate":
                    result = await self._navigate(page, input_data)
                elif action == "click":
                    result = await self._click_element(page, input_data)
                elif action == "fill_form":
                    result = await self._fill_form(page, input_data)
                elif action == "extract":
                    result = await self._extract_data(page, input_data, db)
                elif action == "screenshot":
                    result = await self._take_screenshot(page, input_data)
                else:
                    raise ValueError(f"Unknown action: {action}")

                await browser.close()

            tokens = self._estimate_tokens(str(result))
            return await self._complete_task(db, task, result, tokens, start_time)

        except Exception as e:
            return await self._fail_task(db, task, str(e), start_time)

    async def _navigate(self, page, input_data: Dict) -> Dict[str, Any]:
        """Navigate to URL and wait for page load."""
        url = input_data.get("url", "")
        wait_for = input_data.get("wait_for")

        await page.goto(url, wait_until="domcontentloaded")

        if wait_for:
            await page.wait_for_selector(wait_for, timeout=10000)

        title = await page.title()
        current_url = page.url

        return {
            "navigated": True,
            "url": current_url,
            "title": title,
            "status": "success"
        }

    async def _click_element(self, page, input_data: Dict) -> Dict[str, Any]:
        """Click element by selector."""
        url = input_data.get("url", "")
        selector = input_data.get("selector", "")

        if url:
            await page.goto(url, wait_until="domcontentloaded")

        # Wait for element and click
        await page.wait_for_selector(selector, timeout=10000)
        await page.click(selector)

        # Wait for navigation if triggered
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            logger.debug("networkidle wait timed out after click, continuing")

        return {
            "clicked": True,
            "selector": selector,
            "current_url": page.url
        }

    async def _fill_form(self, page, input_data: Dict) -> Dict[str, Any]:
        """Fill form fields and optionally submit."""
        url = input_data.get("url", "")
        form_data = input_data.get("form_data", {})
        submit_selector = input_data.get("submit_selector")

        if url:
            await page.goto(url, wait_until="domcontentloaded")

        # Fill each field
        filled_fields = []
        failed_fields = []
        for selector, value in form_data.items():
            try:
                await page.fill(selector, str(value))
                filled_fields.append(selector)
            except Exception as e:
                logger.warning(f"Failed to fill form field '{selector}': {e}")
                failed_fields.append(f"{selector}: {str(e)}")

        # Submit if requested
        submitted = False
        if submit_selector:
            await page.click(submit_selector)
            await page.wait_for_load_state("networkidle", timeout=10000)
            submitted = True

        all_succeeded = len(failed_fields) == 0
        return {
            "form_filled": all_succeeded,
            "fields_filled": filled_fields,
            "fields_failed": failed_fields,
            "submitted": submitted,
            "current_url": page.url
        }

    async def _extract_data(self, page, input_data: Dict, db: AsyncSession) -> Dict[str, Any]:
        """Extract data from page using selectors or LLM intelligence."""
        url = input_data.get("url", "")
        extract_selectors = input_data.get("extract_selectors", {})

        if url:
            await page.goto(url, wait_until="domcontentloaded")

        # Simple extraction using selectors
        if extract_selectors:
            extracted = {}
            for key, selector in extract_selectors.items():
                try:
                    element = await page.query_selector(selector)
                    if element:
                        extracted[key] = await element.text_content()
                    else:
                        extracted[key] = None
                except Exception as e:
                    logger.warning(f"Failed to extract '{key}' with selector '{selector}': {e}")
                    extracted[key] = None

            return {
                "extracted_data": extracted,
                "url": page.url,
                "method": "selector"
            }

        # LLM-guided extraction (get page content and use LLM to extract)
        else:
            content = await page.content()
            text = await page.evaluate("document.body.innerText")

            # Use LLM to intelligently extract data
            prompt = f"""Extraia informações relevantes desta página web.

URL: {page.url}
Título: {await page.title()}

Conteúdo (primeiros 5000 chars):
{text[:5000]}

Identifique e extraia:
1. Título/Nome principal
2. Descrição/Resumo
3. Dados estruturados importantes (preços, datas, nomes, etc)
4. Links relevantes

Retorne em JSON:
{{
    "main_title": "título",
    "description": "descrição",
    "structured_data": {{}},
    "important_links": []
}}
"""

            response = await self._call_llm(
                prompt=prompt,
                model=self.default_model,
                schema={
                    "type": "object",
                    "properties": {
                        "main_title": {"type": "string"},
                        "description": {"type": "string"},
                        "structured_data": {"type": "object"},
                        "important_links": {"type": "array"}
                    }
                }
            )

            return {
                "extracted_data": response,
                "url": page.url,
                "method": "llm-guided"
            }

    async def _take_screenshot(self, page, input_data: Dict) -> Dict[str, Any]:
        """Take screenshot of page."""
        import base64
        from pathlib import Path

        url = input_data.get("url", "")
        output_path = input_data.get("output_path", "screenshot.png")
        full_page = input_data.get("full_page", False)

        if url:
            await page.goto(url, wait_until="domcontentloaded")

        # Take screenshot
        screenshot_bytes = await page.screenshot(full_page=full_page)

        # Save to file
        Path(output_path).write_bytes(screenshot_bytes)

        # Also return base64 for inline display
        screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return {
            "screenshot_taken": True,
            "output_path": output_path,
            "screenshot_base64": screenshot_base64,
            "url": page.url,
            "full_page": full_page,
            "size_kb": len(screenshot_bytes) / 1024
        }
