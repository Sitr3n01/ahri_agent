"""
RAG Worker - Retrieval-Augmented Generation for lore and knowledge queries.

Specializes in ChromaDB vector search and synthesizing answers from persona lore.
Uses the configured agent model for context understanding.
"""
import time
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ...models.database import AgentWorkerTask
from ..vector_service import VectorService
from .base_worker import BaseWorker


class RAGWorker(BaseWorker):
    """
    RAG worker for vector database queries and lore retrieval.

    ROLE_PROMPT guides the LLM to focus on synthesis from retrieved documents."""

    ENABLE_EVALUATION = False  # One-shot retrieval + synthesis, no iterative improvement

    ROLE_PROMPT = (
        "[ROLE: Knowledge Retrieval Specialist]\n"
        "You synthesize answers ONLY from the provided retrieved documents.\n"
        "If the documents don't contain the answer, say so explicitly.\n"
        "Cite which document/chunk informed each part of your answer.\n"
        "Never fabricate information not present in the retrieved context.\n"
        "Output: JSON with 'answer', 'sources', and 'confidence' fields."
    )

    """

    Input schema:
    {
        "query": str,              # Question or search query
        "top_k": int               # Number of results to retrieve (default: 5)
    }

    Output schema:
    {
        "answer": str,             # Synthesized answer from retrieved documents
        "sources": [               # List of source documents used
            {
                "text": str,
                "metadata": dict
            }
        ]
    }
    """

    def __init__(self, llm_service, vector_service: Optional[VectorService] = None):
        super().__init__(
            llm_service=llm_service,
            worker_type="RAG",
            default_model="LITE"
        )
        self.vector_service = vector_service or VectorService()

    async def execute(
        self,
        db: AsyncSession,
        execution_id: int,
        input_data: dict
    ) -> AgentWorkerTask:
        """Execute RAG query and return synthesized answer."""
        start_time = time.time()

        # Create task record
        task = await self._create_task_record(db, execution_id, input_data)

        try:
            # Extract input parameters
            query = input_data.get("query", "")
            top_k = input_data.get("top_k", 5)

            if not query:
                raise ValueError("Query is required")

            # Step 1: Retrieve from ChromaDB via search_memory()
            context = self.vector_service.search_memory(
                query=query,
                n_results=top_k,
            )

            if not context.strip():
                output_data = {
                    "answer": f"No information found for query: {query}",
                    "sources": []
                }
                return await self._complete_task(db, task, output_data, 0, start_time)

            # Step 3: Synthesize answer from retrieved docs
            prompt = f"""Based on the following retrieved documents, answer the user's question.

Retrieved Documents:
{context}

User Question: {query}

Instructions:
- Synthesize a clear, accurate answer based ONLY on the provided documents
- If the documents don't contain enough information, say so
- Keep the answer concise (2-3 paragraphs max)
- Cite which documents support your answer when relevant

Answer:"""

            answer = await self._call_llm(prompt, model=self.default_model)

            # Estimate tokens (prompt + response)
            tokens_used = self._estimate_tokens(prompt + answer)

            # Step 4: Format output
            output_data = {
                "answer": answer,
                "sources": context,
            }

            return await self._complete_task(db, task, output_data, tokens_used, start_time)

        except Exception as e:
            return await self._fail_task(db, task, str(e), start_time)
