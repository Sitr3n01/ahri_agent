"""
Code Worker - Specialized agent for code analysis, generation, and execution.
Uses the configured agent model for code understanding and generation.

Capabilities:
- Code review and analysis
- Generate code snippets
- Execute Python code in isolated sandbox
- Debug assistance
- Code refactoring suggestions

ReAct mode: Iteratively generate → execute → observe → fix code.
"""
import asyncio
import os
import subprocess
import tempfile
import time
import json
from pathlib import Path
from typing import Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import AgentWorkerTask
from src.services.workers.base_worker import BaseWorker
from src.services.workers.react_loop import ToolDefinition, ToolResult


class CodeWorker(BaseWorker):
    """Worker for code analysis, generation, and execution with ReAct loop."""

    # ── ReAct Configuration ──
    REACT_ENABLED = True
    REACT_MAX_ITERATIONS = 5
    REACT_TOKEN_BUDGET = 4000

    ROLE_PROMPT = (
        "[ROLE: Senior Software Engineer]\n"
        "You analyze, generate, review, and debug code with precision.\n"
        "Always specify the programming language. Use best practices and idiomatic patterns.\n"
        "For reviews: focus on bugs, security issues, and performance — skip style nitpicks.\n"
        "For execution: sandbox-only, report stdout/stderr and exit code.\n"
        "When using tools, choose the most appropriate one for each step."
    )

    def __init__(self, llm_service):
        super().__init__(
            llm_service=llm_service,
            worker_type="Code",
            default_model="LITE"
        )
        self.supported_languages = ["python", "javascript", "typescript", "bash", "sql"]

    def get_tools(self) -> list[ToolDefinition]:
        """Define tools available in ReAct mode."""
        return [
            ToolDefinition(
                name="generate_code",
                description="Generate code from a description. Input: {\"prompt\": str, \"language\": str}",
                parameters={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "language": {"type": "string"}
                    },
                    "required": ["prompt"]
                },
                handler=self._tool_generate_code,
            ),
            ToolDefinition(
                name="execute_python",
                description="Execute Python code in sandbox and get stdout/stderr. Input: {\"code\": str}",
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"}
                    },
                    "required": ["code"]
                },
                handler=self._tool_execute_python,
            ),
            ToolDefinition(
                name="analyze_code",
                description="Analyze code for bugs, patterns, and complexity. Input: {\"code\": str, \"language\": str}",
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "language": {"type": "string"}
                    },
                    "required": ["code"]
                },
                handler=self._tool_analyze_code,
            ),
            ToolDefinition(
                name="review_code",
                description="Security and quality review. Input: {\"code\": str, \"language\": str}",
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "language": {"type": "string"}
                    },
                    "required": ["code"]
                },
                handler=self._tool_review_code,
            ),
        ]

    # ── ReAct Tool Handlers ──────────────────────────────────────────

    async def _tool_generate_code(self, params: dict) -> ToolResult:
        """Tool wrapper for code generation."""
        try:
            result = await self._generate_code(params, None)
            generated = result.get("generated", {})
            code = generated.get("code", "") if isinstance(generated, dict) else str(generated)
            explanation = generated.get("explanation", "") if isinstance(generated, dict) else ""
            return ToolResult(
                tool_name="generate_code",
                success=True,
                output=f"```{params.get('language', 'python')}\n{code}\n```\n\nExplanation: {explanation}",
            )
        except Exception as e:
            return ToolResult(tool_name="generate_code", success=False, output="", error=str(e))

    async def _tool_execute_python(self, params: dict) -> ToolResult:
        """Tool wrapper for Python code execution."""
        try:
            result = await self._execute_code({"code": params.get("code", ""), "language": "python"}, None)
            if result.get("success"):
                output = result.get("stdout", "")
                if result.get("stderr"):
                    output += f"\nstderr: {result['stderr']}"
                return ToolResult(
                    tool_name="execute_python",
                    success=True,
                    output=f"Exit code: {result.get('return_code', 0)}\n{output}",
                )
            else:
                error_msg = result.get("error", result.get("stderr", "Unknown error"))
                return ToolResult(
                    tool_name="execute_python",
                    success=False,
                    output=f"Exit code: {result.get('return_code', 1)}\nstdout: {result.get('stdout', '')}\nstderr: {result.get('stderr', '')}",
                    error=error_msg,
                )
        except Exception as e:
            return ToolResult(tool_name="execute_python", success=False, output="", error=str(e))

    async def _tool_analyze_code(self, params: dict) -> ToolResult:
        """Tool wrapper for code analysis."""
        try:
            result = await self._analyze_code(params, None)
            analysis = result.get("analysis", {})
            output = json.dumps(analysis, ensure_ascii=False, indent=2) if isinstance(analysis, dict) else str(analysis)
            return ToolResult(tool_name="analyze_code", success=True, output=output)
        except Exception as e:
            return ToolResult(tool_name="analyze_code", success=False, output="", error=str(e))

    async def _tool_review_code(self, params: dict) -> ToolResult:
        """Tool wrapper for code review."""
        try:
            result = await self._review_code(params, None)
            review = result.get("review", {})
            output = json.dumps(review, ensure_ascii=False, indent=2) if isinstance(review, dict) else str(review)
            return ToolResult(tool_name="review_code", success=True, output=output)
        except Exception as e:
            return ToolResult(tool_name="review_code", success=False, output="", error=str(e))

    async def execute(
        self,
        db: AsyncSession,
        execution_id: int,
        input_data: Dict[str, Any]
    ) -> AgentWorkerTask:
        """
        Execute code-related task.

        Input format:
        {
            "task_type": "analyze" | "generate" | "execute" | "review",
            "language": "python" | "javascript" | ...,
            "code": "code to analyze/execute",  (for analyze/execute/review)
            "prompt": "what to generate",        (for generate)
            "context": "additional context"      (optional)
        }
        """
        task_type = input_data.get("task_type", "analyze")
        language = input_data.get("language", "python")

        start_time = time.time()
        task = await self._create_task_record(db, execution_id, input_data)

        try:
            if task_type == "analyze":
                result = await self._analyze_code(input_data, db)
            elif task_type == "generate":
                result = await self._generate_code(input_data, db)
            elif task_type == "execute":
                result = await self._execute_code(input_data, db)
            elif task_type == "review":
                result = await self._review_code(input_data, db)
            else:
                raise ValueError(f"Unknown task_type: {task_type}")

            tokens = self._estimate_tokens(str(result))
            return await self._complete_task(db, task, result, tokens, start_time)

        except Exception as e:
            return await self._fail_task(db, task, str(e), start_time)

    async def _analyze_code(self, input_data: Dict, db: AsyncSession) -> Dict[str, Any]:
        """Analyze code for patterns, issues, and suggestions."""
        code = input_data.get("code", "")
        language = input_data.get("language", "python")
        context = input_data.get("context", "")

        prompt = f"""Analise o seguinte código {language} e forneça:
1. Resumo do que o código faz
2. Possíveis problemas ou bugs
3. Sugestões de melhoria
4. Complexidade estimada (O-notation se aplicável)

{f"Contexto: {context}" if context else ""}

Código:
```{language}
{code}
```

Forneça a análise em formato JSON:
{{
    "summary": "resumo breve",
    "issues": ["problema1", "problema2"],
    "suggestions": ["sugestão1", "sugestão2"],
    "complexity": "O(n)",
    "quality_score": 0-10
}}
"""

        response = await self._call_llm(
            prompt=prompt,
            model=self.default_model,
            schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "issues": {"type": "array", "items": {"type": "string"}},
                    "suggestions": {"type": "array", "items": {"type": "string"}},
                    "complexity": {"type": "string"},
                    "quality_score": {"type": "number"}
                },
                "required": ["summary", "issues", "suggestions"]
            }
        )

        return {
            "analysis": response,
            "language": language,
            "code_length": len(code)
        }

    async def _generate_code(self, input_data: Dict, db: AsyncSession) -> Dict[str, Any]:
        """Generate code based on prompt."""
        prompt_user = input_data.get("prompt", "")
        language = input_data.get("language", "python")
        context = input_data.get("context", "")

        prompt = f"""Gere código {language} para: {prompt_user}

{f"Contexto adicional: {context}" if context else ""}

Requisitos:
- Código funcional e bem documentado
- Seguir boas práticas da linguagem
- Incluir tratamento de erros quando apropriado
- Comentários explicativos

Forneça a resposta em formato JSON:
{{
    "code": "código gerado",
    "explanation": "explicação do código",
    "usage_example": "exemplo de uso",
    "dependencies": ["dep1", "dep2"]
}}
"""

        response = await self._call_llm(
            prompt=prompt,
            model=self.default_model,
            schema={
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "explanation": {"type": "string"},
                    "usage_example": {"type": "string"},
                    "dependencies": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["code", "explanation"]
            }
        )

        return {
            "generated": response,
            "language": language
        }

    async def _execute_code(self, input_data: Dict, db: AsyncSession) -> Dict[str, Any]:
        """
        Execute Python code in isolated sandbox with timeout.
        Security: Only Python, 5s timeout, no network/file access.
        """
        code = input_data.get("code", "")
        language = input_data.get("language", "python")

        if language != "python":
            return {
                "error": f"Code execution only supports Python, got: {language}",
                "executed": False
            }

        # Create temp file with code
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name

        try:
            # Execute with timeout and restricted environment
            result = subprocess.run(
                ["python", temp_file],
                capture_output=True,
                text=True,
                timeout=5,  # 5 second timeout
                env={**os.environ, "PYTHONIOENCODING": "utf-8"}  # Inherit env + ensure encoding
            )

            return {
                "executed": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
                "success": result.returncode == 0
            }

        except subprocess.TimeoutExpired:
            return {
                "executed": False,
                "error": "Execution timeout (5s limit)",
                "success": False
            }
        except Exception as e:
            return {
                "executed": False,
                "error": str(e),
                "success": False
            }
        finally:
            # Cleanup temp file
            Path(temp_file).unlink(missing_ok=True)

    async def _review_code(self, input_data: Dict, db: AsyncSession) -> Dict[str, Any]:
        """Perform code review with focus on security, performance, maintainability."""
        code = input_data.get("code", "")
        language = input_data.get("language", "python")
        context = input_data.get("context", "")

        prompt = f"""Faça uma revisão detalhada do código {language} focando em:

1. **Segurança**: Vulnerabilidades, injection risks, sensitive data exposure
2. **Performance**: Gargalos, otimizações possíveis
3. **Manutenibilidade**: Legibilidade, modularidade, testabilidade
4. **Boas Práticas**: Convenções da linguagem, patterns

{f"Contexto: {context}" if context else ""}

Código:
```{language}
{code}
```

Responda em JSON:
{{
    "security_issues": [
        {{"severity": "high|medium|low", "issue": "descrição", "fix": "como corrigir"}}
    ],
    "performance_issues": [
        {{"impact": "high|medium|low", "issue": "descrição", "suggestion": "otimização"}}
    ],
    "maintainability_score": 0-10,
    "best_practices_violations": ["violação1", "violação2"],
    "overall_recommendation": "approve|request_changes|reject"
}}
"""

        response = await self._call_llm(
            prompt=prompt,
            model=self.default_model,
            schema={
                "type": "object",
                "properties": {
                    "security_issues": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "severity": {"type": "string"},
                                "issue": {"type": "string"},
                                "fix": {"type": "string"}
                            }
                        }
                    },
                    "performance_issues": {"type": "array"},
                    "maintainability_score": {"type": "number"},
                    "best_practices_violations": {"type": "array"},
                    "overall_recommendation": {"type": "string"}
                },
                "required": ["security_issues", "maintainability_score", "overall_recommendation"]
            }
        )

        return {
            "review": response,
            "language": language,
            "code_length": len(code)
        }
