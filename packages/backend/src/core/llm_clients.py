"""
LLM Clients - Abstraçao unificada dos backends LLM.
Usa google-genai SDK (per-instance Client, thread-safe nativo).
"""
import json
import logging
import time
from typing import Optional

import requests
from google import genai
from google.genai import types
from openai import OpenAI

from src.config import get_settings

logger = logging.getLogger("ahri.llm")


class GeminiClient:
    """Cliente Gemini via google-genai SDK.

    Cada instância cria seu próprio genai.Client(api_key=...).
    Thread-safe por design — sem estado global compartilhado.
    """

    def __init__(self, api_key: str = "", model_name: str = ""):
        self.api_key = api_key
        self._masked_key = f"{api_key[:8]}...{api_key[-4:]}" if api_key and len(api_key) > 12 else "***"

        # Garante que o nome do modelo tenha o prefixo 'models/' se necessário
        if model_name and not model_name.startswith("models/") and "/" not in model_name:
            self.model_name = f"models/{model_name}"
        else:
            self.model_name = model_name

        logger.debug(f"GeminiClient init: model={self.model_name!r}, key={self._masked_key}")

        self._client = genai.Client(api_key=api_key) if api_key else None

    def _build_thinking_config(self, reasoning_level: str = "medium") -> Optional[types.ThinkingConfig]:
        """Constrói ThinkingConfig baseado no modelo e nível de raciocínio.

        - Gemini 3.x: usa thinking_level (string: low/medium/high)
        - Gemini 2.5: usa thinking_budget (int: 1024/8192/24576)
        """
        if not reasoning_level or reasoning_level == "off":
            return None

        model_lower = self.model_name.lower()
        is_3x = any(v in model_lower for v in ["3.1", "3.0", "3-flash", "3-pro"])

        if is_3x:
            return types.ThinkingConfig(thinking_level=reasoning_level)
        else:
            budget_map = {"low": 1024, "medium": 8192, "high": 24576}
            budget = budget_map.get(reasoning_level, 8192)
            return types.ThinkingConfig(thinking_budget=budget)

    def create_chat_and_send_stream(
        self,
        system_instruction: str,
        history: list[dict],
        message: str,
        reasoning_level: str = "medium",
    ):
        """Cria chat com histórico e envia mensagem em streaming.

        Retorna iterator de chunks. Substitui create_chat() + send_message(stream=True).
        """
        if not self._client:
            raise RuntimeError("GeminiClient has no API key configured")

        is_gemma = "gemma" in self.model_name.lower()
        sys_inst = None if is_gemma else system_instruction
        thinking = self._build_thinking_config(reasoning_level) if not is_gemma else None

        config = types.GenerateContentConfig(
            system_instruction=sys_inst,
            thinking_config=thinking,
        )

        # Build history no formato do novo SDK
        g_history = []
        if is_gemma:
            g_history.append(types.Content(
                role="user",
                parts=[types.Part(text=f"SYSTEM INSTRUCTIONS:\n{system_instruction}")]
            ))
            g_history.append(types.Content(
                role="model",
                parts=[types.Part(text="Entendido.")]
            ))

        if history:
            for msg in history:
                role = "user" if msg.get("role") == "user" else "model"
                content = str(msg.get("content", "."))
                g_history.append(types.Content(
                    role=role,
                    parts=[types.Part(text=content)]
                ))

        chat = self._client.chats.create(
            model=self.model_name,
            config=config,
            history=g_history,
        )

        try:
            stream = chat.send_message_stream(message)
            for chunk in stream:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"Gemini Streaming Error ({self.model_name}): {str(e)}")
            if "404" in str(e):
                yield f"[Gemini Error] Modelo '{self.model_name}' não encontrado (404). Verifique o nome exato no painel de Configurações > Teste de Modelos."
            else:
                yield f"[Gemini Error] {str(e)}"

    def generate_content_stream(
        self,
        contents,
        system_instruction: Optional[str] = None,
        reasoning_level: str = "medium",
    ):
        """Gera conteúdo em streaming (para multimodal: text + images + files).

        Substitui create_model() + model.generate_content(stream=True).
        """
        if not self._client:
            raise RuntimeError("GeminiClient has no API key configured")

        is_gemma = "gemma" in self.model_name.lower()
        thinking = self._build_thinking_config(reasoning_level) if not is_gemma else None

        config = types.GenerateContentConfig(
            system_instruction=None if is_gemma else system_instruction,
            thinking_config=thinking,
        )

        try:
            stream = self._client.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                config=config,
            )
            for chunk in stream:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"Gemini Multi-modal Error: {str(e)}")
            yield f"[Gemini Error] {str(e)}"

    def generate_content_sync(self, contents, system_instruction: Optional[str] = None):
        """Gera conteúdo não-streaming (para vision worker, agent pre-pass).

        Substitui create_model() + model.generate_content() (sem stream).
        """
        if not self._client:
            raise RuntimeError("GeminiClient has no API key configured")

        is_gemma = "gemma" in self.model_name.lower()
        config = types.GenerateContentConfig(
            system_instruction=None if is_gemma else system_instruction,
        )

        return self._client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=config,
        )

    def upload_file(self, path: str, mime_type: str):
        """Upload file via Gemini File API (novo SDK)."""
        if not self._client:
            raise RuntimeError("GeminiClient has no API key configured")
        return self._client.files.upload(file=path, config={"mime_type": mime_type})

    def get_file(self, name: str):
        """Consulta status de arquivo via Gemini File API."""
        if not self._client:
            raise RuntimeError("GeminiClient has no API key configured")
        return self._client.files.get(name=name)

    def generate_content_rest(
        self, prompt: str, temperature: float = 0.2, thinking_budget: int = 0
    ) -> Optional[str]:
        """Gera conteudo via REST API direta (HTTP puro, sem SDK).

        Thread-safe. Usado por agent workers, memory_analyzer, compaction_service.

        Args:
            prompt: Input text prompt
            temperature: Generation temperature (default: 0.2)
            thinking_budget: Gemini thinking budget in tokens (0=off, 1024=low, 8192=medium, 24576=high)
        """
        full_model = self.model_name if self.model_name.startswith("models/") else f"models/{self.model_name}"
        base_url = f"https://generativelanguage.googleapis.com/v1beta/{full_model}:generateContent"

        payload: dict = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature},
        }

        # Add thinking config for Gemini models that support it
        if thinking_budget > 0:
            payload["generationConfig"]["thinkingConfig"] = {
                "thinkingBudget": thinking_budget
            }

        headers = {"Content-Type": "application/json"}
        url = f"{base_url}?key={self.api_key}"

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()

            if "candidates" in data and data["candidates"]:
                parts = data["candidates"][0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            return None
        except Exception as e:
            logger.error(f"REST API error ({self.model_name}, key={self._masked_key}): {e}")
            return None


class OpenRouterClient:
    """Cliente OpenRouter (DeepSeek, etc) via SDK OpenAI."""

    def __init__(self, api_key: str, model_name: str = "deepseek/deepseek-r1:free"):
        self.model_name = model_name
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )

    def stream_chat(self, messages: list[dict]):
        """Gera resposta em streaming."""
        return self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            stream=True,
        )


class OllamaClient:
    """Cliente para modelos locais via Ollama."""

    def __init__(self, model_name: str = "gpt-oss:20b", api_url: str = "http://localhost:11434/api/chat"):
        self.model_name = model_name
        self.api_url = api_url

    def stream_chat(self, messages: list[dict], ctx_size: int = 4096, think: bool = False):
        """Gera resposta em streaming via Ollama."""
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": 0.7,
                "num_ctx": ctx_size,
                "num_gpu": 999,
                "num_thread": 6,
                "think": think,
            },
        }

        logger.info(f"[OLLAMA] Sending to {self.model_name}...")
        start = time.time()

        try:
            with requests.post(self.api_url, json=payload, stream=True, timeout=600) as r:
                r.raise_for_status()
                first_token = False

                for line in r.iter_lines():
                    if line:
                        try:
                            body = json.loads(line)
                            content = body.get("message", {}).get("content", "")
                            if content:
                                if not first_token:
                                    logger.info(f"[OLLAMA] First token in {time.time() - start:.2f}s")
                                    first_token = True
                                yield content
                        except json.JSONDecodeError:
                            pass

        except requests.exceptions.Timeout:
            yield "\n[TIMEOUT] Model took too long to respond."
        except Exception as e:
            yield f"\n[OLLAMA ERROR] {e}"

    def generate_sync(self, messages: list[dict], ctx_size: int = 4096, think: bool = False) -> str:
        """Gera resposta completa (não-streaming) via Ollama.

        Usado por agent workers que precisam do texto completo
        para validar JSON e aplicar retry logic.

        Args:
            messages: Lista de mensagens [{role, content}]
            ctx_size: Tamanho do contexto (default: 4096)
            think: Enable thinking/reasoning mode (default: False)

        Returns:
            Texto completo da resposta
        """
        options: dict = {
            "temperature": 0.7,
            "num_ctx": ctx_size,
            "num_gpu": 999,
            "num_thread": 6,
        }
        if think:
            options["think"] = True

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": options,
        }

        logger.info(f"[OLLAMA] generate_sync to {self.model_name}...")
        start = time.time()

        try:
            response = requests.post(self.api_url, json=payload, timeout=600)
            response.raise_for_status()
            data = response.json()
            content = data.get("message", {}).get("content", "")
            logger.info(f"[OLLAMA] generate_sync completed in {time.time() - start:.2f}s ({len(content)} chars)")
            return content
        except requests.exceptions.Timeout:
            return "[TIMEOUT] Model took too long to respond."
        except Exception as e:
            logger.error(f"[OLLAMA] generate_sync error: {e}")
            return f"[OLLAMA ERROR] {e}"
