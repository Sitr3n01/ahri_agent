"""
Router Worker - Specialized agent for task classification and worker selection.
Uses the configured agent model for task classification and routing.

Capabilities:
- Classify user tasks into categories
- Select appropriate worker(s) for task
- Detect multi-step workflows
- Estimate task complexity
- Suggest optimal execution order
"""
from typing import Any, Dict, List
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import AgentWorkerTask
from src.services.workers.base_worker import BaseWorker


class RouterWorker(BaseWorker):
    """Worker for intelligent task routing and classification."""

    ENABLE_EVALUATION = False  # Classification is one-shot, no retry benefit

    ROLE_PROMPT = (
        "[ROLE: Task Router & Classifier]\n"
        "You classify tasks and recommend the optimal worker(s) to handle them.\n"
        "Consider task complexity, required capabilities, and execution order.\n"
        "For multi-step tasks, identify dependencies between steps.\n"
        "Output: JSON with 'recommended_workers', 'complexity', and 'reasoning' fields."
    )

    # Worker capabilities mapping
    WORKER_CAPABILITIES = {
        "RAG": {
            "keywords": ["buscar", "pesquisar", "encontrar", "lore", "história", "conhecimento", "documentos"],
            "description": "Search through persona lore and knowledge base documents",
            "cost": "low"
        },
        "Code": {
            "keywords": ["código", "programar", "analisar", "debug", "executar", "script", "função"],
            "description": "Analyze, generate, review, or execute code",
            "cost": "medium"
        },
        "Shell": {
            "keywords": ["comando", "terminal", "arquivo", "pasta", "listar", "criar", "deletar", "mover"],
            "description": "Execute shell commands and file operations",
            "cost": "low"
        },
        "Memory": {
            "keywords": ["lembrar", "memória", "usuário", "perfil", "histórico", "sessão", "conhecimento"],
            "description": "Search user profile, memories, and session history",
            "cost": "low"
        },
        "Web": {
            "keywords": ["site", "página", "web", "url", "http", "baixar", "scraping", "extrair"],
            "description": "Fetch and extract data from web pages",
            "cost": "medium"
        },
        "Vision": {
            "keywords": ["imagem", "foto", "ver", "analisar imagem", "ocr", "texto em imagem", "detectar"],
            "description": "Analyze images, extract text (OCR), detect objects",
            "cost": "high"
        },
        "Browser": {
            "keywords": ["navegar", "clicar", "formulário", "preencher", "automação", "browser", "selenium"],
            "description": "Automate browser interactions (Playwright)",
            "cost": "high"
        }
    }

    def __init__(self, llm_service):
        super().__init__(
            llm_service=llm_service,
            worker_type="Router",
            default_model="LITE"
        )

    async def execute(
        self,
        db: AsyncSession,
        execution_id: int,
        input_data: Dict[str, Any]
    ) -> AgentWorkerTask:
        """
        Classify task and route to appropriate worker(s).

        Input format:
        {
            "task_description": "user's task in natural language",
            "context": "additional context" (optional)
        }
        """
        import time
        start_time = time.time()
        task = await self._create_task_record(db, execution_id, input_data)

        try:
            task_description = input_data.get("task_description", "")
            context = input_data.get("context", "")

            # Classify task
            classification = await self._classify_task(task_description, context, db)

            # Select workers
            selected_workers = await self._select_workers(classification, db)

            # Estimate complexity
            complexity = await self._estimate_complexity(classification, selected_workers, db)

            # Generate execution plan
            execution_plan = await self._generate_execution_plan(
                task_description,
                selected_workers,
                complexity,
                db
            )

            output = {
                "classification": classification,
                "selected_workers": selected_workers,
                "complexity": complexity,
                "execution_plan": execution_plan,
                "routing_confidence": classification.get("confidence", 0.0)
            }
            tokens = self._estimate_tokens(str(output))
            return await self._complete_task(db, task, output, tokens, start_time)

        except Exception as e:
            return await self._fail_task(db, task, str(e), start_time)

    async def _classify_task(
        self,
        task_description: str,
        context: str,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Classify task into categories using LLM."""
        # Build worker info for prompt
        worker_info = "\n".join([
            f"- {name}: {info['description']}"
            for name, info in self.WORKER_CAPABILITIES.items()
        ])

        prompt = f"""Classifique a seguinte tarefa do usuário:

Tarefa: {task_description}
{f"Contexto: {context}" if context else ""}

Workers disponíveis:
{worker_info}

Analise a tarefa e classifique em:
1. Categoria principal (rag, code, shell, memory, web, vision, browser)
2. Categorias secundárias (se a tarefa requer múltiplos workers)
3. Tipo de operação (read, write, analyze, execute, search)
4. Se é tarefa simples (1 worker) ou complexa (múltiplos workers em sequência/paralelo)

Retorne em JSON:
{{
    "primary_category": "categoria principal",
    "secondary_categories": ["cat1", "cat2"],
    "operation_type": "read|write|analyze|execute|search",
    "is_multi_step": true/false,
    "requires_approval": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "explicação da classificação"
}}
"""

        # Use lightweight model for fast routing
        response = await self._call_llm(
            prompt=prompt,
            model=self.default_model,
            schema={
                "type": "object",
                "properties": {
                    "primary_category": {"type": "string"},
                    "secondary_categories": {"type": "array", "items": {"type": "string"}},
                    "operation_type": {"type": "string"},
                    "is_multi_step": {"type": "boolean"},
                    "requires_approval": {"type": "boolean"},
                    "confidence": {"type": "number"},
                    "reasoning": {"type": "string"}
                },
                "required": ["primary_category", "operation_type", "is_multi_step", "confidence"]
            }
        )

        return response

    async def _select_workers(
        self,
        classification: Dict,
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        """Select appropriate workers based on classification."""
        primary = classification.get("primary_category", "").upper()
        secondary = [s.upper() for s in classification.get("secondary_categories", [])]

        selected = []

        # Add primary worker
        if primary in self.WORKER_CAPABILITIES:
            selected.append({
                "worker": primary,
                "priority": "primary",
                "capabilities": self.WORKER_CAPABILITIES[primary]
            })

        # Add secondary workers
        for sec in secondary:
            if sec in self.WORKER_CAPABILITIES and sec != primary:
                selected.append({
                    "worker": sec,
                    "priority": "secondary",
                    "capabilities": self.WORKER_CAPABILITIES[sec]
                })

        return selected

    async def _estimate_complexity(
        self,
        classification: Dict,
        selected_workers: List[Dict],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Estimate task complexity and resource requirements."""
        is_multi_step = classification.get("is_multi_step", False)
        worker_count = len(selected_workers)

        # Calculate cost based on workers
        total_cost = sum(
            {"low": 1, "medium": 2, "high": 3}.get(w["capabilities"]["cost"], 1)
            for w in selected_workers
        )

        # Estimate tokens (rough)
        estimated_tokens = total_cost * 1000  # 1k-3k per worker

        # Estimate time (seconds)
        estimated_time = worker_count * 5  # ~5s per worker

        complexity_level = "simple"
        if total_cost > 4 or worker_count > 2:
            complexity_level = "complex"
        elif total_cost > 2 or is_multi_step:
            complexity_level = "moderate"

        return {
            "level": complexity_level,
            "worker_count": worker_count,
            "estimated_tokens": estimated_tokens,
            "estimated_time_seconds": estimated_time,
            "total_cost_points": total_cost,
            "requires_sequential_execution": is_multi_step
        }

    async def _generate_execution_plan(
        self,
        task_description: str,
        selected_workers: List[Dict],
        complexity: Dict,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Generate step-by-step execution plan."""
        steps = []

        # If sequential (multi-step), order matters
        if complexity.get("requires_sequential_execution"):
            for i, worker_info in enumerate(selected_workers, 1):
                steps.append({
                    "step": i,
                    "worker": worker_info["worker"],
                    "action": f"Execute {worker_info['worker']} worker",
                    "depends_on": i - 1 if i > 1 else None,
                    "parallel": False
                })
        else:
            # Parallel execution possible
            for i, worker_info in enumerate(selected_workers, 1):
                steps.append({
                    "step": i,
                    "worker": worker_info["worker"],
                    "action": f"Execute {worker_info['worker']} worker",
                    "depends_on": None,
                    "parallel": True
                })

        return {
            "steps": steps,
            "total_steps": len(steps),
            "execution_mode": "sequential" if complexity.get("requires_sequential_execution") else "parallel",
            "estimated_duration": complexity.get("estimated_time_seconds"),
            "can_parallelize": not complexity.get("requires_sequential_execution")
        }
